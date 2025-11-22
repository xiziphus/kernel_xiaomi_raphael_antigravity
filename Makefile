.PHONY: help build clean verify flash test

help:
	@echo "Redmi K20 Pro Docker Kernel - Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  build       - Build the kernel"
	@echo "  clean       - Clean build artifacts"
	@echo "  verify      - Verify Docker features on device"
	@echo "  flash       - Flash the kernel to device (requires confirmation)"
	@echo "  test        - Run verification tests"
	@echo "  release     - Create release package"
	@echo ""

build:
	@echo "Building kernel..."
	./run_builder_soviet.sh

clean:
	@echo "Cleaning build artifacts..."
	rm -rf /Volumes/android-kernel/soviet_kernel_stock/out
	@echo "Clean complete"

verify:
	@echo "Verifying kernel features..."
	./scripts/verify_kernel.sh

flash:
	@echo "WARNING: This will flash the kernel to your device!"
	@read -p "Are you sure? (yes/no): " confirm; \
	if [ "$$confirm" = "yes" ]; then \
		adb reboot bootloader; \
		sleep 5; \
		fastboot flash boot release/boot-raphael-docker-v1.0.img; \
		fastboot reboot; \
	else \
		echo "Flash cancelled"; \
	fi

test: verify
	@echo "Running additional tests..."
	@adb shell "su -c 'cat /proc/cgroups'" || echo "Failed to read cgroups"
	@adb shell "su -c 'ls -l /proc/self/ns/'" || echo "Failed to list namespaces"

release:
	@echo "Creating release package..."
	@mkdir -p release
	@cp /Volumes/android-kernel/soviet_kernel_stock/out/arch/arm64/boot/Image.gz-dtb release/
	@echo "Release package created in release/"

.DEFAULT_GOAL := help
