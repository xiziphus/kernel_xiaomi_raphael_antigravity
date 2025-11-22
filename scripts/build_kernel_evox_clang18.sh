#!/bin/bash
set -e

# Navigate to source
cd /kernel/evox_kernel

# Clean previous build
rm -rf out && mkdir -p out

# Set Architecture
export ARCH=arm64
export SUBARCH=arm64

# Set Android Clang Toolchain Paths
export PATH=/opt/clang/bin:$PATH

# Set Compiler and Linker
export CC=clang
export CLANG_TRIPLE=aarch64-linux-gnu-
# Cross compile prefixes are not needed with clang-only toolchain; comment them out
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_ARM32=arm-linux-gnueabi-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export LD=/opt/clang/bin/ld.lld
export AR=llvm-ar
export NM=llvm-nm
export OBJCOPY=llvm-objcopy
export OBJDUMP=llvm-objdump
export STRIP=llvm-strip

# Use LLVM Integrated Assembler
export LLVM_IAS=1

# Load defconfig
make O=out ARCH=arm64 raphael_defconfig

# Prepare
make O=out \
    CC=clang \
    CLANG_TRIPLE=aarch64-linux-gnu- \
    CROSS_COMPILE=aarch64-linux-gnu- \
    CROSS_COMPILE_ARM32=arm-linux-gnueabi- \
    CROSS_COMPILE_COMPAT=arm-linux-gnueabi- \
    LD=/opt/clang/bin/ld.lld \
    AR=llvm-ar \
    NM=llvm-nm \
    OBJCOPY=llvm-objcopy \
    OBJDUMP=llvm-objdump \
    STRIP=llvm-strip \
    prepare

# Compile
make O=out \
    CC=clang \
    CLANG_TRIPLE=aarch64-linux-gnu- \
    CROSS_COMPILE=aarch64-linux-gnu- \
    CROSS_COMPILE_ARM32=arm-linux-gnueabi- \
    CROSS_COMPILE_COMPAT=arm-linux-gnueabi- \
    LD=/opt/clang/bin/ld.lld \
    AR=llvm-ar \
    NM=llvm-nm \
    OBJCOPY=llvm-objcopy \
    OBJDUMP=llvm-objdump \
    STRIP=llvm-strip \
    ${1:-Image.gz-dtb dtbo.img} \
    -j$(nproc)
