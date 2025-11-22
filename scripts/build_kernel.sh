#!/bin/bash
set -e

# Navigate to source
cd /kernel/source

# Set architecture variables
export ARCH=arm64
export SUBARCH=arm64

# Setup Proton Clang toolchain path
export PATH=/kernel/toolchain/bin:$PATH

# Set LLVM toolchain variables (as per engineering document)
export CC=clang
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_ARM32=arm-linux-gnueabi-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export LD=ld.lld
export AR=llvm-ar
export NM=llvm-nm
export OBJCOPY=llvm-objcopy
export OBJDUMP=llvm-objdump
export STRIP=llvm-strip

# Build the kernel
echo "Starting kernel build with Proton Clang..."
make O=out Image.gz-dtb dtbo.img -j$(nproc)

echo "Build complete. Artifacts are in out/arch/arm64/boot/"
