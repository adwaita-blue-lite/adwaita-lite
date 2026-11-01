# Encrypted Disk Swap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Encrypt the disk swap file with a per-boot random key so passwords and credentials never sit in plaintext on disk.

**Architecture:** A systemd oneshot service wraps `/var/swap` in dm-crypt (plain mode, random key from `/dev/urandom`) on every boot. The setup wizard enables this service instead of directly activating swap.

**Tech Stack:** bash, systemd, dm-crypt/cryptsetup, losetup, Python/GTK4 (wizard)

**Spec:** `docs/superpowers/specs/2026-03-25-encrypted-swap-design.md`

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Create | `files/usr/libexec/adwaita-lite-encrypted-swap` | Shell script: start/stop encrypted swap |
| Create | `files/etc/systemd/system/adwaita-lite-encrypted-swap.service` | Systemd unit to run the script |
| Modify | `build_files/build.sh` | Add `cryptsetup` package + chmod new script |
| Modify | `files/usr/bin/adwaita-lite-setup-wizard` | Replace direct mkswap/swapon with service enable |

---

### Task 1: Create the encrypted swap script

**Files:**
- Create: `files/usr/libexec/adwaita-lite-encrypted-swap`

- [ ] **Step 1: Create the script**

```bash
#!/bin/bash
# Manages encrypted swap on /var/swap using dm-crypt with a random per-boot key.
# Called by adwaita-lite-encrypted-swap.service.

set -euo pipefail

SWAPFILE=/var/swap
MAPPER=cryptswap
LOOP_STATE=/run/adwaita-lite-swap-loop

start() {
    [ -f "$SWAPFILE" ] || exit 0

    cleanup() {
        cryptsetup close "$MAPPER" 2>/dev/null || true
        [ -n "${LOOP:-}" ] && losetup -d "$LOOP" 2>/dev/null || true
        rm -f "$LOOP_STATE"
    }
    trap cleanup ERR

    LOOP=$(losetup --find --show "$SWAPFILE")
    echo "$LOOP" > "$LOOP_STATE"

    cryptsetup open \
        --type plain \
        --cipher aes-xts-plain64 \
        --key-size 512 \
        --key-file /dev/urandom \
        "$LOOP" "$MAPPER"

    mkswap "/dev/mapper/$MAPPER"
    swapon "/dev/mapper/$MAPPER"
}

stop() {
    swapoff "/dev/mapper/$MAPPER" 2>/dev/null || true
    cryptsetup close "$MAPPER" 2>/dev/null || true

    if [ -f "$LOOP_STATE" ]; then
        LOOP=$(cat "$LOOP_STATE")
        losetup -d "$LOOP" 2>/dev/null || true
        rm -f "$LOOP_STATE"
    fi
}

case "${1:-}" in
    start) start ;;
    stop)  stop  ;;
    *)     echo "Usage: $0 {start|stop}" >&2; exit 1 ;;
esac
```

- [ ] **Step 2: Verify with shellcheck**

Run: `shellcheck files/usr/libexec/adwaita-lite-encrypted-swap`
Expected: No errors (warnings about `cat` are acceptable).

- [ ] **Step 3: Commit**

```bash
git add files/usr/libexec/adwaita-lite-encrypted-swap
git commit -m "feat: add encrypted swap script (dm-crypt with random per-boot key)"
```

---

### Task 2: Create the systemd service unit

**Files:**
- Create: `files/etc/systemd/system/adwaita-lite-encrypted-swap.service`

- [ ] **Step 1: Create the unit file**

```ini
[Unit]
Description=Encrypted swap
After=local-fs.target
Before=swap.target
ConditionPathExists=/var/swap

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/libexec/adwaita-lite-encrypted-swap start
ExecStop=/usr/libexec/adwaita-lite-encrypted-swap stop

[Install]
WantedBy=swap.target
```

- [ ] **Step 2: Commit**

```bash
git add files/etc/systemd/system/adwaita-lite-encrypted-swap.service
git commit -m "feat: add systemd unit for encrypted swap"
```

---

### Task 3: Update build.sh

**Files:**
- Modify: `build_files/build.sh:17-76` (add cryptsetup to dnf5 install)
- Modify: `build_files/build.sh:96-102` (add chmod for new script)

- [ ] **Step 1: Add `cryptsetup` to the package list**

Insert `cryptsetup \` after `cups \` (line 25) in the `dnf5 install` block. Alphabetical order.

- [ ] **Step 2: Add chmod for the new script**

Add `/usr/libexec/adwaita-lite-encrypted-swap \` to the `chmod 0755` block (line 96-102), after `adwaita-lite-apply-settings`.

- [ ] **Step 3: Verify build.sh syntax**

Run: `bash -n build_files/build.sh`
Expected: No output (clean parse).

- [ ] **Step 4: Commit**

```bash
git add build_files/build.sh
git commit -m "feat: add cryptsetup package and chmod for encrypted swap script"
```

---

### Task 4: Update the setup wizard

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:711-734`

- [ ] **Step 1: Replace mkswap/var-swap.swap/swapon with service enable**

In `_create_account()`, the zswap block after `chmod 600` (lines 711-734) currently does:
- `mkswap /var/swap`
- Writes `/etc/systemd/system/var-swap.swap` unit
- `systemctl enable var-swap.swap`
- `swapon /var/swap`

Replace all of that with a single call:

```python
                    subprocess.run(
                        ["systemctl", "enable", "adwaita-lite-encrypted-swap.service"],
                        check=True, capture_output=True, text=True,
                    )
```

The lines to remove are 711-734 (from the `mkswap` call through the `swapon` call). The `dd` and `chmod 600` calls above (lines 702-710) stay unchanged.

- [ ] **Step 2: Verify wizard syntax**

Run: `python3 -m py_compile files/usr/bin/adwaita-lite-setup-wizard`
Expected: No output (clean compile).

- [ ] **Step 3: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: wizard uses encrypted swap service instead of plaintext mkswap"
```

---

### Task 5: Final verification and push

- [ ] **Step 1: Run all lints**

```bash
just lint  # shellcheck on *.sh files
just check # Justfile syntax
shellcheck files/usr/libexec/adwaita-lite-encrypted-swap  # not covered by just lint (no .sh extension)
bash -n build_files/build.sh
python3 -m py_compile files/usr/bin/adwaita-lite-setup-wizard
```

Expected: All clean.

- [ ] **Step 2: Review full diff**

Run: `git log --oneline -4` to confirm the four commits look right.
Run: `git diff HEAD~4..HEAD` to review the complete changeset.

- [ ] **Step 3: Push**

```bash
git push
```

---

## Testing (post-CI)

After CI builds the new image:

1. Download raw image, `just convert-raw`, import to GNOME Boxes
2. Run the setup wizard, select **zswap + disk swap** with 2 GB
3. After reboot, verify:
   - `systemctl status adwaita-lite-encrypted-swap` shows active
   - `swapon --show` shows `/dev/mapper/cryptswap`
   - `dmsetup table cryptswap` shows `aes-xts-plain64`
   - `losetup -a` shows `/var/swap` attached to a loop device
4. Reboot again, verify swap comes back up automatically
5. Test zram-only path: create a new image without selecting zswap — service should not run (`ConditionPathExists` skips it)
