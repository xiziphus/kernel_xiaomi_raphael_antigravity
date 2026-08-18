#!/usr/bin/env python3
"""Let 4.14 maps accept BPF_F_RDONLY_PROG / BPF_F_WRONLY_PROG (5.2 flags).

Read straight off the device (X3, bool-x claiming 5.4):

    NetBpfLoad: bpf map name tether_dev_map mismatch:
                desired/found: type:25/25 key:4/4 value:4/4 entries:64/64 flags:128/0
    NetBpfLoad: Failed to create maps: (ret=-76)  [-ENOTUNIQ]

Everything matches except the flags. 128 is BPF_F_RDONLY_PROG (5.2); the loader
asks for it, a 4.14 map allocator rejects or drops it, the readback reports 0,
the loader compares desired vs found and refuses the map.

Both flags only restrict what BPF *programs* may do to a map (read-only or
write-only from the program side). Accepting and recording them without
enforcing is safe for our purpose -- the maps in question are written by
userspace and read by the programs -- and it is what lets the loader's
comparison succeed.

This is deliberately the small fix. A full BPF graft also solves it, but costs
a 5.4 core; if this alone gets past map creation it is far less invasive.
"""
import os
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
SYSCALL = "kernel/bpf/syscall.c"
DEVMAP = "kernel/bpf/devmap.c"


def add_flag_defs():
    src = open(UAPI, encoding="utf-8", errors="replace").read()
    if "BPF_F_RDONLY_PROG" in src:
        print("  uapi: RDONLY_PROG/WRONLY_PROG already defined")
        return False
    m = re.search(r"#define BPF_F_ZERO_SEED\s+\(1U << (\d+)\)\n", src)
    anchor = m.group(0) if m else None
    if not anchor:
        m = re.search(r"#define BPF_F_STACK_BUILD_ID\s+\(1U << (\d+)\)\n", src)
        anchor = m.group(0) if m else None
    if not anchor:
        sys.exit("FATAL: no BPF_F_* anchor found in " + UAPI)
    add = ("/* Flags for accessing BPF object from program side. */\n"
           "#define BPF_F_RDONLY_PROG\t(1U << 7)\n"
           "#define BPF_F_WRONLY_PROG\t(1U << 8)\n")
    open(UAPI, "w", encoding="utf-8").write(src.replace(anchor, anchor + add, 1))
    print("  uapi: added BPF_F_RDONLY_PROG (1<<7) / BPF_F_WRONLY_PROG (1<<8)")
    return True


def widen_flag_masks():
    """Let the allocators through. 4.14 validates with masks like
    `attr->map_flags & ~BPF_F_NUMA_NODE`, which rejects anything newer."""
    n = 0
    for path in (DEVMAP, "kernel/bpf/arraymap.c", "kernel/bpf/hashtab.c",
                 "kernel/bpf/lpm_trie.c", SYSCALL):
        if not os.path.exists(path):
            continue
        src = open(path, encoding="utf-8", errors="replace").read()
        out = src
        # Widen the "unknown flag" masks to also permit the two new bits.
        out = re.sub(r"~\(BPF_F_NUMA_NODE\)", "~(BPF_F_NUMA_NODE | BPF_F_RDONLY_PROG | BPF_F_WRONLY_PROG)", out)
        out = re.sub(r"~BPF_F_NUMA_NODE\b", "~(BPF_F_NUMA_NODE | BPF_F_RDONLY_PROG | BPF_F_WRONLY_PROG)", out)
        out = re.sub(r"~\(BPF_F_NO_PREALLOC \| BPF_F_NO_COMMON_LRU \| BPF_F_NUMA_NODE\)",
                     "~(BPF_F_NO_PREALLOC | BPF_F_NO_COMMON_LRU | BPF_F_NUMA_NODE | BPF_F_RDONLY_PROG | BPF_F_WRONLY_PROG)", out)
        if out != src:
            open(path, "w", encoding="utf-8").write(out)
            print("  %s: widened map_flags mask" % path)
            n += 1
    return n


if __name__ == "__main__":
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    a = add_flag_defs()
    b = widen_flag_masks()
    print("  rdonly-prog: %s" % ("applied" if (a or b) else "nothing to do"))
