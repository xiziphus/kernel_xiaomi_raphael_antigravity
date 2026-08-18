#!/usr/bin/env python3
"""Predict whether a kernel build will succeed AND produce what we asked for.

    scripts/preflight.py <owner/repo> <ref> [defconfig] [--dry-run] [--json]

Two questions, in order of importance:

  1. Will the options we care about actually reach the compiled kernel?
     This is the one that matters. `merge_config.sh` retention can be a clean
     63/63 while the build still drops options at olddefconfig time, and CI
     only notices ~20 minutes in ("CONFIG_X lost at config time"). A symbol
     that is not DEFINED anywhere in the tree's Kconfig can never survive, and
     that is checkable in seconds.

  2. Will it build at all?
     Defconfig present, appended-DTB target, dangling Makefile objects, empty
     submodules, and the tree-specific landmines already recorded in CLAUDE.md.

Everything is driven off ONE recursive tree listing rather than dozens of
per-path probes, so it is fast enough that there is no excuse to skip it --
and scripts/launch_build.sh refuses to dispatch without it.
"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
FLAGS = [a for a in sys.argv[1:] if a.startswith("--")]
if len(ARGS) < 2:
    sys.exit(__doc__)
REPO, REF = ARGS[0], ARGS[1]
DEFCONFIG = ARGS[2] if len(ARGS) > 2 else "raphael_defconfig"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

blockers, warns, notes = [], [], []


def gh(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return None if r.returncode else r.stdout


def text(path):
    out = gh("repos/%s/contents/%s?ref=%s" % (REPO, path, REF))
    if not out:
        return None
    try:
        return base64.b64decode(json.loads(out)["content"]).decode("utf-8", "replace")
    except Exception:
        return None


# ---------------------------------------------------------------- one tree read
tree, truncated = set(), False
raw = gh("repos/%s/git/trees/%s?recursive=1" % (REPO, REF))
if raw:
    try:
        j = json.loads(raw)
        truncated = j.get("truncated", False)
        tree = {e["path"]: e for e in j.get("tree", [])}
    except Exception:
        tree = {}
if not tree:
    blockers.append("could not read the git tree for %s@%s" % (REPO, REF))
    print("BLOCKER: " + blockers[-1])
    sys.exit(1)
if truncated:
    warns.append("git tree listing was TRUNCATED -- path checks are incomplete")

has = lambda p: p in tree
notes.append("%d paths%s" % (len(tree), " (truncated)" if truncated else ""))

mk = text("Makefile") or ""
notes.append("version: " + " ".join(l.strip() for l in mk.splitlines()[1:4]))

# ------------------------------------------------- 1. will our options survive?
wanted = []
dc = os.path.join(ROOT, "docker.config")
if os.path.exists(dc):
    for line in open(dc):
        m = re.match(r"CONFIG_(\w+)=", line.strip())
        if m:
            wanted.append(m.group(1))
if wanted:
    # Which symbols does this tree actually DEFINE? One code-search per miss is
    # far too slow, so scan the Kconfig files we can cheaply reach and treat
    # "not found anywhere we looked" as a warning rather than a hard blocker.
    kconfigs = [p for p in tree
                if os.path.basename(p) == "Kconfig" or os.path.basename(p).startswith("Kconfig.")]
    notes.append("%d Kconfig files in tree" % len(kconfigs))
    defined = set()
    # Grep the handful of Kconfigs that define the vast majority of what we want.
    for probe in ("init/Kconfig", "net/Kconfig", "net/netfilter/Kconfig",
                  "net/ipv4/netfilter/Kconfig", "net/ipv6/netfilter/Kconfig",
                  "fs/Kconfig", "fs/overlayfs/Kconfig", "drivers/net/Kconfig",
                  "net/bridge/Kconfig", "net/sched/Kconfig", "security/Kconfig",
                  "net/core/Kconfig", "kernel/Kconfig.preempt", "mm/Kconfig"):
        if not has(probe):
            continue
        t = text(probe) or ""
        for m in re.finditer(r"^\s*(?:menu)?config\s+(\w+)", t, re.M):
            defined.add(m.group(1))
    missing = [w for w in wanted if w not in defined]
    notes.append("docker.config: %d options, %d confirmed defined"
                 % (len(wanted), len(wanted) - len(missing)))
    if missing:
        warns.append("not confirmed in the Kconfigs sampled (may live elsewhere, "
                     "but these are the ones that go missing at config time): %s"
                     % " ".join(missing[:12]))

# ------------------------------------------------------- 2. will it build at all
cfgdir = "arch/arm64/configs/"
cfgs = sorted(p[len(cfgdir):] for p in tree if p.startswith(cfgdir) and "/" not in p[len(cfgdir):])
if DEFCONFIG not in cfgs:
    if has(cfgdir + "vendor/" + DEFCONFIG):
        notes.append("defconfig is under vendor/ -- pass 'vendor/%s'" % DEFCONFIG)
    else:
        blockers.append("defconfig '%s' absent (have: %s)" % (DEFCONFIG, " ".join(cfgs[:8])))

akc = text("arch/arm64/Kconfig") or ""
if "BUILD_ARM64_APPENDED_DTB_IMAGE" not in akc:
    warns.append("no appended-DTB target -- Image.gz-dtb WILL fail; pass append_dtb=<base>.dtb")
    dmk = text("arch/arm64/boot/dts/qcom/Makefile") or ""
    gates = sorted(set(re.findall(r"ifeq \(\$\(CONFIG_(\w+)\),y\)", dmk)))
    if gates:
        warns.append("dts Makefile gated on %s -- if unset, dtb-y is EMPTY and no base dtb is built"
                     % ", ".join(gates))

amk = text("arch/arm64/kernel/Makefile") or ""
for obj in ("perf_trace_counters", "perf_trace_user"):
    if obj + ".o" in amk and not has("arch/arm64/kernel/%s.c" % obj):
        notes.append("dangling Makefile object %s.o (CI strips it)" % obj)

gm = text(".gitmodules")
if gm:
    paths = re.findall(r"path\s*=\s*(\S+)", gm)
    warns.append("submodule(s) %s -- empty on --depth=1; CI inits or drops their Kconfig source()"
                 % " ".join(paths))

# tree-specific landmines, straight out of CLAUDE.md
dcfg = text(cfgdir + DEFCONFIG) or ""
for sym, why in (("CONFIG_FTRACE", "binder_trace.h undeclared strings; 9 errors"),
                 ("CONFIG_DEBUG_FS", "ipa_eth.c calls undeclared debugfs helpers under -Werror"),
                 ("CONFIG_MODULES", "stub-regulator exports an __init fn; mismatches are fatal here")):
    if re.search(r"^%s=y" % sym, dcfg, re.M):
        warns.append("%s=y in the defconfig -- %s" % (sym, why))
if re.search(r"^# CONFIG_LLVM_POLLY is not set", dcfg, re.M):
    notes.append("LLVM_POLLY disabled (good -- it HANGS, 20+ min on one file)")
elif "LLVM_POLLY" in (text("Makefile") or ""):
    warns.append("LLVM_POLLY not explicitly disabled -- it hangs the build rather than failing")

# BPF/pstore facts the patches key off
sysc = text("kernel/bpf/syscall.c") or ""
for cmd in ("BPF_MAP_CREATE", "BPF_PROG_LOAD"):
    m = re.search(r"#define\s+%s_LAST_FIELD\s+(\S+)" % cmd, sysc)
    notes.append("%s_LAST_FIELD = %s" % (cmd, m.group(1) if m else "NOT FOUND"))
uapi = text("include/uapi/linux/bpf.h") or ""
hooks = [k for k in ("BPF_CGROUP_INET4_BIND", "BPF_CGROUP_INET4_CONNECT",
                     "BPF_CGROUP_UDP4_SENDMSG", "BPF_CGROUP_UDP4_RECVMSG",
                     "BPF_CGROUP_GETSOCKOPT", "BPF_CGROUP_SETSOCKOPT",
                     "BPF_PROG_TYPE_CGROUP_SOCKOPT", "BPF_PROG_TYPE_CGROUP_SOCK_ADDR")
         if k in uapi]
notes.append("cgroup hook set: %d/8%s" % (len(hooks), "" if len(hooks) == 8 else "  -> needs a bpf_donor if claiming >=4.19"))
notes.append("DEVMAP_HASH=%s btf.c=%s fake-uname=%s"
             % ("DEVMAP_HASH" in uapi, has("kernel/bpf/btf.c"), "fake uname" in (text("kernel/sys.c") or "")))
sm = text("arch/arm64/boot/dts/qcom/sm8150.dtsi") or ""
if 'compatible = "qcom,pshold"' not in sm:
    warns.append("no qcom,pshold node -- cannot force warm reset, so a clean reboot WIPES the log")
if "ramoops@" not in sm:
    notes.append("no ramoops@ node -- falls back to the ramoops_memreserve cmdline path")

# ------------------------------------------------------------------ 3. dry-run
if "--dry-run" in FLAGS:
    d = tempfile.mkdtemp()
    for rel in ("kernel/sys.c", "kernel/bpf/syscall.c", "include/uapi/linux/bpf.h",
                "include/linux/bpf_types.h", "fs/pstore/ram.c",
                "arch/arm64/boot/dts/qcom/sm8150.dtsi"):
        t = text(rel)
        if t is None:
            continue
        os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
        open(os.path.join(d, rel), "w", encoding="utf-8").write(t)
    for script, env in (("backport_bpf_map_types.py", {}), ("backport_bpf_attr.py", {}),
                        ("fake_uname_bpfloader.py", {"FAKE_UNAME_RELEASE": "5.4.186"}),
                        ("xiaomi_ramoops.py", {})):
        e = dict(os.environ); e.update(env)
        r = subprocess.run(["python3", os.path.join(HERE, script)], cwd=d,
                           capture_output=True, text=True, env=e)
        head = (r.stdout.strip().splitlines() or [""])[0]
        tail = (r.stderr.strip().splitlines() or [""])[-1]
        print("dryrun : %s %-28s %s" % ("ok  " if not r.returncode else "FAIL",
                                        script, head or tail))
        if r.returncode:
            blockers.append("%s fails on this tree: %s" % (script, tail))
    shutil.rmtree(d, ignore_errors=True)

for b in blockers:
    print("BLOCKER: " + b)
for w in warns:
    print("WARN   : " + w)
for n in notes:
    print("note   : " + n)
if "--json" in FLAGS:
    print(json.dumps({"repo": REPO, "ref": REF, "blockers": blockers, "warns": warns}))
print("=== %s" % ("BLOCKED" if blockers else "ok to build"))
sys.exit(1 if blockers else 0)
