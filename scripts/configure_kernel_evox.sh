#!/bin/bash
set -e

# Navigate to source
cd /kernel/evox_kernel

# Clean previous builds
make mrproper
rm -rf out
mkdir -p out

# Load defconfig
make O=out ARCH=arm64 raphael_defconfig

# Enable Docker support
scripts/config --file out/.config \
    -e CONFIG_NAMESPACES \
    -e CONFIG_NET_NS \
    -e CONFIG_PID_NS \
    -e CONFIG_IPC_NS \
    -e CONFIG_UTS_NS \
    -e CONFIG_CGROUPS \
    -e CONFIG_CGROUP_CPUACCT \
    -e CONFIG_CGROUP_DEVICE \
    -e CONFIG_CGROUP_FREEZER \
    -e CONFIG_CGROUP_SCHED \
    -e CONFIG_CPUSETS \
    -e CONFIG_MEMCG \
    -e CONFIG_KEYS \
    -e CONFIG_VETH \
    -e CONFIG_BRIDGE \
    -e CONFIG_BRIDGE_NETFILTER \
    -e CONFIG_IP_NF_FILTER \
    -e CONFIG_IP_NF_TARGET_MASQUERADE \
    -e CONFIG_NETFILTER_XT_MATCH_ADDRTYPE \
    -e CONFIG_NETFILTER_XT_MATCH_CONNTRACK \
    -e CONFIG_NETFILTER_XT_MATCH_IPVS \
    -e CONFIG_NETFILTER_XT_TARGET_REDIRECT \
    -e CONFIG_IP_NF_NAT \
    -e CONFIG_NF_NAT \
    -e CONFIG_POSIX_MQUEUE \
    -e CONFIG_DEVPTS_MULTIPLE_INSTANCES \
    -e CONFIG_NF_NAT_IPV4 \
    -e CONFIG_NF_NAT_NEEDED \
    -e CONFIG_OVERLAY_FS \
    -e CONFIG_IKCONFIG \
    -e CONFIG_IKCONFIG_PROC

# Disable LTO to prevent OOM
scripts/config --file out/.config \
    -d CONFIG_LTO_CLANG \
    -d CONFIG_LTO_CLANG_THIN \
    -d CONFIG_LTO_CLANG_FULL \
    -d CONFIG_FORTIFY_SOURCE \
    -d CONFIG_INIT_STACK_ALL_ZERO \
    -e CONFIG_INIT_STACK_NONE \
    -d CONFIG_LLVM_POLLY

# Save config
make O=out ARCH=arm64 olddefconfig

echo "Configuration complete!"
