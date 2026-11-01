# Settings App Audit Fixes Design

**Goal:** Fix all 31 issues found in the March 29 2026 settings app audit — 5 critical, 16 important, 10 minor — covering crashes, data loss, UI hangs, and edge cases.

**Approach:** Group fixes by file. Start with files containing critical issues, then work through the rest. Each file-group is one commit.

---

## Fix Inventory

### Critical

| ID | File | Issue |
|----|------|-------|
| C1 | display.py | `_apply_resolution` uses `--custom-mode` incorrectly; Hz still in string |
| C2 | display.py + apply-settings | Resolution changes not persisted across reboot |
| C3 | display.py + base.py | Scale revert triggers `_sync_buttons` -> re-entrant `_apply_scale` -> infinite dialog loop |
| C4 | about.py | Update thread calls `set_text` on potentially-destroyed widget (segfault) |
| C5 | display.py | `old_mode` captured at build time; second resolution change reverts to wrong mode |

### Important

| ID | File | Issue |
|----|------|-------|
| I1 | dbus_helpers.py, users.py | All BlueZ, PowerProfiles, AccountsService `call_sync` use `timeout=-1` (infinite) — UI hangs forever if service is stuck |
| I2 | sound.py | PulseAudio event storm: every slider tick -> pactl -> event -> `_refresh()` (8 subprocess calls) -> repeat. No debounce. |
| I4 | display.py | Night light start/end time entries accept arbitrary text ("banana", "25:99") |
| I5 | keyboard.py | Key capture `EventControllerKey` never removed on page unmap — captures keys globally after navigating away |
| I6 | events.py | `publish()` from PulseAudio background thread races with `subscribe()` on main thread — no lock |
| I7 | datetime.py | `timedatectl set-timezone` errors swallowed silently; user sees typo as if it worked |
| I8 | users.py | Password dialog is plain `Gtk.Window` — no Escape key to dismiss |
| I9 | keyboard.py | `_reset_all_shortcuts` shallow-copies default bindings; subsequent edits corrupt the defaults |
| I10 | apply-settings | `restart_program`: pkill then immediate Popen — old process may not have exited, causing duplicates |
| I11 | apply-settings | `lock_timeout` and `display_off_timeout` never validated in `ensure_settings()` |
| I12 | apply-settings | Input device settings (touchpad/mouse/keyboard) never validated |
| I13 | bluetooth.py | Bluetooth toggle shown but non-functional when no adapter found |
| I14 | bluetooth.py, network.py, display.py | `Popen` for "Advanced..." buttons leaks zombie processes |
| I15 | default_apps.py | Terminal dropdown never reflects current selection |
| I16 | display.py | Scale/resolution revert dialog double-fires via `close-request` -> `_revert` -> `destroy` -> `close-request` |
| I17 | power_lock.py | pkexec lid action: unhandled `FileNotFoundError`, no feedback on auth cancel |

### Minor

| ID | File | Issue |
|----|------|-------|
| M1 | settings_store.py | Crashes if defaults file is missing (`FileNotFoundError` unhandled) |
| M2 | dbus_helpers.py | `PulseAudioSubscriber.stop()` can deliver stale events after stop |
| M3 | network.py | Hidden network dialog: empty password with WPA selected produces confusing NM error |
| M4 | network.py | Hidden network password field always visible regardless of security selection |
| M6 | about.py | Multiple simultaneous update check threads on rapid clicking |
| M7 | about.py | `lspci` GPU parsing only shows first GPU on multi-GPU systems |
| M8 | language.py | Empty locales list results in non-functional dropdown |
| M9 | network.py | `NM.Client.new_async` silently swallows errors — WiFi section blank with no explanation |
| M10 | default_apps.py | `_set_terminal` writes unsanitized command to `.desktop` file |
| M11 | dbus_helpers.py | `Gio.bus_get_sync()` in BlueZ/PowerProfiles constructors blocks main thread |

---

## Fixes by File

### 1. `display.py` — C1, C2, C3, C5, I4, I14, I16

**C1 — Fix resolution command:**
Replace `_apply_resolution` body. Strip "Hz", use `--mode` with the full `WxH@rate` string (wlr-randr accepts this format):
```python
@staticmethod
def _apply_resolution(output_name, mode_str):
    # mode_str: "1920x1080@60.0Hz" -> "1920x1080@60.0"
    mode = mode_str.replace("Hz", "")
    subprocess.run(
        ["wlr-randr", "--output", output_name, "--mode", mode],
        check=False,
    )
```

**C2 — Persist resolution across reboot:**
- In `_res_keep`, save the chosen mode per output to settings.json: `self.store.save_and_apply(f"display_resolution", {output_name: mode_str})` — actually, store a dict `display_resolutions` mapping output names to mode strings.
- In `apply-settings`, if `display_resolutions` exists and we're in a Wayland session, call `wlr-randr --output NAME --mode MODE` for each stored output.
- Default: `{}` (empty dict, meaning "use compositor default").

**C3 — Scale revert infinite loop:**
Add a `self._confirming = False` guard flag. Set it `True` in `_revert` and `_keep` before calling `_sync_buttons`, clear after. In `_apply_scale`, early-return if `self._confirming`.

**C5 — Stale old_mode:**
Store confirmed mode as instance state `self._confirmed_modes: dict[str, str]` (output -> mode). Update it in `_res_keep`. In `_on_resolution_changed`, read `old_mode` from `self._confirmed_modes.get(output_name, original)`.

**I4 — Night light time validation:**
Add a `_validate_time(text)` helper that checks `re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text)`. In the `activate` handler, only save if valid; otherwise reset the entry to the stored value.

**I14 — Zombie processes (wdisplays):**
Store Popen reference and use `start_new_session=True` so the child isn't a zombie. Or simpler: use `subprocess.Popen(...).pid` and don't store — set `start_new_session=True` so the process is reparented to init immediately.

**I16 — Double-revert:**
The `close-request` handler already returns `True` (prevents default close). But `_revert` calls `dialog.destroy()`. Add a `_scale_reverting` guard at the top of `_revert`/`_res_revert` to skip if already in progress.

### 2. `events.py` — I6

Add `threading.Lock`:
```python
import threading

class EventBus:
    def __init__(self):
        self._subscribers: dict[str, list] = {}
        self._lock = threading.Lock()

    def subscribe(self, event, callback):
        with self._lock:
            self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event, callback):
        with self._lock:
            if event in self._subscribers:
                self._subscribers[event] = [
                    cb for cb in self._subscribers[event] if cb is not callback
                ]

    def publish(self, event, data=None):
        with self._lock:
            callbacks = list(self._subscribers.get(event, []))
        for cb in callbacks:
            GLib.idle_add(cb, data)
```

### 3. `about.py` — C4, M6, M7

**C4 — Widget-alive check:**
Add `self._alive = True` flag. Set to `False` in unmap handler. In the thread's `GLib.idle_add` callback, check `self._alive` before calling `set_text`.

Connect unmap:
```python
page.connect("unmap", lambda _: setattr(self, '_alive', False))
```

In `_check`:
```python
def _set_if_alive(text):
    if self._alive and self._update_label:
        self._update_label.set_text(text)
GLib.idle_add(_set_if_alive, f"Update available: {version}")
```

**M6 — Multiple threads:**
Add `self._checking = False` flag. Set `True` at start of `_check_updates`, clear in the thread's finally. Early-return if already checking.

**M7 — Multi-GPU:**
Collect all matching `lspci` lines and join with " + ":
```python
gpus = [line.split(": ", 1)[-1] for line in r.stdout.splitlines()
        if any(kw in line for kw in ("VGA", "3D", "Display"))]
gpu = " + ".join(gpus) if gpus else "Unknown"
```

### 4. `keyboard.py` — I5, I9

**I5 — Capture cleanup on unmap:**
In `build()`, add: `page.connect("unmap", lambda _: self._cancel_capture())`

**I9 — Deep copy default bindings:**
Change `_reset_all_shortcuts`:
```python
self._bindings = [dict(b) for b in self._default_bindings]
```
Also fix the constructor's initial copy:
```python
self._bindings = user if user is not None else [dict(b) for b in self._default_bindings]
```

### 5. `dbus_helpers.py` — I1, M2, M11

**I1 — Finite D-Bus timeouts:**
Replace all `timeout_msec=-1` with `5000` (5 seconds) in BlueZ `call_sync` calls and PowerProfiles `call_sync` calls. This is a mechanical replacement of `, -1, None)` -> `, 5000, None)` in the relevant methods.

**M2 — PulseAudioSubscriber stale events:**
Add a `self._stopped = True` flag in `stop()`. Check it in the reader thread before publishing:
```python
def _reader():
    for line in self._proc.stdout:
        if self._stopped:
            break
        ...
```

**M11 — Async bus_get_sync:**
Refactor `BlueZHelper.__init__` and `PowerProfilesHelper.__init__` to use `Gio.bus_get()` (async):

```python
class BlueZHelper:
    def __init__(self, event_bus):
        self._event_bus = event_bus
        self._bus = None
        self._adapter_path = None
        Gio.bus_get(Gio.BusType.SYSTEM, None, self._on_bus_ready)

    def _on_bus_ready(self, _source, result):
        try:
            self._bus = Gio.bus_get_finish(result)
        except GLib.Error:
            return
        self._find_adapter()
        self._subscribe_signals()
        self._event_bus.publish("bluetooth-ready")
```

Pages must handle the helper not being ready yet. Both pages already handle `available == False` gracefully. The pattern:

1. `BluetoothPage.build()`: Show header + "Initializing..." label. Subscribe to `bluetooth-ready`. On ready callback, clear the label and populate the full UI (toggle, device lists, scan button). If no adapter, show "No Bluetooth adapter found" instead.

2. `PowerLockPage.build()`: Show the power profile section with buttons disabled initially. Subscribe to `power-profiles-ready`. On ready callback, set the correct active button and enable them. If unavailable, hide the section.

This matches the existing async pattern used by NetworkManager (`nm-ready` event).

### 6. `sound.py` — I2

**Debounce `_refresh`:**
Replace immediate refresh with a debounced version:
```python
self._refresh_timer_id = None

def _on_audio_changed(self, _data):
    if self._refresh_timer_id is not None:
        return  # refresh already pending
    self._refresh_timer_id = GLib.timeout_add(200, self._do_refresh)

def _do_refresh(self):
    self._refresh_timer_id = None
    self._refresh()
    return GLib.SOURCE_REMOVE
```

Also cancel pending refresh in unmap cleanup.

### 7. `users.py` — I1, I8

**I1 — Finite D-Bus timeouts:**
Replace all `timeout_msec=-1` with `5000` in `_ensure_dbus`, `_get_property`, `_on_name_activate`, `_on_autologin_set`, and the `SetPassword` call.

**I8 — Escape key on password dialog:**
Add EventControllerKey to the password dialog:
```python
esc_ctrl = Gtk.EventControllerKey()
esc_ctrl.connect("key-pressed", lambda _c, keyval, _k, _s:
    dialog.close() if Gdk.keyval_name(keyval) == "Escape" else None)
dialog.add_controller(esc_ctrl)
```

### 8. `bluetooth.py` — I13, I14

**I13 — Hide toggle when no adapter:**
Move the toggle construction inside the `if self._bt.available` branch. When no adapter, show only the "No Bluetooth adapter found" label.

With the M11 async fix, this becomes: show the header without a toggle initially. When `bluetooth-ready` fires, add the toggle if adapter is available, or show the "no adapter" label.

**I14 — Zombie processes (blueman-manager):**
Add `start_new_session=True` to the Popen call.

### 9. `network.py` — I14, M3, M4, M9

**I14 — Zombie processes (nm-connection-editor):**
Add `start_new_session=True`.

**M3 — Empty password validation:**
In the hidden network dialog, before calling `connect_wifi`, check that password is non-empty when security > 0:
```python
if sec_dd.get_selected() > 0 and not pw_entry.get_text().strip():
    # Show inline error
    return
```

**M4 — Hide password field when security is None:**
Connect the security dropdown's `notify::selected` signal to toggle password entry visibility:
```python
pw_entry.set_visible(sec_dd.get_selected() > 0)
sec_dd.connect("notify::selected", lambda d, _: pw_entry.set_visible(d.get_selected() > 0))
```

**M9 — NM.Client error feedback:**
In `_on_client_ready`, on failure, publish an event or set a flag. In NetworkPage, show "Could not connect to NetworkManager" label if NM fails to initialize.

### 10. `datetime.py` — I7

After `_set_timezone`, re-read the timezone to confirm it took effect:
```python
@staticmethod
def _set_timezone(tz, entry=None):
    r = subprocess.run(["timedatectl", "set-timezone", tz],
                       capture_output=True, text=True)
    if r.returncode != 0 and entry:
        # Reset entry to current actual timezone
        entry.set_text(DateTimePage._get_timezone())
```

Pass `entry` as a parameter from the connect handler so we can reset it on failure.

### 11. `power_lock.py` — I17

Wrap in try/except and check result:
```python
def _on_lid_action_changed(self, action):
    self.store.save_and_apply("lid_close_action", action)
    try:
        subprocess.Popen(
            ["pkexec", "/usr/libexec/adwaita-lite-lid-action", action],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        pass  # pkexec not available
```

### 12. `default_apps.py` — I15, M10

**I15 — Terminal default detection:**
Read the existing `terminal.desktop` wrapper to detect current terminal:
```python
@staticmethod
def _get_default_app(mime_type):
    if mime_type is None:
        # Check our terminal wrapper
        wrapper = Path.home() / ".local/share/applications/terminal.desktop"
        if wrapper.exists():
            for line in wrapper.read_text().splitlines():
                if line.startswith("Exec="):
                    cmd = line.split("=", 1)[1].strip()
                    # Match against known terminal desktop IDs by command
                    for app in Gio.AppInfo.get_all():
                        if (app.get_categories() or "").find("TerminalEmulator") >= 0:
                            if app.get_commandline() == cmd or app.get_executable() == cmd:
                                return app.get_id() or ""
        return ""
    ...
```

**M10 — Sanitize desktop file command:**
Escape special characters in the `Exec=` line. Desktop entry spec escaping:
```python
cmd = (app_info.get_commandline() or app_info.get_executable() or "")
# Remove any newlines or control characters
cmd = cmd.replace("\n", "").replace("\r", "")
```

### 13. `settings_store.py` — M1

Wrap defaults file read in try/except:
```python
def _load(self):
    ...
    try:
        defaults = json.loads(self._defaults_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        defaults = {}
    ...
```

### 14. `language.py` — M8

If `_get_locales()` returns empty, fall back to `["en_US.UTF-8"]` for both the dropdown model AND the `locales` list used in the lambda:
```python
locales = self._get_locales() or ["en_US.UTF-8"]
```

### 15. `apply-settings` — C2, I10, I11, I12

**C2 — Apply stored resolution on startup:**
In `main()`, after Wayland session check, read `display_resolutions` from settings and apply:
```python
resolutions = settings.get("display_resolutions", {})
for output_name, mode_str in resolutions.items():
    mode = mode_str.replace("Hz", "")
    subprocess.run(["wlr-randr", "--output", output_name, "--mode", mode],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```

**I10 — restart_program race:**
Replace the pkill/Popen sequence with pkill + wait:
```python
def restart_program(name, command):
    if shutil.which(command[0]) is None:
        return
    subprocess.run(["pkill", "-x", name], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-x", name, "--wait"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=2)
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```
Actually `pkill --wait` isn't available on all systems. Use a simpler approach:
```python
def restart_program(name, command):
    if shutil.which(command[0]) is None:
        return
    subprocess.run(["pkill", "-x", name], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
```

**I11 — Validate lock/display timeouts:**
Add to `ensure_settings()`:
```python
valid_timeouts = (0, 60, 120, 300, 600, 900, 1800)
lock_timeout = int(data.get("lock_timeout", 300))
if lock_timeout not in valid_timeouts:
    lock_timeout = 300
display_off_timeout = int(data.get("display_off_timeout", 600))
if display_off_timeout not in valid_timeouts:
    display_off_timeout = 600
```
Add both to `data.update(...)`.

**I12 — Validate input settings:**
Add validation for all input device settings:
```python
# Validate input settings
tp_speed = data.get("touchpad_pointer_speed", 0)
if not isinstance(tp_speed, (int, float)) or not (-1 <= tp_speed <= 1):
    tp_speed = 0
tp_scroll = data.get("touchpad_scroll_speed", 5)
if not isinstance(tp_scroll, (int, float)) or not (1 <= tp_scroll <= 10):
    tp_scroll = 5
mouse_speed = data.get("mouse_pointer_speed", 0)
if not isinstance(mouse_speed, (int, float)) or not (-1 <= mouse_speed <= 1):
    mouse_speed = 0
mouse_accel = data.get("mouse_accel_profile", "default")
if mouse_accel not in ("default", "flat", "adaptive"):
    mouse_accel = "default"
kb_layout = data.get("keyboard_layout", "us")
if not isinstance(kb_layout, str) or not kb_layout:
    kb_layout = "us"
kb_variant = data.get("keyboard_variant", "")
if not isinstance(kb_variant, str):
    kb_variant = ""
kb_delay = data.get("keyboard_repeat_delay", 300)
if not isinstance(kb_delay, (int, float)) or not (150 <= kb_delay <= 1000):
    kb_delay = 300
kb_rate = data.get("keyboard_repeat_rate", 40)
if not isinstance(kb_rate, (int, float)) or not (10 <= kb_rate <= 80):
    kb_rate = 40
```
Add all to `data.update(...)`.

---

## Night Light Custom Schedule Note

The custom schedule for night light only evaluates at the moment `apply-settings` runs (on settings change or session start). It does not automatically transition at the configured start/end time. Sunset-to-sunrise mode (using native gammastep scheduling) is recommended for automatic transitions. This is an accepted limitation.

---

## Verification

1. **Resolution changes:** Open Display page, change resolution, confirm it applies. Click Keep, reboot, confirm resolution persists. Test with a mode that has a refresh rate.
2. **Scale revert:** Change scale, confirm dialog appears. Click Keep — no second dialog should appear. Click Revert — should revert without infinite loop.
3. **About page:** Navigate to About, click Check for Updates, immediately navigate away. No crash.
4. **Keyboard shortcuts:** Start key capture on Keyboard page, navigate away. Keys should not be captured on other pages. Reset All should not corrupt defaults on subsequent edits.
5. **Sound:** Drag volume slider rapidly. UI should remain responsive (no lag storm).
6. **Bluetooth no adapter:** On a system without Bluetooth, the page should show "No adapter found" with no interactive toggle.
7. **Night light validation:** Type invalid time in custom schedule fields — should be rejected.
8. **Timezone validation:** Type invalid timezone — entry should reset to current timezone.
9. **Password dialog:** Press Escape — dialog should close.
10. **D-Bus timeouts:** With BlueZ/AccountsService stopped, the app should not hang — operations should fail gracefully after 5s.
11. **Terminal default:** Set terminal to foot, close settings, reopen — dropdown should show foot selected.
