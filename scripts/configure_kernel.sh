#!/bin/bash
set -e

# Navigate to source
cd /kernel/source

# Set architecture variables
export ARCH=arm64
export SUBARCH=arm64

# Clean source tree to ensure out-of-tree build works
echo "Cleaning source tree..."
make mrproper

# Create out directory
mkdir -p out

# Load default configuration to out directory
# Adjust 'raphael_defconfig' if the actual file name differs (e.g., vendor/raphael_defconfig)
if [ -f "arch/arm64/configs/vendor/raphael_defconfig" ]; then
    make O=out vendor/raphael_defconfig
elif [ -f "arch/arm64/configs/raphael_defconfig" ]; then
    make O=out raphael_defconfig
else
    echo "Error: Could not find raphael_defconfig"
    exit 1
fi

# Enable Docker-related configurations in out/.config
echo "Enabling Docker configurations..."

# Helper function to modify config in out directory
config_cmd() {
    scripts/config --file out/.config "$@"
}

config_cmd --enable CONFIG_NAMESPACES
config_cmd --enable CONFIG_NET_NS
config_cmd --enable CONFIG_PID_NS
config_cmd --enable CONFIG_IPC_NS
config_cmd --enable CONFIG_UTS_NS
config_cmd --enable CONFIG_USER_NS
config_cmd --enable CONFIG_CGROUPS
config_cmd --enable CONFIG_CGROUP_CPUACCT
config_cmd --enable CONFIG_CGROUP_DEVICE
config_cmd --enable CONFIG_CGROUP_FREEZER
config_cmd --enable CONFIG_CGROUP_SCHED
config_cmd --enable CONFIG_CPUSETS
config_cmd --enable CONFIG_MEMCG
config_cmd --enable CONFIG_KEYS
config_cmd --enable CONFIG_VETH
config_cmd --enable CONFIG_BRIDGE
config_cmd --enable CONFIG_OVERLAY_FS
config_cmd --enable CONFIG_IP_NF_FILTER
config_cmd --enable CONFIG_IP_NF_TARGET_MASQUERADE
config_cmd --enable CONFIG_NETFILTER_ADVANCED
config_cmd --enable CONFIG_NETFILTER_XT_MATCH_ADDRTYPE
config_cmd --enable CONFIG_NETFILTER_XT_MATCH_IPVS
config_cmd --enable CONFIG_EXT4_FS
config_cmd --enable CONFIG_F2FS_FS
config_cmd --enable CONFIG_IKCONFIG
config_cmd --enable CONFIG_IKCONFIG_PROC

# Enable KProbes for KernelSU (Legacy method)
config_cmd --enable CONFIG_KPROBES
config_cmd --enable CONFIG_KPROBE_EVENTS
config_cmd --enable CONFIG_HAVE_KPROBES

# Disable LTO to prevent OOM issues during linking
config_cmd --disable CONFIG_LTO_CLANG
config_cmd --disable CONFIG_LTO_CLANG_THIN
config_cmd --disable CONFIG_LTO_CLANG_FULL

# Ensure KernelSU is enabled (if present)
if grep -q "CONFIG_KSU" out/.config; then
    config_cmd --enable CONFIG_KSU
    echo "KernelSU config found and enabled."
else
    echo "Warning: CONFIG_KSU not found in out/.config. Check if KSU patch is applied."
fi

# Update .config in out directory
make O=out olddefconfig

echo "Configuration complete. Ready to build."
