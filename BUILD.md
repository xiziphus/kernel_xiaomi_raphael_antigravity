# Building the Kernel

This guide explains how to build the Docker-enabled kernel for Redmi K20 Pro from source.

## Prerequisites

### Hardware Requirements
- **RAM**: 16GB+ recommended
- **Disk Space**: 60GB+ free
- **CPU**: Multi-core processor (16+ cores recommended)

### Software Requirements
- Docker (for containerized build)
- Git
- Python 3.x
- ADB and Fastboot tools

## Setup

### 1. Clone the Kernel Source

```bash
# Clone the SOVIET-ANDROID kernel
git clone https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael
cd kernel_xiaomi_raphael
```

### 2. Download the Toolchain

```bash
# Download Android Clang 18.0.1 (r522817)
wget https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/main/clang-r522817.tar.gz

# Extract to /Volumes/android-kernel/clang-r522817 (or your preferred location)
mkdir -p /Volumes/android-kernel/clang-r522817
tar -xzf clang-r522817.tar.gz -C /Volumes/android-kernel/clang-r522817
```

### 3. Prepare Docker Config Fragment

Create `docker.config` with the following content:

```
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_PID_NS=y
CONFIG_IPC_NS=y
CONFIG_UTS_NS=y
CONFIG_USER_NS=y
CONFIG_CGROUPS=y
CONFIG_CGROUP_PIDS=y
CONFIG_CGROUP_DEVICE=y
CONFIG_CGROUP_FREEZER=y
CONFIG_CGROUP_SCHED=y
CONFIG_CPUSETS=y
CONFIG_MEMCG=y
CONFIG_KEYS=y
CONFIG_VETH=y
CONFIG_OVERLAY_FS=y
CONFIG_BRIDGE=y
CONFIG_NETFILTER=y
CONFIG_NETFILTER_ADVANCED=y
CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y
CONFIG_NETFILTER_XT_MATCH_IPVS=y
CONFIG_IP_NF_TARGET_MASQUERADE=y
CONFIG_NETFILTER_XT_MARK=y
CONFIG_IP_NF_NAT=y
CONFIG_NF_NAT=y
CONFIG_POSIX_MQUEUE=y
```

## Build Process

### 1. Create Build Script

Create `build_docker.sh`:

```bash
#!/bin/bash
set -e

export ARCH=arm64
export SUBARCH=arm64
export PATH=/opt/clang/bin:$PATH
export CC=clang
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-gnu-
export CROSS_COMPILE_ARM32=arm-linux-gnueabi-
export CROSS_COMPILE_COMPAT=arm-linux-gnueabi-
export LD=/opt/clang/bin/ld.lld
export AR=llvm-ar
export NM=llvm-nm
export OBJCOPY=llvm-objcopy
export OBJDUMP=llvm-objdump
export STRIP=llvm-strip
export LLVM_IAS=1

# Enable ccache for faster rebuilds
export USE_CCACHE=1
export CCACHE_DIR=/tmp/build/.ccache
mkdir -p $CCACHE_DIR
export PATH=/usr/lib/ccache:$PATH

echo "=== Step 1: Clean build directory ==="
rm -rf out
mkdir -p out

echo "=== Step 2: Generate base config from raphael_defconfig ==="
make O=out ARCH=arm64 raphael_defconfig

echo "=== Step 3: Merge Docker config fragment ==="
ARCH=arm64 scripts/kconfig/merge_config.sh -m -O out out/.config docker.config

echo "=== Step 4: Run olddefconfig to resolve dependencies ==="
make O=out ARCH=arm64 olddefconfig

echo "=== Step 5: Verify Docker flags ==="
grep -E "CONFIG_CGROUP_PIDS|CONFIG_USER_NS|CONFIG_PID_NS" out/.config || echo "WARNING: Some Docker flags missing!"

echo "=== Step 6: Build kernel ==="
make O=out ARCH=arm64 -j$(nproc)

echo "=== Build Complete ==="
ls -lh out/arch/arm64/boot/Image.gz-dtb
echo "SUCCESS: Kernel image ready!"
```

### 2. Create Docker Wrapper

Create `run_builder.sh`:

```bash
#!/bin/bash

docker run --rm -i \
  --name soviet-kernel-builder \
  --cpus="16" \
  --memory="60g" \
  -v /Volumes/android-kernel/soviet_kernel_stock:/kernel/soviet_kernel_stock \
  -v /Volumes/android-kernel/clang-r522817:/opt/clang \
  --tmpfs /tmp/build:rw,size=4G,mode=1777 \
  android-kernel-builder \
  bash /kernel/soviet_kernel_stock/build_docker.sh
```

### 3. Build the Docker Image

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    build-essential \
    bc \
    bison \
    flex \
    libssl-dev \
    libncurses5-dev \
    git \
    curl \
    python3 \
    ccache \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /kernel
EOF

# Build the image
docker build -t android-kernel-builder .
```

### 4. Run the Build

```bash
chmod +x build_docker.sh run_builder.sh
./run_builder.sh
```

The build will take 10-20 minutes depending on your hardware. Output will be in `out/arch/arm64/boot/Image.gz-dtb`.

## Repacking the Boot Image

### 1. Extract Stock Boot Image

```bash
python3 scripts/unpack_boot.py boot_backup.img stock_kernel_extracted
```

### 2. Repack with New Kernel

```bash
python3 mkbootimg_src/mkbootimg.py \
  --kernel out/arch/arm64/boot/Image.gz-dtb \
  --ramdisk stock_kernel_extracted/ramdisk.cpio.gz \
  --cmdline "console=null androidboot.hardware=qcom androidboot.usbcontroller=a600000.dwc3 androidboot.boot_devices=soc/1d84000.ufshc service_locator.enable=1 lpm_levels.sleep_disabled=1 loop.max_part=16 androidboot.init_fatal_reboot_target=recovery kpti=off swiotlb=1 androidboot.super_partition=system" \
  --base 0x10000000 \
  --pagesize 4096 \
  --os_version 0 \
  --os_patch_level 2025-10 \
  --output boot-custom.img
```

**Critical**: The `--os_patch_level 2025-10` parameter is essential for encryption compatibility.

## Verification

### 1. Check Kernel Config

```bash
grep -E "CONFIG_CGROUP_PIDS|CONFIG_USER_NS|CONFIG_PID_NS|CONFIG_KSU" out/.config
```

Expected output:
```
CONFIG_CGROUP_PIDS=y
CONFIG_USER_NS=y
CONFIG_PID_NS=y
CONFIG_KSU=y
```

### 2. Verify Boot Image

```bash
python3 mkbootimg_src/unpack_bootimg.py --boot_img boot-custom.img
```

Check that:
- OS patch level is `2025-10`
- Kernel size matches your built kernel
- Cmdline is correct

## Troubleshooting

### Build Fails with "Out of Memory"
- Increase Docker memory allocation to 60GB+
- Reduce parallel jobs: `make -j8` instead of `make -j$(nproc)`

### Config Flags Missing After Build
- Ensure `merge_config.sh` ran successfully
- Check for dependency conflicts in `out/.config`
- Verify `olddefconfig` didn't silently disable flags

### Boot Image Too Large
- Check partition size: `fastboot getvar partition-size:boot`
- The kernel should be ~13MB, boot image ~14MB

## Optimization Tips

### Faster Builds
- Use ccache (already enabled in script)
- Use tmpfs for build output (already enabled)
- Allocate more CPU cores to Docker

### Smaller Kernel
- Disable unused drivers in `raphael_defconfig`
- Use LZ4 compression instead of GZIP (requires bootloader support)

## Resources

- [Kernel Source](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael)
- [Android Clang Toolchain](https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/)
- [mkbootimg Documentation](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
