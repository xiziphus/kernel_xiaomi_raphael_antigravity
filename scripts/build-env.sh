#!/bin/bash
#
# Source this BEFORE running build_and_flash_interactive.sh:
#
#   source scripts/build-env.sh
#   ./scripts/build_and_flash_interactive.sh
#
# Why this exists
# ---------------
# 1. The repo lives on /Volumes/Untitled, which is exFAT: case-INSENSITIVE, no
#    hardlinks, no real ownership. A Linux source tree cannot survive there --
#    4.14 netfilter alone ships xt_CONNMARK.h/xt_connmark.h, xt_MARK.h/xt_mark.h,
#    xt_DSCP.h/xt_dscp.h, which silently collapse into single files on checkout.
#    So the source tree and toolchain live in a case-sensitive APFS sparse image
#    (build.sparseimage) that still sits inside this folder and is gitignored.
#
# 2. build_and_flash_interactive.sh sizes the container from `sysctl hw.memsize`,
#    which reports the *host's* RAM. On Docker Desktop the real ceiling is the
#    Linux VM's RAM, which is far smaller. Requesting more than the VM has does
#    not fail loudly -- the container is OOM-killed mid-link instead. Size from
#    `docker info` rather than the host.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
IMAGE="$REPO_ROOT/build.sparseimage"
MOUNT="/Volumes/raphael-build"

if [ ! -d "$MOUNT" ]; then
    if [ ! -f "$IMAGE" ]; then
        echo "ERROR: $IMAGE not found. Recreate it with:"
        echo "  hdiutil create -size 120g -fs 'Case-sensitive APFS' -type SPARSE \\"
        echo "    -volname raphael-build build.sparseimage"
        return 1 2>/dev/null || exit 1
    fi
    echo "Attaching $IMAGE ..."
    hdiutil attach "$IMAGE" >/dev/null || { echo "ERROR: attach failed"; return 1 2>/dev/null || exit 1; }
fi

export KERNEL_SRC="$MOUNT/kernel_source"
export CLANG_DIR="$MOUNT/clang-r522817"

# Size the build to the Docker VM, not the host.
mem_bytes="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
if [ "$mem_bytes" -gt 0 ] 2>/dev/null; then
    vm_gb=$(( mem_bytes / 1024 / 1024 / 1024 ))
    export BUILD_JOBS="$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 4)"
    export BUILD_MEM="$(( vm_gb * 9 / 10 ))g"
    echo "Docker VM: ${vm_gb}G RAM / ${BUILD_JOBS} CPUs  ->  BUILD_MEM=$BUILD_MEM BUILD_JOBS=$BUILD_JOBS"
    if [ "$vm_gb" -lt 16 ]; then
        echo
        echo "  WARNING: ${vm_gb}G is below what the ThinLTO link step needs."
        echo "  raphael_defconfig enables CONFIG_LTO_CLANG + CONFIG_THINLTO, and ld.lld"
        echo "  is the memory spike -- it will OOM long before compilation does."
        echo "  Fix: Docker Desktop > Settings > Resources > Memory -> 32G or more,"
        echo "  then Apply & Restart. (This host has 64G, so there is headroom.)"
        echo
    fi
else
    echo "WARNING: could not query Docker. Is Docker Desktop running?"
fi

echo "KERNEL_SRC=$KERNEL_SRC"
echo "CLANG_DIR=$CLANG_DIR"
