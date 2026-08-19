#!/usr/bin/env python3
"""Implement trie_get_next_key() for LPM_TRIE maps (upstream b471f2f1de8b, 5.6).

Why
---
With netbpfload passing and netd surviving, system_server got as far as
NetworkStatsService and then took the whole boot down:

    FATAL EXCEPTION IN SYSTEM PROCESS: main
    java.lang.RuntimeException: Failed to create service
        com.android.server.NetworkStatsServiceInitializer
    Caused by: java.lang.IllegalStateException: Cannot open local_net_access map
        at ...BpfNetMaps.getLocalNetAccessMap(BpfNetMaps.java:303)
    Caused by: android.system.ErrnoException:
        nativeGetNextMapKey failed: errno 524 (Unknown error 524)
        at ...SingleWriterBpfMap.<init>(SingleWriterBpfMap.java:78)

524 is ENOTSUPP, and it comes from rikka-v5's kernel/bpf/lpm_trie.c:

    static int trie_get_next_key(struct bpf_map *map, void *key, void *next_key)
    {
        return -ENOTSUPP;
    }

`local_net_access` is Android 16's local-network-access map, the one
BPF_MAP_TYPE_LPM_TRIE entry in netd.o. SingleWriterBpfMap's constructor calls
getFirstKey() on it, so a stub get_next_key is fatal to system_server even
though the map itself creates and loads perfectly.

The real implementation is a postorder walk of the trie. This is a verbatim
lift from HeliumStudio-Dev/kernel_xiaomi_raphael@oss-base -- Zundamon's own
tree, same 4.14 family -- rather than a hand-port. Every symbol it needs is
already in Rikka's lpm_trie.c: longest_prefix_match(), extract_bit(),
LPM_TREE_NODE_FLAG_IM, and lpm_trie_node.{flags,prefixlen,child,data}.

Idempotent.
"""
import os
import sys

LPM = "kernel/bpf/lpm_trie.c"

STUB = """static int trie_get_next_key(struct bpf_map *map, void *key, void *next_key)
{
	return -ENOTSUPP;
}"""

IMPL = r"""static int trie_get_next_key(struct bpf_map *map, void *_key, void *_next_key)
{
	struct lpm_trie_node *node, *next_node = NULL, *parent, *search_root;
	struct lpm_trie *trie = container_of(map, struct lpm_trie, map);
	struct bpf_lpm_trie_key *key = _key, *next_key = _next_key;
	struct lpm_trie_node **node_stack = NULL;
	int err = 0, stack_ptr = -1;
	unsigned int next_bit;
	size_t matchlen = 0;

	/* The get_next_key follows postorder, returning more specific keys
	 * before less specific ones. Backported from upstream b471f2f1de8b via
	 * oss-base; see scripts/backport_trie_get_next_key.py.
	 */

	/* Empty trie */
	search_root = rcu_dereference(trie->root);
	if (!search_root)
		return -ENOENT;

	/* For invalid key, find the leftmost node in the trie */
	if (!key || key->prefixlen > trie->max_prefixlen)
		goto find_leftmost;

	node_stack = kmalloc_array(trie->max_prefixlen + 1,
				   sizeof(struct lpm_trie_node *),
				   GFP_ATOMIC | __GFP_NOWARN);
	if (!node_stack)
		return -ENOMEM;

	/* Try to find the exact node for the given key */
	for (node = search_root; node;) {
		node_stack[++stack_ptr] = node;
		matchlen = longest_prefix_match(trie, node, key);
		if (node->prefixlen != matchlen ||
		    node->prefixlen == key->prefixlen)
			break;

		next_bit = extract_bit(key->data, node->prefixlen);
		node = rcu_dereference(node->child[next_bit]);
	}
	if (!node || node->prefixlen != matchlen ||
	    (node->flags & LPM_TREE_NODE_FLAG_IM))
		goto find_leftmost;

	/* The node with the exactly-matching key has been found,
	 * find the first node in postorder after the matched node.
	 */
	node = node_stack[stack_ptr];
	while (stack_ptr > 0) {
		parent = node_stack[stack_ptr - 1];
		if (rcu_dereference(parent->child[0]) == node) {
			search_root = rcu_dereference(parent->child[1]);
			if (search_root)
				goto find_leftmost;
		}
		if (!(parent->flags & LPM_TREE_NODE_FLAG_IM)) {
			next_node = parent;
			goto do_copy;
		}

		node = parent;
		stack_ptr--;
	}

	/* did not find anything */
	err = -ENOENT;
	goto free_stack;

find_leftmost:
	/* Find the leftmost non-intermediate node, all intermediate nodes
	 * have exact two children, so this function will never return NULL.
	 */
	for (node = search_root; node;) {
		if (node->flags & LPM_TREE_NODE_FLAG_IM) {
			node = rcu_dereference(node->child[0]);
		} else {
			next_node = node;
			node = rcu_dereference(node->child[0]);
			if (!node)
				node = rcu_dereference(next_node->child[1]);
		}
	}
do_copy:
	next_key->prefixlen = next_node->prefixlen;
	memcpy((void *)next_key + offsetof(struct bpf_lpm_trie_key, data),
	       next_node->data, trie->data_size);
free_stack:
	kfree(node_stack);
	return err;
}"""

if __name__ == "__main__":
    if not os.path.exists(LPM):
        sys.exit("FATAL: run from the kernel tree root")
    s = open(LPM, encoding="utf-8", errors="replace").read()
    if "find_leftmost:" in s:
        print("  lpm_trie.c: trie_get_next_key already implemented")
        sys.exit(0)
    if STUB not in s:
        sys.exit("FATAL: the -ENOTSUPP trie_get_next_key stub is not in %s "
                 "verbatim -- refusing to guess" % LPM)
    for need in ("longest_prefix_match", "extract_bit", "LPM_TREE_NODE_FLAG_IM"):
        if need not in s:
            sys.exit("FATAL: %s missing from %s; the backport needs it" % (need, LPM))
    open(LPM, "w", encoding="utf-8").write(s.replace(STUB, IMPL, 1))
    s = open(LPM, encoding="utf-8", errors="replace").read()
    if "find_leftmost:" not in s or "-ENOTSUPP" in s.split("trie_map_ops")[0][-2000:]:
        sys.exit("FATAL: patch did not take")
    print("  lpm_trie.c: trie_get_next_key implemented (postorder walk)")
