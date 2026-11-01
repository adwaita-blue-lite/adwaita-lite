# Installer Wizard — Design Spec

## Problem

The current wizard runs on an already-installed system deployed via raw DD to
an SD card.  The raw image is large (pre-allocated swap space), and the install
process requires manual `dd` commands — unfriendly for end users and
constrained to SD cards because the image is too big for eMMC.

## Solution

Turn the wizard into a proper installer that boots from USB, installs to a
target drive via `bootc install to-disk`, and configures the system in one
pass.  This follows the same architectural pattern as Anaconda (write config
directly to the mounted sysroot) with Bazzite's Flatpak trick (rsync
pre-downloaded Flatpaks from the live environment).

The DD install path is retired.  Anaconda remains the install path for
devices with enough RAM to run it.  This installer targets constrained
devices (Bay Trail Chromebooks, 2 GB RAM).

## Boot and Session Management

The installer runs from USB via the same greetd + labwc session architecture
established for the first-boot wizard:

1. USB boots into greetd
2. `greeter-setup` detects no users → configures `initial_session` as root
3. greetd auto-logs in root → labwc wizard session starts
4. autostart launches the wizard fullscreen in bare mode (no desktop daemons)

User detection (`getent passwd`, UID >= 1000) still controls wizard vs
greeter routing.  On the installed system after reboot, users exist, so
greetd shows the normal login greeter.

## Wizard Pages (7 total)

### Page 0 — Network

Existing WiFi scan-and-connect page.  Auto-skips if already connected
(ethernet or existing WiFi).  Needed for NTP/timezone detection.

### Page 1 — Disk (new)

Three controls:

- **Target drive** — dropdown populated from `lsblk --json --output
  NAME,SIZE,MODEL,TRAN,RM,TYPE`.  Filtered to show only whole disks
  (`TYPE=disk`), excluding the boot USB (detected by comparing against the
  device backing `/` or by the `RM` removable flag + mounted-as-root
  heuristic).  Display format: `"sda — 16 GB SanDisk eMMC"`.

- **Filesystem** — dropdown: ext4 (default), xfs, btrfs.

- **Memory management** — dropdown: "Compressed RAM only (zram)" (default)
  vs "Compressed RAM + disk backup (zswap)".

- **Swap file size** — only visible when zswap is selected.  Options:
  2 GB, 4 GB, 8 GB, custom.

- **Warning label** at bottom: "All data on the selected drive will be
  erased."

No partition expansion checkbox (gone — `bootc install to-disk` uses the
whole disk).

Memory management and swap size moved here from the System page because
the swap file lives on the target disk — grouping disk-related choices
together.

### Page 2 — Account

Existing page: full name, username, password, confirm password.

### Page 3 — System

Existing page minus partition expansion:

- Timezone dropdown
- Admin (wheel) toggle
- Root password (optional)

### Page 4 — Apps

Existing Flatpak selection page.  Apps are pre-downloaded on the USB image.
Instead of downloading during install, selected apps are rsynced from the
live environment's `/var/lib/flatpak` to the target sysroot.

### Page 5 — Confirm

Summary of all selections.  Same layout as current page, updated to include
target drive and filesystem.

### Page 6 — Progress

Step runner executes the install pipeline:

1. **"Partitioning and installing..."** —
   `bootc install to-disk --filesystem <fs> /dev/<target>`.  If `bootc`'s
   stdout provides clear stage markers (partitioning, deploying image,
   bootloader), pipe them into the step label for progress visibility.
   Otherwise keep it as a single running step.  (Determine during
   implementation by inspecting `bootc` output.)

2. **"Configuring user account..."** — mount sysroot, run
   `useradd --root /mnt/sysroot --create-home --groups wheel --shell
   /bin/bash --password <hashed> <username>`.  Set timezone symlink and
   locale.conf directly on sysroot.

3. **"Copying network configuration..."** — copy
   `/etc/NetworkManager/system-connections/*` from live environment to
   sysroot's `/etc/NetworkManager/system-connections/`.

4. **"Installing selected apps..."** — rsync selected Flatpak app and
   runtime directories from `/var/lib/flatpak` on the live environment to
   the sysroot's `/var/lib/flatpak`.  Only selected apps and their
   dependencies are copied.

5. **"Configuring memory management..."** — write swap strategy (zram or
   zswap) and swap-size file to sysroot's `/var/lib/adwaita-lite/`.
   If zram: write zram-generator config to sysroot's `/etc/`.
   If zswap: write config so first-boot service will enable
   `adwaita-lite-encrypted-swap.service` (dm-crypt with random per-boot
   key), create the swap file, mask zram-generator, and apply zswap kernel
   args via grubby.  The encrypted swap architecture (loop device →
   dm-crypt → mkswap → swapon, fresh random key each boot) must be
   preserved exactly.

6. **"Finalizing..."** — write first-boot config JSON, unmount sysroot.

7. **Reboot** button appears on success.  Same retry/skip UX for non-fatal
   failures (e.g., Flatpak rsync), hard stop for fatal ones (e.g., `bootc
   install` failure).

## First-Boot Service (on installed system)

A headless service reads `/var/lib/adwaita-lite/install-config.json` and
handles operations that require the running system:

- Create swap file at configured size (`/usr/libexec/adwaita-lite-swap-init`)
- Enable encrypted-swap service (if zswap selected)
- Mask zram-generator (if zswap selected) or configure it (if zram selected)
- Apply kernel args via grubby (zswap enable, etc.)
- Enable/disable relevant services
- Create `setup-done` flag

After this service completes, the user lands at the login greeter with
their account ready and apps installed.

## Encrypted Swap

The existing encrypted swap architecture is preserved unchanged:

- `adwaita-lite-swap-init` creates `/var/swap` at the specified size
- `adwaita-lite-encrypted-swap` opens it with dm-crypt using a random
  per-boot key from `/dev/urandom`, runs `mkswap`, and activates it
- Every boot gets a fresh key; previous boot's data is unrecoverable

The installer writes the swap size to the sysroot.  The first-boot service
creates the actual file (needs the final filesystem mounted at full size).

## zram Configuration Change

The default zram size changes from 150% of RAM to **125% of RAM**
(`zram-size = min(ram * 5/4, 3072)`).  This leaves more uncompressed RAM
headroom on 2 GB devices while still providing substantial swap capacity
(2.5 GB on a 2 GB device).

## USB Image Build Changes

The USB image build would:

- Pre-download the selectable Flatpaks into `/var/lib/flatpak` on the live
  image (so they can be rsynced to the target without network download)
- Ship a smaller base (no pre-allocated swap file)
- Include `bootc` CLI tools (likely already present in bootc images)
- No longer produce the large raw DD image

## What Gets Removed

- Partition expansion checkbox and `systemd-repart` enablement
- The swap file creation step in the wizard progress (moved to first-boot)
- DD path documentation and references
- Raw DD image build artifacts

## What Stays the Same

- Pure GTK4, no libadwaita
- Same visual style and CSS
- Same WiFi/NM page (Page 0)
- Same account page (Page 2)
- Same app selection UI (Page 4) — just rsync instead of download
- Runs inside labwc via greetd
- Encrypted swap architecture
- Boot-time service pattern for privileged operations

## Flow Summary

### Install (from USB)

1. Boot USB → greetd auto-login root → labwc → wizard fullscreen
2. User configures: network, drive, account, system, apps
3. Wizard installs via `bootc install to-disk`
4. Wizard writes config directly to mounted sysroot
5. Wizard rsyncs Flatpaks and NM connections
6. Reboot into installed system

### First Boot (on installed system)

1. First-boot service creates swap file, enables services, applies kargs
2. greetd detects users → shows login greeter
3. User logs in to fully configured system

### Subsequent Boots

1. greetd shows login greeter (normal operation)
2. Encrypted swap activates with fresh random key
3. `bootc update` handles OS updates
