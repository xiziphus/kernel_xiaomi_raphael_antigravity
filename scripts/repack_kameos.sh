#!/usr/bin/env bash
# Repack a built Image.gz-dtb into a KameOS-bootable boot.img for `fastboot boot`.
#
# Usage: scripts/repack_kameos.sh <Image.gz-dtb> <ktest-name> [out.img]
#
# Two things here are load-bearing and were each learned the hard way:
#
#   ramoops_memreserve=4M
#     KameOS's kernel gets this from its own built-in CONFIG_CMDLINE, NOT from
#     the boot header -- the stock header's cmdline does not contain it. Our
#     kernels therefore never received it, so the vendor pstore mechanism
#     (scripts/xiaomi_ramoops.py) stayed dormant and every failed boot was
#     silent. Adding it here is what turns the log channel on.
#
#   androidboot.ktest=<name>
#     Surfaces as ro.boot.ktest. Without a marker a failed `fastboot boot` is
#     indistinguishable from a success, because both end up reporting the
#     flashed kernel's version.
#
# Header fields are KameOS's own (os_version 13.0.0 / patch 2022-11); do not
# "fix" them to the ROM's advertised Android version -- FBE key derivation uses
# these bytes and a mismatch costs you the data partition.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${1:?usage: repack_kameos.sh <Image.gz-dtb> <ktest-name> [out.img]}"
KTEST="${2:?need a ktest marker name}"
OUT="${3:-$REPO/builds/boot-${KTEST}.img}"

STOCK="$REPO/builds/kameos-docker-20260804-024211/boot-kameos-stock.img"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$REPO/scripts/unpack_boot.py" "$STOCK" "$WORK" >/dev/null
CMDLINE="$(python3 - "$WORK/boot_params.txt" <<'PY'
import re,sys
print(re.search(r'Cmdline:\s*(.*)', open(sys.argv[1]).read()).group(1).strip())
PY
)"
# ignore_loglevel: netbpfload logs through base::KernelLogger, i.e. /dev/kmsg
# at KERN_INFO. Rikka's console_loglevel drops that, so its pstore console
# recorded init's "bpfloader ... failed" line and NOT the NetBpfLoad lines
# that say WHY -- the log looked complete while missing the only part that
# matters. bool-x happened to ship a higher default and hid the problem.
CMDLINE="$CMDLINE ramoops_memreserve=4M loglevel=8 ignore_loglevel printk.devkmsg=on androidboot.ktest=$KTEST"

mkdir -p "$(dirname "$OUT")"
python3 "$REPO/mkbootimg_src/mkbootimg.py" \
  --kernel "$IMAGE" \
  --ramdisk "$WORK/ramdisk.cpio.gz" \
  --cmdline "$CMDLINE" \
  --header_version 0 \
  --os_version 13.0.0 --os_patch_level 2022-11 \
  --pagesize 4096 --base 0x00000000 \
  --kernel_offset 0x00008000 --ramdisk_offset 0x00000000 --tags_offset 0x00000100 \
  --output "$OUT"

echo "wrote $OUT"
echo "  ktest marker : $KTEST"
echo "  cmdline len  : ${#CMDLINE}"
echo
echo "Test (non-destructive, does not touch the boot partition):"
echo "  adb reboot bootloader && fastboot boot \"$OUT\""
echo "On raphael a FAILED fastboot boot powers the device OFF -- press power to bring it back."
echo "After it fails and you are back in KameOS, read the log:"
echo "  adb shell su -c 'logcat -L -b all' | grep -iE 'bpf|netbpf'"
echo "  adb shell su -c 'dumpsys dropbox --print SYSTEM_LAST_KMSG' | tail -80"
