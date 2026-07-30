#!/system/bin/sh
#
# Mount and enter a Debian chroot on /data.  Runs ON THE DEVICE as root.
#
#   su -c /data/local/tmp/debian-chroot.sh [command...]
#
# Why a real chroot and not proot: proot emulates via ptrace and cannot give
# Docker the namespaces or cgroup writes it needs.  Why /data and not /sdcard:
# /sdcard is FUSE and mounted noexec.  /data is f2fs, rw,nosuid,nodev,noatime --
# crucially WITHOUT noexec, so Debian's own PIE binaries execute directly.
#
# That "PIE" detail is the whole reason this works.  Earlier attempts shipped
# prebuilt STATIC runc/crun, which are ELF ET_EXEC; Android's linker refuses
# non-PIE with "unexpected e_type: 2".  Debian's binaries are ET_DYN.
set -u
ROOT=/data/debian
BB=/data/adb/ksu/bin/busybox

# The chroot root MUST be a mount point, not just a directory.
#
# Docker unpacks every image layer inside a private mount namespace and begins
# by doing mount("", "/", NULL, MS_REC|MS_SLAVE, NULL) to stop propagation
# leaking back to the host. If / is a plain directory on /data that call returns
# EINVAL and the pull dies with:
#     failed to register layer: Error processing tar file(exit status 1):
#     remount /, flags: 0x84000: invalid argument
# 0x84000 is exactly MS_REC|MS_SLAVE. Bind-mounting $ROOT onto itself makes it a
# real mount point so the propagation change is legal.
grep -q " $ROOT " /proc/mounts 2>/dev/null || $BB mount --bind "$ROOT" "$ROOT"
$BB mount --make-rprivate "$ROOT" 2>/dev/null

mnt() {  # mnt <type> <src> <relative-target> [options]
    _t="$ROOT/$3"
    mkdir -p "$_t" 2>/dev/null
    if grep -q " $(echo "$_t" | sed 's/[[\.*^$/]/\\&/g') " /proc/mounts 2>/dev/null; then
        return 0                      # already mounted, leave it alone
    fi
    if [ -n "${4:-}" ]; then
        $BB mount -t "$1" -o "$4" "$2" "$_t" 2>/dev/null
    else
        $BB mount -t "$1" "$2" "$_t" 2>/dev/null
    fi
}

# /dev MUST be a tmpfs of our own.  /data is mounted nodev, so device nodes
# created under $ROOT/dev on f2fs would exist but be unusable.  A fresh tmpfs is
# not nodev, so mknod works and containers get their /dev/null, /dev/zero, etc.
mnt tmpfs tmpfs dev mode=755
[ -e "$ROOT/dev/null" ]    || $BB mknod -m 666 "$ROOT/dev/null"    c 1 3
[ -e "$ROOT/dev/zero" ]    || $BB mknod -m 666 "$ROOT/dev/zero"    c 1 5
[ -e "$ROOT/dev/full" ]    || $BB mknod -m 666 "$ROOT/dev/full"    c 1 7
[ -e "$ROOT/dev/random" ]  || $BB mknod -m 666 "$ROOT/dev/random"  c 1 8
[ -e "$ROOT/dev/urandom" ] || $BB mknod -m 666 "$ROOT/dev/urandom" c 1 9
[ -e "$ROOT/dev/tty" ]     || $BB mknod -m 666 "$ROOT/dev/tty"     c 5 0

mnt proc   proc   proc
mnt sysfs  sysfs  sys
mnt devpts devpts dev/pts
mnt tmpfs  tmpfs  dev/shm mode=1777
mnt tmpfs  tmpfs  run     mode=755

# Docker reads and writes the cgroup2 unified hierarchy.  Android already has it
# at /sys/fs/cgroup with the memory and pids controllers available -- pids only
# exists because this kernel was built with CONFIG_CGROUP_PIDS.
mkdir -p "$ROOT/sys/fs/cgroup" 2>/dev/null
grep -q " $ROOT/sys/fs/cgroup " /proc/mounts 2>/dev/null || \
    $BB mount --rbind /sys/fs/cgroup "$ROOT/sys/fs/cgroup" 2>/dev/null

ln -sf /proc/self/fd    "$ROOT/dev/fd"      2>/dev/null
ln -sf /proc/self/fd/0  "$ROOT/dev/stdin"   2>/dev/null
ln -sf /proc/self/fd/1  "$ROOT/dev/stdout"  2>/dev/null
ln -sf /proc/self/fd/2  "$ROOT/dev/stderr"  2>/dev/null

# Android has no /etc/resolv.conf to inherit; DNS comes from properties.
# The image ships /etc/resolv.conf as a symlink to
# /run/systemd/resolve/stub-resolv.conf.  We mount an empty tmpfs on /run and
# there is no systemd-resolved here, so that symlink dangles and writing through
# it fails with ENOENT.  Replace the link with a real file.
rm -f "$ROOT/etc/resolv.conf"
printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\n' > "$ROOT/etc/resolv.conf"
[ -s "$ROOT/etc/hostname" ] || echo raphael > "$ROOT/etc/hostname"
grep -q raphael "$ROOT/etc/hosts" 2>/dev/null || \
    printf '127.0.0.1 localhost\n127.0.1.1 raphael\n' > "$ROOT/etc/hosts"

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
if [ "$#" -eq 0 ]; then
    exec $BB chroot "$ROOT" /bin/bash -l
else
    exec $BB chroot "$ROOT" /bin/bash -lc "$*"
fi
