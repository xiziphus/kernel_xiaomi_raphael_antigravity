# The phone stack, as code

Everything running on the phone, reproducible from this directory. No ad-hoc
`adb shell` incantations — that is how the first deploy went and it is why it
took all afternoon.

    ./stack/deploy.sh          # push + start everything
    ./stack/deploy.sh status   # what is up
    ./stack/deploy.sh logs erp

## What runs where, and why

| piece | how it runs | why |
|---|---|---|
| dockerd + containerd | native, `/data/local/tmp/nd` | needs the Docker kernel |
| cloudflared | **native host process**, not a container | must survive a dockerd crash — that is exactly when you need remote access. It also cannot work in a container: Android's netd `EPERM`s container UDP, so DNS dies, and the edge dial times out. |
| copyparty, Portainer, ERPNext | containers via compose | ordinary workloads |

## Android-specific traps, all handled by the scripts

These are not Docker problems. They are what makes this phone different from a
VPS, and each one cost real time to find:

1. **Root has no default route.** Android routes per-UID, so `dockerd` cannot
   reach a registry and `docker pull` fails "network is unreachable" while
   containers are fine. Needs `ip rule add pref 29999 lookup <uplink>`.
2. **netd wipes that rule periodically.** `docker-net-watch.sh` re-applies it.
   Without it, pulls and the tunnel break minutes later, seemingly at random.
3. **There is no `/etc/resolv.conf`.** Go binaries fall back to `[::1]:53` and
   every lookup is refused. `nd-setup` overlays `/system/etc` inside a private
   mount namespace to supply one.
4. **`nd-setup` must be run under `unshare -m`.** It deliberately does not
   unshare itself. Run it directly and the overlay lands in init's namespace;
   its own safety check catches that and aborts, because an escaped overlay
   took this device offline once.
5. **Each `nd-setup` needs its own state dir**, or the second one fails
   `device or resource busy` on the overlay workdir.
6. **`/sdcard` does not bind-mount into containers.** sdcardfs does not
   propagate, so the mount silently becomes an empty tmpfs — copyparty caught
   this and refused writes rather than losing uploads. Use `/data/...`.
7. **`pkill -f cloudflared` kills the shell that is starting cloudflared**,
   because the pattern matches its own command line. Match the binary path.

## Credentials

Not in git. `deploy.sh` generates them on first run into
`/data/adb/stack.env` on the phone and prints them once.
