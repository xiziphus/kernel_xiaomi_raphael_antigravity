# Critical device identification and comprehensive kernel compilation plan

## ⚠️ CRITICAL DEVICE IDENTIFICATION ISSUE

**Your request contains a device naming error.** "Xiaomi Redmi K50 Pro (codename: Raphael)" does not exist. Here are the actual devices:

- **Raphael** = Redmi K20 Pro / Mi 9T Pro (2019) with **Snapdragon 855 (SM8150)** and **kernel 4.14.x**
- **Matisse** = Redmi K50 Pro (2022) with **MediaTek Dimensity 9000** (not Snapdragon)
- **SM8450 (Snapdragon 8 Gen 1)** powers devices like Xiaomi 12 (cupid), Xiaomi 12 Pro (zeus), not K50 Pro

Since you specifically mentioned "Raphael," I'll provide guidance for the **Redmi K20 Pro/Mi 9T Pro (Raphael)** with notes for SM8450 devices where applicable. The fundamental difference is kernel version: Raphael uses 4.14.x (non-GKI), while SM8450 devices use 5.10+ (GKI-compatible).

---

## ROM recommendation: Evolution X for Raphael

Evolution X emerges as the best choice for Raphael on Android 15, offering:

**Why Evolution X wins for kernel development:**
- Official Android 15 and 16 builds with active maintenance by Joey Huab
- Uses the industry-standard SOVIET-ANDROID kernel (Linux 4.14.343, most actively maintained)
- **KernelSU v0.9.3 pre-integrated** in official builds
- Complete source code availability with excellent documentation
- Active XDA community and monthly security updates
- Download: https://evolution-x.org/devices/raphael

**Kernel source:** The SOVIET-ANDROID kernel (https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael) is used by most Raphael ROMs and receives regular updates. Latest release R6.6 from December 2024 includes performance optimizations, EEVDF scheduler backports, and GPU undervolting.

**Alternative:** crDroid v11.0 offers similar stability with official status and monthly updates at https://crdroid.net/raphael.

---

## KernelSU integration for Raphael (kernel 4.14.x)

**Version limitation:** KernelSU v1.0.0 (June 2024) removed support for non-GKI kernels. For Raphael's 4.14.x kernel, you **must use KernelSU v0.9.5** (last non-GKI version). The Manager app can update independently to latest version.

### Integration method (choose based on kprobe support)

**Automatic integration with kprobe (preferred):**

```bash
cd /path/to/kernel/source
curl -LSs "https://raw.githubusercontent.com/tiann/KernelSU/main/kernel/setup.sh" | bash -s v0.9.5
```

Add to `arch/arm64/configs/raphael_defconfig`:
```
CONFIG_KPROBES=y
CONFIG_HAVE_KPROBES=y
CONFIG_KPROBE_EVENTS=y
```

**Manual integration (required if kprobe broken):**

After running the setup script above, add to defconfig:
```
CONFIG_KSU=y
# CONFIG_KPROBES is not set
```

Then modify 6 kernel source files to add KernelSU hooks:

**1. fs/exec.c** (execveat hook):
```c
#ifdef CONFIG_KSU
extern bool ksu_execveat_hook __read_mostly;
extern int ksu_handle_execveat(int *fd, struct filename **filename_ptr, void *argv,
    void *envp, int *flags);
extern int ksu_handle_execveat_sucompat(int *fd, struct filename **filename_ptr,
    void *argv, void *envp, int *flags);
#endif

static int do_execveat_common(int fd, struct filename *filename,
    struct user_arg_ptr argv,
    struct user_arg_ptr envp,
    int flags)
{
    #ifdef CONFIG_KSU
    if (unlikely(ksu_execveat_hook))
        ksu_handle_execveat(&fd, &filename, &argv, &envp, &flags);
    else
        ksu_handle_execveat_sucompat(&fd, &filename, &argv, &envp, &flags);
    #endif
    return __do_execve_file(fd, filename, argv, envp, flags, NULL);
}
```

**2. fs/open.c** (faccessat hook):
```c
#ifdef CONFIG_KSU
extern int ksu_handle_faccessat(int *dfd, const char __user **filename_user, int *mode,
    int *flags);
#endif

long do_faccessat(int dfd, const char __user *filename, int mode)
{
    #ifdef CONFIG_KSU
    ksu_handle_faccessat(&dfd, &filename, &mode, NULL);
    #endif
    // ... rest of function
}
```

**3. fs/read_write.c** (vfs_read hook):
```c
#ifdef CONFIG_KSU
extern bool ksu_vfs_read_hook __read_mostly;
extern int ksu_handle_vfs_read(struct file **file_ptr, char __user **buf_ptr,
    size_t *count_ptr, loff_t **pos);
#endif

ssize_t vfs_read(struct file *file, char __user *buf, size_t count, loff_t *pos)
{
    ssize_t ret;
    #ifdef CONFIG_KSU
    if (unlikely(ksu_vfs_read_hook))
        ksu_handle_vfs_read(&file, &buf, &count, &pos);
    #endif
    
    if (!(file->f_mode & FMODE_READ))
        return -EBADF;
    // ... rest of function
}
```

**4. fs/stat.c** (vfs_statx hook):
```c
#ifdef CONFIG_KSU
extern int ksu_handle_stat(int *dfd, const char __user **filename_user, int *flags);
#endif

int vfs_statx(int dfd, const char __user *filename, int flags,
    struct kstat *stat, u32 request_mask)
{
    #ifdef CONFIG_KSU
    ksu_handle_stat(&dfd, &filename, &flags);
    #endif
    // ... rest of function
}
```

**5. drivers/input/input.c** (Safe Mode support):
```c
#ifdef CONFIG_KSU
extern bool ksu_input_hook __read_mostly;
extern int ksu_handle_input_handle_event(unsigned int *type, unsigned int *code, int *value);
#endif

static void input_handle_event(struct input_dev *dev,
    unsigned int type, unsigned int code, int value)
{
    int disposition = input_get_disposition(dev, type, code, &value);
    #ifdef CONFIG_KSU
    if (unlikely(ksu_input_hook))
        ksu_handle_input_handle_event(&type, &code, &value);
    #endif
    // ... rest of function
}
```

**6. fs/devpts/inode.c** (terminal support):
```c
#ifdef CONFIG_KSU
extern int ksu_handle_devpts(struct inode*);
#endif

void *devpts_get_priv(struct dentry *dentry)
{
    #ifdef CONFIG_KSU
    ksu_handle_devpts(dentry->d_inode);
    #endif
    if (dentry->d_sb->s_magic != DEVPTS_SUPER_MAGIC)
        return NULL;
    return dentry->d_fsdata;
}
```

**Critical notes:**
- KernelSU integration must happen BEFORE first compilation
- Test kprobe method first - if device boots, it works
- Use manual method only if kprobe causes bootloops
- Disable CONFIG_KPROBES when using manual integration

**Official documentation:** https://kernelsu.org/guide/how-to-integrate-for-non-gki.html

---

## Docker kernel configuration for full support

Docker requires extensive kernel configuration. Here's the complete list organized by category:

### Namespaces (mandatory)
```
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_PID_NS=y
CONFIG_IPC_NS=y
CONFIG_UTS_NS=y
CONFIG_USER_NS=y                    # For rootless containers
```

### Control groups (mandatory)
```
CONFIG_CGROUPS=y
CONFIG_CGROUP_CPUACCT=y
CONFIG_CGROUP_DEVICE=y
CONFIG_CGROUP_FREEZER=y
CONFIG_CGROUP_SCHED=y
CONFIG_CGROUP_PIDS=y
CONFIG_CGROUP_BPF=y                 # If kernel 4.15+
CONFIG_CPUSETS=y
CONFIG_MEMCG=y
CONFIG_MEMCG_SWAP=y                 # Kernel < 5.8
CONFIG_BLK_CGROUP=y
CONFIG_BLK_DEV_THROTTLING=y
CONFIG_CGROUP_PERF=y
CONFIG_CGROUP_HUGETLB=y
```

### Networking core (mandatory)
```
CONFIG_VETH=y
CONFIG_BRIDGE=y
CONFIG_BRIDGE_NETFILTER=y
CONFIG_BRIDGE_VLAN_FILTERING=y
CONFIG_VXLAN=y
CONFIG_IPVLAN=y
CONFIG_MACVLAN=y
CONFIG_DUMMY=y
```

### Netfilter and NAT (mandatory)
```
CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y
CONFIG_NETFILTER_XT_MATCH_CONNTRACK=y
CONFIG_NETFILTER_XT_MATCH_IPVS=y
CONFIG_NETFILTER_XT_MARK=y
CONFIG_IP_NF_FILTER=y
CONFIG_IP_NF_MANGLE=y
CONFIG_IP_NF_TARGET_MASQUERADE=y
CONFIG_IP_NF_RAW=y
CONFIG_IP_NF_NAT=y
CONFIG_NF_NAT=y
CONFIG_IP6_NF_FILTER=y
CONFIG_IP6_NF_MANGLE=y
CONFIG_IP6_NF_TARGET_MASQUERADE=y
CONFIG_IP6_NF_RAW=y
CONFIG_IP6_NF_NAT=y
```

### Storage driver (at least one required)
```
CONFIG_OVERLAY_FS=y                 # Recommended - overlay2 driver
CONFIG_EXT4_FS=y                    # Backing filesystem
CONFIG_EXT4_FS_POSIX_ACL=y
CONFIG_EXT4_FS_SECURITY=y
```

### Security features
```
CONFIG_KEYS=y
CONFIG_SECCOMP=y
CONFIG_SECCOMP_FILTER=y
CONFIG_SECURITY_SELINUX=y           # Android default
CONFIG_POSIX_MQUEUE=y
```

### Optional but recommended
```
CONFIG_CFS_BANDWIDTH=y              # CPU bandwidth control
CONFIG_FAIR_GROUP_SCHED=y
CONFIG_CGROUP_NET_PRIO=y            # Kernel 3.14+
CONFIG_NF_NAT_FTP=y                 # FTP support
CONFIG_NF_CONNTRACK_FTP=y
```

### Android-specific considerations

**Cgroup conflicts:** Android already uses cgroups for power management. You may need to:
- Mount cgroup v2 separately: `mount -t tmpfs cgroup_root /sys/fs/cgroup`
- Use `--cgroupns=private` flag when starting Docker daemon
- Manually configure cgroup subsystems for Docker

**SELinux:** Android enforces SELinux by default. Options:
- Set permissive mode temporarily: `setenforce 0` (reduces security)
- Create custom SELinux policy allowing Docker operations (recommended)

**Runtime requirements:**
```bash
# Must be set after boot
sysctl -w net.ipv4.ip_forward=1
sysctl -w net.ipv6.conf.all.forwarding=1
```

**Verification:** Download and run Docker's check-config.sh script:
```bash
wget https://github.com/moby/moby/raw/master/contrib/check-config.sh
chmod +x check-config.sh
./check-config.sh /path/to/.config
```

All "Generally Necessary" flags must be green, and at least one storage driver must be available.

---

## Kernel source and defconfig details for Raphael

**Exact defconfig location:** `arch/arm64/configs/raphael_defconfig` or `arch/arm64/configs/raphael_user_defconfig`

**Base configuration:** Derives from Qualcomm's sm8150 platform (msm-4.14 kernel from CAF), using CAF tag LA.UM.9.1.r1-xxxx-SMxxx0.QSSI12.0 series.

**Device tree location:** `arch/arm64/boot/dts/qcom/sm8150-xiaomi-raphael.dts`

**How to modify defconfig for custom features:**

1. **Direct editing (simple changes):**
```bash
# Edit defconfig file directly
nano arch/arm64/configs/raphael_defconfig

# Add Docker configs shown above
# Add KernelSU config (CONFIG_KSU=y for manual integration)

# Regenerate config
make O=out ARCH=arm64 raphael_defconfig
```

2. **Using menuconfig (complex changes):**
```bash
export ARCH=arm64 SUBARCH=arm64
make O=out ARCH=arm64 raphael_defconfig
make O=out ARCH=arm64 menuconfig

# Navigate menus to enable features:
# General setup → Namespaces support
# Device Drivers → Network device support
# File systems → Overlay filesystem support

# Save and copy to defconfig
cp out/.config arch/arm64/configs/raphael_defconfig
```

3. **Fragment approach (recommended for Docker + KernelSU):**
```bash
# Create docker.config fragment
cat << EOF > docker.config
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_OVERLAY_FS=y
# ... (all Docker configs)
EOF

# Create kernelsu.config fragment
cat << EOF > kernelsu.config
CONFIG_KSU=y
# CONFIG_KPROBES is not set
EOF

# Merge with base defconfig
./scripts/kconfig/merge_config.sh -O out \
    arch/arm64/configs/raphael_defconfig \
    docker.config \
    kernelsu.config
```

**Device-specific requirements for Raphael:**
- `CONFIG_F2FS_FS=y` - Required for FBEv2 encryption on modern ROMs
- `CONFIG_BUILD_ARM64_DT_OVERLAY=y` - Device tree overlay support
- `CONFIG_MODULE_FORCE_LOAD=y` - Required for WLAN and audio modules

**Known issues to address:**
- Touchscreen driver needs deferred probe fix (uncomment line ~8480 in fts.c)
- Power supply framework may need patches from newer Xiaomi kernels
- FOD (fingerprint on display) requires custom patches not in public sources

---

## Build environment setup: Docker on Intel MacBook Pro

### Recommended Docker image

**Ubuntu 22.04 is optimal** - Ubuntu 24.04 has glibc 2.38 incompatibility issues, while 20.04 is outdated.

**Dockerfile:**
```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    build-essential bc bison flex git gnupg gperf zip curl \
    libssl-dev libelf-dev libncurses5-dev libncursesw5-dev \
    python3 python3-pip python-is-python3 \
    rsync wget cpio unzip device-tree-compiler lz4 xz-utils \
    zlib1g-dev ccache automake liblz4-tool kmod \
    openjdk-11-jdk \
    && rm -rf /var/lib/apt/lists/*

RUN ccache -M 50G

WORKDIR /workspace
```

Build the image:
```bash
docker build -t android-kernel-builder .
```

### Toolchain selection for Raphael (kernel 4.14.x)

**Recommended: AOSP Clang r536225 or newer** (November 2024+)

Download toolchains:
```bash
# AOSP Clang (official)
git clone --depth=1 -b android15-release \
  https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86 \
  toolchains/clang

# GCC for binutils (required alongside Clang)
git clone --depth=1 \
  https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_aarch64_aarch64-linux-android-4.9 \
  toolchains/gcc-aarch64

git clone --depth=1 \
  https://github.com/LineageOS/android_prebuilts_gcc_linux-x86_arm_arm-linux-androideabi-4.9 \
  toolchains/gcc-arm
```

**Alternative: Proton Clang** (community favorite, simpler setup):
```bash
git clone --depth=1 https://github.com/kdrag0n/proton-clang toolchains/proton-clang
```

### Cross-compilation environment variables

```bash
export ARCH=arm64
export SUBARCH=arm64
export CC=clang
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-android-
export CROSS_COMPILE_ARM32=arm-linux-androideabi-

# Update PATH
export PATH="/workspace/toolchains/clang/bin:/workspace/toolchains/gcc-aarch64/bin:/workspace/toolchains/gcc-arm/bin:${PATH}"
```

### Docker run command with macOS optimizations

```bash
docker run -it --rm \
    --name raphael-kernel-build \
    --cpus=12 \
    --memory=24g \
    -v $(pwd)/kernel:/workspace/kernel:cached \
    -v $(pwd)/out:/workspace/out:delegated \
    -v $(pwd)/toolchains:/workspace/toolchains:cached \
    -v ~/.ccache:/root/.ccache:cached \
    -e ARCH=arm64 \
    -e SUBARCH=arm64 \
    -w /workspace/kernel \
    android-kernel-builder \
    /bin/bash
```

**Volume mount flags for macOS performance:**
- `:cached` - Host authoritative (use for source code, toolchains)
- `:delegated` - Container authoritative (use for build outputs)
- Provides significant performance improvement over default `:consistent`

**Critical macOS optimization: Enable VirtioFS**
1. Docker Desktop → Settings → General
2. Check "Use the new Virtualization framework"
3. Experimental Features → Enable "VirtioFS"
4. Restart Docker Desktop
5. **Result:** 3.5x better file I/O performance

### Resource recommendations

| Component | Minimum | Recommended | Optimal |
|-----------|---------|-------------|---------|
| CPU Cores | 4 | 8 | 12+ |
| RAM | 8 GB | 16 GB | 24 GB |
| Disk Space | 50 GB | 100 GB | 200 GB |

**Build time estimates:**
- Initial build: 20-45 minutes
- Incremental rebuild with ccache: 2-5 minutes

---

## Complete compilation process

### Step-by-step kernel compilation

**1. Clone kernel source (for Raphael):**
```bash
# Using SOVIET-ANDROID kernel (recommended)
git clone https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael -b 15.0 kernel
cd kernel
```

**2. Integrate KernelSU (BEFORE compilation):**
```bash
curl -LSs "https://raw.githubusercontent.com/tiann/KernelSU/main/kernel/setup.sh" | bash -s v0.9.5
```

**3. Modify defconfig for Docker + KernelSU:**
```bash
# Open defconfig
nano arch/arm64/configs/raphael_defconfig

# Add at end:
# KernelSU (if using manual integration)
CONFIG_KSU=y

# Docker support
CONFIG_NAMESPACES=y
CONFIG_NET_NS=y
CONFIG_PID_NS=y
CONFIG_IPC_NS=y
CONFIG_UTS_NS=y
CONFIG_USER_NS=y
CONFIG_CGROUPS=y
CONFIG_CGROUP_CPUACCT=y
CONFIG_CGROUP_DEVICE=y
CONFIG_CGROUP_FREEZER=y
CONFIG_CGROUP_SCHED=y
CONFIG_CGROUP_PIDS=y
CONFIG_CPUSETS=y
CONFIG_MEMCG=y
CONFIG_BLK_CGROUP=y
CONFIG_VETH=y
CONFIG_BRIDGE=y
CONFIG_BRIDGE_NETFILTER=y
CONFIG_IP_NF_NAT=y
CONFIG_NF_NAT=y
CONFIG_OVERLAY_FS=y
CONFIG_KEYS=y
CONFIG_SECCOMP=y
CONFIG_SECCOMP_FILTER=y
CONFIG_POSIX_MQUEUE=y
```

**4. Configure kernel:**
```bash
export ARCH=arm64 SUBARCH=arm64
make O=out ARCH=arm64 raphael_defconfig
```

**5. Compile kernel:**
```bash
PATH="${CLANG_PATH}/bin:${GCC_PATH}/bin:${GCC_ARM_PATH}/bin:${PATH}" \
make -j$(nproc) O=out \
    ARCH=arm64 \
    CC=clang \
    CLANG_TRIPLE=aarch64-linux-gnu- \
    CROSS_COMPILE=aarch64-linux-android- \
    CROSS_COMPILE_ARM32=arm-linux-androideabi-
```

**Substitution variables:**
- `${CLANG_PATH}`: `/workspace/toolchains/clang/clang-r536225`
- `${GCC_PATH}`: `/workspace/toolchains/gcc-aarch64`
- `${GCC_ARM_PATH}`: `/workspace/toolchains/gcc-arm`

**6. Verify output:**
```bash
ls -lh out/arch/arm64/boot/Image.gz-dtb
# Should show kernel image file
```

### Packaging with AnyKernel3

**1. Clone AnyKernel3:**
```bash
git clone https://github.com/osm0sis/AnyKernel3
cd AnyKernel3
```

**2. Configure anykernel.sh:**
```bash
nano anykernel.sh

# Edit these properties:
properties() { '
  kernel.string=SOVIET-ANDROID-KernelSU-Docker by YourName
  do.devicecheck=1
  do.modules=1
  do.systemless=1
  device.name1=raphael
  device.name2=raphaelin
  supported.versions=15
'; }

block=boot;
is_slot_device=auto;
ramdisk_compression=auto;
```

**3. Copy kernel image:**
```bash
cp ../kernel/out/arch/arm64/boot/Image.gz-dtb ./
```

**4. Copy kernel modules (if any):**
```bash
mkdir -p modules/system/lib/modules
find ../kernel/out -name "*.ko" -exec cp {} modules/system/lib/modules/ \;
```

**5. Create flashable ZIP:**
```bash
zip -r9 SOVIET-ANDROID-KernelSU-Docker-v1.0.zip * -x .git README.md *placeholder
```

### Flashing procedures

**Method 1: TWRP/OrangeFox (recommended for testing):**
```bash
# Transfer to device
adb push SOVIET-ANDROID-KernelSU-Docker-v1.0.zip /sdcard/

# Reboot to recovery
adb reboot recovery

# In recovery: Install → Select ZIP → Flash
# Reboot
```

**Method 2: Fastboot (for testing boot.img):**
```bash
# Test boot FIRST (non-permanent)
adb reboot bootloader
fastboot boot boot.img

# If successful, flash permanently
fastboot flash boot boot.img
fastboot reboot
```

**Method 3: ADB Sideload:**
```bash
adb reboot recovery
# In recovery: Advanced → ADB Sideload
adb sideload SOVIET-ANDROID-KernelSU-Docker-v1.0.zip
```

### Verification steps

**1. Check device boots:**
```bash
adb devices
adb shell uname -r
# Should show your custom kernel version
```

**2. Verify KernelSU:**
```bash
# Install KernelSU Manager
adb install KernelSU_Manager.apk

# Check root access
adb shell su -v
# Should output: KernelSU version

adb shell su -c "echo Root works"
# Should output: Root works
```

**3. Verify Docker support:**
```bash
# Check kernel configs
adb shell "zcat /proc/config.gz | grep -E 'CONFIG_NAMESPACES|CONFIG_OVERLAY_FS|CONFIG_VETH'"

# Should show:
# CONFIG_NAMESPACES=y
# CONFIG_OVERLAY_FS=y
# CONFIG_VETH=y
```

**4. Test hardware functionality:**
```bash
# WiFi
adb shell "svc wifi enable && ping -c 4 8.8.8.8"

# Bluetooth
adb shell "svc bluetooth enable"

# Display
# Check screen functions normally

# Fingerprint
# Test fingerprint unlock
```

---

## Stability considerations and recommendations

### Known stable kernel configuration for Raphael Android 15

**Base kernel:** SOVIET-ANDROID kernel_xiaomi_raphael, branch 15.0
- Version: Linux 4.14.343 (latest upstream from OpenELA)
- CAF tag: LA.UM.9.1.r1-16000-SMxxx0.QSSI14.0
- Compiler: Neutron Clang 19.x with O3 optimization

**Recommended commits/patches:**
1. Latest android-4.14-stable merged (security patches)
2. EEVDF scheduler backports (performance)
3. Power supply framework fixes from sm8450 kernel
4. Touchscreen deferred probe fix
5. F2FS updates from jaegeuk/f2fs-stable (FBEv2 support)

### Common pitfalls when adding Docker + KernelSU

**Pitfall 1: Kernel size explosion**
- Docker configs + KernelSU add significant size
- **Solution:** Disable unused features, use LZ4 compression

**Pitfall 2: SELinux denials**
- Docker requires privileged operations
- **Solution:** Set permissive during testing: `setenforce 0` (boot argument: `androidboot.selinux=permissive`)

**Pitfall 3: cgroup conflicts**
- Android's cgroup usage conflicts with Docker
- **Solution:** Use cgroup v2 or separate mount points

**Pitfall 4: Module loading failures**
- WLAN/audio modules may fail to load
- **Solution:** Enable `CONFIG_MODULE_FORCE_LOAD=y`

**Pitfall 5: Bootloop from KernelSU**
- kprobe may not work on all devices
- **Solution:** Test kprobe method first; if bootloop, use manual integration

### Testing methodology

**Phase 1: Compilation verification**
```bash
# Check build succeeded
ls -lh out/arch/arm64/boot/Image.gz-dtb

# Check KernelSU integrated
strings out/arch/arm64/boot/Image | grep -i kernelsu
```

**Phase 2: Boot testing**
```bash
# ALWAYS test boot before permanent flash
fastboot boot boot.img

# If boots successfully, proceed to full flash
```

**Phase 3: Functional testing**
- Boot to system (5-10 minutes)
- Test WiFi, Bluetooth, mobile data
- Test fingerprint sensor, display
- Test camera, sensors
- Test charging, battery drain
- Run for 24 hours minimum

**Phase 4: KernelSU testing**
- Install KernelSU Manager
- Grant root to terminal app
- Test root commands
- Install root-requiring module

**Phase 5: Docker testing**
```bash
# Install Docker (Termux or similar)
pkg install docker

# Start Docker daemon
dockerd &

# Test basic container
docker run hello-world

# Test with resource limits
docker run --memory=512m --cpus=1 ubuntu:latest echo "Success"
```

### Recommended stable configuration summary

**For maximum stability on Raphael:**
- Base: SOVIET-ANDROID kernel 15.0 branch
- KernelSU: v0.9.5 with kprobe method (test first)
- Docker: Enable only required configs, not optional ones
- Compiler: AOSP Clang r536225+ or Neutron Clang 19.x
- Optimization: O2 (O3 may cause instability)
- Disable: `CONFIG_WERROR` (to avoid build failures)
- Enable: `CONFIG_MODULE_FORCE_LOAD=y` (for WLAN/audio)

**Common stable flags:**
```
CONFIG_CC_OPTIMIZE_FOR_PERFORMANCE=y    # Not O3
# CONFIG_DEBUG_INFO is not set
CONFIG_MODULE_SIG=n                      # Disable module signatures
CONFIG_MODVERSIONS=n
```

---

## Complete build script example

Save as `build.sh` in kernel directory:

```bash
#!/bin/bash
set -e

# Configuration
KERNEL_DIR=$(pwd)
OUT_DIR=${KERNEL_DIR}/out
CLANG_PATH=/workspace/toolchains/clang/clang-r536225
GCC_PATH=/workspace/toolchains/gcc-aarch64
GCC_ARM_PATH=/workspace/toolchains/gcc-arm
DEVICE=raphael
JOBS=$(nproc)

# Environment
export ARCH=arm64
export SUBARCH=arm64
export CC=clang
export CLANG_TRIPLE=aarch64-linux-gnu-
export CROSS_COMPILE=aarch64-linux-android-
export CROSS_COMPILE_ARM32=arm-linux-androideabi-
export PATH="${CLANG_PATH}/bin:${GCC_PATH}/bin:${GCC_ARM_PATH}/bin:${PATH}"

# ccache
export CCACHE_DIR=/root/.ccache
export USE_CCACHE=1

echo "================================"
echo "Kernel Build Script for Raphael"
echo "================================"
echo "Kernel: $(pwd)"
echo "Output: ${OUT_DIR}"
echo "Jobs: ${JOBS}"
echo "================================"

# Clean (optional)
echo "Cleaning old build..."
make O=${OUT_DIR} mrproper 2>/dev/null || true

# Configure
echo "Configuring kernel..."
make O=${OUT_DIR} ARCH=arm64 ${DEVICE}_defconfig

# Build
echo "Building kernel..."
time make -j${JOBS} O=${OUT_DIR} \
    ARCH=arm64 \
    CC=clang \
    CLANG_TRIPLE=aarch64-linux-gnu- \
    CROSS_COMPILE=aarch64-linux-android- \
    CROSS_COMPILE_ARM32=arm-linux-androideabi-

# Verify output
if [ -f "${OUT_DIR}/arch/arm64/boot/Image.gz-dtb" ]; then
    echo "================================"
    echo "Build completed successfully!"
    echo "Kernel: ${OUT_DIR}/arch/arm64/boot/Image.gz-dtb"
    echo "Size: $(du -h ${OUT_DIR}/arch/arm64/boot/Image.gz-dtb | cut -f1)"
    echo "================================"
else
    echo "Build failed! Kernel image not found."
    exit 1
fi

# Package with AnyKernel3 (optional)
if [ -d "../AnyKernel3" ]; then
    echo "Packaging with AnyKernel3..."
    cd ../AnyKernel3
    cp ${OUT_DIR}/arch/arm64/boot/Image.gz-dtb ./
    zip -r9 SOVIET-KernelSU-Docker-$(date +%Y%m%d).zip * -x .git README.md *placeholder
    echo "Flashable ZIP: $(pwd)/SOVIET-KernelSU-Docker-$(date +%Y%m%d).zip"
fi
```

Make executable:
```bash
chmod +x build.sh
./build.sh
```

---

## Quick reference: Complete workflow checklist

### Pre-build checklist
- [ ] Docker Desktop installed with VirtioFS enabled
- [ ] Built android-kernel-builder Docker image
- [ ] Downloaded toolchains (Clang + GCC)
- [ ] Cloned kernel source (SOVIET-ANDROID recommended)
- [ ] Backed up stock boot.img

### Build checklist
- [ ] Integrated KernelSU v0.9.5 before first compilation
- [ ] Modified defconfig with Docker + KernelSU configs
- [ ] Ran `make raphael_defconfig`
- [ ] Compiled kernel with proper cross-compilation flags
- [ ] Verified Image.gz-dtb output exists

### Packaging checklist
- [ ] Cloned AnyKernel3
- [ ] Configured anykernel.sh for Raphael
- [ ] Copied kernel image and modules
- [ ] Created flashable ZIP

### Flashing checklist
- [ ] Transferred ZIP to device
- [ ] Booted to TWRP/OrangeFox recovery
- [ ] Made TWRP backup of current boot
- [ ] Flashed kernel ZIP
- [ ] Rebooted to system

### Verification checklist
- [ ] Device boots to system successfully
- [ ] Checked kernel version with `adb shell uname -r`
- [ ] Installed KernelSU Manager, verified root works
- [ ] Tested WiFi, Bluetooth, fingerprint, camera
- [ ] Verified Docker configs with zcat /proc/config.gz
- [ ] Ran device for 24+ hours for stability testing

---

## Critical final notes

**IMPORTANT WARNINGS:**
1. **Always backup** your stock boot.img before flashing
2. **Test with `fastboot boot`** before permanent flash
3. Raphael uses kernel **4.14.x**, which is NON-GKI
4. KernelSU **v0.9.5 ONLY** for kernel 4.14.x (no upgrades possible)
5. Docker on Android is **experimental** - expect issues with cgroups and SELinux

**Success indicators:**
- Device boots to system within 2 minutes
- KernelSU Manager shows "Installed" status
- `adb shell su -c id` returns `uid=0(root)`
- All hardware functions work normally
- No random reboots or thermal issues

**If something goes wrong:**
```bash
# Emergency recovery
adb reboot bootloader
fastboot flash boot stock_boot_backup.img
fastboot reboot
```

**Key repositories:**
- Kernel source: https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael
- KernelSU: https://github.com/tiann/KernelSU
- AnyKernel3: https://github.com/osm0sis/AnyKernel3
- Evolution X ROM: https://evolution-x.org/devices/raphael

This comprehensive plan provides everything needed to compile a stable Android 15 kernel for Raphael with KernelSU v0.9.5 and Docker support, optimized for compilation on Intel MacBook Pro using Docker containers. The configuration prioritizes maximum stability while enabling both root management through KernelSU and containerization through Docker.