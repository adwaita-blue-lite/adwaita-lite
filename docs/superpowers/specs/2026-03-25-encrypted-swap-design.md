# Encrypted Disk Swap

**Date:** 2026-03-25
**Status:** Approved

## Problem

When a user selects the zswap + disk swap option in the setup wizard, a plaintext swap file is created at `/var/swap`. Any data paged out to this file — including passwords, session tokens, and other credentials — is readable by anyone with physical access to the disk. This is unacceptable for a public-facing OS targeting Chromebooks that may be lost or stolen.

## Goal

Encrypt the disk swap file with a random key on every boot so that swap contents are never recoverable after power-off. No user interaction or password required.

## Scope

- **In scope:** Encrypting `/var/swap` when the user chooses zswap in the setup wizard.
- **Out of scope:** The zram-only default path (no disk writes, nothing to encrypt). Full-disk encryption (future work).

## Design

### Approach: Systemd service with dm-crypt

On every boot, a systemd service attaches the swap file to a loop device, opens a `plain` dm-crypt volume with a random key from `/dev/urandom`, formats it as swap, and activates it. On shutdown, it tears down cleanly in reverse.

**Why not crypttab + loop device (Gemini's suggestion):**
- `crypttab` expects stable block device paths; loop device numbers are assigned dynamically
- Hardcoding `/dev/loop0` is fragile — other processes (Flatpak, snap) can claim it first
- `crypttab` runs very early in boot, before `local-fs.target` — boot ordering with a loop device attachment service is fragile and risks hangs on slow eMMC storage
- A systemd service in normal boot sequence avoids all of these issues

### New files

#### 1. `/usr/libexec/adwaita-lite-encrypted-swap`

Shell script with `start` and `stop` subcommands. Uses `set -euo pipefail` with a cleanup trap on the start path to undo partial setup if any step fails.

**start:**
1. Check `/var/swap` exists, exit 0 if not (defense-in-depth with `ConditionPathExists`)
2. Register cleanup trap: on ERR, close cryptswap and detach loop device if either was set up
3. `losetup --find --show /var/swap` — attach to first free loop device
4. Write loop device path to `/run/adwaita-lite-swap-loop`
5. `cryptsetup open --type plain --cipher aes-xts-plain64 --key-size 512 --key-file /dev/urandom $LOOP cryptswap`
6. `mkswap /dev/mapper/cryptswap`
7. `swapon /dev/mapper/cryptswap`

**stop (each step tolerates missing state with `|| true`):**
1. `swapoff /dev/mapper/cryptswap`
2. `cryptsetup close cryptswap`
3. Read loop device path from `/run/adwaita-lite-swap-loop`
4. `losetup -d $LOOP`
5. Clean up `/run/adwaita-lite-swap-loop`

All new files live in the repo under `files/` and are copied into the image at build time via `cp -a /ctx/files/. /` (build.sh line 80).

#### 2. `files/etc/systemd/system/adwaita-lite-encrypted-swap.service`

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

Key details:
- `After=local-fs.target` — ensures `/var/swap` is accessible
- `Before=swap.target` — ensures encrypted swap is active before anything expects swap
- `ConditionPathExists=/var/swap` — silently skips on zram-only systems (no swap file)
- `RemainAfterExit=yes` — keeps the unit "active" so ExecStop runs on shutdown

### Modified files

#### 3. `build_files/build.sh`

Add `cryptsetup` to the dnf5 install list. Required for `cryptsetup open`/`close` commands.

Add `chmod 0755` for the new `/usr/libexec/adwaita-lite-encrypted-swap` script.

#### 4. `/usr/bin/adwaita-lite-setup-wizard`

In the `_create_account()` method, the zswap path currently:
1. Creates `/var/swap` with `dd`
2. `chmod 600`
3. `mkswap /var/swap`
4. Creates `var-swap.swap` systemd unit
5. `systemctl enable var-swap.swap`
6. `swapon /var/swap`

Change to:
1. Creates `/var/swap` with `dd` (unchanged)
2. `chmod 600` (unchanged)
3. `systemctl enable adwaita-lite-encrypted-swap.service` (replaces steps 3-6)

The `var-swap.swap` unit creation, `mkswap`, and `swapon` calls are removed entirely — not just skipped. The encrypted swap service is the sole owner of swap lifecycle.

The swap file is not activated during the wizard session. The wizard reboots immediately after account creation, and the service activates encrypted swap on the next boot.

## Security properties

- **Random key per boot:** `/dev/urandom` provides a fresh key each boot. Previous swap contents are cryptographically unrecoverable.
- **No stored key:** The key exists only in kernel memory while the system is running. Power off = key gone.
- **AES-XTS-PLAIN64:** Standard disk encryption mode. Fast even on older CPUs without AES-NI.
- **Plain dm-crypt (not LUKS):** No header, no metadata. The entire device is encrypted data. Appropriate for ephemeral swap where there's no need to store or manage keys.

## Failure modes

| Scenario | Behavior |
|---|---|
| `/var/swap` doesn't exist (zram-only) | `ConditionPathExists` skips the service silently |
| `cryptsetup` not installed | Service fails, system boots without swap, logged to journal |
| No free loop devices | `losetup` fails, service fails, system boots without swap |
| `mkswap`/`swapon` fails after dm-crypt opens | Cleanup trap closes cryptswap and detaches loop device |
| Shutdown interrupted | Swap data remains encrypted with a key that no longer exists in memory |

All failure modes are non-fatal — the system boots and runs, just without disk swap.
