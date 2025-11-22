# Release v1.0.0 - Docker-Enabled Kernel for Redmi K20 Pro (Android 16)

## Overview

> [!WARNING]
> **This project is not actively maintained.** It is provided as-is for educational purposes and as a foundation for others to build upon.

This is the first stable release of a Docker-enabled custom kernel for the Xiaomi Redmi K20 Pro (raphael) running Android 16 (Baklava).

## Testing Environment

- **Device**: Redmi K20 Pro (raphael)
- **ROM**: Evolution X Android 16
- **Root Method**: Magisk
- **KernelSU**: Code included but tested with Magisk instead

## What's Included

### Kernel Image
- **File**: `boot-raphael-docker-v1.0.img`
- **Size**: ~14 MB
- **Base**: SOVIET-ANDROID kernel 4.14.353-openela
- **Toolchain**: Android Clang 18.0.1 (r522817)

### Features
✅ **Full Docker Kernel Support**
- User Namespaces (CONFIG_USER_NS)
- PID Namespaces (CONFIG_PID_NS)
- Cgroup PIDs Controller
- OverlayFS
- VETH Networking
- Bridge Networking
- IP Masquerading

✅ **KernelSU Support** - KernelSU code included (tested with Magisk)

✅ **Encryption Compatible** - Proper OS patch level (2025-10)

✅ **Stable** - Based on stock kernel source

## Installation

### Quick Install
```bash
# Backup current boot (recommended)
adb reboot bootloader
fastboot getvar current-slot

# Flash the kernel
fastboot flash boot boot-raphael-docker-v1.0.img
fastboot reboot
```

### Verification
After booting, verify Docker support:
```bash
adb shell su -c "cat /proc/cgroups | grep pids"
adb shell su -c "ls -l /proc/self/ns/user"
```

Both commands should show the features are present.

## Known Limitations

### Docker Runtime Compatibility
The kernel has **full Docker support**, but Android's security model (PIE enforcement) blocks standard container runtimes like `runc` and `crun`.

**Status**: Kernel features ✅ Working | Userspace runtime ⚠️ Blocked

**Workarounds**:
- Use PIE-compiled container runtime
- Use alternative containerization (LXC, systemd-nspawn)
- Rootless Podman (if available)

This is a **userspace limitation**, not a kernel issue.

## Changelog

### Added
- Initial Docker-enabled kernel release
- All Docker namespace and cgroup features
- KernelSU support
- Encryption compatibility fix

### Fixed
- Bootloop issues (switched to stock kernel source)
- "Corrupt data" error (added OS patch level)
- Config merging reliability (using merge_config.sh)

## Technical Details

**Kernel Version**: 4.14.353-openela-SOVIET-STAR  
**Build Date**: November 22, 2025  
**Commit**: [Link to commit]  
**Config**: See `docker.config` for enabled flags

## Verification Results

- ✅ Device boots successfully on Evolution X Android 16
- ✅ Encryption working
- ✅ Magisk root working
- ✅ User namespaces verified
- ✅ PIDs cgroup verified
- ✅ Manual unshare test passed
- ⚠️ Docker runtime blocked (Android PIE enforcement)

## Maintenance Status

⚠️ **This project is not actively maintained.**

This kernel was tested on a single device configuration (Redmi K20 Pro + Evolution X Android 16 + Magisk). It is provided as-is for educational purposes and as a foundation for others to build upon.

Feel free to fork and continue development. Pull requests are welcome but may not be reviewed promptly.

## Rollback

If you experience issues:
```bash
fastboot flash boot boot_backup.img
fastboot reboot
```

## Support

- **Issues**: [GitHub Issues](../../issues)
- **Discussions**: [GitHub Discussions](../../discussions)
- **Documentation**: See [README.md](../README.md) and [BUILD.md](../BUILD.md)

## Credits

- Kernel Source: [SOVIET-ANDROID](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael)
- Toolchain: Android Clang 18.0.1
- Build Tools: AOSP mkbootimg

## Disclaimer

⚠️ **Use at your own risk**. Always keep a backup of your stock boot image.

---

**SHA256 Checksums**:
```
[To be filled with actual checksums]
boot-raphael-docker-v1.0.img: [checksum]
Image.gz-dtb: [checksum]
```
