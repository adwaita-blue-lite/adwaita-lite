# Settings App Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the settings app as a sidebar-detail GTK4 application with 9 categories covering appearance, display, panel, input devices, sound, power, default apps, and system info.

**Architecture:** Single-file rewrite of `adwaita-lite-settings` using page classes. Each category is a class returning a `Gtk.Widget`. Main window uses `Gtk.ListBox` sidebar + `Gtk.Stack` content area. Backend changes add two new generators to `apply-settings` (rc.xml overrides for libinput/xkb, swayidle config). Autostart updated to read lock/display timeouts from settings.

**Tech Stack:** Python 3, GTK4 (gi.repository), pactl CLI, wlr-randr, xdg-mime, labwc rc.xml, swayidle

**Spec:** `docs/superpowers/specs/2026-03-28-settings-app-redesign.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `files/usr/bin/adwaita-lite-settings` | Rewrite | Full settings app (sidebar shell + 9 page classes) |
| `files/usr/libexec/adwaita-lite-apply-settings` | Modify | Add `write_labwc_rc_overrides()`, `write_swayidle_config()`, update `main()` |
| `files/usr/share/adwaita-lite/defaults/settings.json` | Modify | Add new default keys for input, keyboard, power |
| `files/etc/xdg/labwc/autostart` | Modify | Read lock/display-off timeouts from settings for swayidle |

---

### Task 1: Update defaults and apply-settings backend

Add the new settings keys and backend generators before touching the UI, so the pipeline is ready when pages need it.

**Files:**
- Modify: `files/usr/share/adwaita-lite/defaults/settings.json`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`
- Modify: `files/etc/xdg/labwc/autostart`

- [ ] **Step 1: Add new default keys to settings.json**

Replace the current contents with:

```json
{
  "edge": "bottom",
  "density": "normal",
  "theme": "light",
  "accent": "blue",
  "scale": 1.0,
  "layout": {
    "start": ["custom/launcher"],
    "center": ["wlr/taskbar"],
    "end": ["pulseaudio", "backlight", "battery", "clock", "custom/power", "tray"]
  },
  "wallpaper": "/usr/share/backgrounds/adwaita-lite/chrome-dawn.svg",
  "pinned": [
    {"name": "Chrome",  "command": "flatpak run com.google.Chrome", "icon": "com.google.Chrome"},
    {"name": "Bazaar",  "command": "flatpak run dev.bazaar.app",    "icon": "dev.bazaar.app"}
  ],
  "touchpad_tap_to_click": true,
  "touchpad_natural_scroll": false,
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

- [ ] **Step 2: Add `write_labwc_rc_overrides()` to apply-settings**

Insert this function before `write_swaylock_config()` in apply-settings. It generates `~/.config/labwc/rc.xml` with libinput touchpad/mouse config plus xkb keyboard settings. labwc merges this with the system `/etc/xdg/labwc/rc.xml`.

```python
def write_labwc_rc_overrides(settings: dict) -> None:
    LABWC_DIR.mkdir(parents=True, exist_ok=True)

    tap = "yes" if settings.get("touchpad_tap_to_click", True) else "no"
    tp_nat = "yes" if settings.get("touchpad_natural_scroll", False) else "no"
    tp_speed = settings.get("touchpad_pointer_speed", 0.0)
    m_nat = "yes" if settings.get("mouse_natural_scroll", False) else "no"
    m_speed = settings.get("mouse_pointer_speed", 0.0)
    m_accel = settings.get("mouse_accel_profile", "adaptive")

    kb_layout = settings.get("keyboard_layout", "us")
    kb_variant = settings.get("keyboard_variant", "")
    repeat_delay = settings.get("keyboard_repeat_delay", 300)
    repeat_rate = settings.get("keyboard_repeat_rate", 40)

    variant_line = ""
    if kb_variant:
        variant_line = f"\n      <xkbVariant>{kb_variant}</xkbVariant>"

    rc = f"""\
<?xml version="1.0"?>
<labwc_config>
  <libinput>
    <device category="touchpad">
      <tap>{tap}</tap>
      <naturalScroll>{tp_nat}</naturalScroll>
      <pointerSpeed>{tp_speed}</pointerSpeed>
    </device>
    <device category="default">
      <naturalScroll>{m_nat}</naturalScroll>
      <pointerSpeed>{m_speed}</pointerSpeed>
      <accelProfile>{m_accel}</accelProfile>
    </device>
  </libinput>
  <keyboard>
    <repeatDelay>{repeat_delay}</repeatDelay>
    <repeatRate>{repeat_rate}</repeatRate>
    <keybind key="NULL">
      <action name="None"/>
    </keybind>
    <xkb>
      <xkbLayout>{kb_layout}</xkbLayout>{variant_line}
    </xkb>
  </keyboard>
</labwc_config>
"""

    with (LABWC_DIR / "rc.xml").open("w", encoding="utf-8") as handle:
        handle.write(rc)
```

Note: The `<keybind key="NULL">` is required because labwc's `<keyboard>` element needs at least one keybind child when used in an override file. This is a no-op keybind that satisfies the parser.

- [ ] **Step 3: Add `write_swayidle_config()` to apply-settings**

Insert after `write_labwc_rc_overrides()`. Writes a shell snippet that the autostart script sources.

```python
SWAYIDLE_CONF = CONFIG_HOME / "adwaita-lite" / "swayidle.conf"

def write_swayidle_config(settings: dict) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)

    lock_timeout = int(settings.get("lock_timeout", 300))
    display_off = int(settings.get("display_off_timeout", 600))

    lines = ["#!/bin/sh", "# Generated by adwaita-lite-apply-settings"]

    args = "swayidle -w"
    if lock_timeout > 0:
        args += f" \\\n  timeout {lock_timeout} 'swaylock -f'"
    if display_off > 0:
        args += f" \\\n  timeout {display_off} 'wlopm --off \"*\"' resume 'wlopm --on \"*\"'"
    args += " \\\n  before-sleep 'swaylock -f'"

    lines.append(args)

    SWAYIDLE_CONF.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Update `main()` in apply-settings to call new functions**

In the `main()` function, add calls after `write_swaylock_config(tokens)`:

```python
    write_labwc_rc_overrides(settings)
    write_swayidle_config(settings)
```

And in the Wayland live-reload section, add swayidle restart:

```python
        restart_program("swayidle", [
            "sh", "-c", f"exec $(cat {SWAYIDLE_CONF})"
        ])
```

Wait — that's fragile. Better: have `write_swayidle_config()` write just the args, and restart swayidle directly with parsed args. Actually, simplest approach: write the timeout values to a file and have autostart read them. Let me revise.

Replace the swayidle restart with:

```python
        # Restart swayidle with updated timeouts
        lock_t = int(settings.get("lock_timeout", 300))
        dpms_t = int(settings.get("display_off_timeout", 600))
        idle_cmd = ["swayidle", "-w"]
        if lock_t > 0:
            idle_cmd += ["timeout", str(lock_t), "swaylock -f"]
        if dpms_t > 0:
            idle_cmd += ["timeout", str(dpms_t), 'wlopm --off "*"',
                         "resume", 'wlopm --on "*"']
        idle_cmd += ["before-sleep", "swaylock -f"]
        restart_program("swayidle", idle_cmd)
```

And remove `write_swayidle_config()` entirely — we don't need a config file if we restart inline. The autostart also needs to read from settings.

- [ ] **Step 5: Update autostart to read swayidle timeouts from settings**

Replace the hardcoded swayidle block (lines 34-38 of autostart) with:

```sh
# Read idle timeouts from user settings (defaults: lock 300s, display-off 600s)
_lock_timeout=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('lock_timeout', 300))" "$_settings" 2>/dev/null || echo "300")
_dpms_timeout=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('display_off_timeout', 600))" "$_settings" 2>/dev/null || echo "600")

_idle_args="swayidle -w"
[ "$_lock_timeout" != "0" ] && _idle_args="$_idle_args timeout $_lock_timeout 'swaylock -f'"
[ "$_dpms_timeout" != "0" ] && _idle_args="$_idle_args timeout $_dpms_timeout 'wlopm --off \"*\"' resume 'wlopm --on \"*\"'"
_idle_args="$_idle_args before-sleep 'swaylock -f'"
eval "$_idle_args" >/dev/null 2>&1 &
```

- [ ] **Step 6: Verify apply-settings still parses**

Run: `python3 -m py_compile files/usr/libexec/adwaita-lite-apply-settings`
Expected: no output (success)

- [ ] **Step 7: Commit**

```
git add files/usr/share/adwaita-lite/defaults/settings.json \
       files/usr/libexec/adwaita-lite-apply-settings \
       files/etc/xdg/labwc/autostart
git commit -m "feat: add backend for input, keyboard, and power settings"
```

---

### Task 2: Settings app shell — sidebar + stack + CSS

Rewrite the settings app with the new window structure. This task creates the shell with empty placeholder pages. Subsequent tasks fill in each page.

**Files:**
- Rewrite: `files/usr/bin/adwaita-lite-settings`

- [ ] **Step 1: Write the app skeleton with sidebar navigation**

Replace the entire file. This establishes: CSS, constants, settings I/O, the sidebar `Gtk.ListBox`, the `Gtk.Stack` content area, and stub page classes.

Key structural elements:

```python
#!/usr/bin/env python3

import copy
import json
import os
import socket
import subprocess
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

APP_ID = "org.adwaitabluelite.Settings"
# ... (same path constants as current file) ...

CATEGORIES = [
    ("display-brightness-symbolic", "Appearance"),
    ("video-display-symbolic", "Display"),
    ("view-app-grid-symbolic", "Panel"),
    ("input-mouse-symbolic", "Mouse & Touchpad"),
    ("input-keyboard-symbolic", "Keyboard"),
    ("audio-volume-high-symbolic", "Sound"),
    ("system-shutdown-symbolic", "Power & Lock"),
    ("application-x-executable-symbolic", "Default Apps"),
    ("help-about-symbolic", "About"),
]
```

The window class:

```python
class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Settings")
        self.set_default_size(900, 600)
        self.settings = ensure_settings()

        # Horizontal paned: sidebar | content
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_position(220)

        # Sidebar
        sidebar_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self._sidebar = Gtk.ListBox()
        self._sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar.add_css_class("sidebar")
        sidebar_scroll.set_child(self._sidebar)
        paned.set_start_child(sidebar_scroll)

        # Content stack
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        content_scroll = Gtk.ScrolledWindow()
        content_scroll.set_child(self._stack)
        paned.set_end_child(content_scroll)

        self._pages = [
            AppearancePage(self),
            DisplayPage(self),
            PanelPage(self),
            MouseTouchpadPage(self),
            KeyboardPage(self),
            SoundPage(self),
            PowerLockPage(self),
            DefaultAppsPage(self),
            AboutPage(self),
        ]

        for i, (icon_name, label) in enumerate(CATEGORIES):
            row = self._build_sidebar_row(icon_name, label)
            self._sidebar.append(row)
            self._stack.add_named(self._pages[i].build(), f"page-{i}")

        self._sidebar.connect("row-selected", self._on_row_selected)
        self._sidebar.select_row(self._sidebar.get_row_at_index(0))

        self.set_child(paned)
```

Each page class follows this pattern:

```python
class AppearancePage:
    def __init__(self, win: SettingsWindow) -> None:
        self.win = win

    def build(self) -> Gtk.Widget:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.set_margin_top(32)
        page.set_margin_bottom(32)
        page.set_margin_start(40)
        page.set_margin_end(40)
        # ... build groups ...
        return page
```

Shared helper methods on `SettingsWindow`:
- `_build_sidebar_row(icon_name, label)` — creates a ListBoxRow with icon + label
- `_on_row_selected(listbox, row)` — switches stack to corresponding page
- `save_and_apply(key, value)` — saves one key to settings.json and runs apply-settings
- `save_dict_and_apply(updates: dict)` — saves multiple keys at once
- `_make_group_label(text)` — returns a bold section header label
- `_make_setting_row(label, subtitle, control)` — returns a horizontal box with label on left, control on right
- `_make_toggle_cards(options, active, callback)` — returns a row of selectable card buttons

CSS string (loaded in `do_activate`):

```python
CSS = """\
.sidebar {
    background-color: @headerbar_bg_color;
}
.sidebar row {
    padding: 12px 16px;
    margin: 2px 8px;
    border-radius: 8px;
}
.sidebar row:selected {
    background-color: alpha(@accent_color, 0.15);
}
.sidebar .category-icon {
    margin-end: 12px;
    opacity: 0.8;
}
.sidebar .category-label {
    font-size: 14px;
}
.group-title {
    font-size: 15px;
    font-weight: bold;
    margin-bottom: 4px;
}
.setting-row {
    min-height: 48px;
    padding: 8px 0;
}
.setting-subtitle {
    font-size: 12px;
    opacity: 0.6;
}
.toggle-card {
    padding: 16px 24px;
    border-radius: 12px;
    border: 2px solid alpha(@borders, 0.5);
    background: none;
}
.toggle-card:checked,
.toggle-card.selected {
    border-color: @accent_color;
    background: alpha(@accent_color, 0.08);
}
.accent-circle {
    min-width: 32px;
    min-height: 32px;
    border-radius: 16px;
    padding: 0;
}
.accent-circle:checked {
    box-shadow: 0 0 0 3px @accent_color;
}
"""
```

Note: The CSS uses GTK4 named colors (`@headerbar_bg_color`, `@accent_color`, `@borders`) which are defined by the adw-gtk3 theme. This means the settings app automatically respects the current theme without any custom color management.

- [ ] **Step 2: Stub out all 9 page classes**

Each page class gets a `build()` method that returns a `Gtk.Box` with just the page title for now:

```python
class DisplayPage:
    def __init__(self, win): self.win = win
    def build(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        page.set_margin_top(32); page.set_margin_start(40)
        page.append(self.win._make_group_label("Display"))
        return page
# ... same pattern for all 9 ...
```

- [ ] **Step 3: Verify app launches**

Run: `python3 files/usr/bin/adwaita-lite-settings`
Expected: Window opens with sidebar showing 9 categories. Clicking each switches to a page with just the title.

- [ ] **Step 4: Commit**

```
git add files/usr/bin/adwaita-lite-settings
git commit -m "feat: settings app shell with sidebar navigation"
```

---

### Task 3: Appearance page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (AppearancePage class)

- [ ] **Step 1: Implement AppearancePage.build()**

Three groups:

**Theme group** — two `Gtk.ToggleButton` cards ("Light" / "Dark"). Use `_make_toggle_cards()`. On toggle, call `self.win.save_and_apply("theme", value)`.

**Accent group** — row of 9 `Gtk.ToggleButton` circles. Each gets a CSS class with inline background-color via a `Gtk.CssProvider` per button. Selecting saves `accent` key.

**Wallpaper group** — `Gtk.FlowBox` with thumbnails. Scan `BACKGROUNDS_ROOT` for image files. Each child is a `Gtk.Picture` (120x80) wrapped in a `Gtk.ToggleButton`. Add a "Custom..." button that opens `Gtk.FileDialog`. Selected wallpaper saves `wallpaper` key.

Use `Gtk.Picture.new_for_filename()` for thumbnails. Set `content_fit=Gtk.ContentFit.COVER` and fixed size request for uniform grid. Thumbnails load synchronously — with the small number of wallpapers in `/usr/share/backgrounds/` this is fine.

- [ ] **Step 2: Test appearance page**

Run the app, switch to Appearance. Verify:
- Theme cards toggle between light/dark, apply live
- Accent circles highlight on click, apply live
- Wallpaper grid shows thumbnails, clicking changes wallpaper

- [ ] **Step 3: Commit**

```
git commit -am "feat: appearance page — theme, accent, wallpaper"
```

---

### Task 4: Display page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (DisplayPage class)

- [ ] **Step 1: Implement DisplayPage.build()**

**Scale group** — row of `Gtk.ToggleButton` cards for each scale value: 75%, 100%, 125%, 150%, 175%, 200%. Port the existing revert dialog logic from the current settings app. On select:

1. Apply scale via `wlr-randr --output <name> --scale <value>` for all outputs
2. Show a `Gtk.MessageDialog` with 15-second countdown: "Keep this scale? Reverting in Ns..."
3. If confirmed, save to settings.json
4. If timer expires or cancelled, revert to previous scale

The revert dialog and scale application logic can be ported directly from the current `_build_display_tab()` method — it already works correctly.

- [ ] **Step 2: Test**

Run app, switch to Display. Change scale, verify revert dialog appears, verify countdown works.

- [ ] **Step 3: Commit**

```
git commit -am "feat: display page — scale presets with revert"
```

---

### Task 5: Panel page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (PanelPage class)

- [ ] **Step 1: Implement PanelPage.build()**

Port the existing Layout tab functionality into the new page class structure:

**Position group** — four toggle cards (Bottom, Top, Left, Right). Save `edge` key.

**Density group** — two toggle cards (Normal, Compact). Save `density` key.

**Module layout group** — port the existing drag-and-drop three-section system (`_build_layout_tab` from current file). The existing implementation uses `Gtk.DragSource` + `Gtk.DropTarget` on module labels within three `Gtk.ListBox` widgets (start, center, end). Port this as-is — it works well.

**Pinned apps group** — port existing pinned apps management (add/remove/reorder). Same pattern.

**Reset button** — restores default layout and pinned apps.

All existing layout/pinned logic from the current file transfers directly. The only change is wrapping it in the page class structure and using group labels instead of notebook tab headers.

- [ ] **Step 2: Test**

Run app. Verify drag-and-drop works, position/density cards apply, pinned apps add/remove works.

- [ ] **Step 3: Commit**

```
git commit -am "feat: panel page — position, density, layout, pinned apps"
```

---

### Task 6: Mouse & Touchpad page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (MouseTouchpadPage class)

- [ ] **Step 1: Implement MouseTouchpadPage.build()**

**Touchpad group:**
- Tap to click — `Gtk.Switch`, setting row. Reads/writes `touchpad_tap_to_click`.
- Natural scrolling — `Gtk.Switch` with subtitle "Content moves with your fingers". Reads/writes `touchpad_natural_scroll`.
- Pointer speed — `Gtk.Scale` horizontal, range -1.0 to 1.0, step 0.1, default 0.0. Reads/writes `touchpad_pointer_speed`.

**Mouse group:**
- Natural scrolling — `Gtk.Switch`. Reads/writes `mouse_natural_scroll`.
- Pointer speed — `Gtk.Scale`, same range. Reads/writes `mouse_pointer_speed`.
- Acceleration profile — two toggle cards: "Adaptive" / "Flat". Reads/writes `mouse_accel_profile`.

Each control's change signal calls `self.win.save_and_apply(key, value)`. The apply-settings backend (Task 1) writes these into the labwc rc.xml override.

For the `Gtk.Scale` sliders, use `connect("value-changed", ...)` with a 300ms debounce via `GLib.timeout_add` to avoid calling apply-settings on every pixel of slider movement.

- [ ] **Step 2: Test**

Run app, switch to Mouse & Touchpad. Toggle switches, move sliders, change accel profile. Verify settings.json updates. Verify `~/.config/labwc/rc.xml` is generated with correct libinput values.

- [ ] **Step 3: Commit**

```
git commit -am "feat: mouse and touchpad page — tap, scroll, speed, accel"
```

---

### Task 7: Keyboard page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (KeyboardPage class)

- [ ] **Step 1: Implement KeyboardPage.build()**

**Layout group:**

Populate keyboard layouts from `localectl list-x11-keymap-layouts`. Parse output into a list of layout codes. For human-readable names, maintain a small lookup dict for common layouts (us, gb, de, fr, es, it, pt, ru, jp, kr, etc.) and fall back to the raw code for others.

- Layout dropdown — `Gtk.DropDown` with `Gtk.StringList`. On change, saves `keyboard_layout` and repopulates variant dropdown.
- Variant dropdown — `Gtk.DropDown` populated from `localectl list-x11-keymap-variants <layout>`. Hidden if layout has no variants. Saves `keyboard_variant`.

**Repeat group:**
- Repeat delay — `Gtk.Scale`, range 150-1000ms, step 50, default 300. Saves `keyboard_repeat_delay`.
- Repeat rate — `Gtk.Scale`, range 10-80, step 5, default 40. Saves `keyboard_repeat_rate`.

Same debounce pattern as Mouse page for sliders.

- [ ] **Step 2: Test**

Run app, switch to Keyboard. Change layout, verify variant dropdown updates. Move sliders, verify settings.json and rc.xml update.

- [ ] **Step 3: Commit**

```
git commit -am "feat: keyboard page — layout, variant, repeat settings"
```

---

### Task 8: Sound page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (SoundPage class)

- [ ] **Step 1: Implement SoundPage.build()**

This page is a direct control surface — no settings.json, no apply-settings.

**Output group:**

Populate sinks: `pactl -f json list sinks`. Parse JSON, extract `name` and `description` for each sink. The default sink: `pactl get-default-sink`.

- Device dropdown — `Gtk.DropDown`. On change: `pactl set-default-sink <name>`.
- Volume slider — `Gtk.Scale`, 0-100. Read current: `pactl get-sink-volume @DEFAULT_SINK@` (parse percentage). On change: `pactl set-sink-volume @DEFAULT_SINK@ <N>%`.
- Mute toggle — `Gtk.Switch`. Read: `pactl get-sink-mute @DEFAULT_SINK@`. On change: `pactl set-sink-mute @DEFAULT_SINK@ <toggle>`.

**Input group:**

Same pattern with `pactl list sources` / `get-default-source` / `set-default-source` / `get-source-volume` / `set-source-mute`. Filter out monitor sources (names containing `.monitor`).

All pactl calls via `subprocess.run(..., capture_output=True, text=True)`. Device lists populated once in `build()`, not polling.

Volume slider uses the same 300ms debounce.

- [ ] **Step 2: Test**

Run app, switch to Sound. Verify device dropdowns populate. Change volume slider, verify audio changes. Toggle mute.

- [ ] **Step 3: Commit**

```
git commit -am "feat: sound page — output/input device, volume, mute"
```

---

### Task 9: Power & Lock page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (PowerLockPage class)

- [ ] **Step 1: Implement PowerLockPage.build()**

**Lock group:**

Timeout options as a list of `(label, seconds)` tuples:

```python
TIMEOUT_OPTIONS = [
    ("1 minute", 60),
    ("2 minutes", 120),
    ("5 minutes", 300),
    ("10 minutes", 600),
    ("15 minutes", 900),
    ("30 minutes", 1800),
    ("Never", 0),
]
```

- Lock screen after — `Gtk.DropDown` with `Gtk.StringList` of labels. Read current value from `lock_timeout`, find matching index. On change: `self.win.save_and_apply("lock_timeout", seconds)`.
- Turn off display after — same pattern with `display_off_timeout`.

apply-settings restarts swayidle with updated timeouts (from Task 1).

- [ ] **Step 2: Test**

Run app, switch to Power & Lock. Change timeouts, verify settings.json updates. Verify swayidle restarts with new timeout values (check `ps aux | grep swayidle`).

- [ ] **Step 3: Commit**

```
git commit -am "feat: power and lock page — idle timeouts"
```

---

### Task 10: Default Apps page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (DefaultAppsPage class)

- [ ] **Step 1: Implement DefaultAppsPage.build()**

**App categories:**

```python
APP_CATEGORIES = [
    ("Web Browser", "x-scheme-handler/http"),
    ("File Manager", "inode/directory"),
    ("Terminal", None),  # special: filter by Categories=TerminalEmulator
    ("Text Editor", "text/plain"),
    ("Media Player", "video/mp4"),
]
```

For each category, scan `.desktop` files in `/usr/share/applications/` and `~/.local/share/applications/`:
- Parse each `.desktop` file for `Name=`, `Exec=`, `MimeType=`, `Categories=`
- Filter to files whose `MimeType` contains the target mime type (or `Categories` contains `TerminalEmulator` for Terminal)
- Get current default: `xdg-mime query default <mime-type>` returns a `.desktop` filename

Build a `Gtk.DropDown` for each category. On change: `subprocess.run(["xdg-mime", "default", desktop_file, mime_type])`. For Terminal, also set the `x-scheme-handler/terminal` type.

Use `Gio.DesktopAppInfo` for parsing `.desktop` files — it handles the format correctly and provides `get_name()`, `get_id()`, `get_categories()`.

```python
def _scan_apps_for_mime(self, mime_type: str) -> list[Gio.DesktopAppInfo]:
    return Gio.AppInfo.get_all_for_type(mime_type)

def _scan_terminal_apps(self) -> list[Gio.DesktopAppInfo]:
    return [app for app in Gio.AppInfo.get_all()
            if app.get_categories() and "TerminalEmulator" in app.get_categories()]
```

- [ ] **Step 2: Test**

Run app, switch to Default Apps. Verify dropdowns populate with installed apps. Change a default, verify `xdg-mime query default` reflects the change.

- [ ] **Step 3: Commit**

```
git commit -am "feat: default apps page — browser, files, terminal, editor, media"
```

---

### Task 11: About page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings` (AboutPage class)

- [ ] **Step 1: Implement AboutPage.build()**

Read-only info page. Each item is a setting row with label on left, value on right.

```python
def build(self) -> Gtk.Widget:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    page.set_margin_top(32)
    page.set_margin_bottom(32)
    page.set_margin_start(40)
    page.set_margin_end(40)

    page.append(self.win._make_group_label("About"))

    # OS
    os_name = "Adwaita-Lite"
    os_version = ""
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("VERSION_ID="):
                os_version = line.split("=", 1)[1].strip('"')
    except OSError:
        pass
    page.append(self.win._make_info_row("Operating System", f"{os_name} {os_version}".strip()))

    # Hostname
    page.append(self.win._make_info_row("Hostname", socket.gethostname()))

    # CPU
    cpu = "Unknown"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    page.append(self.win._make_info_row("Processor", cpu))

    # RAM
    ram = "Unknown"
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                kb = int(line.split()[1])
                ram = f"{kb / 1048576:.1f} GB"
                break
    except (OSError, ValueError):
        pass
    page.append(self.win._make_info_row("Memory", ram))

    # Disk
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bfree) * st.f_frsize
        page.append(self.win._make_info_row(
            "Disk", f"{used / 1073741824:.1f} GB used of {total / 1073741824:.1f} GB"))
    except OSError:
        pass

    # Desktop
    labwc_ver = "unknown"
    try:
        result = subprocess.run(["labwc", "--version"], capture_output=True, text=True)
        labwc_ver = result.stdout.strip()
    except FileNotFoundError:
        pass
    page.append(self.win._make_info_row("Desktop", f"labwc {labwc_ver}"))

    return page
```

Add `_make_info_row(label, value)` helper to SettingsWindow — same layout as `_make_setting_row` but with a non-interactive `Gtk.Label` as the value.

- [ ] **Step 2: Test**

Run app, switch to About. Verify all info rows display correct system information.

- [ ] **Step 3: Commit**

```
git commit -am "feat: about page — system information"
```

---

### Task 12: Final integration and polish

**Files:**
- All modified files

- [ ] **Step 1: Verify full syntax**

```bash
python3 -m py_compile files/usr/bin/adwaita-lite-settings
python3 -m py_compile files/usr/libexec/adwaita-lite-apply-settings
bash -n files/etc/xdg/labwc/autostart
```

Expected: all pass silently.

- [ ] **Step 2: End-to-end test**

Launch the app. Walk through every page:
1. Appearance: toggle light/dark, change accent, pick wallpaper
2. Display: change scale, verify revert dialog
3. Panel: change edge, density, drag modules, add pinned app
4. Mouse: toggle tap-to-click, adjust speed slider
5. Keyboard: change layout, adjust repeat delay
6. Sound: switch output device, adjust volume
7. Power: change lock timeout
8. Default Apps: change default browser
9. About: verify system info displays

Verify no console errors, no crashes, all settings persist across app restart.

- [ ] **Step 3: Final commit**

```
git commit -am "feat: settings app redesign — complete 9-page sidebar layout"
```
