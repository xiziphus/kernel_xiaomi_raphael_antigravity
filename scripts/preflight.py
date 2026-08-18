#!/usr/bin/env python3
"""Check a kernel tree for the known build-breakers BEFORE burning a 20-min runner.

Usage:  scripts/preflight.py <owner/repo> <ref> [defconfig]

Every check here exists because it actually broke a build in this project. Runs
in seconds against the GitHub API -- no clone. Exit code is non-zero if any
BLOCKER is found; WARNs are advisory.
"""
import json
import re
import subprocess
import sys

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = [a for a in sys.argv[1:] if a.startswith("--")]
REPO, REF = ARGS[0], ARGS[1]
DEFCONFIG = ARGS[2] if len(ARGS) > 2 else "raphael_defconfig"
blockers, warns, notes = [], [], []


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return None if r.returncode else r.stdout


def text(path):
    import base64
    out = gh("repos/%s/contents/%s?ref=%s" % (REPO, path, REF))
    if not out:
        return None
    try:
        return base64.b64decode(json.loads(out)["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def listdir(path):
    out = gh("repos/%s/contents/%s?ref=%s" % (REPO, path, REF))
    if not out:
        return []
    try:
        return [e["name"] for e in json.loads(out)]
    except Exception:
        return []


print("=== preflight %s@%s (defconfig=%s)" % (REPO, REF, DEFCONFIG))

# 0. tree exists / version
mk = text("Makefile")
if not mk:
    print("BLOCKER: cannot read Makefile -- wrong repo or ref?")
    sys.exit(1)
ver = " ".join(l.strip() for l in mk.splitlines()[1:4])
notes.append("version: %s" % ver)

# 1. defconfig present (a missing one fails only after clang is fetched)
cfgs = listdir("arch/arm64/configs")
if DEFCONFIG not in cfgs:
    vend = listdir("arch/arm64/configs/vendor")
    if DEFCONFIG in vend:
        notes.append("defconfig lives under vendor/ -- pass 'vendor/%s'" % DEFCONFIG)
    else:
        blockers.append("defconfig '%s' not in arch/arm64/configs (have: %s)"
                        % (DEFCONFIG, " ".join(sorted(cfgs)[:8])))

# 2. appended-DTB target: 5.4/GKI trees have none, so Image.gz-dtb does not exist
akc = text("arch/arm64/Kconfig") or ""
if "BUILD_ARM64_APPENDED_DTB_IMAGE" not in akc:
    warns.append("no BUILD_ARM64_APPENDED_DTB_IMAGE in arch/arm64/Kconfig -- "
                 "'make Image.gz-dtb' will fail; you MUST pass append_dtb=<base>.dtb")
    # and the named base must actually be reachable: msm trees gate the whole
    # dts Makefile behind a MACH_* symbol, so dtb-y can be empty even though
    # the .dts is sitting right there.
    dmk = text("arch/arm64/boot/dts/qcom/Makefile") or ""
    dts = [n for n in listdir("arch/arm64/boot/dts/qcom") if n.endswith(".dts")]
    notes.append("qcom .dts available: %s" % " ".join(sorted(dts)[:8]))
    gate = re.findall(r"ifeq \(\$\(CONFIG_(\w+)\),y\)", dmk)
    if gate:
        notes.append("dts Makefile gated on: %s -- these must be =y or dtb-y is EMPTY"
                     % ", ".join(sorted(set(gate))))

# 3. Makefile references to source files that were deleted from the tree
amk = text("arch/arm64/kernel/Makefile") or ""
srcs = set(listdir("arch/arm64/kernel"))
for obj in ("perf_trace_counters", "perf_trace_user"):
    if obj + ".o" in amk and obj + ".c" not in srcs:
        warns.append("arch/arm64/kernel/Makefile wants %s.o but %s.c is absent "
                     "(CI strips this automatically)" % (obj, obj))

# 4. the two BPF patch scripts must be able to no-op safely
sysc = text("kernel/bpf/syscall.c") or ""
for cmd in ("BPF_MAP_CREATE", "BPF_PROG_LOAD"):
    m = re.search(r"#define\s+%s_LAST_FIELD\s+(\S+)" % cmd, sysc)
    notes.append("%s_LAST_FIELD = %s" % (cmd, m.group(1) if m else "NOT FOUND"))
    if not m:
        warns.append("%s_LAST_FIELD not found -- bpf_attr patch will skip" % cmd)

uapi = text("include/uapi/linux/bpf.h") or ""
m = re.search(r"enum bpf_map_type \{(.*?)\n\};", uapi, re.S)
if m:
    last = re.findall(r"\bBPF_MAP_TYPE_[A-Z0-9_]+", m.group(1))[-1]
    notes.append("enum bpf_map_type ends at %s" % last)
    if last != "BPF_MAP_TYPE_SOCKMAP" and "DEVMAP_HASH" not in uapi:
        warns.append("map-type backport refuses trees whose enum ends at %s" % last)
notes.append("has DEVMAP_HASH=%s  expected_attach_type=%s  btf.c=%s"
             % ("DEVMAP_HASH" in uapi, "expected_attach_type" in uapi,
                bool(gh("repos/%s/contents/kernel/bpf/btf.c?ref=%s" % (REPO, REF)))))

# 5. pstore: the log channel. Needs a ramoops node AND a pshold node for warm reset.
found_ramoops = found_pshold = False
for f in listdir("arch/arm64/boot/dts/qcom"):
    if not f.endswith((".dts", ".dtsi")):
        continue
    if f not in ("sm8150.dtsi",):
        continue
    t = text("arch/arm64/boot/dts/qcom/" + f) or ""
    found_ramoops = found_ramoops or ("ramoops@" in t)
    found_pshold = found_pshold or ('compatible = "qcom,pshold"' in t)
if not found_ramoops:
    warns.append("no ramoops@ node in sm8150.dtsi -- falls back to the cmdline mechanism")
if not found_pshold:
    warns.append("no qcom,pshold node in sm8150.dtsi -- cannot force warm reset, "
                 "so a clean reboot will WIPE the log")

# 6. Polly hangs the build (20+ min at 99% CPU on one file, never finishes)
if "CONFIG_LLVM_POLLY" in (text("Makefile") or "") or "polly" in (mk or "").lower():
    notes.append("tree references LLVM_POLLY -- ensure it is disabled")


# 11. Submodules / gitlinks. A --depth=1 clone leaves these EMPTY, and a Kconfig
#     `source` or Makefile obj-y pointing into one then kills the build --
#     e.g. Rikka: can't open file "drivers/staging/kernelsu/kernel/Kconfig".
#     This project has hit the same class before (mkbootimg_src is a gitlink
#     with no .gitmodules, so it clones empty), which is why it is checked here
#     rather than waiting to be surprised by it again.
gm = text(".gitmodules")
if gm:
    paths = re.findall(r"path\s*=\s*(\S+)", gm)
    notes.append(".gitmodules declares: %s" % (" ".join(paths) or "(none)"))
    warns.append("%d submodule(s) -- CI inits them and drops dangling Kconfig "
                 "source() lines; without that the build dies at defconfig"
                 % len(paths))
# gitlinks are entries of type "commit"; catch the ones with no .gitmodules too
for probe in ("", "drivers", "drivers/staging"):
    out = gh("repos/%s/contents/%s?ref=%s" % (REPO, probe, REF))
    if not out:
        continue
    try:
        entries = json.loads(out)
    except Exception:
        continue
    if not isinstance(entries, list):
        continue
    for e in entries:
        if e.get("type") == "submodule" or (e.get("type") == "file" and e.get("size") == 0
                                            and e.get("submodule_git_url")):
            where = probe + "/" + e["name"] if probe else e["name"]
            if not gm:
                blockers.append("gitlink '%s' with NO .gitmodules -- clones empty "
                                "and cannot be inited" % where)
            else:
                notes.append("gitlink: %s" % where)


# 12. DRY-RUN every patch script against the real files. Three of the failures
#     so far were our own tooling, not the trees, and an inline heredoc in the
#     workflow could not be tested at all -- hence scripts/, and hence this.
import subprocess, tempfile, shutil
def dry_run():
    need = ["kernel/sys.c", "kernel/bpf/syscall.c", "include/uapi/linux/bpf.h",
            "include/linux/bpf_types.h", "fs/pstore/ram.c",
            "arch/arm64/boot/dts/qcom/sm8150.dtsi"]
    d = tempfile.mkdtemp()
    got = []
    for rel in need:
        t = text(rel)
        if t is None:
            continue
        os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
        open(os.path.join(d, rel), "w", encoding="utf-8").write(t)
        got.append(rel)
    here = os.path.dirname(os.path.abspath(__file__))
    for script, env in (("backport_bpf_map_types.py", {}),
                        ("backport_bpf_attr.py", {}),
                        ("fake_uname_bpfloader.py", {"FAKE_UNAME_RELEASE": "5.4.186"}),
                        ("xiaomi_ramoops.py", {})):
        e = dict(os.environ); e.update(env)
        r = subprocess.run(["python3", os.path.join(here, script)],
                           cwd=d, capture_output=True, text=True, env=e)
        tag = "ok  " if r.returncode == 0 else "FAIL"
        first = (r.stdout.strip().splitlines() or [""])[0]
        err = (r.stderr.strip().splitlines() or [""])[-1]
        print("dryrun : %s %-28s %s" % (tag, script, first or err))
        if r.returncode != 0:
            blockers.append("%s fails on this tree: %s" % (script, err))
    shutil.rmtree(d, ignore_errors=True)

import os
if "--dry-run" in FLAGS:
    dry_run()

for b in blockers:
    print("BLOCKER: " + b)
for w in warns:
    print("WARN   : " + w)
for n in notes:
    print("note   : " + n)
print("=== %s" % ("BLOCKED" if blockers else "ok to build"))
sys.exit(1 if blockers else 0)
