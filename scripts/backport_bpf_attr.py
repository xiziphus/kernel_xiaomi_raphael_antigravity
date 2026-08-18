#!/usr/bin/env python3
"""Let a modern netbpfload talk to bool-x's 4.14 bpf() syscall.

Why this exists
---------------
bool-x reaches init on KameOS and then dies `reboot,bpfloader-failed`, and
every structural explanation has been eliminated: the map types, program types,
attach types (the 4.19/5.4-gated ones are correctly skipped on 4.14) and all 16
helpers the required programs call are present. `backport_bpf_map_types.py`
fixed a genuine defect (DEVMAP_HASH) and it still failed.

The remaining mechanism is not a missing feature -- it is the ABI check.

bool-x carries a PARTIAL Android backport of `union bpf_attr`: it has
`map_name`, `prog_name` and `file_flags`, but not `btf_fd`, `btf_key_type_id`,
`btf_value_type_id`, `map_ifindex`, `expected_attach_type`, `prog_btf_fd`,
`func_info*` or `line_info*`. Meanwhile kernel/bpf/syscall.c says:

    #define BPF_MAP_CREATE_LAST_FIELD map_name
    #define BPF_PROG_LOAD_LAST_FIELD  prog_name

and CHECK_ATTR() runs memchr_inv() from the end of LAST_FIELD all the way to
sizeof(union bpf_attr), rejecting the call with **EINVAL** if any byte is
nonzero. The syscall entry adds a second guard, check_uarg_tail_zero(), which
returns **-E2BIG** for nonzero bytes past the union entirely.

So a loader built against modern uapi headers -- which netbpfload is; its own
strings include `bpf_create_map[%s] btf:%d -> %d`, and the objects declare
`btf_min_bpfloader_ver=42` against a `bpfloader_min_ver=43`, so BTF *is*
attempted -- writes fields this kernel does not know about, and the kernel
refuses the syscall before ever looking at the map type or the program. That is
consistent with the one thing we could never explain: DEVMAP_HASH was a real
bug, fixing it changed nothing, because map creation was failing for a reason
that has nothing to do with the map.

What this does
--------------
Extends the two command structs to the upstream 5.4 layout and moves the
LAST_FIELD markers to match, so the kernel ACCEPTS and IGNORES the extra
metadata. Field order is upstream's exactly -- the offsets have to line up with
what userspace writes, so this is a layout fix, not a feature.

It deliberately does NOT implement BTF. Nothing here needs BTF to work: the
loader has a retry and a "marked optional - continuing..." path, and KameOS's
own kernel exposes no /sys/kernel/btf yet boots. Tolerating the fields is
enough, and it is a few dozen lines instead of transplanting btf.c.

Ignoring `expected_attach_type` is safe here specifically because every program
this ROM loads on a 4.14 kernel resolves to attach type 0 -- the sock_addr and
sockopt programs that would actually need it are min_kver-gated to 4.19/5.4 and
never attempted.

Idempotent, and a no-op on trees that already have the modern layout.
"""
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
SYSCALL = "kernel/bpf/syscall.c"

MAP_ADD = """		__u32	map_ifindex;	/* ifindex of netdev to create on */
		__u32	btf_fd;		/* fd pointing to a BTF type data */
		__u32	btf_key_type_id;	/* BTF type_id of the key */
		__u32	btf_value_type_id;	/* BTF type_id of the value */
"""

PROG_ADD = """		__u32		prog_ifindex;	/* ifindex of netdev to prep for */
		__u32		expected_attach_type;
		__u32		prog_btf_fd;	/* fd pointing to BTF type data */
		__u32		func_info_rec_size;
		__aligned_u64	func_info;
		__u32		func_info_cnt;
		__u32		line_info_rec_size;
		__aligned_u64	line_info;
		__u32		line_info_cnt;
"""


def patch_uapi() -> bool:
    src = open(UAPI, encoding="utf-8", errors="replace").read()
    if "btf_value_type_id" in src and "expected_attach_type" in src:
        print("  uapi: modern bpf_attr already present, skipping")
        return False
    out = src
    changed = False

    if "btf_value_type_id" not in out:
        m = re.search(r"(\n\t\tchar\smap_name\[BPF_OBJ_NAME_LEN\];\n)", out)
        if not m:
            sys.exit("FATAL: could not find map_name in BPF_MAP_CREATE attr")
        out = out[:m.end(1)] + MAP_ADD + out[m.end(1):]
        changed = True
        print("  uapi: BPF_MAP_CREATE += map_ifindex, btf_fd, btf_key_type_id, btf_value_type_id")

    if "expected_attach_type" not in out:
        m = re.search(r"(\n\t\tchar\t\tprog_name\[BPF_OBJ_NAME_LEN\];\n)", out)
        if not m:
            sys.exit("FATAL: could not find prog_name in BPF_PROG_LOAD attr")
        out = out[:m.end(1)] + PROG_ADD + out[m.end(1):]
        changed = True
        print("  uapi: BPF_PROG_LOAD += prog_ifindex, expected_attach_type, prog_btf_fd, func_info*, line_info*")

    if changed:
        open(UAPI, "w", encoding="utf-8").write(out)
    return changed


def patch_syscall() -> bool:
    src = open(SYSCALL, encoding="utf-8", errors="replace").read()
    out = src
    for cmd, old, new in (
        ("BPF_MAP_CREATE", "map_name", "btf_value_type_id"),
        ("BPF_PROG_LOAD", "prog_name", "line_info_cnt"),
    ):
        pat = re.compile(r"(#define\s+%s_LAST_FIELD\s+)%s\b" % (cmd, old))
        if not pat.search(out):
            if re.search(r"#define\s+%s_LAST_FIELD\s+%s\b" % (cmd, new), out):
                print("  syscall.c: %s_LAST_FIELD already %s" % (cmd, new))
                continue
            sys.exit("FATAL: could not find %s_LAST_FIELD %s" % (cmd, old))
        out = pat.sub(r"\g<1>" + new, out)
        print("  syscall.c: %s_LAST_FIELD %s -> %s" % (cmd, old, new))
    if out != src:
        open(SYSCALL, "w", encoding="utf-8").write(out)
        return True
    return False


if __name__ == "__main__":
    a = patch_uapi()
    b = patch_syscall()
    print("  bpf_attr: %s" % ("applied" if (a or b) else "nothing to do"))
