# Frequently Asked Questions (FAQ)

## General Questions

### Q: What is this project?
**A**: This is a Docker-enabled custom kernel for the Redmi K20 Pro (raphael) running Android 16. It includes all necessary kernel features for Docker containers, along with comprehensive build documentation.

### Q: Is this project actively maintained?
**A**: No, this project is provided as-is for educational purposes and as a foundation for others to build upon. It was tested on a single device configuration and is not actively maintained. Pull requests are welcome but may not be reviewed promptly.

### Q: Do I need programming experience to use this?
**A**: No programming experience is needed to flash the pre-built kernel. However, if you want to modify or rebuild it, basic command-line knowledge is helpful. See the [Beginner's Guide](BEGINNERS_GUIDE.md) for step-by-step instructions.

---

## Compatibility Questions

### Q: Will this work on my device?
**A**: This kernel is **specifically for Redmi K20 Pro (raphael)** only. It will NOT work on:
- Redmi K20 (non-Pro) - different SoC
- Other Xiaomi devices
- Other brands

However, the build process and documentation can be adapted for other Snapdragon 855 devices.

### Q: What ROM do I need?
**A**: This kernel was tested on **Evolution X Android 16**. It should work on other Android 16 ROMs for raphael, but compatibility is not guaranteed. The kernel is based on the SOVIET-ANDROID source, so ROMs using that kernel base are most likely to work.

### Q: Can I use this with MIUI?
**A**: Possibly, but untested. MIUI may have different kernel requirements. Proceed with caution and keep a backup.

### Q: Does this work with Android 15 or earlier?
**A**: No, this is specifically for Android 16. The OS patch level and other parameters are configured for Android 16.

---

## Root & Security Questions

### Q: Do I need root to flash this kernel?
**A**: No, you only need an **unlocked bootloader**. Root is not required for flashing, but you'll need root (Magisk or KernelSU) to use Docker features.

### Q: Does this include KernelSU?
**A**: The KernelSU code is included in the kernel, but it was **not tested**. This kernel was tested with **Magisk** for root access. You can try KernelSU, but it may or may not work.

### Q: Will this void my warranty?
**A**: Unlocking the bootloader (required for custom kernels) typically voids manufacturer warranty. Check with your device manufacturer.

### Q: Is this safe?
**A**: As safe as any custom kernel. It's based on the stock SOVIET-ANDROID source with minimal changes (Docker features added). However, **always keep a backup** of your stock boot image.

---

## Docker Questions

### Q: Can I run Docker containers with this kernel?
**A**: The kernel has **all Docker features enabled**, but there's a userspace limitation: Android's PIE (Position Independent Executable) enforcement blocks standard Docker runtimes like `runc` and `crun`.

**Status**:
- ✅ Kernel features: Working
- ⚠️ Docker runtime: Blocked by Android security

See [JOURNEY.md](JOURNEY.md#final-status) for details.

### Q: Why can't I run `docker run hello-world`?
**A**: The Docker daemon (`dockerd`) works fine, but the container runtime (`runc`/`crun`) is rejected because it's a statically-linked binary (non-PIE). Android 16 enforces PIE for security.

**Error**: `unexpected e_type: 2`

**Workarounds**:
- Compile a PIE-compatible `crun` binary
- Use alternative containerization (LXC, systemd-nspawn)
- Use rootless Podman (if available)

### Q: What Docker features are confirmed working?
**A**: All kernel-level features:
- ✅ User namespaces (`/proc/self/ns/user` exists)
- ✅ PID namespaces
- ✅ Cgroup PIDs controller (`/proc/cgroups` shows `pids`)
- ✅ OverlayFS
- ✅ VETH networking
- ✅ Bridge networking
- ✅ Manual container creation with `unshare`

### Q: Can someone fix the Docker runtime issue?
**A**: Yes! The solution is to compile `crun` or `runc` with PIE flags (`-fPIE -pie`). This is a userspace issue, not a kernel limitation. Contributions welcome!

---

## Build Questions

### Q: How long does the build take?
**A**: 10-20 minutes on a modern computer with 16 CPU cores. First build is slower; rebuilds with ccache are faster (3-5 minutes).

### Q: Do I need a powerful computer?
**A**: Recommended specs:
- **RAM**: 16GB minimum (32GB recommended)
- **Disk**: 60GB free
- **CPU**: Multi-core (8+ cores recommended)

### Q: Can I build on Windows?
**A**: Yes, using WSL2 (Windows Subsystem for Linux). Install Docker Desktop for Windows and follow the Linux build instructions.

### Q: The build failed with "Out of Memory". What do I do?
**A**: 
1. Increase Docker memory allocation (Docker Desktop → Settings → Resources → 60GB)
2. Reduce parallel jobs: Change `make -j$(nproc)` to `make -j8`
3. Close other applications

### Q: Why do my config flags disappear after `make olddefconfig`?
**A**: This happens when dependencies aren't met. Use `merge_config.sh` instead of manual `scripts/config` commands. See [JOURNEY.md - Phase 4](JOURNEY.md#phase-4-docker-config-challenges).

---

## Installation Questions

### Q: Will I lose my data?
**A**: No, flashing a kernel does not wipe data. However, **always backup** before flashing custom kernels, just in case.

### Q: My phone shows "Corrupt Data" after flashing. Help!
**A**: This is caused by incorrect OS patch level in the boot image. The pre-built kernel has this fixed (`--os_patch_level 2025-10`). If you built it yourself, make sure you used the correct patch level. See [JOURNEY.md - Phase 3](JOURNEY.md#phase-3-the-corrupt-data-mystery-critical-discovery).

**Recovery**:
```bash
fastboot flash boot boot_backup.img
fastboot reboot
```

### Q: My phone is stuck in a bootloop. What do I do?
**A**: 
1. Hold Power + Volume Down to force reboot to bootloader
2. Flash your backup: `fastboot flash boot boot_backup.img`
3. Reboot: `fastboot reboot`

See [Beginner's Guide - Troubleshooting](BEGINNERS_GUIDE.md#phone-wont-boot-bootloop).

### Q: Can I update my ROM after installing this kernel?
**A**: ROM updates usually replace the kernel. You'll need to reflash the custom kernel after updating your ROM.

---

## Verification Questions

### Q: How do I verify the kernel is working?
**A**: After booting, run:
```bash
adb shell uname -r
# Should show: 4.14.353-openela-SOVIET-STAR

adb shell cat /proc/cgroups | grep pids
# Should show: pids  0  XXX  1

adb shell ls -l /proc/self/ns/user
# Should show: user:[XXXXXXX]
```

### Q: `/proc/config.gz` says my features are disabled, but they work. Why?
**A**: `/proc/config.gz` can be stale. The real source of truth is:
1. `autoconf.h` (what was compiled)
2. Actual functionality tests

See [JOURNEY.md - Phase 5](JOURNEY.md#phase-5-the-procconfiggz-lie).

### Q: How do I test Docker features manually?
**A**: 
```bash
# Test namespaces
adb shell su -c "unshare -u -p -f sh"

# Test cgroups
adb shell su -c "cat /proc/cgroups"

# Test OverlayFS
adb shell su -c "mount -t overlay overlay -o lowerdir=/,upperdir=/tmp,workdir=/tmp2 /mnt"
```

---

## Contribution Questions

### Q: Can I contribute to this project?
**A**: Yes! Contributions are welcome. See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines. Note that the project is not actively maintained, so PRs may not be reviewed immediately.

### Q: I fixed the Docker runtime issue! How do I share?
**A**: Excellent! Please:
1. Open a pull request with your changes
2. Include testing results
3. Update documentation
4. Consider writing a guide for others

### Q: Can I port this to another device?
**A**: Yes! The build process and documentation can be adapted. See [PORTING.md](PORTING.md) (if available) or use this as a reference.

---

## Troubleshooting Questions

### Q: Where can I find more help?
**A**: 
1. Check [JOURNEY.md](JOURNEY.md) for common pitfalls and solutions
2. Read [TECHNICAL.md](TECHNICAL.md) for deep technical details
3. See [BEGINNERS_GUIDE.md](BEGINNERS_GUIDE.md) troubleshooting section
4. Search existing GitHub issues
5. Open a new issue with the "Build Help" template

### Q: What logs should I provide when asking for help?
**A**:
- Build log (if build failed)
- `dmesg` output (if boot failed)
- `logcat` output (if system issue)
- Output of `uname -r` and `cat /proc/version`

### Q: The kernel boots but some features don't work. What do I check?
**A**:
1. Verify configs in `autoconf.h` (not just `.config`)
2. Test features manually (don't rely on `/proc/config.gz`)
3. Check `dmesg` for errors
4. Compare with stock kernel behavior

---

## Advanced Questions

### Q: Can I modify the kernel source code?
**A**: Yes, but this repository contains the **build system**, not the full kernel source. To modify the kernel:
1. Clone the SOVIET-ANDROID kernel source
2. Make your changes
3. Use the build scripts from this repo
4. Test thoroughly

### Q: How do I add more kernel features?
**A**: 
1. Add configs to `docker.config`
2. Rebuild using `./run_builder_soviet.sh`
3. Verify in `autoconf.h`
4. Test on device

### Q: Can I use a different toolchain?
**A**: Possible, but not recommended. The stock kernel uses Android Clang 18.0.1. Using a different toolchain may cause ABI incompatibility and bootloops.

### Q: What's the difference between this and the stock kernel?
**A**: Only the Docker-related configs are different. Everything else is identical to the SOVIET-ANDROID stock kernel.

---

## Still Have Questions?

- 📖 Read the [full documentation](README.md)
- 🔍 Search [existing issues](../../issues)
- 💬 Open a [new issue](../../issues/new/choose)
- 📚 Check the [JOURNEY.md](JOURNEY.md) for detailed explanations
