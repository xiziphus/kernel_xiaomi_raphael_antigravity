#!/usr/bin/env python3
"""Make BPF_MAP_TYPE_DEVMAP_HASH (25) creatable on a stock 4.14 raphael tree.

Why this exists
---------------
On KameOS (HyperOS 3 / Android 16) a bool-x 16-HyperMiui kernel boots and runs
init, then dies with `reboot,bpfloader-failed`. The cause, read straight out of
the ROM's own BPF objects:

    /apex/com.android.tethering/etc/bpf/tethering/offload.o   [critical]
        tether_dev_map   type=25 (BPF_MAP_TYPE_DEVMAP_HASH)
                         key_size=4 value_size=4 max_entries=64
                         min_kver=0  max_kver=inf

`min_kver=0` means Android does NOT version-gate this map -- it is required on
every kernel, including 4.14 -- and `offload.o` is marked `critical`, so if the
map cannot be created bpfloader exits non-zero and init reboots the device.

DEVMAP_HASH landed upstream in 5.4 (6f9d451ab1a3). bool-x's enum stops at
15:SOCKMAP, so the map type does not exist and creation fails with EINVAL.
Everything *else* Android needs is already supported on this tree: all required
program types, all 12 helpers the required programs call, no JMP32
instructions, and the 4.17-5.10 cgroup hooks (bind/connect/sendmsg/recvmsg/
get+setsockopt) are correctly min_kver-gated and skipped on 4.14. This single
map type is the whole blocker.

What this does
--------------
1. Extends `enum bpf_map_type` in include/uapi/linux/bpf.h with the upstream
   entries 16..25, so that DEVMAP_HASH lands on exactly 25 -- the numeric value
   bpfloader passes in. The intermediate entries are declared but not
   registered; creating one returns EINVAL, which is correct and harmless
   because every map using them is either optional or min_kver-gated above
   4.14 (checked: XSKMAP only in osrtpPolicy.o [optional]; RINGBUF gated to
   5.10).
2. Registers DEVMAP_HASH in include/linux/bpf_types.h against the tree's
   existing `dev_map_ops`.

On the aliasing, honestly
-------------------------
This maps DEVMAP_HASH onto the index-array DEVMAP implementation rather than
backporting the real hash table. dev_map_alloc's validation
(key_size==4, value_size==4, max_entries!=0) accepts tether_dev_map's 4/4/64
exactly, so creation succeeds and bpfloader proceeds. The semantic difference
only shows up in tethering *hardware offload*: a DEVMAP is indexed, so an
ifindex >= max_entries returns -E2BIG on update and NULL on lookup instead of
hashing. Tethering still works over the normal software path, and the BPF
programs already handle a NULL lookup. That is an acceptable trade for booting;
a faithful port of 6f9d451ab1a3 would need bpf_map_charge_init /
bpf_map_init_from_attr, which this 4.14 tree does not have.

Idempotent: safe to run twice, and a no-op on trees that already have the type
(the openela lineage does).
"""
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
TYPES = "include/linux/bpf_types.h"

# Upstream order; DEVMAP_HASH must come out as 25.
NEW_TYPES = [
    "BPF_MAP_TYPE_CPUMAP",                  # 16
    "BPF_MAP_TYPE_XSKMAP",                  # 17
    "BPF_MAP_TYPE_SOCKHASH",                # 18
    "BPF_MAP_TYPE_CGROUP_STORAGE",          # 19
    "BPF_MAP_TYPE_REUSEPORT_SOCKARRAY",     # 20
    "BPF_MAP_TYPE_PERCPU_CGROUP_STORAGE",   # 21
    "BPF_MAP_TYPE_QUEUE",                   # 22
    "BPF_MAP_TYPE_STACK",                   # 23
    "BPF_MAP_TYPE_SK_STORAGE",              # 24
    "BPF_MAP_TYPE_DEVMAP_HASH",             # 25
]


def patch_uapi() -> bool:
    src = open(UAPI, encoding="utf-8", errors="replace").read()
    if "BPF_MAP_TYPE_DEVMAP_HASH" in src:
        print("  uapi/linux/bpf.h: DEVMAP_HASH already present, skipping")
        return False
    m = re.search(r"(enum bpf_map_type \{\n)(.*?)(\n\};)", src, re.S)
    if not m:
        sys.exit("FATAL: could not find 'enum bpf_map_type' in " + UAPI)
    body = m.group(2)
    existing = re.findall(r"\bBPF_MAP_TYPE_[A-Z0-9_]+", body)
    if existing[-1] != "BPF_MAP_TYPE_SOCKMAP":
        sys.exit(f"FATAL: enum ends at {existing[-1]}, expected BPF_MAP_TYPE_SOCKMAP.\n"
                 "       Numbering would not line up; refusing to guess.")
    add = "".join(f"\n\t{t}," for t in NEW_TYPES)
    out = src[:m.end(2)] + add + src[m.end(2):]
    open(UAPI, "w", encoding="utf-8").write(out)
    # verify the numbering came out right
    body2 = re.search(r"enum bpf_map_type \{\n(.*?)\n\};", out, re.S).group(1)
    names = re.findall(r"\bBPF_MAP_TYPE_[A-Z0-9_]+", body2)
    idx = names.index("BPF_MAP_TYPE_DEVMAP_HASH")
    if idx != 25:
        sys.exit(f"FATAL: DEVMAP_HASH landed at {idx}, must be 25")
    print(f"  uapi/linux/bpf.h: added {len(NEW_TYPES)} types; DEVMAP_HASH = 25 OK")
    return True


def patch_types() -> bool:
    src = open(TYPES, encoding="utf-8", errors="replace").read()
    if "BPF_MAP_TYPE_DEVMAP_HASH" in src:
        print("  bpf_types.h: already registered, skipping")
        return False
    line = "BPF_MAP_TYPE(BPF_MAP_TYPE_DEVMAP, dev_map_ops)\n"
    if line not in src:
        sys.exit("FATAL: DEVMAP registration not found in " + TYPES)
    # Register inside the same CONFIG_NET guard, right after DEVMAP.
    src = src.replace(line, line + "BPF_MAP_TYPE(BPF_MAP_TYPE_DEVMAP_HASH, dev_map_ops)\n", 1)
    open(TYPES, "w", encoding="utf-8").write(src)
    print("  bpf_types.h: registered DEVMAP_HASH -> dev_map_ops")
    return True


if __name__ == "__main__":
    a = patch_uapi()
    b = patch_types()
    print("  backport applied" if (a or b) else "  nothing to do (tree already supports it)")
