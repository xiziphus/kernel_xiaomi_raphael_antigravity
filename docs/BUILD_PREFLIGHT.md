# Build preflight

## The model

A preflight exists to stop an **expensive resource** being spent on knowably
doomed work. So it is organised by *what it protects*, not by "checks someone
thought of". Two resources matter here, and they are not equally scarce:

* a **CI runner** — ~20 min, free, and massively parallel
* the **phone** — ~2 min, strictly serial, and a failed boot needs a human to
  press power. This is the scarce one.

| layer | protects | catches | tool |
|---|---|---|---|
| 0 tree facts | runner, first 2 min | ref, defconfig, submodules, DTB gating | `preflight.py` |
| 1 patch applicability | runner, patch step | scripts abort or silently no-op | `preflight.py --dry-run` |
| 2 config prediction | **a green build that ships the wrong kernel** | symbol undefined → "lost at config time" | `preflight.py` |
| 3 compile | runner, 17 min | implicit decls, missing headers, bad shims | smoke gate in CI |
| 4 image validation | flashing a lie | decoy config; option absent from the COMPILED image | `verify_kernel_config.py` |
| 5 device readiness | **a boot cycle and the human** | image cannot leave a log; already tested | `preflight_image.py` |

Layer 2 is the most dangerous because it fails **silently** — CI once printed
`config OK` for all 12 options and shipped `# CONFIG_PID_NS is not set`.

Layer 5 is the most valuable day to day, because it is the only one guarding a
resource that cannot be parallelised. Its key check is not "will it boot" but
**"if it fails, will it tell us why"** — an image without
`qcom,force-warm-reboot` produces a silent failure, which burns the cycle and
yields nothing. That is how most device time in this project was wasted.


Run this before launching a build. Every item is here because it actually broke
a build in this project and cost a ~20-minute runner.

```bash
python3 scripts/preflight.py <owner/repo> <ref> [defconfig]
```

Non-zero exit = BLOCKER. It runs against the GitHub API in seconds, no clone.

## The checklist

| # | Check | Symptom if missed | Fix |
|---|---|---|---|
| 1 | Defconfig exists in `arch/arm64/configs` | fails *after* Clang is fetched, ~4 min in | pass `vendor/<name>` or the tree's real name |
| 2 | `BUILD_ARM64_APPENDED_DTB_IMAGE` exists in `arch/arm64/Kconfig` | `No rule to make target 'Image.gz-dtb'` after a **successful** vmlinux link | pass `append_dtb=sm8150-v2.dtb` |
| 3 | Makefile objects whose `.c` was deleted | `No rule to make target '…/perf_trace_counters.o'` | CI strips these automatically |
| 4 | Two files instantiating one trace header | `duplicate symbol: __tracepoint_bus_update_request` | CI strips `CREATE_TRACE_POINTS` from the non-owner |
| 5 | Read Makefile **conditionals** before "fixing" a duplicate pair | `undefined symbol: __tracepoint_cluster_enter` — `lpm-levels.c`/`lpm-levels-legacy.c` are `ifeq/else`, mutually exclusive | leave mutually-exclusive pairs alone |
| 6 | `BPF_{MAP_CREATE,PROG_LOAD}_LAST_FIELD` current values | patch scripts must **no-op**, never `sys.exit` | 5.4 uses `btf_vmlinux_value_type_id` / `attach_prog_fd` |
| 7 | `enum bpf_map_type` last entry | map-type backport refuses to guess the numbering | only patch trees ending at `SOCKMAP` |
| 8 | `ramoops@` node in `sm8150.dtsi` | no node → falls back to the `ramoops_memreserve` cmdline mechanism | either is fine, never both |
| 9 | `qcom,pshold` node present | without `qcom,force-warm-reboot` a clean reboot **wipes the log** | see below |
| 10 | `CONFIG_LLVM_POLLY` | not an error — a **hang**, 20+ min at 99% CPU on one file | disable via the Kconfig symbol |

## Rules for the patch scripts themselves

Three of the six failures were my own scripts, not the trees. So:

- **Never `sys.exit` on "already done".** A tree that already has the modern
  layout is not broken. Skip and say so.
- **Fail loudly only when you would produce something wrong** — e.g. the
  map-type backport refusing a tree whose enum does not end where it expects,
  because guessing the numbering would silently mis-assign DEVMAP_HASH.
- **Be idempotent**, and test on a scratch copy of the real file before pushing.
- **Watch escaping** when one script writes another: `\n` in an outer Python
  string becomes a real newline in the emitted source.

## Why the log kept disappearing

Worth stating once, because it wasted several cycles: matching the ROM's ramoops
geometry byte-for-byte is necessary but **not sufficient**. On this device a
clean reboot does not preserve the region at all — verified by writing a marker
to `/dev/kmsg` on KameOS's own kernel, `adb reboot`, and finding
`/sys/fs/pstore` empty. Only a panic survived. The fix is
`qcom,force-warm-reboot` on the `qcom,pshold` node so the PMIC does a warm
reset instead of re-initialising DDR.

## What preflight CANNOT do

It is a static checker. It reads the tree over the API and dry-runs the patch
scripts, so it proves patches *apply*. It cannot prove the result *compiles*,
and the majority of recent failures were compile errors:

| failure | catchable statically? |
|---|---|
| `filter.h` implicit declarations after a BPF graft | no |
| missing `linux/bpf_lirc.h` | no |
| `atomic_fetch_add_unless` / `perf_event_bpf_event` | no |
| `'/*' within block comment` in a generated shim | no |

Chasing these with more static rules is a losing game. The answer is the
**smoke gate** in the workflow: right after `olddefconfig` it builds only the
subsystems our patches touch — `kernel/bpf/`, `kernel/sys.o`, `fs/pstore/`,
`net/core/` — so a broken patch fails in ~4 minutes rather than ~17, and none
of that work is thrown away because the full build needs those objects anyway.

Rule of thumb: **preflight for facts about the tree, smoke gate for whether our
patches survive a compiler.**
