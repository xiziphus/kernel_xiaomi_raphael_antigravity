# Technical Deep Dive: Android Kernel Boot Process & Encryption

This document provides technical details about Android boot process, encryption, and kernel compilation for advanced users and developers.

## Table of Contents
1. [Android Boot Sequence](#android-boot-sequence)
2. [File-Based Encryption (FBE)](#file-based-encryption-fbe)
3. [Boot Image Structure](#boot-image-structure)
4. [Kernel Configuration System](#kernel-configuration-system)
5. [Docker Requirements](#docker-requirements)

---

## Android Boot Sequence

### Boot Chain
```
Power On
  ↓
Bootloader (ABL - Android Boot Loader)
  ↓
Loads boot.img from boot partition
  ↓
Verifies boot image (AVB - Android Verified Boot)
  ↓
Extracts kernel + ramdisk
  ↓
Kernel starts (init process)
  ↓
Mounts system partitions
  ↓
Decrypts /data (if encrypted)
  ↓
Starts Android framework
```

### Critical Boot Parameters

**Kernel Command Line** (`cmdline`):
```
console=null                          # Disable console output
androidboot.hardware=qcom             # Hardware platform
androidboot.usbcontroller=a600000.dwc3  # USB controller
androidboot.boot_devices=soc/1d84000.ufshc  # Boot device
service_locator.enable=1              # Service locator
lpm_levels.sleep_disabled=1           # Low power mode
loop.max_part=16                      # Loop device partitions
androidboot.init_fatal_reboot_target=recovery  # Crash recovery
kpti=off                              # Kernel page-table isolation
swiotlb=1                             # Software I/O TLB
androidboot.super_partition=system    # Super partition name
```

**Memory Layout**:
```
Base Address:     0x10000000
Kernel Offset:    0x00008000  → Kernel loads at 0x10008000
Ramdisk Offset:   0x01000000  → Ramdisk loads at 0x11000000
Tags Offset:      0x00000100  → Device tree at 0x10000100
```

---

## File-Based Encryption (FBE)

### How FBE Works

Android uses File-Based Encryption to protect user data. Each file is encrypted with a unique key.

#### Key Derivation Process
```
Master Key = PBKDF2(
    password,
    salt,
    iterations,
    hardware_id,
    os_patch_level  ← CRITICAL!
)
```

#### Why OS Patch Level Matters

The OS patch level is part of the encryption key derivation. If it changes:
1. New key is derived
2. Old key is lost
3. Encrypted data becomes inaccessible
4. System shows "corrupt data" error

**Example**:
```
Stock boot:    os_patch_level = 2025-10
Custom boot:   os_patch_level = 2000-00  (default)
Result:        Different keys → Can't decrypt → Data "corrupt"
```

#### Verification
```bash
# Check current patch level
adb shell getprop ro.build.version.security_patch
# Output: 2025-10-05

# Extract from boot image
python3 unpack_boot.py boot.img
cat boot_params.txt | grep "OS Patch Level"
# Output: OS Patch Level: 2025-10
```

### Keymaster & TEE

Android uses a Trusted Execution Environment (TEE) for key storage:
```
User enters password
  ↓
Android derives key (using patch level)
  ↓
Sends to Keymaster (in TEE)
  ↓
Keymaster verifies:
  - Patch level matches
  - Boot state is valid
  - No rollback detected
  ↓
If OK: Release decryption keys
If NOT: Refuse → "Corrupt data"
```

---

## Boot Image Structure

### Boot Image Header (Version 0)

```c
struct boot_img_hdr {
    uint8_t  magic[8];           // "ANDROID!"
    uint32_t kernel_size;        // Size of kernel
    uint32_t kernel_addr;        // Physical load addr
    uint32_t ramdisk_size;       // Size of ramdisk
    uint32_t ramdisk_addr;       // Physical load addr
    uint32_t second_size;        // Size of second stage
    uint32_t second_addr;        // Physical load addr
    uint32_t tags_addr;          // Physical addr for tags
    uint32_t page_size;          // Flash page size (4096)
    uint32_t header_version;     // 0, 1, 2, 3, or 4
    uint32_t os_version;         // OS version
    uint32_t os_patch_level;     // YYYY-MM format
    uint8_t  name[16];           // Product name
    uint8_t  cmdline[512];       // Kernel command line
    uint32_t id[8];              // SHA1 hash
    uint8_t  extra_cmdline[1024]; // Extra cmdline
};
```

### Layout on Disk
```
[Header - 1 page]
[Kernel - N pages]
[Ramdisk - M pages]
[Second stage - P pages] (optional)
[Recovery DTBO - Q pages] (optional, header v1+)
[DTB - R pages] (optional, header v2+)
```

### Extracting Boot Image

```python
# Simplified extraction logic
with open('boot.img', 'rb') as f:
    header = f.read(2048)  # First page
    
    # Parse header
    magic = header[0:8]  # Should be b'ANDROID!'
    kernel_size = struct.unpack('<I', header[8:12])[0]
    ramdisk_size = struct.unpack('<I', header[16:20])[0]
    page_size = struct.unpack('<I', header[36:40])[0]
    os_patch_level = struct.unpack('<I', header[44:48])[0]
    
    # Decode patch level
    year = ((os_patch_level >> 4) & 0x7F) + 2000
    month = os_patch_level & 0x0F
    print(f"Patch Level: {year}-{month:02d}")
    
    # Extract kernel
    f.seek(page_size)  # Skip header
    kernel = f.read(kernel_size)
    
    # Extract ramdisk
    kernel_pages = (kernel_size + page_size - 1) // page_size
    f.seek(page_size * (1 + kernel_pages))
    ramdisk = f.read(ramdisk_size)
```

---

## Kernel Configuration System

### Kconfig Hierarchy

The kernel uses Kconfig for configuration management:

```
Kconfig (root)
  ├── arch/arm64/Kconfig
  ├── init/Kconfig
  │   ├── NAMESPACES
  │   │   ├── UTS_NS
  │   │   ├── IPC_NS
  │   │   ├── USER_NS  ← Depends on NAMESPACES
  │   │   └── PID_NS   ← Depends on NAMESPACES
  │   └── CGROUPS
  │       ├── CGROUP_PIDS  ← Depends on CGROUPS
  │       └── CGROUP_DEVICE
  └── ...
```

### Dependency Resolution

**Example**: Enabling `USER_NS`

```kconfig
config USER_NS
    bool "User namespace"
    depends on NAMESPACES
    default n
```

If you enable `USER_NS` but `NAMESPACES` is disabled:
```bash
scripts/config --enable USER_NS
make olddefconfig
# Result: USER_NS gets disabled because NAMESPACES is off
```

**Correct approach**:
```bash
scripts/config --enable NAMESPACES
scripts/config --enable USER_NS
make olddefconfig
# Result: Both stay enabled
```

### Config Fragment Merging

**Using merge_config.sh** (recommended):
```bash
# Create fragment
cat > docker.config << EOF
CONFIG_NAMESPACES=y
CONFIG_USER_NS=y
CONFIG_PID_NS=y
EOF

# Merge it
scripts/kconfig/merge_config.sh -m -O out out/.config docker.config

# This handles dependencies automatically
```

### Verification Hierarchy

Three sources of configuration truth:

1. **`.config`** - Build configuration (can be stale)
2. **`autoconf.h`** - Generated C headers (actual build)
3. **`/proc/config.gz`** - Embedded in kernel (can be stale)

**Trust order**: `autoconf.h` > `.config` > `/proc/config.gz`

```bash
# Most reliable
grep CONFIG_USER_NS out/include/generated/autoconf.h
# #define CONFIG_USER_NS 1  ← This is what was actually compiled

# Less reliable
grep CONFIG_USER_NS out/.config
# CONFIG_USER_NS=y  ← This is what was requested

# Least reliable
zcat /proc/config.gz | grep CONFIG_USER_NS
# # CONFIG_USER_NS is not set  ← This might be outdated
```

---

## Docker Requirements

### Kernel Features Required

#### Namespaces
```
CONFIG_NAMESPACES=y        # Master switch
CONFIG_UTS_NS=y            # Hostname isolation
CONFIG_IPC_NS=y            # IPC isolation
CONFIG_USER_NS=y           # User ID isolation
CONFIG_PID_NS=y            # Process ID isolation
CONFIG_NET_NS=y            # Network isolation
```

#### Control Groups (cgroups)
```
CONFIG_CGROUPS=y           # Master switch
CONFIG_CGROUP_PIDS=y       # Process limit controller
CONFIG_CGROUP_DEVICE=y     # Device access controller
CONFIG_CGROUP_FREEZER=y    # Freeze/thaw controller
CONFIG_MEMCG=y             # Memory controller
CONFIG_CPUSETS=y           # CPU/memory node controller
```

#### Filesystems
```
CONFIG_OVERLAY_FS=y        # OverlayFS (for layers)
CONFIG_EXT4_FS=y           # Ext4 support
CONFIG_PROC_FS=y           # /proc filesystem
CONFIG_SYSFS=y             # /sys filesystem
```

#### Networking
```
CONFIG_VETH=y              # Virtual Ethernet pairs
CONFIG_BRIDGE=y            # Network bridging
CONFIG_IP_NF_NAT=y         # NAT support
CONFIG_IP_NF_TARGET_MASQUERADE=y  # IP masquerading
CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y
CONFIG_NETFILTER_XT_MATCH_IPVS=y
```

### Testing Docker Support

#### Manual Container Creation

```bash
# Test namespaces
unshare --user --pid --net --mount --fork sh
# If this works, namespaces are functional

# Test cgroups
mount -t cgroup -o pids none /sys/fs/cgroup/pids
# If this works, PIDs cgroup is functional

# Test OverlayFS
mount -t overlay overlay \
  -o lowerdir=/lower,upperdir=/upper,workdir=/work \
  /merged
# If this works, OverlayFS is functional
```

#### Verification Script

```bash
#!/bin/bash
echo "=== Docker Kernel Feature Check ==="

# Check namespaces
for ns in user pid net uts ipc; do
    if [ -e /proc/self/ns/$ns ]; then
        echo "✓ ${ns} namespace"
    else
        echo "✗ ${ns} namespace MISSING"
    fi
done

# Check cgroups
for cg in pids memory devices freezer; do
    if grep -q "^$cg" /proc/cgroups; then
        echo "✓ ${cg} cgroup"
    else
        echo "✗ ${cg} cgroup MISSING"
    fi
done

# Check filesystems
for fs in overlay ext4 proc sysfs; do
    if grep -q "$fs" /proc/filesystems; then
        echo "✓ ${fs} filesystem"
    else
        echo "✗ ${fs} filesystem MISSING"
    fi
done
```

### Android-Specific Limitations

#### PIE Enforcement

Android enforces Position Independent Executables (PIE) for security:

```c
// Kernel checks ELF header
if (elf_header->e_type == ET_EXEC) {  // Type 2
    // Reject: Static executable
    return -ENOEXEC;
}
if (elf_header->e_type == ET_DYN) {   // Type 3
    // Accept: PIE executable
    return 0;
}
```

**Impact on Docker**:
- `runc` is statically linked → Type 2 → Rejected
- `crun` (prebuilt) is statically linked → Type 2 → Rejected
- Need PIE-compiled runtime → Type 3 → Accepted

#### SELinux Policies

Android's SELinux can block container operations:

```bash
# Check SELinux status
getenforce
# Enforcing

# Check denials
dmesg | grep avc
# avc: denied { ... } for comm="runc" ...
```

**Workarounds**:
- Add custom SELinux policies
- Use `setenforce 0` (not recommended for production)
- Run in permissive domain

---

## Build Optimizations

### ccache

Compiler cache speeds up rebuilds:

```bash
export USE_CCACHE=1
export CCACHE_DIR=/tmp/ccache
export CCACHE_MAXSIZE=50G

# First build: ~15 minutes
# Rebuild with ccache: ~3 minutes (80% faster)
```

### tmpfs

RAM disk for build artifacts:

```bash
# Mount tmpfs
mount -t tmpfs -o size=4G tmpfs /tmp/build

# Build to tmpfs
make O=/tmp/build -j$(nproc)

# Result: 2-3x faster I/O
```

### Parallel Compilation

```bash
# Use all CPU cores
make -j$(nproc)

# Or specify count
make -j16

# Monitor CPU usage
htop  # Should see 1000%+ CPU usage
```

---

## References

- [Android Boot Image Header](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
- [File-Based Encryption](https://source.android.com/docs/security/features/encryption/file-based)
- [Kernel Kconfig Language](https://www.kernel.org/doc/html/latest/kbuild/kconfig-language.html)
- [Docker Kernel Requirements](https://github.com/moby/moby/blob/master/contrib/check-config.sh)
