---
name: Bug Report
about: Report a build or boot issue
title: '[BUG] '
labels: bug
assignees: ''
---

## Bug Description
A clear and concise description of what the bug is.

## Environment
- **Device**: Redmi K20 Pro (raphael)
- **ROM**: (e.g., Evolution X Android 16, MIUI, etc.)
- **Root Method**: (e.g., Magisk, KernelSU, None)
- **Kernel Version**: (output of `uname -r`)

## Steps to Reproduce
1. 
2. 
3. 

## Expected Behavior
What you expected to happen.

## Actual Behavior
What actually happened.

## Logs
Please provide relevant logs:

<details>
<summary>Build Log (if build failed)</summary>

```
Paste build log here
```
</details>

<details>
<summary>dmesg (if boot failed)</summary>

```bash
adb shell dmesg > dmesg.log
# Paste output here
```
</details>

<details>
<summary>logcat (if system issue)</summary>

```bash
adb logcat > logcat.log
# Paste output here
```
</details>

## Screenshots
If applicable, add screenshots to help explain your problem.

## Additional Context
Add any other context about the problem here.

## Checklist
- [ ] I have read the [JOURNEY.md](../docs/JOURNEY.md) troubleshooting section
- [ ] I have checked existing issues for duplicates
- [ ] I have verified my toolchain version (Android Clang 18.0.1)
- [ ] I have verified my kernel source (SOVIET-ANDROID)
- [ ] I have a backup of my stock boot image
