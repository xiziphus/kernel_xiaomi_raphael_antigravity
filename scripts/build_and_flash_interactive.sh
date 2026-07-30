#!/bin/bash
#
# Redmi K20 Pro (raphael) Docker Kernel — interactive build/flash tool
#
# Usage:  ./scripts/build_and_flash_interactive.sh
#
# Environment overrides (optional):
#   KERNEL_SRC=/path/to/kernel_xiaomi_raphael    reuse an existing source tree
#   CLANG_DIR=/path/to/clang-r522817             reuse an existing toolchain
#   BUILD_JOBS=8                                 override CPU count
#   BUILD_MEM=32g                                override container memory
#
set -euo pipefail

# --- Paths -------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
WORK_DIR="$(dirname "$SCRIPT_DIR")"
cd "$WORK_DIR"   # every relative path below is now anchored to the repo root

REPO_URL="https://github.com/SOVIET-ANDROID/kernel_xiaomi_raphael"
# This repo has no 'main' branch — `git clone -b main` fails outright. Branches are
# per-Android-release (10.0 … 16.0, plus -susfs and backport-bpf-* variants); the
# default is 16.0, which is the one matching an Android 16 ROM.
#
# Upstream has moved past the validated baseline (v1.0 shipped 4.14.353-openela).
# Building from a moving HEAD means building something nobody has booted on this
# device. Pin, and override deliberately:  KERNEL_REF=16.0-susfs ./scripts/...
KERNEL_REF="${KERNEL_REF:-16.0}"
EXPECTED_SUBLEVEL="${EXPECTED_SUBLEVEL:-353}"
KERNEL_DIR="${KERNEL_SRC:-$WORK_DIR/kernel_source}"
TOOLCHAIN_DIR="$WORK_DIR/toolchain"
CLANG_PATH="${CLANG_DIR:-$TOOLCHAIN_DIR/clang-r522817}"
OUT_DIR="$WORK_DIR/out"
BACKUP_DIR="$WORK_DIR/backups"
STOCK_DIR="$WORK_DIR/stock_kernel_extracted"
BOOT_IMG="$WORK_DIR/boot-personalized.img"
DOCKER_IMAGE="android-kernel-builder"

# Device constants (raphael / sm8150, boot header v0)
BOOT_BASE="0x10000000"

# --- Output ------------------------------------------------------------------
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
log()   { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[ERROR]${NC} $1"; return 1; }
die()   { echo -e "${RED}[FATAL]${NC} $1"; exit 1; }
info()  { echo -e "${BLUE}[MENU]${NC} $1"; }

# --- Prerequisites -----------------------------------------------------------
install_if_missing() {
    local cmd=$1 package=$2 is_cask=${3:-false}
    if command -v "$cmd" >/dev/null 2>&1; then
        log "$cmd found."
        return 0
    fi
    warn "$cmd is not installed."
    if ! command -v brew >/dev/null 2>&1; then
        die "$package is required and Homebrew was not found. Install it manually."
    fi
    read -r -p "Install $package via Homebrew? (y/n) " -n 1 REPLY; echo
    [[ $REPLY =~ ^[Yy]$ ]] || die "$package is required."
    if [[ "$is_cask" == "true" ]]; then brew install --cask "$package"; else brew install "$package"; fi
}

check_prerequisites() {
    log "Checking host prerequisites..."
    command -v docker >/dev/null 2>&1 || die "Docker is not installed. Install Docker Desktop first."
    docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker Desktop."
    install_if_missing python3 python
    install_if_missing git git
    install_if_missing curl curl
    install_if_missing zip zip
    command -v fastboot >/dev/null 2>&1 || install_if_missing fastboot android-platform-tools true
    command -v adb >/dev/null 2>&1 || warn "adb not found — backup, logs and auto-reboot will be unavailable."

    # AOSP Clang is a linux-x86 binary; an arm64 container cannot execute it.
    #
    # NOTE: every use of DOCKER_PLATFORM must be written as
    #   ${DOCKER_PLATFORM[@]+"${DOCKER_PLATFORM[@]}"}
    # macOS /bin/bash is 3.2.57, where expanding an EMPTY array as
    # "${arr[@]}" under `set -u` is an unbound-variable error and kills the
    # script outright. On an Intel host this branch leaves the array empty, so
    # the plain form aborts at the first docker invocation. The +alternate form
    # expands to nothing when unset and is safe on both bash 3.2 and 4+.
    if [[ "$(uname -m)" == "arm64" ]]; then
        warn "Apple Silicon detected — the build container will run under x86_64 emulation (slow but works)."
        DOCKER_PLATFORM=(--platform linux/amd64)
    else
        DOCKER_PLATFORM=()
    fi
}

# If the repo sits on a filesystem without native xattr support (exFAT, FAT,
# SMB), macOS writes a "._name" AppleDouble sidecar beside every file. BuildKit
# packs the build context by walking it and reading xattrs, and aborts:
#
#   ERROR: failed to solve: failed to read dockerfile:
#          error from sender: failed to xattr ._.editorconfig: operation not permitted
#
# A .dockerignore does NOT fix this -- BuildKit reads the context (including
# .dockerignore and its own "._" sidecar) before ignore rules are applied. The
# only reliable fix is to hand `docker build` a context that has no sidecars at
# all. The Dockerfile COPYs nothing, so a directory containing just it is enough.
stage_docker_context() {
    local ctx="${TMPDIR:-/tmp}/raphael-dockerctx"
    rm -rf "$ctx"; mkdir -p "$ctx"
    cp Dockerfile "$ctx/Dockerfile"
    find "$ctx" -name '._*' -delete 2>/dev/null || true
    printf '%s' "$ctx"
}

# Refuse to run with a half-populated repo rather than silently generating stubs.
verify_repo_integrity() {
    local missing=0
    for f in docker.config scripts/build_kernel_soviet_docker.sh mkbootimg_src/mkbootimg.py \
             scripts/unpack_boot.py Dockerfile; do
        [[ -f "$f" ]] || { fail "Missing required file: $f" || true; missing=1; }
    done
    (( missing == 0 )) || die "Repo is incomplete. Re-clone rather than continuing — a partial build can produce an unbootable image."
    log "Repo integrity OK."
}

# --- Environment -------------------------------------------------------------
setup_environment() {
    mkdir -p "$TOOLCHAIN_DIR" "$OUT_DIR" "$BACKUP_DIR"

    if [[ -d "$KERNEL_DIR/.git" ]]; then
        log "Using kernel source at $KERNEL_DIR"
    else
        log "Cloning kernel source ($KERNEL_REF) into $KERNEL_DIR ..."
        git clone --depth 1 --branch "$KERNEL_REF" "$REPO_URL" "$KERNEL_DIR"
    fi

    # Version drift check: the shipped kernel was built from 4.14.$EXPECTED_SUBLEVEL.
    local sublevel
    sublevel=$(sed -n 's/^SUBLEVEL = //p' "$KERNEL_DIR/Makefile" | head -1)
    if [[ -n "$sublevel" && "$sublevel" != "$EXPECTED_SUBLEVEL" ]]; then
        warn "Source tree is 4.14.$sublevel; the validated build was 4.14.$EXPECTED_SUBLEVEL."
        warn "Upstream has moved. This build is untested on your device — keep a backup and test-boot."
    fi

    if [[ -x "$CLANG_PATH/bin/clang" ]]; then
        log "Using toolchain at $CLANG_PATH"
    else
        log "Downloading Android Clang r522817 (this is large; expect a wait)..."
        mkdir -p "$CLANG_PATH"
        local url="https://android.googlesource.com/platform/prebuilts/clang/host/linux-x86/+archive/refs/heads/main/clang-r522817.tar.gz"
        # This must be the AOSP prebuilt. The kernel Makefile hardcodes
        #   -mllvm -regalloc-enable-advisor=release
        # which needs an MLGO-enabled clang. A distro clang of the same major
        # version (e.g. Ubuntu 18.1.3) fails immediately on kernel/bounds.s.
        curl -fL --retry 3 -o "$TOOLCHAIN_DIR/clang.tar.gz" "$url" \
            || die "Toolchain download failed. Fetch the AOSP prebuilt clang-r522817 manually (a distro clang will NOT work) and re-run with CLANG_DIR=/path/to/it"
        tar -xzf "$TOOLCHAIN_DIR/clang.tar.gz" -C "$CLANG_PATH"
        rm -f "$TOOLCHAIN_DIR/clang.tar.gz"
        [[ -x "$CLANG_PATH/bin/clang" ]] \
            || die "Toolchain extracted but $CLANG_PATH/bin/clang is missing. The download was probably an error page."
    fi

    if [[ -z "$(docker images -q "$DOCKER_IMAGE" 2>/dev/null)" ]]; then
        log "Building Docker build environment..."
        docker build ${DOCKER_PLATFORM[@]+"${DOCKER_PLATFORM[@]}"} -t "$DOCKER_IMAGE" "$(stage_docker_context)"
    fi
}

# --- Build -------------------------------------------------------------------
build_kernel() {
    log "Starting kernel build..."

    # Size the container to the host instead of assuming a 16-core / 64 GB Mac.
    local jobs mem
    jobs="${BUILD_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
    mem="${BUILD_MEM:-}"
    if [[ -z "$mem" ]]; then
        local total_gb
        total_gb=$(( $(sysctl -n hw.memsize 2>/dev/null || echo $((8*1024**3))) / 1024**3 ))
        mem="$(( total_gb * 3 / 4 ))g"
    fi
    log "Container limits: ${jobs} CPUs, ${mem} memory"
    # CONFIG_LTO_CLANG + CONFIG_THINLTO are on in raphael_defconfig; the ld.lld
    # link step is the memory spike and will OOM well before compilation does.
    if [[ "${mem%g}" =~ ^[0-9]+$ ]] && (( ${mem%g} < 16 )); then
        warn "Under 16 GB for the container — ThinLTO linking may OOM. Set BUILD_MEM to raise it, or disable CONFIG_LTO_CLANG."
    fi

    cp scripts/build_kernel_soviet_docker.sh "$KERNEL_DIR/build_docker.sh"
    cp docker.config "$KERNEL_DIR/docker.config"
    chmod +x "$KERNEL_DIR/build_docker.sh"

    docker run --rm -i ${DOCKER_PLATFORM[@]+"${DOCKER_PLATFORM[@]}"} \
        --name soviet-kernel-builder \
        --cpus="$jobs" \
        --memory="$mem" \
        -v "$KERNEL_DIR":/kernel/soviet_kernel_stock \
        -v "$CLANG_PATH":/opt/clang \
        "$DOCKER_IMAGE" \
        bash /kernel/soviet_kernel_stock/build_docker.sh

    local img="$KERNEL_DIR/out/arch/arm64/boot/Image.gz-dtb"
    [[ -f "$img" ]] || die "Build failed — Image.gz-dtb not produced."

    # The in-tree build script only greps 3 of the 26 fragment flags, and the flag
    # that actually gets dropped by olddefconfig is not one of them. Check all.
    if [[ -f "$KERNEL_DIR/out/.config" ]]; then
        local lost=()
        while read -r line; do
            [[ -z "$line" || "$line" == \#* ]] && continue
            grep -qx -- "$line" "$KERNEL_DIR/out/.config" || lost+=("${line%%=*}")
        done < docker.config
        if (( ${#lost[@]} > 0 )); then
            warn "Dropped by olddefconfig (unmet dependencies): ${lost[*]}"
            warn "Known-benign: CONFIG_NETFILTER_XT_MATCH_IPVS needs CONFIG_IP_VS (Swarm only)."
            read -r -p "Continue with these missing? (y/n) " -n 1 REPLY; echo
            [[ $REPLY =~ ^[Yy]$ ]] || return 1
        else
            log "All ${#lost[@]:-0} fragment flags present in final .config."
        fi
    fi

    # Guard against copying a stale artifact from an earlier run.
    if [[ -n "$(find "$img" -mmin +60 2>/dev/null)" ]]; then
        warn "Image.gz-dtb is over an hour old — this may be a stale artifact, not a fresh build."
        read -r -p "Use it anyway? (y/n) " -n 1 REPLY; echo
        [[ $REPLY =~ ^[Yy]$ ]] || return 1
    fi

    cp "$img" "$OUT_DIR/Image.gz-dtb"
    log "Kernel compiled: $OUT_DIR/Image.gz-dtb ($(du -h "$OUT_DIR/Image.gz-dtb" | cut -f1))"
}

clean_build() {
    log "Cleaning build artifacts..."
    rm -rf "$KERNEL_DIR/out" "$OUT_DIR"
    mkdir -p "$OUT_DIR"
    log "Clean complete."
}

# --- Boot image --------------------------------------------------------------
# The OS patch level must match the running ROM or Keymaster refuses to release
# the FBE keys and Android reports "Your data may be corrupt". Read it from the
# device's own boot image instead of hardcoding a value that goes stale on every
# ROM update.
repack_boot_img() {
    log "Repacking boot image..."

    if [[ ! -f "$STOCK_DIR/ramdisk.cpio.gz" || ! -f "$STOCK_DIR/boot_params.txt" ]]; then
        local src
        src=$(ls -t "$BACKUP_DIR"/boot_backup_*.img 2>/dev/null | head -1 || true)
        [[ -n "$src" ]] || die "No stock boot image available. Run option 4 (Backup) first — it supplies both the ramdisk and the boot parameters."
        log "Extracting ramdisk and parameters from $(basename "$src")"
        python3 scripts/unpack_boot.py "$src" "$STOCK_DIR"
    fi

    local params="$STOCK_DIR/boot_params.txt"
    local patch_level os_version page_size cmdline
    patch_level=$(sed -n 's/^OS Patch Level: //p' "$params")
    os_version=$(sed -n 's/^OS Version: //p' "$params")
    page_size=$(sed -n 's/^Page size: //p' "$params")
    cmdline=$(sed -n 's/^Cmdline: //p' "$params")

    [[ -n "$patch_level" ]] || die "Could not read OS Patch Level from $params — refusing to build an image that will fail to decrypt."
    if [[ "$patch_level" == "2000-00" ]]; then
        die "Stock image reports patch level 2000-00. That backup was not taken from a live device; re-run option 4."
    fi

    log "Inherited from device: patch level $patch_level, OS version $os_version, page size $page_size"

    [[ -f "$OUT_DIR/Image.gz-dtb" ]] || die "No compiled kernel found. Build first (option 2)."

    # Delete any previous image FIRST. Because every menu action is invoked as
    # `func || warn`, bash disables errexit for the whole function body, so a
    # failing mkbootimg does NOT abort this function. mkbootimg also opens
    # --output only after parsing earlier arguments, so an error such as a
    # missing ramdisk leaves the previous boot-personalized.img untouched --
    # and the verification below would then happily re-read that stale image,
    # match its patch level, and report success. The user flashes an old kernel
    # believing it is the one just built.
    rm -f "$BOOT_IMG"

    python3 mkbootimg_src/mkbootimg.py \
        --kernel "$OUT_DIR/Image.gz-dtb" \
        --ramdisk "$STOCK_DIR/ramdisk.cpio.gz" \
        --cmdline "$cmdline" \
        --base "$BOOT_BASE" \
        --pagesize "$page_size" \
        --os_version "$os_version" \
        --os_patch_level "$patch_level" \
        --output "$BOOT_IMG" \
        || { fail "mkbootimg failed - no image written."; return 1; }

    [[ -s "$BOOT_IMG" ]] || { fail "mkbootimg produced no output."; return 1; }
    log "Created $(basename "$BOOT_IMG")"
    log "Verifying written header..."
    python3 scripts/unpack_boot.py "$BOOT_IMG" /tmp/verify_boot >/dev/null
    local written written_ver
    written=$(sed -n 's/^OS Patch Level: //p' /tmp/verify_boot/boot_params.txt)
    written_ver=$(sed -n 's/^OS Version: //p' /tmp/verify_boot/boot_params.txt)
    if [[ "$written" != "$patch_level" ]]; then
        rm -rf /tmp/verify_boot
        fail "Patch level mismatch — wrote '$written', expected '$patch_level'. Do not flash this image."
        return 1
    fi
    # os_version is bound into Keymaster alongside the patch level, so verify it
    # too rather than trusting the patch level alone.
    if [[ "$written_ver" != "$os_version" ]]; then
        rm -rf /tmp/verify_boot
        fail "OS version mismatch — wrote '$written_ver', expected '$os_version'. Do not flash this image."
        return 1
    fi
    log "Verified: patch level $written, OS version $written_ver"
    rm -rf /tmp/verify_boot
}

backup_boot() {
    command -v adb >/dev/null 2>&1 || die "adb is required for backup."
    adb get-state >/dev/null 2>&1 || die "No device in ADB mode."

    mkdir -p "$BACKUP_DIR"
    local stamp dest
    stamp=$(date +%Y%m%d_%H%M%S)
    dest="$BACKUP_DIR/boot_backup_${stamp}.img"

    log "Dumping boot partition (requires root)..."
    adb shell 'su -c "dd if=/dev/block/bootdevice/by-name/boot of=/data/local/tmp/boot_backup.img"' \
        || die "dd failed — is root granted to the shell?"
    adb pull /data/local/tmp/boot_backup.img "$dest" >/dev/null || die "adb pull failed."
    adb shell 'su -c "rm -f /data/local/tmp/boot_backup.img"' || true

    # An Android boot image starts with the magic "ANDROID!".
    if [[ "$(head -c 8 "$dest")" != "ANDROID!" ]]; then
        rm -f "$dest"
        die "Pulled file is not a valid boot image. Backup discarded."
    fi

    log "Backup verified and saved to $dest"
    log "Extracting ramdisk and boot parameters for repack..."
    rm -rf "$STOCK_DIR"
    python3 scripts/unpack_boot.py "$dest" "$STOCK_DIR"
}

# --- Flash -------------------------------------------------------------------
flash_kernel() {
    [[ -f "$BOOT_IMG" ]] || die "No boot image to flash. Run option 3 first."
    ls "$BACKUP_DIR"/boot_backup_*.img >/dev/null 2>&1 \
        || warn "No backup found in $BACKUP_DIR. If this image fails you will need a stock boot.img to recover."

    log "Checking for connected devices..."
    if adb get-state >/dev/null 2>&1; then
        log "Device in ADB mode."
        read -r -p "Reboot to bootloader? (y/n) " -n 1 REPLY; echo
        [[ $REPLY =~ ^[Yy]$ ]] || return 0
        adb reboot bootloader
        log "Waiting for fastboot..."
        fastboot wait-for-device
    elif [[ -n "$(fastboot devices 2>/dev/null)" ]]; then
        log "Device in fastboot mode."
    else
        warn "No device detected."
        return 0
    fi

    echo
    warn "About to overwrite the boot partition. A bad image means a bootloop."
    read -r -p "Type FLASH to continue: " confirm
    [[ "$confirm" == "FLASH" ]] || { log "Cancelled."; return 0; }

    # Boot it first: this leaves the installed kernel untouched if it fails.
    read -r -p "Test-boot the image without flashing first? (recommended) (y/n) " -n 1 REPLY; echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        fastboot boot "$BOOT_IMG" || die "Test boot failed — do not flash this image."
        log "Test boot issued. If the device came up cleanly, re-run this option and skip the test."
        return 0
    fi

    fastboot flash boot "$BOOT_IMG" || die "Flash failed."
    log "Flashed. Rebooting..."
    fastboot reboot
}

# --- Verification ------------------------------------------------------------
# /proc/config.gz is unreliable on this build; test the features functionally.
verify_features() {
    command -v adb >/dev/null 2>&1 || die "adb is required."
    adb get-state >/dev/null 2>&1 || die "No device in ADB mode."

    log "Kernel version:"
    adb shell 'uname -r'

    log "cgroup controllers (looking for 'pids'):"
    adb shell 'cat /proc/cgroups' | awk 'NR==1 || /^(pids|memory|devices|freezer|cpuset)\b/'

    log "Namespaces:"
    adb shell 'ls -l /proc/self/ns/' 2>/dev/null | awk '{print "  " $NF}'

    log "Functional namespace test (the one that actually matters):"
    if adb shell 'su -c "unshare -U -m -n -p -f --mount-proc /system/bin/sh -c \"echo OK\""' 2>/dev/null | grep -q OK; then
        log "  PASS — full namespace creation works. Kernel side is proven."
    else
        warn "  FAIL — namespace creation refused. Check root and SELinux mode."
    fi
}

collect_logs() {
    command -v adb >/dev/null 2>&1 || die "adb is required."
    mkdir -p logs
    local stamp; stamp=$(date +%Y%m%d_%H%M%S)

    # dmesg is root-only on modern Android.
    adb shell 'su -c dmesg' > "logs/dmesg_$stamp.log" 2>/dev/null || warn "dmesg failed (needs root)."
    adb logcat -d > "logs/logcat_$stamp.log" 2>/dev/null || warn "logcat failed."

    # The previous boot's console — the only useful artifact after a bootloop.
    if adb shell 'su -c "test -f /sys/fs/pstore/console-ramoops && echo yes"' 2>/dev/null | grep -q yes; then
        adb shell 'su -c "cat /sys/fs/pstore/console-ramoops"' > "logs/pstore_$stamp.log" 2>/dev/null
        log "Captured pstore console from previous boot."
    else
        warn "No pstore console-ramoops present."
    fi
    log "Logs saved to logs/"
}

create_anykernel_zip() {
    [[ -f "$OUT_DIR/Image.gz-dtb" ]] || die "No compiled kernel found."
    [[ -d AnyKernel3 ]] || die "AnyKernel3/ is missing from the repo — it holds the device-specific anykernel.sh."
    cp "$OUT_DIR/Image.gz-dtb" AnyKernel3/
    ( cd AnyKernel3 && zip -r9 "$WORK_DIR/kernel-installer-$(date +%Y%m%d).zip" . -x '.git/*' 'README.md' '*placeholder' )
    log "Created kernel-installer-$(date +%Y%m%d).zip"
}

rebuild_docker_image() {
    [[ -f Dockerfile ]] || die "Dockerfile not found."
    docker build ${DOCKER_PLATFORM[@]+"${DOCKER_PLATFORM[@]}"} --no-cache -t "$DOCKER_IMAGE" "$(stage_docker_context)"
    log "Docker image rebuilt."
}

update_kernel_source() {
    [[ -d "$KERNEL_DIR/.git" ]] || { warn "No kernel source yet."; setup_environment; return; }
    git -C "$KERNEL_DIR" pull
    log "Kernel source updated."
}

# --- Main --------------------------------------------------------------------
verify_repo_integrity
check_prerequisites
setup_environment

while true; do
    echo ""
    info "=== Docker Kernel Builder — raphael ==="
    echo "1.  Clean build directory"
    echo "2.  Build kernel"
    echo "3.  Repack boot image (inherits patch level from device)"
    echo "4.  Backup current boot image  <-- do this first"
    echo "5.  Flash kernel"
    echo "6.  Create AnyKernel3 zip"
    echo "7.  Verify Docker features on device"
    echo "8.  Collect debug logs (incl. pstore)"
    echo "9.  Rebuild Docker image (force)"
    echo "10. Update kernel source"
    echo "0.  FULL AUTO (backup -> build -> repack -> flash)"
    echo "x.  Exit"
    echo ""
    read -r -p "Select an option: " choice

    # A failure inside one action should not kill the whole session.
    case $choice in
        1)  clean_build          || warn "Clean failed." ;;
        2)  build_kernel         || warn "Build failed." ;;
        3)  repack_boot_img      || warn "Repack failed." ;;
        4)  backup_boot          || warn "Backup failed." ;;
        5)  flash_kernel         || warn "Flash aborted." ;;
        6)  create_anykernel_zip || warn "Zip failed." ;;
        7)  verify_features      || warn "Verification failed." ;;
        8)  collect_logs         || warn "Log collection failed." ;;
        9)  rebuild_docker_image || warn "Image rebuild failed." ;;
        10) update_kernel_source || warn "Update failed." ;;
        0)
            backup_boot && build_kernel && repack_boot_img && flash_kernel \
                || warn "Auto sequence stopped."
            ;;
        x|X) exit 0 ;;
        *)  warn "Invalid option" ;;
    esac
done
