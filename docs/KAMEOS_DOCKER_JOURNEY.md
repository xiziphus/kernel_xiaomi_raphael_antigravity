# Docker on KameOS (raphael) — a field log

Target: run Docker on **KameOS v3.303 CN** (`OS3.0.303.0.WPKCNXM`) on the Redmi
K20 Pro. KameOS is HyperOS 3 / **Android 16** grafted onto a **MIUI 12.5.6 /
Android 11 vendor** (`ro.vendor.build.fingerprint =
Xiaomi/raphael/raphael:11/RKQ1.200826.002/V12.5.6.0.RFKCNXM`), kernel
`4.14.356-Zundamon-v3.0`, built with **Clang 22.0.0 (r584948)**.

Status: **not achieved.** A Docker-capable kernel now boots this ROM and reaches
init — no kernel had ever got that far — and dies on one userspace service. This
document records what was proven, what was disproven, and how to pick it up.

Companion notes: [JOURNEY.md](JOURNEY.md) (the Evolution X era),
[NATIVE_DOCKER.md](NATIVE_DOCKER.md) (Docker userspace on bionic).

---

## 1. The ROM has no Docker support, and that is not a config question

Verified functionally **as root** on the running kernel — the only trustworthy
method here, because this tree falsifies its own config (§2):

```
namespaces : pid ✗  ipc ✗  uts ✗  user ✗        (net / mnt / cgroup ✓)
cgroups    : cpuset cpu cpuacct blkio memory freezer   — pids ✗  devices ✗
veth       : RTNETLINK answers: Operation not supported
overlay,fuse : ✓
```

Docker needs PID namespaces, the `pids`/`devices` controllers and `veth`. All
are compiled out. Hence the custom-kernel work.

## 2. `/proc/config.gz` on these trees is a deliberate lie

Several raphael trees (SOVIET-ANDROID@16.0, HeliumStudio, VoltageOS, rikka,
hxsyzl@16.0-raphael) carry Sultan Alsawaf's *"use the stock raphael config for
/proc/config.gz"* patch. `kernel/Makefile` builds `config_data.gz` from a
**checked-in defconfig** rather than `$(KCONFIG_CONFIG)`:

```make
$(obj)/config_data.gz: arch/arm64/configs/raphael-vts_defconfig FORCE
```

The image therefore advertises a kernel that was never compiled — CTS/VTS
compliance spoofing, the config-side sibling of PIF fingerprint spoofing.

**The tell is the version.** KameOS: banner 4.14.356, embedded config 4.14.180.
A SOVIET 4.14.357 build embeds `raphael-vts_defconfig` (4.14.226) byte-for-byte,
all 5995 lines.

This cost two retracted conclusions — a phantom "CI ships kernels with PID_NS
unset" bug, and a "MIUI vs AOSP DT-overlay lineage" theory. Both were read off
the decoy. `scripts/verify_kernel_config.py` now **refuses** any image whose
config version ≠ banner version, and the CI rewrites that Makefile rule so our
own builds embed the truth.

Trust, in order: the build's `out/.config` / `autoconf.h`; **kallsyms** from the
image; a **functional** check on-device.

## 3. Lineage is real: 13 kernels, 5 trees, none booted

`fastboot boot` only — nothing written. Every image carried
`androidboot.ktest=<name>`, readable as `ro.boot.ktest`; without it a failed
boot is indistinguishable from success, because both end up reporting the
flashed kernel's version.

| kernel | Docker-capable | boots KameOS |
|---|---|---|
| **CONTROL — KameOS's own kernel, our repack** | n/a | ✅ every time |
| SOVIET 4.14.357 (+KameOS DTB, +kallsyms variants) | ✓ | ❌ ❌ ❌ |
| purpose-built `boot-kameos-docker.img` (openela-rc1) | ✓ | ❌ |
| romtree · evox-final (openela-perf) | ✓ | ❌ ❌ |
| DT_OVERLAY-off variant | ✓ | ❌ |
| **Helium `oss-base` 4.14.356** (Zundamon's own maintainer) | ✓ | ❌ |
| Helium + KameOS's byte-exact DTB | ✓ | ❌ |

Eliminated along the way, so **do not re-test**: packaging (the control boots;
cmdline 401 B < 512), missing Docker options (verified in the *compiled*
images), wrong tree (same maintainer, same sublevel), missing driver — the
kallsyms diff after stripping `.llvm.*` LTO suffixes shows **58,200 of ~60,000
functions shared (97%)** — DTB identity (both are the same generic SM8150 v2
base, `msm-id 0x153/0x20000`, `board-id 0/0`), dtbo pairing, and `earlycon`.

The community states it plainly: *"Soviet Kernel: has no MIUI or HyperOS
support."* Kernels like BoolX and Envy ship **separate MIUI and AOSP builds**.
KameOS is an Android 16 system on an **Android 11 MIUI vendor**, so it needs a
MIUI-lineage kernel.

## 4. Breakthrough: a MIUI-lineage kernel boots

**`onettboots/bool-x_xiaomi_raphael` branch `16-HyperMiui`** (4.14.356) is the
first custom kernel to reach init on this ROM. Use the plain branch, not
`-erofs` — KameOS's system/vendor are ext4 and only APEX is erofs.

It then reboots with **`reboot,bpfloader-failed`**. That is a *userspace*
failure: kernel up, init running. Every previous failure was pre-init.

Also useful: it reboots **cleanly in ~27 s**, so iterating no longer needs a
physical power press (a failed `fastboot boot` on raphael otherwise powers the
device *off*).

## 5. Reading the ROM's own BPF objects — how to replace guesses with facts

This technique produces evidence, not a booting kernel. It has ruled several
theories out and found one real defect; Docker still does not run on KameOS.

The real loader is `/apex/com.android.tethering/bin/netbpfload`; its rc file
documents this exact bootloop and says the cause is usually *"the kernel's bpf
verifier … unsupported / unknown operation / helper"*. Rather than guess, pull
the objects and parse them:

```sh
adb pull /apex/com.android.tethering/etc/bpf   # net_shared, netd_shared, tethering
adb pull /system/etc/bpf                       # incl. MIUI-specific programs
```

Each `.o` carries a `progs` section of `bpf_prog_def` and a `maps` section of
`bpf_map_def`, both with **`min_kver` / `max_kver`**. Android ships
kernel-version-gated variants on purpose, so *what a 4.14 kernel must load* is a
computable subset, not a guess.

Checked for this kernel, all clean:

- **program types** — every required one exists
- **helpers** — all 12 called by required programs (ids 1,2,15,23,26,31,39,40,43,46,47,50)
- **instruction set** — no `JMP32` (5.1+)
- **map flags** — only `NO_PREALLOC`; key/value/max_entries within 4.14 limits
- **the 4.17–5.10 cgroup hooks** (`bind4/6`, `connect4/6`, `sendmsg`, `recvmsg`,
  `get/setsockopt`, `sock_release`) are correctly **min_kver-gated and skipped**
- `RINGBUF` gated to 5.10; `XSKMAP` only in an **optional** object; everything
  under `/system/etc/bpf/` (incl. the MIUI kprobe programs) is **optional**

## 6. The one real defect found this way: `BPF_MAP_TYPE_DEVMAP_HASH`

```
/apex/com.android.tethering/etc/bpf/tethering/offload.o   [critical]
    tether_dev_map   type=25 (DEVMAP_HASH)  key=4 value=4 max_entries=64
                     min_kver=0   max_kver=inf
```

`min_kver=0` means Android does **not** version-gate this map — it must be
created on 4.14 too — and `offload.o` is marked `critical`. `DEVMAP_HASH` is a
5.4 type (`6f9d451ab1a3`); bool-x's enum stops at `15:SOCKMAP`, so creation
returns `EINVAL` and bpfloader exits non-zero.

Fixed by `scripts/backport_bpf_map_types.py`: extends the enum so `DEVMAP_HASH`
lands on exactly 25 and registers it against the tree's existing `dev_map_ops`
(`dev_map_alloc` validation accepts 4/4/64 exactly). Idempotent; a no-op on the
openela lineage, which already has types to 25.

**Necessary but not sufficient** — the kernel still exits with
`bpfloader-failed`, so at least one more blocker remains, most plausibly the
4.14 verifier rejecting a program the 5.x verifier accepts.

## 7. Theories that were wrong (recorded so they are not retried)

- **`BPF_EVENTS` / tracing is required.** No. KameOS's own working kernel
  contains **no tracepoint name strings at all** (`sched_switch`,
  `cpu_frequency`, `cgroup_attach_task` all absent) — FTRACE/TRACING are off
  there and bpfloader still passes. It tolerates tracepoint programs it cannot
  load. Cost: three build failures. Tracing is now behind CI input
  `enable_tracing` (default false).
- **Missing 4.17–5.10 cgroup attach types.** No — they are min_kver-gated (§5).
- **Our Docker options break bpfloader.** No. A `stock_only=true` control build
  (no `docker.config`, no tracing, `PID_NS` off) fails **identically**.
- **DT overlay / dtbo / cmdline / AVB.** All eliminated in §3.

## 8. Diagnostics on a stock, locked-down user build

What works without root:

- `getprop persist.sys.boot.reason.history` — the key signal.
  `bootloader,*` = the kernel never ran; `reboot,bpfloader-failed` = it booted
  and init ran.
- `adb shell dumpsys dropbox --print SYSTEM_LAST_KMSG` — reads pstore
  indirectly; `/sys/fs/pstore` itself is SELinux-blocked for shell.
- `cmd window dismiss-keyguard` raises the PIN pad;
  `locksettings verify --old <pin>` validates a PIN from shell.
- Wake with `svc power stayon usb; input keyevent 224` — MIUI blocks
  `settings put system screen_off_timeout`.

What does **not** work:

- `adb root` — `ro.debuggable=0`, `ro.build.type=user` (the cmdline's
  `buildvariant=userdebug` is cosmetic).
- **All shell input injection**, locked or unlocked: `input tap/keyevent` →
  `SecurityException: requires INJECT_EVENTS`; raw `sendevent` to
  `/dev/input/event3` (goodix_ts, protocol B) → SELinux denied despite shell
  being in group `input`. The UI cannot be driven from adb on MIUI.
- `/dev/mem` — absent (`CONFIG_DEVMEM` off).

## 9. Root: how, and its limits here

KameOS ships a Magisk **stub** (33 KB, obfuscated launcher
`x.COMPONENT_PLACEHOLDER_2`) that cannot self-upgrade — upstream
`HuskyDG/magisk-files` is 404 — and its policy **rejects** shell outright
(`Magisk: su: request rejected (2000)`). `magisk --sqlite` needs root to fix
that: chicken-and-egg. Official **KernelSU v3.2.5 and v1.0.5** both report
*"only supports GKI kernels"* (4.14 is pre-GKI); **KernelSU-Next v3.3.0**
installs but its activity times out.

What worked: install **official Magisk 30.7**, patch a *known-good* boot image
via **Install → Select and Patch a File**, and flash that. Then grant Shell in
Superuser.

> **Do not use Direct Install.** It patches whatever is currently in the boot
> slot. During kernel testing that slot may hold anything, and patching a test
> kernel is what produced a fastboot-stuck device (§10).

Two gotchas once rooted:

- **`su -M` (mount-master) is mandatory** or you are inside Magisk's isolated
  namespace seeing a phantom filesystem (`df` reports `/data` mounted on
  `/system/etc/hosts`, and `/data/adb/service.d` appears to exist when it does
  not).
- On this ROM root **cannot write to `/data` at all** — not `/data/adb`, not
  `/data/bb.txt` — while `/data/local/tmp` works, with no AVC denials logged.
  Magisk's policy patching is only partially applied. This kills the
  `post-fs-data.d` hook trick for capturing a boot log.

## 10. Recovering a fastboot-stuck raphael

Two independent partitions were broken; fixing one is not enough.

1. **boot** — restore a verified stock image:
   `fastboot flash boot builds/kameos-docker-20260804-024211/boot-kameos-stock.img`
2. **recovery** — a broken recovery causes the *loop*. Requesting recovery
   writes `boot-recovery` to the BCB in `misc`; if recovery fails the bootloader
   bounces back with the BCB still set. `fastboot erase misc` breaks the loop but
   does **not** fix recovery. Flash a working one — TWRP 3.7.1 for raphael.

**Verify the device codename before flashing any recovery.** An
`OrangeFox-…-Pong-…` image in the same Downloads folder is for the *Nothing
Phone 2*; its `recovery.img` contains `pong`/`nothing` strings and no `sm8150`.
The correct raphael image verifies the other way: `sm8150` ×27, `raphael` ×3,
`k20` ×4.

## 11. ramoops: the ROM's region is `0xB0000000`

KameOS registers pstore from a **built-in platform device**, not from DT — its
DTB has no ramoops node at all. Read the real geometry as root:

```
/sys/module/ramoops/parameters/
  mem_address = 0xB0000000   mem_size = 0x400000
  console_size = 0x200000    pmsg_size = 0x200000   record_size = 0
```

bool-x reserves `0xa1600000` instead, which is why adding `console-size` alone
changed nothing: our kernel wrote its console where KameOS's reader never looks.
The CI now relocates ramoops to `0xB0000000` with matching geometry (ecc 0).

**It still captured nothing** — pstore stayed empty after both a RAM boot and a
real reboot from the recovery slot. Our kernel's ramoops appears not to
initialise, likely a reservation conflict, and confirming that needs its dmesg —
which is the thing we cannot read. This is the current dead end.

## 12. Where to pick it up

The kernel boots and reaches init; one service stands between that and a Docker
host. The blocker is netbpfload's own error text, and every capture route from
outside is closed (§8, §9, §11).

Realistic next steps, in order of expected value:

1. **A UART/serial console.** raphael exposes one on the USB-C SBU pins with a
   Qualcomm-compatible cable. That bypasses pstore, SELinux and the reboot
   entirely, and would end this in minutes.
2. **Make the failing kernel's ramoops work** — establish why the reservation at
   `0xB0000000` fails; then `dumpsys dropbox --print SYSTEM_LAST_KMSG` and
   `logcat -L` both become available after a failure.
3. **Transplant openela's BPF into bool-x.** Both trees are 4.14.356. openela
   adds `btf.c cpumap.c disasm.c local_storage.c offload.c queue_stack_maps.c
   reuseport_array.c sysfs_btf.c xskmap.c` plus `include/linux/btf.h`,
   `include/uapi/linux/btf.h`, `net/core/sock_map.c` (replacing bool-x's
   `kernel/bpf/sockmap.c`); `uapi/linux/bpf.h` 991→3553 lines, `verifier.c`
   5273→9733, `net/core/filter.c` 4452→9117. Large but mechanical, and the CI
   can clone a donor tree and copy files rather than carrying a giant patch.
4. **Accept the split.** InfinityX runs the full Docker stack today; the images
   in `builds/` are verified.

## 13. CI hardening earned along the way

All in [.github/workflows/build-raphael.yml](../.github/workflows/build-raphael.yml):

- `libyaml-dev`, and aliasing **`HOSTLOADLIBES_dtc`** (4.14's `Makefile.host`
  name) to `HOSTLDLIBS_dtc` (what backported dtc sets) — otherwise dtc dies with
  `undefined reference to yaml_emitter_emit`
- inject raphael's CPU topology (`LITTLE=15 BIG=112 PRIME=128`) — `int` symbols
  with no default, else `(NEW) aborted!`
- layer a foreign ROM config **over** the tree defconfig, never as the base
- config + build in **one step** with an identical make-variable set, then gate
  on `verify_kernel_config.py` against the **compiled image**
- strip the `/proc/config.gz` decoy; `KALLSYMS_ALL` so images are symbol-diffable
- drop Makefile references to sources a tree deleted (bool-x removed
  `perf_trace_counters.c`/`perf_trace_user.c` but kept the `ifeq(CONFIG_TRACING)`
  rule)
- de-duplicate tracepoint instantiation (`msm_bus_core.c` + `msm_bus_rules.c`
  both instantiate `trace_msm_bus.h`) — **and read the Makefile's conditionals**:
  `lpm-levels.c`/`lpm-levels-legacy.c` look like the same bug but are an
  `ifeq/else`, so "fixing" them yields `undefined symbol: __tracepoint_cluster_enter`
- inputs `stock_only` (control build) and `enable_tracing` (default off)

## 14. Reading the working kernel as a spec, and the pstore unlock (2026-08-18)

With root on the *running* ROM, KameOS's own kernel becomes the reference
implementation. Everything below came from the device, not from reasoning.

### 14.1 What `4.14.356-Zundamon-v3.0` actually contains

`adb shell su -c 'cat /proc/kallsyms'` — it carries a large ~5.4-era BPF
backport on a 4.14 base: full `btf.c` (70 `btf_*` symbols, `btf_new_fd`,
`btf_get_by_fd`), the genuine `dev_map_hash_update_elem`, `bpf_map_charge_init`
/ `bpf_map_init_from_attr`, `bpf_sk_storage_get`, and the `sock_addr` +
`get/setsockopt` cgroup hooks. It does **not** have ringbuf, sockmap/sockhash,
map batch ops, iterators, LSM, or `bpf_raw_tracepoint_open`.

Note the shape of that list: our `scripts/backport_bpf_map_types.py` aliases
DEVMAP_HASH onto the index-based `dev_map_ops`, whereas the ROM's kernel has the
real hash implementation *and* the charge/init infrastructure that patch's
docstring says 4.14 lacks.

### 14.2 BTF is not the blocker

`/sys/kernel/btf/` does not exist on KameOS — that sysfs node is 5.5+ — yet the
ROM boots. So netbpfload does not require it. (The BTF *code* is present and
`BPF_BTF_LOAD` does work there; the loader also has an explicit retry and a
`failed program %s is marked optional - continuing...` path.)

### 14.3 The `min_kver` decode, verified

Earlier analysis was doubted. It is correct, and the proof is a boundary pair
inside `offload.o`: `..._rawip$stub` has max_kver `0x040E0000` while
`..._rawip$4_14` has min_kver `0x040E0000`. That pins the layout unambiguously —
in a 92-byte `bpf_prog_def`, u32[2] is min_kver and u32[3] is max_kver.

Decoding `netd.o` with it:

| program | min_kver | on 4.14 |
|---|---|---|
| `bpf_cgroup_{ingress,egress}_4_9` | 0 (max 4.19) | **required** |
| `inet_socket_create` | 4.14 | **required** |
| `xt_bpf_*`, `tc_bpf_ingress_account` | 0 | **required** |
| `inet{4,6}_{bind,connect}`, `udp{4,6}_{send,recv}msg` | 4.19 | skipped |
| `getsockopt`/`setsockopt` | 5.4 | skipped |

So the "missing 4.17–5.10 cgroup hooks" theory is dead for good. Zundamon
backported those hooks, but nothing on this ROM asks a 4.14 kernel for them.

### 14.4 The MIUI BPF set exists — and is not the cause

HyperOS ships a second loader, `/system_ext/bin/hyper_bpfloader`
(`/system_ext/etc/init/hyper_bpfloader.rc`), plus `/system/etc/bpf/miui/*`,
`memevents`, `gpuWork`, `MiuiMmTrace`. These are HyperOS-only and invisible to
any AOSP-based analysis, so they looked like a promising suspect.

They are not. Every one of them needs tracepoints, kprobes, or ringbuf
(`BPF_MAP_TYPE_RINGBUF`, type 27) — and KameOS's own kernel has **no**
`trace_call_bpf`, no `register_kprobe`, and no `bpf_ringbuf_reserve`. They
cannot be loading on the working kernel either, and the device boots fine.
That also settles a general point: **non-critical load failures are tolerated.**

Two distinct reboot reasons, worth not confusing:
`hyper_bpfloader` → `reboot,hyper-bpfloader-failed`; the apex
`/apex/com.android.tethering/etc/netbpfload.rc` → `reboot,bpfloader-failed`,
which is ours. Critical objects are exactly four: `netd.o`, `offload.o`,
`clatd.o`, `dscpPolicy.o`.

### 14.5 Helpers all check out

Disassembling every 4.14-eligible program in those four objects for `BPF_CALL`
(opcode `0x85`, src_reg 0) yields 16 distinct helper ids. All 16 are present in
bool-x — whose `__BPF_FUNC_MAPPER` list is in fact byte-identical to the modern
one (126 entries, same tail). Helpers, program types, attach types and map types
are now all accounted for.

### 14.6 Why every failed boot was silent — and the fix

The ROM's cmdline contains **`ramoops_memreserve=4M`**. KameOS does not take
pstore from the device tree at all: a Xiaomi patch in `fs/pstore/ram.c` parses
that early param, hardcodes `0xB0000000`, splits the size half to console and
half to pmsg, and registers a bare platform device. Hence no
`/proc/device-tree` node, and hence every region we declared in DTS was in the
wrong place.

Worse, the trigger is **not in the boot header** — the stock boot image's
cmdline has no such param. The ROM's kernel supplies it from its own built-in
`CONFIG_CMDLINE`. So our images never even armed the mechanism.

Both halves are now fixed: `scripts/xiaomi_ramoops.py` installs the vendor
mechanism (and deletes any DT ramoops node, which would otherwise reserve a
second region and win the platform-device race), and
`scripts/repack_kameos.sh` puts `ramoops_memreserve=4M` on the cmdline.

Geometry has to match byte for byte — pstore lays the region out as
records → console → ftrace → pmsg, so a single differing size shifts every
later buffer. Verified against the live device
(`/sys/module/ramoops/parameters/*`): `mem_address=0xB0000000`,
`mem_size=0x400000`, `console_size=0x200000`, `pmsg_size=0x200000`,
`record_size=0`, `ftrace_size=0`, `ecc=0`, `dump_oops=1`.

After a failed test boot, back in KameOS:

```sh
adb shell su -c 'logcat -L -b all' | grep -iE 'bpf|netbpf'      # pmsg  (bpfloader's own error)
adb shell su -c 'dumpsys dropbox --print SYSTEM_LAST_KMSG'      # console (kernel)
```

### 14.7 Better base trees than bool-x

Found by search; all carry DEVMAP_HASH, the full cgroup attach types and
`btf.c`, so they need no hand-porting:

| tree / branch | ver | note |
|---|---|---|
| `qaz6750/android_kernel_xiaomi_sm8150@a16-hyper-xiaomi-4.14.y` | 4.14.356 | HyperOS lineage, KameOS's exact sublevel, full BPF — but **no** raphael dts/defconfig (its `a14-xiaomi-4.14.y` branch has those and no BPF). Likely the base Zundamon combined. |
| `hxsyzl/kernel_xiaomi_raphael@{16.0-raphael,dynamic}` | 4.14.357 | has `raphael_defconfig`, biggest `btf.c`, and **implements `ramoops_memreserve`** — the source of the pstore patch above |
| `waffleowo/kernel_xiaomi_raphael_bpf@bpf-5.4-backport` | 4.14.353 | explicit BPF-5.4-backport onto raphael, incl. "fake uname to 5.4.186" |
| `HeliumStudio-Dev/kernel_xiaomi_raphael_5.4@zundamon-miui-5.4` | 5.4.302 | MIUI lineage on 5.4, where every netbpfload requirement is native |

## 15. THE ROOT CAUSE: netbpfload refuses any kernel below 5.4 (2026-08-18)

Everything in sections 5-14 was chasing symptoms. The cause is a version gate,
and it was never reached by any BPF feature we investigated.

### 15.1 The log that ended it

With the warm-reset pstore fix (14.6 + below), the first readable log from a
failed boot said:

```
[   14.565835] NetBpfLoad: Android V requires kernel 4.19.
[   14.571829] init: Service bpfloader has 'reboot_on_failure' option and failed
```

`strings` on `/apex/com.android.tethering/bin/netbpfload` gives the full ladder:

```
Android S & T require kernel 4.9.
Android U    requires kernel 4.14.
Android V    requires kernel 4.19.
Android 25Q2 requires kernel 5.4.     <- netbpfload.rc says this ROM is 25q2
```

### 15.2 Confirmed by prediction, not by fitting

Claiming 4.19 (`fake_uname=4.19.0`) moved the failure to the **next rung**,
exactly as the ladder predicts:

```
[   14.643684] NetBpfLoad: Android 25Q2 requires kernel 5.4.
```

Claiming 5.4.186 cleared both gates and reached real BPF work:

```
NetBpfLoad: bpf map name tether_dev_map mismatch:
            desired/found: type:25/25 key:4/4 value:4/4 entries:64/64 flags:128/0
NetBpfLoad: Failed to create maps: (ret=-76) in .../offload.o
```

Note `type:25/25` -- **the DEVMAP_HASH backport works**. The only mismatch is
`flags:128` = `BPF_F_RDONLY_PROG` (5.2), which 4.14's `dev_map_alloc` drops.

### 15.3 How KameOS's own 4.14 kernel passes -- disassembled

`uname -r` on the ROM reports `4.14.356-Zundamon-v3.0`, so the gate should
reject it too. It does not, because the kernel lies to exactly three callers.
Decompressed the shipped Image, found ADRP/ADD pairs referencing the string
`netbpfload`, and disassembled (capstone; kallsyms addresses are pointer-hashed
and there is no /proc/kcore, so this was done offline against the image):

```asm
add  x1, x1, #0xa63    ; "bpfloader"
add  x0, x21, #0x6d0   ; current->comm
mov  w2, #9            ; strncmp(comm, "bpfloader", 9)
cbz  w0, spoof
...                    ; likewise "netbpfload" (10) and "netd" (4)
mov  x8, #0x2e35       ; "5."
movk x8, #0x2e34, lsl #16   ; "4."
movk x8, #0x3831, lsl #32   ; "18"
movk x8, #0x36,   lsl #48   ; "6"
stur x8, [sp, #0x8c]   ; utsname.release = "5.4.186"
```

So Zundamon spoofs `uname()` to **5.4.186** for `bpfloader`, `netbpfload` and
`netd` only. `scripts/fake_uname_bpfloader.py` reproduces this. There is one
extra guard in the ROM's version (a task_struct field checked before spoofing,
consistent with the upstream "only fake uname on the very first call" commit)
which we do not replicate.

### 15.4 What claiming a version costs you

The claim is a promise. netbpfload skips programs whose `min_kver` exceeds the
running kernel, so a higher claim makes it demand more:

| claim | additionally attempted | needs |
|---|---|---|
| 4.19 | bind4/6, connect4/6, udp sendmsg/recvmsg | `CGROUP_SOCK_ADDR` |
| 5.4 | + get/setsockopt | `CGROUP_SOCKOPT` |

Hence the hook audit. **No single tree has both halves:**

| tree | cgroup hooks | boots KameOS |
|---|---|---|
| bool-x 16-HyperMiui | 0/8 | **yes** |
| Rikka rikka-v5 | 4/8 | **yes** |
| qaz a16-hyper | 8/8 | not a device tree (donor only) |
| hxsyzl dynamic | 8/8 | no -- powers off pre-init |
| waffleowo | 8/8 | no -- init panic, exit 127 |

### 15.5 Lineage, confirmed from the running binary

The Helium changelog states *"Renamed kernel name from Rikka to Zundamon"*, and
KameOS's own kallsyms carry `cass_` (3) and EEVDF symbols (4) -- both listed in
that changelog -- plus 107 `ksu_` symbols. So **KameOS = Zundamon = Rikka
lineage**, and Rikka is the correct base. Rikka also reaches
`reboot,bpfloader-failed`, making it the second tree ever to boot this ROM.

KameOS's kernel also lacks `skb_metadata_len`, `cant_sleep` and
`set_vm_flush_reset_perms` -- so Zundamon hit the same 4.14-core gap our BPF
graft hits, and solved it the same way.

### 15.6 Reconstruction

    KameOS kernel  ~=  Rikka  +  5.x BPF graft  +  uname spoof to 5.4.186

## 16. Why failed boots were invisible, and the fix

Matching the ROM's ramoops geometry byte-for-byte is necessary but **not
sufficient**: on this device a clean reboot does not preserve the region at all.
Proven by writing a marker to `/dev/kmsg` on KameOS's own kernel, running
`adb reboot`, and finding `/sys/fs/pstore` empty. Only a panic survived -- which
is why waffleowo (kernel panic) left 40 KB and bool-x (init reboots cleanly on
bpfloader failure) left nothing.

A hard PMIC reset re-initialises DDR. `msm-poweroff.c` already supports the fix
and it needs no C change: `msm_restart_prepare()` selects
`PON_POWER_OFF_WARM_RESET` when `force_warm_reboot` is set, read from a DT
property. So one line on the `qcom,pshold` node:

```dts
qcom,force-warm-reboot;
```

`scripts/xiaomi_ramoops.py` applies that, sets the ramoops node to the ROM's
exact geometry (0xB0000000, 4M, console 2M, pmsg 2M, record 0, ecc 0), and
creates the node if the tree has none. Then, after a failed boot:

```sh
adb shell su -c 'cat /sys/fs/pstore/console-ramoops-0'   # kernel
adb shell su -c 'cat /sys/fs/pstore/pmsg-ramoops-0'      # userspace/logd
```

## 17. Build discipline

Roughly half the build failures in this effort were the harness, not the trees.
See [BUILD_PREFLIGHT.md](BUILD_PREFLIGHT.md). `scripts/preflight.py` checks a
tree over the GitHub API in seconds and `--dry-run` executes every patch script
against it; `scripts/launch_build.sh` refuses to dispatch on a BLOCKER, and a
PreToolUse hook blocks `gh workflow run` that bypasses it.

Rules that came out of the failures:
- never `sys.exit` on "already done" -- a tree that already has the modern
  layout is not broken
- fail loudly only when you would emit something *wrong* (e.g. refusing to
  guess an enum's numbering)
- never put logic in a CI heredoc; it cannot be tested, and the one we had
  silently deleted `source "arch/$SRCARCH/Kconfig"`
- a checklist that can be skipped will be skipped
