#!/usr/bin/env python3
"""Assert that every patch we ASKED for actually landed. Run after all patches.

    scripts/verify_patches.py            (env-driven, see below)

Why this exists
---------------
Three separate times a patch script printed "applied" and had changed nothing:

  * accept_rdonly_prog_flag.py added the uapi constant but never widened the
    CREATE_FLAG_MASK macros, so the allocator kept rejecting the flag. Cost: a
    build and a device cycle, and the device reported the identical error as
    before, which looked like the theory was wrong rather than the patch.
  * xiaomi_ramoops.py "fixed" the ramoops node in apq8016-sbc.dtsi (a
    Dragonboard) and stopped, leaving sm8150.dtsi alone.
  * the same script then inserted the node into sa8195-vm-lv.dtsi (another SoC).

Each was a different bug with the same shape: the script matched something that
was not the thing that ships, and had no post-condition to catch it. Fixing them
one at a time does not work -- so this asserts the END STATE of the tree, in one
place, and FAILS THE BUILD rather than producing a kernel that quietly lacks
what was requested.

Driven by the same inputs the workflow used, via environment:
    WANT_FAKE_UNAME=5.4.186     WANT_RDONLY_PROG=true
    WANT_DEVMAP_HASH=true       WANT_LOGGING=true
"""
import os
import re
import sys

fails, oks = [], []


def check(cond, ok_msg, fail_msg):
    (oks if cond else fails).append(ok_msg if cond else fail_msg)


def read(p):
    try:
        return open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


DTSI = "arch/arm64/boot/dts/qcom/sm8150.dtsi"

if os.environ.get("WANT_LOGGING", "true") == "true":
    dt = read(DTSI).lower()
    # The node must be in the dtsi raphael actually builds -- not in whatever
    # unrelated board file happened to sort first.
    check("ramoops@b0000000" in dt,
          "ramoops@b0000000 present in sm8150.dtsi",
          "sm8150.dtsi has NO ramoops@b0000000 -- a failed boot will be SILENT")
    check("qcom,force-warm-reboot" in dt,
          "qcom,force-warm-reboot present in sm8150.dtsi",
          "sm8150.dtsi lacks qcom,force-warm-reboot -- a clean reboot WIPES the log")
    if "ramoops@b0000000" in dt:
        seg = dt[dt.index("ramoops@b0000000"):][:400]
        for want in ("record-size = <0x0>", "console-size = <0x200000>",
                     "pmsg-size = <0x200000>", "ecc-size = <0>"):
            check(want in seg, "ramoops %s" % want,
                  "ramoops geometry wrong: missing '%s' (must match the ROM byte for byte)" % want)

want_uname = os.environ.get("WANT_FAKE_UNAME", "")
if want_uname:
    sysc = read("kernel/sys.c")
    check('"%s"' % want_uname in sysc,
          "kernel/sys.c spoofs uname to %s" % want_uname,
          "kernel/sys.c does NOT contain the release string %s" % want_uname)
    for comm in ("bpfloader", "netbpfload", "netd"):
        check('"%s"' % comm in sysc, "sys.c matches comm %s" % comm,
              "sys.c does not match comm '%s'" % comm)

if os.environ.get("WANT_RDONLY_PROG") == "true":
    uapi = read("include/uapi/linux/bpf.h")
    check("BPF_F_RDONLY_PROG" in uapi, "uapi defines BPF_F_RDONLY_PROG",
          "uapi lacks BPF_F_RDONLY_PROG")
    widened = [p for p in ("kernel/bpf/devmap.c", "kernel/bpf/arraymap.c",
                           "kernel/bpf/hashtab.c", "kernel/bpf/lpm_trie.c",
                           "kernel/bpf/stackmap.c")
               if "BPF_F_RDONLY_PROG" in read(p)]
    check(len(widened) >= 3,
          "CREATE_FLAG_MASK widened in %d allocators" % len(widened),
          "only %d allocator(s) widened -- the map will still mismatch as "
          "flags:128/0, which is exactly the bug this check exists for" % len(widened))

if os.environ.get("WANT_DEVMAP_HASH", "true") == "true":
    uapi = read("include/uapi/linux/bpf.h")
    check("BPF_MAP_TYPE_DEVMAP_HASH" in uapi, "DEVMAP_HASH in the map-type enum",
          "DEVMAP_HASH missing from the map-type enum")

for o in oks:
    print("  ok   %s" % o)
for f in fails:
    print("  FAIL %s" % f)
if fails:
    print("\n%d requested patch(es) did NOT land. Failing now rather than "
          "shipping a kernel that silently lacks them." % len(fails))
    sys.exit(1)
print("\nall %d requested patches verified present" % len(oks))
