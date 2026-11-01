# Settings App v2 Phase 2: Display + Accessibility + Sound + Power

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Model guidance:** Use Sonnet for Tasks 1–6 (settings/infra). Use **Opus** for Tasks 7–11 (page implementations with D-Bus and complex UI).
>
> **GTK4 reference:** Use context7 (`/websites/gtk_gtk4`) to verify GTK4 patterns before implementing widget or async code.

**Goal:** Add Accessibility page, expand Display/Sound/Power pages with live D-Bus integration, and modernize the Panel page's pinned apps picker.

**Architecture:** Builds on Phase 1's package structure. Adds PowerProfilesHelper and PulseAudioSubscriber to `dbus_helpers.py`. Updates `apply-settings` to handle new settings (font_size, cursor_size, night light, power profiles). Adds polkit helper for lid close behavior.

**Tech Stack:** Python 3, GTK 4 (PyGObject), power-profiles-daemon D-Bus, PulseAudio (pactl), gammastep, wlr-randr, polkit/pkexec

**Spec:** `docs/superpowers/specs/2026-03-29-settings-app-v2-design.md` (Phase 2 section)

---

## File Structure

### Create

```
files/usr/lib/adwaita-lite/settings/pages/accessibility.py
files/usr/libexec/adwaita-lite-lid-action
files/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy
```

### Modify

```
files/usr/share/adwaita-lite/defaults/settings.json      (add Phase 2 keys)
files/usr/libexec/adwaita-lite-apply-settings             (font_size, cursor_size, high_contrast, reduce_motion, night light, suspend)
files/usr/lib/adwaita-lite/settings/dbus_helpers.py       (add PowerProfilesHelper, PulseAudioSubscriber)
files/usr/lib/adwaita-lite/settings/pages/__init__.py     (register Accessibility)
files/usr/lib/adwaita-lite/settings/pages/display.py      (resolution, night light, wdisplays)
files/usr/lib/adwaita-lite/settings/pages/sound.py        (live updates)
files/usr/lib/adwaita-lite/settings/pages/power_lock.py   (power profiles, suspend, lid close)
files/usr/lib/adwaita-lite/settings/pages/panel.py        (app picker, reorder buttons)
```

---

### Task 1: Add Phase 2 Settings Keys

**Files:**
- Modify: `files/usr/share/adwaita-lite/defaults/settings.json`

- [ ] **Step 1: Add new default keys**

Add these keys to the defaults JSON (after the existing `display_off_timeout` key):

```json
  "font_size": 11,
  "cursor_size": 24,
  "high_contrast": false,
  "reduce_motion": false,
  "night_light_enabled": false,
  "night_light_temp": 4500,
  "night_light_schedule": "sunset-sunrise",
  "night_light_start": "20:00",
  "night_light_end": "06:00",
  "power_profile": "balanced",
  "suspend_timeout": 0,
  "lid_close_action": "suspend"
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/share/adwaita-lite/defaults/settings.json
git commit -m "feat: add Phase 2 settings keys to defaults"
```

---

### Task 2: Update apply-settings for Accessibility Settings

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Read the apply-settings script**

Read the full file to understand current structure. Key sections to modify:
- `_build_tokens()` (around line 151): Replace hardcoded `font_size_ui: 13` and `font_size_mono: 11`
- `write_gtk_settings()` (around line 564): Replace hardcoded `Roboto 11` and `cursor-size=24`
- `ensure_settings()` (around line 217): Add validation for new keys

- [ ] **Step 2: Update `_build_tokens()` to use settings-driven font and cursor sizes**

Find this block in `_build_tokens()`:
```python
        # Typography
        "font_ui": "Roboto",
        "font_mono": "Roboto Mono",
        "font_size_ui": 13,
        "font_size_mono": 11,
```

Replace with:
```python
        # Typography
        "font_ui": "Roboto",
        "font_mono": "Roboto Mono",
        "font_size_ui": settings.get("font_size", 11) + 2,
        "font_size_mono": settings.get("font_size", 11),
        # Accessibility
        "cursor_size": settings.get("cursor_size", 24),
        "reduce_motion": settings.get("reduce_motion", False),
```

Note: `font_size_ui` is 2pt larger than the base font_size because waybar/fuzzel use a larger render size than GTK. The `font_size` setting stores the GTK font point size (10, 11, 13, 15).

- [ ] **Step 3: Update `write_gtk_settings()` to use token-driven values**

Find and replace the hardcoded values in `write_gtk_settings()`:

Replace:
```python
            handle.write("gtk-font-name=Roboto 11\n")
            handle.write("gtk-cursor-theme-name=Adwaita\n")
            handle.write("gtk-cursor-theme-size=24\n")
```
With:
```python
            handle.write(f"gtk-font-name=Roboto {tokens['font_size_mono']}\n")
            handle.write("gtk-cursor-theme-name=Adwaita\n")
            handle.write(f"gtk-cursor-theme-size={tokens['cursor_size']}\n")
            handle.write(f"gtk-enable-animations={'1' if not tokens['reduce_motion'] else '0'}\n")
```

Also replace the gsettings commands for font and cursor:

Replace:
```python
        ["gsettings", "set", "org.gnome.desktop.interface", "font-name", "Roboto 11"],
        ["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", "Adwaita"],
        ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", "24"],
```
With:
```python
        ["gsettings", "set", "org.gnome.desktop.interface", "font-name", f"Roboto {tokens['font_size_mono']}"],
        ["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", "Adwaita"],
        ["gsettings", "set", "org.gnome.desktop.interface", "cursor-size", str(tokens["cursor_size"])],
```

- [ ] **Step 4: Update `write_foot_config()` to use token-driven font size**

Find the hardcoded font size in the foot config writer (search for `font=Roboto Mono`). Replace with token-driven value:
```python
font=Roboto Mono:size={tokens['font_size_mono']}
```

- [ ] **Step 5: Update `write_fuzzel_config()` to use token-driven font size**

Find the hardcoded font size in the fuzzel config writer (search for `font=Roboto`). Replace with token-driven value:
```python
font=Roboto:size={tokens['font_size_mono']}
```

- [ ] **Step 6: Add validation for new keys in `ensure_settings()`**

At the end of `ensure_settings()`, before the `data.update(...)` call, add validation:

```python
    # Validate accessibility settings
    font_size = data.get("font_size", 11)
    if font_size not in (10, 11, 13, 14, 15):
        font_size = 11
    cursor_size = data.get("cursor_size", 24)
    if cursor_size not in (24, 32, 48):
        cursor_size = 24
    high_contrast = bool(data.get("high_contrast", False))
    reduce_motion = bool(data.get("reduce_motion", False))

    # Apply high contrast: force dark theme + stronger borders
    if high_contrast:
        theme = "dark"
```

Add these to the `data.update(...)` dict:
```python
        "font_size": font_size,
        "cursor_size": cursor_size,
        "high_contrast": high_contrast,
        "reduce_motion": reduce_motion,
```

- [ ] **Step 7: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: apply-settings handles font_size, cursor_size, reduce_motion, high_contrast"
```

---

### Task 3: Update apply-settings for Night Light and Suspend

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add night light validation to `ensure_settings()`**

Add after the accessibility validation (before `data.update`):

```python
    # Validate night light settings
    night_light_enabled = bool(data.get("night_light_enabled", False))
    night_light_temp = int(data.get("night_light_temp", 4500))
    if not (3500 <= night_light_temp <= 6500):
        night_light_temp = 4500
    night_light_schedule = data.get("night_light_schedule", "sunset-sunrise")
    if night_light_schedule not in ("sunset-sunrise", "custom"):
        night_light_schedule = "sunset-sunrise"
    night_light_start = str(data.get("night_light_start", "20:00"))
    night_light_end = str(data.get("night_light_end", "06:00"))

    # Validate power settings
    suspend_timeout = int(data.get("suspend_timeout", 0))
    if suspend_timeout not in (0, 60, 120, 300, 600, 900, 1800):
        suspend_timeout = 0
    lid_close_action = data.get("lid_close_action", "suspend")
    if lid_close_action not in ("suspend", "lock", "nothing"):
        lid_close_action = "suspend"
    power_profile = data.get("power_profile", "balanced")
    if power_profile not in ("balanced", "power-saver", "performance"):
        power_profile = "balanced"
```

Add all to `data.update(...)`.

- [ ] **Step 2: Add gammastep management to `main()`**

In the `main()` function, after the `if os.environ.get("WAYLAND_DISPLAY"):` block, within that block, add gammastep management before the swayidle restart:

```python
        # Manage gammastep (night light)
        if settings.get("night_light_enabled", False):
            temp = str(settings.get("night_light_temp", 4500))
            schedule = settings.get("night_light_schedule", "sunset-sunrise")
            gs_cmd = ["gammastep", "-O", temp]
            if schedule == "sunset-sunrise":
                gs_cmd = ["gammastep", "-t", f"{temp}:{temp}"]
            else:
                start = settings.get("night_light_start", "20:00")
                end = settings.get("night_light_end", "06:00")
                gs_cmd = ["gammastep", "-t", f"6500:{temp}", "-l", "0:0",
                          "-m", "wayland"]
            restart_program("gammastep", gs_cmd)
        else:
            subprocess.run(["pkill", "-x", "gammastep"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```

- [ ] **Step 3: Add suspend timeout to swayidle command**

Find the swayidle restart block in `main()`. Add suspend_timeout handling. Replace the existing swayidle block:

```python
        # Restart swayidle with updated timeouts
        lock_t = int(settings.get("lock_timeout", 300))
        dpms_t = int(settings.get("display_off_timeout", 600))
        suspend_t = int(settings.get("suspend_timeout", 0))
        idle_cmd = ["swayidle", "-w"]
        if lock_t > 0:
            idle_cmd += ["timeout", str(lock_t), "swaylock -f"]
        if dpms_t > 0:
            idle_cmd += ["timeout", str(dpms_t), 'wlopm --off "*"',
                         "resume", 'wlopm --on "*"']
        if suspend_t > 0:
            idle_cmd += ["timeout", str(suspend_t), "systemctl suspend"]
        idle_cmd += ["before-sleep", "swaylock -f"]
        restart_program("swayidle", idle_cmd)
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: apply-settings handles night light (gammastep) and suspend timeout"
```

---

### Task 4: Add PowerProfilesHelper and PulseAudioSubscriber to dbus_helpers.py

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`

- [ ] **Step 1: Read the current dbus_helpers.py**

Read `files/usr/lib/adwaita-lite/settings/dbus_helpers.py` to understand the existing structure.

- [ ] **Step 2: Add PowerProfilesHelper class**

Add after the `BlueZHelper` class at the bottom of the file:

```python
# ---------------------------------------------------------------------------
#  power-profiles-daemon helper
# ---------------------------------------------------------------------------

class PowerProfilesHelper:
    """Wraps net.hadess.PowerProfiles D-Bus. Publishes event: power-profile-changed."""

    BUS_NAME = "net.hadess.PowerProfiles"
    OBJECT_PATH = "/net/hadess/PowerProfiles"
    IFACE = "net.hadess.PowerProfiles"

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error:
            return
        self._bus.signal_subscribe(
            self.BUS_NAME, "org.freedesktop.DBus.Properties",
            "PropertiesChanged", self.OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, self._on_props_changed, None,
        )

    @property
    def available(self) -> bool:
        return self._bus is not None

    def get_active_profile(self) -> str:
        if self._bus is None:
            return "balanced"
        try:
            result = self._bus.call_sync(
                self.BUS_NAME, self.OBJECT_PATH,
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (self.IFACE, "ActiveProfile")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            return result.unpack()[0]
        except GLib.Error:
            return "balanced"

    def set_active_profile(self, profile: str) -> None:
        if self._bus is None:
            return
        try:
            self._bus.call_sync(
                self.BUS_NAME, self.OBJECT_PATH,
                "org.freedesktop.DBus.Properties", "Set",
                GLib.Variant("(ssv)", (self.IFACE, "ActiveProfile", GLib.Variant("s", profile))),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass

    def _on_props_changed(self, _conn, _sender, _path, _iface, _signal, params, _data) -> None:
        changed = params.unpack()[1]
        if "ActiveProfile" in changed:
            self._event_bus.publish("power-profile-changed", changed["ActiveProfile"])


# ---------------------------------------------------------------------------
#  PulseAudio event subscriber
# ---------------------------------------------------------------------------

class PulseAudioSubscriber:
    """Runs `pactl subscribe` in background thread, publishes audio-changed events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._proc: subprocess.Popen | None = None
        self._start()

    def _start(self) -> None:
        import shutil
        import threading

        if shutil.which("pactl") is None:
            return
        try:
            self._proc = subprocess.Popen(
                ["pactl", "subscribe"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except FileNotFoundError:
            return

        def _reader():
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                if any(kw in line for kw in ("sink", "source", "server")):
                    self._event_bus.publish("audio-changed")

        threading.Thread(target=_reader, daemon=True).start()

    def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
```

Also add `import subprocess` to the top-level imports if not already present.

- [ ] **Step 3: Verify import**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.dbus_helpers import PowerProfilesHelper, PulseAudioSubscriber
print('New helpers imported OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/dbus_helpers.py
git commit -m "feat: add PowerProfilesHelper and PulseAudioSubscriber to D-Bus helpers"
```

---

### Task 5: Create Lid-Action Helper and Polkit Policy

**Files:**
- Create: `files/usr/libexec/adwaita-lite-lid-action`
- Create: `files/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy`

- [ ] **Step 1: Create the helper script**

Create `files/usr/libexec/adwaita-lite-lid-action`:

```bash
#!/bin/bash
# Sets lid close action via logind.conf.d override.
# Must be run via pkexec for root access.
set -euo pipefail

ACTION="${1:-suspend}"

case "$ACTION" in
    suspend|lock|nothing)
        case "$ACTION" in
            suspend) LOGIND_ACTION="suspend" ;;
            lock)    LOGIND_ACTION="lock" ;;
            nothing) LOGIND_ACTION="ignore" ;;
        esac
        ;;
    *)
        echo "Usage: $0 {suspend|lock|nothing}" >&2
        exit 1
        ;;
esac

mkdir -p /etc/systemd/logind.conf.d
cat > /etc/systemd/logind.conf.d/lid-action.conf <<EOF
[Login]
HandleLidSwitch=$LOGIND_ACTION
HandleLidSwitchExternalPower=$LOGIND_ACTION
HandleLidSwitchDocked=ignore
EOF

systemctl kill -s HUP systemd-logind
```

Make it executable:
```bash
chmod +x files/usr/libexec/adwaita-lite-lid-action
```

- [ ] **Step 2: Create the polkit policy**

Create `files/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE policyconfig PUBLIC
 "-//freedesktop//DTD PolicyKit Policy Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/PolicyKit/1/policyconfig.dtd">
<policyconfig>
  <action id="org.adwaitabluelite.lid-action">
    <description>Set lid close behavior</description>
    <message>Authentication is required to change the lid close behavior</message>
    <defaults>
      <allow_any>auth_admin</allow_any>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_active>yes</allow_active>
    </defaults>
    <annotate key="org.freedesktop.policykit.exec.path">/usr/libexec/adwaita-lite-lid-action</annotate>
    <annotate key="org.freedesktop.policykit.exec.allow_gui">true</annotate>
  </action>
</policyconfig>
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/libexec/adwaita-lite-lid-action files/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy
git commit -m "feat: lid-action helper script with polkit policy for logind override"
```

---

### Task 6: Create Accessibility Page and Register It

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/accessibility.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/__init__.py`

- [ ] **Step 1: Create accessibility.py**

Create `files/usr/lib/adwaita-lite/settings/pages/accessibility.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage

CURSOR_SIZES = [
    ("24", "Default (24px)"),
    ("32", "Large (32px)"),
    ("48", "Larger (48px)"),
]


class AccessibilityPage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Accessibility", "Large text"),
            ("Accessibility", "Cursor size"),
            ("Accessibility", "High contrast"),
            ("Accessibility", "Reduce motion"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Accessibility"))

        # Large text toggle
        large_text = Gtk.Switch()
        large_text.set_active(self.store.get("font_size", 11) >= 14)

        def _on_large_text(_, state):
            self.store.save_and_apply("font_size", 14 if state else 11)
            return False

        large_text.connect("state-set", _on_large_text)
        page.append(self.make_setting_row(
            "Large text", "Increases font size for better readability", large_text))

        # Cursor size
        labels = [label for _, label in CURSOR_SIZES]
        values = [val for val, _ in CURSOR_SIZES]
        cursor_dd = Gtk.DropDown.new_from_strings(labels)
        current = str(self.store.get("cursor_size", 24))
        try:
            cursor_dd.set_selected(values.index(current))
        except ValueError:
            cursor_dd.set_selected(0)
        cursor_dd.connect("notify::selected", lambda d, _:
            self.store.save_and_apply("cursor_size", int(values[d.get_selected()])))
        page.append(self.make_setting_row("Cursor size", "", cursor_dd))

        # High contrast
        contrast = Gtk.Switch()
        contrast.set_active(self.store.get("high_contrast", False))

        def _on_contrast(_, state):
            self.store.save_and_apply("high_contrast", state)
            return False

        contrast.connect("state-set", _on_contrast)
        page.append(self.make_setting_row(
            "High contrast", "Forces dark theme with stronger borders", contrast))

        # Reduce motion
        motion = Gtk.Switch()
        motion.set_active(self.store.get("reduce_motion", False))

        def _on_motion(_, state):
            self.store.save_and_apply("reduce_motion", state)
            return False

        motion.connect("state-set", _on_motion)
        page.append(self.make_setting_row(
            "Reduce motion", "Disables animations throughout the interface", motion))

        return page
```

- [ ] **Step 2: Register the page in `__init__.py`**

Read `files/usr/lib/adwaita-lite/settings/pages/__init__.py`. Add the import and entry:

Add to imports:
```python
from .accessibility import AccessibilityPage
```

Add to `ALL_PAGES` list, after the Power & Lock entry and before Default Apps:
```python
    ("preferences-desktop-accessibility-symbolic", "Accessibility", AccessibilityPage),
```

- [ ] **Step 3: Verify import**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.pages import ALL_PAGES
print(f'{len(ALL_PAGES)} pages registered')
for _, label, _ in ALL_PAGES:
    print(f'  {label}')
"
```

Expected: 12 pages, including "Accessibility".

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/accessibility.py files/usr/lib/adwaita-lite/settings/pages/__init__.py
git commit -m "feat: create Accessibility page with large text, cursor size, contrast, motion"
```

---

### Task 7: Expand Display Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/display.py`

- [ ] **Step 1: Read current display.py**

Read the full `files/usr/lib/adwaita-lite/settings/pages/display.py`.

- [ ] **Step 2: Rewrite with resolution, night light, and advanced button**

Replace the entire file with a version that adds:
1. **Existing scale controls** (keep as-is)
2. **Resolution & refresh rate section** — query `wlr-randr` for available modes per output, show dropdown, apply with 15s revert dialog
3. **Night light section** — toggle, temperature slider (3500-6500), schedule dropdown (Sunset to Sunrise / Custom), start/end time entries for custom schedule
4. **Advanced button** — opens `wdisplays`

The full implementation should:

- Parse `wlr-randr` output to get display name, current mode, and available modes
- Show a dropdown per display with `WxH@RHz` format options
- Use the existing `_show_revert_dialog` pattern for resolution changes
- Night light toggle calls `self.store.save_and_apply("night_light_enabled", state)`
- Temperature slider uses `self.store.save_debounced("night_light_temp", value)`
- Schedule dropdown saves `night_light_schedule`
- Custom time entries save `night_light_start` / `night_light_end`
- Advanced button: `subprocess.Popen(["wdisplays"])`

Write the complete replacement file. Key structure:

```python
import re
import subprocess
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk
from ..base import BasePage

SCALE_OPTIONS = [...]
SCALE_VALUES = [...]

class DisplayPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._scale_buttons = []
        self._revert_timer_id = None
        self._revert_seconds = 15

    @property
    def search_keywords(self):
        return [
            ("Display Scale", "Scale"),
            ("Resolution", "Resolution"),
            ("Resolution", "Refresh rate"),
            ("Night Light", "Night light"),
            ("Night Light", "Color temperature"),
        ]

    def build(self):
        page = self.make_page_box()
        # -- Scale section (existing) --
        # -- Resolution section (new) --
        # -- Night Light section (new) --
        # -- Advanced button (new) --
        return page
```

For parsing `wlr-randr` output, use this pattern:
```python
def _get_displays(self):
    """Parse wlr-randr output. Returns list of (name, current_mode, available_modes)."""
    try:
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True)
    except FileNotFoundError:
        return []
    displays = []
    current_name = None
    current_mode = None
    modes = []
    for line in result.stdout.splitlines():
        if line and not line[0].isspace():
            if current_name:
                displays.append((current_name, current_mode, modes))
            current_name = line.split()[0]
            current_mode = None
            modes = []
        elif "current" in line.lower():
            m = re.search(r"(\d+x\d+)\s+px,\s+([\d.]+)\s+Hz", line)
            if m:
                current_mode = f"{m.group(1)}@{m.group(2)}Hz"
        m = re.search(r"(\d+x\d+)\s+px,\s+([\d.]+)\s+Hz", line)
        if m and current_name:
            mode_str = f"{m.group(1)}@{m.group(2)}Hz"
            if mode_str not in modes:
                modes.append(mode_str)
    if current_name:
        displays.append((current_name, current_mode, modes))
    return displays
```

For applying resolution:
```python
def _set_resolution(self, output_name, mode_str):
    # mode_str format: "1920x1080@60.0Hz"
    parts = mode_str.replace("Hz", "").split("@")
    res = parts[0]
    rate = parts[1] if len(parts) > 1 else ""
    cmd = ["wlr-randr", "--output", output_name, "--mode", res]
    if rate:
        cmd += ["--custom-mode", f"{res}@{rate}Hz"]
    subprocess.run(cmd, check=False)
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/display.py
git commit -m "feat: expand Display page with resolution, night light, and wdisplays"
```

---

### Task 8: Rewrite Sound Page with Live Updates

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/sound.py`

- [ ] **Step 1: Read current sound.py**

Read the full `files/usr/lib/adwaita-lite/settings/pages/sound.py`.

- [ ] **Step 2: Rewrite with live D-Bus updates**

Replace the entire file. The new version:
1. Starts a `PulseAudioSubscriber` in `build()`
2. Subscribes to `"audio-changed"` events
3. On event, refreshes device dropdowns and volume sliders
4. Stores widget references for live updates
5. All existing functionality preserved (output/input device, volume, mute)

Key changes from the current implementation:
- Store references to all widgets (`self._sink_dd`, `self._out_vol`, `self._out_mute`, etc.)
- `_refresh()` method re-reads current state from `pactl` and updates widgets without triggering callbacks
- Use a `self._updating` guard flag to prevent feedback loops when programmatically updating widgets
- Subscribe: `self.event_bus.subscribe("audio-changed", lambda _: self._refresh())`
- Start subscriber: `from ..dbus_helpers import PulseAudioSubscriber; self._pa = PulseAudioSubscriber(self.event_bus)`
- Add `page.connect("unmap", lambda _: self._pa.stop())` for cleanup

The complete rewritten file structure:

```python
import json
import re
import subprocess
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk
from ..base import BasePage

class SoundPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._pa = None
        self._updating = False
        self._sink_dd = None
        self._out_vol = None
        self._out_mute = None
        self._source_dd = None
        self._in_vol = None
        self._in_mute = None
        self._sink_names = []
        self._source_names = []

    @property
    def search_keywords(self):
        return [
            ("Output", "Output device"), ("Output", "Volume"), ("Output", "Mute"),
            ("Input", "Input device"), ("Input", "Microphone"),
        ]

    def build(self):
        from ..dbus_helpers import PulseAudioSubscriber
        self._pa = PulseAudioSubscriber(self.event_bus)

        page = self.make_page_box()
        # Build output section with stored widget refs
        # Build input section with stored widget refs
        # Subscribe to audio-changed
        self.event_bus.subscribe("audio-changed", lambda _: self._refresh())
        page.connect("unmap", lambda _: self._cleanup())
        # Initial populate
        self._refresh()
        return page

    def _refresh(self):
        if self._updating:
            return
        self._updating = True
        try:
            # Re-read sinks, sources, volumes, mutes from pactl
            # Update widgets without triggering callbacks
            pass
        finally:
            self._updating = False

    def _cleanup(self):
        if self._pa:
            self._pa.stop()
```

Write the complete implementation with all the pactl query methods moved from the current file, plus the refresh logic.

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/sound.py
git commit -m "feat: rewrite Sound page with live PulseAudio event subscriptions"
```

---

### Task 9: Expand Power & Lock Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`

- [ ] **Step 1: Read current power_lock.py**

Read the full `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`.

- [ ] **Step 2: Expand with power profiles, suspend, and lid close**

Add three new sections after the existing Lock & Display section:

1. **Power Profile section** — Toggle cards for Balanced/Power Saver/Performance via `PowerProfilesHelper`
2. **Suspend on idle section** — Dropdown with same timeout options as lock/display
3. **Lid close behavior section** — Dropdown (Suspend/Lock/Do Nothing), applies via `pkexec /usr/libexec/adwaita-lite-lid-action`

The page needs to:
- Import and create `PowerProfilesHelper` in `build()`
- Subscribe to `"power-profile-changed"` events for live updates
- Use `pkexec` for the lid close action (runs the helper script)

Key additions:

```python
from ..dbus_helpers import PowerProfilesHelper

# In build():
self._pph = PowerProfilesHelper(self.event_bus)

# Power Profile section
page.append(self.make_group_label("Power Profile"))
profile_cards = self.make_toggle_cards(
    [("balanced", "Balanced"), ("power-saver", "Power Saver"), ("performance", "Performance")],
    self._pph.get_active_profile(),
    lambda v: self._pph.set_active_profile(v),
)
page.append(profile_cards)
# Store card buttons for live update
self.event_bus.subscribe("power-profile-changed", self._on_profile_changed)

# Suspend on idle section
page.append(self.make_group_label("Suspend"))
suspend_dd = Gtk.DropDown.new_from_strings(labels)
current_suspend = self.store.get("suspend_timeout", 0)
# ... same pattern as lock_timeout

# Lid close section
page.append(self.make_group_label("Lid"))
lid_options = ["Suspend", "Lock", "Do Nothing"]
lid_values = ["suspend", "lock", "nothing"]
lid_dd = Gtk.DropDown.new_from_strings(lid_options)
current_lid = self.store.get("lid_close_action", "suspend")
lid_dd.connect("notify::selected", lambda d, _: self._set_lid_action(lid_values[d.get_selected()]))

def _set_lid_action(self, action):
    self.store.save_and_apply("lid_close_action", action)
    subprocess.Popen(
        ["pkexec", "/usr/libexec/adwaita-lite-lid-action", action],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
```

Write the complete replacement file.

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/power_lock.py
git commit -m "feat: expand Power page with profiles, suspend on idle, lid close"
```

---

### Task 10: Panel Improvements — App Picker and Reorder Buttons

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py`

- [ ] **Step 1: Read current panel.py**

Read the full `files/usr/lib/adwaita-lite/settings/pages/panel.py`.

- [ ] **Step 2: Replace pinned apps text entry with app picker**

Replace `_show_add_pinned_dialog()` with a new implementation that:
1. Opens a scrollable list of all installed apps (from `Gio.AppInfo.get_all()`)
2. Filters out `NoDisplay` apps
3. Shows icon + app name per row
4. Click to add — automatically extracts name, exec command, and icon from the `.desktop` entry

```python
def _show_add_pinned_dialog(self):
    dialog = Gtk.Window(title="Add Pinned App", modal=True)
    dialog.set_transient_for(self._pinned_list.get_root())
    dialog.set_default_size(400, 500)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_margin_top(16)
    outer.set_margin_bottom(16)
    outer.set_margin_start(16)
    outer.set_margin_end(16)

    # Search filter
    search = Gtk.SearchEntry()
    search.set_placeholder_text("Search apps...")
    outer.append(search)

    scroll = Gtk.ScrolledWindow()
    scroll.set_vexpand(True)
    listbox = Gtk.ListBox()
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)
    scroll.set_child(listbox)
    outer.append(scroll)

    apps = []
    for app in Gio.AppInfo.get_all():
        if app.should_show():
            apps.append(app)
    apps.sort(key=lambda a: a.get_display_name().lower())

    for app in apps:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(8)
        box.set_margin_end(8)

        icon_info = app.get_icon()
        icon = Gtk.Image.new_from_gicon(icon_info) if icon_info else Gtk.Image.new_from_icon_name("application-x-executable-symbolic")
        icon.set_pixel_size(24)
        box.append(icon)

        name = Gtk.Label(label=app.get_display_name(), xalign=0)
        name.set_hexpand(True)
        box.append(name)

        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", lambda _, a=app: self._add_app_from_info(a, dialog))
        box.append(add_btn)

        row.set_child(box)
        listbox.append(row)

    # Search filter
    def _filter(row):
        text = search.get_text().lower()
        if not text:
            return True
        child_box = row.get_child()
        label = child_box.get_first_child().get_next_sibling()
        return text in label.get_label().lower()

    search.connect("search-changed", lambda _: listbox.set_filter_func(_filter))

    cancel = Gtk.Button(label="Cancel")
    cancel.connect("clicked", lambda _: dialog.destroy())
    cancel.set_halign(Gtk.Align.END)
    outer.append(cancel)

    dialog.set_child(outer)
    dialog.present()

def _add_app_from_info(self, app_info, dialog):
    name = app_info.get_display_name()
    cmd = app_info.get_commandline() or ""
    icon_gicon = app_info.get_icon()
    icon = icon_gicon.to_string() if icon_gicon else "application-x-executable-symbolic"
    self._pinned_data.append({"name": name, "command": cmd, "icon": icon})
    self._refresh_pinned_list()
    self.store.save_and_apply("pinned", self._pinned_data)
    dialog.destroy()
```

- [ ] **Step 3: Add context-dependent reorder buttons to module layout**

In `_build_module_row()`, change the move buttons to be context-dependent based on panel orientation:

```python
def _build_module_row(self, mod_key, section):
    row = Gtk.ListBoxRow()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    box.set_margin_top(4)
    box.set_margin_bottom(4)
    box.set_margin_start(4)
    box.set_margin_end(4)
    label = Gtk.Label(label=MODULE_NAMES.get(mod_key, mod_key), xalign=0)
    label.set_hexpand(True)
    box.append(label)

    edge = self.store.get("edge", "bottom")
    is_horizontal = edge in ("top", "bottom")
    sec_idx = SECTION_ORDER.index(section)
    modules = self._layout_data.get(section, [])
    mod_idx = modules.index(mod_key) if mod_key in modules else -1

    # Section-move buttons (between sections)
    section_prev = "\u25C2" if is_horizontal else "\u25B2"  # ◂ or ▲
    section_next = "\u25B8" if is_horizontal else "\u25BC"  # ▸ or ▼

    if sec_idx > 0:
        btn = Gtk.Button(label=section_prev)
        btn.set_tooltip_text(f"Move to {SECTION_ORDER[sec_idx - 1]}")
        btn.connect("clicked", lambda _, k=mod_key, s=section: self._move_module(
            k, s, SECTION_ORDER[SECTION_ORDER.index(s) - 1]))
        box.append(btn)

    if sec_idx < len(SECTION_ORDER) - 1:
        btn = Gtk.Button(label=section_next)
        btn.set_tooltip_text(f"Move to {SECTION_ORDER[sec_idx + 1]}")
        btn.connect("clicked", lambda _, k=mod_key, s=section: self._move_module(
            k, s, SECTION_ORDER[SECTION_ORDER.index(s) + 1]))
        box.append(btn)

    # Reorder buttons (within section)
    reorder_up = "\u25B2" if is_horizontal else "\u25C2"    # ▲ or ◂
    reorder_down = "\u25BC" if is_horizontal else "\u25B8"  # ▼ or ▸

    if mod_idx > 0:
        btn = Gtk.Button(label=reorder_up)
        btn.set_tooltip_text("Move up")
        btn.connect("clicked", lambda _, k=mod_key, s=section: self._reorder_module(k, s, -1))
        box.append(btn)

    if mod_idx < len(modules) - 1:
        btn = Gtk.Button(label=reorder_down)
        btn.set_tooltip_text("Move down")
        btn.connect("clicked", lambda _, k=mod_key, s=section: self._reorder_module(k, s, 1))
        box.append(btn)

    row.set_child(box)
    return row
```

Add the `_reorder_module` method:

```python
def _reorder_module(self, mod_key, section, direction):
    modules = self._layout_data.get(section, [])
    if mod_key not in modules:
        return
    idx = modules.index(mod_key)
    new_idx = idx + direction
    if 0 <= new_idx < len(modules):
        modules[idx], modules[new_idx] = modules[new_idx], modules[idx]
        self._refresh_module_lists()
        self.store.save_and_apply("layout", self._layout_data)
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/panel.py
git commit -m "feat: panel app picker replaces text entry, context-dependent reorder buttons"
```

---

### Task 11: Integration Verification

- [ ] **Step 1: Run all tests**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify full import chain**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.pages import ALL_PAGES
print(f'{len(ALL_PAGES)} pages registered:')
for _, label, cls in ALL_PAGES:
    print(f'  {label}')
"
```

Expected: 12 pages including Accessibility.

- [ ] **Step 3: Verify new settings keys in defaults**

```bash
cd /var/home/race/ublue-mike && python -c "
import json
data = json.load(open('files/usr/share/adwaita-lite/defaults/settings.json'))
for key in ['font_size', 'cursor_size', 'high_contrast', 'reduce_motion',
            'night_light_enabled', 'night_light_temp', 'power_profile',
            'suspend_timeout', 'lid_close_action']:
    print(f'  {key}: {data[key]}')
"
```

- [ ] **Step 4: Verify apply-settings syntax**

```bash
python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
exec(open('files/usr/libexec/adwaita-lite-apply-settings').read().split('def main')[0])
print('apply-settings parses OK')
"
```

- [ ] **Step 5: Verify new system files exist**

```bash
ls -la files/usr/libexec/adwaita-lite-lid-action
ls -la files/usr/share/polkit-1/actions/org.adwaitabluelite.lid-action.policy
```

- [ ] **Step 6: Commit any fixes**

```bash
git add -A && git status
# If changes: git commit -m "fix: integration fixes for settings v2 phase 2"
```
