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
    """Add whichever of the two flags is missing -- independently.

    Rikka already defines BPF_F_RDONLY_PROG but not BPF_F_WRONLY_PROG. The
    first version bailed out if EITHER was present, so it added neither, while
    widen_flag_masks() still referenced both -- and the smoke gate caught
    `use of undeclared identifier 'BPF_F_WRONLY_PROG'` in 11 seconds.
    """
    src = open(UAPI, encoding="utf-8", errors="replace").read()
    want = [("BPF_F_RDONLY_PROG", 7), ("BPF_F_WRONLY_PROG", 8)]
    missing = [(n, b) for n, b in want if n not in src]
    if not missing:
        print("  uapi: both RDONLY_PROG and WRONLY_PROG already defined")
        return False
    anchor = None
    for cand in ("BPF_F_ZERO_SEED", "BPF_F_STACK_BUILD_ID", "BPF_F_RDONLY_PROG",
                 "BPF_F_RDONLY", "BPF_F_NUMA_NODE", "BPF_F_NO_COMMON_LRU",
                 "BPF_F_NO_PREALLOC"):
        m = re.search(r"#define %s\s+\(1U << \d+\)\n" % cand, src)
        if m:
            anchor = m.group(0)
            break
    if not anchor:
        print("  uapi: no BPF_F_* anchor; skipping")
        return False
    add = "".join("#define %s\t(1U << %d)\n" % (n, b) for n, b in missing)
    open(UAPI, "w", encoding="utf-8").write(src.replace(anchor, anchor + add, 1))
    print("  uapi: added %s" % ", ".join(n for n, _ in missing))
    return True


def widen_flag_masks():
    """Widen the *_CREATE_FLAG_MASK macros.

    First attempt targeted the usage site (`attr->map_flags & ~BPF_F_NUMA_NODE`)
    and matched nothing, because every allocator masks with a macro:

        #define DEV_CREATE_FLAG_MASK \\
            (BPF_F_NUMA_NODE | BPF_F_RDONLY | BPF_F_WRONLY)
        ... attr->map_flags & ~DEV_CREATE_FLAG_MASK

    The script reported "applied" purely on the uapi defines, the allocator kept
    rejecting the flag, and the device came back with the identical
    flags:128/0 mismatch. Patch the macro, and verify something actually changed.
    """
    n = 0
    # The five allocators all end their mask list with `BPF_F_WRONLY)`, and that
    # exact text appears nowhere else, so a literal substitution is both
    # sufficient and safer than a multi-line regex (the regex version silently
    # matched nothing and the script still reported "applied").
    OLD = "BPF_F_RDONLY | BPF_F_WRONLY)"
    NEW = "BPF_F_RDONLY | BPF_F_WRONLY | BPF_F_RDONLY_PROG | BPF_F_WRONLY_PROG)"
    for path in ("kernel/bpf/devmap.c", "kernel/bpf/arraymap.c", "kernel/bpf/hashtab.c",
                 "kernel/bpf/lpm_trie.c", "kernel/bpf/stackmap.c",
                 "kernel/bpf/sockmap.c", "kernel/bpf/cpumap.c"):
        if not os.path.exists(path):
            continue
        src = open(path, encoding="utf-8", errors="replace").read()
        if "BPF_F_RDONLY_PROG" in src:
            continue
        if OLD not in src:
            continue
        open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW))
        print("  %s: widened CREATE_FLAG_MASK" % path)
        n += 1
    if not n:
        print("  WARNING: no CREATE_FLAG_MASK widened -- allocators will still "
              "reject BPF_F_RDONLY_PROG and the map will mismatch as flags:128/0")
    return n


if __name__ == "__main__":
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    a = add_flag_defs()
    b = widen_flag_masks()
    print("  rdonly-prog: %s" % ("applied" if (a or b) else "nothing to do"))
