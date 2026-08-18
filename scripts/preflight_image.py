#!/usr/bin/env python3
"""Decide whether a boot.img is worth a device cycle.

    scripts/preflight_image.py <boot.img> [--expect "what this should prove"]

The runner is free and parallel; the phone is not. A device test costs a reboot,
~2 minutes, and often a physical power press -- i.e. it costs the human. So an
image should not reach the phone unless it can (a) actually run, (b) leave
evidence behind, and (c) tell us something we do not already know.

Three questions, in order:

  1. CAN IT BOOT?      header fields FBE depends on, a kernel of plausible size,
                       an appended DTB.
  2. CAN IT TALK?      ramoops geometry + warm reset + the cmdline trigger. An
                       image without these produces a silent failure, which is
                       the single most expensive outcome: it burns the cycle and
                       yields nothing. Most of this project's wasted device time
                       went exactly here.
  3. IS IT NEW?        a fingerprint of (kernel bytes) against a ledger of what
                       has already been tested, so the same image is not booted
                       twice by accident.
"""
import hashlib
import json
import os
import re
import struct
import subprocess
import sys

LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "builds", ".tested.json")
args = [a for a in sys.argv[1:] if not a.startswith("--")]
expect = None
if "--expect" in sys.argv:
    expect = sys.argv[sys.argv.index("--expect") + 1]
if not args:
    sys.exit(__doc__)
IMG = args[0]

blockers, warns, notes = [], [], []
d = open(IMG, "rb").read()
if d[:8] != b"ANDROID!":
    sys.exit("BLOCKER: not an Android boot image")

kernel_size, kernel_addr, ramdisk_size = struct.unpack_from("<III", d, 8)[0], 0, struct.unpack_from("<I", d, 16)[0]
page = struct.unpack_from("<I", d, 36)[0]
os_ver = struct.unpack_from("<I", d, 44)[0]
cmdline = d[64:64+512].split(b"\x00")[0].decode("utf-8", "replace")
notes.append("kernel %.1f MB, ramdisk %.1f MB, pagesize %d" % (kernel_size/1e6, ramdisk_size/1e6, page))

# ---- 1. can it boot -------------------------------------------------------
# os_version/patch_level are packed: (ver<<11)|patch. FBE derives keys from these.
patch = os_ver & 0x7ff
y, m = 2000 + (patch >> 4), patch & 0xf
notes.append("os_patch_level %04d-%02d" % (y, m))
if (y, m) != (2022, 11):
    blockers.append("os_patch_level is %04d-%02d, KameOS's stock is 2022-11 -- "
                    "FBE derives keys from this and a mismatch costs /data" % (y, m))
if kernel_size < 8_000_000:
    warns.append("kernel is only %.1f MB -- suspiciously small" % (kernel_size/1e6))
ko = page
kern = d[ko:ko+kernel_size]
if not kern.startswith(b"\x1f\x8b"):
    warns.append("kernel does not start with gzip magic")
if kern.count(b"\xd0\x0d\xfe\xed") == 0:
    blockers.append("no appended DTB found in the kernel blob")
else:
    notes.append("appended DTBs: %d" % kern.count(b"\xd0\x0d\xfe\xed"))

# ---- 2. can it talk -------------------------------------------------------
if "ramoops_memreserve" not in cmdline:
    warns.append("cmdline lacks ramoops_memreserve -- only matters for trees "
                 "using the vendor cmdline path, but it is free to include")
mk = re.search(r"androidboot\.ktest=(\S+)", cmdline)
if not mk:
    blockers.append("no androidboot.ktest marker -- a failed boot would be "
                    "indistinguishable from a success")
else:
    notes.append("ktest marker: %s" % mk.group(1))
# ramoops + warm reset live in the appended DTB
have_ramoops = b"ramoops" in kern
have_warm = b"qcom,force-warm-reboot" in kern
notes.append("DTB: ramoops=%s force-warm-reboot=%s" % (have_ramoops, have_warm))
if not have_warm:
    blockers.append("DTB has no qcom,force-warm-reboot -- a clean reboot WIPES "
                    "pstore on this device, so a userspace failure leaves NO log. "
                    "This is the most expensive way to spend a device cycle.")
if not have_ramoops:
    warns.append("no ramoops node in the DTB (cmdline mechanism may still apply)")

# ---- 3. is it new ---------------------------------------------------------
fp = hashlib.sha256(kern).hexdigest()[:16]
notes.append("kernel fingerprint %s" % fp)
ledger = {}
if os.path.exists(LEDGER):
    try: ledger = json.load(open(LEDGER))
    except Exception: ledger = {}
if fp in ledger:
    prev = ledger[fp]
    blockers.append("this exact kernel was already tested as '%s' -> %s"
                    % (prev.get("name"), prev.get("result", "?")))

for b in blockers: print("BLOCKER: " + b)
for w in warns:    print("WARN   : " + w)
for n in notes:    print("note   : " + n)
if expect: print("expect : " + expect)
print("=== %s" % ("DO NOT TEST" if blockers else "worth a device cycle"))
sys.exit(1 if blockers else 0)
