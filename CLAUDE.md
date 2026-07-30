# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

**This repo contains no kernel source.** It is a build harness, config fragment, and documentation set for producing a Docker-enabled kernel for the Xiaomi Redmi K20 Pro (`raphael`) on Android 16.

The actual kernel tree is cloned separately from [SOVIET-ANDROID/kernel_xiaomi_raphael](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael) and lives outside git (`kernel_source/` and `soviet_kernel_stock/` are gitignored; the scripts default to `/Volumes/android-kernel/soviet_kernel_stock`). Everything here manipulates that external tree from the outside.

The project is explicitly **not maintained** — it is a working reference/foundation, not an active codebase.

## Build architecture

Three layers, and the seam between them is the main thing to understand:

```
host wrapper                    →  docker container            →  in-container build script
run_builder_soviet.sh              android-kernel-builder          scripts/build_kernel_soviet_docker.sh
scripts/build_and_flash_*.sh       (built from ./Dockerfile)       (runs as /kernel/soviet_kernel_stock/build_docker.sh)
```

**The host↔container path contract is hardcoded, not parameterized.** The in-container scripts use absolute container paths (`/kernel/soviet_kernel_stock`, `/opt/clang`) that only exist because the wrapper mounts them there. `build_and_flash_interactive.sh` additionally *copies* files into the kernel tree before launching Docker:

- `scripts/build_kernel_soviet_docker.sh` → `$KERNEL_DIR/build_docker.sh`
- `docker.config` → `$KERNEL_DIR/docker.config`

So editing `scripts/build_kernel_soviet_docker.sh` only takes effect on the next run through the interactive script (or after manually re-copying). A stale `build_docker.sh` inside the kernel tree will silently win.

`build_and_flash_interactive.sh` also uses repo-root-relative paths (`cp scripts/...`, `python3 mkbootimg_src/...`) without `cd`-ing, so **it must be invoked from the repo root**: `./scripts/build_and_flash_interactive.sh`.

### Config strategy

The build does *not* ship a defconfig. It regenerates config on every run:

1. `make O=out raphael_defconfig` (from the kernel tree)
2. `scripts/kconfig/merge_config.sh -m -O out out/.config docker.config` (this repo's fragment)
3. `make O=out olddefconfig`

`merge_config.sh` is mandatory here. Earlier attempts used `scripts/config --enable ...` and `olddefconfig` silently dropped the flags due to unmet Kconfig dependencies. The `configure_kernel*.sh` scripts still use that abandoned approach — see "Dead script generations" below.

`raphael_docker_defconfig` and `stock_raphael_defconfig_original.txt` are captured snapshots for diffing (they differ only by the Docker flags plus `CONFIG_LOCALVERSION`), not build inputs.

## Commands

```bash
make build      # → ./run_builder_soviet.sh (Docker build of the external kernel tree)
make clean      # rm -rf /Volumes/android-kernel/soviet_kernel_stock/out  (hardcoded path)
make verify     # → ./scripts/verify_kernel.sh — runs feature checks over ADB on a connected device
make test       # verify + raw /proc/cgroups and /proc/self/ns dumps
make flash      # prompts, then fastboot flash boot release/boot-raphael-docker-v1.0.img
make release    # copies Image.gz-dtb from the external out/ into release/

./scripts/build_and_flash_interactive.sh   # menu-driven: deps → clone → build → repack → flash → AnyKernel zip
```

There is no test suite. "Testing" means `scripts/verify_kernel.sh` against a physical device over ADB, plus booting it. CI (`.github/workflows/verify.yml`) only checks that required `CONFIG_*` lines exist in `docker.config`, that doc files are present, and lints markdown — **it never compiles a kernel**.

Repack after building:

```bash
python3 mkbootimg_src/mkbootimg.py \
  --kernel out/arch/arm64/boot/Image.gz-dtb \
  --ramdisk stock_kernel_extracted/ramdisk.cpio.gz \
  --cmdline "<verbatim stock cmdline>" \
  --base 0x10000000 --pagesize 4096 \
  --os_version 0 --os_patch_level 2025-10 \
  --output boot.img
```

Inspect any boot image with `python3 scripts/unpack_boot.py boot.img out_dir/` — it prints header fields and writes `boot_params.txt`.

## Non-obvious invariants

These were each discovered by bricking or bootlooping a device (full history in [docs/JOURNEY.md](docs/JOURNEY.md)). Do not "clean up" past them:

- **`--os_patch_level 2025-10` is load-bearing.** Android FBE derives encryption keys from the boot header's patch level. Omitting it defaults to `2000-00`, Keymaster refuses to release keys, and the device shows "Can't load Android system. Your data may be corrupt." This is the single most expensive mistake in this project's history.
- **Toolchain must be Android Clang 18.0.1 (r522817).** Stock was built with it; other Clang versions (e.g. Proton 13) produce ABI-incompatible kernels that bootloop.
- **Kernel source must be SOVIET-ANDROID, not Evolution X.** The ROM ships `4.14.353-openela-SOVIET-STAR` regardless of being "Evolution X"; matching the ROM name instead of `uname -r` caused a bootloop.
- **The kernel cmdline must be copied verbatim** from the stock boot image (see `stock_kernel_extracted/boot_params.txt`).
- **`/proc/config.gz` lies.** It can be stale relative to what was compiled. Trust order: `out/include/generated/autoconf.h` > `out/.config` > `/proc/config.gz`. Verify features functionally via `/proc/cgroups`, `/proc/self/ns/*`, and `unshare`.
- **Docker's kernel side is complete; the userspace side is blocked.** `runc`/`crun` are statically linked (ELF `ET_EXEC`), and Android rejects non-PIE binaries with `unexpected e_type: 2`. This is not a kernel bug — do not chase it in the config. [docs/DISABLE_PIE.md](docs/DISABLE_PIE.md) sketches an (unrecommended, security-degrading) `fs/binfmt_elf.c` patch.

## Build environment on this host (important)

**This repo sits on an exFAT volume, which cannot host a Linux source tree.** Verified: case-INSENSITIVE, no hardlinks, no real ownership (`noowners`). 4.14 netfilter alone ships `xt_CONNMARK.h`/`xt_connmark.h`, `xt_MARK.h`/`xt_mark.h`, `xt_DSCP.h`/`xt_dscp.h` — on checkout one silently overwrites the other. The stray `._*` files and `non-monotonic index` git warnings throughout are the same root cause and are harmless noise.

The kernel tree and toolchain therefore live in **`build.sparseimage`**, a case-sensitive APFS sparse image in this folder (gitignored, grows on demand, mounts at `/Volumes/raphael-build`). Always start with:

```bash
source scripts/build-env.sh          # attaches the image, exports KERNEL_SRC/CLANG_DIR, sizes the build
./scripts/build_and_flash_interactive.sh
```

`scripts/build-env.sh` also fixes a sizing bug: the interactive script derives container memory from `sysctl hw.memsize` (the *host's* RAM), but on Docker Desktop the real ceiling is the Linux VM's RAM. Over-requesting doesn't fail loudly — the container is OOM-killed mid-link. It derives `BUILD_MEM` from `docker info` instead. `raphael_defconfig` sets `CONFIG_LTO_CLANG=y`, and the ld.lld ThinLTO link is the memory spike; give the Docker VM 32 GB+.

### Upstream branches

There is **no `main` branch** — `git clone -b main` fails outright. Branches are per-Android-release. Default and correct for an Android 16 ROM is **`16.0`** (currently 4.14.357, KernelSU-Next 3.2.0 at `drivers/kernelsu`). `16.0-SUSFS` tracks slightly ahead but adds root-hiding; `16.0-susfs` (lowercase) and `staging` are stale by a year. Override with `KERNEL_REF=`.

Note the shipped v1.0 image was 4.14.**353**; upstream is now .357, so the script's `EXPECTED_SUBLEVEL` drift warning fires by design.

### Options that do NOT work on this tree (learned by building, 2026-07-29)

`raphael_defconfig` ships these off, so the code behind them has never faced a compiler. Config validation cannot catch any of it — `merge_config.sh` retention was a clean 63/63 while the build failed:

| Option | Failure |
|---|---|
| `CONFIG_FTRACE` + `FUNCTION_TRACER` | 9 errors. `drivers/android/binder_trace.h:400,416` reference undeclared `binder_command_strings`/`binder_return_strings`; `kernel/trace/trace_event_perf.c:433` redefines `event`. Enabling `FTRACE` instantiates the `TRACE_EVENT` macros for real instead of as no-ops. |
| `CONFIG_DEBUG_FS` | `drivers/platform/msm/ipa/ipa_clients/ipa_eth.c:131,675` call `ipa3_eth_debugfs_init`/`_add_node` from inside `#ifdef CONFIG_DEBUG_FS` without including `ipa_v3/ipa_i.h` where they're declared; `-Werror` kills it. Fixable in one line, but **8 more files under `drivers/platform/msm/ipa/` have equally untested `CONFIG_DEBUG_FS` ifdefs**. |
| `CONFIG_LLVM_POLLY` (**on by default!**) | Not a failure — a **hang**. `Makefile:763` appends 8 polyhedral-optimizer flags incl. `-polly-reschedule=1`. Polly's ISL solver is exponential worst-case; `qca-wifi-host-cmn/.../reg_build_chan_list.c` (1245 lines) ran **20+ min at 99% CPU** and never finished. Disable via the Kconfig symbol — the `ifdef` removes all 8 flags, no source patch. |
| `CONFIG_MODULES` | Builds fine, but trips modpost: `raphael_defconfig:703` explicitly sets `# CONFIG_SECTION_MISMATCH_WARN_ONLY is not set`, making mismatches **fatal**. `CONFIG_MODULES=y` makes `EXPORT_SYMBOL` emit `__ksymtab` entries (`include/linux/export.h:40,103,124` — it's a no-op without MODULES), exposing `drivers/regulator/stub-regulator.c:296`, which exports the `__init` function `regulator_stub_init`. Needs `CONFIG_SECTION_MISMATCH_WARN_ONLY=y`. Benign here: zero symbols are `=m`, so nothing can dereference the dangling entry. |

Diagnosing a mismatch requires `CONFIG_DEBUG_SECTION_MISMATCH=y` — without it `modpost.c` prints only the count. Drop it again afterwards; it adds `-fno-inline-functions-called-once`.

### Builds are I/O-bound, not CPU-bound

The tree lives on a bind-mounted sparse image, so every `open()` crosses virtiofs: **893 µs vs 4.2 µs** on the container's own fs (213×). At 550–669 headers per object × ~3400 objects that's **~2M opens/build**. Measured split: 20% user / 42% sys / 22% iowait. A cold build is ~31 min; staging the tree into a container tmpfs and baking clang into the image should get it to ~11.

Cheap wins: `# CONFIG_LOCALVERSION_AUTO is not set` (`setlocalversion` runs `git status`, which takes **154 s** here, on every build via a `FORCE` rule), and moving `--thinlto-cache-dir` (`Makefile:972`, currently relative to `out/`, destroyed by the unconditional `rm -rf out`).

**ccache cannot help while on virtiofs** — a direct-mode hit still reads every header to hash it (~536 ms/hit vs an 88 ms full compile). Also note `setup_environment` only builds the Docker image when it's **absent**, so Dockerfile edits need `docker build --no-cache` or a tag bump.

### Config interactions worth knowing

- `LTO_CLANG` (`arch/Kconfig:669`) depends on `!FTRACE_MCOUNT_RECORD || HAVE_C_RECORDMCOUNT`. `arch/arm64/Kconfig:114` selects `HAVE_C_RECORDMCOUNT`, so **ftrace and LTO do coexist on arm64**.
- `LTO_CLANG` has no `!MODULES` dependency, and the defconfig sets no `CFI_CLANG`, `TRIM_UNUSED_KSYMS`, `MODULE_SIG` or `MODVERSIONS` — so `CONFIG_MODULES=y` is safe to add.
- 4.14 splits nftables NAT per address family. `NFT_NAT`/`NFT_MASQ`/`NFT_REDIR` alone are **not** functional; you also need `NFT_CHAIN_NAT_IPV4/6`, `NFT_MASQ_IPV4/6`, `NFT_REDIR_IPV4/6`. Modern kernels dropped these spellings.

## Missing pieces after a fresh clone

Several things the scripts call are not actually present in a clean checkout:

- **`mkbootimg_src/` is a gitlink (submodule) with no `.gitmodules`** — it clones empty, so `python3 mkbootimg_src/mkbootimg.py` fails and `verify_repo_integrity` aborts the interactive script on startup. Repopulate with:
  ```bash
  rmdir mkbootimg_src && git clone --depth 1 \
    https://android.googlesource.com/platform/system/tools/mkbootimg mkbootimg_src
  ```
- **`AnyKernel3/` contains only `anykernel.sh`.** `create_anykernel_zip()` skips its `git clone` because the directory exists, so the resulting zip lacks `tools/ak3-core.sh` and won't flash. Clone [osm0sis/AnyKernel3](https://github.com/osm0sis/AnyKernel3) into it, preserving the repo's customized `anykernel.sh`.
- **`stock_kernel_extracted/ramdisk.cpio.gz` is gitignored** (`*.gz`). Repacking requires pulling a `boot_backup.img` off a device first and running `scripts/unpack_boot.py`. The committed `stock_kernel_extracted*/` dirs hold only the kernel and header dump.
- `run_builder_soviet.sh` hardcodes `--cpus="16" --memory="60g"` and `/Volumes/android-kernel/*` mounts; adjust for the host.

## Dead script generations

`scripts/` accumulates three abandoned attempts alongside the working one. Only the `*_soviet_*` path is current:

| Path | Status |
|---|---|
| `build_kernel_soviet_docker.sh`, `run_builder_soviet.sh` | **Canonical.** Clang 18 + `merge_config.sh` + ccache. |
| `build_kernel_evox*.sh`, `configure_kernel_evox*.sh`, `run_builder_evox_clang18.sh` | Evolution X source attempt — bootlooped, superseded. |
| `build_kernel_16.sh`, `configure_kernel_16.sh` | Different mount layout (`/kernel/soviet_kernel_16`, `/kernel/toolchain`); does not match any wrapper here. |
| `build_kernel.sh`, `configure_kernel.sh` | Generic `/kernel/source` variant using `scripts/config` (the approach that silently loses flags). |
| `run_builder.sh` | Drops into an interactive container shell; does not build. |

`claude_plan.md` and `geminiplan.md` are historical LLM-generated research documents. They recommend a *different* kernel source (`etnperlong/kernel_xiaomi_raphael_bool-x`) and toolchain (Proton Clang) than what actually shipped. Treat them as archive, not spec.

## Docs map

- [docs/JOURNEY.md](docs/JOURNEY.md) — every failure and its root cause; read before debugging a boot problem.
- [docs/TECHNICAL.md](docs/TECHNICAL.md) — boot sequence, FBE key derivation, boot header layout, Kconfig dependency behavior.
- [docs/FAQ.md](docs/FAQ.md), [docs/BEGINNERS_GUIDE.md](docs/BEGINNERS_GUIDE.md) — user-facing.
- [BUILD.md](BUILD.md) — manual build path, partly duplicating script contents inline.
