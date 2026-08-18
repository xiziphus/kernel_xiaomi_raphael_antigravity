#!/usr/bin/env python3
"""Make BPF_MAP_TYPE_XSKMAP (17) creatable so Xiaomi's osrtpPolicy.o loads.

Where this comes from
---------------------
With the cgroup attach types and the sockopt program type in place, netd.o
loads completely on rikka-v5 -- all 27 code sections, get/setsockopt included.
The next object in the same directory then stops the boot:

    NetBpfLoad: Loading ELF object .../netd_shared/osrtpPolicy.o
    NetBpfLoad: bpf_create_map[mi_xsk_port_map] btf:0 -> -1 errno:22
    NetBpfLoad: Failed to create maps: (ret=-22) in .../osrtpPolicy.o
    NetBpfLoad: === CRITICAL FAILURE LOADING BPF PROGRAMS FROM .../netd_shared/ ===

`optional` is a property of a *program*; a map that cannot be created fails the
whole object, and one failed object fails the directory. osrtpPolicy.o is
Xiaomi's own (an RTP policy XDP program); its `xdp/xdp_sock` section is
`optional=0, min_kver=0`, i.e. required on every kernel.

Decoding its map section: type=17 key=4 value=4 max_entries=1024 flags=0 --
BPF_MAP_TYPE_XSKMAP, which arrived with AF_XDP in 4.18. rikka-v5 has no
net/xdp/ at all, so CONFIG_XDP_SOCKETS is not an option here. (KameOS's own
kernel does have the real thing: `xsk_map_alloc` and `__xsk_map_redirect` are
both in its kallsyms.)

What this does
--------------
Registers type 17 against the tree's existing `array_map_ops`, whose
array_map_alloc validation (key_size==4, value_size!=0, max_entries!=0,
map_flags within ARRAY_CREATE_FLAG_MASK) accepts 4/4/1024/0 exactly, and
teaches the verifier that XSKMAP is a legal map for bpf_redirect_map -- the
only helper the program uses it with (the other two helper calls,
map_lookup_elem and map_update_elem, act on the object's second map, a plain
HASH).

NOT dev_map_ops, which was the first choice and failed on device:

    bpf map name mi_xsk_port_map mismatch: desired/found:
        type:17/17 key:4/4 value:4/4 entries:1024/1024 flags:0/128

kernel/bpf/devmap.c:121 does `attr->map_flags |= BPF_F_RDONLY_PROG;` ("Lookup
returns a pointer straight to dev->ifindex, so make sure the verifier prevents
writes from the BPF side"). The loader asks for flags=0 on an XSKMAP, reads
back 128, and refuses the map with -ENOTUNIQ.

That same line is the answer to the long-standing bool-x mystery, from the
other direction: bool-x's older dev_map_alloc does NOT force the flag, so when
the loader asked for BPF_F_RDONLY_PROG on tether_dev_map it read back 0 --
`flags:128/0`. Widening the CREATE_FLAG_MASKs could never fix that, which is
why it did not. The flag is set by the allocator, not accepted from userspace.

Being honest about the aliasing: this makes the map *creatable and verifiable*,
not functional. A real XSKMAP redirects into an AF_XDP socket's ring; an array
holds plain u32s. Nothing ever populates this map -- that would need an AF_XDP
socket fd, and there are none on this kernel -- so the lookup inside
bpf_redirect_map finds nothing and the program falls through to XDP_PASS. The
cost is that Xiaomi's RTP fast path does not accelerate. The benefit is that
the device boots.

Idempotent, and a no-op on trees that already have XSKMAP.
"""
import os
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
TYPES = "include/linux/bpf_types.h"
VERIFIER = "kernel/bpf/verifier.c"


def main():
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    changed = 0

    src = open(UAPI, encoding="utf-8", errors="replace").read()
    if "BPF_MAP_TYPE_XSKMAP" in src:
        print("  uapi: XSKMAP already present")
    else:
        m = re.search(r"(enum bpf_map_type \{\n)(.*?)(\n\};)", src, re.S)
        if not m:
            sys.exit("FATAL: no 'enum bpf_map_type' in " + UAPI)
        # Explicit value: the surrounding entries are sparse on this tree
        # (SOCKMAP=15, then DEVMAP_HASH=25), so position must not be inferred.
        src = src[:m.end(2)] + "\n\tBPF_MAP_TYPE_XSKMAP = 17," + src[m.end(2):]
        open(UAPI, "w", encoding="utf-8").write(src)
        print("  uapi: BPF_MAP_TYPE_XSKMAP = 17")
        changed += 1

    src = open(TYPES, encoding="utf-8", errors="replace").read()
    if "BPF_MAP_TYPE_XSKMAP" in src:
        print("  bpf_types.h: already registered")
    else:
        anchor = "BPF_MAP_TYPE(BPF_MAP_TYPE_ARRAY, array_map_ops)\n"
        if anchor not in src:
            sys.exit("FATAL: ARRAY registration not found in " + TYPES)
        src = src.replace(
            anchor, anchor + "BPF_MAP_TYPE(BPF_MAP_TYPE_XSKMAP, array_map_ops)\n", 1)
        open(TYPES, "w", encoding="utf-8").write(src)
        print("  bpf_types.h: XSKMAP -> array_map_ops")
        changed += 1

    src = open(VERIFIER, encoding="utf-8", errors="replace").read()
    if "BPF_MAP_TYPE_XSKMAP" in src:
        print("  verifier.c: already allows XSKMAP")
    else:
        a1 = "\tcase BPF_MAP_TYPE_DEVMAP:\n"
        # Extend the EXISTING condition. Prefixing another `if (...)  &&` line
        # ahead of it produced two consecutive `if`s and
        # "verifier.c:1810: error: expected expression".
        a2 = "\t\t    map->map_type != BPF_MAP_TYPE_DEVMAP_HASH)\n"
        if a1 not in src or a2 not in src:
            sys.exit("FATAL: redirect_map compatibility check not found in " + VERIFIER)
        src = src.replace(a1, a1 + "\tcase BPF_MAP_TYPE_XSKMAP:\n", 1)
        src = src.replace(
            a2,
            "\t\t    map->map_type != BPF_MAP_TYPE_DEVMAP_HASH &&\n"
            "\t\t    map->map_type != BPF_MAP_TYPE_XSKMAP)\n", 1)
        open(VERIFIER, "w", encoding="utf-8").write(src)
        print("  verifier.c: bpf_redirect_map accepts XSKMAP")
        changed += 1

    for path, need in ((UAPI, "BPF_MAP_TYPE_XSKMAP = 17"),
                       (TYPES, "BPF_MAP_TYPE(BPF_MAP_TYPE_XSKMAP, array_map_ops)"),
                       (VERIFIER, "case BPF_MAP_TYPE_XSKMAP:")):
        if need not in open(path, encoding="utf-8", errors="replace").read():
            sys.exit("FATAL: %r missing from %s after patch" % (need, path))
    print("  VERIFIED: XSKMAP creatable and legal for bpf_redirect_map")
    print("  xskmap-alias: %s" % ("applied" if changed else "nothing to do"))


if __name__ == "__main__":
    main()
