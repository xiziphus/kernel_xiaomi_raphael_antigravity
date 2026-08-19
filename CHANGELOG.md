# Changelog

Docker-enabled kernels for the Xiaomi Redmi K20 Pro (`raphael`).

Both releases are `fastboot boot`-testable first; `fastboot flash boot` only
once you have seen the device come up. Stock restore images are in `backups/`.

---

## kameos-v1 — 2026-08-19

First kernel to run Docker on **KameOS v3.303** (HyperOS 3 / Android 16 system
on MIUI 12.5.6 / Android 11 vendor).

Verified on device: `docker run --rm alpine` returns
`Linux <cid> 4.14.341 aarch64` with outbound networking.

* Base `tingyuwuxin/kernel_xiaomi_raphael@rikka-v5`; BPF backports from
  `HeliumStudio-Dev/kernel_xiaomi_raphael@oss-base` (Zundamon). Clang r522817.
* Namespaces the stock ROM kernel lacks: `pid`, `ipc`, `uts`, `user`
  (stock has only `cgroup`, `mnt`, `net`), plus cgroup `devices` and `pids`.

Eleven distinct blockers had to fall; full narrative with the wrong turns in
[docs/KAMEOS_DOCKER_JOURNEY.md](docs/KAMEOS_DOCKER_JOURNEY.md) §18.

| | blocker | fix |
|---|---|---|
| 1 | netbpfload refuses any kernel <5.4 on a 25Q2 ROM | report `5.4.186` to bpfloader/netbpfload/netd only |
| 2 | `recvmsg4` load EINVAL | declare attach types 14/15/19/20/21/22 |
| 3 | `getsockopt_prog` load EINVAL | `BPF_PROG_TYPE_CGROUP_SOCKOPT` + `struct bpf_sockopt` |
| 4 | `mi_xsk_port_map` errno 22 | declare XSKMAP (17) |
| 5 | `flags:0/128` mismatch | alias it to `array_map_ops` — `dev_map_ops` force-sets `BPF_F_RDONLY_PROG` |
| 6 | osrtpPolicy's XDP program rejected | no-op `bpf_trace_printk`, as the ROM's own kernel does |
| 7 | booted fine, no root, no log anywhere | hexpatch `skip_initramfs` → `want_initramfs` |
| 8 | `attach failed` → netd SIGABRT | attach *and* detach carry their own switches |
| 9 | silent `abort()` in netd | `BPF_PROG_QUERY` is a fourth switch |
| 10 | `nativeGetNextMapKey errno 524` killed system_server | implement `trie_get_next_key` (upstream `b471f2f1de8b`) |
| 11 | `bpf_prog_query(BPF_CGROUP_DEVICE)` blocked `docker run` | add `BPF_CGROUP_DEVICE`/`BPF_PROG_TYPE_CGROUP_DEVICE` |

### Known limits

* **Container device restrictions are not enforced.** The CGROUP_DEVICE program
  loads and attaches but has no runtime hook. Trusted images only.
* Same for sockopt and sendmsg/recvmsg: loaded and attached, never run. The
  loaders cannot tell; tethering's RTP fast path does not accelerate.
* XSKMAP is an array underneath, so AF_XDP redirect is a no-op.
* Root has no default route on Android — `docker pull` needs the `ip rule` that
  `docker-net-watch.sh` maintains, or netd wipes it.

---

## infinityx-v1 — 2026-08-04

Docker on **InfinityX 3.11** (`4.14.356-openela-rc1-perf`). Ran the full stack —
sshd, Portainer, pumpd, notification relays — for days.

Superseded on KameOS: this kernel is AOSP-lineage and **powers the device off
before init** on a MIUI-vendor ROM. Kept because it is the reference for the
InfinityX/EvolutionX line, and because the userspace stack above it is the one
being carried forward.

---

## Restoring the userspace stack

The InfinityX `dockerctl` stack ran Docker in a Debian chroot at `/data/debian`.
On the KameOS kernel Docker runs natively out of `/data/local/tmp/nd`. Only the
bottom two files change — see
[scripts/device/native-compat/](scripts/device/native-compat/).
