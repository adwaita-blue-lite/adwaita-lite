# Settings App v2: Comprehensive Settings for a Complete Desktop

Supersedes: `2026-03-28-settings-app-redesign.md` (v1 redesign)

## Goal

Transform the settings app from a functional-but-incomplete 9-page utility into a comprehensive system settings application that gives users full desktop configurability. A user should never need to open a terminal to change a routine setting.

## Design Philosophy

**Adwaita-centered, ChromeOS-inspired.** Adwaita provides the design tokens and theme consistency (colors, typography, widget styling). ChromeOS provides the interaction model and UX expectations (bottom shelf, app launcher, settings layout). Where they conflict, ChromeOS patterns win — this is a Chromebook replacement, not a GNOME derivative.

**libadwaita-free.** The image ships `adw-gtk3` for theming but does not link libadwaita at runtime. This avoids duplicating the library across RPM and Flatpak runtimes on RAM-constrained Chromebooks. All Adwaita visual patterns (toasts, action rows, toggle cards) are implemented in pure GTK4 CSS + Python to match Adwaita's look and behavior.

**Use context7 for GTK4 patterns during implementation.** All GTK4 widget usage, D-Bus integration, and async patterns must be verified against current GTK4 documentation via context7 to ensure modern best practices.

## Architecture

### Package Structure

The single-file monolith (`/usr/bin/adwaita-lite-settings`, 1609 lines) is replaced by a proper Python package:

```
/usr/lib/adwaita-lite/settings/
├── __init__.py
├── app.py              # SettingsApp, CSS loading, entry point
├── window.py           # SettingsWindow, sidebar, stack, search bar
├── base.py             # BasePage class, shared widget factories
├── settings_store.py   # JSON load/save, apply dispatch, toast feedback
├── dbus_helpers.py     # NM, BlueZ, logind, power-profiles D-Bus clients
├── events.py           # Event bus — pages subscribe to system changes
├── css/
│   └── style.css       # Extracted from inline CSS string
└── pages/
    ├── __init__.py
    ├── appearance.py
    ├── display.py
    ├── network.py
    ├── bluetooth.py
    ├── panel.py
    ├── mouse_touchpad.py
    ├── keyboard.py
    ├── sound.py
    ├── power_lock.py
    ├── accessibility.py
    ├── datetime.py
    ├── users.py
    ├── language.py
    ├── default_apps.py
    └── about.py
```

`/usr/bin/adwaita-lite-settings` becomes a thin launcher that adds the package root to `sys.path`:

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/lib/adwaita-lite")
from settings.app import main
main()
```

### BasePage

All page classes inherit from `BasePage`, which provides:

- Standard page margins (40px horizontal, 32px vertical) and spacing (24px between groups)
- Widget factories moved from `SettingsWindow`: `make_group_label()`, `make_setting_row()`, `make_info_row()`, `make_toggle_cards()`
- A `refresh()` method pages can override for live-updating content
- Access to the `SettingsStore` and `EventBus` instances
- A `search_keywords` property returning `list[tuple[str, str]]` of `(group_label, setting_label)` pairs for search indexing

### SettingsStore

Encapsulates all settings persistence:

- Reads/writes `~/.config/adwaita-lite/settings.json`
- Defaults from `/usr/share/adwaita-lite/defaults/settings.json`
- Atomic file writes (write to `.tmp`, then `os.rename`)
- `save_and_apply(key, value)` and `save_dict_and_apply(updates)` — return success/failure
- Built-in debounce for slider-type settings (configurable delay, default 300ms), replacing per-page timer boilerplate
- Triggers toast notification on apply completion or failure
- Runs `/usr/libexec/adwaita-lite-apply-settings` via `subprocess.Popen`, then monitors the process with `GLib.child_watch_add` to detect exit code. Exit 0 triggers success toast; non-zero triggers error toast with stderr excerpt.

### Event Bus

Simple publish/subscribe system for D-Bus signals:

- D-Bus signal handlers publish typed events (e.g., `"network-changed"`, `"audio-device-added"`, `"bluetooth-device-found"`, `"power-profile-changed"`)
- Pages subscribe in their constructor, unsubscribe on teardown
- All signal callbacks marshal to the main GTK thread via `GLib.idle_add`
- Keeps D-Bus wiring out of page code entirely

### D-Bus Helpers (`dbus_helpers.py`)

`Gio.DBusProxy` wrappers for:

- **NetworkManager** (`org.freedesktop.NetworkManager`): connection state, WiFi scan/connect/disconnect, access point enumeration, hidden network connection, device changes
- **BlueZ** (`org.bluez`): adapter power, device discovery, pairing, connect/disconnect, device removal
- **PulseAudio/PipeWire**: device hotplug, volume changes via `Gio.DBusConnection.signal_subscribe` on the PulseAudio D-Bus interface
- **power-profiles-daemon** (`net.hadess.PowerProfiles`): read/set active profile, subscribe to changes
- **logind** (`org.freedesktop.login1`): lid switch state, suspend configuration
- **AccountsService** (`org.freedesktop.Accounts`): user display name, password, auto-login, avatar

### Toast Notification System

Custom lightweight toast widget matching Adwaita's `AdwToast` visual pattern:

- Overlay on the content area, slides in from the bottom
- Shows success ("Settings applied") or error ("Failed to apply: ...") messages
- Auto-dismisses after 3 seconds, or click to dismiss
- `SettingsStore.save_and_apply()` triggers toast on completion/failure

### Search

- `Gtk.SearchBar` + `Gtk.SearchEntry` in the sidebar header area
- Each page registers searchable keywords via `search_keywords` property
- Typing filters sidebar rows to pages containing matching keywords
- `Ctrl+F` toggles search bar via `Gtk.Application.set_accels_for_action`

## Category Order

Updated from 9 to 15 categories:

1. Appearance
2. Display
3. Network
4. Bluetooth
5. Panel
6. Mouse & Touchpad
7. Keyboard
8. Sound
9. Power & Lock
10. Accessibility
11. Date & Time
12. Users
13. Language & Region
14. Default Apps
15. About

Network and Bluetooth are placed immediately after Display — users expect connectivity settings near the top, matching ChromeOS and GNOME Settings ordering.

## New Pages

### Network Page (`network-wired-symbolic`)

**WiFi section:**
- Toggle: WiFi on/off via NM D-Bus `Enable` property
- Scan results: List of available networks with signal strength icon (4 levels), security lock icon, network name. Auto-refreshes via NM D-Bus signals.
- Click a network to connect. If secured, open password dialog (SSID pre-filled, password entry, "Show password" toggle, Connect/Cancel buttons).
- "Connect to Hidden Network" button: Dialog with SSID text entry, security type dropdown (None / WPA/WPA2 / WPA3), password entry. Uses `AddAndActivateConnection` on NM D-Bus. Same pattern as the setup wizard for consistency.
- Forget saved networks: Each saved/connected network row has a "Forget" button visible on the right side of the row.

**Active connection section:**
- Current network name, signal strength, IP address, gateway, DNS

**Wired section:**
- Show status if ethernet detected (connected/disconnected, auto-connect indicator, DHCP/static)

**Advanced button:** Opens `nm-connection-editor` for VPN, proxy, static IP, 802.1x Enterprise.

### Bluetooth Page (`bluetooth-symbolic`)

- Toggle: Bluetooth on/off via BlueZ D-Bus adapter `Powered` property
- **Paired devices list:** Name, device type icon, connection status badge, Connect/Disconnect button, Forget button
- **Scan section:** "Search for devices" button triggers BlueZ `StartDiscovery`. Shows found devices in a list with Pair button. Auto-stops discovery after 30 seconds or on page leave.
- **Pairing flow:** Click Pair -> BlueZ agent handles PIN confirmation dialog if needed -> device appears in paired list
- **Advanced button:** Opens `blueman-manager`

### Accessibility Page (`preferences-desktop-accessibility-symbolic`)

- **Large text:** Toggle. Scales system font from Roboto 11 to Roboto 14. Propagates through the design token system to all config writers (GTK, foot, fuzzel, waybar, mako).
- **Cursor size:** Dropdown (Default 24px / Large 32px / Larger 48px). Updates `org.gnome.desktop.interface cursor-size` and labwc config.
- **High contrast:** Toggle. Forces dark theme + increased border opacity/width for better visibility.
- **Reduce motion:** Toggle. Disables stack crossfade transitions, sets `gtk-enable-animations` to false.

### Date & Time Page (`preferences-system-time-symbolic`)

- **Timezone:** Searchable dropdown populated from `/usr/share/zoneinfo`. Applied via `timedatectl set-timezone`.
- **Automatic time:** Toggle for NTP sync via `timedatectl set-ntp`.
- **24-hour clock:** Toggle. Updates waybar clock format string in settings.json and apply-settings config writer.
- **Current date/time display:** Live-updating label showing current time in chosen format. Refreshes every second via `GLib.timeout_add_seconds`.

### Users Page (`system-users-symbolic`)

- **Display name:** Editable text field. Applied via AccountsService D-Bus `SetRealName`.
- **Password:** "Change Password" button opens dialog with current password, new password, confirm new password fields. Applied via AccountsService D-Bus `SetPassword`.
- **Auto-login:** Toggle via AccountsService D-Bus `SetAutomaticLogin`.

### Language & Region Page (`preferences-desktop-locale-symbolic`)

- **System language:** Dropdown of installed locales. Applied via `localectl set-locale LANG=<locale>`.
- **Regional formats:** Dropdown for date/number/currency format locale (e.g., `LC_TIME`, `LC_NUMERIC`).
- **Info banner:** "Changes take effect after logging out" — persistent info bar at top of page when changes are pending.

## Existing Page Expansions

### Appearance Page

**New setting — Font size:**
- Dropdown: Small (10pt) / Default (11pt) / Large (13pt) / Larger (15pt)
- Propagates through design token system to all config writers

No other changes. Cursor size moves to Accessibility page.

### Display Page

**New settings:**
- **Resolution & refresh rate:** Dropdown per detected display via `wlr-randr` query. Uses the same 15-second revert confirmation dialog as scale changes.
- **Night light:** Toggle + color temperature slider (3500K–6500K) + schedule dropdown (Sunset to Sunrise / Custom hours with time pickers). "Sunset to Sunrise" uses gammastep's automatic mode which calculates times from the system timezone — no geolocation required. "Custom" lets the user set explicit start/end times. Managed by spawning/killing `gammastep` with configured temperature. Settings stored in `settings.json` as `night_light_enabled`, `night_light_temp`, `night_light_schedule`, `night_light_start`, `night_light_end`.
- **Advanced button:** Opens `wdisplays` for spatial multi-monitor arrangement, mirroring, and extended desktop configuration.

### Panel Page

**Pinned apps picker (replaces text entry):**
- "Add pinned app" opens a scrollable list of all installed apps (from `Gio.AppInfo.get_all()`, filtered to exclude NoDisplay entries)
- Each row shows icon + app name
- Click to add. Name, exec command, and icon are extracted from the `.desktop` entry automatically.
- No more manual Name/Command/Icon text fields.

**Module reordering within sections:**
- Context-dependent buttons based on panel orientation:
  - Horizontal panel (top/bottom): `◂`/`▸` to move between sections, `▲`/`▼` to reorder within a section
  - Vertical panel (left/right): `▲`/`▼` to move between sections, `◂`/`▸` to reorder within a section
- Arrows always match the spatial direction they represent on screen.

### Sound Page

**Live updates:**
- Subscribe to PulseAudio/PipeWire D-Bus signals for device hotplug and volume changes
- Dropdowns and sliders update in real-time when devices are added/removed or volume changes externally (e.g., via panel slider or hardware keys)

### Power & Lock Page

**New settings:**
- **Power profile:** Toggle cards for Balanced / Power Saver / Performance. Read/written via `net.hadess.PowerProfiles` D-Bus interface. Live-updates via D-Bus signal subscription.
- **Suspend on idle:** Dropdown with timeout options (same intervals as lock timeout). Integrated with swayidle.
- **Lid close behavior:** Dropdown (Suspend / Lock / Do Nothing). Requires root to write `/etc/systemd/logind.conf.d/`. Implementation: a small helper script at `/usr/libexec/adwaita-lite-lid-action` that accepts the action as an argument, writes the logind override, and calls `systemctl kill -s HUP systemd-logind`. The helper is authorized via a polkit policy file at `/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy` that grants the active session user permission to run it via `pkexec`.

### Keyboard Page

**New — Shortcuts editor:**
- Full list of current labwc keybindings parsed from `rc.xml`
- Each row: action description (human-readable) + current key binding displayed as a styled badge
- Click the binding badge to enter capture mode: overlay says "Press new shortcut...", `Gtk.EventControllerKey` captures the combo, Escape cancels
- Conflict detection: if combo is already bound, show warning with option to reassign or cancel
- "Reset to Default" button per individual shortcut
- "Reset All Shortcuts" button at bottom of section

**New — Caps Lock behavior:**
- Dropdown: Default / Ctrl / Escape / Disabled
- Applied via xkb options (`caps:ctrl_modifier`, `caps:escape`, `caps:none`) in labwc `rc.xml`

### Default Apps Page

**Fix Terminal selection:**
- Write a `~/.local/share/applications/terminal.desktop` wrapper that references the chosen terminal, so the selection actually takes effect system-wide.

**Additional categories:**
- Image Viewer (`image/png`)
- PDF Viewer (`application/pdf`)
- Email Client (`x-scheme-handler/mailto`)

### About Page

**New info rows:**
- **Graphics:** GPU name from `/sys/class/drm/` or parsed from `lspci`
- **OS Updates:** Current image version and date. "Check for Updates" button runs `bootc status --json`, parses output, reports if an update is available with version info.

## New Packages for Image

Added to `build.sh`:

| Package | Purpose | Approx Size |
|---------|---------|-------------|
| `wdisplays` | Multi-monitor arrangement (launched from Display page) | ~1MB |
| `gammastep` | Night light color temperature control | ~200KB |
| `nm-connection-editor` | Advanced network configuration (VPN, 802.1x) | ~2MB |

Already present: `blueman` (includes `blueman-manager`), `pavucontrol` (advanced audio).

## New Settings Keys

Added to `settings.json` defaults:

```json
{
  "font_size": 11,
  "cursor_size": 24,
  "high_contrast": false,
  "reduce_motion": false,
  "night_light_enabled": false,
  "night_light_temp": 4500,
  "night_light_schedule": "sunset-sunrise",
  "night_light_start": "20:00",
  "night_light_end": "06:00",
  "clock_24h": false,
  "power_profile": "balanced",
  "suspend_timeout": 0,
  "lid_close_action": "suspend",
  "capslock_behavior": "default"
}
```

Keys not stored in settings.json (managed by their respective systems):
- Network/WiFi state: NetworkManager
- Bluetooth state: BlueZ
- Sound devices/volume: PipeWire/PulseAudio
- Timezone/NTP: timedatectl
- User account: AccountsService
- Locale: localectl
- Default apps: xdg-mime / mimeapps.list
- Keyboard shortcuts: labwc rc.xml directly

## Phasing

### Phase 1 — Architecture + Connectivity

1. Split monolith into `adwaita_lite_settings/` package structure
2. Extract CSS to `css/style.css`
3. Implement `BasePage`, `SettingsStore` (with atomic writes, debounce, toast feedback)
4. Implement event bus (`events.py`)
5. Implement D-Bus helpers for NetworkManager and BlueZ
6. Implement toast notification widget
7. Implement search bar with sidebar filtering
8. Build Network page (WiFi scan/connect/hidden network, wired status, active connection info, advanced button)
9. Build Bluetooth page (toggle, paired devices, scan/pair, advanced button)
10. Migrate all 9 existing pages to new package structure (no feature changes, just move + inherit BasePage)
11. Add `gammastep`, `wdisplays`, `nm-connection-editor` to `build.sh`

**Exit criteria:** All existing functionality works identically on the new architecture. Network and Bluetooth pages are live with D-Bus event subscriptions. Toast notifications work. Search filters sidebar.

### Phase 2 — Display + Accessibility + Sound + Power

1. Display page expansion: resolution/refresh rate dropdowns, night light (gammastep integration), advanced wdisplays button
2. Accessibility page: large text, cursor size, high contrast, reduce motion
3. Sound page rewrite with live PipeWire/PulseAudio D-Bus event subscriptions
4. Power & Lock expansion: power profiles toggle cards, suspend on idle, lid close behavior
5. Pinned apps picker: replace text entry with app chooser using `Gio.AppInfo`
6. Panel page: context-dependent reorder buttons

**Exit criteria:** Display page is a real display manager. Sound page is live-reactive. Accessibility exists. Power page exposes power-profiles-daemon. Pinned apps are user-friendly.

### Phase 3 — Keyboard + System Pages + Polish

1. Keyboard shortcuts editor: full keybinding list, `Gtk.EventControllerKey` capture mode, conflict detection, reset
2. Caps Lock behavior dropdown
3. Date & Time page: timezone, NTP toggle, 24h clock, live time display
4. Users page: display name, password change, auto-login
5. Language & Region page: locale selection, regional formats, relogin info banner
6. Default Apps fixes: terminal actually works, add image/PDF/email categories
7. About page expansion: GPU info, bootc update check
8. Appearance page: font size dropdown
9. Final polish pass across all pages

**Exit criteria:** Every page is complete. Full settings coverage. No setting requires a terminal to change.
