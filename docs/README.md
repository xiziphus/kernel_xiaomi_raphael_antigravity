# Documentation Index

Welcome to the Redmi K20 Pro Docker Kernel documentation!

## Quick Start

**New to kernel compilation?** Start here:
- 📘 [Beginner's Guide](BEGINNERS_GUIDE.md) - Step-by-step tutorial for first-time kernel builders

**Want to understand what happened?** Read this:
- 📖 [The Journey](JOURNEY.md) - Complete development story with all pitfalls and solutions

**Need technical details?** Check this:
- 🔧 [Technical Deep Dive](TECHNICAL.md) - Advanced topics: boot process, encryption, Kconfig

## Documentation Structure

### For Beginners
1. **[BEGINNERS_GUIDE.md](BEGINNERS_GUIDE.md)**
   - Prerequisites and setup
   - Step-by-step build process
   - Installation guide
   - Troubleshooting common issues
   - FAQ

### For Understanding the Process
2. **[JOURNEY.md](JOURNEY.md)**
   - Complete development timeline
   - Discovery process
   - All pitfalls encountered
   - Solutions implemented
   - Lessons learned

### For Advanced Users
3. **[TECHNICAL.md](TECHNICAL.md)**
   - Android boot sequence
   - File-Based Encryption details
   - Boot image structure
   - Kernel configuration system
   - Docker requirements
   - Build optimizations

## Main Repository Documentation

### Essential Files
- **[README.md](../README.md)** - Project overview, features, installation
- **[BUILD.md](../BUILD.md)** - Detailed build instructions
- **[CHANGELOG.md](../CHANGELOG.md)** - Version history and changes
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - How to contribute
- **[LICENSE](../LICENSE)** - GPL-2.0 license

### Release Information
- **[release/RELEASE_NOTES.md](../release/RELEASE_NOTES.md)** - v1.0.0 release details
- **[release/SHA256SUMS](../release/SHA256SUMS)** - File checksums

## Learning Path

### Path 1: "I just want to build and install"
```
README.md → BEGINNERS_GUIDE.md → Done!
```

### Path 2: "I want to understand everything"
```
README.md → JOURNEY.md → TECHNICAL.md → BEGINNERS_GUIDE.md
```

### Path 3: "I want to contribute"
```
README.md → JOURNEY.md → BUILD.md → CONTRIBUTING.md
```

### Path 4: "I'm debugging an issue"
```
JOURNEY.md (Pitfalls section) → TECHNICAL.md → BEGINNERS_GUIDE.md (Troubleshooting)
```

## Key Topics

### Boot Issues
- **Bootloop**: [JOURNEY.md - Phase 1 & 2](JOURNEY.md#phase-1-source-selection-first-attempt-failed)
- **"Corrupt Data"**: [JOURNEY.md - Phase 3](JOURNEY.md#phase-3-the-corrupt-data-mystery-critical-discovery)
- **Boot Process**: [TECHNICAL.md - Boot Sequence](TECHNICAL.md#android-boot-sequence)

### Configuration
- **Docker Configs**: [JOURNEY.md - Phase 4](JOURNEY.md#phase-4-docker-config-challenges)
- **Kconfig System**: [TECHNICAL.md - Kernel Configuration](TECHNICAL.md#kernel-configuration-system)
- **Config Verification**: [JOURNEY.md - Phase 5](JOURNEY.md#phase-5-the-procconfiggz-lie)

### Encryption
- **FBE Explained**: [TECHNICAL.md - File-Based Encryption](TECHNICAL.md#file-based-encryption-fbe)
- **OS Patch Level**: [JOURNEY.md - Phase 3](JOURNEY.md#the-breakthrough)
- **Key Derivation**: [TECHNICAL.md - Key Derivation Process](TECHNICAL.md#key-derivation-process)

### Docker
- **Kernel Requirements**: [TECHNICAL.md - Docker Requirements](TECHNICAL.md#docker-requirements)
- **PIE Enforcement**: [TECHNICAL.md - Android-Specific Limitations](TECHNICAL.md#android-specific-limitations)
- **Runtime Issues**: [JOURNEY.md - Final Status](JOURNEY.md#final-status)

## Quick Reference

### Build Commands
```bash
# Full build
./run_builder.sh

# Repack boot image
python3 mkbootimg.py \
  --kernel out/arch/arm64/boot/Image.gz-dtb \
  --ramdisk stock_extracted/ramdisk.cpio.gz \
  --os_patch_level 2025-10 \
  --output boot.img

# Flash kernel
fastboot flash boot boot.img
```

### Verification Commands
```bash
# Check kernel version
adb shell uname -r

# Check Docker features
adb shell cat /proc/cgroups
adb shell ls -l /proc/self/ns/

# Test namespaces
adb shell su -c "unshare -u -p -f sh"
```

### Recovery Commands
```bash
# Restore backup
fastboot flash boot boot_backup.img
fastboot reboot
```

## Troubleshooting Quick Links

| Issue | Solution |
|-------|----------|
| Bootloop | [BEGINNERS_GUIDE.md - Troubleshooting](BEGINNERS_GUIDE.md#phone-wont-boot-bootloop) |
| Corrupt Data | [BEGINNERS_GUIDE.md - Troubleshooting](BEGINNERS_GUIDE.md#corrupt-data-error) |
| Build Fails | [BEGINNERS_GUIDE.md - Troubleshooting](BEGINNERS_GUIDE.md#build-fails-with-out-of-memory) |
| Missing Features | [BEGINNERS_GUIDE.md - Troubleshooting](BEGINNERS_GUIDE.md#docker-features-not-working) |
| Docker Runtime | [JOURNEY.md - Final Status](JOURNEY.md#what-doesnt-work-️) |

## External Resources

### Kernel Source
- [SOVIET-ANDROID/kernel_xiaomi_raphael](https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael)

### Toolchain
- [Android Clang Prebuilts](https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/)

### Documentation
- [Android Boot Image Header](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
- [File-Based Encryption](https://source.android.com/docs/security/features/encryption/file-based)
- [Kernel Kconfig](https://www.kernel.org/doc/html/latest/kbuild/kconfig-language.html)

## Contributing to Documentation

Found an error? Want to add more details? See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to contribute.

### Documentation Style Guide
- Use clear, simple language
- Include code examples
- Add troubleshooting sections
- Link to related documentation
- Keep beginners in mind

---

**Need help?** Open an issue on GitHub or check the [FAQ](BEGINNERS_GUIDE.md#faq).
