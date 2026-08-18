#!/usr/bin/env python3
"""Add the cgroup attach types netbpfload demands of a kernel claiming 5.4.

Read straight off the device (S3rk = rikka-v5 + fake_uname 5.4.186, with
ignore_loglevel + printk.devkmsg=on so netbpfload's own output survives):

    NetBpfLoad: NetBpfLoad v0.47 ... api:36/36 kver:50400ba
    NetBpfLoad: detected 5 of 5: 2025Q2 api:36.0.0
    NetBpfLoad: BPF_PROG_LOAD call for .../netd_shared/netd.o
                (recvmsg4_udp4_recvmsg) returned fd: -1 (Invalid argument)
    NetBpfLoad: non-optional program recvmsg4_udp4_recvmsg failed to load.

Everything before that succeeded: tethering/offload.o loaded, tether_dev_map
was created (Rikka has the real dev_map_hash_ops, so bool-x's flags:128/0 wall
never appears), and the 5.10-gated ringbuf map was correctly skipped. The one
thing missing is the attach type.

rikka-v5's `enum bpf_attach_type` stops at BPF_CGROUP_INET6_POST_BIND (13). A
kernel claiming 5.4 is offered netd.o's 4.19- and 5.4-gated programs, and
bpf_prog_load_check_attach_type() rejects every expected_attach_type it does
not name -- hence EINVAL at load, before the verifier is ever reached.

Stage 1 (this script, ~20 lines of kernel change):
  * declare attach types 14,15 (UDP sendmsg) and 19,20 (UDP recvmsg) and
    21,22 (cgroup get/setsockopt), with EXPLICIT numbers so 16-18
    (LIRC_MODE2, FLOW_DISSECTOR, CGROUP_SYSCTL) stay unclaimed and the
    numbering matches the ABI netbpfload compiled against.
  * accept the sendmsg/recvmsg four in the CGROUP_SOCK_ADDR arm of
    bpf_prog_load_check_attach_type(), and let them attach.

That is all sendmsg/recvmsg need: they reuse BPF_PROG_TYPE_CGROUP_SOCK_ADDR
and `struct bpf_sock_addr`, both of which Rikka already implements for
bind/connect. No new program type, no new context, no verifier work.

What this deliberately does NOT do: call the programs. Upstream adds
__cgroup_bpf_run_filter_sock_addr() hooks inside udp_sendmsg/udp_recvmsg;
without them a loaded sendmsg/recvmsg program is attached and never runs. For
netbpfload that is invisible -- it loads and pins, and netd attaches -- and it
is the difference between a device that boots and one that does not. The
runtime hooks are a separate, additive change.

Idempotent, and a no-op on trees that already have the types.
"""
import os
import re
import sys

UAPI = "include/uapi/linux/bpf.h"
SYSCALL = "kernel/bpf/syscall.c"

# (name, value) -- explicit so unclaimed slots stay unclaimed.
NEW_ATTACH = [
    ("BPF_CGROUP_UDP4_SENDMSG", 14),
    ("BPF_CGROUP_UDP6_SENDMSG", 15),
    ("BPF_CGROUP_UDP4_RECVMSG", 19),
    ("BPF_CGROUP_UDP6_RECVMSG", 20),
    ("BPF_CGROUP_GETSOCKOPT", 21),
    ("BPF_CGROUP_SETSOCKOPT", 22),
]
# Only these route through the existing CGROUP_SOCK_ADDR program type.
SOCK_ADDR = ["BPF_CGROUP_UDP4_SENDMSG", "BPF_CGROUP_UDP6_SENDMSG",
             "BPF_CGROUP_UDP4_RECVMSG", "BPF_CGROUP_UDP6_RECVMSG"]


def patch_uapi():
    src = open(UAPI, encoding="utf-8", errors="replace").read()
    m = re.search(r"(enum bpf_attach_type \{\n)(.*?)(\t__MAX_BPF_ATTACH_TYPE)",
                  src, re.S)
    if not m:
        sys.exit("FATAL: no 'enum bpf_attach_type' in " + UAPI)
    body = m.group(2)
    missing = [(n, v) for n, v in NEW_ATTACH if not re.search(r"\b%s\b" % n, body)]
    if not missing:
        print("  uapi: all attach types already present")
        return False
    add = "".join("\t%s = %d,\n" % (n, v) for n, v in missing)
    src = src[:m.start(3)] + add + src[m.start(3):]
    open(UAPI, "w", encoding="utf-8").write(src)
    print("  uapi: added %s" % ", ".join(n for n, _ in missing))
    return True


def patch_syscall():
    src = open(SYSCALL, encoding="utf-8", errors="replace").read()
    anchor = "\t\tcase BPF_CGROUP_INET6_CONNECT:\n\t\t\treturn 0;\n"
    if anchor not in src:
        sys.exit("FATAL: CGROUP_SOCK_ADDR arm of bpf_prog_load_check_attach_type "
                 "not found in " + SYSCALL + " -- refusing to guess")
    if "BPF_CGROUP_UDP4_SENDMSG" in src:
        print("  syscall.c: sendmsg/recvmsg already accepted")
        return False
    add = "".join("\t\tcase %s:\n" % n for n in SOCK_ADDR)
    src = src.replace(anchor,
                      "\t\tcase BPF_CGROUP_INET6_CONNECT:\n" + add + "\t\t\treturn 0;\n",
                      1)
    open(SYSCALL, "w", encoding="utf-8").write(src)
    print("  syscall.c: CGROUP_SOCK_ADDR now accepts sendmsg4/6 + recvmsg4/6")
    return True


def verify():
    """Post-condition. A patch script that reports success without changing the
    tree is worse than one that fails: three builds have already been spent on
    'applied' messages that were not true."""
    u = open(UAPI, encoding="utf-8", errors="replace").read()
    s = open(SYSCALL, encoding="utf-8", errors="replace").read()
    bad = [n for n, _ in NEW_ATTACH if n not in u]
    if bad:
        sys.exit("FATAL: attach types missing after patch: " + " ".join(bad))
    bad = [n for n in SOCK_ADDR if "case %s:" % n not in s]
    if bad:
        sys.exit("FATAL: not accepted at load time: " + " ".join(bad))
    print("  VERIFIED: 6 attach types declared, 4 accepted for CGROUP_SOCK_ADDR")


if __name__ == "__main__":
    if not os.path.exists(UAPI):
        sys.exit("FATAL: run from the kernel tree root")
    a = patch_uapi()
    b = patch_syscall()
    verify()
    print("  attach-types: %s" % ("applied" if (a or b) else "nothing to do"))
