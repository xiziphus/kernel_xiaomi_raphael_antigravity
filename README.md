# Docker on a Redmi K20 Pro

![License](https://img.shields.io/badge/license-GPL--2.0-blue)
![Device](https://img.shields.io/badge/device-Redmi%20K20%20Pro%20%2F%20Mi%209T%20Pro-orange)
![Docker](https://img.shields.io/badge/docker-29.7.1-brightgreen)

Real Docker on an Android phone. Not a VM, not a Linux chroot — `dockerd` runs
directly on Android, and containers get their own PID, network and mount
namespaces from the kernel.

```
$ docker run --rm alpine uname -a
Linux ba3ef3f3dc33 4.14.341 #1 SMP PREEMPT aarch64 Linux
```

Stock Android kernels can't do this: they ship without the namespaces Docker
needs. This repo builds one that can, and gives you the userspace to go with it.

## Will this work on my phone?

You need **all** of these:

- [ ] Xiaomi Redmi K20 Pro or Mi 9T Pro (`raphael` / `raphaelin`) — no other device
- [ ] Bootloader unlocked
- [ ] Root (Magisk). The kernel boots without it, but you can't start Docker without it
- [ ] A stock `boot.img` for your ROM, saved somewhere safe
- [ ] `adb` and `fastboot` on a computer

**Which kernel you need depends on your ROM**, and picking the wrong one just
fails to boot:

| Your ROM | Download |
|---|---|
| KameOS, or another HyperOS / MIUI-based Android 16 ROM | [`kameos-v1`](../../releases) |
| InfinityX 3.11, EvolutionX, other AOSP-based ROMs | [`infinityx-v1`](../../releases/tag/infinityx-v1) |

If you're unsure, `adb shell getprop ro.vendor.build.fingerprint` — if it says
`raphael:11/RKQ1...MIUI`-style, you're on the MIUI side.

## Install

**1. Try it without installing anything.** This does not touch your phone's
storage. If the kernel is wrong, you reboot and nothing has changed.

```bash
adb reboot bootloader
fastboot boot boot-raphael-kameos-docker-v1.img
```

Wait ~90 seconds. If your phone boots normally, it worked.

> If the screen stays black and the phone seems dead, it isn't — a failed boot
> powers it off. Hold **Power** for 3 seconds to turn it back on. Your phone is
> untouched.

**2. Make it permanent** — only after step 1 worked:

```bash
fastboot flash boot boot-raphael-kameos-docker-v1.img
```

**3. Install Docker's userspace** (once):

```bash
git clone https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity
cd kernel_xiaomi_raphael_antigravity
./scripts/build_native_docker.sh      # builds and pushes to the phone
```

## Using it

```bash
adb shell su -c /data/local/tmp/nd/native-docker.sh start
```

Then, on the phone (or over `adb shell su`):

```bash
alias docker='/data/local/tmp/nd/bin/docker -H unix:///data/local/tmp/nd/docker.sock'

docker run --rm alpine uname -a
docker run -d --restart=always -p 8080:80 nginx
docker ps
```

Port 8080 is then reachable from anything on your Wi-Fi. Images pull from
Docker Hub over the phone's own connection.

To start Docker automatically at boot, copy
`scripts/device/service.d-native-docker.sh` into `/data/adb/service.d/`.

## Going back

```bash
fastboot flash boot <your-stock-boot.img>
```

Or if you only did step 1, just reboot.

## What doesn't work

Be aware of these before you rely on it:

- **Containers are not isolated from your device's hardware.** The kernel
  accepts Docker's device restrictions but doesn't enforce them, so a container
  can reach device nodes it shouldn't. **Run images you trust.**
- **`docker pull` needs a helper running.** Android keeps rewriting the routing
  table, which cuts the daemon off from the internet. Run
  `scripts/device/docker-net-watch.sh` in the background, or re-run
  `docker-net.sh` when pulls start failing.
- Tethering's hardware acceleration is disabled while this kernel is running.
  Tethering itself still works.
- This is a personal project, tested on one phone. It is not a product.

## Under the hood

Android 16 refuses to boot on a kernel it thinks is too old — its network stack
checks the kernel version before it checks anything else — and once you satisfy
that, it demands a pile of modern eBPF features that a 2017-era 4.14 kernel
doesn't have. Getting from "the kernel boots" to `docker run` meant clearing
eleven separate blockers, each found by reading logs off the device rather than
guessing.

- [**How it was built**](docs/KAMEOS_DOCKER_BUILD.md) — the exact recipe, one row per fix
- [**How it was figured out**](docs/KAMEOS_DOCKER_JOURNEY.md) — the full debugging story, wrong turns included
- [**Docker on bionic**](docs/NATIVE_DOCKER.md) — why no chroot is needed
- [**Changelog**](CHANGELOG.md)

Every fix is a separate script under `scripts/` and a toggleable input to the
GitHub Actions build, so you can rebuild any of this yourself.

## Credits

Built by **[@xiziphus](https://github.com/xiziphus)**.

This stands on other people's kernels, all GPL-2.0:

- [Rikka](https://github.com/tingyuwuxin/kernel_xiaomi_raphael) — the base tree
- [Zundamon / HeliumStudio](https://github.com/HeliumStudio-Dev/kernel_xiaomi_raphael) — the eBPF backports
- [SOVIET-ANDROID](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael), [bool-x](https://github.com/onettboots/bool-x_xiaomi_raphael)

Docker, containerd and runc are upstream and unmodified apart from two path
patches ([`patches/`](patches/)).

## License

GPL-2.0, following the upstream kernel sources.

---

⚠️ Flashing kernels can brick a phone. Always `fastboot boot` first, and keep a
stock boot image. Nothing here is anyone's fault but yours.
