# raphael Docker Kernel

![License](https://img.shields.io/badge/license-GPL--2.0-blue)
![Device](https://img.shields.io/badge/device-Redmi%20K20%20Pro%20(raphael)-orange)
![Kernel](https://img.shields.io/badge/kernel-4.14-red)
![Docker](https://img.shields.io/badge/docker-29.7.1%20native-brightgreen)

Docker-enabled kernels for the Xiaomi Redmi K20 Pro (`raphael`), plus the build
harness and the on-device userspace that runs containers **natively on bionic —
no chroot, no VM**.

```
$ adb shell su -c 'docker run --rm alpine uname -a'
Linux ba3ef3f3dc33 4.14.341 #1 SMP PREEMPT aarch64 Linux
```

## Releases

| release | ROM | status |
|---|---|---|
| [`kameos-v1`](../../releases) | KameOS v3.303 — HyperOS 3 / Android 16 system on MIUI 12.5.6 vendor | Docker verified on device |
| [`infinityx-v1`](../../releases/tag/infinityx-v1) | InfinityX 3.11 (`4.14.356-openela-rc1-perf`) | ran the full stack for days |

**A kernel only boots the ROM lineage it was built for.** The InfinityX kernel
is AOSP-lineage and powers the device off before init on a MIUI-vendor ROM;
`kameos-v1` is the one for HyperOS/MIUI. See
[CHANGELOG.md](CHANGELOG.md).

## Quick start

Test without touching the boot partition — this is always the first step:

```bash
fastboot boot boot-raphael-kameos-docker-v1.img
```

If it comes up, make it permanent:

```bash
fastboot flash boot boot-raphael-kameos-docker-v1.img
```

Then, on the device:

```bash
su -c /data/local/tmp/nd/native-docker.sh start
su -c '/data/local/tmp/nd/bin/docker -H unix:///data/local/tmp/nd/docker.sock run --rm hello-world'
```

Keep a stock boot image to hand. Restore is
`fastboot flash boot <stock>.img`.

## What is actually hard about this

Not the kernel config. Android 16's `netbpfload` refuses to run on any kernel
below 5.4 and, once you claim 5.4, demands the eBPF surface that goes with it.
Getting from "boots" to `docker run` took eleven distinct blockers, each found
by reading the device rather than guessing:

* a version gate that checks `uname()` before it looks at a single BPF feature
* six cgroup attach types that must be taught to **four** independent switches
  (load, attach, detach, query) — the kernel names none of them when one is missing
* a map alias onto the one allocator that force-sets `BPF_F_RDONLY_PROG`
* a kernel that booted perfectly with no root and no log anywhere, because
  raphael is system-as-root and the bootloader passes `skip_initramfs`
* a `-ENOTSUPP` stub in `lpm_trie.c` that took down `system_server`
* cgroup v2 having no `devices.allow` — the device controller *is* BPF, so
  `docker run` needs a program type this tree never had

Full narrative, including the wrong turns and the three self-inflicted ones:
[docs/KAMEOS_DOCKER_JOURNEY.md](docs/KAMEOS_DOCKER_JOURNEY.md) §18.

## Repository map

| path | what |
|---|---|
| [docs/KAMEOS_DOCKER_BUILD.md](docs/KAMEOS_DOCKER_BUILD.md) | the reproducible build recipe, one row per flag |
| [docs/KAMEOS_DOCKER_JOURNEY.md](docs/KAMEOS_DOCKER_JOURNEY.md) | how it was reached; read before re-debugging anything |
| [docs/NATIVE_DOCKER.md](docs/NATIVE_DOCKER.md) | running Docker on bionic with no chroot; disproves the PIE blocker |
| [docs/TECHNICAL.md](docs/TECHNICAL.md) | boot sequence, FBE key derivation, boot header layout |
| `.github/workflows/build-raphael.yml` | the build; every fix is a toggleable input |
| `scripts/*.py` | one patch per file, each asserting its own post-conditions |
| `scripts/device/` | on-device: `native-docker.sh`, `docker-net.sh`, watchdogs |
| `scripts/device/native-compat/` | runs the InfinityX `dockerctl` stack against the native path |
| `scripts/preflight*.py` | refuses to spend a build, or a device cycle, on a bad input |

## Known limits

* **Container device restrictions are not enforced.** The CGROUP_DEVICE program
  loads and attaches but has no runtime hook. Trusted images only.
* The sockopt and sendmsg/recvmsg hooks are likewise accepted but never run.
  The loaders cannot tell; tethering's hardware offload does not accelerate.
* Root has no default route under Android's per-uid routing, so `docker pull`
  needs the rule `docker-net-watch.sh` maintains — netd wipes it periodically.

## Credits

Built by **[@xiziphus](https://github.com/xiziphus)** —
<https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity>

Standing on other people's work, all GPL-2.0:

* [`tingyuwuxin/kernel_xiaomi_raphael`](https://github.com/tingyuwuxin/kernel_xiaomi_raphael) — Rikka, the base tree for `kameos-v1`
* [`HeliumStudio-Dev/kernel_xiaomi_raphael`](https://github.com/HeliumStudio-Dev/kernel_xiaomi_raphael) — Zundamon; the eBPF backports and the `uname` approach came from here
* [`SOVIET-ANDROID/kernel_xiaomi_raphael`](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael) — the original base for the Android 16 work
* [`onettboots/bool-x_xiaomi_raphael`](https://github.com/onettboots/bool-x_xiaomi_raphael) — first tree to reach init on KameOS
* Docker, containerd and runc upstream; AOSP Clang r522817 and `mkbootimg`

## License

GPL-2.0, following the upstream kernel sources.

## Disclaimer

Flashing custom kernels can brick your device. `fastboot boot` first, every
time, and keep a stock boot image. On raphael a failed `fastboot boot` powers
the device off — it needs a physical power press, not a reflash.
