#!/usr/bin/env python3
"""Verify a BUILT kernel image actually contains the required CONFIG options.

Why this exists
---------------
Checking `out/.config` is not enough. On 2026-08-15 a CI build merged
docker.config, ran olddefconfig, printed "config OK" for all 12 required
options -- and still shipped a kernel with `# CONFIG_PID_NS is not set`.
The build step's own `--silentoldconfig` re-resolved the config after the
check and dropped the dependency-gated options.

The only source of truth is the config embedded *inside the compiled image*
(CONFIG_IKCONFIG=y stores it, gzipped, between IKCFG_ST/IKCFG_ED markers).
That is what /proc/config.gz serves at runtime, and it is what this reads --
straight out of the Image.gz-dtb, before anything is ever flashed.

Usage:
    verify_kernel_config.py <Image.gz-dtb> [--require OPT[,OPT...]] [--forbid OPT[,OPT...]]
    verify_kernel_config.py <Image.gz-dtb> --dump out.config

Exit status: 0 = all requirements met, 1 = a requirement failed / no config found.
"""
import argparse
import re
import sys
import zlib

DEFAULT_REQUIRE = [
    "NAMESPACES", "PID_NS", "NET_NS", "IPC_NS", "UTS_NS",
    "CGROUPS", "CGROUP_PIDS", "CGROUP_DEVICE", "CGROUP_FREEZER",
    "CPUSETS", "MEMCG", "KEYS", "VETH", "BRIDGE", "OVERLAY_FS",
    "POSIX_MQUEUE", "NETFILTER", "NETFILTER_XT_MATCH_ADDRTYPE",
    "NF_NAT", "IP_NF_NAT", "IP_NF_TARGET_MASQUERADE",
]
# Options that must NOT be on (LLVM_POLLY hangs this tree's build; see CLAUDE.md).
DEFAULT_FORBID = ["LLVM_POLLY"]


def gunzip_at(data: bytes, start: int) -> bytes:
    """Decompress the gzip stream beginning at `start`, ignoring trailing data
    (Image.gz-dtb carries an appended DTB after the gzip stream)."""
    return zlib.decompressobj(31).decompress(data[start:])


def extract_config(path: str) -> str:
    raw = open(path, "rb").read()

    # The image may be raw vmlinux-ish or gzip-compressed (Image.gz / Image.gz-dtb).
    blobs = [raw]
    gz = raw.find(b"\x1f\x8b\x08")
    if gz >= 0:
        try:
            blobs.insert(0, gunzip_at(raw, gz))
        except zlib.error:
            pass

    for blob in blobs:
        marker = blob.find(b"IKCFG_ST")
        if marker < 0:
            continue
        tail = blob[marker + len(b"IKCFG_ST"):]
        inner = tail.find(b"\x1f\x8b\x08")
        if inner < 0 or inner > 16:
            continue
        try:
            return gunzip_at(tail, inner).decode("utf-8", errors="replace")
        except zlib.error:
            continue

    sys.exit(
        f"FATAL: no embedded config found in {path}.\n"
        "       Build with CONFIG_IKCONFIG=y so the image carries its own config,\n"
        "       otherwise the build cannot be verified before flashing."
    )


def banner_version(path: str) -> str:
    """The kernel's own 'Linux version X.Y.Z...' string."""
    raw = open(path, "rb").read()
    for blob in (raw, *( [gunzip_at(raw, raw.find(b"\x1f\x8b\x08"))]
                         if raw.find(b"\x1f\x8b\x08") >= 0 else [] )):
        m = re.search(rb"Linux version (\d+\.\d+\.\d+)", blob)
        if m:
            return m.group(1).decode()
    return ""


def decoy_check(path: str, config: str) -> None:
    """Refuse to verify a kernel whose embedded config is a decoy.

    Several raphael trees (SOVIET-ANDROID, HeliumStudio, VoltageOS, rikka...)
    carry Sultan Alsawaf's "use the stock raphael config for /proc/config.gz"
    patch, which rewrites kernel/Makefile:

        $(obj)/config_data.gz: arch/arm64/configs/raphael-vts_defconfig FORCE

    instead of the normal $(KCONFIG_CONFIG). The image then embeds a checked-in
    defconfig -- NOT what was compiled -- and /proc/config.gz serves that same
    lie at runtime. Verified 2026-08-17: a SOVIET 4.14.357 build embedded
    raphael-vts_defconfig (4.14.226) verbatim, which says
    '# CONFIG_PID_NS is not set' regardless of what the build actually enabled.

    The tell is the version: the config header declares a different kernel than
    the banner. When that happens the only trustworthy sources are the build's
    own out/.config / out/include/generated/autoconf.h, or a functional check on
    the running device (/proc/cgroups, /proc/self/ns, /proc/filesystems).
    """
    m = re.search(r"^# Linux/\S+ (\d+\.\d+\.\d+) Kernel Configuration", config, re.M)
    if not m:
        return
    cfg_ver, kern_ver = m.group(1), banner_version(path)
    if kern_ver and cfg_ver != kern_ver:
        sys.exit(
            f"FATAL: embedded config is a DECOY, not this kernel's config.\n"
            f"       kernel banner says {kern_ver}, embedded config says {cfg_ver}.\n"
            f"       This tree redirects config_data.gz at a checked-in defconfig,\n"
            f"       so neither this check nor /proc/config.gz can tell you what was\n"
            f"       compiled. Verify against the build's out/.config (post-build) or\n"
            f"       functionally on-device: /proc/cgroups, /proc/self/ns, unshare.\n"
            f"       To make builds honest, point config_data.gz back at\n"
            f"       $(KCONFIG_CONFIG) in kernel/Makefile."
        )


def state_of(config: str, opt: str) -> str:
    """Return 'y', 'm', a literal value, 'n' (explicitly unset), or 'absent'."""
    m = re.search(rf"^CONFIG_{re.escape(opt)}=(.*)$", config, re.M)
    if m:
        return m.group(1)
    if re.search(rf"^# CONFIG_{re.escape(opt)} is not set$", config, re.M):
        return "n"
    return "absent"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--require", default=",".join(DEFAULT_REQUIRE))
    ap.add_argument("--forbid", default=",".join(DEFAULT_FORBID))
    ap.add_argument("--dump", help="write the extracted config to this path")
    args = ap.parse_args()

    config = extract_config(args.image)
    if args.dump:
        open(args.dump, "w").write(config)
    decoy_check(args.image, config)

    banner = re.search(r"^CONFIG_LOCALVERSION=.*$", config, re.M)
    total = len(re.findall(r"^CONFIG_\w+=", config, re.M))
    print(f"embedded config: {len(config)} bytes, {total} options set"
          + (f"  [{banner.group()}]" if banner else ""))

    failures = []
    require = [o for o in args.require.split(",") if o]
    forbid = [o for o in args.forbid.split(",") if o]

    for opt in require:
        st = state_of(config, opt)
        ok = st in ("y", "m")
        print(f"  {'OK  ' if ok else 'FAIL'}  CONFIG_{opt} = {st}")
        if not ok:
            failures.append(f"CONFIG_{opt} is '{st}', expected y/m")

    for opt in forbid:
        st = state_of(config, opt)
        ok = st not in ("y", "m")
        print(f"  {'OK  ' if ok else 'FAIL'}  CONFIG_{opt} = {st}  (must be off)")
        if not ok:
            failures.append(f"CONFIG_{opt} is '{st}', must be off")

    if failures:
        print("\nFAILED -- the compiled kernel does not match what was requested:")
        for f in failures:
            print(f"  - {f}")
        print("\nThe image would boot but silently lack these features. Not shipping it.")
        return 1

    print(f"\nPASS -- all {len(require)} required options present in the COMPILED image.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
