# Contributing to Redmi K20 Pro Docker Kernel

Thank you for your interest in contributing! This project aims to provide a stable, Docker-enabled kernel for the Redmi K20 Pro running Android 16.

## How to Contribute

### Reporting Issues

When reporting issues, please include:
- Device model and Android version
- Kernel version (from `uname -a`)
- Steps to reproduce
- Relevant logs (`dmesg`, `logcat`)
- Whether you can boot back to stock kernel

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Test thoroughly on your device
5. Commit with clear messages
6. Push to your fork
7. Create a Pull Request

### Code Style

- Follow existing code formatting
- Comment complex sections
- Keep commits atomic and focused
- Write descriptive commit messages

### Testing Requirements

Before submitting:
- [ ] Kernel builds successfully
- [ ] Device boots without bootloop
- [ ] Encryption works (no "corrupt data" error)
- [ ] Docker features verified (if applicable)
- [ ] No regressions in core functionality

## Areas for Contribution

### High Priority
- PIE-compatible container runtime solution
- Additional device support (other Snapdragon 855 devices)
- Automated testing scripts
- Performance optimizations

### Medium Priority
- Additional Docker features (AppArmor, SELinux profiles)
- Better documentation
- Build automation (GitHub Actions)
- Alternative containerization guides

### Low Priority
- UI/UX improvements for build scripts
- Additional language translations
- Example Docker configurations

## Questions?

Open an issue with the `question` label or join our discussions.

## Code of Conduct

- Be respectful and constructive
- Help others learn
- Focus on technical merit
- No harassment or discrimination

Thank you for contributing!
