# Build preflight

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
