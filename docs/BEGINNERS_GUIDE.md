# Beginner's Guide: Building Your First Android Kernel

This guide will walk you through building the Docker-enabled kernel step-by-step, assuming you have little to no experience with kernel compilation.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Understanding the Basics](#understanding-the-basics)
3. [Step-by-Step Build Process](#step-by-step-build-process)
4. [Installation Guide](#installation-guide)
5. [Troubleshooting](#troubleshooting)
6. [FAQ](#faq)

---

## Prerequisites

### What You'll Need

#### Hardware
- **Computer**: Mac or Linux (Windows with WSL2 also works)
- **RAM**: 16GB minimum (32GB recommended)
- **Disk Space**: 60GB free
- **Phone**: Redmi K20 Pro (raphael) with unlocked bootloader

#### Software
- Docker Desktop installed
- ADB and Fastboot tools
- Git
- Python 3.x
- Text editor (VS Code, Sublime, etc.)

#### Knowledge Level
- ✅ Basic command line usage
- ✅ Ability to follow instructions carefully
- ❌ No prior kernel compilation experience needed
- ❌ No programming knowledge required

---

## Understanding the Basics

### What is a Kernel?

Think of the kernel as the **translator** between your apps and your phone's hardware:
- Apps want to use the camera → Kernel talks to camera hardware
- Apps want to save files → Kernel talks to storage
- Apps want to connect to WiFi → Kernel talks to WiFi chip

### What is Docker?

Docker lets you run **isolated containers** (like mini virtual machines) on your phone. This is useful for:
- Running Linux apps on Android
- Development environments
- Server applications
- Testing software safely

### Why Do We Need a Custom Kernel?

Stock Android kernels don't have Docker support enabled. We need to:
1. Get the kernel source code
2. Enable Docker features
3. Compile it
4. Install it on the phone

---

## Step-by-Step Build Process

### Step 1: Set Up Your Computer

#### Install Docker Desktop

**Mac**:
```bash
# Download from https://www.docker.com/products/docker-desktop
# Install the .dmg file
# Start Docker Desktop
```

**Linux**:
```bash
sudo apt-get update
sudo apt-get install docker.io
sudo systemctl start docker
sudo usermod -aG docker $USER  # Add yourself to docker group
# Log out and back in
```

#### Install ADB and Fastboot

**Mac**:
```bash
brew install android-platform-tools
```

**Linux**:
```bash
sudo apt-get install android-tools-adb android-tools-fastboot
```

#### Verify Installation
```bash
docker --version
# Should show: Docker version 20.x.x or higher

adb version
# Should show: Android Debug Bridge version 1.x.x

fastboot --version
# Should show: fastboot version 1.x.x
```

---

### Step 2: Download the Kernel Source

#### Clone the Repository
```bash
# Create a workspace
mkdir -p ~/android-kernel
cd ~/android-kernel

# Clone the SOVIET-ANDROID kernel source
git clone https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael
cd kernel_xiaomi_raphael
```

**What just happened?**
- You created a folder for kernel work
- You downloaded the kernel source code (about 2GB)
- You're now inside the kernel source directory

---

### Step 3: Download the Toolchain

The toolchain is the set of tools (compiler, linker, etc.) needed to build the kernel.

#### Download Android Clang 18.0.1
```bash
# Create toolchain directory
mkdir -p ~/android-kernel/toolchains
cd ~/android-kernel/toolchains

# Download the toolchain (this is large, ~1.5GB)
wget https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/main/clang-r522817.tar.gz

# Extract it
mkdir clang-r522817
tar -xzf clang-r522817.tar.gz -C clang-r522817

# Verify
ls clang-r522817/bin/clang
# Should show the clang compiler
```

**What just happened?**
- You downloaded the official Android compiler
- You extracted it to a known location
- This compiler will turn source code into a working kernel

---

### Step 4: Create the Docker Config Fragment

This file tells the kernel to enable Docker features.

```bash
cd ~/android-kernel/kernel_xiaomi_raphael

# Create the config file
cat > docker.config << 'EOF'
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
EOF

# Verify it was created
cat docker.config
```

**What just happened?**
- You created a list of Docker features to enable
- This file will be merged with the base kernel config

---

### Step 5: Create the Build Script

This script automates the compilation process.

```bash
# Create the build script
cat > build_docker.sh << 'EOF'
#!/bin/bash
set -e

echo "=== Docker-Enabled Kernel Build ==="

# Set up environment variables
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

echo "Step 1: Cleaning old build..."
rm -rf out
mkdir -p out

echo "Step 2: Creating base config..."
make O=out ARCH=arm64 raphael_defconfig

echo "Step 3: Merging Docker config..."
ARCH=arm64 scripts/kconfig/merge_config.sh -m -O out out/.config docker.config

echo "Step 4: Finalizing config..."
make O=out ARCH=arm64 olddefconfig

echo "Step 5: Verifying Docker flags..."
grep -E "CONFIG_CGROUP_PIDS|CONFIG_USER_NS|CONFIG_PID_NS" out/.config

echo "Step 6: Building kernel (this will take 10-20 minutes)..."
make O=out ARCH=arm64 -j$(nproc)

echo "=== Build Complete! ==="
ls -lh out/arch/arm64/boot/Image.gz-dtb
EOF

# Make it executable
chmod +x build_docker.sh
```

**What just happened?**
- You created a script that will:
  1. Set up the build environment
  2. Create the base config
  3. Add Docker features
  4. Compile the kernel
- The script is now ready to run

---

### Step 6: Create the Docker Wrapper

This runs the build inside a Docker container for consistency.

```bash
# Create the wrapper script
cat > run_builder.sh << 'EOF'
#!/bin/bash

# Build the Docker image first (one-time setup)
docker build -t android-kernel-builder - << 'DOCKERFILE'
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    build-essential bc bison flex libssl-dev \
    libncurses5-dev git curl python3 ccache \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /kernel
DOCKERFILE

# Run the build
docker run --rm -i \
  --name kernel-builder \
  --cpus="16" \
  --memory="60g" \
  -v $(pwd):/kernel \
  -v ~/android-kernel/toolchains/clang-r522817:/opt/clang \
  --tmpfs /tmp/build:rw,size=4G,mode=1777 \
  android-kernel-builder \
  bash /kernel/build_docker.sh
EOF

# Make it executable
chmod +x run_builder.sh
```

**What just happened?**
- You created a wrapper that:
  1. Builds a Docker container with all needed tools
  2. Mounts your kernel source and toolchain
  3. Runs the build script inside the container
- This ensures a clean, reproducible build environment

---

### Step 7: Run the Build!

```bash
# Start the build
./run_builder.sh
```

**What to expect:**
- First run will download Docker base image (~200MB)
- Build will take 10-20 minutes
- You'll see lots of compilation messages scrolling by
- Final output: `out/arch/arm64/boot/Image.gz-dtb`

**Coffee break time!** ☕

---

### Step 8: Extract Your Stock Boot Image

Before we can use the new kernel, we need to get the ramdisk from your current boot image.

#### Connect Your Phone
```bash
# Enable USB Debugging on your phone:
# Settings → About Phone → Tap "Build Number" 7 times
# Settings → Developer Options → Enable "USB Debugging"

# Connect phone via USB
adb devices
# Should show your device
```

#### Backup Current Boot
```bash
# Reboot to bootloader
adb reboot bootloader

# Wait for bootloader mode, then:
fastboot getvar current-slot
# Note the output (either 'a' or 'b')

# Save your current boot image (IMPORTANT BACKUP!)
fastboot boot boot_backup.img
# This creates a backup

# Reboot back to system
fastboot reboot
```

#### Extract the Boot Image
```bash
# Download the unpack script
curl -O https://raw.githubusercontent.com/[your-repo]/scripts/unpack_boot.py

# Unpack it
python3 unpack_boot.py boot_backup.img stock_extracted

# You should now have:
# stock_extracted/ramdisk.cpio.gz
# stock_extracted/boot_params.txt
```

**What just happened?**
- You backed up your current boot image (safety first!)
- You extracted the ramdisk (needed for the new boot image)
- You saved the boot parameters (needed for repacking)

---

### Step 9: Repack the Boot Image

Now we combine your new kernel with the stock ramdisk.

```bash
# Download mkbootimg
git clone https://android.googlesource.com/platform/system/tools/mkbootimg
cd mkbootimg

# Repack with your new kernel
python3 mkbootimg.py \
  --kernel ../out/arch/arm64/boot/Image.gz-dtb \
  --ramdisk ../stock_extracted/ramdisk.cpio.gz \
  --cmdline "console=null androidboot.hardware=qcom androidboot.usbcontroller=a600000.dwc3 androidboot.boot_devices=soc/1d84000.ufshc service_locator.enable=1 lpm_levels.sleep_disabled=1 loop.max_part=16 androidboot.init_fatal_reboot_target=recovery kpti=off swiotlb=1 androidboot.super_partition=system" \
  --base 0x10000000 \
  --pagesize 4096 \
  --os_version 0 \
  --os_patch_level 2025-10 \
  --output boot-custom.img

# Verify it was created
ls -lh boot-custom.img
# Should be about 14MB
```

**What just happened?**
- You combined:
  - Your new kernel (with Docker support)
  - The stock ramdisk (system files)
  - The correct boot parameters
- Result: A flashable boot image!

---

## Installation Guide

### Step 10: Flash the Kernel

⚠️ **IMPORTANT**: Make sure you have `boot_backup.img` saved somewhere safe!

```bash
# Reboot to bootloader
adb reboot bootloader

# Flash your new kernel
fastboot flash boot boot-custom.img

# Reboot
fastboot reboot
```

**What to expect:**
- Phone will reboot
- Should boot normally (takes 1-2 minutes)
- If it doesn't boot after 5 minutes → see Troubleshooting below

---

### Step 11: Verify It Worked

```bash
# Once booted, reconnect via ADB
adb shell

# Check kernel version
uname -r
# Should show: 4.14.353-openela-SOVIET-STAR

# Check Docker features
cat /proc/cgroups | grep pids
# Should show: pids  0  XXX  1

ls -l /proc/self/ns/user
# Should show: user:[XXXXXXX]

# Success! Your kernel has Docker support!
```

---

## Troubleshooting

### Phone Won't Boot (Bootloop)

**Don't Panic!** This is fixable.

```bash
# Hold Power + Volume Down to force reboot to bootloader
# OR wait for it to auto-reboot to bootloader after a few tries

# Flash your backup
fastboot flash boot boot_backup.img
fastboot reboot

# Your phone will boot normally now
```

**What went wrong?**
- Possible causes:
  1. Wrong kernel source
  2. Wrong toolchain
  3. Config error
  4. Corrupted build

**Next steps:**
- Check the [JOURNEY.md](JOURNEY.md) for common pitfalls
- Verify you used the SOVIET-ANDROID source
- Verify you used Android Clang 18.0.1

### "Corrupt Data" Error

**Symptom**: Phone boots to recovery saying data is corrupt.

**Cause**: Wrong OS patch level in boot image.

**Fix**:
```bash
# Repack with correct patch level
python3 mkbootimg.py \
  ... \
  --os_patch_level 2025-10 \  # Make sure this matches!
  --output boot-custom-fixed.img

# Flash again
fastboot flash boot boot-custom-fixed.img
fastboot reboot
```

### Build Fails with "Out of Memory"

**Symptom**: Build stops with memory errors.

**Fix**:
```bash
# Reduce parallel jobs
# Edit build_docker.sh, change:
make O=out ARCH=arm64 -j$(nproc)
# To:
make O=out ARCH=arm64 -j8

# Or increase Docker memory:
# Docker Desktop → Settings → Resources → Memory → 60GB
```

### Docker Features Not Working

**Symptom**: Kernel boots but Docker features missing.

**Verify**:
```bash
# Check build config
grep CONFIG_USER_NS out/.config
# Should show: CONFIG_USER_NS=y

# Check autoconf.h (the real truth)
grep CONFIG_USER_NS out/include/generated/autoconf.h
# Should show: #define CONFIG_USER_NS 1

# If both show enabled but /proc/config.gz says disabled:
# This is normal! See JOURNEY.md "The /proc/config.gz Lie"
```

---

## FAQ

For more questions and answers, see the comprehensive [FAQ.md](FAQ.md) which covers:
- General questions about the project
- Compatibility with different devices and ROMs
- Root and security questions
- Docker functionality details
- Build process questions
- Installation and troubleshooting

### Q: How long does the build take?
**A**: 10-20 minutes on a modern computer with 16 CPU cores. First build is slower, rebuilds are faster with ccache.

### Q: Can I use this kernel on other devices?
**A**: No, this is specifically for Redmi K20 Pro (raphael). Other devices need different kernel sources and configs.

### Q: Will this void my warranty?
**A**: Unlocking the bootloader (required for custom kernels) typically voids warranty. Check with your manufacturer.

### Q: Can I update my ROM after installing this kernel?
**A**: ROM updates usually replace the kernel. You'll need to reflash the custom kernel after updating.

### Q: Is this safe?
**A**: As safe as any custom kernel. We're using the stock kernel source with minimal changes. Always keep a backup!

### Q: Why can't I run Docker containers?
**A**: The kernel supports Docker, but Android's security (PIE enforcement) blocks the standard Docker runtime. See [JOURNEY.md](JOURNEY.md) for details.

### Q: Can I use KernelSU?
**A**: The code is included but wasn't tested. Magisk works fine for root access.

### Q: How do I go back to stock?
**A**: Flash your `boot_backup.img`:
```bash
fastboot flash boot boot_backup.img
fastboot reboot
```

### Q: Can I help improve this?
**A**: Yes! This project is open source. See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to contribute.

---

## Next Steps

Now that you have a working kernel:

1. **Learn More**: Read [JOURNEY.md](JOURNEY.md) to understand what happened behind the scenes
2. **Experiment**: Try enabling other kernel features
3. **Contribute**: Help solve the Docker runtime PIE issue
4. **Share**: Help others by documenting your experience

---

## Getting Help

- **Issues**: Check existing issues on GitHub
- **Discussions**: Join the discussions section
- **Documentation**: Read [JOURNEY.md](JOURNEY.md) for detailed explanations

---

**Congratulations!** 🎉

You've just built your first Android kernel! This is a significant achievement that many developers never attempt. You now understand:
- How kernels are built
- How Android boot images work
- How to enable kernel features
- How to troubleshoot boot issues

Welcome to the world of kernel development!
