#!/bin/bash
# Kernel Feature Verification Script
# Checks if all Docker features are present on the device

set -e

echo "=== Kernel Feature Verification ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if device is connected
if ! adb devices | grep -q "device$"; then
    echo -e "${RED}✗ No device connected${NC}"
    echo "Please connect your device via ADB"
    exit 1
fi

echo -e "${GREEN}✓ Device connected${NC}"
echo ""

# Check kernel version
echo "--- Kernel Version ---"
KERNEL_VERSION=$(adb shell uname -r 2>/dev/null)
echo "Kernel: $KERNEL_VERSION"

if echo "$KERNEL_VERSION" | grep -q "SOVIET-STAR"; then
    echo -e "${GREEN}✓ Custom kernel detected${NC}"
else
    echo -e "${YELLOW}⚠ Stock or unknown kernel${NC}"
fi
echo ""

# Check namespaces
echo "--- Namespaces ---"
NAMESPACES=("user" "pid" "net" "uts" "ipc" "mnt")
NS_PASS=0
NS_TOTAL=${#NAMESPACES[@]}

for ns in "${NAMESPACES[@]}"; do
    if adb shell "[ -e /proc/self/ns/$ns ]" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $ns namespace"
        ((NS_PASS++))
    else
        echo -e "${RED}✗${NC} $ns namespace MISSING"
    fi
done
echo "Namespaces: $NS_PASS/$NS_TOTAL"
echo ""

# Check cgroups
echo "--- Cgroups ---"
CGROUPS=("pids" "memory" "devices" "freezer" "cpuset")
CG_PASS=0
CG_TOTAL=${#CGROUPS[@]}

CGROUP_DATA=$(adb shell cat /proc/cgroups 2>/dev/null)

for cg in "${CGROUPS[@]}"; do
    if echo "$CGROUP_DATA" | grep -q "^$cg"; then
        echo -e "${GREEN}✓${NC} $cg cgroup"
        ((CG_PASS++))
    else
        echo -e "${RED}✗${NC} $cg cgroup MISSING"
    fi
done
echo "Cgroups: $CG_PASS/$CG_TOTAL"
echo ""

# Check filesystems
echo "--- Filesystems ---"
FILESYSTEMS=("overlay" "ext4" "proc" "sysfs")
FS_PASS=0
FS_TOTAL=${#FILESYSTEMS[@]}

FS_DATA=$(adb shell cat /proc/filesystems 2>/dev/null)

for fs in "${FILESYSTEMS[@]}"; do
    if echo "$FS_DATA" | grep -q "$fs"; then
        echo -e "${GREEN}✓${NC} $fs filesystem"
        ((FS_PASS++))
    else
        echo -e "${RED}✗${NC} $fs filesystem MISSING"
    fi
done
echo "Filesystems: $FS_PASS/$FS_TOTAL"
echo ""

# Test namespace creation
echo "--- Functional Tests ---"
if adb shell "su -c 'unshare -u -p -f sh -c exit'" 2>/dev/null; then
    echo -e "${GREEN}✓${NC} Namespace creation works"
else
    echo -e "${RED}✗${NC} Namespace creation failed"
fi

# Check root access
if adb shell "su -c 'id'" 2>/dev/null | grep -q "uid=0"; then
    echo -e "${GREEN}✓${NC} Root access available"
else
    echo -e "${YELLOW}⚠${NC} Root access not available (needed for Docker)"
fi
echo ""

# Summary
echo "=== Summary ==="
TOTAL_CHECKS=$((NS_TOTAL + CG_TOTAL + FS_TOTAL))
TOTAL_PASS=$((NS_PASS + CG_PASS + FS_PASS))
PERCENTAGE=$((TOTAL_PASS * 100 / TOTAL_CHECKS))

echo "Total Checks: $TOTAL_PASS/$TOTAL_CHECKS ($PERCENTAGE%)"
echo ""

if [ $PERCENTAGE -ge 90 ]; then
    echo -e "${GREEN}✓ Kernel is Docker-ready!${NC}"
    echo ""
    echo "Note: Kernel features are present, but Docker runtime may still be"
    echo "blocked by Android's PIE enforcement. See FAQ.md for details."
    exit 0
elif [ $PERCENTAGE -ge 70 ]; then
    echo -e "${YELLOW}⚠ Most features present, but some are missing${NC}"
    echo "Check the output above for details."
    exit 1
else
    echo -e "${RED}✗ Many features are missing${NC}"
    echo "This kernel may not have Docker support enabled."
    exit 1
fi
