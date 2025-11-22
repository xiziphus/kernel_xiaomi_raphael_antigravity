#!/bin/bash
set -e

# Mount points
KERNEL_SRC=/Volumes/android-kernel/evox_kernel
CLANG_DIR=/Volumes/android-kernel/clang-r522817

# Run build inside docker
docker run --rm \
  -v "$KERNEL_SRC":/kernel/evox_kernel \
  -v "$CLANG_DIR":/opt/clang \
  -v "$(pwd)":/kernel/scripts \
  -w /kernel/scripts \
  android-kernel-builder \
  bash scripts/build_kernel_evox_clang18.sh
