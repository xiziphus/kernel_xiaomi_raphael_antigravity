# Redmi K20 Pro Docker Kernel (Android 16)

> [!WARNING]
> **This project is not actively maintained.** It is provided as-is for educational purposes and as a foundation for others to build upon. Feel free to fork and continue development.

Custom kernel for Xiaomi Redmi K20 Pro (raphael) with Docker support, compatible with Android 16 (Baklava).

## Features

- ✅ **Full Docker Support**: All required kernel features enabled
  - User Namespaces (`USER_NS`)
  - PID Namespaces (`PID_NS`)
  - Cgroup PIDs controller
  - OverlayFS
  - VETH networking
  - Bridge networking
  - IP Masquerading
- ✅ **KernelSU Support**: KernelSU code included (can be used with Magisk or KernelSU)
- ✅ **Stable**: Based on stock SOVIET-ANDROID kernel (4.14.353-openela)
- ✅ **Encryption Compatible**: Properly configured for Android 16 FBE

## Device Compatibility

- **Device**: Xiaomi Redmi K20 Pro (raphael)
- **Android Version**: Android 16 (Baklava) - Evolution X ROM
- **Kernel Version**: 4.14.353-openela-SOVIET-STAR
- **Architecture**: ARM64 (aarch64)
- **Root**: Tested with Magisk (KernelSU code included but not tested)

## Testing Status

This kernel has been tested on:
- **Device**: Redmi K20 Pro (raphael)
- **ROM**: Evolution X Android 16
- **Root Method**: Magisk
- **Status**: ✅ Boots successfully, encryption working, Docker kernel features verified

## Installation

### Prerequisites
- Unlocked bootloader
- ADB and Fastboot installed
- Backup of your current boot partition (recommended)

### Steps

1. **Download the latest release**
   - Get `boot-raphael-docker-v1.0.img` from [Releases](../../releases)

2. **Backup your current boot** (optional but recommended)
   ```bash
   adb reboot bootloader
   fastboot getvar current-slot  # Note your active slot (a or b)
   fastboot boot boot-raphael-docker-v1.0.img  # Test boot first
   ```

3. **Flash the kernel**
   ```bash
   adb reboot bootloader
   fastboot flash boot boot-raphael-docker-v1.0.img
   fastboot reboot
   ```

## Docker Setup (Known Limitation)

### Kernel Support: ✅ Complete
The kernel has **all** Docker features enabled and working:
- Verified via `/proc/cgroups` (PIDs controller present)
- Verified via `/proc/self/ns/user` (User namespaces working)
- Verified via manual `unshare` tests

### Userspace Runtime: ⚠️ Compatibility Issue
Android's security model (ASLR/PIE enforcement) rejects statically-linked container runtimes like `runc` and `crun`.

**Error**: `unexpected e_type: 2` (non-PIE binary rejected)

**Workarounds**:
1. Use rootless Podman (if available for Termux)
2. Compile a PIE-compatible `crun` binary
3. Use alternative containerization (LXC, systemd-nspawn)

This is a **userspace limitation**, not a kernel issue. The kernel is fully Docker-ready.

## Building from Source

### Requirements
- Docker (for build environment)
- macOS or Linux host
- 60GB+ free disk space
- Android Clang 18.0.1 toolchain

### Build Steps

1. **Clone the kernel source**
   ```bash
   git clone https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael
   cd kernel_xiaomi_raphael
   ```

2. **Download toolchain**
   ```bash
   # Download Android Clang 18.0.1 (r522817)
   # https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/
   ```

3. **Run the build**
   ```bash
   ./run_builder_soviet.sh
   ```

4. **Repack the boot image**
   ```bash
   python3 mkbootimg_src/mkbootimg.py \
     --kernel out/arch/arm64/boot/Image.gz-dtb \
     --ramdisk stock_kernel_extracted/ramdisk.cpio.gz \
     --cmdline "console=null androidboot.hardware=qcom ..." \
     --base 0x10000000 \
     --pagesize 4096 \
     --os_version 0 \
     --os_patch_level 2025-10 \
     --output boot.img
   ```

See [BUILD.md](BUILD.md) for detailed instructions.

## Technical Details

### Enabled Kernel Configs
```
CONFIG_NAMESPACES=y
CONFIG_USER_NS=y
CONFIG_PID_NS=y
CONFIG_NET_NS=y
CONFIG_CGROUPS=y
CONFIG_CGROUP_PIDS=y
CONFIG_CGROUP_DEVICE=y
CONFIG_MEMCG=y
CONFIG_OVERLAY_FS=y
CONFIG_VETH=y
CONFIG_BRIDGE=y
CONFIG_IP_NF_TARGET_MASQUERADE=y
CONFIG_KSU=y
```

### Boot Parameters
- **OS Patch Level**: 2025-10 (critical for encryption)
- **Page Size**: 4096
- **Base Address**: 0x10000000
- **Kernel Offset**: 0x00008000
- **Ramdisk Offset**: 0x01000000

## Troubleshooting

### "Corrupt Data" Error
This was caused by missing `os_patch_level` in the boot image header. The released kernel has this fixed.

### Bootloop
If you experience a bootloop:
1. Reboot to fastboot: `fastboot reboot bootloader`
2. Flash your backup: `fastboot flash boot boot_backup.img`
3. Report the issue with logs

### Docker Runtime Error
See the "Docker Setup" section above. This is a known Android security limitation, not a kernel bug.

## Maintenance Status

⚠️ **This project is not actively maintained.**

This kernel was created as a proof-of-concept and tested on a single device (Redmi K20 Pro running Evolution X Android 16 with Magisk root). It is provided as-is for:
- Educational purposes
- A foundation for others to build upon
- Reference implementation for Docker kernel features on Android 16

Feel free to fork this repository and continue development. Pull requests are welcome but may not be reviewed promptly.

## Credits

- **Kernel Source**: [SOVIET-ANDROID/kernel_xiaomi_raphael](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael)
- **Toolchain**: Android Clang 18.0.1 (r522817)
- **Build Tools**: mkbootimg from AOSP

## License

This project follows the same license as the upstream kernel source (GPL-2.0).

## Disclaimer

⚠️ **Use at your own risk**. Flashing custom kernels can potentially brick your device. Always keep a backup of your stock boot image.

---

**Maintained by**: [Your GitHub Username]  
**Last Updated**: November 2025
