#!/bin/bash
set -e

# Navigate to source
cd /kernel/soviet_kernel_16

# Clean
make mrproper

# Load default config
make O=out ARCH=arm64 raphael_defconfig

# Enable Docker Support
scripts/config --file out/.config \
    -e CONFIG_NAMESPACES \
    -e CONFIG_NET_NS \
    -e CONFIG_PID_NS \
    -e CONFIG_IPC_NS \
    -e CONFIG_UTS_NS \
    -e CONFIG_USER_NS \
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
    -e CONFIG_OVERLAY_FS \
    -e CONFIG_IP_NF_FILTER \
    -e CONFIG_IP_NF_TARGET_MASQUERADE \
    -e CONFIG_NETFILTER_ADVANCED \
    -e CONFIG_NETFILTER_XT_MATCH_ADDRTYPE \
    -e CONFIG_NETFILTER_XT_MATCH_IPVS \
    -e CONFIG_IKCONFIG \
    -e CONFIG_IKCONFIG_PROC

# Enable KernelSU (Kprobes method preferred for 4.14)
scripts/config --file out/.config \
    -e CONFIG_KPROBES \
    -e CONFIG_KPROBE_EVENTS \
    -e CONFIG_HAVE_KPROBES \
    -e CONFIG_KSU

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
