#!/bin/bash
#
# Docker wrapper for the Project Infinity-X sm8150 kernel build.
#
#   source scripts/build-env.sh      # attaches build.sparseimage
#   ./run_builder_infinityx.sh
#
# The tree MUST be the ROM's own source, not LineageOS. See the header of
# infinityx.config: a pristine 4.14 compiles and boots, then dies at bpfloader.
#
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="${KERNEL_SRC_INFINITYX:-/Volumes/raphael-build/infinityx_kernel}"
CLANG="${CLANG_DIR:-/Volumes/raphael-build/clang-r522817}"
LOG="${BUILD_LOG:-/Volumes/raphael-build/infinityx-build.log}"

[ -d "$SRC" ]   || { echo "kernel tree not found: $SRC"; exit 1; }
[ -d "$CLANG" ] || { echo "toolchain not found: $CLANG"; exit 1; }

# Fail here rather than 11 minutes in. These four are the fingerprint of the
# ROM's tree; a pristine 4.14 has none of them.
for f in drivers/kernelsu/Makefile fs/susfs.c kernel/bpf/btf.c; do
    [ -f "$SRC/$f" ] || { echo "WRONG TREE: $SRC/$f missing."; exit 1; }
done
nprog="$(grep -c 'BPF_PROG_TYPE_' "$SRC/include/uapi/linux/bpf.h" 2>/dev/null || echo 0)"
[ "$nprog" -ge 36 ] || {
    echo "WRONG TREE: only $nprog BPF_PROG_TYPE_ entries (need >=36)."
    echo "Android 16's netbpfload asks for prog types 18/25 and map type 25;"
    echo "a pristine 4.14 answers -EINVAL and init reboots: bpfloader-failed."
    exit 1
}

# Size to the Docker VM, not the host. The interactive script's sysctl-based
# sizing reports the Mac's RAM, which is not the ceiling here.
MEM_BYTES="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
VM_GB=$(( MEM_BYTES / 1024 / 1024 / 1024 ))
JOBS="$(docker info --format '{{.NCPU}}' 2>/dev/null || echo 4)"
MEM="$(( VM_GB * 9 / 10 ))g"
TMPFS_GB=24

echo "Docker VM: ${VM_GB}G / ${JOBS} CPUs  ->  --memory=$MEM, tmpfs ${TMPFS_GB}g"

# --------------------------------------------------------------------------
# IMPORTANT: use --tmpfs with an explicit `exec`, NOT --mount type=tmpfs.
#
# Docker's --mount type=tmpfs form defaults to nosuid,nodev,NOEXEC. The kernel
# build shells out to dozens of scripts (merge_config.sh, setlocalversion,
# dtc wrappers, ...), so a noexec staging area fails immediately with a
# confusing "Permission denied" that looks like a file-mode problem:
#
#   scripts/kconfig/merge_config.sh: Permission denied
#
# It is not a mode problem - the files are 0755 and rsync preserves them.
# --tmpfs <path>:rw,exec,size=N is the form that permits execution.
# --------------------------------------------------------------------------
exec docker run --rm -i --name infinityx-builder \
    --cpus="$JOBS" --memory="$MEM" \
    --tmpfs /work:rw,exec,size=${TMPFS_GB}g \
    -v "$SRC":/kernel/src \
    -v "$CLANG":/opt/clang \
    -v "$REPO":/cfg:ro \
    android-kernel-builder \
    bash /cfg/scripts/build_kernel_infinityx.sh 2>&1 | tee "$LOG"
