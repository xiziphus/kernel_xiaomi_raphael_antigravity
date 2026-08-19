#!/usr/bin/env bash
# Deploy / manage the whole phone stack. Idempotent -- safe to re-run.
#
# Written after the first deploy was done by hand, one adb command at a time,
# and could not be reproduced. Every Android-specific workaround below is
# explained in README.md; none of them are Docker's fault.
set -uo pipefail
ND=/data/local/tmp/nd
CF=/data/local/tmp/cf
ENVF=/data/adb/stack.env
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
D="$ND/bin/docker -H unix://$ND/docker.sock"
DC="$ND/bin/docker-compose"

sh_() { adb shell "su -c '$*'" 2>/dev/null | tr -d '\r'; }
say() { printf '  %s\n' "$*"; }

need_device() {
  [ "$(adb get-state 2>/dev/null)" = device ] || { echo "no device on adb"; exit 1; }
  sh_ "pgrep -f $ND/bin/dockerd >/dev/null" || { echo "dockerd not running: su -c $ND/native-docker.sh start"; exit 1; }
}

# Android routes per-UID; root gets no default route, so dockerd cannot reach a
# registry even though containers can. netd wipes this, hence the watcher.
route() {
  for t in $(sh_ "ip route show table all 2>/dev/null | awk '/^default/{print \$NF}'" | sort -u); do
    sh_ "ip rule del pref 29999 2>/dev/null; ip rule add pref 29999 lookup $t" && { say "route via table $t"; return; }
  done
}
watcher() {
  sh_ "pgrep -f docker-net-watch >/dev/null" && { say "net watcher already running"; return; }
  sh_ "nohup $ND/docker-net-watch.sh >$ND/netwatch.log 2>&1 & echo ok" >/dev/null
  say "net watcher started"
}

# cloudflared runs NATIVE, never in a container: Android EPERMs container UDP
# so DNS dies, and it must outlive a dockerd crash. nd-setup supplies the
# /etc/resolv.conf Android lacks, and must be run under `unshare -m`.
tunnel() {
  # match the binary path, not "cloudflared" -- the loose pattern matches the
  # very shell starting it and kills it before nohup runs.
  sh_ "pkill -9 -f $CF/cloudflared; pkill -9 -f nd-setup" >/dev/null; sleep 2
  sh_ "mkdir -p $CF/etcup $CF/etcwork"
  adb shell "su -c 'cd $CF && nohup unshare -m $ND/bin/nd-setup $CF ./cloudflared --config $CF/config.yml --no-autoupdate --protocol http2 tunnel run > $CF/cf.log 2>&1 &'" >/dev/null 2>&1
  for i in $(seq 1 20); do
    sleep 5
    [ "$(sh_ "grep -ic 'registered tunnel connection' $CF/cf.log")" -gt 0 ] 2>/dev/null && { say "tunnel up"; return; }
  done
  say "tunnel did NOT register -- see $CF/cf.log"
}

gen_env() {
  sh_ "[ -f $ENVF ]" && return
  say "generating credentials -> $ENVF (shown once)"
  local cp; cp=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c20)
  sh_ "mkdir -p /data/adb; printf 'COPYPARTY_USER=dell\nCOPYPARTY_PASS=%s\n' '$cp' > $ENVF; chmod 600 $ENVF"
  echo "  copyparty: dell / $cp"
}

case "${1:-up}" in
  up)
    need_device; route; watcher; gen_env
    adb push -q "$HERE/compose.yml" /sdcard/stack-compose.yml >/dev/null 2>&1
    sh_ "mkdir -p /data/stack /data/copyparty /data/portainer; cp /sdcard/stack-compose.yml /data/stack/compose.yml"
    sh_ "cd /data/stack && DOCKER_HOST=unix://$ND/docker.sock $DC --env-file $ENVF -p stack up -d" | tail -3
    sh_ "cd /data/erpnext && DOCKER_HOST=unix://$ND/docker.sock $DC -p erpnext up -d" | tail -3
    tunnel
    "$0" status
    ;;
  status)
    need_device
    say "containers:"
    # No nested single quotes: sh_ wraps the whole command in them already,
    # which silently produced an empty list the first time.
    sh_ "$D ps --format {{.Names}}=={{.Status}}" | sed 's/==/  /' | sed 's/^/    /' 
    say "tunnel: $(sh_ "pgrep -f $CF/cloudflared >/dev/null && echo running || echo DOWN")"
    for h in files portainer erp helpdesk; do
      printf '  %-10s %s\n' "$h" "$(curl -s -m 15 -o /dev/null -w '%{http_code}' "https://$h.stratifyx.win/" 2>/dev/null)"
    done
    ;;
  logs)   need_device; sh_ "$D logs --tail 40 ${2:?container}" ;;
  down)   need_device
          sh_ "cd /data/stack   && DOCKER_HOST=unix://$ND/docker.sock $DC -p stack down"   | tail -2
          sh_ "cd /data/erpnext && DOCKER_HOST=unix://$ND/docker.sock $DC -p erpnext down" | tail -2
          sh_ "pkill -9 -f $CF/cloudflared" >/dev/null; say "tunnel stopped" ;;
  *) echo "usage: $0 {up|status|logs <container>|down}"; exit 2 ;;
esac
