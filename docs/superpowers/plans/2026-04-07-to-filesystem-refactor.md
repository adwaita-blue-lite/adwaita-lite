# bootc to-filesystem Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `bootc install to-disk --wipe` with caller-managed partitioning (`sfdisk` + `mkfs`) and `bootc install to-filesystem`, eliminating ostree bug #1343 and the fragile post-install remount heuristic.

**Architecture:** The single `_step_bootc_install` method (which called `to-disk` then `_mount_sysroot`) splits into two steps: `_step_partition_disk` (sfdisk + mkfs + mount) and `_step_install_system` (bootc to-filesystem). The `_mount_sysroot` and `_unmount_sysroot` helpers are deleted along with all OSTree GI bindings and ref-cleanup workarounds. Post-install steps are unchanged — they already write to `self._sysroot_deploy` and `self._sysroot_var`, which are now set during partition rather than after remount.

**Tech Stack:** Python 3, GTK4 (PyGObject), sfdisk, mkfs.vfat, mkfs.ext4, mkfs.xfs, mkfs.btrfs, blkid, bootc

**Spec:** `docs/superpowers/specs/2026-04-07-to-filesystem-refactor-design.md`

---

## File Structure

Only one file is modified:

- **Modify:** `files/usr/bin/adwaita-lite-setup-wizard`
  - Delete: `_mount_sysroot()`, `_unmount_sysroot()`, ostree ref cleanup block, `gi.require_version("OSTree", "1.0")` import
  - Add: `_step_partition_disk()`, `_step_install_system()`
  - Modify: `_step_finalize()` (unmount path changes), `_on_setup_clicked()` (step list)

No new files. No test files (this is a single-file GTK wizard with no test harness — testing is manual per the spec's testing section).

---

### Task 1: Delete dead code — `_mount_sysroot`, `_unmount_sysroot`, OSTree GI bindings

Remove the code that will be replaced. Do this first so subsequent tasks start from a clean slate.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2214-2301` (delete `_mount_sysroot` and `_unmount_sysroot`)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2329-2350` (delete ostree ref cleanup block inside `_step_bootc_install`)

- [ ] **Step 1: Delete `_mount_sysroot` method**

Delete the entire `_mount_sysroot` method (lines 2214–2290). This includes the "largest partition" heuristic, the `gi.require_version("OSTree", "1.0")` import, the `OSTree.Sysroot` API call, the glob fallback, and the /var subdirectory initialization.

Remove from `def _mount_sysroot(self) -> str | None:` through the `return None` at the end of the method.

- [ ] **Step 2: Delete `_unmount_sysroot` method**

Delete the entire `_unmount_sysroot` method (lines 2292–2301). This is a simple `umount -R self._sysroot_mount` wrapper.

- [ ] **Step 3: Delete ostree ref cleanup block in `_step_bootc_install`**

Inside `_step_bootc_install`, delete the entire `# Workaround for bootc bug #1343` block (lines 2329–2350). This is the `ostree refs` + `ostree prune` workaround that never reliably fixed the bug.

- [ ] **Step 4: Delete the remainder of `_step_bootc_install`**

Delete the entire `_step_bootc_install` method. It will be replaced by two new methods in Tasks 2 and 3. After this step, the method should not exist at all.

- [ ] **Step 5: Verify no remaining OSTree GI references**

Search the file for `OSTree` (case-sensitive). The only remaining references should be in comments about ostree deployment paths (which are still valid — bootc to-filesystem creates the same ostree layout). There should be no `gi.require_version("OSTree"` or `from gi.repository import OSTree` left.

- [ ] **Step 6: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "refactor(wizard): remove to-disk code path and OSTree GI bindings

Removes _mount_sysroot, _unmount_sysroot, _step_bootc_install, and the
ostree ref cleanup workaround for bug #1343. These are replaced in the
next commits by caller-managed partitioning + bootc to-filesystem."
```

---

### Task 2: Add `_step_partition_disk`

Create the new partitioning step that replaces the first half of the old `_step_bootc_install`. This step creates a GPT partition table with sfdisk, formats each partition, mounts them in the correct order, and sets `self._sysroot_deploy`/`self._sysroot_var` path attributes for downstream steps.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — add new method after the `# Install pipeline steps` comment (around line 2305)

- [ ] **Step 1: Write `_step_partition_disk` method**

Insert this method right after the `_get_booted_image_name` method (after the `# Install pipeline steps` section header and `_get_booted_image_name`):

```python
    def _step_partition_disk(self) -> str | None:
        """Create GPT partition table, format, and mount target disk.

        Partition layout (matches Anaconda/Readymade pattern):
          1: BIOS boot   —   1 MiB  — no filesystem (for grub-install)
          2: EFI System  — 512 MiB  — FAT32
          3: XBOOTLDR    —   1 GiB  — ext4
          4: Linux root  — remaining — user's choice (ext4/xfs/btrfs)

        Sets self._mount_point and self._root_uuid for _step_install_system.
        """
        target = self._setup_target_drive
        fs = self._setup_filesystem
        dev = f"/dev/{target}"
        mount_point = "/mnt/target"

        # --- Wipe and partition with sfdisk ---
        sfdisk_script = (
            "label: gpt\n"
            "size=1MiB,  type=21686148-6449-6E6F-744E-656564454649\n"  # BIOS boot
            "size=512MiB,type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B\n"  # EFI System
            "size=1GiB,  type=BC13C2FF-59E6-4262-A352-B275FD6F7172\n"  # XBOOTLDR
            ",            type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n"  # Linux root
        )
        try:
            self._run_logged(
                ["sfdisk", "--wipe", "always", "--wipe-partitions", "always", dev],
                input=sfdisk_script.encode(),
                check=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            return f"Partitioning failed: {(exc.output or '').strip().splitlines()[-1:] or exc}"
        except subprocess.TimeoutExpired:
            return "Partitioning timed out"

        # Give the kernel a moment to re-read the partition table
        subprocess.run(["partprobe", dev], capture_output=True, timeout=10)
        subprocess.run(["udevadm", "settle", "--timeout=5"], capture_output=True, timeout=10)

        # Discover partition device names (handles both sdX1 and nvme0n1p1 styles)
        try:
            result = subprocess.run(
                ["lsblk", "-lnpo", "NAME,TYPE", dev],
                capture_output=True, text=True, check=True, timeout=10,
            )
            parts = [
                line.split()[0] for line in result.stdout.strip().splitlines()
                if len(line.split()) >= 2 and line.split()[1] == "part"
            ]
            if len(parts) < 4:
                return f"Expected 4 partitions, found {len(parts)}: {parts}"
        except subprocess.CalledProcessError as exc:
            return f"Failed to list partitions: {exc.stderr.strip() or exc}"

        part_efi, part_boot, part_root = parts[1], parts[2], parts[3]
        # parts[0] is BIOS boot — no filesystem

        # --- Format partitions ---
        mkfs_cmds = [
            (["mkfs.vfat", "-F", "32", "-n", "EFI", part_efi], "EFI"),
            (["mkfs.ext4", "-F", "-L", "boot", part_boot], "boot"),
        ]
        if fs == "btrfs":
            mkfs_cmds.append((["mkfs.btrfs", "-f", "-L", "root", part_root], "root"))
        elif fs == "xfs":
            mkfs_cmds.append((["mkfs.xfs", "-f", "-L", "root", part_root], "root"))
        else:
            mkfs_cmds.append((["mkfs.ext4", "-F", "-L", "root", part_root], "root"))

        for cmd, label in mkfs_cmds:
            try:
                self._run_logged(cmd, check=True, timeout=60)
            except subprocess.CalledProcessError as exc:
                return f"Failed to format {label} partition: {(exc.output or '').strip().splitlines()[-1:] or exc}"
            except subprocess.TimeoutExpired:
                return f"Formatting {label} partition timed out"

        # --- Read root partition UUID for bootc --root-mount-spec ---
        try:
            result = subprocess.run(
                ["blkid", "-s", "UUID", "-o", "value", part_root],
                capture_output=True, text=True, check=True, timeout=10,
            )
            self._root_uuid = result.stdout.strip()
            if not self._root_uuid:
                return "blkid returned empty UUID for root partition"
        except subprocess.CalledProcessError as exc:
            return f"Failed to read root UUID: {exc.stderr.strip() or exc}"

        # --- Mount in correct order: root, then /boot, then /boot/efi ---
        Path(mount_point).mkdir(parents=True, exist_ok=True)

        mount_sequence = [
            (part_root, mount_point),
            (part_boot, f"{mount_point}/boot"),
            (part_efi, f"{mount_point}/boot/efi"),
        ]
        for part_dev, mnt in mount_sequence:
            Path(mnt).mkdir(parents=True, exist_ok=True)
            try:
                self._run_logged(
                    ["mount", part_dev, mnt],
                    check=True, timeout=30,
                )
            except subprocess.CalledProcessError as exc:
                # Clean up any already-mounted paths
                subprocess.run(["umount", "-R", mount_point],
                               capture_output=True, timeout=10)
                return f"Failed to mount {mnt}: {(exc.output or '').strip().splitlines()[-1:] or exc}"

        self._mount_point = mount_point
        return None
```

- [ ] **Step 2: Update `_run_logged` to accept `input` parameter**

The current `_run_logged` uses a temp file for stdout but doesn't support passing stdin data. `sfdisk` needs its partition script on stdin. Add `input` support:

Find this block in `_run_logged`:

```python
        self._log(f"$ {' '.join(str(c) for c in cmd)}\n")

        import tempfile
        log_path = tempfile.mktemp(suffix=".log")
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        proc = subprocess.Popen(
            cmd, stdout=log_fd, stderr=subprocess.STDOUT,
            close_fds=True, start_new_session=True,
            preexec_fn=_reset_child_signals,
            **kwargs,
        )
        os.close(log_fd)  # Parent doesn't need the write end
```

Replace with:

```python
        self._log(f"$ {' '.join(str(c) for c in cmd)}\n")

        stdin_data = kwargs.pop("input", None)

        import tempfile
        log_path = tempfile.mktemp(suffix=".log")
        log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)

        proc = subprocess.Popen(
            cmd, stdout=log_fd, stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
            close_fds=True, start_new_session=True,
            preexec_fn=_reset_child_signals,
            **kwargs,
        )
        os.close(log_fd)  # Parent doesn't need the write end

        # Feed stdin data and close the pipe so the child sees EOF
        if stdin_data is not None:
            try:
                proc.stdin.write(stdin_data if isinstance(stdin_data, bytes)
                                 else stdin_data.encode())
            finally:
                proc.stdin.close()
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(wizard): add _step_partition_disk with sfdisk + mkfs + mount

Creates GPT layout: BIOS boot (1 MiB) + EFI (512 MiB) + XBOOTLDR
(1 GiB) + root (remaining, user's filesystem choice). Mounts in
correct order for bootc to-filesystem. Also adds stdin/input support
to _run_logged for sfdisk's partition script."
```

---

### Task 3: Add `_step_install_system`

Create the new bootc install step that replaces the second half of the old `_step_bootc_install`.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — add new method after `_step_partition_disk`

- [ ] **Step 1: Write `_step_install_system` method**

Insert this method immediately after `_step_partition_disk`:

```python
    def _step_install_system(self) -> str | None:
        """Install OS image into the mounted target via bootc to-filesystem."""
        image_name = self._get_booted_image_name()
        if not image_name:
            return ("Could not determine the booted image reference. "
                    "Is this system booted from a bootc image?")

        mount_point = self._mount_point

        cmd = [
            "bootc", "install", "to-filesystem",
            "--source-imgref", f"docker://{image_name}",
            "--bootloader", "grub",
            "--root-mount-spec", f"UUID={self._root_uuid}",
            mount_point,
        ]

        try:
            self._run_logged(cmd, check=True, timeout=900)
        except subprocess.CalledProcessError as exc:
            lines = (exc.output or "").strip().splitlines()
            tail = "\n".join(lines[-5:]) if lines else str(exc)
            return f"Installation failed: {tail}"
        except subprocess.TimeoutExpired:
            return "Installation timed out after 15 minutes"

        # Locate the ostree deployment directory for post-install steps.
        # bootc to-filesystem creates the standard ostree layout under our
        # mount point.  We glob for it (same approach Anaconda uses) —
        # sorted so [-1] picks the highest-serial deployment.
        deploy_dirs = sorted(Path(mount_point).glob("ostree/deploy/*/deploy/*/"))
        if not deploy_dirs:
            return "No ostree deployment found after install"
        self._sysroot_deploy = str(deploy_dirs[-1])

        var_dirs = list(Path(mount_point).glob("ostree/deploy/*/var"))
        if not var_dirs:
            return "No var directory found after install"
        self._sysroot_var = str(var_dirs[0])

        # Initialize standard /var subdirectories that ostree expects
        # (on ostree systems /home, /root, /srv etc. are symlinks into /var)
        for subdir in ["home", "roothome", "opt", "srv", "usrlocal",
                        "mnt", "media", "spool/mail"]:
            Path(self._sysroot_var, subdir).mkdir(parents=True, exist_ok=True)

        return None
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(wizard): add _step_install_system with bootc to-filesystem

Calls bootc install to-filesystem with --bootloader grub and
--root-mount-spec UUID=<root>. Discovers the ostree deployment
via glob (same pattern as Anaconda). Sets _sysroot_deploy and
_sysroot_var for downstream post-install steps."
```

---

### Task 4: Update `_step_finalize` to use `/mnt/target`

Replace the `_unmount_sysroot()` call with a direct `umount -R /mnt/target`.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — `_step_finalize` method

- [ ] **Step 1: Replace unmount logic in `_step_finalize`**

Find this block at the end of `_step_finalize`:

```python
        # Flush writes before unmounting
        os.sync()

        # Unmount sysroot
        err = self._unmount_sysroot()
        if err:
            return err

        return None
```

Replace with:

```python
        # Flush writes before unmounting
        os.sync()

        # Unmount all target filesystems (root, /boot, /boot/efi)
        try:
            subprocess.run(
                ["umount", "-R", self._mount_point],
                check=True, capture_output=True, text=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            return f"Failed to unmount target: {exc.stderr.strip() or exc}"

        return None
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "fix(wizard): finalize step unmounts /mnt/target instead of old sysroot path"
```

---

### Task 5: Update `_on_setup_clicked` step list

Change the step list from one combined step to two separate steps with updated labels.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — `_on_setup_clicked` method

- [ ] **Step 1: Replace the step list definition**

Find this block in `_on_setup_clicked`:

```python
        # Build step list: (english_label, callable, error_behavior)
        # error_behavior: "fatal" = Back button, "retry" = Retry button,
        #                 "skippable" = Skip + Retry buttons
        self._steps: list[tuple[str, callable, str]] = [
            (N_("Partitioning and installing"), self._step_bootc_install, "fatal"),
            (N_("Configuring user account"), self._step_configure_user, "retry"),
            (N_("Copying network configuration"), self._step_copy_network, "retry"),
        ]
```

Replace with:

```python
        # Build step list: (english_label, callable, error_behavior)
        # error_behavior: "fatal" = Back button, "retry" = Retry button,
        #                 "skippable" = Skip + Retry buttons
        self._steps: list[tuple[str, callable, str]] = [
            (N_("Partitioning disk"), self._step_partition_disk, "fatal"),
            (N_("Installing system"), self._step_install_system, "fatal"),
            (N_("Configuring user account"), self._step_configure_user, "retry"),
            (N_("Copying network configuration"), self._step_copy_network, "retry"),
        ]
```

Both partitioning and installing are "fatal" — if either fails, the user needs to go back and potentially change the target drive.

- [ ] **Step 2: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(wizard): split install into two progress steps for better feedback

'Partitioning and installing' becomes 'Partitioning disk' + 'Installing
system'. Both are fatal — user can go back to change drive on failure."
```

---

### Task 6: Clean up stale references

Verify and fix any remaining references to the old code paths.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

- [ ] **Step 1: Remove the `Sysroot management` section header comment**

The section header at line ~2210-2212 reads:

```python
    # ------------------------------------------------------------------
    # Sysroot management (installer mode)
    # ------------------------------------------------------------------
```

This section is now empty (its methods were deleted in Task 1). Delete these three comment lines.

- [ ] **Step 2: Verify no stale `_sysroot_mount` references remain**

Search the file for `_sysroot_mount`. There should be zero hits — all references should now use `self._mount_point`. If any remain, update them.

- [ ] **Step 3: Verify no stale `_step_bootc_install` references remain**

Search the file for `_step_bootc_install`. There should be zero hits. If any remain (e.g., in comments), remove them.

- [ ] **Step 4: Verify the docstring is still accurate**

The file's module docstring (lines 1-19) does not mention specific install steps, just the page flow. Confirm it still accurately describes the wizard. No changes expected.

- [ ] **Step 5: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "chore(wizard): remove stale section header and verify no dead references"
```

---

### Task 7: Final review and integration commit

Do a full read-through of the modified install pipeline to catch any issues.

**Files:**
- Read: `files/usr/bin/adwaita-lite-setup-wizard` (the install pipeline section)

- [ ] **Step 1: Read the complete install pipeline**

Read from `_get_booted_image_name` through `_step_finalize` and verify:

1. `_step_partition_disk` sets `self._mount_point` and `self._root_uuid`
2. `_step_install_system` reads `self._mount_point` and `self._root_uuid`, sets `self._sysroot_deploy` and `self._sysroot_var`
3. `_step_configure_user` reads `self._sysroot_deploy` and `self._sysroot_var` (unchanged)
4. `_step_copy_network` reads `self._sysroot_deploy` (unchanged)
5. `_step_copy_flatpaks` reads `self._sysroot_var` (unchanged)
6. `_step_configure_memory` reads `self._sysroot_deploy` and `self._sysroot_var` (unchanged)
7. `_step_finalize` reads `self._sysroot_deploy`, `self._sysroot_var`, and `self._mount_point`
8. No method references `self._sysroot_mount` (old name)
9. No method calls `_mount_sysroot()` or `_unmount_sysroot()`
10. No `gi.require_version("OSTree"` or `from gi.repository import OSTree` exists

- [ ] **Step 2: Verify step list in `_on_setup_clicked`**

Confirm the step list is:
1. "Partitioning disk" → `_step_partition_disk` → "fatal"
2. "Installing system" → `_step_install_system` → "fatal"
3. "Configuring user account" → `_step_configure_user` → "retry"
4. "Copying network configuration" → `_step_copy_network` → "retry"
5. (conditional) "Installing selected apps" → `_step_copy_flatpaks` → "skippable"
6. "Configuring memory management" → `_step_configure_memory` → "retry"
7. "Finalizing" → `_step_finalize` → "retry"

- [ ] **Step 3: Verify `_run_logged` stdin handling is correct**

Confirm:
- `stdin_data` is popped from kwargs before passing to Popen
- `stdin=subprocess.PIPE` is set when input is provided, `subprocess.DEVNULL` otherwise
- The pipe is written and closed in a try/finally
- Non-sfdisk callers (bootc, rsync, restorecon) don't pass `input` and get DEVNULL

- [ ] **Step 4: Squash into a clean feature commit (optional)**

If the repository prefers clean history, squash Tasks 1-6 into a single commit:

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(wizard): switch from bootc to-disk to to-filesystem

Replace the single 'bootc install to-disk --wipe' call with:
1. Caller-managed partitioning via sfdisk + mkfs
2. bootc install to-filesystem into the mounted target

This eliminates ostree bug #1343 ('Multiple commit objects found'),
removes the fragile post-install remount heuristic, and aligns with
the Anaconda/Readymade installation pattern.

Partition layout: BIOS boot (1 MiB) + EFI (512 MiB) + XBOOTLDR
(1 GiB) + root (remaining, user's choice of ext4/xfs/btrfs).

Removes: _mount_sysroot, _unmount_sysroot, OSTree GI bindings,
ostree ref cleanup workaround, largest-partition heuristic."
```

---

## Execution Checklist

After all tasks complete, manually test per the spec:

1. Fresh disk (no partition table) → partitions created, OS installed, boots
2. Previously installed disk → partitions recreated, clean install
3. ext4, xfs, btrfs root filesystems all work
4. EFI and BIOS boot both work (BIOS boot partition present)
5. Post-install steps (user, network, flatpaks, memory, finalize) still work
6. Reboot → greetd starts → user can log in
