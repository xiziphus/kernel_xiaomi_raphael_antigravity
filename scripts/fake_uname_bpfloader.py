#!/usr/bin/env python3
"""Report a >=4.19 kernel release to Android's BPF loader, and only to it.

THE ROOT CAUSE
--------------
Recovered from a real boot log on 2026-08-18 (bool-x on KameOS, warm-reset
pstore):

    [   14.565835] NetBpfLoad: Android V requires kernel 4.19.
    [   14.571829] init: Service bpfloader has 'reboot_on_failure' option and
                   failed, shutting down system.

netbpfload hard-refuses to run on a kernel older than 4.19. It is a plain
version gate, checked before it looks at a single BPF feature. That single
line invalidates every theory we chased for the missing map type, the missing
cgroup attach types, BTF, and the bpf_attr layout: none of them were ever
reached. `reboot,bpfloader-failed` on any 4.14 kernel under Android V/W means
this, until proven otherwise.

The gate reads uname()'s release field, so the fix is to spoof that field --
and only for the loader. Taken from
waffleowo/kernel_xiaomi_raphael_bpf@bpf-5.4-backport, whose history walks the
whole idea ("Fake uname to 4.19 also for netbpfload" -> "Only fake uname on
very first call" -> "Increase bpf fake uname to 5.4.186"). KameOS's own
4.14.356-Zundamon kernel must carry the same trick: it reports 4.14.356 to the
shell yet satisfies netbpfload.

WHAT VERSION TO CLAIM, AND THE CATCH
------------------------------------
Claiming a version is a promise. netbpfload skips programs whose min_kver is
above the running kernel, so the number chosen decides how much the loader will
then demand:

  claim 4.19  -> it will now attempt bind4/6, connect4/6, udp sendmsg/recvmsg,
                 which need the CGROUP_SOCK_ADDR hooks (4.17+).
  claim 5.4   -> all of the above plus getsockopt/setsockopt (CGROUP_SOCKOPT).

So this patch alone is NOT sufficient on a tree with stock 4.14 BPF -- it moves
the failure from "refuses to start" to "non-optional program failed to load".
It must be paired with a tree that actually has those hooks (rikka-v5, hxsyzl,
qaz a16-hyper all do; bool-x does not).

Default here is 4.19.0: the lowest claim that clears the gate, which keeps the
promise as small as possible. Override with FAKE_UNAME_RELEASE.

Matching is by current->comm so nothing else on the system sees a false
version -- `uname -r` in a shell still reports the truth.
"""
import os
import re
import sys

SYS_C = "kernel/sys.c"
REL = os.environ.get("FAKE_UNAME_RELEASE", "4.19.0")

HUNK = '''	if (!strncmp(current->comm, "bpfloader", 9) ||
	    !strncmp(current->comm, "netbpfload", 10) ||
	    !strncmp(current->comm, "netd", 4)) {
		strcpy(tmp.release, "%s");
		pr_debug("fake uname: %%s/%%d release=%%s\\n",
			 current->comm, current->pid, tmp.release);
	}
''' % REL


def main():
    if not os.path.exists(SYS_C):
        sys.exit("FATAL: %s not found -- run from the kernel tree root" % SYS_C)
    src = open(SYS_C, encoding="utf-8", errors="replace").read()
    if "fake uname" in src:
        print("  sys.c: already fakes uname, leaving alone")
        return
    m = re.search(r"SYSCALL_DEFINE1\(newuname,.*?\n\{", src, re.S)
    if not m:
        sys.exit("FATAL: could not find SYSCALL_DEFINE1(newuname) in " + SYS_C)
    body = src[m.end():]
    # Insert straight after the copy of the real utsname, before it is handed out.
    cm = re.search(r"\n\tmemcpy\(&tmp, utsname\(\), sizeof\(tmp\)\);\n", body)
    if not cm:
        sys.exit("FATAL: could not find the memcpy of utsname in newuname()")
    at = m.end() + cm.end()
    open(SYS_C, "w", encoding="utf-8").write(src[:at] + HUNK + src[at:])
    print("  sys.c: uname() now reports release=%s to bpfloader/netbpfload/netd" % REL)
    print("         (everything else, including `uname -r`, still sees the truth)")


if __name__ == "__main__":
    main()
