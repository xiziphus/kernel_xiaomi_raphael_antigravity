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

**Does this help if you have a different phone?** The kernel patches here are
not device-specific — they close gaps between a 2017-era 4.14 kernel and what
Android 16's network stack demands, and any device stuck on an old kernel with
a new Android will hit the same walls in the same order. What *is* specific to
this phone is the boot image packing and which ROM lineage a kernel will boot.
So the fixes should port; the release binaries will not. The
[build recipe](docs/KAMEOS_DOCKER_BUILD.md) marks which is which.

## Will this work on my phone?

You need **all** of these:

- [ ] Xiaomi Redmi K20 Pro or Mi 9T Pro (`raphael` / `raphaelin`) — no other device
- [ ] Bootloader unlocked
- [ ] Root via [Magisk](https://github.com/topjohnwu/Magisk) (the standard Android
      rooting tool). The kernel boots fine without root — you just can't start
      Docker, since `dockerd` needs it
- [ ] A stock `boot.img` for your ROM, saved somewhere safe
- [ ] `adb` and `fastboot` on a computer (Google's
      [platform-tools](https://developer.android.com/tools/releases/platform-tools))

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

This compiles Docker, containerd and runc for arm64 and pushes them, along with
the `native-docker.sh` launcher used below, to `/data/local/tmp/nd/` on the
phone.

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
- **Battery and heat.** An idle `dockerd` costs little, but a busy container
  will warm the phone and drain it. Keep it plugged in if it's always-on.
- This is a personal project, tested on one phone. It is not a product.

## Under the hood

Android 16 refuses to boot on a kernel it thinks is too old — its network stack
checks `uname()` before it looks at a single feature — and once you satisfy
that, it demands a pile of modern eBPF the 4.14 kernel never had. Eleven
separate things had to be fixed to get from "the kernel boots" to `docker run`.
A sample, so you can judge the depth without leaving this page:

- Android's BPF loader checks the kernel *version string* before any feature,
  so the kernel reports `5.4.186` to that one process and nothing else.
- Six cgroup attach types had to be taught to **four** independent kernel
  switches — load, attach, detach, query. Miss one and the kernel names none
  of them; you get a bare `abort()` in a daemon three layers away.
- The kernel booted perfectly with no root and no log anywhere, because this
  phone is system-as-root and the bootloader tells the kernel to skip the
  ramdisk that root lives in.
- On cgroup v2 there is no `devices.allow` file — the device controller *is* a
  BPF program — so `docker run` needs a program type this kernel never had.

Each was found by reading logs off the device, not by guessing.

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
