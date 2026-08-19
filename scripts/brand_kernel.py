#!/usr/bin/env python3
"""Brand the kernel: credit banner in dmesg + attribution.

Prints once at late_initcall, so it cannot affect early boot -- the one thing
this project has learned to be careful about (an enum edit that ran no code at
all still panicked before ramoops; see JOURNEY 18).

Env:
  BRAND_AUTHOR  default "xiziphus"
  BRAND_REPO    default the harness repo
"""
import os
import sys

MAIN = "init/main.c"
AUTHOR = os.environ.get("BRAND_AUTHOR", "xiziphus")
REPO = os.environ.get("BRAND_REPO",
                      "https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity")

BANNER = '''
/* ---------------------------------------------------------------------------
 * Docker-enabled raphael kernel -- build harness branding.
 * late_initcall so it cannot perturb early boot. See scripts/brand_kernel.py.
 */
static int __init raphael_docker_banner(void)
{
	pr_info("=====================================================\\n");
	pr_info("  Docker-enabled kernel for Xiaomi Redmi K20 Pro\\n");
	pr_info("  built by %s\\n", "@@AUTHOR@@");
	pr_info("  %s\\n", "@@REPO@@");
	pr_info("  base: tingyuwuxin/kernel_xiaomi_raphael (Rikka)\\n");
	pr_info("  BPF backports from HeliumStudio-Dev (Zundamon)\\n");
	pr_info("=====================================================\\n");
	return 0;
}
late_initcall(raphael_docker_banner);
'''.replace("@@AUTHOR@@", AUTHOR).replace("@@REPO@@", REPO)

if __name__ == "__main__":
    if not os.path.exists(MAIN):
        sys.exit("FATAL: run from the kernel tree root")
    s = open(MAIN, encoding="utf-8", errors="replace").read()
    if "raphael_docker_banner" in s:
        print("  brand: already applied")
        sys.exit(0)
    open(MAIN, "w", encoding="utf-8").write(s.rstrip("\n") + "\n" + BANNER)
    if "late_initcall(raphael_docker_banner);" not in open(MAIN, encoding="utf-8").read():
        sys.exit("FATAL: brand did not apply")
    print("  brand: banner added (%s / %s)" % (AUTHOR, REPO))
