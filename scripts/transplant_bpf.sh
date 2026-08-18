#!/usr/bin/env bash
# Graft a donor tree's BPF subsystem onto the current kernel tree.
#
# Usage: transplant_bpf.sh <donor-git-url> <donor-ref>
#
# Rationale: KameOS's own 4.14.356-Zundamon kernel is, by symbol comparison, a
# MIUI/bool-x-lineage kernel with the complete openela BPF stack grafted onto it
# (btf, sk_storage, cgroup storage, queue/stack, reuseport, xsk, cpumap, offload).
# bool-x is the only tree that boots this ROM and it has the OLDEST BPF; the
# trees with complete BPF do not boot. So the direction is to bring BPF to
# bool-x, never bool-x's platform support to them.
#
# Both sides must be 4.14.356 for this to have any chance. It is expected to
# need several compile iterations -- that is the point of running it on free
# parallel runners rather than reasoning about it.
set -euo pipefail
URL="${1:?donor git url}"; REF="${2:?donor ref}"
D="$(mktemp -d)/donor"
git clone --depth 1 -b "$REF" "$URL" "$D" >/dev/null 2>&1
echo "  donor $URL@$REF -> $(sed -n '2,4p' "$D/Makefile" | tr '\n' ' ')"
echo "  local           -> $(sed -n '2,4p' Makefile | tr '\n' ' ')"

# Whole-file replacements: the BPF core plus the headers that define its ABI.
FILES="
kernel/bpf/btf.c kernel/bpf/cpumap.c kernel/bpf/disasm.c kernel/bpf/disasm.h
kernel/bpf/local_storage.c kernel/bpf/offload.c kernel/bpf/queue_stack_maps.c
kernel/bpf/reuseport_array.c kernel/bpf/sysfs_btf.c kernel/bpf/xskmap.c
kernel/bpf/core.c kernel/bpf/syscall.c kernel/bpf/verifier.c kernel/bpf/cgroup.c
kernel/bpf/hashtab.c kernel/bpf/arraymap.c kernel/bpf/devmap.c kernel/bpf/helpers.c
kernel/bpf/inode.c kernel/bpf/lpm_trie.c kernel/bpf/map_in_map.c kernel/bpf/map_in_map.h
kernel/bpf/stackmap.c kernel/bpf/tnum.c kernel/bpf/percpu_freelist.c kernel/bpf/percpu_freelist.h
kernel/bpf/bpf_lru_list.c kernel/bpf/bpf_lru_list.h kernel/bpf/Makefile
include/linux/bpf.h include/linux/bpf_types.h include/linux/bpf_verifier.h
include/linux/btf.h include/linux/filter.h include/linux/bpf-cgroup.h
include/uapi/linux/bpf.h include/uapi/linux/btf.h include/uapi/linux/bpf_common.h
net/core/filter.c net/core/sock_map.c net/core/bpf_sk_storage.c
"
n=0; miss=0
for f in $FILES; do
  if [ -f "$D/$f" ]; then
    mkdir -p "$(dirname "$f")"; cp "$D/$f" "$f"; n=$((n+1))
  else
    echo "    donor lacks $f"; miss=$((miss+1))
  fi
done
# bool-x's sockmap.c is replaced by net/core/sock_map.c upstream; drop it if the
# donor took that route, or the two definitions collide at link time.
if [ -f "$D/net/core/sock_map.c" ] && [ -f kernel/bpf/sockmap.c ] && [ ! -f "$D/kernel/bpf/sockmap.c" ]; then
  rm -f kernel/bpf/sockmap.c
  sed -i -E 's/^obj-\$\(CONFIG_BPF_SYSCALL\)[[:space:]]*\+=[[:space:]]*sockmap\.o$//' kernel/bpf/Makefile 2>/dev/null || true
  echo "    removed kernel/bpf/sockmap.c (donor uses net/core/sock_map.c)"
fi
echo "  transplanted $n files ($miss absent in donor)"
rm -rf "$(dirname "$D")"
