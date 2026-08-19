#!/system/bin/sh
# Native dockerd lifecycle. Replaces the chroot version.

daemon_start() {
    running && { ok "dockerd already running"; return 0; }
    mount_chroot >/dev/null || return 1

    # Stale runtime state is the single most common reason this fails to come
    # up, and the message it produces is misleading. Both pidfiles survive a
    # reboot in /data, and Linux recycles PIDs: dockerd refused to start
    # because "PID 2592 is still running", and containerd's stale pid pointed
    # at what had become system_server. Clear both every time.
    rm -f "$ND/docker.pid" "$ND/docker.sock" 2>/dev/null
    rm -rf "$ND/exec" "$ND/run" 2>/dev/null

    "$ND/native-docker.sh" start || return 1

    # Android gives root no default route (per-uid routing), so dockerd itself
    # cannot reach a registry and `docker pull` fails "network is unreachable"
    # even though containers are fine. net_apply covers container egress; this
    # covers the daemon. netd wipes it periodically -- see docker-net-watch.sh.
    net_apply 2>/dev/null
    daemon_route

    ok "dockerd started"
}

# Give root's own traffic a default route via the first uplink that has one.
# Uses uplinks() from lib.sh, which parses `ip route show table all` rather
# than looking tables up by name -- netd's name map is not reliably resolvable
# from a boot service, and egress rules were silently never installed.
daemon_route() {
    for t in $(uplinks); do
        ip rule del pref 29999 2>/dev/null
        ip rule add pref 29999 lookup "$t" 2>/dev/null && return 0
    done
    warn "no uplink with a default route; docker pull will fail"
    return 1
}

daemon_stop() {
    running || { ok "dockerd not running"; return 0; }
    "$ND/native-docker.sh" stop >/dev/null 2>&1
    sleep 1
    for p in dockerd containerd containerd-shim-runc-v2; do
        pkill -9 -f "$NDBIN/$p" 2>/dev/null
    done
    rm -f "$ND/docker.pid" "$ND/docker.sock" 2>/dev/null
    rm -rf "$ND/exec" "$ND/run" 2>/dev/null
    ip rule del pref 29999 2>/dev/null
    umount_chroot
    ok "dockerd stopped"
}
