#!/usr/bin/env python3
"""Neutralise Kconfig source() lines pointing into an EMPTY submodule.

Trees that vendor KernelSU/SukiSU as a git submodule clone empty under
--depth=1, and Kconfig then dies at defconfig with:

    drivers/staging/Kconfig:123: can't open file "drivers/staging/kernelsu/kernel/Kconfig"

We do not need KernelSU to test whether a kernel boots, so the source() line is
dropped rather than the submodule fetched.

Scope is deliberately tiny, because a broader version of this caused its own
outage: matching every source() whose literal path was absent also matched
`source "arch/$SRCARCH/Kconfig"` -- a variable, not a missing file -- and
deleting that took whole Kconfig subtrees with it. Every Docker option then came
back "lost at config time". So:

  * only paths that start with a submodule declared in .gitmodules
  * only when that submodule directory is actually empty
  * never a path containing '$'

Run from the kernel tree root. Idempotent.
"""
import os
import re
import sys


def empty_submodules(root="."):
    gm = os.path.join(root, ".gitmodules")
    if not os.path.exists(gm):
        return []
    subs = re.findall(r"path\s*=\s*(\S+)", open(gm, encoding="utf-8", errors="replace").read())
    out = []
    for p in subs:
        d = os.path.join(root, p)
        if not os.path.isdir(d) or not os.listdir(d):
            out.append(p)
    return out


def fix(root="."):
    subs = empty_submodules(root)
    if not subs:
        print("  kconfig: no empty submodules, nothing to do")
        return 0
    print("  kconfig: empty submodule(s): %s" % " ".join(subs))
    n = 0
    for dirpath, _d, files in os.walk(root):
        if os.sep + ".git" in dirpath:
            continue
        for fn in files:
            if fn != "Kconfig" and not fn.startswith("Kconfig."):
                continue
            fp = os.path.join(dirpath, fn)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            out, changed = [], False
            for line in txt.splitlines(True):
                m = re.match(r'\s*source\s+"?([^"\s]+)"?', line)
                tgt = m.group(1) if m else None
                if (tgt and "$" not in tgt
                        and any(tgt.startswith(sp) for sp in subs)
                        and not os.path.exists(os.path.join(root, tgt))):
                    out.append("# [ci] empty submodule, dropped: " + line)
                    changed = True
                else:
                    out.append(line)
            if changed:
                open(fp, "w", encoding="utf-8").write("".join(out))
                print("  kconfig: %s" % os.path.relpath(fp, root))
                n += 1
    print("  kconfig: %d file(s) fixed" % n)
    return n


if __name__ == "__main__":
    sys.exit(0 if fix(sys.argv[1] if len(sys.argv) > 1 else ".") >= 0 else 1)
