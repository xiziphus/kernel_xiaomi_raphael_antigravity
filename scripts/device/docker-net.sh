#!/system/bin/sh
##########################################################################
# Make Docker bridge networking work under Android's netd.
#
# Android does NOT use a conventional routing table. netd installs per-network
# tables (wlan0, rmnet_data*) selected by fwmark/uid rules, and it DELETES the
# usual "32766: from all lookup main" rule -- the rule list ends at
# "32000: from all unreachable". Docker's routes live in main, so without help
# they are never consulted and every container packet dies.
#
# Scope is Docker's whole default address pool (172.16.0.0/12), not just
# docker0's 172.17.0.0/16: every compose project creates its own bridge on the
# next free /16 (172.18, 172.19, ...) behind an interface named br-<id>. Rules
# are matched on SUBNET rather than interface name so they cover all of them.
#
# Re-run after a reboot or a Wi-Fi reconnect; netd rewrites its rules then.
##########################################################################
set -u
POOL="${DOCKER_POOL:-172.16.0.0/12}"
IFACE="${UPLINK:-wlan0}"

# 1. Egress: container -> internet. Without this the packet has no default route.
ip rule del from "$POOL" lookup "$IFACE" 2>/dev/null
ip rule add from "$POOL" lookup "$IFACE" priority 11500

# 2. Return path: replies are un-NAT'd back to a container address and then need
#    the bridge route, which only exists in table main.
ip rule del to "$POOL" lookup main 2>/dev/null
ip rule add to "$POOL" lookup main priority 11400

# 3. Android's tetherctrl_FORWARD ends in "DROP all" because tethering is off,
#    and FORWARD reaches it before anything Docker installs. Jump the queue.
#    Docker's own DOCKER chain still decides which published ports are open, so
#    this does not expose anything Docker has not published.
iptables -D FORWARD -s "$POOL" -j ACCEPT 2>/dev/null
iptables -D FORWARD -d "$POOL" -j ACCEPT 2>/dev/null
iptables -I FORWARD 1 -s "$POOL" -j ACCEPT
iptables -I FORWARD 2 -d "$POOL" -j ACCEPT

echo "docker networking: rules applied for $POOL via $IFACE"
ip rule show 2>/dev/null | grep -E "172\.(1[6-9]|2[0-9]|3[01])\." | sed 's/^/  /'
