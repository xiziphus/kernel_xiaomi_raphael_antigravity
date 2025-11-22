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
        # Read header (1648 bytes for v0/v1/v2)
        header = f.read(1648)
        
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
        
        # Extract os_version and os_patch_level
        os_version_packed = struct.unpack('<I', header[44:48])[0]
        os_version = (os_version_packed >> 11) & 0x7F
        os_patch_level_year = ((os_version_packed >> 4) & 0x7F) + 2000
        os_patch_level_month = os_version_packed & 0x0F
        
        # Extract cmdline (null-terminated string)
        cmdline = header[64:576].split(b'\x00')[0].decode('utf-8', errors='ignore')
        
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
        
        # Extract second stage (if present, often DTB)
        if second_size > 0:
            f.seek(second_offset)
            second_data = f.read(second_size)
            second_path = os.path.join(output_dir, 'dtb')
            with open(second_path, 'wb') as sf:
                sf.write(second_data)
            print(f"  Extracted second/DTB to: {second_path}")
        
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
