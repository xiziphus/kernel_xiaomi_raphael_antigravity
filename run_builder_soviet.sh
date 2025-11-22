#!/bin/bash
# Docker wrapper for SOVIET kernel build

docker run --rm -i \
  --name soviet-kernel-builder \
  --cpus="16" \
  --memory="60g" \
  -v /Volumes/android-kernel/soviet_kernel_stock:/kernel/soviet_kernel_stock \
  -v /Volumes/android-kernel/clang-r522817:/opt/clang \
  --tmpfs /tmp/build:rw,size=4G,mode=1777 \
  --tmpfs /tmp/build:rw,size=4G,mode=1777 \
  android-kernel-builder \
  bash /kernel/soviet_kernel_stock/build_docker.sh
