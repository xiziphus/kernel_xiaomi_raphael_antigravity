#!/bin/bash
set -e

echo "=== SOVIET Kernel - Docker Patched Build ==="
echo "Source: SOVIET-ANDROID/kernel_xiaomi_raphael"
echo "Target: Raphael (Mi 9T Pro) - Android 16"
echo "Toolchain: Android Clang 18.0.1"
echo ""

# Paths (container-relative)
KERNEL_DIR="/kernel/soviet_kernel_stock"
CLANG_DIR="/opt/clang"
OUT_DIR="$KERNEL_DIR/out"

# Enable ccache for faster rebuilds
export USE_CCACHE=1
export CCACHE_DIR="$KERNEL_DIR/ccache"
mkdir -p "$CCACHE_DIR"
export PATH="/usr/lib/ccache:$PATH"
echo "=== ccache enabled (faster rebuilds) ==="

cd $KERNEL_DIR

# Set environment
export ARCH=arm64
export SUBARCH=arm64
export PATH=$CLANG_DIR/bin:$PATH
export CC=clang
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
make -j$(nproc) \
    O=out \
    ARCH=arm64 \
    CC=$CC \
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
