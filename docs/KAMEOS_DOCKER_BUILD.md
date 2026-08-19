# Building the Docker kernel for KameOS (raphael)

Working as of 2026-08-19. Verified on device: `docker run --rm alpine` returns
`Linux <cid> 4.14.341-Rikka-V5 aarch64` with outbound networking.

## Build

```bash
scripts/launch_build.sh https://github.com/tingyuwuxin/kernel_xiaomi_raphael rikka-v5 KDv1 \
  -f defconfig=noksu.config -f tree_defconfig=raphael_defconfig \
  -f fake_uname=5.4.186 \
  -f bpf_attr_abi=false -f bpf_devmap_hash=false -f rdonly_prog_flag=false \
  -f cgroup_attach_types=true -f cgroup_sockopt=true -f xskmap_alias=true \
  -f trace_printk_dummy=true -f trie_next_key=true -f cgroup_device=true
```

Then `scripts/repack_kameos.sh <Image.gz-dtb> KDv1`, which also applies the
`want_initramfs` hexpatch and uses `builds/ramdisk-magisk.cpio.gz`.

Reference image: `builds/boot-raphael-kameos-docker-v1.img`
sha256 `90764a63bf025cfe63f3ba4cee9947d598e6f6afabe580ae80172318181c4549`

## What each flag is for

| flag | wall it clears |
|---|---|
| `fake_uname=5.4.186` | netbpfload refuses <5.4 on a 25Q2 ROM. Exactly 5.4.186 — higher pulls in 5.9/5.10-gated programs. |
| `cgroup_attach_types` | declares sendmsg4/6, recvmsg4/6, get/setsockopt; wires them into load, attach, detach **and query** |
| `cgroup_sockopt` | `BPF_PROG_TYPE_CGROUP_SOCKOPT` + `struct bpf_sockopt` |
| `xskmap_alias` | XSKMAP(17) → `array_map_ops` for Xiaomi's osrtpPolicy.o |
| `trace_printk_dummy` | its XDP program calls helper 6 and is non-optional |
| `trie_next_key` | `local_net_access` LPM_TRIE; without it NetworkStatsService kills system_server |
| `cgroup_device` | runc's cgroup-v2 device program; without it `docker run` fails |
| `noksu.config` | in-tree KernelSU stops Magisk taking over |

`bpf_attr_abi`/`bpf_devmap_hash`/`rdonly_prog_flag` are **off**: they target
bool-x-era defects Rikka does not have, and are disproven (see JOURNEY §18.4).

## Flashing (persistent)

`fastboot boot` is volatile. To persist:

```bash
fastboot flash boot builds/boot-raphael-kameos-docker-v1.img
```

Restore: `fastboot flash boot builds/kameos-docker-20260804-024211/boot-kameos-stock.img`

## Running Docker

```bash
adb shell su -c /data/local/tmp/nd/native-docker.sh start
adb shell su -c 'ip rule add pref 29999 lookup wlan0'   # root has no default route
```

The `ip rule` is wiped by netd periodically — run `docker-net-watch.sh` to keep
it applied. Android's per-uid routing means dockerd itself cannot reach the
registry without it, so `docker pull` fails with "network is unreachable".

## Known limits

* **Device restrictions inside containers are not enforced.** CGROUP_DEVICE
  programs load and attach but have no runtime hook. Trusted images only.
* Same for the sockopt and sendmsg/recvmsg hooks — loaded and attached, never
  run. netbpfload and netd cannot tell; tethering's RTP fast path does not
  accelerate.
* XSKMAP is an array underneath, so AF_XDP redirect is a no-op.
