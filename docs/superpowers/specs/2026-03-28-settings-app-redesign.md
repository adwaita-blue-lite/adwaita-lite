# Settings App Redesign

## Overview

Redesign the Adwaita-Lite settings application from a 3-tab utility into a full sidebar-detail settings app with 9 categories. Goal: ChromeOS-level refinement on constrained hardware, using pure GTK4 (no libadwaita dependency).

## Architecture

**Single-file rewrite** of `/usr/bin/adwaita-lite-settings`. Each category is a page class that returns a widget. The main window owns the sidebar and swaps content via `Gtk.Stack`.

**Backend unchanged.** All settings flow through the existing pipeline: `settings.json` → `adwaita-lite-apply-settings` → generated configs. New categories (mouse, keyboard, power) add keys to settings.json and corresponding generation logic to apply-settings. Sound and Default Apps are direct control surfaces that don't use settings.json.

## Window Structure

- Default size: 900x600, minimum: 700x500
- Left: 220px sidebar (`Gtk.ListBox`, single selection), icon + label per row
- Right: scrollable content area (`Gtk.Stack`, crossfade transition 150ms)
- Sidebar background: `headerbar_bg` (slightly darker than content `window_bg`)
- All colors derived from existing Adwaita design token system

## Category Order

1. Appearance
2. Display
3. Panel
4. Mouse & Touchpad
5. Keyboard
6. Sound
7. Power & Lock
8. Default Apps
9. About

## Page Designs

### 1. Appearance

**Theme group** — two large toggleable cards: "Light" / "Dark". Each shows a mini colored preview rectangle. Clicking selects.

**Accent color group** — row of 9 colored circles. Selected circle gets a ring/check indicator. Same 9 colors as today (blue, teal, green, yellow, orange, red, pink, purple, slate).

**Wallpaper group** — grid of thumbnail previews from `/usr/share/backgrounds/` plus a "Custom..." button that opens a file chooser via the XDG portal. Selected wallpaper gets a highlight border.

All changes apply live via `apply-settings`.

### 2. Display

**Scale group** — horizontal row of preset buttons: 75%, 100%, 125%, 150%, 175%, 200%. Clicking applies immediately via `wlr-randr`. 15-second revert confirmation dialog retained from current implementation.

Resolution, refresh rate, and multi-monitor layout are out of scope for v1.

### 3. Panel

**Position group** — four toggleable cards: Bottom, Top, Left, Right. Each shows a mini diagram.

**Density group** — two toggleable cards: "Normal" ("Larger touch targets") / "Compact" ("More screen space").

**Module layout group** — existing three-section drag-and-drop (Start, Center, End). No changes.

**Pinned apps group** — existing add/remove/reorder list. No changes.

### 4. Mouse & Touchpad

New page. Settings applied via libinput configuration in labwc's `rc.xml`.

**Touchpad group:**
- Tap to click — toggle (default: on)
- Natural scrolling — toggle (default: off), subtitle: "Content moves with your fingers"
- Scroll speed — slider, 1-10, default 5
- Pointer speed — slider, -1.0 to 1.0, default 0

**Mouse group:**
- Natural scrolling — toggle (default: off)
- Pointer speed — slider, -1.0 to 1.0, default 0
- Acceleration profile — two toggleable cards: "Adaptive" (default) / "Flat"

New keys in settings.json. apply-settings writes `<libinput>` config into `~/.config/labwc/rc.xml`, then `labwc --reconfigure`.

### 5. Keyboard

New page. Settings applied via xkb configuration in labwc's `rc.xml`.

**Layout group:**
- Keyboard layout — dropdown from `localectl list-x11-keymap-layouts`. Human-readable names (e.g., "English (US)"). Default: "us".
- Variant — secondary dropdown, populated from selected layout. Hidden if no variants exist.

**Repeat group:**
- Repeat delay — slider, 150-1000ms, default 300ms
- Repeat rate — slider, 10-80/sec, default 40/sec

New keys in settings.json. apply-settings writes xkb and repeat settings into rc.xml.

### 6. Sound

Direct control surface — no settings.json persistence. PipeWire/PulseAudio manages state.

**Output group:**
- Output device — dropdown from `pactl list sinks`. Changing calls `pactl set-default-sink`.
- Volume — slider 0-100% with mute toggle.

**Input group:**
- Input device — dropdown from `pactl list sources`. Changing calls `pactl set-default-source`.
- Volume — slider 0-100% with mute toggle.

Device lists populated on page navigate (not polling).

### 7. Power & Lock

**Lock group:**
- Lock screen after — dropdown: 1, 2, 5, 10, 15, 30 minutes, Never. Default: 5 min.
- Turn off display after — dropdown: same intervals. Default: 10 min.

New keys in settings.json. apply-settings regenerates swayidle invocation and restarts it.

Lid close behavior is out of scope for v1 (requires root for logind.conf).

### 8. Default Apps

**Application dropdowns:**
- Web Browser — `.desktop` files with `x-scheme-handler/http`
- File Manager — `.desktop` files with `inode/directory`
- Terminal — `.desktop` files with `TerminalEmulator` category
- Text Editor — `.desktop` files with `text/plain`
- Media Player — `.desktop` files with `video/*`

Dropdowns show app display name + icon. Selection writes to `~/.config/mimeapps.list` via `xdg-mime default`. Desktop file scan runs once per page visit.

### 9. About

Read-only info page:
- OS name + version — `/etc/os-release`
- Hostname — `socket.gethostname()`
- Hardware — CPU from `/proc/cpuinfo`, RAM from `/proc/meminfo`
- Disk — used/total for root via `os.statvfs`
- Desktop — labwc version from `labwc --version`

## Visual Design

All pages use the same visual language:

- **Group headers** — bold label, no box or frame, consistent top margin between groups
- **Toggle cards** — rounded rectangles with subtle border, fill with accent color when selected
- **Toggles** — `Gtk.Switch`, right-aligned in setting rows
- **Sliders** — `Gtk.Scale`, accent-colored fill
- **Dropdowns** — `Gtk.DropDown`, consistent width within groups
- **Setting rows** — label on left, control on right, optional subtitle below label in secondary color

Colors, fonts, and spacing all derived from the existing Adwaita design token system. Dark/light theme applies to the settings app itself in real-time when changed on the Appearance page.

## Backend Changes (apply-settings)

New settings.json keys for v1:

```json
{
  "touchpad_tap_to_click": true,
  "touchpad_natural_scroll": false,
  "touchpad_scroll_speed": 5,
  "touchpad_pointer_speed": 0.0,
  "mouse_natural_scroll": false,
  "mouse_pointer_speed": 0.0,
  "mouse_accel_profile": "adaptive",
  "keyboard_layout": "us",
  "keyboard_variant": "",
  "keyboard_repeat_delay": 300,
  "keyboard_repeat_rate": 40,
  "lock_timeout": 300,
  "display_off_timeout": 600
}
```

apply-settings gains two new generation functions:
- `write_labwc_rc_overrides()` — writes libinput, xkb, and repeat settings into `~/.config/labwc/rc.xml`
- `write_swayidle_config()` — writes swayidle command args to a config file, restarts swayidle

## Performance Considerations

- 150ms crossfade transitions (GPU-composited via Wayland, near-zero CPU)
- Device lists (sound, keyboard layouts) populated on-navigate, not at startup
- No polling anywhere — all controls are one-shot reads + event-driven updates
- Wallpaper thumbnails loaded lazily as grid populates

## Scope Boundaries

**In scope:** All 9 pages as described above.

**Out of scope for v1:**
- Multi-monitor layout and per-monitor scaling
- Display resolution and refresh rate
- Lid close behavior (requires root)
- Notification behavior settings
- Accessibility settings
- Session/startup app management
- Bluetooth and WiFi management (handled by tray applets)
