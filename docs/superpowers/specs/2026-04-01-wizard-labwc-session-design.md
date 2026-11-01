# Wizard in labwc Session — Design Spec

## Problem

The setup wizard runs inside cage launched by a standalone systemd service
(`adwaita-lite-first-boot.service`).  Cage requires a logind session with
proper seat assignment, POSIX session leadership, and controlling-terminal
setup — all of which greetd provides automatically but a raw systemd service
does not.  This results in a blank screen with a visible cursor in VMs and
potentially on bare metal.

Running the wizard inside greetd's greeter session (xdm_t) was previously
attempted but abandoned because SELinux blocked the privileged operations the
wizard needs: useradd, systemctl mask/enable, grubby, Flatpak install, etc.

## Solution

Instead of fighting cage's session requirements, boot into a real labwc
desktop session managed by greetd and launch the wizard as a regular
fullscreen GTK4 application inside it.

greetd handles all session/seat/VT management (proven to work).  The wizard
runs as root in a full user session with no SELinux xdm_t constraints.

## Detection: Users, Not Flags

The wizard targets the **DD install path** — low-RAM devices where Anaconda
cannot run and the disk image is written directly.  On the Anaconda path,
user accounts are created during installation.

The decision of wizard-mode vs normal-greeter is based on whether any real
user accounts (UID 1000–65533) exist in `/etc/passwd`, not a `setup-done`
flag file.  This avoids the wizard running on Anaconda-installed systems.

```bash
has_users=$(getent passwd \
  | awk -F: '$3 >= 1000 && $3 < 65534 { found=1; exit } END { print found+0 }')
```

## greetd Configuration

`/usr/libexec/adwaita-lite-greeter-setup` (runs as `ExecStartPre` for
greetd) generates `/etc/greetd/config.toml` dynamically.

**No users (DD path) — wizard mode:**

```toml
[terminal]
vt = 7

[default_session]
command = "/usr/libexec/adwaita-lite-greeter-launch"
user = "greetd"

[initial_session]
command = "/usr/libexec/adwaita-lite-wizard-session"
user = "root"
```

`initial_session` runs once.  If the wizard crashes or exits without
creating a user, greetd falls back to `default_session` (the login greeter)
so the device is not bricked.

**Users exist — normal greeter:**

```toml
[terminal]
vt = 7

[default_session]
command = "/usr/libexec/adwaita-lite-greeter-launch"
user = "greetd"
```

No `initial_session` block.

## Wizard Session Script

New file: `/usr/libexec/adwaita-lite-wizard-session`

- Sets `ADWAITA_LITE_WIZARD=1` (tells autostart to launch the wizard)
- Detects VM via `systemd-detect-virt -q` → exports `WLR_NO_HARDWARE_CURSORS=1`
  (fixes wlroots hardware cursor rendering upside-down/misplaced in VMs)
- Conditional `GSK_RENDERER=gl` when Vulkan is unavailable (VMs, Bay Trail)
- Execs `labwc`

No `.desktop` file in `/usr/share/wayland-sessions/` — the wizard session is
invisible to session selectors in the login greeter.

## Autostart Changes

At the very top of `/etc/xdg/labwc/autostart`, before any other logic:

```sh
if [ "${ADWAITA_LITE_WIZARD:-}" = "1" ]; then
    /usr/bin/adwaita-lite-setup-wizard &
    exit 0
fi
```

This skips all desktop daemons (waybar, nm-applet, blueman, mako, swayidle,
Thunar, etc.).  This keeps RAM usage minimal on the 2 GB Chromebooks that
use the DD path.

The wizard must call `self.fullscreen()` on its GTK4 window.  Previously
cage forced fullscreen; in labwc the application is responsible.

The wizard already has its own WiFi UI (NM via GObject introspection) and
does not need nm-applet or any other desktop infrastructure.

## Hardware Cursor Fix for Normal Sessions

The VM cursor fix (`WLR_NO_HARDWARE_CURSORS=1`) must also apply to regular
labwc sessions, not just the wizard.  The normal session script
(`/usr/libexec/adwaita-lite-session`) gets the same `systemd-detect-virt`
check:

```sh
if systemd-detect-virt -q; then
    export WLR_NO_HARDWARE_CURSORS=1
fi
```

The greeter launcher (`/usr/libexec/adwaita-lite-greeter-launch`) gets
the same check for cage running the login greeter in VMs.

## setup-done Flag

The wizard still creates `/var/lib/adwaita-lite/setup-done` on completion.
Boot-time services (zswap, swap-init, etc.) may check this flag.  It is no
longer used for the greetd launch decision — that is based solely on user
detection.

## Cleanup

Remove files that are no longer needed:

- `files/etc/systemd/system/adwaita-lite-first-boot.service`
- `files/etc/pam.d/adwaita-lite-first-boot`
- `files/usr/libexec/adwaita-lite-wizard-launch`
- `systemctl enable adwaita-lite-first-boot.service` line in `build.sh`
- `chmod` entry for `adwaita-lite-wizard-launch` in `build.sh`

## Flow Summary

### DD install path (no users)

1. greetd starts → `greeter-setup` detects no users
2. Config includes `initial_session` pointing at wizard session as root
3. greetd auto-logs in root → `adwaita-lite-wizard-session` runs
4. labwc starts → autostart sees `ADWAITA_LITE_WIZARD=1` → launches wizard
5. Wizard creates user, configures system, installs Flatpaks
6. Wizard reboots
7. Next boot: `greeter-setup` detects user → normal greeter config

### Anaconda install path (user exists)

1. greetd starts → `greeter-setup` detects user
2. Config has no `initial_session` → normal greeter launches
3. User logs in normally

### Wizard crash safety

If the wizard crashes, greetd falls back to `default_session` (the login
greeter).  Since no users exist, the greeter will show an empty user list —
but the device is not stuck in a reboot loop.  A future enhancement could
detect this state and show a recovery message.
