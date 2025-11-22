# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-11-22

### Testing
- Tested on Redmi K20 Pro (raphael)
- ROM: Evolution X Android 16
- Root: Magisk (KernelSU code included but not tested)
- Status: Fully functional

### Added
- Initial release of Docker-enabled kernel for Redmi K20 Pro (Android 16)
- Full Docker kernel support:
  - User Namespaces (`CONFIG_USER_NS`)
  - PID Namespaces (`CONFIG_PID_NS`)
  - Cgroup PIDs controller (`CONFIG_CGROUP_PIDS`)
  - Cgroup Device controller (`CONFIG_CGROUP_DEVICE`)
  - OverlayFS (`CONFIG_OVERLAY_FS`)
  - VETH networking (`CONFIG_VETH`)
  - Bridge networking (`CONFIG_BRIDGE`)
  - IP Masquerading (`CONFIG_IP_NF_TARGET_MASQUERADE`)
- KernelSU support (built-in)
- Based on SOVIET-ANDROID kernel 4.14.353-openela

### Fixed
- Boot encryption compatibility by setting correct OS patch level (2025-10)
- Bootloop issues by using stock kernel source instead of Evolution X
- Config fragment merging using `merge_config.sh` for reliable flag application

### Known Issues
- Docker userspace runtime (`runc`/`crun`) incompatible due to Android PIE enforcement
  - Kernel features are fully functional
  - Workaround: Use PIE-compiled runtime or alternative containerization

### Technical Details
- **Kernel Version**: 4.14.353-openela-SOVIET-STAR
- **Build Date**: November 22, 2025
- **Toolchain**: Android Clang 18.0.1 (r522817)
- **Build Optimizations**: ccache, tmpfs, 16-core parallel compilation

### Verification
- ✅ Device boots successfully on Evolution X Android 16
- ✅ Encryption working (no "corrupt data" error)
- ✅ Magisk root working
- ✅ User namespaces verified (`/proc/self/ns/user` present)
- ✅ PIDs cgroup verified (`/proc/cgroups` shows `pids` enabled)
- ✅ Manual `unshare` test successful
- ⚠️ Docker runtime blocked by Android security (non-PIE binary rejection)

### Maintenance Status
- ⚠️ **Not actively maintained** - Provided as-is for educational purposes and as a foundation for others

---

## Release Assets

- `boot-raphael-docker-v1.0.img` - Flashable boot image
- `Image.gz-dtb` - Kernel image with device tree
- `docker.config` - Kernel config fragment for Docker support
- Source code (linked to SOVIET-ANDROID repository)
