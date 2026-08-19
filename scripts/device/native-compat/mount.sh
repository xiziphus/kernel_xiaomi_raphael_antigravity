#!/system/bin/sh
# Native replacement for the chroot layer.
#
# The InfinityX stack ran Docker inside a Debian chroot at /data/debian, and
# ~20 service scripts on top of it (dockerctl and friends)
# call into it through exactly four functions. On the KameOS kernel Docker runs
# NATIVELY on bionic out of /data/local/tmp/nd, so those four are reimplemented
# here and everything above them works unchanged.
#
# Drop this over $STATE/mount.sh; keep net.sh, ui.sh and the rest as they are.

ND=${ND:-/data/local/tmp/nd}
NDBIN=$ND/bin
DOCKER_SOCK=${DOCKER_SOCK:-$ND/docker.sock}
NPATH=$NDBIN:/system/bin:/system/xbin:/data/adb/magisk

# No chroot to mount. Kept as a named no-op so callers do not have to change,
# and so it stays the one place to add native preconditions.
mount_chroot() {
    [ -x "$NDBIN/dockerd" ] || { echo "missing $NDBIN/dockerd -- run scripts/build_native_docker.sh"; return 1; }
    mkdir -p "$ND/data" "$ND/exec" "$ND/run" 2>/dev/null
    return 0
}

umount_chroot() {
    # The mount namespace and its /system/etc overlay die with dockerd; there is
    # nothing of ours left on the host namespace. Verify rather than assume --
    # a stray overlay escaping into init's namespace took this device offline
    # once (see CLAUDE.md).
    if grep -q " overlay " /proc/1/mounts 2>/dev/null; then
        echo "  [warn] an overlay is visible in init's namespace; investigate before rebooting"
        return 1
    fi
    return 0
}

in_chroot() {          # run a command STRING
    mount_chroot >/dev/null || return 1
    if [ "$#" -eq 0 ]; then
        PATH=$NPATH DOCKER_HOST="unix://$DOCKER_SOCK" /system/bin/sh
    else
        PATH=$NPATH DOCKER_HOST="unix://$DOCKER_SOCK" /system/bin/sh -c "$*"
    fi
}

in_chroot_exec() {     # run a command preserving ARGV exactly
    # Passthrough must keep `--format "{{.Names}} {{.Image}}"` as ONE argument;
    # flattening argv into a string splits it and docker rejects the extras.
    mount_chroot >/dev/null || return 1
    cmd="$1"; shift
    case "$cmd" in
        docker) PATH=$NPATH "$NDBIN/docker" -H "unix://$DOCKER_SOCK" "$@" ;;
        *)      PATH=$NPATH DOCKER_HOST="unix://$DOCKER_SOCK" "$cmd" "$@" ;;
    esac
}
