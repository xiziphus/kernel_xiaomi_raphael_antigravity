#!/bin/bash
#
# In-container build for the InfinityX / LineageOS sm8150 kernel (raphael).
#
# Separate from build_kernel_soviet_docker.sh on purpose: that targets the
# SOVIET-ANDROID tree, whose kernel bootlooped on this ROM. Do not merge them.
#
# Mounts expected:
#   /kernel/src   -> LineageOS/android_kernel_xiaomi_sm8150 @ lineage-23.2 (+ KernelSU-Next)
#   /opt/clang    -> AOSP clang prebuilt
#   /cfg          -> this repo (read-only): kernel/container.config + kernel/base/
#   /work         -> tmpfs, sized by the caller
set -e

SRC=/kernel/src
CFG=/cfg
WORK=/work

echo "=== InfinityX kernel build ==="
echo "Base config : the device's own /proc/config.gz, not a defconfig"
echo "Fragment    : kernel/container.config"
echo ""

# ---------------------------------------------------------------------------
# Stage the tree onto tmpfs.
#
# The source lives on a bind-mounted sparse image, and every open() crosses
# virtiofs: measured 893us vs 4.2us on a container-local fs -- 213x. With
# 550-669 headers per object over ~3400 objects that is ~2M opens, and the
# build measures 20% user / 42% sys / 22% iowait, i.e. I/O bound with the CPUs
# mostly idle. Copying the tree in once costs ~2-3 min and removes that tax
# from every single compile.
#
# Falls back to building in place if /work is not a tmpfs, so the script still
# works if the caller forgets the mount.
# ---------------------------------------------------------------------------
if mountpoint -q "$WORK" 2>/dev/null || [ -d "$WORK" ]; then
    echo "=== Staging tree to $WORK (avoids ~2M virtiofs open() calls) ==="
    mkdir -p "$WORK/src"
    # The kernel's own .git is ~2 GB of pure overhead for a build, so drop it.
    #
    # On the ROM's tree this is safe in a way it was NOT on the old bolted-on
    # KernelSU layout. There, KSU_VERSION came from `git rev-list --count HEAD`
    # in KernelSU-Next/.git, so losing that directory silently produced
    # KSU_VERSION=1 and root that did not work. Here drivers/kernelsu is IN-TREE
    # and its Makefile hardcodes `KSU_GIT_VERSION := 3131`, so no git is
    # consulted and there is no fallback path to trip over.
    time rsync -a --delete \
        --exclude=out --exclude=/.git \
        "$SRC/" "$WORK/src/"
    if [ ! -f "$WORK/src/drivers/kernelsu/Makefile" ]; then
        echo "ERROR: drivers/kernelsu did not survive staging -- no root in this build."
        exit 1
    fi
    if [ ! -f "$WORK/src/fs/susfs.c" ]; then
        echo "ERROR: fs/susfs.c missing -- this is not the ROM's tree."
        exit 1
    fi
    # Stage the TOOLCHAIN too. Staging only the source still leaves clang on the
    # bind mount, and the 135 MB clang binary is demand-paged over virtiofs on
    # every exec -- ~4500 of them per build. Symptom: sys time exceeding user
    # time even though the tree is on tmpfs (measured 131m user / 139m sys on a
    # 27 min wall-clock build).
    if [ -x /opt/clang/bin/clang ] && [ ! -x "$WORK/clang/bin/clang" ]; then
        echo "=== Staging toolchain to $WORK/clang ==="
        mkdir -p "$WORK/clang"
        time cp -a /opt/clang/. "$WORK/clang/"
        export PATH="$WORK/clang/bin:$PATH"
        CLANG_ROOT="$WORK/clang"
    fi
    BUILD_SRC="$WORK/src"
    OUT="$WORK/out"
else
    echo "=== /work absent - building in place (slow path) ==="
    BUILD_SRC="$SRC"
    OUT="$SRC/out"
fi

cd "$BUILD_SRC"
rm -rf "$OUT" && mkdir -p "$OUT"

export ARCH=arm64 SUBARCH=arm64
CLANG_ROOT="${CLANG_ROOT:-/opt/clang}"
export PATH="$CLANG_ROOT/bin:$PATH"
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_ARM32=arm-linux-gnueabi-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export LD="$CLANG_ROOT/bin/ld.lld"
export AR=llvm-ar NM=llvm-nm OBJCOPY=llvm-objcopy OBJDUMP=llvm-objdump STRIP=llvm-strip
export LLVM_IAS=1

# Build identity. These two are what /proc/version and the boot banner report
# as "who built this kernel", and they do NOT affect `uname -r`, so branding
# here costs nothing in compatibility. Override at build time if you fork this.
export KBUILD_BUILD_USER="${KBUILD_BUILD_USER:-antigravitykernel}"
export KBUILD_BUILD_HOST="${KBUILD_BUILD_HOST:-antigravity}"

export CCACHE_DIR="${CCACHE_DIR:-$WORK/ccache}"
mkdir -p "$CCACHE_DIR"
if command -v ccache >/dev/null 2>&1; then
    export CC="ccache clang"
    ccache -M 10G >/dev/null 2>&1 || true
    echo "=== ccache active ($CCACHE_DIR) ==="
else
    export CC=clang
    echo "=== ccache unavailable - cold build ==="
fi

echo ""
echo "=== Step 1: seed .config from the DEVICE's running config ==="
# Starting from /proc/config.gz rather than sm8150-perf_defconfig means we
# reproduce exactly what InfinityX ships, including their tuning, instead of
# guessing from a defconfig that may have drifted.
cp "$CFG/infinityx/running.config" "$OUT/.config"

echo "=== Step 2: lint the fragment, then merge it ==="
# merge_config.sh extracts symbols with
#     s/^\(# \)\{0,1\}\(CONFIG_[a-zA-Z0-9_]*\)[= ].*/\2/p
# which cannot tell a directive from a COMMENT that merely mentions one. Two
# explanatory lines here once began "# CONFIG_KSU=y, ..." and merge_config.sh
# duly "redefined" CONFIG_KSU and CONFIG_KSU_MANUAL_HOOK to the literal comment
# text. olddefconfig then reset both to their Kconfig defaults, which happened
# to match the device -- so root survived by luck, not correctness.
#
# Legal '#' lines are exactly "# CONFIG_FOO is not set". Anything else that
# starts with "# CONFIG_<name>" followed by '=' or a space is prose and is a bug.
if bad=$(grep -nE '^# CONFIG_[a-zA-Z0-9_]*[= ]' "$CFG/infinityx.config" \
         | grep -vE '^[0-9]+:# CONFIG_[a-zA-Z0-9_]+ is not set$'); then
    echo "  ERROR: comment lines in kernel/container.config parse as config directives:"
    printf '    %s\n' "$bad"
    echo "  Write symbol names without the CONFIG_ prefix in prose."
    exit 1
fi
echo "  fragment lint: clean"
ARCH=arm64 scripts/kconfig/merge_config.sh -m -O "$OUT" "$OUT/.config" "$CFG/infinityx.config"

echo "=== Step 3: olddefconfig ==="
make O="$OUT" ARCH=arm64 olddefconfig

echo ""
echo "=== Step 4: flag retention (all directives, positive AND negative) ==="
# A previous version did `case "$line" in ''|\#*) continue;; esac`, which skipped
# EVERY line starting with '#'. That silently excluded the negative directives --
# "# CONFIG_FOO is not set" -- from the check, so a run could report a confident
# "41/41, zero dropped" while only 41 of 43 directives had actually been verified.
lost=0; kept=0
while IFS= read -r line; do
    case "$line" in
        '') continue ;;
        '# CONFIG_'*' is not set') ;;          # a real directive -- check it
        \#*) continue ;;                        # an ordinary comment -- skip
    esac
    sym=$(printf '%s' "$line" | sed -E 's/^# ?//; s/[ =].*$//')
    if grep -qx -- "$line" "$OUT/.config"; then
        kept=$((kept+1))
    else
        lost=$((lost+1))
        printf '  LOST  %-34s -> %s\n' "$sym" \
            "$(grep -E "^(# )?${sym}[ =]" "$OUT/.config" || echo absent)"
    fi
done < "$CFG/infinityx.config"
echo "  kept: $kept   lost: $lost"
if [ "$lost" -ne 0 ]; then
    echo "  ERROR: refusing to build with dropped flags."
    echo "  The nftables IPv6 entries need NF_NAT_IPV6."
    exit 1
fi

echo ""
echo "=== Step 4b: FULL config drift vs the device's running config ==="
# Retention only proves OUR flags survived. It says nothing about symbols
# olddefconfig changed on its own. On the lineage-23.2 tree that silently turned
# on CONFIG_SPECULATIVE_PAGE_FAULT (mm/Kconfig default y + arm64 selects
# ARCH_SUPPORTS_SPECULATIVE_PAGE_FAULT) and CONFIG_IR_LIRC_CODEC -- an unreviewed
# mm change that shipped to a daily driver unnoticed. Report every difference and
# let a human read them, rather than spot-checking a list of symbols we thought of.
python3 - "$CFG/infinityx/running.config" "$OUT/.config" "$CFG/infinityx.config" <<'PY'
import re, sys
def load(p):
    m = {}
    for ln in open(p, errors='replace'):
        ln = ln.rstrip('\n')
        if (x := re.match(r'^(CONFIG_\w+)=(.*)$', ln)): m[x.group(1)] = x.group(2)
        elif (x := re.match(r'^# (CONFIG_\w+) is not set$', ln)): m[x.group(1)] = 'n'
    return m
run, new, frag = (load(p) for p in sys.argv[1:4])
intended = set(frag)
unexpected = []
for k in sorted(set(run) | set(new)):
    a, b = run.get(k, 'n'), new.get(k, 'n')
    if a != b and k not in intended:
        unexpected.append((k, a, b))
print(f"  intentional (from fragment): {len(intended)}")
print(f"  UNINTENDED differences     : {len(unexpected)}")
for k, a, b in unexpected:
    print(f"    ~ {k:<44} device={a:<6} ours={b}")
PY

echo "=== Step 5: the checks that actually matter ==="
for s in CONFIG_KSU CONFIG_USER_NS CONFIG_PID_NS CONFIG_CGROUP_PIDS CONFIG_CGROUP_DEVICE CONFIG_NF_TABLES CONFIG_OVERLAY_FS; do
    printf '  %-24s %s\n' "$s" "$(grep -E "^(# )?$s[ =]" "$OUT/.config" || echo ABSENT)"
done

echo ""
echo "=== Step 5b: eBPF capability gate (SOURCE, not config) ==="
# This gate exists because a config check structurally cannot catch what broke
# the first flash. Every CONFIG_BPF* symbol was byte-identical to the device's,
# and the kernel still bootlooped with reboot,bpfloader-failed.
#
# The ROM sets ro.bpf.kver_override=5.4.299 (LineageOS legacy-bpf-compat), so
# Android's netbpfload believes it is on a 5.4 kernel and skips the
# DEVMAP_HASH->HASH downgrade it would otherwise apply below 5.4. It then asks
# for BPF_MAP_TYPE_DEVMAP_HASH (25) and BPF_PROG_TYPE_CGROUP_SOCK_ADDR (18) /
# CGROUP_SOCKOPT (25). A pristine 4.14 tree tops out at map 15 / prog 14, so
# BPF_MAP_CREATE returns -EINVAL, the loader aborts, and init reboots.
#
# Only a tree carrying the ACK android-4.14 BPF backports can satisfy this.
nprog=$(grep -c 'BPF_PROG_TYPE_' include/uapi/linux/bpf.h 2>/dev/null || echo 0)
echo "  BPF_PROG_TYPE_ entries in uapi: $nprog  (pristine 4.14 = 15, backported = 36)"
bpf_missing=0
for s in BPF_PROG_TYPE_CGROUP_SOCK_ADDR BPF_PROG_TYPE_CGROUP_SOCKOPT BPF_MAP_TYPE_DEVMAP_HASH; do
    if grep -q "$s" include/uapi/linux/bpf.h 2>/dev/null; then
        printf '  present  %s\n' "$s"
    else
        printf '  MISSING  %s\n' "$s"; bpf_missing=$((bpf_missing+1))
    fi
done
[ -f kernel/bpf/btf.c ] && echo "  present  kernel/bpf/btf.c" \
    || { echo "  MISSING  kernel/bpf/btf.c"; bpf_missing=$((bpf_missing+1)); }
if [ "$bpf_missing" -ne 0 ]; then
    echo "  ERROR: this tree lacks the BPF backports Android 16's netbpfload needs."
    echo "         It will compile and boot, then die at bpfloader and reboot."
    echo "         Use the ROM's own kernel source, not a pristine 4.14 tree."
    exit 1
fi

echo ""
echo "=== Step 6: build ==="
# Targets are EXPLICIT. The default `all` is wrong for us here:
#
#   arch/arm64/Makefile:170  CONFIG_BUILD_ARM64_APPENDED_DTB_IMAGE is not set
#   arch/arm64/Makefile:163  CONFIG_BUILD_ARM64_KERNEL_COMPRESSION_GZIP is not set
#                            CONFIG_BUILD_ARM64_UNCOMPRESSED_KERNEL=y
#
# so KBUILD_TARGET resolves to plain `Image` and `all` never builds Image.gz
# or Image.gz-dtb. But the SHIPPED boot.img carries a GZIP-compressed kernel:
# the stock kernel section begins 1f 8b 08 and is 18,439,608 B against a 44 MB
# raw Image. The running /proc/config.gz claiming UNCOMPRESSED is about how the
# ROM's build packaged it, not about what the bootloader is handed -- don't
# trust it over the bytes in the boot image.
#
# dtbs is DELIBERATELY NOT BUILT. Two independent reasons:
#
# 1. We do not ship any DT artifact. The boot image's DTB section is the
#    device's own, copied byte-for-byte out of its boot partition -- ground
#    truth for what this ROM runs, and strictly safer than a regenerated one.
#    The dtbo partition is not flashed at all.
#
# 2. It cannot be built with the in-tree tooling anyway. Every xiaomi overlay
#    (raphael's included, not just andromeda's) opens with a bare reference:
#        raphael-pinctrl.dtsi:2   &tlmm {
#    and this tree bundles dtc 1.4.4, whose grammar has no production letting a
#    `devicetree` BEGIN with DT_REF -- scripts/dtc/dtc-parser.y:161 requires
#    `'/' nodedef` first. Newer dtc accepts it for /plugin/ files. The ROM's own
#    build supplies an external Android dtc via DTC_EXT (scripts/Makefile.lib:323).
#    The base sm8150-*.dtb files compile fine because they do start with '/'.
#
# Image.gz does not depend on dtbs: arch/arm64/Makefile has `Image: vmlinux` and
# `Image.%: Image`. Only Image-dtb / Image.gz-dtb pull dtbs in, and we build
# neither. Set DTC_EXT to a dtc >= 1.4.5 if DT artifacts are ever needed.
time make -j"$(nproc)" O="$OUT" ARCH=arm64 CC="$CC" \
    CLANG_TRIPLE=$CLANG_TRIPLE CROSS_COMPILE=$CROSS_COMPILE \
    CROSS_COMPILE_ARM32=$CROSS_COMPILE_ARM32 CROSS_COMPILE_COMPAT=$CROSS_COMPILE_COMPAT \
    LD=$LD AR=$AR NM=$NM OBJCOPY=$OBJCOPY OBJDUMP=$OBJDUMP STRIP=$STRIP \
    LLVM_IAS=$LLVM_IAS \
    Image.gz

echo ""
echo "=== Step 7: copy artifacts back to the bind mount ==="
mkdir -p "$SRC/out/arch/arm64/boot"
for f in Image.gz Image dtbo.img; do
    [ -f "$OUT/arch/arm64/boot/$f" ] && cp "$OUT/arch/arm64/boot/$f" "$SRC/out/arch/arm64/boot/" && echo "  $f"
done
cp "$OUT/.config" "$SRC/out/.config"
[ -f "$OUT/include/config/kernel.release" ] && cp "$OUT/include/config/kernel.release" "$SRC/out/"

# Image.gz is the artifact that goes into the boot image -- NOT Image.gz-dtb.
# This tree/ROM uses boot header v2, which carries the DTB in its own section
# (dtb size 1786528 @ 0x01f00000), so nothing is appended to the kernel.
if [ -f "$SRC/out/arch/arm64/boot/Image.gz" ]; then
    ls -lh "$SRC/out/arch/arm64/boot/Image.gz"
    echo "SUCCESS: $(cat "$SRC/out/kernel.release" 2>/dev/null)"
else
    echo "ERROR: no Image.gz produced."
    exit 1
fi
