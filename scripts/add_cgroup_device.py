#!/usr/bin/env python3
"""Add BPF_PROG_TYPE_CGROUP_DEVICE so runc can start a container on cgroup v2.

Why
---
With the trie fix in, the device boots fully, dockerd runs and `docker pull`
works. `docker run` then fails in the runtime:

    runc create failed: error setting cgroup config for procHooks process:
        bpf_prog_query(BPF_CGROUP_DEVICE) failed: invalid argument

On cgroup v2 the device controller IS BPF -- there is no devices.allow file, so
runc queries the cgroup for an attached BPF_PROG_TYPE_CGROUP_DEVICE program,
loads its own, and attaches it. rikka-v5 has none of that: its
`enum bpf_attach_type` skips 6 and its `enum bpf_prog_type` skips 15.

Upstream is ebc614f68736 ("bpf, cgroup: implement eBPF-based device controller
for cgroup v2", 4.15) -- Rikka is one release short of it.

Hand-fitted rather than lifted
------------------------------
oss-base has this code, but its version routes through cgroup_base_func_proto()
and pulls in 5.x helpers Rikka does not have (bpf_map_push_elem_proto,
bpf_get_local_storage_proto, bpf_get_current_cgroup_id_proto), and it uses the
newer split bpf_prog_ops/bpf_verifier_ops while Rikka still has one combined
struct. So the func_proto is trimmed to the four helpers Rikka actually
exports, and is_valid_access is written as a plain bounds+alignment check
instead of using bpf_ctx_record_field_size(), which lives in a different header
here. Narrow (1/2-byte) context loads are simply rejected; runc's program reads
all three fields as u32.

Scope, stated plainly
---------------------
This makes the program LOAD, ATTACH and QUERY. It does NOT wire up
__cgroup_bpf_check_dev_permission(), so the program never actually runs and
**device restrictions inside containers are not enforced** -- a container that
asks for a device node gets it. For a personal device running trusted images
that is an acceptable trade for `docker run` working at all; it is not
acceptable for running untrusted containers, and the runtime hook is the
obvious follow-up.

Idempotent.
"""
import os
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
TYPES = "include/linux/bpf_types.h"
CGROUP = "kernel/bpf/cgroup.c"
SYSCALL = "kernel/bpf/syscall.c"

CTX = """
/* Backported for runc on cgroup v2; see scripts/add_cgroup_device.py. */
struct bpf_cgroup_dev_ctx {
	/* access_type encoded as (BPF_DEVCG_ACC_* << 16) | BPF_DEVCG_DEV_* */
	__u32 access_type;
	__u32 major;
	__u32 minor;
};

#define BPF_DEVCG_ACC_MKNOD	(1ULL << 0)
#define BPF_DEVCG_ACC_READ	(1ULL << 1)
#define BPF_DEVCG_ACC_WRITE	(1ULL << 2)

#define BPF_DEVCG_DEV_BLOCK	(1ULL << 0)
#define BPF_DEVCG_DEV_CHAR	(1ULL << 1)
"""

OPS = """
/* --- cgroup device controller (backported, load/attach/query only) -------- *
 * See scripts/add_cgroup_device.py. Enough of upstream ebc614f68736 for runc
 * to query, load and attach its device program on cgroup v2. The enforcement
 * hook is deliberately not wired up.
 */
static const struct bpf_func_proto *
cgroup_dev_func_proto(enum bpf_func_id func_id, const struct bpf_prog *prog)
{
	switch (func_id) {
	case BPF_FUNC_map_lookup_elem:
		return &bpf_map_lookup_elem_proto;
	case BPF_FUNC_map_update_elem:
		return &bpf_map_update_elem_proto;
	case BPF_FUNC_map_delete_elem:
		return &bpf_map_delete_elem_proto;
	case BPF_FUNC_get_current_uid_gid:
		return &bpf_get_current_uid_gid_proto;
	case BPF_FUNC_trace_printk:
		if (capable(CAP_SYS_ADMIN))
			return bpf_get_trace_printk_proto();
		/* fall through */
	default:
		return NULL;
	}
}

static bool cgroup_dev_is_valid_access(int off, int size,
				       enum bpf_access_type type,
				       const struct bpf_prog *prog,
				       struct bpf_insn_access_aux *info)
{
	if (type == BPF_WRITE)
		return false;
	if (off < 0 || off + size > sizeof(struct bpf_cgroup_dev_ctx))
		return false;
	if (off % size != 0)
		return false;
	/* Only full 32-bit reads of the three u32 fields. */
	if (size != sizeof(__u32))
		return false;
	return true;
}

const struct bpf_verifier_ops cg_dev_prog_ops = {
	.get_func_proto		= cgroup_dev_func_proto,
	.is_valid_access	= cgroup_dev_is_valid_access,
};
"""


def check_max_attach_type():
    """__MAX_BPF_ATTACH_TYPE must end up >= the largest explicit value.

    It is defined as `previous enumerator + 1`, so ANY new entry placed last
    with a small explicit value silently truncates it. That cost one build and
    two device cycles, with no log to show for it because the kernel died
    before ramoops.
    """
    s = open(UAPI, encoding="utf-8", errors="replace").read()
    body = re.search(r"enum bpf_attach_type \{\n(.*?)\t__MAX_BPF_ATTACH_TYPE",
                     s, re.S).group(1)
    val, biggest, last = -1, -1, -1
    for line in body.splitlines():
        m = re.match(r"\s*(BPF_[A-Z0-9_]+)\s*(?:=\s*(\d+))?\s*,", line)
        if not m:
            continue
        val = int(m.group(2)) if m.group(2) else val + 1
        biggest = max(biggest, val)
        last = val
    if last != biggest:
        sys.exit("FATAL: last attach-type enumerator is %d but the largest is %d "
                 "-- __MAX_BPF_ATTACH_TYPE would be %d and truncate "
                 "cgrp->bpf.progs[]" % (last, biggest, last + 1))
    print("  VERIFIED: __MAX_BPF_ATTACH_TYPE = %d (largest value + 1)" % (biggest + 1))


def main():
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    if "BPF_PROG_TYPE_CGROUP_DEVICE" in open(UAPI, encoding="utf-8",
                                             errors="replace").read():
        print("  cgroup-device: already present")
        return

    # 1. uapi: prog type 15, attach type 6, context struct
    s = open(UAPI, encoding="utf-8", errors="replace").read()
    m = re.search(r"(enum bpf_prog_type \{\n.*?)(\n\};)", s, re.S)
    if not m:
        sys.exit("FATAL: no 'enum bpf_prog_type' in " + UAPI)
    s = s[:m.end(1)] + "\n\tBPF_PROG_TYPE_CGROUP_DEVICE = 15," + s[m.end(1):]
    # Insert in NUMERIC position, never last. __MAX_BPF_ATTACH_TYPE takes the
    # value of the preceding enumerator + 1, so appending "= 6" just before it
    # collapsed MAX from 23 to 7 -- which shrinks cgrp->bpf.progs[]/effective[]
    # and makes every attach type >= 7 index out of bounds. The kernel panicked
    # before ramoops came up, so it booted nothing and logged nothing.
    anchor = "\tBPF_SK_SKB_STREAM_VERDICT,\n"
    if anchor not in s:
        sys.exit("FATAL: expected BPF_SK_SKB_STREAM_VERDICT in the attach enum")
    s = s.replace(anchor, anchor + "\tBPF_CGROUP_DEVICE = 6,\n", 1)
    i = s.rfind("#endif")
    s = s[:i] + CTX + "\n" + s[i:]
    open(UAPI, "w", encoding="utf-8").write(s)
    print("  uapi: BPF_PROG_TYPE_CGROUP_DEVICE=15, BPF_CGROUP_DEVICE=6, ctx struct")

    # 2. register the ops
    s = open(TYPES, encoding="utf-8", errors="replace").read()
    a = "BPF_PROG_TYPE(BPF_PROG_TYPE_CGROUP_SOCK_ADDR, cg_sock_addr_prog_ops)\n"
    if a not in s:
        sys.exit("FATAL: cg_sock_addr registration not found in " + TYPES)
    open(TYPES, "w", encoding="utf-8").write(
        s.replace(a, a + "BPF_PROG_TYPE(BPF_PROG_TYPE_CGROUP_DEVICE, cg_dev_prog_ops)\n", 1))
    print("  bpf_types.h: registered cg_dev_prog_ops")

    # 3. the ops themselves, appended to cgroup.c
    s = open(CGROUP, encoding="utf-8", errors="replace").read()
    if "EXPORT_SYMBOL(__cgroup_bpf_run_filter_sock_ops);" not in s:
        sys.exit("FATAL: expected anchor missing from " + CGROUP)
    open(CGROUP, "w", encoding="utf-8").write(s.rstrip("\n") + "\n" + OPS)
    print("  cgroup.c: cg_dev verifier ops")

    # 4. load / attach / detach / query -- all four, as ever
    s = open(SYSCALL, encoding="utf-8", errors="replace").read()
    sockops = "\tcase BPF_CGROUP_SOCK_OPS:\n\t\tptype = BPF_PROG_TYPE_SOCK_OPS;\n"
    n = s.count(sockops)
    if n != 2:
        sys.exit("FATAL: expected the SOCK_OPS arm twice (attach, detach) in %s, "
                 "found %d" % (SYSCALL, n))
    s = s.replace(sockops,
                  "\tcase BPF_CGROUP_DEVICE:\n"
                  "\t\tptype = BPF_PROG_TYPE_CGROUP_DEVICE;\n"
                  "\t\tbreak;\n" + sockops)
    q = "\tcase BPF_CGROUP_SOCK_OPS:\n\t\tbreak;\n"
    if q not in s:
        sys.exit("FATAL: bpf_prog_query switch not found in " + SYSCALL)
    s = s.replace(q, "\tcase BPF_CGROUP_DEVICE:\n" + q, 1)
    open(SYSCALL, "w", encoding="utf-8").write(s)
    print("  syscall.c: CGROUP_DEVICE wired into attach, detach and query")

    # post-conditions
    s = open(SYSCALL, encoding="utf-8", errors="replace").read()
    if s.count("ptype = BPF_PROG_TYPE_CGROUP_DEVICE;\n\t\tbreak;") != 2:
        sys.exit("FATAL: CGROUP_DEVICE attach/detach arms missing their break")
    if s.count("case BPF_CGROUP_DEVICE:") != 3:
        sys.exit("FATAL: BPF_CGROUP_DEVICE appears %d times in %s, expected 3"
                 % (s.count("case BPF_CGROUP_DEVICE:"), SYSCALL))
    check_max_attach_type()
    print("  VERIFIED: cgroup device program type loadable, attachable, queryable")


if __name__ == "__main__":
    main()
