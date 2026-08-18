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
# SCOPED mode (BPF_GRAFT_SCOPE=sockopt): reproduce what Zundamon actually did
# rather than transplanting a whole 5.4 BPF core.
#
# Rikka already has __cgroup_bpf_run_filter_sock_addr and the bind/connect
# attach types, so the delta to KameOS is only two upstream features:
#   * sendmsg/recvmsg attach types -- route through the EXISTING sock_addr hook
#   * cgroup sockopt (5.3)         -- new prog type + get/setsockopt hooks
# Far smaller surface than the 40-file graft, and it matches the historical path.
if [ "${BPF_GRAFT_SCOPE:-full}" = "devmap" ]; then
  # Smallest useful graft: the REAL DEVMAP_HASH. Our backport aliases type 25
  # onto 4.14's array-based dev_map_ops, and the loader rejects the result
  # (flags:128/0) even with the flag masks widened -- proven on device. KameOS
  # has the genuine dev_map_hash_ops, so take devmap.c wholesale.
  FILES="kernel/bpf/devmap.c"   # enum + registration are handled by backport_bpf_map_types.py
  echo "  scope: devmap only (real dev_map_hash_ops)"
elif [ "${BPF_GRAFT_SCOPE:-full}" = "sockopt" ]; then
  FILES="
kernel/bpf/cgroup.c kernel/bpf/syscall.c kernel/bpf/verifier.c kernel/bpf/core.c
include/linux/bpf-cgroup.h include/linux/bpf.h include/linux/bpf_types.h
include/uapi/linux/bpf.h
net/socket.c net/ipv4/udp.c net/ipv6/udp.c net/ipv4/af_inet.c
"
  echo "  scope: sockopt+sendmsg only ($(echo $FILES | wc -w) files)"
else
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
fi
# Copy every bpf/btf header the donor has, rather than guessing a list: the
# enumerated version missed linux/bpf_lirc.h and cost a build. Globs first,
# explicit list second.
# Header glob is FULL-SCOPE ONLY. It used to run unconditionally, which meant a
# "scoped" graft still replaced include/linux/bpf.h with the donor's -- and then
# the base tree's own un-grafted files broke on it ("no member named 'pages' in
# struct bpf_map", because Rikka's bpf_map has u32 pages and the donor's does
# not). A scope that overwrites the core header is not a scope.
if [ "${BPF_GRAFT_SCOPE:-full}" = "full" ]; then
  for pat in "include/linux/bpf*.h" "include/uapi/linux/bpf*.h" \
             "include/linux/btf*.h" "include/uapi/linux/btf*.h"; do
    for f in $(cd "$D" && ls $pat 2>/dev/null); do
      mkdir -p "$(dirname "$f")"; cp "$D/$f" "$f"
    done
  done
  echo "  headers: globbed bpf*/btf* from donor (full scope)"
else
  echo "  headers: NOT globbed -- scoped graft keeps the base tree's headers"
fi

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

# The donor's include/linux/filter.h reaches for 5.x core helpers that a 4.14
# tree does not have, and -Werror turns each into a build stop:
#   skb_metadata_len        4.18  (skb_shinfo()->meta_len does not exist here)
#   cant_sleep              5.2   (a might_sleep-style debug assertion)
#   set_vm_flush_reset_perms 5.4  (TLB-flush optimisation when freeing exec pages)
#   kallsyms_show_value     4.15  (kptr_restrict gate; signature changed in 5.x)
# All four are safely stubbable on 4.14: two are pure debug, one is an
# optimisation, and refusing to show kallsyms values is the conservative answer.
cat > include/linux/bpf_transplant_compat.h <<'SHIM'
/* Generated by scripts/transplant_bpf.sh -- 4.14 shims for a 5.x BPF graft. */
#ifndef _BPF_TRANSPLANT_COMPAT_H
#define _BPF_TRANSPLANT_COMPAT_H

#include <linux/types.h>

#ifndef BPF_TRANSPLANT_HAVE_SKB_METADATA
static inline u32 skb_metadata_len(const struct sk_buff *skb)
{
	return 0;	/* no XDP metadata area on 4.14 */
}
#endif

#ifndef cant_sleep
#define cant_sleep() do { } while (0)
#endif

#ifndef set_vm_flush_reset_perms
#define set_vm_flush_reset_perms(addr) do { (void)(addr); } while (0)
#endif

#ifndef BPF_TRANSPLANT_HAVE_KALLSYMS_SHOW_VALUE
#define kallsyms_show_value(...) (false)
#endif


/* 5.x core helpers the donor BPF sources call, with 4.14 equivalents. */
#ifndef atomic_fetch_add_unless
#define atomic_fetch_add_unless(v, a, u)	__atomic_add_unless((v), (a), (u))
#endif

#ifndef ktime_get_boottime_ns
#define ktime_get_boottime_ns()			ktime_get_boot_ns()
#endif

#ifndef ktime_get_coarse_boottime_ns
#define ktime_get_coarse_boottime_ns()		ktime_get_boot_ns()
#endif

/* perf BPF notifications (5.1). Purely observability -- stub them out. */
#ifndef PERF_BPF_EVENT_PROG_LOAD
enum perf_bpf_event_type {
	PERF_BPF_EVENT_UNKNOWN		= 0,
	PERF_BPF_EVENT_PROG_LOAD	= 1,
	PERF_BPF_EVENT_PROG_UNLOAD	= 2,
};
#define perf_event_bpf_event(prog, type, flags) do { } while (0)
#endif


/* flow_dissector BPF (5.0) -- the donor's syscall.c references these for
 * BPF_PROG_TYPE_FLOW_DISSECTOR attach/detach/query. Nothing on Android loads a
 * flow_dissector program, so refusing the operation is correct behaviour, not
 * a degradation. */
#ifndef BPF_TRANSPLANT_HAVE_FLOW_DISSECTOR
struct bpf_prog;
struct netlink_ext_ack;
union bpf_attr;
static inline int skb_flow_dissector_bpf_prog_attach(const union bpf_attr *attr,
						     struct bpf_prog *prog)
{ return -EINVAL; }
static inline int skb_flow_dissector_bpf_prog_detach(const union bpf_attr *attr)
{ return -EINVAL; }
static inline int skb_flow_dissector_prog_query(const union bpf_attr *attr,
						union bpf_attr __user *uattr)
{ return -EINVAL; }
#endif

/* BPF_CALL_ARGS (5.0) lives in filter.h upstream; the donor's syscall.c uses it
 * for the interpreter-with-args entry point. */
#ifndef BPF_CALL_ARGS
#define BPF_CALL_ARGS(a, b, c, d, e, f) ({ (void)(a); 0; })
#endif


/* Raw-tracepoint BPF (5.0) and the kallsyms dump gate (4.18). Both donors'
 * syscall.c want exactly these three, which is what made the sockopt graft
 * look finishable: two independent donors converged on the same short list.
 *
 * Safe to stub on this tree. Rikka has no tracing at all -- no ftrace, no
 * kprobes, no trace_call_bpf -- so refusing to register a raw tracepoint is the
 * truthful answer rather than a degradation, and KameOS's own shipped kernel is
 * in the same position. bpf_dump_raw_ok gates exposing raw instructions to
 * userspace; returning false is the conservative choice.
 */
#ifndef BPF_TRANSPLANT_HAVE_RAW_TP
struct bpf_raw_event_map;
static inline bool bpf_dump_raw_ok(void) { return false; }
static inline int bpf_probe_register(struct bpf_raw_event_map *btp,
				     struct bpf_prog *prog)
{ return -EOPNOTSUPP; }
static inline int bpf_probe_unregister(struct bpf_raw_event_map *btp,
				       struct bpf_prog *prog)
{ return -EOPNOTSUPP; }
#endif

#endif /* _BPF_TRANSPLANT_COMPAT_H */
SHIM

# Drop shims the base tree already provides. See the vmalloc.h note above.
python3 - <<'PYPRUNE'
import re, os
p = "include/linux/bpf_transplant_compat.h"
s = open(p, encoding="utf-8", errors="replace").read()
hdrs = []
for root, _, files in os.walk("include"):
    for f in files:
        if f.endswith(".h") and f != "bpf_transplant_compat.h":
            hdrs.append(os.path.join(root, f))
blob = ""
for h in hdrs:
    try: blob += open(h, encoding="utf-8", errors="replace").read()
    except OSError: pass
dropped = []
def prune(m):
    name = m.group(1)
    # a real declaration or definition of the symbol elsewhere in include/
    if re.search(r"\b%s\s*\(" % re.escape(name), blob):
        dropped.append(name); return ""
    return m.group(0)
s = re.sub(r"#ifndef (\w+)\n(?:(?!#ifndef|#endif).)*?#endif\n",
           prune, s, flags=re.S)
open(p, "w", encoding="utf-8").write(s)
print("    shims pruned (tree already has them): %s" % (", ".join(dropped) or "none"))
PYPRUNE

# Pull the shims in from filter.h, after its own includes.
python3 - <<'PYINJ'
import re
p = "include/linux/filter.h"
s = open(p, encoding="utf-8", errors="replace").read()
if "bpf_transplant_compat.h" not in s:
    m = None
    for m in re.finditer(r"^#include [<\"][^\n]+\n", s, re.M):
        pass                      # take the LAST include of the opening block
    at = m.end() if m else 0
    s = s[:at] + "#include <linux/bpf_transplant_compat.h>\n" + s[at:]
    open(p, "w", encoding="utf-8").write(s)
    print("    filter.h: pulled in bpf_transplant_compat.h")
PYINJ
# syscall.c/verifier.c call these too, so pull the shims in there as well.
for f in kernel/bpf/syscall.c kernel/bpf/verifier.c kernel/bpf/core.c kernel/bpf/cgroup.c; do
  [ -f "$f" ] || continue
  grep -q bpf_transplant_compat.h "$f" || \
    sed -i '0,/^#include /s//#include <linux\/bpf_transplant_compat.h>\n#include /' "$f"
done
echo "  compat shims installed"

rm -rf "$(dirname "$D")"
