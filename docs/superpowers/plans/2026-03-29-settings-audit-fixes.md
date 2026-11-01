# Settings App Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 31 bugs found in the March 29 settings app audit — 5 critical, 16 important, 10 minor.

**Architecture:** Fixes are grouped by file, starting with infrastructure (events, store, dbus_helpers) then pages, then backend. Each task is one commit touching 1-2 files. The dbus_helpers async refactor (M11) changes how BlueZ and PowerProfiles helpers initialize, which cascades into bluetooth.py and power_lock.py.

**Tech Stack:** Python 3, GTK 4 (PyGObject), GIO D-Bus, wlr-randr, pactl, timedatectl, localectl

**Model guidance:** Use Sonnet minimum for all tasks. Use Opus for Tasks 3, 5, 9, and 13 (async D-Bus refactor, display.py 7-fix rewrite, bluetooth/power_lock async adaptation).

---

## File Map

| File | Fixes | Action |
|------|-------|--------|
| `files/usr/lib/adwaita-lite/settings/events.py` | I6 | Modify |
| `files/usr/lib/adwaita-lite/settings/settings_store.py` | M1 | Modify |
| `files/usr/lib/adwaita-lite/settings/dbus_helpers.py` | I1, M2, M11 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/display.py` | C1, C2, C3, C5, I4, I14, I16 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/about.py` | C4, M6, M7 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/keyboard.py` | I5, I9 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/sound.py` | I2 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py` | I13, I14 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/network.py` | I14, M3, M4, M9 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/users.py` | I1, I8 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/datetime.py` | I7 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/power_lock.py` | I17 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/default_apps.py` | I15, M10 | Modify |
| `files/usr/lib/adwaita-lite/settings/pages/language.py` | M8 | Modify |
| `files/usr/libexec/adwaita-lite-apply-settings` | C2, I10, I11, I12 | Modify |
| `tests/test_event_bus.py` | I6 | Modify (add thread-safety test) |
| `tests/test_settings_store.py` | M1 | Modify (add missing-defaults test) |

---

### Task 1: Fix EventBus thread safety (I6)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/events.py`
- Modify: `tests/test_event_bus.py`

- [ ] **Step 1: Add thread-safety test**

Add to `tests/test_event_bus.py`:

```python
import threading

def test_concurrent_publish_subscribe(bus):
    """publish() from a background thread must not crash when subscribe() runs on main."""
    results = []
    bus.subscribe("event", lambda d: results.append(d))
    errors = []

    def bg_publish():
        try:
            for _ in range(100):
                bus.publish("event", "bg")
        except Exception as e:
            errors.append(e)

    def bg_subscribe():
        try:
            for i in range(100):
                bus.subscribe(f"event-{i}", lambda d: None)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=bg_publish)
    t2 = threading.Thread(target=bg_subscribe)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert not errors, f"Thread safety error: {errors}"
```

- [ ] **Step 2: Run test to verify it can fail**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_event_bus.py::test_concurrent_publish_subscribe -v`

Expected: May pass or fail depending on timing (race condition). The point is it exercises the concurrent path.

- [ ] **Step 3: Add threading.Lock to EventBus**

Replace the entire content of `files/usr/lib/adwaita-lite/settings/events.py`:

```python
import threading

from gi.repository import GLib


class EventBus:
    """Thread-safe publish/subscribe for system events. Callbacks run on the main GTK thread."""

    def __init__(self):
        self._subscribers: dict[str, list] = {}
        self._lock = threading.Lock()

    def subscribe(self, event: str, callback) -> None:
        with self._lock:
            self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback) -> None:
        with self._lock:
            if event in self._subscribers:
                self._subscribers[event] = [
                    cb for cb in self._subscribers[event] if cb is not callback
                ]

    def publish(self, event: str, data=None) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event, []))
        for cb in callbacks:
            GLib.idle_add(cb, data)
```

- [ ] **Step 4: Run all event bus tests**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_event_bus.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/events.py tests/test_event_bus.py
git commit -m "fix: add threading lock to EventBus for thread-safe publish/subscribe"
```

---

### Task 2: Fix SettingsStore crash on missing defaults (M1)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/settings_store.py:29-40`
- Modify: `tests/test_settings_store.py`

- [ ] **Step 1: Add test for missing defaults file**

Add to `tests/test_settings_store.py`:

```python
def test_missing_defaults_file(tmp_path):
    """SettingsStore should not crash if the defaults file does not exist."""
    settings_path = tmp_path / "settings.json"
    missing_defaults = tmp_path / "nonexistent" / "defaults.json"
    store = SettingsStore(
        settings_path=str(settings_path),
        defaults_path=str(missing_defaults),
    )
    # Should fall back to empty dict, not crash
    assert store.get("anything") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_settings_store.py::test_missing_defaults_file -v`

Expected: FAIL with `FileNotFoundError`.

- [ ] **Step 3: Fix _load to handle missing defaults**

In `files/usr/lib/adwaita-lite/settings/settings_store.py`, replace the `_load` method (lines 29-40):

```python
    def _load(self) -> dict:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Read defaults (may be missing in dev/test environments)
        try:
            default_text = self._defaults_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            default_text = "{}"
        if not self._path.exists():
            self._path.write_text(default_text, encoding="utf-8")
            return json.loads(default_text)
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._path.write_text(default_text, encoding="utf-8")
            return json.loads(default_text)
```

- [ ] **Step 4: Run all settings store tests**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_settings_store.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/settings_store.py tests/test_settings_store.py
git commit -m "fix: handle missing defaults file in SettingsStore without crashing"
```

---

### Task 3: Fix dbus_helpers — timeouts, stale events, async init (I1, M2, M11)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`

This is a large change. The three fixes are:

1. **I1**: Replace all `timeout_msec=-1` with `5000` in BlueZ and PowerProfiles `call_sync` calls
2. **M2**: Add `_stopped` flag to PulseAudioSubscriber so reader thread stops publishing after `stop()`
3. **M11**: Refactor `BlueZHelper.__init__` and `PowerProfilesHelper.__init__` to use `Gio.bus_get()` (async) instead of `Gio.bus_get_sync()`, publishing `bluetooth-ready` / `power-profiles-ready` events when done

- [ ] **Step 1: Replace all infinite D-Bus timeouts with 5000ms**

In `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`, replace every occurrence of `, -1, None)` inside BlueZHelper methods and PowerProfilesHelper methods with `, 5000, None)`.

The affected lines are in these methods:
- `BlueZHelper._find_adapter` (line 247): `Gio.DBusCallFlags.NONE, -1, None,` → `Gio.DBusCallFlags.NONE, 5000, None,`
- `BlueZHelper.is_powered` (line 270): same change
- `BlueZHelper.set_powered` (line 284): same change
- `BlueZHelper.get_devices` (line 297): same change
- `BlueZHelper.start_discovery` (line 324): same change
- `BlueZHelper.stop_discovery` (line 336): same change
- `BlueZHelper.disconnect_device` (line 375): same change
- `BlueZHelper.remove_device` (line 389): same change
- `PowerProfilesHelper.get_active_profile` (line 467): same change
- `PowerProfilesHelper.set_active_profile` (line 481): same change

- [ ] **Step 2: Add _stopped flag to PulseAudioSubscriber**

Replace the `PulseAudioSubscriber` class (lines 496-537):

```python
class PulseAudioSubscriber:
    """Runs `pactl subscribe` in background thread, publishes audio-changed events."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._proc: subprocess.Popen | None = None
        self._stopped = False
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
                if self._stopped:
                    break
                line = line.strip()
                if not line:
                    continue
                if any(kw in line for kw in ("sink", "source", "server")):
                    self._event_bus.publish("audio-changed")

        threading.Thread(target=_reader, daemon=True).start()

    def stop(self) -> None:
        self._stopped = True
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.stdout.close()
            except Exception:
                pass
            self._proc = None
```

- [ ] **Step 3: Refactor BlueZHelper to async bus init**

Replace `BlueZHelper.__init__` and `_find_adapter` (lines 230-255):

```python
class BlueZHelper:
    """Wraps BlueZ D-Bus API via Gio.DBusProxy. Publishes events: bluetooth-ready, bluetooth-changed."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        self._adapter_path: str | None = None
        Gio.bus_get(Gio.BusType.SYSTEM, None, self._on_bus_ready)

    def _on_bus_ready(self, _source, result) -> None:
        try:
            self._bus = Gio.bus_get_finish(result)
        except GLib.Error:
            self._event_bus.publish("bluetooth-ready")
            return
        self._find_adapter()
        self._subscribe_signals()
        self._event_bus.publish("bluetooth-ready")

    def _find_adapter(self) -> None:
        try:
            result = self._bus.call_sync(
                "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                None, GLib.VariantType("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE, 5000, None,
            )
            objects = result.unpack()[0]
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    self._adapter_path = path
                    break
        except GLib.Error:
            pass
```

- [ ] **Step 4: Refactor PowerProfilesHelper to async bus init**

Replace `PowerProfilesHelper.__init__` (lines 441-452):

```python
class PowerProfilesHelper:
    """Wraps net.hadess.PowerProfiles D-Bus. Publishes events: power-profiles-ready, power-profile-changed."""

    BUS_NAME = "net.hadess.PowerProfiles"
    OBJECT_PATH = "/net/hadess/PowerProfiles"
    IFACE = "net.hadess.PowerProfiles"

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        Gio.bus_get(Gio.BusType.SYSTEM, None, self._on_bus_ready)

    def _on_bus_ready(self, _source, result) -> None:
        try:
            self._bus = Gio.bus_get_finish(result)
        except GLib.Error:
            self._event_bus.publish("power-profiles-ready")
            return
        self._bus.signal_subscribe(
            self.BUS_NAME, "org.freedesktop.DBus.Properties",
            "PropertiesChanged", self.OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, self._on_props_changed, None,
        )
        self._event_bus.publish("power-profiles-ready")
```

- [ ] **Step 5: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/dbus_helpers.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/dbus_helpers.py
git commit -m "fix: finite D-Bus timeouts, stale event guard, async bus init for BlueZ/PowerProfiles"
```

---

### Task 4: Fix display.py — 7 bugs (C1, C2, C3, C5, I4, I14, I16)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/display.py`

This is the largest single-file change. All fixes are localized within display.py.

- [ ] **Step 1: Add instance variables for new guard flags and state**

In `__init__` (lines 19-25), add after line 25:

```python
        self._confirming: bool = False
        self._confirmed_modes: dict[str, str] = {}
```

- [ ] **Step 2: Fix C1 — Replace _apply_resolution (lines 287-296)**

Replace the entire `_apply_resolution` method:

```python
    @staticmethod
    def _apply_resolution(output_name, mode_str):
        """Apply a resolution mode. mode_str format: '1920x1080@60.0Hz'"""
        mode = mode_str.replace("Hz", "")
        subprocess.run(
            ["wlr-randr", "--output", output_name, "--mode", mode],
            check=False,
        )
```

- [ ] **Step 3: Fix C3 — Add guard to _apply_scale (line 166)**

Replace `_apply_scale`:

```python
    def _apply_scale(self, new_scale):
        if self._confirming:
            return
        old_scale = self.store.get("scale", 1.0)
        self._set_scale(new_scale)
        self._show_revert_dialog(old_scale, new_scale)
```

- [ ] **Step 4: Fix C3+I16 — Add guard to _revert and _keep**

Replace `_revert` (lines 224-230):

```python
    def _revert(self, dialog, old_scale):
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        self._set_scale(old_scale)
        self._confirming = True
        self._sync_buttons(old_scale)
        self._confirming = False
        dialog.destroy()
```

Replace `_keep` (lines 232-238):

```python
    def _keep(self, dialog, new_scale):
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        self.store.save_and_apply("scale", new_scale)
        self._confirming = True
        self._sync_buttons(new_scale)
        self._confirming = False
        dialog.destroy()
```

- [ ] **Step 5: Fix C5 — Use instance state for confirmed modes**

Replace `_on_resolution_changed` (lines 280-285):

```python
    def _on_resolution_changed(self, dd, _param, output_name, modes, original_mode):
        new_mode = modes[dd.get_selected()]
        old_mode = self._confirmed_modes.get(output_name, original_mode)
        if new_mode == old_mode:
            return
        self._apply_resolution(output_name, new_mode)
        self._show_res_revert_dialog(dd, output_name, modes, old_mode, new_mode)
```

- [ ] **Step 6: Fix C2 — Persist resolution in _res_keep**

Replace `_res_keep` (lines 354-358):

```python
    def _res_keep(self, dialog, output_name, new_mode):
        if self._res_revert_timer_id is not None:
            GLib.source_remove(self._res_revert_timer_id)
            self._res_revert_timer_id = None
        self._confirmed_modes[output_name] = new_mode
        # Persist so apply-settings can restore on reboot
        resolutions = self.store.get("display_resolutions", {})
        resolutions[output_name] = new_mode
        self.store.save_and_apply("display_resolutions", resolutions)
        dialog.destroy()
```

This also requires updating `_show_res_revert_dialog` to pass `output_name` and `new_mode` to `_res_keep`. Replace the keep button's connect (line 324):

```python
        keep_btn.connect("clicked", lambda _: self._res_keep(dialog, output_name, new_mode))
```

- [ ] **Step 7: Fix I16 — Add guard to _res_revert**

Replace `_res_revert` (lines 345-352):

```python
    def _res_revert(self, dialog, dropdown, output_name, modes, old_mode):
        if self._res_revert_timer_id is not None:
            GLib.source_remove(self._res_revert_timer_id)
            self._res_revert_timer_id = None
        self._apply_resolution(output_name, old_mode)
        if old_mode in modes:
            dropdown.set_selected(modes.index(old_mode))
        dialog.destroy()
```

- [ ] **Step 8: Initialize confirmed modes from current display state**

At the top of `build()`, after `displays = self._get_displays()` (line 59), initialize confirmed modes:

```python
        for name, current, modes in displays:
            if current:
                self._confirmed_modes[name] = current
```

- [ ] **Step 9: Fix I4 — Add time validation for night light entries**

Add a static method after `_get_displays`:

```python
    @staticmethod
    def _is_valid_time(text):
        """Validate HH:MM format with valid ranges."""
        return bool(re.match(r"^([01]\d|2[0-3]):[0-5]\d$", text))
```

Replace the start_entry `activate` handler (lines 126-128):

```python
        def _on_start_time(e):
            text = e.get_text().strip()
            if self._is_valid_time(text):
                self.store.save_and_apply("night_light_start", text)
            else:
                e.set_text(self.store.get("night_light_start", "20:00"))
        start_entry.connect("activate", _on_start_time)
```

Replace the end_entry `activate` handler (lines 136-138):

```python
        def _on_end_time(e):
            text = e.get_text().strip()
            if self._is_valid_time(text):
                self.store.save_and_apply("night_light_end", text)
            else:
                e.set_text(self.store.get("night_light_end", "06:00"))
        end_entry.connect("activate", _on_end_time)
```

- [ ] **Step 10: Fix I14 — Add start_new_session to wdisplays Popen**

Replace the wdisplays Popen (lines 157-158):

```python
        adv_btn.connect("clicked", lambda _: subprocess.Popen(
            ["wdisplays"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True))
```

- [ ] **Step 11: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/display.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 12: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/display.py
git commit -m "fix: resolution command, persistence, scale revert loop, stale mode, time validation"
```

---

### Task 5: Fix about.py — segfault, multi-thread, multi-GPU (C4, M6, M7)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/about.py`

- [ ] **Step 1: Add instance variables**

In `__init__` (lines 15-17), replace:

```python
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._update_label = None
        self._alive = True
        self._checking = False
```

- [ ] **Step 2: Fix M7 — Multi-GPU support**

Replace the GPU block (lines 71-80):

```python
        gpu = "Unknown"
        try:
            r = subprocess.run(["lspci"], capture_output=True, text=True)
            gpus = [line.split(": ", 1)[-1] for line in r.stdout.splitlines()
                    if any(kw in line for kw in ("VGA", "3D", "Display")) and ": " in line]
            gpu = " + ".join(gpus) if gpus else "Unknown"
        except FileNotFoundError:
            pass
        page.append(self.make_info_row("Graphics", gpu))
```

- [ ] **Step 3: Add unmap handler for alive flag**

After `page.append(update_box)` (line 99), add:

```python
        page.connect("unmap", lambda _: setattr(self, '_alive', False))
```

- [ ] **Step 4: Fix C4 and M6 — Rewrite _check_updates**

Replace the entire `_check_updates` method (lines 103-120):

```python
    def _check_updates(self):
        if self._checking:
            return
        self._checking = True
        self._update_label.set_text("Checking...")
        import threading

        def _set_if_alive(text):
            if self._alive and self._update_label:
                self._update_label.set_text(text)
            self._checking = False
            return False

        def _check():
            try:
                r = subprocess.run(["bootc", "status", "--json"],
                                   capture_output=True, text=True, timeout=30)
                import json as _json
                status = _json.loads(r.stdout)
                staged = status.get("status", {}).get("staged", None)
                if staged:
                    version = staged.get("image", {}).get("version", "unknown")
                    GLib.idle_add(_set_if_alive, f"Update available: {version}")
                else:
                    GLib.idle_add(_set_if_alive, "System is up to date")
            except Exception:
                GLib.idle_add(_set_if_alive, "Could not check for updates")

        threading.Thread(target=_check, daemon=True).start()
```

- [ ] **Step 5: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/about.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/about.py
git commit -m "fix: about page — prevent segfault on destroyed widget, multi-thread guard, multi-GPU"
```

---

### Task 6: Fix keyboard.py — capture leak, shallow copy (I5, I9)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`

- [ ] **Step 1: Fix I9 — Deep copy default bindings in constructor**

In `__init__` (line 213), replace:

```python
        self._bindings = user if user is not None else list(self._default_bindings)
```

with:

```python
        self._bindings = user if user is not None else [dict(b) for b in self._default_bindings]
```

- [ ] **Step 2: Fix I9 — Deep copy in _reset_all_shortcuts**

In `_reset_all_shortcuts` (line 546), replace:

```python
        self._bindings = list(self._default_bindings)
```

with:

```python
        self._bindings = [dict(b) for b in self._default_bindings]
```

- [ ] **Step 3: Fix I5 — Add unmap cleanup for key capture**

At the end of `build()`, before `return page` (line 338), add:

```python
        page.connect("unmap", lambda _: self._cancel_capture())
```

- [ ] **Step 4: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/keyboard.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/keyboard.py
git commit -m "fix: keyboard — deep copy default bindings, cleanup capture controller on unmap"
```

---

### Task 7: Fix sound.py — debounce refresh (I2)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/sound.py`

- [ ] **Step 1: Add refresh timer instance variable**

In `__init__`, after `self._source_names = []` (line 27), add:

```python
        self._refresh_timer_id = None
```

- [ ] **Step 2: Replace _on_audio_changed with debounced version**

Replace `_on_audio_changed` (lines 170-171):

```python
    def _on_audio_changed(self, _data):
        # Debounce: collapse rapid events into one refresh after 200ms
        if self._refresh_timer_id is not None:
            return
        self._refresh_timer_id = GLib.timeout_add(200, self._do_refresh)

    def _do_refresh(self):
        self._refresh_timer_id = None
        self._refresh()
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 3: Cancel pending refresh on unmap**

Replace the unmap handler (line 108):

```python
        def _cleanup(_):
            if self._refresh_timer_id is not None:
                GLib.source_remove(self._refresh_timer_id)
                self._refresh_timer_id = None
            if self._pa:
                self._pa.stop()
        page.connect("unmap", _cleanup)
```

- [ ] **Step 4: Add GLib import**

Ensure `GLib` is imported. Replace line 8:

```python
from gi.repository import GLib, Gtk
```

- [ ] **Step 5: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/sound.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/sound.py
git commit -m "fix: debounce sound page refresh to prevent event storm lag"
```

---

### Task 8: Fix bluetooth.py — async init, toggle visibility, zombies (I13, I14)

**Depends on:** Task 3 (BlueZHelper now publishes `bluetooth-ready` event)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py`

- [ ] **Step 1: Restructure build() for async BlueZ init**

The key change: BlueZHelper no longer blocks in `__init__`. The page must show a placeholder UI and populate when `bluetooth-ready` fires.

Replace the entire `build()` method (lines 30-91):

```python
    def build(self):
        from ..dbus_helpers import BlueZHelper
        self._bt = BlueZHelper(self.event_bus)

        page = self.make_page_box()

        # -- Header (toggle added later when we know adapter status) --
        self._header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._header.append(self.make_group_label("Bluetooth"))
        self._header_spacer = Gtk.Box()
        self._header_spacer.set_hexpand(True)
        self._header.append(self._header_spacer)
        page.append(self._header)

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("setting-subtitle")
        self._status_label.set_text("Initializing...")
        page.append(self._status_label)

        # Placeholders for device lists (populated on ready)
        self._content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.append(self._content_box)

        # Subscribe to events
        self.event_bus.subscribe("bluetooth-ready", self._on_bt_ready)
        self.event_bus.subscribe("bluetooth-changed", lambda _: self._refresh_devices())
        self.event_bus.subscribe("bluetooth-pair-success", self._on_pair_success)
        self.event_bus.subscribe("bluetooth-pair-error", self._on_pair_error)

        # Stop discovery if page is torn down
        page.connect("unmap", lambda _: self._cleanup())
        return page

    def _on_bt_ready(self, _data):
        self._status_label.set_text("")
        self._status_label.set_visible(False)

        if not self._bt.available:
            self._status_label.set_text("No Bluetooth adapter found")
            self._status_label.set_visible(True)
            return

        # Add toggle to header now that we know adapter exists
        self._toggle = Gtk.Switch()
        self._toggle.set_valign(Gtk.Align.CENTER)
        self._toggle.set_active(self._bt.is_powered())
        self._toggle.connect("state-set", self._on_toggle)
        self._header.append(self._toggle)

        # Paired devices
        self._content_box.append(self.make_group_label("Paired Devices"))
        self._paired_list = Gtk.ListBox()
        self._paired_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._content_box.append(self._paired_list)

        # Found devices
        self._content_box.append(self.make_group_label("Available Devices"))
        self._found_list = Gtk.ListBox()
        self._found_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._content_box.append(self._found_list)

        self._scan_btn = Gtk.Button(label="Search for devices")
        self._scan_btn.set_halign(Gtk.Align.START)
        self._scan_btn.connect("clicked", self._on_scan_clicked)
        self._content_box.append(self._scan_btn)

        # Advanced
        adv_btn = Gtk.Button(label="Advanced...")
        adv_btn.set_halign(Gtk.Align.START)
        adv_btn.connect("clicked", lambda _: subprocess.Popen(
            ["blueman-manager"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True))
        self._content_box.append(adv_btn)

        self._refresh_devices()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/bluetooth.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
git commit -m "fix: bluetooth — async init, hide toggle when no adapter, prevent zombie processes"
```

---

### Task 9: Fix network.py — zombies, hidden dialog, NM error feedback (I14, M3, M4, M9)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/network.py`
- Modify: `files/usr/lib/adwaita-lite/settings/dbus_helpers.py` (minor: publish nm-error event)

- [ ] **Step 1: Fix I14 — Add start_new_session to nm-connection-editor Popen**

Replace line 82-83:

```python
        adv_btn.connect("clicked", lambda _: subprocess.Popen(
            ["nm-connection-editor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True))
```

- [ ] **Step 2: Fix M3+M4 — Hidden network dialog password validation and visibility**

In `_show_hidden_dialog`, after `pw_entry` creation (line 237), add:

```python
        pw_entry.set_visible(False)
        sec_dd.connect("notify::selected", lambda d, _: pw_entry.set_visible(d.get_selected() > 0))
```

In `_do_connect` (line 248), add password validation:

```python
        def _do_connect(_btn):
            ssid = ssid_entry.get_text().strip()
            if not ssid:
                return
            if sec_dd.get_selected() > 0:
                pw = pw_entry.get_text()
                if not pw:
                    self._status_label.set_text("Password required for secured network")
                    self._status_label.set_visible(True)
                    return
            else:
                pw = None
            self._status_label.set_text(f"Connecting to {ssid}...")
            self._status_label.set_visible(True)
            self._nm.connect_wifi(ssid, pw, hidden=True)
            dialog.destroy()
```

- [ ] **Step 3: Fix M9 — NM error feedback**

In `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`, in `NetworkManagerHelper._on_client_ready` (line 60-63), replace:

```python
    def _on_client_ready(self, _source: object, result: Gio.AsyncResult) -> None:
        try:
            self._client = NM.Client.new_finish(result)
        except Exception:
            self._publish("nm-error", "Could not connect to NetworkManager")
            return
```

In `files/usr/lib/adwaita-lite/settings/pages/network.py`, subscribe to nm-error in `build()`, after line 90:

```python
        self.event_bus.subscribe("nm-error", self._on_nm_error)
```

Add the handler:

```python
    def _on_nm_error(self, message):
        self._status_label.set_text(str(message) if message else "NetworkManager unavailable")
        self._status_label.set_visible(True)
```

- [ ] **Step 4: Verify syntax for both files**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/network.py').read()); print('OK')"` and same for dbus_helpers.py.

Expected: Both `OK`.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/network.py files/usr/lib/adwaita-lite/settings/dbus_helpers.py
git commit -m "fix: network — zombie processes, hidden network validation, NM error feedback"
```

---

### Task 10: Fix users.py — D-Bus timeouts, Escape key (I1, I8)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/users.py`

- [ ] **Step 1: Fix I1 — Replace all infinite D-Bus timeouts**

In `_ensure_dbus` (line 52), replace `, -1, None,` with `, 5000, None,`.

In `_get_property` (line 62), replace `, -1, None,` with `, 5000, None,`.

In `_on_name_activate` (line 121), replace `, -1, None,` with `, 5000, None,`.

In `_on_autologin_set` (line 133), replace `, -1, None,` with `, 5000, None,`.

In `_apply` inside `_on_change_password` (line 195), replace `, -1, None,` with `, 5000, None,`.

- [ ] **Step 2: Fix I8 — Add Escape key handler to password dialog**

Add import for Gdk at the top of the file:

```python
from gi.repository import Gdk, Gio, GLib, Gtk
```

In `_on_change_password`, after `dialog.set_child(box)` (line 205), add:

```python
        esc_ctrl = Gtk.EventControllerKey()
        esc_ctrl.connect("key-pressed", lambda _c, kv, _k, _s:
            dialog.close() if Gdk.keyval_name(kv) == "Escape" else None)
        dialog.add_controller(esc_ctrl)
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/users.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/users.py
git commit -m "fix: users — finite D-Bus timeouts, Escape key for password dialog"
```

---

### Task 11: Fix datetime.py — timezone validation feedback (I7)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/datetime.py`

- [ ] **Step 1: Update timezone entry handler to pass entry ref**

Replace the `tz_entry.connect` line (line 43):

```python
        tz_entry.connect("activate", lambda e: self._set_timezone(e.get_text().strip(), e))
```

- [ ] **Step 2: Update _set_timezone to validate and give feedback**

Replace `_set_timezone` (lines 87-89):

```python
    @staticmethod
    def _set_timezone(tz, entry=None):
        r = subprocess.run(["timedatectl", "set-timezone", tz],
                           capture_output=True, text=True)
        if r.returncode != 0 and entry:
            # Reset entry to current actual timezone on failure
            actual = DateTimePage._get_timezone()
            entry.set_text(actual)
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/datetime.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/datetime.py
git commit -m "fix: reset timezone entry on invalid input instead of silently failing"
```

---

### Task 12: Fix power_lock.py — pkexec error handling, async PowerProfiles (I17)

**Depends on:** Task 3 (PowerProfilesHelper now publishes `power-profiles-ready` event)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`

- [ ] **Step 1: Fix I17 — Wrap pkexec in try/except**

Replace `_on_lid_action_changed` (lines 132-136):

```python
    def _on_lid_action_changed(self, action):
        self.store.save_and_apply("lid_close_action", action)
        try:
            subprocess.Popen(
                ["pkexec", "/usr/libexec/adwaita-lite-lid-action", action],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            pass
```

- [ ] **Step 2: Adapt Power Profile section for async init**

The PowerProfilesHelper now inits asynchronously. We need to build the UI with disabled buttons and enable them on ready.

Replace the Power Profile section of `build()` (lines 70-88):

```python
        # ── Power Profile ──
        page.append(self.make_group_label("Power Profile"))

        from ..dbus_helpers import PowerProfilesHelper
        self._power_helper = PowerProfilesHelper(self.event_bus)

        cards_box = self.make_toggle_cards(
            PROFILE_OPTIONS, "balanced",
            lambda v: self._power_helper.set_active_profile(v),
        )
        self._profile_buttons = []
        child = cards_box.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ToggleButton):
                child.set_sensitive(False)
                self._profile_buttons.append(child)
            child = child.get_next_sibling()
        page.append(cards_box)

        self.event_bus.subscribe("power-profiles-ready", self._on_profiles_ready)
        self.event_bus.subscribe("power-profile-changed", self._on_profile_changed)
```

Add the ready handler:

```python
    def _on_profiles_ready(self, _data):
        if not self._power_helper.available:
            for btn in self._profile_buttons:
                btn.set_visible(False)
            return
        current = self._power_helper.get_active_profile()
        for btn in self._profile_buttons:
            btn.set_sensitive(True)
        self._on_profile_changed(current)
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/power_lock.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/power_lock.py
git commit -m "fix: power_lock — pkexec error handling, async power profiles init"
```

---

### Task 13: Fix default_apps.py — terminal default, sanitize desktop file (I15, M10)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`

- [ ] **Step 1: Fix I15 — Detect current terminal from wrapper**

Replace `_get_default_app` (lines 95-103):

```python
    @staticmethod
    def _get_default_app(mime_type):
        if mime_type is None:
            wrapper = Path.home() / ".local/share/applications/terminal.desktop"
            if wrapper.exists():
                try:
                    for line in wrapper.read_text().splitlines():
                        if line.startswith("Exec="):
                            cmd = line.split("=", 1)[1].strip()
                            for app in Gio.AppInfo.get_all():
                                if not app.get_id():
                                    continue
                                cats = app.get_categories() or ""
                                if "TerminalEmulator" not in cats:
                                    continue
                                app_cmd = app.get_commandline() or ""
                                app_exe = app.get_executable() or ""
                                if cmd == app_cmd or cmd == app_exe:
                                    return app.get_id()
                except OSError:
                    pass
            return ""
        try:
            return subprocess.run(["xdg-mime", "query", "default", mime_type],
                                  capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return ""
```

- [ ] **Step 2: Fix M10 — Sanitize command in desktop file**

Replace `_set_terminal` (lines 64-71):

```python
    @staticmethod
    def _set_terminal(app_info):
        cmd = app_info.get_commandline() or app_info.get_executable() or ""
        name = app_info.get_display_name()
        # Sanitize: remove control characters that would break desktop file format
        cmd = "".join(c for c in cmd if c >= " ")
        name = "".join(c for c in name if c >= " ")
        desktop_dir = Path.home() / ".local/share/applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        (desktop_dir / "terminal.desktop").write_text(
            f"[Desktop Entry]\nName={name}\nExec={cmd}\nType=Application\nTerminal=false\nCategories=TerminalEmulator;\n"
        )
```

- [ ] **Step 3: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/default_apps.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/default_apps.py
git commit -m "fix: default apps — detect current terminal, sanitize desktop file commands"
```

---

### Task 14: Fix language.py — empty locales fallback (M8)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/language.py`

- [ ] **Step 1: Ensure locales list is never empty for lambda closures**

In `build()`, replace line 33:

```python
        locales = self._get_locales() or ["en_US.UTF-8"]
```

This ensures the `locales` list used in the dropdown lambdas (lines 42-43, 54-55) is never empty, so `locales[d.get_selected()]` always has a valid target.

Also remove the redundant fallback in the dropdown model creation (line 36):

```python
        lang_dd = Gtk.DropDown.new_from_strings(locales)
```

And line 47:

```python
        fmt_dd = Gtk.DropDown.new_from_strings(locales)
```

And simplify the lambdas (lines 42-43, 54-55) by removing the `if locales` guard:

```python
        lang_dd.connect("notify::selected", lambda d, _:
            self._set_locale(locales[d.get_selected()]))
```

```python
        fmt_dd.connect("notify::selected", lambda d, _:
            self._set_format(locales[d.get_selected()]))
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/language.py').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/language.py
git commit -m "fix: ensure locales list is never empty for dropdown callbacks"
```

---

### Task 15: Fix apply-settings — resolution persistence, restart race, validation (C2, I10, I11, I12)

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Fix I10 — Add sleep to restart_program**

Add `import time` at the top of the file (line 2 area, with the other imports).

Replace `restart_program` (lines 990-994):

```python
def restart_program(name: str, command: list[str]) -> None:
    if shutil.which(command[0]) is None:
        return
    subprocess.run(["pkill", "-x", name], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
```

- [ ] **Step 2: Fix I11 — Validate lock_timeout and display_off_timeout**

In `ensure_settings()`, after the `suspend_timeout` validation (lines 308-311), add:

```python
    valid_timeouts = (0, 60, 120, 300, 600, 900, 1800)
    lock_timeout = int(data.get("lock_timeout", 300))
    if lock_timeout not in valid_timeouts:
        lock_timeout = 300
    display_off_timeout = int(data.get("display_off_timeout", 600))
    if display_off_timeout not in valid_timeouts:
        display_off_timeout = 600
```

Note: wrap in try/except for non-int values:

```python
    try:
        lock_timeout = int(data.get("lock_timeout", 300))
    except (ValueError, TypeError):
        lock_timeout = 300
    if lock_timeout not in valid_timeouts:
        lock_timeout = 300
    try:
        display_off_timeout = int(data.get("display_off_timeout", 600))
    except (ValueError, TypeError):
        display_off_timeout = 600
    if display_off_timeout not in valid_timeouts:
        display_off_timeout = 600
```

Add `lock_timeout` and `display_off_timeout` to the `data.update(...)` block (line 325):

```python
    data.update({
        ...existing keys...
        "lock_timeout": lock_timeout,
        "display_off_timeout": display_off_timeout,
    })
```

- [ ] **Step 3: Fix I12 — Validate input device settings**

In `ensure_settings()`, after the lock/display timeout validation, add:

```python
    # Validate input settings
    try:
        tp_speed = float(data.get("touchpad_pointer_speed", 0))
    except (ValueError, TypeError):
        tp_speed = 0
    if not (-1 <= tp_speed <= 1):
        tp_speed = 0
    try:
        tp_scroll = float(data.get("touchpad_scroll_speed", 5))
    except (ValueError, TypeError):
        tp_scroll = 5
    if not (1 <= tp_scroll <= 10):
        tp_scroll = 5
    try:
        mouse_speed = float(data.get("mouse_pointer_speed", 0))
    except (ValueError, TypeError):
        mouse_speed = 0
    if not (-1 <= mouse_speed <= 1):
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
    try:
        kb_delay = int(data.get("keyboard_repeat_delay", 300))
    except (ValueError, TypeError):
        kb_delay = 300
    if not (150 <= kb_delay <= 1000):
        kb_delay = 300
    try:
        kb_rate = int(data.get("keyboard_repeat_rate", 40))
    except (ValueError, TypeError):
        kb_rate = 40
    if not (10 <= kb_rate <= 80):
        kb_rate = 40
```

Add all to `data.update(...)`:

```python
    data.update({
        ...existing keys...
        "touchpad_pointer_speed": tp_speed,
        "touchpad_scroll_speed": tp_scroll,
        "mouse_pointer_speed": mouse_speed,
        "mouse_accel_profile": mouse_accel,
        "keyboard_layout": kb_layout,
        "keyboard_variant": kb_variant,
        "keyboard_repeat_delay": kb_delay,
        "keyboard_repeat_rate": kb_rate,
    })
```

- [ ] **Step 4: Fix C2 — Apply stored resolution on startup**

In `main()`, after `subprocess.run(["labwc", "--reconfigure"], ...)` (line 1013), add:

```python
        # Apply stored display resolutions
        resolutions = settings.get("display_resolutions", {})
        if isinstance(resolutions, dict):
            for output_name, mode_str in resolutions.items():
                mode = str(mode_str).replace("Hz", "")
                subprocess.run(
                    ["wlr-randr", "--output", str(output_name), "--mode", mode],
                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
```

- [ ] **Step 5: Fix night light time validation in ensure_settings**

Replace the night light start/end validation (lines 305-306):

```python
    import re as _re
    night_light_start = str(data.get("night_light_start", "20:00"))
    if not _re.match(r"^([01]\d|2[0-3]):[0-5]\d$", night_light_start):
        night_light_start = "20:00"
    night_light_end = str(data.get("night_light_end", "06:00"))
    if not _re.match(r"^([01]\d|2[0-3]):[0-5]\d$", night_light_end):
        night_light_end = "06:00"
```

- [ ] **Step 6: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/libexec/adwaita-lite-apply-settings').read()); print('OK')"`

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "fix: apply-settings — restart race, validate timeouts/input/time, persist resolution"
```

---

## Verification Checklist

After all tasks are complete, verify end-to-end:

1. **Syntax check all modified files:**
   ```bash
   find files/usr/lib/adwaita-lite/settings -name "*.py" -exec python3 -c "import ast; ast.parse(open('{}').read()); print('{}: OK')" \;
   python3 -c "import ast; ast.parse(open('files/usr/libexec/adwaita-lite-apply-settings').read()); print('apply-settings: OK')"
   ```

2. **Run all tests:**
   ```bash
   cd /var/home/race/ublue-mike && python -m pytest tests/ -v
   ```

3. **Manual verification** (on running system):
   - Scale change → Keep → no second dialog
   - Resolution change → Keep → persists after closing/reopening settings
   - About → Check for Updates → navigate away immediately → no crash
   - Keyboard → start capture → navigate away → keys not captured elsewhere
   - Sound → drag volume slider rapidly → no lag
   - Bluetooth (no adapter) → "No adapter found" with no toggle
   - Night light → type "abc" in time field → resets to stored value
   - Timezone → type "Invalid/Zone" → resets to current timezone
   - Password dialog → press Escape → closes
