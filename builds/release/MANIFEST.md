# Release artifacts

Binaries are **not** in git (13 MB+ each; `builds/` holds 1.5 GB of test
images). They are attached to GitHub Releases. This file is the provenance
record so it survives without them.

| artifact | what it is |
|---|---|
| `*-AnyKernel3.zip` | kernel only, no ramdisk — **prefer this for publishing** |
| `boot-*.img` | ready to `fastboot boot` / `fastboot flash boot`; embeds a Magisk-patched ramdisk, i.e. device state |

Build recipe and per-flag rationale: [../../docs/KAMEOS_DOCKER_BUILD.md](../../docs/KAMEOS_DOCKER_BUILD.md)
Full history of how it was reached: [../../docs/KAMEOS_DOCKER_JOURNEY.md](../../docs/KAMEOS_DOCKER_JOURNEY.md) §18

## v1 — 2026-08-19

* Target: KameOS v3.303 (HyperOS 3 / Android 16 system, MIUI 12.5.6 vendor), raphael
* Base: `tingyuwuxin/kernel_xiaomi_raphael@rikka-v5` (4.14.341)
* BPF backports sourced from `HeliumStudio-Dev/kernel_xiaomi_raphael@oss-base` (Zundamon)
* Toolchain: AOSP Clang r522817
* Verified on device: `docker run --rm alpine` → `Linux <cid> aarch64`, outbound networking OK
* sha256 of `boot-raphael-kameos-docker-v1.img`:
  `90764a63bf025cfe63f3ba4cee9947d598e6f6afabe580ae80172318181c4549`
