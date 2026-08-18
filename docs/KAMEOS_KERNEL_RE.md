# Reverse engineering KameOS's kernel

Target: `4.14.356-Zundamon-v3.0`, the kernel shipped in KameOS v3.303 on raphael.
Everything here is from the shipped binary and the running device, not from
release notes.

## Method

* **Image**: `builds/kameos-docker-20260804-024211/boot-kameos-stock.img` →
  unpack → the kernel blob is gzip; inflate with
  `zlib.decompressobj(16+MAX_WBITS)` (plain `gzip.GzipFile` chokes on the
  appended DTB trailer).
* **Symbols**: `/proc/kallsyms` with root (60,283 names).
  **Addresses are useless** — they are pointer-hashed even at
  `kptr_restrict=0`, and `/proc/kcore` does not exist. Names only.
* **Disassembly**: capstone, offline, against the inflated image. Because the
  Image is flat, `target_VA - insn_VA == target_off - insn_off`, so ADRP/ADD
  pairs resolve **without knowing the load base** — which is what makes
  string-cross-referencing possible despite the hashed addresses.

## 1. The uname spoof — the mechanism that makes this ROM work

Cross-referencing the string `netbpfload` found exactly one code site, at file
offset `0x605b0`:

```asm
add  x1, x1, #0xa63    ; "bpfloader"
add  x0, x21, #0x6d0   ; current->comm   (x21 = sp_el0 = current)
mov  w2, #9
bl   strncmp
cbz  w0, spoof
add  x1, x1, #0xb47    ; "netbpfload"   (len 10)
cbz  w0, spoof
add  x1, x1, #0x4aa    ; "netd"         (len 4)
cbnz w0, skip
spoof:
mov  x8, #0x2e35            ; "5."
movk x8, #0x2e34, lsl #16   ; "4."
movk x8, #0x3831, lsl #32   ; "18"
movk x8, #0x36,   lsl #48   ; "6"
stur x8, [sp, #0x8c]        ; utsname.release = "5.4.186"
```

Equivalent C:

```c
if (!strncmp(current->comm, "bpfloader",  9) ||
    !strncmp(current->comm, "netbpfload", 10) ||
    !strncmp(current->comm, "netd",       4))
        strcpy(tmp.release, "5.4.186");
```

`uname -r` still reports `4.14.356-Zundamon-v3.0` to everyone else. This is what
gets past netbpfload's *"Android 25Q2 requires kernel 5.4"* check.

There is an **extra guard** we do not replicate: immediately before the copy,

```asm
ldr  x8, [x21, #0x6c8]
ldr  w8, [x8, #8]
cbnz w8, skip_spoof
```

a task_struct field is dereferenced and the spoof skipped if non-zero —
consistent with the upstream *"only fake uname on the very first call"* commit.

## 2. Other behavioural patches

Scanning for process/package-name strings **referenced by code** (ADRP/ADD, not
merely present in rodata) found only two clusters:

| strings | offset | what it is |
|---|---|---|
| `bpfloader`, `netbpfload`, `netd` | `0x605b0` | the uname spoof above |
| `zygote`, `system_server`, `packages.list` | `0x121xxxx` | KernelSU's hooks |

No SafetyNet/GMS spoof, no other comm-based behaviour. The uname lie is the only
Android-compat hack in this kernel.

## 3. Feature inventory

Read from symbol names. **Caveat:** absence of a single symbol proves nothing —
LTO inlines aggressively, and e.g. `alloc_pid` / `setup_net` exist regardless of
`CONFIG_PID_NS` / `CONFIG_NET_NS`. Only multi-symbol probes are trusted below.

### BPF — a near-complete 5.4 backport

| present | absent |
|---|---|
| `btf_new_fd`, full `btf.c` | `bpf_ringbuf_reserve` (5.8) |
| `dev_map_hash_update_elem` (the real DEVMAP_HASH, not an alias) | `sock_map_*` / sockhash |
| `bpf_sk_storage_get`, `bpf_cgroup_storage_assign` | |
| `cpu_map_alloc`, `xsk_map_alloc`, `reuseport_array_alloc` | |
| `bpf_map_charge_init`, `bpf_map_init_from_attr` | |

Cgroup hooks — **all seven** netbpfload can ask for on a 5.4 claim:

```
__cgroup_bpf_run_filter_skb          skb ingress/egress
__cgroup_bpf_run_filter_sk           sock_create
__cgroup_bpf_run_filter_sock_addr    bind / connect / sendmsg / recvmsg
__cgroup_bpf_run_filter_sock_ops     sock_ops
__cgroup_bpf_run_filter_getsockopt   getsockopt      <- 5.3
__cgroup_bpf_run_filter_setsockopt   setsockopt      <- 5.3
__cgroup_bpf_run_filter_sysctl       sysctl
```

### Tracing — entirely absent

`ftrace_startup`, `register_kprobe`, `trace_call_bpf`, `uprobe_register` all
missing. So every `/system/etc/bpf/miui/*` program (all tracepoint/kprobe, some
ringbuf) **cannot load on the ROM's own kernel** — and the device boots anyway.
That is the proof that non-critical BPF objects are tolerated.

### Docker-relevant — what Zundamon left OFF

| need | state |
|---|---|
| overlayfs | **PRESENT** (`ovl_lookup`, `ovl_copy_up`, `ovl_permission`) |
| cgroup freezer, memcg, cpuset, blkio, cgroup v2 | PRESENT |
| ext4 / f2fs / fuse / erofs | PRESENT |
| bridge, netfilter, nf_nat, iptables, conntrack | PRESENT |
| **USER_NS / UTS_NS / IPC_NS** | **ABSENT** (multi-symbol) |
| **veth** | **ABSENT** (`veth_newlink`, `veth_setup`, `veth_xmit`, `veth_link_ops`) |
| **cgroup pids / devices** | **ABSENT** (multi-symbol) |
| vxlan, ipvs | ABSENT |

This matches the functional test done on-device earlier in the project, by an
independent method. **KameOS's own kernel cannot run Docker**, and the missing
pieces are exactly what `docker.config` adds.

### Other

* KernelSU built in (107 `ksu_*` symbols); no SUSFS.
* `cass_` and EEVDF scheduler symbols — both named in the Helium changelog,
  which is what ties this binary to the Rikka/Zundamon lineage.
* Built with Clang 22.0.0 (r584948) by `Zundamon@WSL2`, 2026-03-23.

## 4. Reconstruction

```
Zundamon v3.0 = Xiaomi MIUI msm-4.14 raphael base   (boots HyperOS)
              + RikkaKernel                         (EEVDF, CASS, upstream backports)
              + stable bump 4.14.341 -> .356
              + BPF top-up: sendmsg/recvmsg attach types, cgroup sockopt,
                            sk_storage, real dev_map_hash, map_charge
              + uname spoof -> "5.4.186" for bpfloader/netbpfload/netd
              + KernelSU (SukiSU-Ultra)
              - namespaces, veth, cgroup pids/devices  (never enabled)
```

The BPF top-up is smaller than it looks: `rikka-v5` **already** has
`__cgroup_bpf_run_filter_sock_addr` and the bind/connect attach types, so the
delta is sendmsg/recvmsg (which reuse the existing sock_addr hook) plus cgroup
sockopt (5.3). Two features, not a subsystem.

## 5. What this means for building a Docker kernel

1. Start from **Rikka** (`tingyuwuxin/kernel_xiaomi_raphael@rikka-v5`) — proven
   to boot KameOS, and already 4/8 on the hooks.
2. Add the uname spoof (`scripts/fake_uname_bpfloader.py`), claiming `5.4.186`.
3. Add **sendmsg/recvmsg + cgroup sockopt** — the only BPF gap. All the
   version-gated programs netbpfload will then demand are `optional = 0`, i.e.
   fatal if they fail, so this is not skippable.
4. Add `docker.config` for the namespaces/veth/cgroup-controllers Zundamon left
   off. Note overlayfs is already on in this lineage.
