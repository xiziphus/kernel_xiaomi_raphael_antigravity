#!/bin/bash
set -e

echo "=== SOVIET Kernel - Docker Patched Build ==="
echo "Source: SOVIET-ANDROID/kernel_xiaomi_raphael"
echo "Target: Raphael (Mi 9T Pro) - Android 16"
echo "Toolchain: Android Clang 18.0.1"
echo ""

# =========================================================
# PERSONALIZATION (Edit these to customize your build)
# =========================================================
export KBUILD_BUILD_USER="Xiziphus/ Gemini 3 pro"
export KBUILD_BUILD_HOST="github.com/xiziphus/kernel_xiaomi_raphael_antigravity"
export LOCALVERSION="-1.0-Alpha"
# =========================================================

# Paths (container-relative)
KERNEL_DIR="/kernel/soviet_kernel_stock"
CLANG_DIR="/opt/clang"
OUT_DIR="$KERNEL_DIR/out"

# Enable ccache for faster rebuilds.
#
# This previously did nothing at all. Two independent bugs:
#   1. ccache was not installed in the image (the Dockerfile never had it),
#      so /usr/lib/ccache did not exist and the PATH entry was inert.
#   2. Even installed, "export PATH=$CLANG_DIR/bin:$PATH" below is applied
#      AFTER the ccache entry, so plain `clang` resolves to the real binary
#      at /opt/clang/bin and the wrapper is never reached.
# Net effect: CCACHE_DIR stayed 0 bytes and every run recompiled ~3700 objects
# from cold -- which matters because Step 1 does "rm -rf out" unconditionally.
#
# The /usr/lib/ccache symlink farm only covers gcc/g++/cc/c++, never clang, and
# this tree must build with the AOSP prebuilt. So invoke ccache through CC
# instead, which is PATH-order independent. Set USE_CCACHE=0 to bypass.
export CCACHE_DIR="$KERNEL_DIR/ccache"
export USE_CCACHE="${USE_CCACHE:-1}"
mkdir -p "$CCACHE_DIR"

cd $KERNEL_DIR

# Set environment
export ARCH=arm64
export SUBARCH=arm64
export PATH=$CLANG_DIR/bin:$PATH

if [ "$USE_CCACHE" = "1" ] && command -v ccache >/dev/null 2>&1; then
    export CC="ccache clang"
    ccache -M 50G >/dev/null 2>&1 || true
    echo "=== ccache ACTIVE: $(ccache --version | head -1), dir=$CCACHE_DIR ==="
    ccache -s 2>/dev/null | grep -iE "cache hit rate|cache size" | sed 's/^/    /' || true
else
    export CC=clang
    echo "=== ccache NOT available - full cold rebuild (~30+ min) ==="
fi
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_ARM32=arm-linux-gnueabi-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export LD=$CLANG_DIR/bin/ld.lld
export AR=llvm-ar
export NM=llvm-nm
export OBJCOPY=llvm-objcopy
export OBJDUMP=llvm-objdump
export STRIP=llvm-strip
export LLVM_IAS=1

echo "=== Step 1: Clean build directory ==="
rm -rf out
mkdir -p out

echo "=== Step 2: Generate base config from raphael_defconfig ==="
make O=out ARCH=arm64 raphael_defconfig

echo "=== Step 3: Merge Docker config fragment ==="
# Use kernel's merge_config.sh to apply docker.config on top of raphael_defconfig
# This handles dependencies much better than scripts/config
ARCH=arm64 scripts/kconfig/merge_config.sh -m -O out out/.config /kernel/soviet_kernel_stock/docker.config

echo "=== Step 4: Run olddefconfig to resolve dependencies ==="
make O=out ARCH=arm64 olddefconfig

# Verify critical configs
echo "=== Step 5: Verify Docker flags ==="
grep -E "CONFIG_CGROUP_PIDS|CONFIG_USER_NS|CONFIG_PID_NS" out/.config || echo "WARNING: Some Docker flags missing!"
make O=out ARCH=arm64 olddefconfig

echo "=== Step 6: Build kernel ==="
# CC must be quoted: when ccache is active it is the two-word "ccache clang",
# and unquoted word-splitting would pass CC=ccache to make and leave "clang"
# parsed as a separate build target.
make -j$(nproc) \
    O=out \
    ARCH=arm64 \
    CC="$CC" \
    CLANG_TRIPLE=$CLANG_TRIPLE \
    CROSS_COMPILE=$CROSS_COMPILE \
    CROSS_COMPILE_ARM32=$CROSS_COMPILE_ARM32 \
    CROSS_COMPILE_COMPAT=$CROSS_COMPILE_COMPAT \
    LD=$LD \
    AR=$AR \
    NM=$NM \
    OBJCOPY=$OBJCOPY \
    OBJDUMP=$OBJDUMP \
    STRIP=$STRIP \
    LLVM_IAS=$LLVM_IAS

echo "=== Build Complete ==="
if [ -f "out/arch/arm64/boot/Image.gz-dtb" ]; then
    ls -lh out/arch/arm64/boot/Image.gz-dtb
    echo "SUCCESS: Kernel image ready!"
else
    echo "ERROR: Image.gz-dtb not found!"
    exit 1
fi
