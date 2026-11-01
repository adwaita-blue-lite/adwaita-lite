# Wizard Network Configuration + First-Boot Flatpak Install

**Date:** 2026-03-25
**Status:** Approved

## Overview

Extend the Adwaita-Lite first-boot setup wizard with two new capabilities:

1. **Network configuration page** -- WiFi scan-and-connect so the user can get online during first boot.
2. **First-boot Flatpak installation** -- Install selected Flatpak apps (starting with Bazaar) as part of the wizard flow, with real-time progress and retry/skip on failure.

The existing `adwaita-lite-flatpak-setup.service` and its script are removed; the wizard takes full ownership of Flatpak provisioning.

## Page Flow

```
Network -> Account -> System -> Apps -> Confirm -> Progress
```

Six pages total (up from three). Constants:

| Page | Constant | Name | Purpose |
|------|----------|------|---------|
| 0 | PAGE_NETWORK | "network" | WiFi scan-and-connect + hidden network |
| 1 | PAGE_ACCOUNT | "account" | Full name, username, password (unchanged) |
| 2 | PAGE_SYSTEM | "system" | Timezone, swap, admin, root password (unchanged) |
| 3 | PAGE_APPS | "apps" | Per-app Flatpak toggles |
| 4 | PAGE_CONFIRM | "confirm" | Summary of all selections |
| 5 | PAGE_PROGRESS | "progress" | Real-time setup execution |

## Network Page (Page 0)

### Auto-Skip

After the `NM.Client` is initialized (see below), the wizard checks `client.get_connectivity()`. If the result is `NM.ConnectivityState.FULL`, `_current_page` starts at 1 (Account) and the Network page is never shown. The step indicator adjusts ("Step 1 of 5" instead of "Step 1 of 6"). If no WiFi device is found among `client.get_devices()`, auto-skip also applies.

### Layout

- **Header:** "Connect to Wi-Fi"
- **Scrollable list** of discovered networks, each row showing:
  - SSID
  - Signal strength indicator
  - Lock icon if secured
- **Clicking a row** expands it inline with a password entry + "Connect" button
- **"Join hidden network..."** link at the bottom opens SSID + password fields
- **Status area** shows connection progress or errors ("Wrong password")
- **"Skip" button** in the bottom-left for users who want to proceed offline

### Implementation: libnm GObject Introspection

The `libnm` typelib provides `gi.repository.NM` -- the native Python-GObject API for NetworkManager. It integrates directly with the GLib main loop (no threads needed for network operations).

- `NM.Client.new_async(None, callback)` for async client initialization (avoids blocking the GTK main thread during D-Bus handshake). All network page UI setup happens in the callback once the client is ready.
- `client.get_devices()` -> filter for `NM.DeviceWifi` -> `device.request_scan_async()` -> `device.get_access_points()`
- Connection via `NM.SimpleConnection` + `client.add_and_activate_connection_async()`
- All async operations use GLib main loop callbacks
- Auto-scan on page entry; "Rescan" button triggers `request_scan_async()` (NM rate-limits scans to ~10s intervals; the button is insensitive during cooldown)

**Client lifecycle:** The `NM.Client` instance is created during `SetupWizardApp.__init__` (async) and kept alive through the Confirm page (for network status summary). It is not explicitly disposed -- GC handles cleanup after the wizard reboots.

**Scope:** WPA-PSK (home WiFi) and open networks only. WPA-Enterprise / 802.1X is out of scope for v1; users needing enterprise auth can configure it post-setup via `nm-applet`.

**Signal strength:** Displayed as a 3-tier icon (weak/medium/strong) derived from `NM.AccessPoint.get_strength()` (0-100 scale). Thresholds: weak < 40, medium 40-70, strong > 70.

### Edge Cases

- **No WiFi adapter:** auto-skip (same as connectivity present)
- **Scan returns empty:** "No networks found" message with a "Rescan" button
- **Connection fails:** inline error, user can retry or pick another network
- **Already on Ethernet:** auto-skip via NM connectivity check

## Apps Page (Page 3)

### Layout

- **Header:** "Install Apps"
- **Subtitle:** "These apps will be installed during setup. Uncheck any you don't want."
- **Scrollable list** of app rows, each with:
  - App icon (bundled icon or generic placeholder)
  - App name + one-line description
  - Checkbox toggle (checked by default)

### Data Structure

```python
DEFAULT_FLATPAKS = [
    ("dev.bazaar.app", "Bazaar", "Browse and install apps"),
]
```

Simple list of tuples. The page builds one row per entry. Easy to extend by adding entries.

### Behavior

- If all apps are unchecked, the Flatpak steps are skipped entirely during progress (no Flathub remote added).
- If the user skipped the Network page (offline) but left apps checked, Flatpak install will fail during Progress. This is handled by the existing retry/skip flow on the Progress page -- no special pre-validation needed.
- The wizard writes `/var/lib/adwaita-lite/flatpak-setup.done` on **any successful wizard completion**, regardless of whether Flatpak apps were selected or installed. This prevents the `session-init` notification from firing.

### Flatpak Commands

All Flatpak operations use `subprocess.run()` with `--system` scope (wizard runs as root):

```python
# Add Flathub remote
subprocess.run(
    ["flatpak", "remote-add", "--system", "--if-not-exists",
     "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"],
    check=True, capture_output=True, text=True,
)

# Install an app
subprocess.run(
    ["flatpak", "install", "--system", "--noninteractive", "flathub", app_id],
    check=True, capture_output=True, text=True,
)
```

`--noninteractive` is required since there is no terminal for prompts.

## Confirm Page Updates (Page 4)

Existing summary sections remain unchanged. Two new sections added:

- **Network:** "Connected to MyNetwork" / "No network (offline setup)" / "Wired connection"
- **Apps:** List of selected app names, or "No apps selected"

Network summary appears at the top (first step); Apps summary appears after System config.

## Progress Page (Page 5)

### Layout

- **Header:** "Setting Up..."
- **Vertical list of steps** with status indicators:
  - Pending / In progress / Done / Failed
- **Steps displayed:**
  1. Creating user account
  2. Configuring system
  3. Adding Flathub repository (skipped if no apps selected)
  4. Installing [App Name] (one row per selected app; skipped if unchecked)
- **No Back/Next buttons** on this page during execution

### Completion States

**Success:** All steps show done. A **"Reboot"** button appears. User clicks to reboot.

**Flatpak failure:** The failed step shows the error. Two buttons appear: **Retry** and **Skip**. Skip marks remaining Flatpak installs as skipped and shows the Reboot button. Retry re-attempts the failed step.

**Non-Flatpak failure** (user creation, system config): Fatal. Error displayed with a **Back** button to return to the relevant page for correction.

### Threading Model

Background thread runs a step-runner loop:

```python
steps = [
    ("Creating user account", _step_create_user),
    ("Configuring system", _step_configure_system),
    # Flatpak steps appended dynamically based on app selection
]
if selected_apps:
    steps.append(("Adding Flathub repository", _step_add_flathub))
    for app_id, app_name, _ in selected_apps:
        steps.append((f"Installing {app_name}", lambda aid=app_id: _step_install_flatpak(aid)))

for i, (label, func) in enumerate(steps):
    GLib.idle_add(_update_step, i, "in_progress")
    err = func()
    if err:
        GLib.idle_add(_update_step, i, "failed", err)
        GLib.idle_add(_show_retry_or_back, i, is_flatpak_step)
        return  # thread exits; retry/skip re-launches thread from failed step
    GLib.idle_add(_update_step, i, "done")
```

Each step function returns `None` on success or an error string on failure. The retry button re-launches the thread starting from the failed step. The skip button marks remaining Flatpak steps as skipped and shows the Reboot button.

## Removed Components

The following files are deleted from the repository:

- `files/etc/systemd/system/adwaita-lite-flatpak-setup.service`
- `files/usr/libexec/adwaita-lite-flatpak-setup`

References in `build_files/build.sh`:
- Remove `systemctl enable adwaita-lite-flatpak-setup.service`
- Remove `chmod 0755 /usr/libexec/adwaita-lite-flatpak-setup`

Update `files/usr/libexec/adwaita-lite-session-init`:
- Remove lines 53-60 (the background subshell that checks for the stamp file and sends a `notify-send` notification). The wizard now always writes the stamp file on completion, making this notification path obsolete.

## Package Dependencies

Add to `build_files/build.sh` `dnf5 install` list:

- `NetworkManager-libnm` -- provides `gi.repository.NM` typelib. `network-manager-applet` pulls the `libnm` shared library but NOT the GObject introspection typelib. Must be added explicitly.
- `flatpak` -- not present in the Fedora bootc base image (`ghcr.io/ublue-os/base-main:latest`). Must be added explicitly.

## Navigation Changes

- Page constants shift: `PAGE_ACCOUNT=1`, `PAGE_SYSTEM=2`, `PAGE_APPS=3`, `PAGE_CONFIRM=4`, `PAGE_PROGRESS=5`
- Step indicator uses dynamic count: `f"Step {n} of {total}"` where total adjusts if Network was auto-skipped
- Step indicator hidden on Progress page
- Back button hidden on Network page (or Account if Network was skipped) and Progress page
- Next button label: "Next" on all pages except Confirm ("Set Up") and Progress (hidden)

## File Changes Summary

| File | Change |
|------|--------|
| `files/usr/bin/adwaita-lite-setup-wizard` | Add Network page, Apps page, Progress page; update navigation; add libnm imports; update Confirm summary; step-runner threading |
| `build_files/build.sh` | Add `NetworkManager-libnm` and `flatpak` packages; remove flatpak-setup service enable and chmod |
| `files/usr/libexec/adwaita-lite-session-init` | Remove stamp file notification block (lines 53-60) |
| `files/etc/systemd/system/adwaita-lite-flatpak-setup.service` | Delete |
| `files/usr/libexec/adwaita-lite-flatpak-setup` | Delete |
