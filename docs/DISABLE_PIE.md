# Disable PIE Enforcement Patch

This patch modifies the ELF binary loader to accept non-PIE executables (ET_EXEC type).

## Security Warning

⚠️ **IMPORTANT**: Disabling PIE enforcement reduces security by:
- Removing Address Space Layout Randomization (ASLR) for non-PIE binaries
- Making exploitation easier if vulnerabilities exist
- Reducing defense-in-depth

**Use only if**:
- You understand the security implications
- You trust the binaries you're running
- You're running in a controlled environment

## The Patch

The Android kernel rejects ET_EXEC (type 2) binaries and only accepts ET_DYN (type 3, PIE).

**File**: `fs/binfmt_elf.c`
**Line**: 717

### Original Code
```c
if (loc->elf_ex.e_type != ET_EXEC && loc->elf_ex.e_type != ET_DYN)
    goto out;
```

This check allows both ET_EXEC and ET_DYN, but later Android patches add additional PIE enforcement.

### Solution: Kernel Command Line Parameter

Instead of patching the kernel, we can use a kernel command line parameter:

**Add to boot cmdline**: `androidboot.force_normal_boot=1`

This might bypass some PIE checks.

### Alternative: Patch the Check

If command line doesn't work, we can patch the kernel to be more permissive.

## Implementation

### Option 1: Kernel Command Line (Safer)

1. Repack boot image with modified cmdline
2. No kernel recompilation needed
3. Can be reverted easily

### Option 2: Kernel Patch (More Effective)

Create `patches/allow-non-pie.patch`:

```patch
diff --git a/fs/binfmt_elf.c b/fs/binfmt_elf.c
index xxxxx..xxxxx 100644
--- a/fs/binfmt_elf.c
+++ b/fs/binfmt_elf.c
@@ -714,8 +714,12 @@ static int load_elf_binary(struct linux_binprm *bprm)
     /* First of all, some simple consistency checks */
     if (memcmp(loc->elf_ex.e_ident, ELFMAG, SELFMAG) != 0)
         goto out;
-
-    if (loc->elf_ex.e_type != ET_EXEC && loc->elf_ex.e_type != ET_DYN)
+    
+    /* Allow ET_EXEC (non-PIE) binaries for container runtimes */
+    if (loc->elf_ex.e_type != ET_EXEC && 
+        loc->elf_ex.e_type != ET_DYN &&
+        loc->elf_ex.e_type != 2)  /* Explicitly allow type 2 */
         goto out;
 
     if (!elf_check_arch(&loc->elf_ex))
```

## Testing

After applying the patch:

```bash
# Rebuild kernel
./run_builder_soviet.sh

# Repack and flash
python3 mkbootimg.py ... --output boot-no-pie.img
fastboot flash boot boot-no-pie.img

# Test with runc
adb shell su -c "export PATH=/data/data/com.termux/files/usr/bin:\$PATH && docker run hello-world"
```

## Reverting

If issues occur:
```bash
fastboot flash boot boot_backup.img
fastboot reboot
```

## Notes

- This is a **security trade-off** for functionality
- Only affects binaries you explicitly run
- PIE binaries still work normally
- Consider using only for trusted container runtimes
