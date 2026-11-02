# Adwaita-Lite

A lightweight, auto-updating Linux desktop for old x86_64 Chromebooks and
old or low-end computers. Built on [Universal Blue](https://universal-blue.org/) —
the image updates itself daily and rolls back automatically if anything
goes wrong. No package manager, no manual maintenance, no surprises.

> Adwaita-Lite is an independent derivative of
> [Universal Blue's image-template](https://github.com/ublue-os/image-template).
> Upstream changes are merged through the `upstream` git remote; see
> [docs/operations/upstream-sync.md](docs/operations/upstream-sync.md).

Designed for the handful of real-world cases where this combination
actually matters:

- **2 GB Chromebooks** that ChromeOS has dropped from updates
- **Performance-minded users** on newer hardware who want a lean desktop
  that leaves more of the machine for their apps and games
- **Non-technical users** who need a simple, stable
  desktop that looks and feels like ChromeOS (bottom panel, rounded
  windows, big clear labels, familiar keyboard shortcuts). We're also trying to work on accessibility concerns and are open to input on what to prioritize.
- **Handing a laptop to a relative** without also signing up to maintain it
  
## Is this for you?

You're a good fit if you have:

- An old Chromebook, low-end x86_64 computer, or a faster PC you want to
  keep lean
- At least 2 GB of RAM
- At least 32 GB of target storage
- Either UEFI firmware already, or a Chromebook you're willing to flash
  with [MrChromebox](https://mrchromebox.tech) UEFI Full ROM

The desktop runs labwc (wlroots compositor) + waybar + our own Adwaita-
styled settings app. Chrome runs from Flathub so every user gets the
same browser they're used to. Apps beyond the built-ins install from
Flathub via Bazaar.

> **Chromebook note:** Flashing UEFI firmware requires removing the
> write-protect screw. See [MrChromebox](https://mrchromebox.tech) for
> device-specific instructions. x86_64 only — ARM Chromebooks are not
> supported.

> **Storage note:** Adwaita-Lite needs **32 GB minimum** target storage.
> Many old Chromebooks shipped with 16 GB eMMC, and by now that storage is
> often worn out. For those machines, use a high-endurance, application-rated
> SD card instead of the internal eMMC; look for A2/U3/V30-class media from a
> reputable vendor.
>
> **DX storage note:** DX developer mode needs **40 GB minimum** target storage
> for update staging room; **64 GB or larger is recommended** if you plan to
> keep containers, virtual machines, Homebrew packages, or development trees on
> the system.

## Install

### .raw USB installer (recommended for Chromebooks under 4 GB of RAM)

You need:

- A second Linux machine (or VM) to prepare the USB
- A USB drive, **16 GB minimum** (holds the live installer environment)
- A target drive in the machine, **32 GB minimum**

**Step 1 — Download the image.** Open
[GitHub Actions → Build disk images](../../actions/workflows/build-disk.yml),
click the most recent successful run, and download the
**adwaita-lite-raw** artifact from the Artifacts section at the
bottom of the page. Unzip it — you'll get a `disk.raw` file a few GB
in size.

**Step 2 — Flash the image to a USB drive:**

```bash
lsblk   # identify the USB drive — double-check before writing
sudo dd if=disk.raw of=/dev/sdX bs=4M status=progress conv=fsync
```

Or use [Impression](https://flathub.org/apps/io.gitlab.adhami3310.Impression)
if you'd rather not stare at `dd`.

**Step 3 — Boot from USB.** The installer wizard launches automatically.
It walks through language, network, target disk, account, system, apps,
and a final confirmation before `bootc install to-filesystem` writes the
system into the prepared target partitions.

**Step 4 — Reboot.** Remove the USB when prompted. The login screen comes
up with your chosen username pre-filled. Selected Flatpaks are downloaded
from Flathub on first boot; the greeter shows finishing-setup progress
until requested app installation completes.

### ISO installer (Anaconda)

For machines with 4+ GB of RAM or anything where the raw USB path is
inconvenient, grab the **adwaita-lite-anaconda-iso** artifact from
the most recent successful run of
[Build disk images](../../actions/workflows/build-disk.yml), unzip it,
and flash the `.iso` file inside to a USB drive the same way as the
raw image.

Anaconda handles partitioning, user creation, and timezone setup on
boot. A kickstart `%post` rebases the installed system to the published
Adwaita-Lite image, seeds `/var/lib/adwaita-lite/install-config.json`
with sensible defaults (zram memory strategy, anaconda-created UID 1000
as the primary user), and triggers the same first-boot flow the USB
path uses.

On first boot the flatpak-install service pulls the default Flatpaks
(Chrome, Bazaar, and GTK3 theme helpers) from Flathub. Offline or failed
installs retry on the next boot.

### Switch from an existing Fedora Atomic system

If the machine already runs Silverblue, Kinoite, Bazzite, Bluefin, Aurora,
or any other Fedora Atomic / Universal Blue image, you can rebase without
reflashing.

**On Fedora 42+ / Universal Blue (bootc):**

```bash
sudo bootc switch ghcr.io/adwaita-blue-lite/adwaita-lite:latest
sudo systemctl reboot
```

**On older systems using rpm-ostree:**

```bash
# Unsigned rebase (works everywhere)
rpm-ostree rebase ostree-unverified-registry:ghcr.io/adwaita-blue-lite/adwaita-lite:latest
systemctl reboot

# Then, for signature verification on subsequent updates:
rpm-ostree rebase ostree-image-signed:docker://ghcr.io/adwaita-blue-lite/adwaita-lite:latest
systemctl reboot
```

### After install

The system manages itself. Daily image builds publish to
`ghcr.io/adwaita-blue-lite/adwaita-lite:latest` and the unified updater
(`uupd`) pulls them on a timer, handling both the bootc image and
Flatpak apps. If an update ever causes a problem, the previous image is
always available in the boot menu — select it to roll back.

Adwaita-Lite's published update image is hosted on Quay. Older test
installs that still track GHCR can move to the current update stream with
one manual rebase:

```bash
sudo rpm-ostree rebase ostree-unverified-registry:ghcr.io/adwaita-blue-lite/adwaita-lite:latest
sudo systemctl reboot
```

## Image streams

Adwaita-Lite publishes one container image with multiple stream tags:

| Stream | Branch | Base | Purpose |
|--------|--------|------|---------|
| `latest` | `main` | Daily refresh from `ghcr.io/ublue-os/base-main:latest`; routine main builds from Quay `latest` | Stable, low-resource consumer image |
| `dx` | `dx` | Quay `latest` | Stable developer-mode image with Homebrew, Distrobox, Docker, Podman, libvirt/QEMU, Incus, Cockpit, VS Code, and DX group/workaround services |
| `testing` | `testing` | Quay `dx` | WIP stream; currently inherits `dx` and is where DX-adjacent experiments can bake |
| `beta` | `beta` | Daily refresh from `ghcr.io/ublue-os/base-main:beta`; routine beta builds from Quay `beta` | Fedora-next compatibility canary based on `main`; intentionally does not inherit DX payload |

Published tags use `ghcr.io/adwaita-blue-lite/adwaita-lite:<stream>`. Stream
builds also publish date tags like `dx.YYYYMMDD`, `testing.YYYYMMDD`, and
`beta.YYYYMMDD`; `latest` additionally publishes bare `YYYYMMDD` tags.

### Switch streams

To enable developer mode like Universal Blue/Aurora/Bluefin, switch to the
DX image first, reboot into it, then finish the user group setup from the DX
image:

Install `latest` first, then enable DX with `ujust devmode`. Direct DX
installer artifacts are not the supported path; they may exist from branch
builds, but Adwaita-Lite follows upstream by treating DX as a post-install
transition.

```bash
# From latest/main:
ujust devmode         # confirm the switch from latest -> dx
sudo systemctl reboot

# After rebooting into dx, complete the DX user setup:
ujust dx-group        # add your user to docker/incus-admin/libvirt/dialout
sudo systemctl reboot # or log out and back in so group membership applies
```

`ujust toggle-devmode` is an alias for `ujust devmode`. The `dx-group` recipe
is provided by the DX image; if it does not exist yet, reboot into the pending
DX deployment first.

`ujust devmode` intentionally maps `latest` <-> `dx` directly because
Adwaita-Lite publishes DX as a stream tag, not as a separate `-dx` image
name. If you are on `testing`, `beta`, or a date-pinned tag, switch manually:

```bash
# Stable consumer image
pkexec bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:latest

# Stable developer image
pkexec bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:dx

# WIP developer/testing image
pkexec bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:testing

# Fedora-next compatibility canary
pkexec bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:beta

sudo systemctl reboot
```

## Installer wizard

The USB installer boots into a labwc session running the setup wizard
fullscreen. It walks through:

1. **Language** — system language plus keyboard layout, with common
   regional variants
2. **Network** — connect to WiFi if needed (skipped if already online)
3. **Disk** — target drive, filesystem (ext4/xfs/btrfs), and memory
   management strategy
4. **Account** — full name, username, password, administrator access,
   optional root password
5. **System** — timezone and hostname
6. **Apps** — Flatpaks to install from Flathub on first boot
7. **Confirm** — review every choice before anything is written
8. **Progress** — live status through partitioning, `bootc install
   to-filesystem`, account creation, network carryover, app selection
   handoff, memory setup, and finalization

Errors are handled per step: partitioning failures return you to change
settings, and post-partition install/configuration failures show a retry
button from the failed step. First-boot Flatpak installs retry on later
boots until every selected app is present.

### Memory management

Two strategies; the wizard asks at install time and you can switch later
without reinstalling.

| Option | How it works | Best for |
|--------|-------------|----------|
| **zram** (default) | Compressed in-RAM swap via `zram-generator`. Sized at 1.25× RAM, capped at 16 GB. | Most machines — fast, no disk wear |
| **zswap + encrypted disk swap** | Compressed RAM cache that spills to a `dm-crypt`-encrypted swap file when RAM + zram fill. Configurable swap file size. `vm.swappiness=100` to favor page-out. | 2 GB Chromebooks running heavy apps |

The encrypted disk swap uses `aes-xts-plain64` with a 512-bit key read
from `/dev/urandom` at each boot. The key lives only in kernel memory —
swap contents are unrecoverable across a power cycle.

### Switching strategy after install

If you picked wrong at install time, the `ujust` recipes let you swap
without reinstalling:

```bash
ujust swap-status    # show the configured strategy and active swap devices
ujust toggle-swap    # switch between zram and zswap; prompts for swap
                     # file size when moving to zswap, then asks about
                     # rebooting to activate
```

The toggle is functionally equivalent to reinstalling with the other
option selected — writes the same config files, enables/disables the
same services, installs the same `vm.swappiness` tuning. Kernel-level
changes take effect on the next reboot.

## What's included

| Component | Choice | Why |
|-----------|--------|-----|
| Base image | `ghcr.io/ublue-os/base-main:latest` | Lightest Universal Blue base — no bundled DE |
| Compositor | `labwc` | wlroots-based, minimal memory footprint |
| Panel | `waybar` | Chromebook-style shelf (bottom by default) |
| App menu | `adwaita-lite-app-menu` (in-process GTK4) | Token-aware search, categorized launcher, triggered by Super+Space or the panel launcher |
| Browser | Google Chrome (Flatpak, first boot) | Chrome to replace ChromeOS effectively; other browsers can be installed from Flathub |
| File manager | `Thunar` | Lightweight, thumbnail support |
| Terminal | `foot` | GPU-accelerated, minimal (~8-15 MiB resident) |
| Greeter | `greetd` + custom GTK4 greeter | Login screen via `cage` kiosk, palette-synced to the user's theme + accent |
| Notifications | `mako` | Low-overhead notification daemon |
| Screen lock | `swayidle` + `swaylock` | Configurable timeouts from the Settings app |
| Power | `power-profiles-daemon` | Battery/performance profiles for laptops |
| Audio | `pipewire` + `wireplumber` | Modern audio stack with PulseAudio compatibility |
| Bluetooth | `bluez` | Pair devices via Settings app or system tray |
| Printing | `CUPS` | Local and network printers |
| App store | `Bazaar` (Flatpak, first-boot) | Browse and install apps from Flathub |
| Settings | `adwaita-lite-settings` | Full libadwaita settings app — 15 pages, responsive layout, 22 locale codes |
| Night light | `gammastep` + per-user systemd timer | Reconciles every 15 min during a configured schedule |
| Multimedia | RPM Fusion + GStreamer + JPEG-XL/WebP loaders | Codec + image-format support out of the box |

### Keyboard shortcuts

#### Chromebook top-row keys

| Key | Action |
|-----|--------|
| Volume Up / Down / Mute | Adjust or mute audio |
| Brightness Up / Down | Adjust screen brightness |
| Fullscreen (F4) | Toggle fullscreen |

#### Search key (Super)

| Shortcut | Action |
|----------|--------|
| `Super+Space` | App menu (search / browse apps) |
| `Super+L` | Lock screen |
| `Super+E` | File manager |
| `Super+Escape` | Task manager (xfce4-taskmanager) |
| `Super+,` | Settings |
| `Super+Up` | Maximize window |
| `Super+Down` | Minimize window |

#### Window management

| Shortcut | Action |
|----------|--------|
| `Alt+Tab` / `Alt+Shift+Tab` | Cycle windows |
| `Alt+[` | Snap window left |
| `Alt+]` | Snap window right |
| `Alt+F4` | Close window |
| `Ctrl+Alt+T` | Terminal |

#### Screenshots

| Shortcut | Action |
|----------|--------|
| `Print Screen` | Full screenshot to clipboard |
| `Shift+Print Screen` | Area selection to clipboard |

### Default app associations

| File type | Opens with |
|-----------|------------|
| PDFs | Evince |
| Text files | GNOME Text Editor |
| Images (JPEG/PNG/GIF/SVG/WebP/BMP/TIFF/JXL/ICO/…) | Ristretto |
| Videos | mpv |
| Audio | mpv |
| Web links | Chrome |

Defaults ship at `/etc/xdg/mimeapps.list`. Change any of them from the
Settings app's Default Apps page.

### Settings app

`Super+,` or the panel tray opens `adwaita-lite-settings`, a full
libadwaita settings app with an adaptive sidebar+content layout (sidebar
collapses to push-navigation below 700sp for narrow windows or Large Text
accessibility scaling).

| Page | What it configures |
|------|--------------------|
| Appearance | Light/dark theme, accent color (9 options), font size, wallpaper picker with bundled + custom wallpapers |
| Display | Scale (0.75×–2.5×), resolution, refresh rate, night light (temperature + schedule) |
| Network | WiFi scanning/connection, hidden networks, wired status |
| Bluetooth | Device discovery, pairing, connect/disconnect |
| Panel | Position, density, module layout, pinned apps |
| Mouse & Touchpad | Pointer speed, natural scrolling, tap to click, acceleration profile |
| Keyboard | Layout + variant, repeat delay/rate, Caps Lock behavior, custom shortcuts |
| Sound | Output/input device, volume, mute |
| Power & Lock | Lock/display-off/suspend timeouts, power profile, lid close action |
| Accessibility | Large text, cursor size, high contrast, reduce motion |
| Date & Time | Timezone entry, NTP toggle, 12/24-hour clock |
| Users | Display name, password, automatic login |
| Language & Region | System locale, regional formats |
| Default Apps | Browser, file manager, terminal, editor, image/PDF/media/email |
| About | System info, hardware, disk usage, update check, restore-defaults |

Most changes apply immediately and are applied consistently across labwc
(SSD titlebars), waybar (panel), mako (notifications), foot (terminal),
swaylock, and CSD GTK apps. Language and regional-format changes take
effect after logging out; display scale and resolution changes use a
timed confirmation dialog so a bad mode can revert automatically.

Translated to 22 locale codes (am, ar, de, es, fa, fr, ha, hi, it, ja,
ko, nl, pl, pt, ru, sv, sw, th, tr, vi, yo, zh). Human translator
pass recommended before shipping widely — machine translation used to
seed every entry, but native speakers will spot register mismatches.

### Debug utilities

Shipped in `/usr/bin/`:

- `ul-debug-nm` — one-command diagnostic snapshot when NetworkManager
  fails to start (writes `~/nm-diag.txt` with unit state, symlink
  presence, journal breadcrumbs, dependency chain, boot timing)

## Development

### Prerequisites

- [just](https://just.systems) — task runner
- [podman](https://podman.io) — container runtime
- `pytest` — unit tests
- `shellcheck` — `just lint`
- `qemu-img` — `just convert-raw`

### Build

```bash
just build          # OCI container image
just build-raw      # Raw disk image (USB installer — flash with dd)
just build-iso      # ISO installer (Anaconda — requires 4+ GB RAM)
just build-qcow2    # QCOW2 for VM testing
just convert-raw    # Convert raw → QCOW2 (for GNOME Boxes import)
```

### Test in a VM

```bash
just run-vm-qcow2   # Run QCOW2 in a browser-accessible VM (qemux/qemu)
just run-vm-raw     # Run raw image the same way
just run-vm-iso     # Run the Anaconda ISO image
just spawn-vm       # Run with systemd-vmspawn (GUI)
```

> **GNOME Boxes:** Don't import `disk.raw` directly — Boxes may truncate it.
> Run `just convert-raw` first and import the resulting QCOW2.

### Lint

```bash
just lint           # shellcheck on all shell scripts
just check          # Justfile syntax check
```

### Test

```bash
python -m pytest tests
```

### CI/CD

Pull requests, non-README pushes to `main`, `dx`, `testing`, and `beta`,
plus the daily schedule build the OCI image. Stream branches publish
`ghcr.io/adwaita-blue-lite/adwaita-lite` tags and sign images with
[cosign](https://github.com/sigstore/cosign): `main` publishes `latest`,
`dx` publishes `dx`, `testing` publishes `testing`, and `beta` publishes
`beta`. Pull requests validate builds but do not publish or sign images.

The Quay repository is the primary public update source for Adwaita-Lite.

To set up signing on a fresh fork:

```bash
COSIGN_PASSWORD='' cosign generate-key-pair
gh secret set SIGNING_SECRET < cosign.key
```

Disk images (raw + anaconda-iso) build on manual dispatch and after
successful scheduled `main` container builds via the
[disk image workflow](../../actions/workflows/build-disk.yml). Manual disk
builds can choose `latest`, `dx`, `testing`, or `beta`; automatic disk builds
stay on `latest`. Disk-config pull requests validate the image build without
uploading artifacts.

Stream sync is automated but conservative: successful scheduled `main` builds
merge `main` into `dx` and `beta`, then dispatch those stream builds even when
the branch is already aligned so base-image security updates still publish.
Successful sync-triggered `dx` builds dispatch `dx` into `testing`, and the
testing build is dispatched after that sync succeeds. Conflicts open disposable
`sync/<source>-to-<target>` pull requests for human or agent resolution and skip
the blocked target build.
Dependencies are kept current by Dependabot and Renovate.

## Project layout

```
Containerfile                              # Image build definition
build_files/build.sh                       # Package install + configuration
build_files/dx/                            # DX developer payload install + image checks
disk_config/
  disk.toml                                # Raw disk image config (10 GiB root)
  iso.toml                                 # ISO config (Anaconda + kickstart bootc-switch)
po/                                        # Translation sources
  settings/*.po                            # 22 locale codes for settings + greeter
tests/                                     # Unit tests for wizard, settings, desktop defaults, helpers
  test_branch_channels.py                  # Branch/tag/base workflow contracts
  test_dx_payload.py                       # DX payload and devmode recipe contracts
files/
  etc/
    gtk-3.0/, gtk-4.0/                     # Decoration-layout defaults (min/max/close)
    xdg/
      foot/, labwc/, mako/,
      swaylock/, gtk-3.0/, gtk-4.0/        # App defaults
      mimeapps.list                        # Default app associations (pdf, image, etc.)
    sysctl.d/                              # Memory tuning (swappiness for zswap)
    systemd/
      zram-generator.conf                  # Default 125%-of-RAM zram config
  usr/
    bin/
      adwaita-lite-app-menu              # In-process GTK4 start menu
      adwaita-lite-greeter               # Custom GTK4 login greeter
      adwaita-lite-settings              # Settings app entry point
      adwaita-lite-setup-wizard          # Installer wizard (GTK4)
      ul-debug-nm                          # NetworkManager diagnostic snapshot
    lib/
      bootc/install/00-adwaita-lite.toml # bootc install config
      systemd/
        system/                            # Canonical location for our systemd units
          adwaita-lite-first-boot.service
          adwaita-lite-flatpak-install.service
          adwaita-lite-flatpak-update.service
          adwaita-lite-swap-init.service
          adwaita-lite-encrypted-swap.service
          adwaita-lite-zswap.service
          greetd.service.d/                # Drop-ins on the greetd unit
        user/                              # Per-user systemd units
          adwaita-lite-nightlight.{service,timer}
      adwaita-lite/settings/             # Settings app Python package
        pages/                             # 15 settings pages (all libadwaita)
        app.py, window.py, base.py         # App shell, sidebar, base page
        settings_store.py, events.py       # Persistent store + event bus
    libexec/
      adwaita-lite-apply-settings        # Reconciles settings → compositor/panel/etc.
      adwaita-lite-encrypted-swap        # dm-crypt swap setup
      adwaita-lite-first-boot            # Post-install reconciliation
      adwaita-lite-flatpak-setup         # Flatpak app installer
      adwaita-lite-greeter-launch        # Cage kiosk wrapper for greeter
      adwaita-lite-greeter-setup         # Detects users, sets greetd initial session
      adwaita-lite-lid-action            # Lid close action helper
      adwaita-lite-menu                  # labwc pipemenu generator
      adwaita-lite-nightlight            # Reconcile gammastep with night-light state
      adwaita-lite-session               # Wayland session startup
      adwaita-lite-set-memory-strategy   # zram ↔ zswap toggle helper (called by ujust)
      adwaita-lite-swap-init             # Creates /var/swap at configured size
      adwaita-lite-volume, -brightness   # Media-key helpers
      adwaita-lite-wizard-session        # Wizard-mode labwc session
    share/
      applications/                        # .desktop files
      backgrounds/adwaita-lite/          # Bundled wallpapers
      glib-2.0/schemas/
        zz-adwaita-lite.gschema.override # Window button layout (min/max/close)
      locale/<lang>/LC_MESSAGES/           # Compiled .mo files per language
      polkit-1/actions/                    # Polkit policy for lid action
      themes/Adwaita-Lite/               # labwc theme (openbox-3 compat)
      ublue-os/just/90-adwaita-lite.just # ujust recipes (swap toggle, etc.)
      adwaita-lite/
        defaults/                          # Default settings (JSON)
        palette.json                       # Single source of truth for theme colors
.github/workflows/
  build.yml                                # Branch-aware OCI image build + sign + push
  build-disk.yml                           # Raw + anaconda-iso artifact builds
  sync-streams.yml                         # main -> dx/beta and dx -> testing trigger workflow
  sync-one-stream.yml                      # Reusable stream merge-or-conflict-PR workflow
```

## License

Adwaita-Lite original code is licensed under **GPL-3.0-or-later**. See
[LICENSE](LICENSE).

The project is derived from
[ublue-os/image-template](https://github.com/ublue-os/image-template), whose
upstream-derived files remain **Apache-2.0**. See [NOTICE](NOTICE) and
[LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt). The combined work is
distributed under GPL-3.0-or-later.

Third-party software in the image retains its own license. A GPL-2.0-only
component must remain a separate program and cannot be linked into the GPLv3
code.
