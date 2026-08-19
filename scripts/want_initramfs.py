#!/usr/bin/env python3
"""Rewrite `skip_initramfs` to `want_initramfs` inside a built Image.gz-dtb.

raphael is a legacy system-as-root device: the bootloader passes
`skip_initramfs`, the kernel mounts /system as root and IGNORES the initramfs
entirely. Magisk lives only in the ramdisk, so magiskinit never runs -- the
device boots perfectly and silently has no root. Nothing logs a complaint.

Magisk's historical fix is a hexpatch of this one string, and the two names are
the same length so it is an in-place edit. KameOS's own kernel already carries
it, which is what made the difference visible:

    ROM (Zundamon)   skip_initramfs=0  want_initramfs=2
    ours (A7rk)      skip_initramfs=1  want_initramfs=0

Note that Magisk's current boot_patch.sh does NOT apply it -- running the
device's own /data/adb/magisk/boot_patch.sh over our image left the string
untouched and produced an equally rootless boot. So we do it ourselves.

This works on the packed Image.gz-dtb: gunzip the kernel, patch, re-gzip, and
re-append the DTB blob that followed the gzip stream.

Usage: want_initramfs.py <Image.gz-dtb> [out]   (default: patch in place)
"""
import gzip
import io
import sys
import zlib

def main(src, dst):
    d = open(src, "rb").read()
    if not d.startswith(b"\x1f\x8b\x08"):
        sys.exit("FATAL: %s does not start with a gzip stream" % src)
    z = zlib.decompressobj(16 + 15)
    img = z.decompress(d)
    dtb = z.unused_data          # appended DTB, if any
    n = img.count(b"skip_initramfs")
    if n == 0:
        if img.count(b"want_initramfs"):
            print("  want_initramfs: already patched")
        else:
            print("  want_initramfs: WARNING -- neither string present; this "
                  "kernel may not honour the bootloader's skip_initramfs at all")
        return
    img = img.replace(b"skip_initramfs", b"want_initramfs")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as g:
        g.write(img)
    out = buf.getvalue() + dtb
    open(dst, "wb").write(out)
    print("  want_initramfs: patched %d occurrence(s) (kernel %d B, dtb %d B)"
          % (n, len(img), len(dtb)))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
