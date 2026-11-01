# Settings App v2 Phase 3: Keyboard + System Pages + Polish

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Model guidance:** Use Sonnet for Tasks 1–2, 6–9. Use **Opus** for Tasks 3–5 (keyboard shortcuts editor, Date/Time, Users — complex D-Bus/XML/key capture).
>
> **GTK4 reference:** Use context7 (`/websites/gtk_gtk4`) to verify Gtk.EventControllerKey and other GTK4 patterns.

**Goal:** Complete all remaining settings pages — keyboard shortcuts editor, Date & Time, Users, Language & Region — plus fix Default Apps, expand About, and add font size to Appearance. After this phase, every setting in the spec is implemented.

**Architecture:** Builds on Phase 1+2 package. Keyboard shortcuts parsed from labwc `rc.xml` via `xml.etree.ElementTree`. Users page uses AccountsService D-Bus. Language page uses `localectl`. New settings keys: `clock_24h`, `capslock_behavior`.

**Tech Stack:** Python 3, GTK 4, xml.etree.ElementTree, Gtk.EventControllerKey, AccountsService D-Bus, timedatectl, localectl, bootc

**Spec:** `docs/superpowers/specs/2026-03-29-settings-app-v2-design.md` (Phase 3 section)

---

## File Structure

### Create

```
files/usr/lib/adwaita-lite/settings/pages/datetime.py
files/usr/lib/adwaita-lite/settings/pages/users.py
files/usr/lib/adwaita-lite/settings/pages/language.py
```

### Modify

```
files/usr/share/adwaita-lite/defaults/settings.json        (add clock_24h, capslock_behavior)
files/usr/libexec/adwaita-lite-apply-settings               (clock_24h waybar format, capslock xkb options)
files/usr/lib/adwaita-lite/settings/pages/keyboard.py       (shortcuts editor, caps lock dropdown)
files/usr/lib/adwaita-lite/settings/pages/appearance.py     (font size dropdown)
files/usr/lib/adwaita-lite/settings/pages/default_apps.py   (fix terminal, add categories)
files/usr/lib/adwaita-lite/settings/pages/about.py          (GPU info, bootc updates)
files/usr/lib/adwaita-lite/settings/pages/__init__.py       (register 3 new pages)
```

---

### Task 1: Add Phase 3 Settings Keys + apply-settings Updates

**Files:**
- Modify: `files/usr/share/adwaita-lite/defaults/settings.json`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add new keys to settings.json defaults**

Add after the existing Phase 2 keys:

```json
  "clock_24h": false,
  "capslock_behavior": "default"
```

- [ ] **Step 2: Read apply-settings and add clock_24h to waybar config**

Read `files/usr/libexec/adwaita-lite-apply-settings`. Find the waybar config writer where the clock module format is defined. Search for `"clock"` in the waybar config section. Change the clock format to be conditional on `clock_24h`:

In the waybar config dict where `"clock"` is defined, change the format to:
```python
"format": "{:%H:%M}" if tokens.get("clock_24h", False) else "{:%I:%M %p}",
```

- [ ] **Step 3: Add capslock_behavior to labwc rc.xml overrides**

In `write_labwc_rc_overrides()`, find where xkb options are written. Add capslock behavior mapping:

```python
capslock = settings.get("capslock_behavior", "default")
xkb_options_parts = []
if capslock == "ctrl":
    xkb_options_parts.append("caps:ctrl_modifier")
elif capslock == "escape":
    xkb_options_parts.append("caps:escape")
elif capslock == "disabled":
    xkb_options_parts.append("caps:none")
xkb_options = ",".join(xkb_options_parts) if xkb_options_parts else ""
```

Write the xkb options into the `<xkb>` element if not empty:
```xml
<xkbOptions>{xkb_options}</xkbOptions>
```

- [ ] **Step 4: Add validation in ensure_settings()**

```python
    clock_24h = bool(data.get("clock_24h", False))
    capslock_behavior = data.get("capslock_behavior", "default")
    if capslock_behavior not in ("default", "ctrl", "escape", "disabled"):
        capslock_behavior = "default"
```

Add `"clock_24h"` and `"capslock_behavior"` to `_build_tokens()` return dict and `data.update()`.

- [ ] **Step 5: Commit**

```bash
git add files/usr/share/adwaita-lite/defaults/settings.json files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: add clock_24h and capslock_behavior settings with apply-settings support"
```

---

### Task 2: Appearance Page — Font Size Dropdown

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/appearance.py`

- [ ] **Step 1: Read the current appearance.py**

- [ ] **Step 2: Add font size dropdown**

After the Accent color group (before the Wallpaper group), add a Font size section:

```python
# -- Font size group --
page.append(self.make_group_label("Font size"))
font_sizes = [("10", "Small"), ("11", "Default"), ("13", "Large"), ("15", "Larger")]
font_labels = [label for _, label in font_sizes]
font_values = [val for val, _ in font_sizes]
font_dd = Gtk.DropDown.new_from_strings(font_labels)
current_font = str(self.store.get("font_size", 11))
try:
    font_dd.set_selected(font_values.index(current_font))
except ValueError:
    font_dd.set_selected(1)
font_dd.connect("notify::selected", lambda d, _:
    self.store.save_and_apply("font_size", int(font_values[d.get_selected()])))
page.append(self.make_setting_row("Font size", "Affects all text throughout the interface", font_dd))
```

Update `search_keywords` to include `("Font size", "Font")`.

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/appearance.py
git commit -m "feat: add font size dropdown to Appearance page"
```

---

### Task 3: Keyboard Page — Shortcuts Editor + Caps Lock

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`

This is the most complex feature. The implementing agent should read:
- `files/etc/xdg/labwc/rc.xml` — system default keybindings (XML structure)
- `files/usr/lib/adwaita-lite/settings/pages/keyboard.py` — current page

- [ ] **Step 1: Read both files**

- [ ] **Step 2: Add Caps Lock behavior dropdown**

After the Repeat section, add:

```python
# -- Caps Lock group --
page.append(self.make_group_label("Caps Lock Behavior"))
caps_options = ["Default", "Ctrl", "Escape", "Disabled"]
caps_values = ["default", "ctrl", "escape", "disabled"]
caps_dd = Gtk.DropDown.new_from_strings(caps_options)
current_caps = self.store.get("capslock_behavior", "default")
try:
    caps_dd.set_selected(caps_values.index(current_caps))
except ValueError:
    caps_dd.set_selected(0)
caps_dd.connect("notify::selected", lambda d, _:
    self.store.save_and_apply("capslock_behavior", caps_values[d.get_selected()]))
page.append(self.make_setting_row("Caps Lock key", "Remap Caps Lock to another function", caps_dd))
```

- [ ] **Step 3: Add the shortcuts editor section**

After Caps Lock, add a full Keyboard Shortcuts section. Implementation requirements:

**Parsing:** Use `xml.etree.ElementTree` to parse `/etc/xdg/labwc/rc.xml`. Extract all `<keybind>` elements from `<keyboard>`. For each, read the `key` attribute and the child `<action>` element's `name`, `command`, and `menu` attributes.

**Human-readable action names:** Map action+command combos to friendly descriptions:
```python
SHORTCUT_NAMES = {
    ("Execute", "foot"): "Open Terminal",
    ("Execute", "Thunar"): "Open File Manager",
    ("Execute", "fuzzel"): "App Launcher",
    ("Execute", "adwaita-lite-settings"): "Open Settings",
    ("Execute", "swaylock -f"): "Lock Screen",
    ("Execute", "foot -e htop"): "System Monitor",
    ("NextWindow", ""): "Switch Windows",
    ("PreviousWindow", ""): "Switch Windows (Reverse)",
    ("Close", ""): "Close Window",
    ("ToggleMaximize", ""): "Maximize/Restore",
    ("Iconify", ""): "Minimize",
    ("ToggleFullscreen", ""): "Toggle Fullscreen",
}
```

For `SnapToEdge` actions, check the `<direction>` child element:
```python
    ("SnapToEdge", "left"): "Snap Left",
    ("SnapToEdge", "right"): "Snap Right",
```

For volume/brightness/screenshot commands, match by substring:
```python
if "volume up" in command: name = "Volume Up"
elif "volume down" in command: name = "Volume Down"
elif "volume mute" in command: name = "Mute"
elif "brightness up" in command: name = "Brightness Up"
elif "brightness down" in command: name = "Brightness Down"
elif "grim -g" in command: name = "Screenshot (Region)"
elif "grim" in command: name = "Screenshot"
```

Skip internal bindings (like `C-F12` for root-menu) that users shouldn't rebind.

**UI layout:** Each shortcut row has:
- Left: action description label
- Right: a button showing the current key combo as text (styled badge)

**Key capture:** When the user clicks the key badge button:
1. Change button label to "Press new shortcut..."
2. Add a `Gtk.EventControllerKey` to the window
3. On `key-pressed` signal, capture the keyval and modifier state
4. Build the labwc key string (e.g., `"C-A-T"` for Ctrl+Alt+T)
5. Check for conflicts (is this key already bound?)
6. If conflict: show a dialog "Already bound to [action]. Reassign?"
7. If no conflict or user confirms: update the binding and save
8. Escape cancels capture mode

**Key string building from GDK:**
```python
def _build_key_string(self, keyval, state):
    from gi.repository import Gdk
    parts = []
    if state & Gdk.ModifierType.CONTROL_MASK:
        parts.append("C")
    if state & Gdk.ModifierType.ALT_MASK:
        parts.append("A")
    if state & Gdk.ModifierType.SHIFT_MASK:
        parts.append("S")
    if state & Gdk.ModifierType.SUPER_MASK:
        parts.append("W")
    key_name = Gdk.keyval_name(keyval)
    if key_name:
        parts.append(key_name)
    return "-".join(parts)
```

**Saving changes:** Write modified keybindings to `~/.config/labwc/rc.xml`. The user override file should contain the full `<keyboard>` section with all keybinds. After writing, call `labwc --reconfigure`.

**Reset:** "Reset to Default" per shortcut restores the original key from the system rc.xml. "Reset All Shortcuts" deletes the user override file's keyboard section.

- [ ] **Step 4: Update search_keywords**

Add entries for Shortcuts, Caps Lock, keybinding-related terms.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/keyboard.py
git commit -m "feat: keyboard shortcuts editor with key capture and conflict detection"
```

---

### Task 4: Date & Time Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/datetime.py`

- [ ] **Step 1: Create datetime.py**

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..base import BasePage


class DateTimePage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._time_label = None
        self._timer_id = None

    @property
    def search_keywords(self):
        return [
            ("Date & Time", "Timezone"),
            ("Date & Time", "Automatic time"),
            ("Date & Time", "NTP"),
            ("Date & Time", "24-hour clock"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Date & Time"))

        # Current time display (live updating)
        self._time_label = Gtk.Label(xalign=0)
        self._time_label.add_css_class("group-title")
        self._update_time()
        self._timer_id = GLib.timeout_add_seconds(1, self._update_time)
        page.append(self._time_label)
        page.connect("unmap", lambda _: self._cleanup())

        # Timezone
        tz_entry = Gtk.Entry()
        tz_entry.set_text(self._get_timezone())
        tz_entry.set_placeholder_text("e.g. America/New_York")
        tz_entry.set_size_request(280, -1)
        tz_entry.connect("activate", lambda e: self._set_timezone(e.get_text().strip()))
        page.append(self.make_setting_row("Timezone", "Press Enter to apply", tz_entry))

        # Automatic time (NTP)
        ntp_switch = Gtk.Switch()
        ntp_switch.set_active(self._get_ntp())
        ntp_switch.connect("state-set", lambda _, s: self._set_ntp(s) or False)
        page.append(self.make_setting_row("Automatic time", "Sync clock via network (NTP)", ntp_switch))

        # 24-hour clock
        clock_switch = Gtk.Switch()
        clock_switch.set_active(self.store.get("clock_24h", False))
        clock_switch.connect("state-set", lambda _, s: self.store.save_and_apply("clock_24h", s) or False)
        page.append(self.make_setting_row("24-hour clock", "Use 24-hour time format", clock_switch))

        return page

    def _update_time(self):
        import datetime
        now = datetime.datetime.now()
        if self.store.get("clock_24h", False):
            fmt = "%A, %B %d, %Y  %H:%M:%S"
        else:
            fmt = "%A, %B %d, %Y  %I:%M:%S %p"
        if self._time_label:
            self._time_label.set_text(now.strftime(fmt))
        return GLib.SOURCE_CONTINUE

    def _cleanup(self):
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    @staticmethod
    def _get_timezone():
        try:
            r = subprocess.run(["timedatectl", "show", "--property=Timezone", "--value"],
                               capture_output=True, text=True)
            return r.stdout.strip()
        except FileNotFoundError:
            return "UTC"

    @staticmethod
    def _set_timezone(tz):
        subprocess.run(["timedatectl", "set-timezone", tz], check=False,
                       capture_output=True)

    @staticmethod
    def _get_ntp():
        try:
            r = subprocess.run(["timedatectl", "show", "--property=NTP", "--value"],
                               capture_output=True, text=True)
            return r.stdout.strip().lower() == "yes"
        except FileNotFoundError:
            return False

    @staticmethod
    def _set_ntp(enabled):
        subprocess.run(["timedatectl", "set-ntp", "true" if enabled else "false"],
                       check=False, capture_output=True)
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/datetime.py
git commit -m "feat: create Date & Time page with timezone, NTP, and 24h clock"
```

---

### Task 5: Users Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/users.py`

Uses AccountsService D-Bus to manage user display name, password, and auto-login. The setup wizard (`files/usr/bin/adwaita-lite-setup-wizard`) already uses AccountsService — follow the same patterns.

- [ ] **Step 1: Read the wizard's AccountsService usage**

Read `files/usr/bin/adwaita-lite-setup-wizard` and search for `AccountsService`, `SetRealName`, `SetPassword`, `SetAutomaticLogin` to understand the D-Bus patterns used.

- [ ] **Step 2: Create users.py**

The page should have:

1. **Display name** — editable entry, applied via AccountsService D-Bus `SetRealName`
2. **Change Password** — button that opens dialog with current/new/confirm fields, applied via AccountsService D-Bus `SetPassword`
3. **Auto-login** — toggle via AccountsService D-Bus `SetAutomaticLogin`

AccountsService D-Bus pattern:
```python
import os
from gi.repository import Gio, GLib

bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
uid = os.getuid()

# Find user object path
result = bus.call_sync(
    "org.freedesktop.Accounts",
    "/org/freedesktop/Accounts",
    "org.freedesktop.Accounts",
    "FindUserById",
    GLib.Variant("(x)", (uid,)),
    GLib.VariantType("(o)"),
    Gio.DBusCallFlags.NONE, -1, None,
)
user_path = result.unpack()[0]

# Get current display name
result = bus.call_sync(
    "org.freedesktop.Accounts", user_path,
    "org.freedesktop.DBus.Properties", "Get",
    GLib.Variant("(ss)", ("org.freedesktop.Accounts.User", "RealName")),
    GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, -1, None,
)
real_name = result.unpack()[0]

# Set display name
bus.call_sync(
    "org.freedesktop.Accounts", user_path,
    "org.freedesktop.Accounts.User", "SetRealName",
    GLib.Variant("(s)", (new_name,)),
    None, Gio.DBusCallFlags.NONE, -1, None,
)

# Set password (SHA-512 hashed)
import crypt
hashed = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
bus.call_sync(
    "org.freedesktop.Accounts", user_path,
    "org.freedesktop.Accounts.User", "SetPassword",
    GLib.Variant("(ss)", (hashed, "")),
    None, Gio.DBusCallFlags.NONE, -1, None,
)

# Set auto-login
bus.call_sync(
    "org.freedesktop.Accounts", user_path,
    "org.freedesktop.Accounts.User", "SetAutomaticLogin",
    GLib.Variant("(b)", (enabled,)),
    None, Gio.DBusCallFlags.NONE, -1, None,
)
```

The password change dialog should:
- Have fields: Current password (unused by AccountsService but good UX), New password, Confirm password
- Validate that new == confirm before applying
- Show error if they don't match
- Use `Gtk.PasswordEntry` with peek icons
- Set transient_for on the dialog

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/users.py
git commit -m "feat: create Users page with display name, password change, auto-login"
```

---

### Task 6: Language & Region Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/language.py`

- [ ] **Step 1: Create language.py**

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage


class LanguagePage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Language & Region", "Language"),
            ("Language & Region", "Locale"),
            ("Language & Region", "Regional format"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Language & Region"))

        # Info banner
        banner = Gtk.Label(
            label="Changes take effect after logging out",
            xalign=0,
        )
        banner.add_css_class("setting-subtitle")
        page.append(banner)

        # System language
        locales = self._get_locales()
        current_locale = self._get_current_locale()

        lang_dd = Gtk.DropDown.new_from_strings(locales if locales else ["en_US.UTF-8"])
        try:
            lang_dd.set_selected(locales.index(current_locale))
        except (ValueError, IndexError):
            lang_dd.set_selected(0)
        lang_dd.set_size_request(280, -1)
        lang_dd.connect("notify::selected", lambda d, _:
            self._set_locale(locales[d.get_selected()]) if locales else None)
        page.append(self.make_setting_row("System language", "", lang_dd))

        # Regional formats
        fmt_dd = Gtk.DropDown.new_from_strings(locales if locales else ["en_US.UTF-8"])
        current_fmt = self._get_current_format()
        try:
            fmt_dd.set_selected(locales.index(current_fmt))
        except (ValueError, IndexError):
            fmt_dd.set_selected(0)
        fmt_dd.set_size_request(280, -1)
        fmt_dd.connect("notify::selected", lambda d, _:
            self._set_format(locales[d.get_selected()]) if locales else None)
        page.append(self.make_setting_row("Regional formats", "Date, number, and currency format", fmt_dd))

        return page

    @staticmethod
    def _get_locales():
        try:
            r = subprocess.run(["localectl", "list-locales"],
                               capture_output=True, text=True)
            return [l.strip() for l in r.stdout.splitlines() if l.strip()]
        except FileNotFoundError:
            return ["en_US.UTF-8"]

    @staticmethod
    def _get_current_locale():
        try:
            r = subprocess.run(["localectl", "status"], capture_output=True, text=True)
            for line in r.stdout.splitlines():
                if "LANG=" in line:
                    return line.split("LANG=")[-1].strip()
        except FileNotFoundError:
            pass
        return "en_US.UTF-8"

    @staticmethod
    def _get_current_format():
        try:
            r = subprocess.run(["localectl", "status"], capture_output=True, text=True)
            for line in r.stdout.splitlines():
                if "LC_TIME=" in line:
                    return line.split("LC_TIME=")[-1].strip()
        except FileNotFoundError:
            pass
        return LanguagePage._get_current_locale()

    @staticmethod
    def _set_locale(locale):
        subprocess.run(["localectl", "set-locale", f"LANG={locale}"],
                       check=False, capture_output=True)

    @staticmethod
    def _set_format(locale):
        subprocess.run(["localectl", "set-locale", f"LC_TIME={locale}",
                        f"LC_NUMERIC={locale}", f"LC_MONETARY={locale}"],
                       check=False, capture_output=True)
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/language.py
git commit -m "feat: create Language & Region page with locale and format selection"
```

---

### Task 7: Fix Default Apps Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`

- [ ] **Step 1: Read current default_apps.py**

- [ ] **Step 2: Fix terminal selection**

The terminal dropdown currently doesn't apply the selection (no `xdg-mime` call because there's no MIME type for terminals). Fix by writing a wrapper desktop file:

When terminal is selected, write `~/.local/share/applications/terminal.desktop`:
```ini
[Desktop Entry]
Name=Terminal
Exec={command}
Type=Application
Terminal=false
Categories=TerminalEmulator;
```

Add this logic in the dropdown handler for the Terminal entry.

- [ ] **Step 3: Add new MIME type categories**

Update `APP_MIME_TYPES` to include:
```python
APP_MIME_TYPES = [
    ("Web Browser", "x-scheme-handler/http"),
    ("File Manager", "inode/directory"),
    ("Terminal", None),
    ("Text Editor", "text/plain"),
    ("Image Viewer", "image/png"),
    ("PDF Viewer", "application/pdf"),
    ("Media Player", "video/x-matroska"),
    ("Email Client", "x-scheme-handler/mailto"),
]
```

- [ ] **Step 4: Update search_keywords**

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/default_apps.py
git commit -m "feat: fix terminal selection, add image/PDF/email default app categories"
```

---

### Task 8: Expand About Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/about.py`

- [ ] **Step 1: Read current about.py**

- [ ] **Step 2: Add GPU info**

After the Disk row, add a Graphics row. Get GPU name from `/sys/class/drm/`:

```python
gpu = "Unknown"
try:
    for card_dir in sorted(Path("/sys/class/drm/").iterdir()):
        device_vendor = card_dir / "device" / "vendor"
        device_device = card_dir / "device" / "device"
        if device_vendor.exists():
            # Try lspci for friendly name
            try:
                r = subprocess.run(["lspci"], capture_output=True, text=True)
                for line in r.stdout.splitlines():
                    if "VGA" in line or "3D" in line or "Display" in line:
                        gpu = line.split(": ", 1)[-1] if ": " in line else line
                        break
            except FileNotFoundError:
                pass
            break
except OSError:
    pass
page.append(self.make_info_row("Graphics", gpu))
```

- [ ] **Step 3: Add OS Updates section**

After the Desktop row, add an updates section:

```python
# OS Updates
page.append(self.make_group_label("Updates"))
update_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
update_box.set_valign(Gtk.Align.CENTER)
self._update_label = Gtk.Label(label="Click to check for updates", xalign=0)
self._update_label.set_hexpand(True)
update_box.append(self._update_label)
check_btn = Gtk.Button(label="Check for Updates")
check_btn.connect("clicked", lambda _: self._check_updates())
update_box.append(check_btn)
page.append(update_box)
```

The `_check_updates` method:
```python
def _check_updates(self):
    self._update_label.set_text("Checking...")
    import threading
    def _check():
        try:
            r = subprocess.run(["bootc", "status", "--json"],
                               capture_output=True, text=True)
            import json
            status = json.loads(r.stdout)
            staged = status.get("status", {}).get("staged", None)
            if staged:
                version = staged.get("image", {}).get("version", "unknown")
                GLib.idle_add(self._update_label.set_text, f"Update available: {version}")
            else:
                GLib.idle_add(self._update_label.set_text, "System is up to date")
        except Exception:
            GLib.idle_add(self._update_label.set_text, "Could not check for updates")
    threading.Thread(target=_check, daemon=True).start()
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/about.py
git commit -m "feat: expand About page with GPU info and bootc update check"
```

---

### Task 9: Register New Pages + Integration Verification

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/__init__.py`

- [ ] **Step 1: Register Date & Time, Users, and Language pages**

Add imports:
```python
from .datetime import DateTimePage
from .language import LanguagePage
from .users import UsersPage
```

Add to `ALL_PAGES`, inserting in the correct order per spec:
- After Accessibility: `("preferences-system-time-symbolic", "Date & Time", DateTimePage)`
- After Date & Time: `("system-users-symbolic", "Users", UsersPage)`
- After Users: `("preferences-desktop-locale-symbolic", "Language & Region", LanguagePage)`

The final `ALL_PAGES` should have 15 entries in this order:
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

- [ ] **Step 2: Run all tests**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/ -v
```

- [ ] **Step 3: Verify page count**

```bash
python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.pages import ALL_PAGES
print(f'{len(ALL_PAGES)} pages registered:')
for _, label, _ in ALL_PAGES:
    print(f'  {label}')
"
```

Expected: 15 pages.

- [ ] **Step 4: Verify all page files exist**

```bash
ls files/usr/lib/adwaita-lite/settings/pages/*.py | wc -l
```

Expected: 16 files (15 pages + `__init__.py`).

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/__init__.py
git commit -m "feat: register Date/Time, Users, Language pages — all 15 pages complete"
```
