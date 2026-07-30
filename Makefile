.PHONY: help build clean verify flash test release env

# The kernel tree and toolchain live inside build.sparseimage (case-sensitive
# APFS), because this repo sits on an exFAT volume that cannot hold a Linux
# source tree. scripts/build-env.sh attaches it and exports these.
KERNEL_DIR ?= $(if $(KERNEL_SRC),$(KERNEL_SRC),/Volumes/raphael-build/kernel_source)
BOOT_IMG   := boot-personalized.img

help:
	@echo "Redmi K20 Pro Docker Kernel - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  env         - Show resolved build paths"
	@echo "  build       - Build the kernel (via the interactive script)"
	@echo "  clean       - Clean build artifacts"
	@echo "  verify      - Verify Docker features on device"
	@echo "  flash       - Delegates to the interactive script (option 4 -> 3 -> 5)"
	@echo "  test        - Run verification tests"
	@echo "  release     - Copy the built kernel into release/"
	@echo ""
	@echo "Start with:  source scripts/build-env.sh"
	@echo ""

env:
	@echo "KERNEL_DIR = $(KERNEL_DIR)"
	@echo "BOOT_IMG   = $(BOOT_IMG)"
	@test -d "$(KERNEL_DIR)" || echo "  WARNING: kernel tree not found - run 'source scripts/build-env.sh'"

build:
	@echo "Use ./scripts/build_and_flash_interactive.sh (option 2)."
	@echo "It sizes the container, stages docker.config, and verifies flag retention."
	@echo "Run 'source scripts/build-env.sh' first."
	@false

clean:
	@echo "Cleaning build artifacts..."
	rm -rf "$(KERNEL_DIR)/out" out
	@echo "Clean complete."

verify:
	@echo "Verifying kernel features..."
	./scripts/verify_kernel.sh

# Flashing is deliberately NOT implemented here.
#
# This target used to run, unconditionally:
#     fastboot flash boot release/boot-raphael-docker-v1.0.img
# which is wrong in three separate ways:
#   1. It flashes the committed v1.0 artifact, never the kernel you just built.
#   2. That image carries a FIXED OS patch level (2025-10). Android's FBE keys
#      are bound to the patch level, so flashing it after a ROM update presents
#      a downgrade, Keymaster refuses to release the keys, and /data reads as
#      "corrupt" -- the exact failure this project exists to document.
#   3. It never takes a backup and never confirms anything with the device.
#
# repack_boot_img in the interactive script inherits the patch level and OS
# version from the device's own boot image and re-verifies them after writing.
# Use that path.
flash:
	@echo "Refusing to flash from the Makefile."
	@echo ""
	@echo "  Use: ./scripts/build_and_flash_interactive.sh"
	@echo "       option 4  (backup - supplies the ramdisk AND the patch level)"
	@echo "       option 3  (repack - inherits both from the device)"
	@echo "       option 5  (flash  - offers 'fastboot boot' to test first)"
	@echo ""
	@echo "The old target here flashed release/boot-raphael-docker-v1.0.img with a"
	@echo "hardcoded 2025-10 patch level, which can make /data undecryptable."
	@false

test: verify
	@echo "Running additional tests..."
	@adb shell "su -c 'cat /proc/cgroups'" || echo "Failed to read cgroups"
	@adb shell "su -c 'ls -l /proc/self/ns/'" || echo "Failed to list namespaces"

release:
	@echo "Creating release package..."
	@mkdir -p release
	@test -f "$(KERNEL_DIR)/out/arch/arm64/boot/Image.gz-dtb" \
		|| { echo "No built kernel at $(KERNEL_DIR)/out/arch/arm64/boot/Image.gz-dtb"; exit 1; }
	@cp "$(KERNEL_DIR)/out/arch/arm64/boot/Image.gz-dtb" release/
	@echo "Release package created in release/"

.DEFAULT_GOAL := help
