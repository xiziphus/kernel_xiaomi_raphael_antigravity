#!/usr/bin/env python3
"""Reproduce KameOS's pstore geometry exactly, so a failed boot leaves a readable log.

Why this exists
---------------
Every custom kernel we boot on KameOS that dies in userspace has been a black
box: `logcat -L` comes back empty and `dumpsys dropbox --print SYSTEM_LAST_KMSG`
shows nothing from our boot. The reason is that KameOS's kernel does NOT get its
ramoops region from the device tree at all. Its cmdline carries

    ramoops_memreserve=4M

which a Xiaomi patch in fs/pstore/ram.c turns into a hardcoded region, then
registers as a plain platform device -- which is why there is no
/proc/device-tree node for it and why the region never lined up with the one our
DTS declared. Read off the running ROM with root
(/sys/module/ramoops/parameters/*):

    mem_address=0xB0000000  mem_size=0x400000  (4M)
    console_size=0x200000   pmsg_size=0x200000
    record_size=0           ftrace_size=0      ecc=0     dump_oops=1

This patch is that vendor mechanism, taken from hxsyzl/kernel_xiaomi_raphael
(fs/pstore/ram.c, branch `dynamic`), where size/2 goes to console and size/2 to
pmsg -- reproducing all seven values above field for field.

Getting the geometry byte-identical is the whole point: pstore lays its region
out as dump-records -> console -> ftrace -> pmsg, so a single differing size
shifts every later buffer and makes our records unreadable to the ROM's reader.
With it matched, after a test kernel fails and the device reboots back into
KameOS's own kernel, both channels work:

    adb shell su -c 'dumpsys dropbox --print SYSTEM_LAST_KMSG'   # console (kernel)
    adb shell su -c 'logcat -L -b all'                           # pmsg (logd)

The second one is the prize: bpfloader's own error text and the kernel BPF
verifier log it dumps, which is the thing netbpfload.rc tells you to go read and
the thing we have never once been able to see.

Two deliberate differences from the vendor code
-----------------------------------------------
1. No `#ifdef CONFIG_MACH_XIAOMI_SM8150` guard. bool-x sets MACH_XIAOMI and
   MACH_XIAOMI_RAPHAEL but not _SM8150, so the guarded version compiles to
   nothing there. Unguarded is harmless: the code only ever activates if the
   cmdline actually contains ramoops_memreserve=.
2. The DTS ramoops node is deleted. Leaving it would reserve a second, differently
   located region and register a competing "ramoops" platform device; the second
   registration loses. KameOS has no DT node, so neither do we.

Idempotent: safe to run twice.
"""
import os
import re
import sys

RAM_C = "fs/pstore/ram.c"

BLOCK = r'''
/* Xiaomi vendor mechanism: ramoops region from the cmdline, not the DT.
 * Mirrors KameOS, whose cmdline carries ramoops_memreserve=4M and whose
 * /sys/module/ramoops/parameters report mem_address=0xB0000000 mem_size=4M
 * console=2M pmsg=2M record=0 ecc=0. Matching this exactly is what makes a
 * failed boot readable via `dumpsys dropbox SYSTEM_LAST_KMSG` / `logcat -L`.
 */
static struct ramoops_platform_data xiaomi_ramoops_data;

static struct platform_device xiaomi_ramoops_dev = {
	.name = "ramoops",
	.dev = {
		.platform_data = &xiaomi_ramoops_data,
	},
};

static int __init xiaomi_ramoops_memreserve(char *p)
{
	unsigned long size;

	if (!p)
		return 1;

	size = memparse(p, &p) & PAGE_MASK;
	xiaomi_ramoops_data.mem_size = size;
	xiaomi_ramoops_data.mem_address = 0xB0000000;
	xiaomi_ramoops_data.console_size = size / 2;
	xiaomi_ramoops_data.pmsg_size = size / 2;
	xiaomi_ramoops_data.dump_oops = 1;

	pr_info("xiaomi_ramoops: addr=%llx size=%lx console=%lx pmsg=%lx\n",
		(unsigned long long)xiaomi_ramoops_data.mem_address,
		xiaomi_ramoops_data.mem_size,
		xiaomi_ramoops_data.console_size,
		xiaomi_ramoops_data.pmsg_size);

	memblock_reserve(xiaomi_ramoops_data.mem_address,
			 xiaomi_ramoops_data.mem_size);

	return 0;
}
early_param("ramoops_memreserve", xiaomi_ramoops_memreserve);

static int __init xiaomi_register_ramoops_device(void)
{
	if (platform_device_register(&xiaomi_ramoops_dev))
		pr_info("xiaomi_ramoops: unable to register platform device\n");
	return 0;
}
core_initcall(xiaomi_register_ramoops_device);

'''


def patch_ram_c() -> bool:
    if not os.path.exists(RAM_C):
        sys.exit("FATAL: %s not found -- run from the kernel tree root" % RAM_C)
    src = open(RAM_C, encoding="utf-8", errors="replace").read()
    if "xiaomi_ramoops_memreserve" in src:
        print("  ram.c: already patched, skipping")
        return False
    if "early_param(\"ramoops_memreserve\"" in src:
        print("  ram.c: tree already implements ramoops_memreserve, skipping")
        return False

    if "linux/memblock.h" not in src:
        anchor = "#include <linux/pstore_ram.h>\n"
        if anchor not in src:
            sys.exit("FATAL: could not find pstore_ram.h include in " + RAM_C)
        src = src.replace(anchor, anchor + "#include <linux/memblock.h>\n", 1)

    m = re.search(r"^static int __init ramoops_init\(void\)", src, re.M)
    if not m:
        sys.exit("FATAL: could not find ramoops_init() in " + RAM_C)
    src = src[:m.start()] + BLOCK.lstrip("\n") + src[m.start():]
    open(RAM_C, "w", encoding="utf-8").write(src)
    print("  ram.c: added ramoops_memreserve -> 0xB0000000, console=size/2, pmsg=size/2")
    return True


def rewrite_dts_nodes(base="0xB0000000") -> int:
    """Rewrite DT ramoops nodes to the ROM's exact geometry.

    This is the PROVEN channel: a kernel built this way produced 40 KB of
    readable console-ramoops-0 on KameOS (waffleowo, 2026-08-18). An earlier
    revision of this script deleted the node and relied solely on the
    memreserve platform device instead -- that produced NO pstore records at
    all on bool-x, so the DT node is preferred wherever one exists.
    """
    node = ("ramoops: ramoops@%s {\n"
            "\t\t\tcompatible = \"ramoops\";\n"
            "\t\t\treg = <0x0 %s 0x0 0x400000>;\n"
            "\t\t\trecord-size = <0x0>;\n"
            "\t\t\tconsole-size = <0x200000>;\n"
            "\t\t\tpmsg-size = <0x200000>;\n"
            "\t\t\tecc-size = <0>;\n"
            "\t\t};") % (base[2:].lower(), base)
    n = 0
    for root, _dirs, files in os.walk("arch/arm64/boot/dts/qcom"):
        for fn in files:
            if not fn.endswith((".dts", ".dtsi")):
                continue
            # ONLY files raphael actually builds. An earlier version rewrote the
            # ramoops node in apq8016-sbc.dtsi (a Dragonboard 410c), counted it
            # as done, and left sm8150.dtsi -- the one that ships -- untouched.
            if not ("sm8150" in fn or "raphael" in fn):
                continue
            p = os.path.join(root, fn)
            try:
                s = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            m = re.search(r"\w*:?\s*ramoops@[0-9a-fA-F]+\s*\{[^{}]*\}\s*;", s, re.S)
            if not m:
                continue
            open(p, "w", encoding="utf-8").write(s[:m.start()] + node + s[m.end():])
            print("  dts: %s -> %s (4MB: console 2MB + pmsg 2MB, record 0, ecc 0)" % (p, base))
            n += 1
    return n



def force_warm_reboot() -> int:
    """Make the PMIC do a WARM reset, so DRAM (and thus ramoops) survives.

    Proven on device 2026-08-18: after a CLEAN reboot /sys/fs/pstore is empty
    even for KameOS's own kernel -- write a marker to /dev/kmsg, `adb reboot`,
    and nothing comes back. Only a panic preserves the buffer. That is exactly
    why waffleowo (Kernel panic) left 40 KB of console and bool-x (init reboots
    cleanly on bpfloader failure) left nothing at all, and why chasing the
    ramoops geometry could never have fixed it.

    A hard PMIC reset re-initialises DDR and wipes the region. msm-poweroff.c
    already supports the fix -- msm_restart_prepare() selects
    PON_POWER_OFF_WARM_RESET when force_warm_reboot is set, and that flag is
    read straight from a DT property -- so no C change is needed:

        force_warm_reboot = of_property_read_bool(dev->of_node,
                                                  "qcom,force-warm-reboot");

    Helium's 5.4 tree carries the same idea as a commit: "power: msm: Always
    perform warm reboot".
    """
    n = 0
    for root, _dirs, files in os.walk("arch/arm64/boot/dts/qcom"):
        for name in files:
            if not name.endswith((".dts", ".dtsi")):
                continue
            fp = os.path.join(root, name)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if 'compatible = "qcom,pshold"' not in txt:
                continue
            if "qcom,force-warm-reboot" in txt:
                print("  warm-reboot: already set in %s" % fp)
                continue
            txt = txt.replace('compatible = "qcom,pshold";',
                              'compatible = "qcom,pshold";' + chr(10) +
                              chr(9) + chr(9) + "qcom,force-warm-reboot;", 1)
            open(fp, "w", encoding="utf-8").write(txt)
            print("  warm-reboot: qcom,force-warm-reboot added in %s" % fp)
            n += 1
    if not n:
        print("  warm-reboot: no qcom,pshold node found")
    return n



def insert_dts_node(base="0xB0000000") -> int:
    """Add a ramoops node to reserved-memory when the tree has none.

    Rikka has no ramoops@ node, so an earlier version of this script fell back
    to the ramoops_memreserve cmdline path -- which has never once produced a
    readable buffer, on any tree. The DT route is the one we have actually seen
    work (waffleowo, bool-x), so create the node rather than fall back.
    """
    node = (
        "\n\t\tramoops: ramoops@%s {\n"
        "\t\t\tcompatible = \"ramoops\";\n"
        "\t\t\treg = <0x0 %s 0x0 0x400000>;\n"
        "\t\t\trecord-size = <0x0>;\n"
        "\t\t\tconsole-size = <0x200000>;\n"
        "\t\t\tpmsg-size = <0x200000>;\n"
        "\t\t\tecc-size = <0>;\n"
        "\t\t};\n") % (base[2:].lower(), base)
    for root, _dirs, files in os.walk("arch/arm64/boot/dts/qcom"):
        for name in files:
            if not name.endswith(".dtsi"):
                continue
            # Same filter as rewrite_dts_nodes. Without it this inserted the
            # node into sa8195-vm-lv.dtsi -- a different SoC -- and reported
            # success, exactly as the earlier version "fixed" apq8016-sbc.dtsi.
            if not ("sm8150" in name or "raphael" in name):
                continue
            fp = os.path.join(root, name)
            try:
                txt = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            m = re.search(r"reserved[_-]memory\s*:\s*reserved-memory\s*\{", txt)
            if not m:
                continue
            # Insert at the END of the reserved-memory block, not the start.
            # DTS requires "properties must precede subnodes", and putting our
            # subnode first pushed #address-cells/#size-cells/ranges after it:
            #   Error: sm8150.dtsi:606.3-24 Properties must precede subnodes
            depth, i = 1, m.end()
            while i < len(txt) and depth:
                if txt[i] == "{":
                    depth += 1
                elif txt[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if depth:
                print("  dts: unbalanced braces in %s, skipping" % fp)
                continue
            at = txt.rfind("\n", 0, i) + 1
            open(fp, "w", encoding="utf-8").write(txt[:at] + node.lstrip("\n") + txt[at:])
            print("  dts: INSERTED ramoops@%s into reserved-memory in %s" % (base[2:], fp))
            return 1
    print("  dts: no reserved-memory node to insert into")
    return 0


if __name__ == "__main__":
    # Prefer the DT node -- it is the channel we have actually seen work.
    # Only fall back to the vendor cmdline mechanism when the tree has no node
    # to fix, so we never end up with two competing ramoops devices.
    force_warm_reboot()
    n = rewrite_dts_nodes()
    if n:
        print("  xiaomi ramoops: %d DT node(s) set to the ROM geometry" % n)
    else:
        # Prefer creating the node over the cmdline mechanism: the DT route is
        # the only one we have observed to actually yield a readable buffer.
        if not insert_dts_node():
            print("  no reserved-memory to extend; falling back to the cmdline path")
            patch_ram_c()

    # Post-condition. Twice now this script has patched a device tree belonging
    # to a completely different board and reported success, costing a device
    # cycle each time. Verify the file raphael actually builds ended up with the
    # node, and say so loudly if not.
    ok = False
    for cand in ("arch/arm64/boot/dts/qcom/sm8150.dtsi",):
        if os.path.exists(cand) and "ramoops@b0000000" in open(cand, encoding="utf-8", errors="replace").read().lower():
            ok = True
    if ok:
        print("  VERIFIED: sm8150.dtsi carries ramoops@b0000000")
    else:
        print("  WARNING: sm8150.dtsi has NO ramoops@b0000000 -- a failed boot "
              "will leave no log. Do not spend a device cycle on this image.")
