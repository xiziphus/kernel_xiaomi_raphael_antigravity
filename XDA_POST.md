[SIZE=6][B]Docker-Enabled Kernel for Redmi K20 Pro (Android 16)[/B][/SIZE]


[B]Device:[/B] Xiaomi Redmi K20 Pro (raphael)
[B]Android Version:[/B] Android 16 (Baklava)
[B]Kernel Version:[/B] 4.14.353-openela-SOVIET-STAR
[B]Based on:[/B] SOVIET-ANDROID kernel source
[B]Tested on:[/B] Evolution X Android 16 with Magisk

---


---

[SIZE=5][B]What is this?[/B][/SIZE]


A custom kernel with [B]full Docker support[/B] for the Redmi K20 Pro running Android 16. All necessary kernel features for containerization are enabled and verified working.

---


---

[SIZE=5][B]Features[/B][/SIZE]


[B]✅ Docker Kernel Support (Complete)[/B]

• User Namespaces (USER_NS)

• PID Namespaces (PID_NS)

• Cgroup PIDs controller

• OverlayFS filesystem

• VETH networking

• Bridge networking

• IP Masquerading

• All features verified via /proc/cgroups and namespace tests

[B]✅ KernelSU Support[/B]

• KernelSU code included (tested with Magisk)

[B]✅ Stable & Secure[/B]

• Based on stock SOVIET-ANDROID kernel

• Proper encryption support (FBE compatible)

• No bootloops, no data corruption


---

[SIZE=5][B]Download[/B][/SIZE]


[B]GitHub Repository:[/B] [URL]https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity[/URL]

[B]Latest Release:[/B] [URL]https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity/releases/latest[/URL]

[B]Files:[/B]

• 
[CODE]boot-raphael-docker-v1.0.img[/CODE]
 - Flashable boot image (14 MB)

• 
[CODE]Image.gz-dtb[/CODE]
 - Kernel image only (12 MB)

• SHA256 checksums included


---

[SIZE=5][B]Installation[/B][/SIZE]


[B]Prerequisites:[/B]

• Unlocked bootloader

• ADB and Fastboot installed

• Backup of your current boot image (recommended)

[B]Steps:[/B]

[CODE]
# Backup current boot (recommended)
adb reboot bootloader
fastboot getvar current-slot

# Flash the kernel
fastboot flash boot boot-raphael-docker-v1.0.img
fastboot reboot
[/CODE]


[B]Verification:[/B]

[CODE]
# After booting, verify Docker features
adb shell su -c "cat /proc/cgroups | grep pids"
adb shell su -c "ls -l /proc/self/ns/user"
[/CODE]


Both commands should show the features are present.


---

[SIZE=5][B]Known Limitations[/B][/SIZE]


[B]⚠️ Docker Runtime Compatibility[/B]

The kernel has [B]full Docker support[/B], but there's a userspace limitation:

[B]Issue:[/B] Android's PIE (Position Independent Executable) enforcement blocks standard container runtimes like 
[CODE]runc[/CODE]
 and 
[CODE]crun[/CODE]
.

[B]Error:[/B] 
[CODE]unexpected e_type: 2[/CODE]
 (non-PIE binary rejected)

[B]Status:[/B]

• ✅ Kernel features: [COLOR="Green"]Working perfectly[/COLOR]

• ⚠️ Docker runtime: [COLOR="Orange"]Blocked by Android security[/COLOR]

[B]Workarounds:[/B]
1. Use Termux directly for running Node.js, Python, databases (works great!)
2. Use proot-distro for full Linux environment
3. Compile PIE-compatible container runtime (advanced)

[B]For most use cases, Termux + your apps works perfectly without containers.[/B]


---

[SIZE=5][B]Documentation[/B][/SIZE]


Comprehensive documentation included:

[B]📘 Beginner's Guide[/B] - Step-by-step tutorial for first-time kernel builders
[B]📖 The Journey[/B] - Complete development story with all pitfalls and solutions
[B]🔧 Technical Deep Dive[/B] - Advanced topics: boot process, encryption, Kconfig
[B]❓ FAQ[/B] - 70+ frequently asked questions
[B]🛠️ Build Instructions[/B] - How to compile from source

All docs available in the GitHub repository.


---

[SIZE=5][B]Compatibility[/B][/SIZE]


[B]✅ Works on:[/B]

• Redmi K20 Pro (raphael) only

• Android 16 ROMs (tested on Evolution X)

• Should work on other Android 16 ROMs using SOVIET kernel base

[B]❌ Does NOT work on:[/B]

• Redmi K20 (non-Pro) - different SoC

• Android 15 or earlier

• Other devices


---

[SIZE=5][B]Building from Source[/B][/SIZE]


Full build instructions included in repository. Uses:

• Docker build environment

• Android Clang 18.0.1 toolchain

• Automated build scripts

• Config fragment for Docker features


[CODE]
# Clone kernel source
git clone https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael

# Run build
./run_builder_soviet.sh
[/CODE]

See the [B]BUILD.md[/B] file in the repository for detailed instructions.

---

[SIZE=5][B]What Makes This Different?[/B][/SIZE]


[B]1. Comprehensive Documentation[/B]

• Complete journey documented with all failures and solutions

• Beginner-friendly step-by-step guide

• Technical deep-dive for advanced users

• 70+ FAQ entries

[B]2. Verified Working[/B]

• All Docker kernel features tested and confirmed

• Boots successfully, no data corruption

• Encryption working properly

• Tested on real device for daily use

[B]3. Educational Resource[/B]

• Learn about Android boot process

• Understand File-Based Encryption

• Kernel configuration management

• Build system optimization

[B]4. Community Ready[/B]

• Issue templates for bug reports

• Pull request template

• GitHub Actions for automated verification

• Comprehensive troubleshooting guides


---

[SIZE=5][B]Credits[/B][/SIZE]



• [B]Kernel Source:[/B] [URL]https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael[/URL]

• [B]Toolchain:[/B] Android Clang 18.0.1 (r522817)

• [B]Build Tools:[/B] mkbootimg from AOSP


---

[SIZE=5][B]Maintenance Status[/B][/SIZE]


[B]⚠️ This project is not actively maintained.[/B]

Provided as-is for educational purposes and as a foundation for others to build upon. The kernel is stable and working, but future updates are not guaranteed.

Feel free to fork and continue development. Pull requests are welcome!


---

[SIZE=5][B]License[/B][/SIZE]


GPL-2.0 (same as Linux kernel)


---

[SIZE=5][B]Disclaimer[/B][/SIZE]


[B]⚠️ Use at your own risk.[/B] Flashing custom kernels can potentially brick your device. Always keep a backup of your stock boot image.


---

[SIZE=5][B]Support & Discussion[/B][/SIZE]



• [B]GitHub Issues:[/B] [URL]https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity/issues[/URL]

• [B]GitHub Discussions:[/B] [URL]https://github.com/xiziphus/kernel_xiaomi_raphael_antigravity/discussions[/URL]


---

---

[SIZE=5][B]Verification Output[/B][/SIZE]

[B]Kernel Version:[/B]
[CODE]
# uname -r
4.14.353-openela-SOVIET-STAR-//932efc887a
[/CODE]

[B]Docker Features Verification:[/B]
[CODE]
# cat /proc/cgroups
#subsys_name    hierarchy       num_cgroups     enabled
cpuset          3               8               1
cpu             2               11              1
cpuacct         5               1               1
blkio           1               2               1
memory          0               457             1
devices         6               1               1
freezer         7               1               1
pids            4               1               1  ← Docker PIDs cgroup enabled!
[/CODE]

[CODE]
# ls -l /proc/self/ns/
lrwxrwxrwx 1 root root 0 user:[4026531837]  ← User namespace present!
lrwxrwxrwx 1 root root 0 pid:[4026531836]
lrwxrwxrwx 1 root root 0 net:[4026531905]
[/CODE]

All Docker kernel features confirmed working! ✅

---

[SIZE=4][B]Changelog[/B][/SIZE]


[B]v1.0.0 - November 2025[/B]

• Initial release

• Full Docker kernel support

• KernelSU included

• Comprehensive documentation

• Tested on Evolution X Android 16

---

If you find this useful, please ⭐ star the repository on GitHub!

Questions? Check the FAQ first, then feel free to ask in this thread or open a GitHub issue.
