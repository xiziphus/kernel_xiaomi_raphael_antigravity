#!/bin/bash
set -e

echo "Configuring Evolution X kernel with STOCK config + Docker support..."

cd /Volumes/android-kernel/evox_kernel

# Use stock config as base
make O=out ARCH=arm64 stock_raphael_defconfig

# Enable Docker support (layer on top of stock config)
./scripts/config --file out/.config \
    --enable CONFIG_NAMESPACES \
    --enable CONFIG_NET_NS \
    --enable CONFIG_PID_NS \
    --enable CONFIG_IPC_NS \
    --enable CONFIG_UTS_NS \
    --enable CONFIG_CGROUPS \
    --enable CONFIG_CGROUP_CPUACCT \
    --enable CONFIG_CGROUP_DEVICE \
    --enable CONFIG_CGROUP_FREEZER \
    --enable CONFIG_CGROUP_SCHED \
    --enable CONFIG_CPUSETS \
    --enable CONFIG_MEMCG \
    --enable CONFIG_KEYS \
    --enable CONFIG_VETH \
    --enable CONFIG_BRIDGE \
    --enable CONFIG_BRIDGE_NETFILTER \
    --enable CONFIG_IP_NF_FILTER \
    --enable CONFIG_IP_NF_TARGET_MASQUERADE \
    --enable CONFIG_NETFILTER_XT_MATCH_ADDRTYPE \
    --enable CONFIG_NETFILTER_XT_MATCH_CONNTRACK \
    --enable CONFIG_NETFILTER_XT_MATCH_IPVS \
    --enable CONFIG_NETFILTER_XT_TARGET_REDIRECT \
    --enable CONFIG_IP_NF_NAT \
    --enable CONFIG_NF_NAT \
    --enable CONFIG_POSIX_MQUEUE \
    --enable CONFIG_DEVPTS_MULTIPLE_INSTANCES \
    --enable CONFIG_NF_NAT_IPV4 \
    --enable CONFIG_NF_NAT_NEEDED \
    --enable CONFIG_OVERLAY_FS

# Verify KernelSU flags (should already be in stock config)
./scripts/config --file out/.config \
    --enable CONFIG_KPROBES \
    --enable CONFIG_HAVE_KPROBES \
    --enable CONFIG_KPROBE_EVENTS

# Update the config
cd out
make olddefconfig

echo "Stock-based configuration complete!"
echo "Docker flags enabled on top of working stock config"
