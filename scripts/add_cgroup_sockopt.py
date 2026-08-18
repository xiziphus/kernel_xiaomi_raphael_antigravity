#!/usr/bin/env python3
"""Make BPF_PROG_TYPE_CGROUP_SOCKOPT loadable on a 4.14 tree.

Why only this much
------------------
netd.o's sockopt programs are four instructions each, read straight out of
/apex/com.android.tethering/etc/bpf/netd_shared/netd.o:

    getsockopt/prog, setsockopt/prog:
        r2 = 0
        *(u32 *)(r1 + 32) = r2      ; struct bpf_sockopt.optlen = 0
        r0 = 1
        exit

They call no helpers and touch exactly one context field. So the whole of
upstream 0d01da6afc54 is not needed -- what is needed is that BPF_PROG_LOAD
stops returning EINVAL, which means: the program type must exist, and the
verifier must accept a 4-byte write at offsetof(struct bpf_sockopt, optlen).

(The sendmsg/recvmsg programs in the same object are two instructions,
`r0 = 1; exit`, with no context access at all -- those need nothing beyond the
attach types added by add_cgroup_attach_types.py.)

What this adds
--------------
  uapi/linux/bpf.h   BPF_PROG_TYPE_CGROUP_SOCKOPT = 25, and struct bpf_sockopt
                     laid out to upstream offsets (sk 0, optval 8,
                     optval_end 16, level 24, optname 28, optlen 32, retval 36)
  linux/filter.h     struct bpf_sockopt_kern, the in-kernel counterpart
  linux/bpf_types.h  registers cg_sockopt_prog_ops
  net/core/filter.c  cg_sockopt_is_valid_access + cg_sockopt_convert_ctx_access
                     + the verifier ops, next to cg_sock_addr_prog_ops
  kernel/bpf/syscall.c  accepts BPF_CGROUP_{GET,SET}SOCKOPT for this type

What this deliberately does NOT add: the runtime hooks in
__sys_setsockopt/__sys_getsockopt. A loaded, pinned, attached sockopt program
simply never runs. netbpfload cannot tell the difference -- it loads and pins,
and that is what stands between this ROM and a boot -- but be honest about it:
this makes the kernel *accept* the program, not *honour* it. Adding the two
call sites later is additive and changes nothing here.

Requires add_cgroup_attach_types.py to have run first (for the enum values).
Idempotent.
"""
import os
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
FILTER_H = "include/linux/filter.h"
TYPES = "include/linux/bpf_types.h"
FILTER_C = "net/core/filter.c"
SYSCALL = "kernel/bpf/syscall.c"

STRUCT_UAPI = """
/* Backported for netbpfload: struct bpf_sockopt (5.3, 0d01da6afc54).
 * Pointers are spelled __u64 rather than upstream's __bpf_md_ptr() union,
 * which this tree does not have; the field OFFSETS are what the ABI fixes and
 * they are identical: 0, 8, 16, 24, 28, 32, 36.
 */
struct bpf_sockopt {
	__u64	sk;		/* struct bpf_sock * */
	__u64	optval;
	__u64	optval_end;

	__s32	level;
	__s32	optname;
	__s32	optlen;
	__s32	retval;
};
"""

STRUCT_KERN = """
/* Backported for netbpfload; see scripts/add_cgroup_sockopt.py. */
struct bpf_sockopt_kern {
	struct sock	*sk;
	u8		*optval;
	u8		*optval_end;
	s32		level;
	s32		optname;
	s32		optlen;
	s32		retval;
};
"""

OPS_C = """
/* --- cgroup get/setsockopt (backported, load-only) ----------------------- *
 * See scripts/add_cgroup_sockopt.py. Enough of upstream 0d01da6afc54 for the
 * verifier to accept netd.o's four-instruction programs; the runtime hooks in
 * __sys_{get,set}sockopt are deliberately not wired up.
 */
static const struct bpf_func_proto *
cg_sockopt_func_proto(enum bpf_func_id func_id, const struct bpf_prog *prog)
{
	return bpf_base_func_proto(func_id);
}

static bool cg_sockopt_is_valid_access(int off, int size,
				       enum bpf_access_type type,
				       const struct bpf_prog *prog,
				       struct bpf_insn_access_aux *info)
{
	const int size_default = sizeof(__u32);

	if (off < 0 || off >= sizeof(struct bpf_sockopt))
		return false;
	if (off % size != 0)
		return false;

	if (type == BPF_WRITE) {
		switch (off) {
		case offsetof(struct bpf_sockopt, retval):
		case offsetof(struct bpf_sockopt, optlen):
			return size == size_default;
		default:
			return false;
		}
	}

	switch (off) {
	case offsetof(struct bpf_sockopt, sk):
	case offsetof(struct bpf_sockopt, optval):
	case offsetof(struct bpf_sockopt, optval_end):
		return false;	/* pointer reads need PTR_TO_* plumbing we skip */
	default:
		return size == size_default;
	}
}

static u32 cg_sockopt_convert_ctx_access(enum bpf_access_type type,
					 const struct bpf_insn *si,
					 struct bpf_insn *insn_buf,
					 struct bpf_prog *prog,
					 u32 *target_size)
{
	struct bpf_insn *insn = insn_buf;

#define SOCKOPT_FIELD(F)						       \\
	case offsetof(struct bpf_sockopt, F):				       \\
		if (type == BPF_WRITE)					       \\
			*insn++ = BPF_STX_MEM(BPF_W, si->dst_reg, si->src_reg,  \\
				offsetof(struct bpf_sockopt_kern, F));	       \\
		else							       \\
			*insn++ = BPF_LDX_MEM(BPF_W, si->dst_reg, si->src_reg,  \\
				offsetof(struct bpf_sockopt_kern, F));	       \\
		break

	switch (si->off) {
	SOCKOPT_FIELD(level);
	SOCKOPT_FIELD(optname);
	SOCKOPT_FIELD(optlen);
	SOCKOPT_FIELD(retval);
	}
#undef SOCKOPT_FIELD

	return insn - insn_buf;
}

const struct bpf_verifier_ops cg_sockopt_prog_ops = {
	.get_func_proto		= cg_sockopt_func_proto,
	.is_valid_access	= cg_sockopt_is_valid_access,
	.convert_ctx_access	= cg_sockopt_convert_ctx_access,
};
"""


def edit(path, fn):
    s = open(path, encoding="utf-8", errors="replace").read()
    out = fn(s)
    if out is None:
        return False
    open(path, "w", encoding="utf-8").write(out)
    return True


def main():
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    changed = 0

    # 1. program type + uapi struct
    def f_uapi(s):
        if "BPF_PROG_TYPE_CGROUP_SOCKOPT" in s:
            return None
        m = re.search(r"(enum bpf_prog_type \{\n.*?)(\n\};)", s, re.S)
        if not m:
            sys.exit("FATAL: no 'enum bpf_prog_type' in " + UAPI)
        s = s[:m.end(1)] + "\n\tBPF_PROG_TYPE_CGROUP_SOCKOPT = 25," + s[m.end(1):]
        # put the struct next to the other ctx structs, at end of file before
        # the final #endif so no forward declaration is needed.
        i = s.rfind("#endif")
        return s[:i] + STRUCT_UAPI + "\n" + s[i:]
    if edit(UAPI, f_uapi):
        print("  uapi: BPF_PROG_TYPE_CGROUP_SOCKOPT = 25 + struct bpf_sockopt")
        changed += 1

    # 2. kernel-side struct
    def f_filter_h(s):
        if "bpf_sockopt_kern" in s:
            return None
        anchor = "struct bpf_sock_ops_kern {"
        if anchor not in s:
            sys.exit("FATAL: bpf_sock_ops_kern not found in " + FILTER_H)
        return s.replace(anchor, STRUCT_KERN.lstrip("\n") + "\n" + anchor, 1)
    if edit(FILTER_H, f_filter_h):
        print("  filter.h: struct bpf_sockopt_kern")
        changed += 1

    # 3. register the ops
    def f_types(s):
        if "BPF_PROG_TYPE_CGROUP_SOCKOPT" in s:
            return None
        anchor = "BPF_PROG_TYPE(BPF_PROG_TYPE_CGROUP_SOCK_ADDR, cg_sock_addr_prog_ops)\n"
        if anchor not in s:
            sys.exit("FATAL: cg_sock_addr registration not found in " + TYPES)
        return s.replace(
            anchor,
            anchor + "BPF_PROG_TYPE(BPF_PROG_TYPE_CGROUP_SOCKOPT, cg_sockopt_prog_ops)\n", 1)
    if edit(TYPES, f_types):
        print("  bpf_types.h: registered cg_sockopt_prog_ops")
        changed += 1

    # 4. the ops themselves
    def f_filter_c(s):
        if "cg_sockopt_prog_ops" in s:
            return None
        anchor = "const struct bpf_verifier_ops cg_sock_addr_prog_ops = {"
        i = s.find(anchor)
        if i < 0:
            sys.exit("FATAL: cg_sock_addr_prog_ops not found in " + FILTER_C)
        j = s.index("};\n", i) + 3
        return s[:j] + OPS_C + s[j:]
    if edit(FILTER_C, f_filter_c):
        print("  filter.c: cg_sockopt verifier ops")
        changed += 1

    # 5. let it load
    def f_syscall(s):
        if "BPF_PROG_TYPE_CGROUP_SOCKOPT" in s:
            return None
        anchor = "\tcase BPF_PROG_TYPE_CGROUP_SOCK_ADDR:\n\t\tswitch (expected_attach_type) {\n"
        if anchor not in s:
            sys.exit("FATAL: load-check switch not found in " + SYSCALL)
        arm = ("\tcase BPF_PROG_TYPE_CGROUP_SOCKOPT:\n"
               "\t\tswitch (expected_attach_type) {\n"
               "\t\tcase BPF_CGROUP_GETSOCKOPT:\n"
               "\t\tcase BPF_CGROUP_SETSOCKOPT:\n"
               "\t\t\treturn 0;\n"
               "\t\tdefault:\n"
               "\t\t\treturn -EINVAL;\n"
               "\t\t}\n")
        s = s.replace(anchor, arm + anchor, 1)
        # and let it attach, for whenever netd tries
        a2 = ("\tcase BPF_PROG_TYPE_CGROUP_SOCK:\n"
              "\tcase BPF_PROG_TYPE_CGROUP_SOCK_ADDR:\n"
              "\t\treturn attach_type == prog->expected_attach_type ? 0 : -EINVAL;\n")
        if a2 in s:
            s = s.replace(a2, a2.replace(
                "\tcase BPF_PROG_TYPE_CGROUP_SOCK:\n",
                "\tcase BPF_PROG_TYPE_CGROUP_SOCK:\n\tcase BPF_PROG_TYPE_CGROUP_SOCKOPT:\n"), 1)
        return s
    if edit(SYSCALL, f_syscall):
        print("  syscall.c: CGROUP_SOCKOPT accepted at load and attach")
        changed += 1

    # post-conditions -- an 'applied' message that is not true costs a build
    u = open(UAPI, encoding="utf-8", errors="replace").read()
    for need, where in (("BPF_PROG_TYPE_CGROUP_SOCKOPT", UAPI),
                        ("struct bpf_sockopt {", UAPI)):
        if need not in u:
            sys.exit("FATAL: %s missing from %s after patch" % (need, where))
    for path, need in ((FILTER_H, "bpf_sockopt_kern"),
                       (TYPES, "cg_sockopt_prog_ops"),
                       (FILTER_C, "cg_sockopt_prog_ops"),
                       (SYSCALL, "BPF_CGROUP_GETSOCKOPT")):
        if need not in open(path, encoding="utf-8", errors="replace").read():
            sys.exit("FATAL: %s missing from %s after patch" % (need, path))
    print("  VERIFIED: cgroup sockopt program type is loadable")
    print("  cgroup-sockopt: %s" % ("applied" if changed else "nothing to do"))


if __name__ == "__main__":
    main()
