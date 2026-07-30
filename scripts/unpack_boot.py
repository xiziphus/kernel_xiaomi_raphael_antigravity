#!/usr/bin/env python3
"""
Simple boot image unpacker for Android boot.img
Extracts kernel, ramdisk, and DTB from boot image
"""
import struct
import sys
import os

def unpack_boot_img(boot_img_path, output_dir):
    """Unpack Android boot image"""
    
    # Android boot image header format
    # See: https://android.googlesource.com/platform/system/core/+/master/mkbootimg/include/bootimg/bootimg.h
    
    with open(boot_img_path, 'rb') as f:
        # v0 header is 1632 bytes; v1 adds recovery_dtbo (-> 1648); v2 adds
        # dtb_size + dtb_addr (-> 1660). Reading only 1648 truncated the v2
        # tail, so the DTB section was invisible and silently never extracted
        # -- on a v2 image that is where the whole device tree lives.
        header = f.read(1660)

        # Check magic
        magic = header[:8]
        if magic != b'ANDROID!':
            print(f"Error: Not a valid Android boot image (magic: {magic})")
            return False
        
        # Parse header fields (using struct.unpack for little-endian)
        kernel_size = struct.unpack('<I', header[8:12])[0]
        kernel_addr = struct.unpack('<I', header[12:16])[0]
        ramdisk_size = struct.unpack('<I', header[16:20])[0]
        ramdisk_addr = struct.unpack('<I', header[20:24])[0]
        second_size = struct.unpack('<I', header[24:28])[0]
        second_addr = struct.unpack('<I', header[28:32])[0]
        tags_addr = struct.unpack('<I', header[32:36])[0]
        page_size = struct.unpack('<I', header[36:40])[0]
        header_version = struct.unpack('<I', header[40:44])[0]
        
        # Extract os_version and os_patch_level.
        #
        # The 32-bit word packs BOTH values (see mkbootimg.py: it writes
        # (os_version << 11) | os_patch_level, where os_version is itself
        # (a << 14) | (b << 7) | c):
        #
        #   bits 31..25  A  (major)
        #   bits 24..18  B  (minor)
        #   bits 17..11  C  (patch)
        #   bits 10..4   year - 2000
        #   bits  3..0   month
        #
        # This previously read `(packed >> 11) & 0x7F`, which is only C --
        # the major and minor components were silently discarded, so
        # boot_params.txt recorded "OS Version: 0" and the repack passed
        # `--os_version 0`, packing 0.0.0 into every rebuilt image.
        os_version_packed = struct.unpack('<I', header[44:48])[0]
        os_major = (os_version_packed >> 25) & 0x7F
        os_minor = (os_version_packed >> 18) & 0x7F
        os_patch = (os_version_packed >> 11) & 0x7F
        os_version = f"{os_major}.{os_minor}.{os_patch}"
        os_patch_level_year = ((os_version_packed >> 4) & 0x7F) + 2000
        os_patch_level_month = os_version_packed & 0x0F
        
        # Extract cmdline (null-terminated string)
        cmdline = header[64:576].split(b'\x00')[0].decode('utf-8', errors='ignore')

        # v1+ tail: recovery_dtbo_size u32 @1632, recovery_dtbo_offset u64 @1636,
        #           header_size u32 @1644
        # v2  tail: dtb_size u32 @1648, dtb_addr u64 @1652   (total 1660)
        recovery_dtbo_size = 0
        dtb_size = 0
        dtb_addr = 0
        if header_version >= 1:
            recovery_dtbo_size = struct.unpack('<I', header[1632:1636])[0]
        if header_version >= 2:
            dtb_size = struct.unpack('<I', header[1648:1652])[0]
            dtb_addr = struct.unpack('<Q', header[1652:1660])[0]

        print(f"Boot Image Info:")
        print(f"  Header version: {header_version}")
        print(f"  OS Version: {os_version}")
        print(f"  OS Patch Level: {os_patch_level_year}-{os_patch_level_month:02d}")
        print(f"  Page size: {page_size}")
        print(f"  Kernel size: {kernel_size} bytes")
        print(f"  Ramdisk size: {ramdisk_size} bytes")
        print(f"  Second stage size: {second_size} bytes")
        print(f"  Cmdline: {cmdline}")
        
        # Calculate offsets (aligned to page_size)
        def align(size, page_size):
            return ((size + page_size - 1) // page_size) * page_size
        
        kernel_offset = page_size
        ramdisk_offset = kernel_offset + align(kernel_size, page_size)
        second_offset = ramdisk_offset + align(ramdisk_size, page_size)
        # recovery_dtbo sits between second and dtb, so it must be stepped over
        # even when it is empty-but-present.
        dtb_offset = (second_offset + align(second_size, page_size)
                      + align(recovery_dtbo_size, page_size))

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract kernel
        if kernel_size > 0:
            f.seek(kernel_offset)
            kernel_data = f.read(kernel_size)
            kernel_path = os.path.join(output_dir, 'kernel')
            with open(kernel_path, 'wb') as kf:
                kf.write(kernel_data)
            print(f"  Extracted kernel to: {kernel_path}")
        
        # Extract ramdisk
        if ramdisk_size > 0:
            f.seek(ramdisk_offset)
            ramdisk_data = f.read(ramdisk_size)
            ramdisk_path = os.path.join(output_dir, 'ramdisk.cpio.gz')
            with open(ramdisk_path, 'wb') as rf:
                rf.write(ramdisk_data)
            print(f"  Extracted ramdisk to: {ramdisk_path}")
        
        # Extract second stage. On v0 images this slot is where a DTB was
        # conventionally stashed; on v2 the DTB has its own section instead
        # and this is normally empty.
        if second_size > 0:
            f.seek(second_offset)
            second_data = f.read(second_size)
            second_path = os.path.join(output_dir, 'dtb' if header_version < 2 else 'second')
            with open(second_path, 'wb') as sf:
                sf.write(second_data)
            print(f"  Extracted second stage to: {second_path}")

        # Extract the v2 DTB section.
        if dtb_size > 0:
            f.seek(dtb_offset)
            dtb_data = f.read(dtb_size)
            dtb_path = os.path.join(output_dir, 'dtb')
            with open(dtb_path, 'wb') as df:
                df.write(dtb_data)
            magic = dtb_data[:4].hex()
            ok = ' (valid FDT)' if magic == 'd00dfeed' else ' (WARNING: not an FDT magic)'
            print(f"  Extracted DTB to: {dtb_path}  magic={magic}{ok}")

        # Save boot parameters
        params_path = os.path.join(output_dir, 'boot_params.txt')
        with open(params_path, 'w') as pf:
            pf.write(f"Header version: {header_version}\n")
            pf.write(f"OS Version: {os_version}\n")
            pf.write(f"OS Patch Level: {os_patch_level_year}-{os_patch_level_month:02d}\n")
            pf.write(f"Page size: {page_size}\n")
            pf.write(f"Kernel address: 0x{kernel_addr:08x}\n")
            pf.write(f"Ramdisk address: 0x{ramdisk_addr:08x}\n")
            pf.write(f"Second address: 0x{second_addr:08x}\n")
            pf.write(f"Tags address: 0x{tags_addr:08x}\n")
            if header_version >= 2:
                pf.write(f"DTB size: {dtb_size}\n")
                pf.write(f"DTB address: 0x{dtb_addr:08x}\n")
            pf.write(f"Cmdline: {cmdline}\n")
        print(f"  Saved boot parameters to: {params_path}")
        
        return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python3 unpack_boot.py <boot.img> <output_dir>")
        sys.exit(1)
    
    boot_img = sys.argv[1]
    output_dir = sys.argv[2]
    
    if not os.path.exists(boot_img):
        print(f"Error: {boot_img} not found")
        sys.exit(1)
    
    if unpack_boot_img(boot_img, output_dir):
        print(f"\nBoot image successfully unpacked to: {output_dir}")
    else:
        print("\nFailed to unpack boot image")
        sys.exit(1)
