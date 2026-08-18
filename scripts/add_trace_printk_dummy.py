#!/usr/bin/env python3
"""Give bpf_trace_printk a no-op implementation on a tree without BPF_EVENTS.

Xiaomi's osrtpPolicy.o calls helper 6 (bpf_trace_printk) from its XDP program,
and that program is `optional=0, min_kver=0` -- required on every kernel. On a
tree with CONFIG_BPF_EVENTS off, kernel/trace/bpf_trace.c is not compiled, the
weak bpf_get_trace_printk_proto() in kernel/bpf/core.c returns NULL, and the
verifier rejects the program with "unknown func bpf_trace_printk".

KameOS's own kernel solves it exactly this way rather than by enabling tracing.
Its kallsyms carry:

    T bpf_trace_printk_dummy
    W bpf_get_trace_printk_proto

i.e. a strong dummy helper, with the weak accessor still the linked one --
returning the dummy's proto instead of NULL. (Confirming the program really
does load there: /sys/fs/bpf/netd_shared/prog_osrtpPolicy_xdp_xdp_sock is
pinned on the running ROM.) The same patch is already in bool-x and in a dozen
other 4.14 Xiaomi trees; rikka-v5 is the one that lacks it.

Enabling CONFIG_FTRACE/TRACING to get the real helper is not an option here:
it breaks these trees at compile time (binder_trace.h references undeclared
binder_command_strings, trace_event_perf.c redefines `event`), and KameOS
demonstrates the dummy is sufficient.

The helper returns 0 and prints nothing. A BPF program that logs for debugging
gets silence, which is the correct trade against not booting.

Idempotent.
"""
import os
import sys

CORE = "kernel/bpf/core.c"

OLD = """const struct bpf_func_proto * __weak bpf_get_trace_printk_proto(void)
{
	return NULL;
}"""

NEW = """/* Backported from KameOS's own kernel (T bpf_trace_printk_dummy); see
 * scripts/add_trace_printk_dummy.py. Without CONFIG_BPF_EVENTS there is no
 * real bpf_trace_printk, and returning NULL here makes the verifier reject
 * every program that calls helper 6 -- including Xiaomi's non-optional
 * osrtpPolicy.o XDP program, which is enough to stop the boot.
 */
BPF_CALL_5(bpf_trace_printk_dummy, char *, fmt, u32, fmt_size, u64, arg1,
	   u64, arg2, u64, arg3)
{
	return 0;
}

static const struct bpf_func_proto bpf_trace_printk_dummy_proto = {
	.func		= bpf_trace_printk_dummy,
	.gpl_only	= true,
	.ret_type	= RET_INTEGER,
	.arg1_type	= ARG_PTR_TO_MEM,
	.arg2_type	= ARG_CONST_SIZE,
};

const struct bpf_func_proto * __weak bpf_get_trace_printk_proto(void)
{
	return &bpf_trace_printk_dummy_proto;
}"""

if __name__ == "__main__":
    if not os.path.exists(CORE):
        sys.exit("FATAL: run from the kernel tree root")
    s = open(CORE, encoding="utf-8", errors="replace").read()
    if "bpf_trace_printk_dummy" in s:
        print("  core.c: dummy trace_printk already present")
        sys.exit(0)
    if OLD not in s:
        sys.exit("FATAL: weak bpf_get_trace_printk_proto returning NULL not found "
                 "in %s -- this tree may already provide the real helper" % CORE)
    open(CORE, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
    s = open(CORE, encoding="utf-8", errors="replace").read()
    if "return &bpf_trace_printk_dummy_proto;" not in s:
        sys.exit("FATAL: patch did not take")
    print("  core.c: bpf_trace_printk now resolves to a no-op proto")
