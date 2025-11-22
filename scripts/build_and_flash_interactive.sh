#!/bin/bash
set -e

# Configuration
REPO_URL="https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael"
BRANCH="main"
# Robustly find the repo root (assuming script is in scripts/)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
WORK_DIR="$(dirname "$SCRIPT_DIR")"
KERNEL_DIR="$WORK_DIR/kernel_source"
TOOLCHAIN_DIR="$WORK_DIR/toolchain"
OUT_DIR="$WORK_DIR/out"
BOOT_IMG_NAME="boot-personalized.img"
GITHUB_REPO="xiziphus/kernel_xiaomi_raphael_antigravity"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${GREEN}[INFO] $1${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $1${NC}"; }
error() { echo -e "${RED}[ERROR] $1${NC}"; exit 1; }
info() { echo -e "${BLUE}[MENU] $1${NC}"; }

# --- Helper Functions ---

install_if_missing() {
    local cmd=$1
    local package=$2
    local is_cask=$3
    
    if ! command -v $cmd >/dev/null 2>&1; then
        warn "$cmd is not installed."
        if command -v brew >/dev/null 2>&1; then
            read -p "Install $package via Homebrew? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                if [[ "$is_cask" == "true" ]]; then
                    brew install --cask $package
                else
                    brew install $package
                fi
            else
                error "$package is required. Please install it manually."
            fi
        else
            error "$package is required. Please install it manually (Homebrew not found)."
        fi
    else
        log "$cmd is installed."
    fi
}

check_prerequisites() {
    log "Checking host prerequisites..."
    
    # Docker is special, usually a cask or manual install
    if ! command -v docker >/dev/null 2>&1; then
        error "Docker is not installed. Please install Docker Desktop."
    fi

    install_if_missing "python3" "python"
    install_if_missing "git" "git"
    install_if_missing "wget" "wget"
    install_if_missing "zip" "zip"
    
    # Check for fastboot/adb (android-platform-tools)
    if ! command -v fastboot >/dev/null 2>&1; then
         install_if_missing "fastboot" "android-platform-tools" "true"
    else
        log "fastboot is installed."
    fi
    
    if ! command -v adb >/dev/null 2>&1; then
         warn "adb is not installed (usually comes with platform-tools)."
    fi
}

setup_environment() {
    mkdir -p "$KERNEL_DIR" "$TOOLCHAIN_DIR" "$OUT_DIR"
    
    # Clone Kernel
    if [ ! -d "$KERNEL_DIR/.git" ]; then
        if [ -d "/Volumes/android-kernel/soviet_kernel_stock" ]; then
            log "Using existing kernel source at /Volumes/android-kernel/soviet_kernel_stock"
            KERNEL_DIR="/Volumes/android-kernel/soviet_kernel_stock"
        else
            log "Cloning kernel source..."
            git clone "$REPO_URL" "$KERNEL_DIR"
        fi
    fi

    # Setup Toolchain
    if [ ! -d "$TOOLCHAIN_DIR/clang-r522817" ]; then
        if [ -d "/Volumes/android-kernel/clang-r522817" ]; then
            log "Linking existing toolchain..."
            ln -sf /Volumes/android-kernel/clang-r522817 "$TOOLCHAIN_DIR/clang-r522817"
        else
            log "Downloading toolchain..."
            wget https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/main/clang-r522817.tar.gz -O clang.tar.gz
            mkdir -p "$TOOLCHAIN_DIR/clang-r522817"
            tar -xzf clang.tar.gz -C "$TOOLCHAIN_DIR/clang-r522817"
            rm clang.tar.gz
        fi
    fi

    # Build Docker Image
    if [[ "$(docker images -q android-kernel-builder 2> /dev/null)" == "" ]]; then
        log "Building Docker image..."
        docker build -t android-kernel-builder .
    fi
}

clean_build() {
    log "Cleaning build artifacts..."
    rm -rf "$KERNEL_DIR/out"
    rm -rf "$OUT_DIR"
    log "Clean complete."
}

build_kernel() {
    log "Starting Kernel Build..."
    cp scripts/build_kernel_soviet_docker.sh "$KERNEL_DIR/build_docker.sh"
    cp docker.config "$KERNEL_DIR/docker.config"
    chmod +x "$KERNEL_DIR/build_docker.sh"

    docker run --rm -i \
      --name soviet-kernel-builder \
      --cpus="16" \
      --memory="60g" \
      -v "$KERNEL_DIR":/kernel/soviet_kernel_stock \
      -v "$TOOLCHAIN_DIR/clang-r522817":/opt/clang \
      --tmpfs /tmp/build:rw,size=4G,mode=1777 \
      android-kernel-builder \
      bash /kernel/soviet_kernel_stock/build_docker.sh
      
    # Copy artifacts
    if [ -f "$KERNEL_DIR/out/arch/arm64/boot/Image.gz-dtb" ]; then
        cp "$KERNEL_DIR/out/arch/arm64/boot/Image.gz-dtb" "$OUT_DIR/Image.gz-dtb"
        log "Kernel compiled successfully!"
    else
        error "Build failed! Image.gz-dtb not found."
    fi
}

repack_boot_img() {
    log "Repacking Boot Image..."
    if [ ! -f "stock_kernel_extracted/ramdisk.cpio.gz" ]; then
        if [ -f "boot_backup.img" ]; then
            python3 scripts/unpack_boot.py boot_backup.img stock_kernel_extracted
        else
            error "Ramdisk missing! Need boot_backup.img to extract it."
        fi
    fi

    python3 mkbootimg_src/mkbootimg.py \
      --kernel "$OUT_DIR/Image.gz-dtb" \
      --ramdisk stock_kernel_extracted/ramdisk.cpio.gz \
      --cmdline "console=null androidboot.hardware=qcom androidboot.usbcontroller=a600000.dwc3 androidboot.boot_devices=soc/1d84000.ufshc service_locator.enable=1 lpm_levels.sleep_disabled=1 loop.max_part=16 androidboot.init_fatal_reboot_target=recovery kpti=off swiotlb=1 androidboot.super_partition=system" \
      --base 0x10000000 \
      --pagesize 4096 \
      --os_version 0 \
      --os_patch_level 2025-10 \
      --output "$BOOT_IMG_NAME"
      
    log "Created $BOOT_IMG_NAME"
}

backup_boot() {
    log "Attempting to backup current boot image..."
    ADB_DEVICES=$(adb devices | grep -v "List" | grep "device" || true)
    
    if [[ -n "$ADB_DEVICES" ]]; then
        # Requires root
        mkdir -p "$WORK_DIR/backups"
        adb shell "su -c 'dd if=/dev/block/bootdevice/by-name/boot of=/sdcard/boot_backup_$(date +%Y%m%d).img'"
        adb pull "/sdcard/boot_backup_$(date +%Y%m%d).img" "$WORK_DIR/backups/"
        log "Backup saved to $WORK_DIR/backups/"
    else
        warn "Device not found in ADB mode. Cannot backup."
    fi
}

flash_kernel() {
    log "Checking for connected devices..."
    ADB_DEVICES=$(adb devices | grep -v "List" | grep "device" || true)
    FASTBOOT_DEVICES=$(fastboot devices || true)

    if [[ -n "$ADB_DEVICES" ]]; then
        log "Device found in ADB mode."
        read -p "Reboot to bootloader? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            adb reboot bootloader
            log "Waiting for fastboot..."
            fastboot wait-for-device
        fi
    elif [[ -n "$FASTBOOT_DEVICES" ]]; then
        log "Device found in Fastboot mode."
    else
        warn "No device detected!"
        return
    fi

    log "Flashing boot partition..."
    fastboot flash boot "$BOOT_IMG_NAME"
    log "Rebooting..."
    fastboot reboot
}

create_anykernel_zip() {
    log "Creating AnyKernel3 Zip..."
    if [ ! -d "AnyKernel3" ]; then
        git clone https://github.com/osm0sis/AnyKernel3
    fi
    cp "$OUT_DIR/Image.gz-dtb" AnyKernel3/
    cd AnyKernel3
    zip -r9 "../kernel-installer-$(date +%Y%m%d).zip" * -x .git README.md *placeholder
    cd ..
    log "Created kernel-installer.zip"
}

collect_logs() {
    log "Collecting logs..."
    mkdir -p logs
    adb shell dmesg > "logs/dmesg_$(date +%Y%m%d_%H%M%S).log"
    adb logcat -d > "logs/logcat_$(date +%Y%m%d_%H%M%S).log"
    log "Logs saved to logs/ directory."
}

rebuild_docker_image() {
    log "Rebuilding Docker Image..."
    if [ -f "$WORK_DIR/Dockerfile" ]; then
        docker build --no-cache -t android-kernel-builder "$WORK_DIR"
        log "Docker image rebuilt successfully."
    else
        error "Dockerfile not found at $WORK_DIR/Dockerfile!"
    fi
}

update_kernel_source() {
    log "Updating Kernel Source..."
    if [ -d "$KERNEL_DIR/.git" ]; then
        cd "$KERNEL_DIR"
        git pull
        cd "$WORK_DIR"
        log "Kernel source updated."
    else
        warn "Kernel source not found. Cloning..."
        setup_environment
    fi
}

ensure_config_files() {
    # If running standalone, we might need to generate these files
    if [ ! -f "docker.config" ]; then
        log "Generating docker.config..."
        cat <<EOF > docker.config
CONFIG_CGROUP_PIDS=y
CONFIG_MEMCG=y
CONFIG_VETH=y
CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y
CONFIG_POSIX_MQUEUE=y
EOF
    fi

    if [ ! -f "scripts/build_kernel_soviet_docker.sh" ]; then
        log "Generating build script..."
        mkdir -p scripts
        cat <<EOF > scripts/build_kernel_soviet_docker.sh
#!/bin/bash
set -e
echo "=== SOVIET Kernel - Docker Patched Build ==="
# ... (Simplified build script content would go here, but for now we assume repo context)
# Ideally, this script should be part of the repo.
EOF
        # For now, we rely on the repo structure as the user is in the repo.
        # But to be robust, we check if they exist.
    fi
}

# --- Main Menu ---

check_prerequisites
setup_environment
ensure_config_files

while true; do
    echo ""
    info "=== Docker Kernel Builder Menu ==="
    echo "1.  Clean Build Directory"
    echo "2.  Build Kernel"
    echo "3.  Repack Boot Image"
    echo "4.  Backup Current Boot Image (ADB Root)"
    echo "5.  Flash Kernel (Auto-detect)"
    echo "6.  Create AnyKernel3 Zip"
    echo "7.  Collect Debug Logs"
    echo "8.  Rebuild Docker Image (Force)"
    echo "9.  Update Kernel Source"
    echo "0.  FULL AUTO (Build -> Repack -> Flash)"
    echo "x.  Exit"
    echo ""
    read -p "Select an option: " choice

    case $choice in
        1) clean_build ;;
        2) build_kernel ;;
        3) repack_boot_img ;;
        4) backup_boot ;;
        5) flash_kernel ;;
        6) create_anykernel_zip ;;
        7) collect_logs ;;
        8) rebuild_docker_image ;;
        9) update_kernel_source ;;
        0) 
            build_kernel
            repack_boot_img
            read -p "Flash now? (y/n) " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                flash_kernel
            fi
            ;;
        x) exit 0 ;;
        *) warn "Invalid option" ;;
    esac
done
