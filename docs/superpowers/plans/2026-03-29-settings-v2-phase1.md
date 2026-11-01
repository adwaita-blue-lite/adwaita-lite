# Settings App v2 Phase 1: Architecture + Connectivity

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Model guidance:** Use Sonnet for Tasks 1–7 and 10–15 (infrastructure, migrations). Use **Opus** for Tasks 8–9 (D-Bus helpers) and 16–17 (Network/Bluetooth pages) — these involve complex D-Bus integration and async patterns.
>
> **GTK4 reference:** Use context7 (`/websites/gtk_gtk4` and `/websites/pygobject_gnome`) to verify GTK4 patterns before implementing any widget or async code.

**Goal:** Refactor the monolithic settings app into a proper Python package and add Network + Bluetooth pages with live D-Bus event subscriptions.

**Architecture:** Package at `/usr/lib/adwaita-lite/settings/` with `BasePage`, `SettingsStore`, `EventBus`, and `ToastWidget` infrastructure. NM integration via `gi.repository.NM` (matching the setup wizard's pattern). BlueZ via `Gio.DBusProxy`. Thin launcher at `/usr/bin/adwaita-lite-settings`.

**Tech Stack:** Python 3, GTK 4 (PyGObject), NM 1.0 GI bindings, Gio D-Bus, GLib event loop

**Spec:** `docs/superpowers/specs/2026-03-29-settings-app-v2-design.md`

---

## File Structure

### Create

```
files/usr/lib/adwaita-lite/settings/__init__.py
files/usr/lib/adwaita-lite/settings/app.py
files/usr/lib/adwaita-lite/settings/window.py
files/usr/lib/adwaita-lite/settings/base.py
files/usr/lib/adwaita-lite/settings/settings_store.py
files/usr/lib/adwaita-lite/settings/events.py
files/usr/lib/adwaita-lite/settings/dbus_helpers.py
files/usr/lib/adwaita-lite/settings/css/style.css
files/usr/lib/adwaita-lite/settings/pages/__init__.py
files/usr/lib/adwaita-lite/settings/pages/appearance.py
files/usr/lib/adwaita-lite/settings/pages/display.py
files/usr/lib/adwaita-lite/settings/pages/network.py
files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
files/usr/lib/adwaita-lite/settings/pages/panel.py
files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py
files/usr/lib/adwaita-lite/settings/pages/keyboard.py
files/usr/lib/adwaita-lite/settings/pages/sound.py
files/usr/lib/adwaita-lite/settings/pages/power_lock.py
files/usr/lib/adwaita-lite/settings/pages/default_apps.py
files/usr/lib/adwaita-lite/settings/pages/about.py
tests/test_settings_store.py
tests/test_event_bus.py
```

### Modify

```
files/usr/bin/adwaita-lite-settings          (replace with thin launcher)
build_files/build.sh                           (add nm-connection-editor, wdisplays, gammastep)
```

---

### Task 1: Create Package Directory Structure

**Files:**
- Create: all `__init__.py` files and `css/` directory

- [ ] **Step 1: Create directory tree**

```bash
mkdir -p files/usr/lib/adwaita-lite/settings/css
mkdir -p files/usr/lib/adwaita-lite/settings/pages
mkdir -p tests
```

- [ ] **Step 2: Create empty __init__.py files**

Create `files/usr/lib/adwaita-lite/settings/__init__.py`:
```python
```

Create `files/usr/lib/adwaita-lite/settings/pages/__init__.py` (placeholder, populated in Task 15):
```python
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/ tests/
git commit -m "chore: create settings v2 package directory structure"
```

---

### Task 2: Implement and Test SettingsStore

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/settings_store.py`
- Create: `tests/test_settings_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_settings_store.py`:

```python
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings.settings_store import SettingsStore


def _make_store(tmp_path, defaults=None, existing=None):
    defaults = defaults or {"theme": "light", "accent": "blue"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    settings_file = tmp_path / "settings.json"
    if existing is not None:
        settings_file.write_text(json.dumps(existing))
    return SettingsStore(
        settings_path=settings_file,
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )


def test_loads_defaults_when_no_file(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("theme") == "light"
    assert store.get("accent") == "blue"


def test_loads_existing_file(tmp_path):
    store = _make_store(tmp_path, existing={"theme": "dark", "accent": "red"})
    assert store.get("theme") == "dark"
    assert store.get("accent") == "red"


def test_get_with_default(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("nonexistent", "fallback") == "fallback"


def test_save_and_apply_writes_json(tmp_path):
    store = _make_store(tmp_path)
    store.save_and_apply("theme", "dark")
    assert store.get("theme") == "dark"
    written = json.loads((tmp_path / "settings.json").read_text())
    assert written["theme"] == "dark"


def test_save_dict_and_apply(tmp_path):
    store = _make_store(tmp_path)
    store.save_dict_and_apply({"theme": "dark", "accent": "red"})
    assert store.get("theme") == "dark"
    assert store.get("accent") == "red"


def test_atomic_write_creates_file(tmp_path):
    store = _make_store(tmp_path)
    store.save_and_apply("theme", "dark")
    assert (tmp_path / "settings.json").exists()
    assert not (tmp_path / "settings.json.tmp").exists()


def test_corrupted_file_resets_to_defaults(tmp_path):
    defaults = {"theme": "light"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{invalid json")
    store = SettingsStore(
        settings_path=settings_file,
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )
    assert store.get("theme") == "light"
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/test_settings_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'settings.settings_store'`

- [ ] **Step 3: Implement SettingsStore**

Create `files/usr/lib/adwaita-lite/settings/settings_store.py`:

```python
import json
import os
import subprocess
import threading
from pathlib import Path

from gi.repository import GLib


class SettingsStore:
    """JSON settings persistence with atomic writes, debounce, and apply feedback."""

    def __init__(self, settings_path=None, defaults_path=None, apply_script=None):
        self._path = Path(
            settings_path
            or Path.home() / ".config/adwaita-lite/settings.json"
        )
        self._defaults_path = Path(
            defaults_path
            or "/usr/share/adwaita-lite/defaults/settings.json"
        )
        self._apply_script = str(
            apply_script or "/usr/libexec/adwaita-lite-apply-settings"
        )
        self._debounce_timers: dict[str, int] = {}
        self._toast_callback = None
        self._data = self._load()

    def _load(self) -> dict:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            default_text = self._defaults_path.read_text(encoding="utf-8")
            self._path.write_text(default_text, encoding="utf-8")
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            default_text = self._defaults_path.read_text(encoding="utf-8")
            self._path.write_text(default_text, encoding="utf-8")
            return json.loads(default_text)

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def save_and_apply(self, key: str, value) -> None:
        self._data[key] = value
        self._write()
        self._run_apply()

    def save_dict_and_apply(self, updates: dict) -> None:
        self._data.update(updates)
        self._write()
        self._run_apply()

    def save_debounced(self, key: str, value, delay_ms: int = 300) -> None:
        if key in self._debounce_timers:
            GLib.source_remove(self._debounce_timers[key])

        def _apply():
            self._debounce_timers.pop(key, None)
            self.save_and_apply(key, value)
            return GLib.SOURCE_REMOVE

        self._debounce_timers[key] = GLib.timeout_add(delay_ms, _apply)

    def set_toast_callback(self, callback) -> None:
        self._toast_callback = callback

    def _write(self) -> None:
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, indent=2) + "\n", encoding="utf-8"
        )
        os.rename(tmp, self._path)

    def _run_apply(self) -> None:
        try:
            proc = subprocess.Popen(
                [self._apply_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            if self._toast_callback:
                self._toast_callback("Apply script not found", True)
            return

        def _wait():
            _, stderr = proc.communicate()
            GLib.idle_add(self._on_apply_done, proc.returncode, stderr)

        threading.Thread(target=_wait, daemon=True).start()

    def _on_apply_done(self, returncode: int, stderr_bytes: bytes) -> bool:
        if self._toast_callback is not None:
            if returncode == 0:
                self._toast_callback("Settings applied", False)
            else:
                err = stderr_bytes.decode("utf-8", errors="replace").strip()
                msg = f"Failed to apply: {err[:80]}" if err else "Failed to apply settings"
                self._toast_callback(msg, True)
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/test_settings_store.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/settings_store.py tests/test_settings_store.py
git commit -m "feat: implement SettingsStore with atomic writes and debounce"
```

---

### Task 3: Implement and Test EventBus

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/events.py`
- Create: `tests/test_event_bus.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_event_bus.py`:

```python
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings.events import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe("test-event", lambda data: received.append(data))
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("test-event", "payload")
    assert received == ["payload"]


def test_unsubscribe():
    bus = EventBus()
    received = []
    cb = lambda data: received.append(data)
    bus.subscribe("test-event", cb)
    bus.unsubscribe("test-event", cb)
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("test-event", "payload")
    assert received == []


def test_publish_no_subscribers():
    bus = EventBus()
    bus.publish("nonexistent-event", "data")  # should not raise


def test_multiple_subscribers():
    bus = EventBus()
    r1, r2 = [], []
    bus.subscribe("evt", lambda d: r1.append(d))
    bus.subscribe("evt", lambda d: r2.append(d))
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("evt", 42)
    assert r1 == [42]
    assert r2 == [42]
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/test_event_bus.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement EventBus**

Create `files/usr/lib/adwaita-lite/settings/events.py`:

```python
from gi.repository import GLib


class EventBus:
    """Thread-safe publish/subscribe for system events. Callbacks run on the main GTK thread."""

    def __init__(self):
        self._subscribers: dict[str, list] = {}

    def subscribe(self, event: str, callback) -> None:
        self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback) -> None:
        if event in self._subscribers:
            self._subscribers[event] = [
                cb for cb in self._subscribers[event] if cb is not callback
            ]

    def publish(self, event: str, data=None) -> None:
        for cb in list(self._subscribers.get(event, [])):
            GLib.idle_add(cb, data)
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/test_event_bus.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/events.py tests/test_event_bus.py
git commit -m "feat: implement EventBus with thread-safe publish/subscribe"
```

---

### Task 4: Implement BasePage

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/base.py`

- [ ] **Step 1: Create BasePage with widget factories**

Create `files/usr/lib/adwaita-lite/settings/base.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .events import EventBus
from .settings_store import SettingsStore


class BasePage:
    """Base class for all settings pages. Provides shared widget factories and infrastructure."""

    def __init__(self, store: SettingsStore, event_bus: EventBus) -> None:
        self.store = store
        self.event_bus = event_bus

    @property
    def search_keywords(self) -> list[tuple[str, str]]:
        return []

    def build(self) -> Gtk.Widget:
        raise NotImplementedError

    def refresh(self) -> None:
        pass

    @staticmethod
    def make_page_box() -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        page.set_margin_top(32)
        page.set_margin_bottom(32)
        page.set_margin_start(40)
        page.set_margin_end(40)
        return page

    @staticmethod
    def make_group_label(text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.add_css_class("group-title")
        return lbl

    @staticmethod
    def make_setting_row(label: str, subtitle: str, control: Gtk.Widget) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("setting-row")
        row.set_valign(Gtk.Align.CENTER)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        left.set_hexpand(True)
        left.set_valign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=label, xalign=0)
        left.append(lbl)
        if subtitle:
            sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
            sub.add_css_class("setting-subtitle")
            left.append(sub)
        row.append(left)
        control.set_valign(Gtk.Align.CENTER)
        row.append(control)
        return row

    @staticmethod
    def make_info_row(label: str, value: str) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("setting-row")
        row.set_valign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        row.append(lbl)
        val = Gtk.Label(label=value, xalign=1)
        val.add_css_class("setting-subtitle")
        row.append(val)
        return row

    @staticmethod
    def make_toggle_cards(options: list[tuple[str, str]], active: str, callback) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons: list[Gtk.ToggleButton] = []

        def _on_toggled(btn: Gtk.ToggleButton, value: str) -> None:
            if not btn.get_active():
                btn.set_active(True)
                return
            for other in buttons:
                if other is not btn and other.get_active():
                    other.set_active(False)
            callback(value)

        for value, label in options:
            btn = Gtk.ToggleButton(label=label)
            btn.add_css_class("toggle-card")
            btn.set_active(value == active)
            btn.connect("toggled", _on_toggled, value)
            buttons.append(btn)
            box.append(btn)
        return box
```

- [ ] **Step 2: Verify import works**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.base import BasePage
print('BasePage imported OK')
"
```

Expected: `BasePage imported OK`

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/base.py
git commit -m "feat: implement BasePage with shared widget factories"
```

---

### Task 5: Implement ToastWidget and Extract CSS

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/toast.py`
- Create: `files/usr/lib/adwaita-lite/settings/css/style.css`

- [ ] **Step 1: Create ToastWidget**

Create `files/usr/lib/adwaita-lite/settings/toast.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk


class ToastWidget(Gtk.Revealer):
    """Adwaita-style toast notification. Slides up from the bottom of the overlay."""

    def __init__(self) -> None:
        super().__init__()
        self.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.set_transition_duration(200)
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(16)

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._box.add_css_class("toast")

        self._label = Gtk.Label()
        self._label.set_wrap(True)
        self._label.set_max_width_chars(50)
        self._box.append(self._label)

        dismiss = Gtk.Button.new_from_icon_name("window-close-symbolic")
        dismiss.add_css_class("flat")
        dismiss.connect("clicked", lambda _: self.dismiss())
        self._box.append(dismiss)

        self.set_child(self._box)
        self._timer_id: int | None = None

    def show_toast(self, message: str, is_error: bool = False, timeout: int = 3) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
        self._label.set_text(message)
        if is_error:
            self._box.add_css_class("toast-error")
        else:
            self._box.remove_css_class("toast-error")
        self.set_reveal_child(True)
        self._timer_id = GLib.timeout_add_seconds(timeout, self._auto_dismiss)

    def dismiss(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None
        self.set_reveal_child(False)

    def _auto_dismiss(self) -> int:
        self._timer_id = None
        self.set_reveal_child(False)
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 2: Extract CSS from the existing monolith**

Create `files/usr/lib/adwaita-lite/settings/css/style.css`:

```css
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
.toggle-card:checked {
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
.accent-blue { background-color: #3584e4; }
.accent-teal { background-color: #2190a4; }
.accent-green { background-color: #3a944a; }
.accent-yellow { background-color: #c88800; }
.accent-orange { background-color: #ed5b00; }
.accent-red { background-color: #e62d42; }
.accent-pink { background-color: #d56199; }
.accent-purple { background-color: #9141ac; }
.accent-slate { background-color: #6f8396; }
.toast {
    background-color: @headerbar_bg_color;
    color: @theme_fg_color;
    border-radius: 8px;
    padding: 8px 16px;
    box-shadow: 0 2px 8px alpha(black, 0.15);
    border: 1px solid alpha(@borders, 0.3);
}
.toast-error {
    background-color: #c01c28;
    color: white;
    border-color: #c01c28;
}
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/toast.py files/usr/lib/adwaita-lite/settings/css/style.css
git commit -m "feat: implement ToastWidget and extract CSS to style.css"
```

---

### Task 6: Implement Window

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/window.py`

- [ ] **Step 1: Create SettingsWindow with sidebar, stack, search, and toast overlay**

Create `files/usr/lib/adwaita-lite/settings/window.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from .events import EventBus
from .settings_store import SettingsStore
from .toast import ToastWidget


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, store: SettingsStore, event_bus: EventBus) -> None:
        super().__init__(application=app)
        self.set_title("Adwaita-Lite Settings")
        self.set_default_size(900, 600)
        self.set_size_request(700, 500)

        self._store = store
        self._event_bus = event_bus
        self._page_names: list[str] = []
        self._pages: list = []

        # Toast overlay wraps everything
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        self._toast = ToastWidget()
        overlay.add_overlay(self._toast)
        store.set_toast_callback(self._toast.show_toast)

        # Main paned layout
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(220)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        overlay.set_child(paned)

        # --- Sidebar ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_size_request(220, -1)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text("Search settings...")
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._search_entry.connect("search-changed", self._on_search_changed)
        sidebar_box.append(self._search_bar)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_vexpand(True)

        self._sidebar = Gtk.ListBox()
        self._sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar.add_css_class("sidebar")
        self._sidebar.set_margin_top(8)
        self._sidebar.set_margin_bottom(8)
        sidebar_scroll.set_child(self._sidebar)
        sidebar_box.append(sidebar_scroll)
        paned.set_start_child(sidebar_box)

        # --- Content stack ---
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        self._content_scroll = Gtk.ScrolledWindow()
        self._content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._content_scroll.set_child(self._stack)
        self._content_scroll.set_hexpand(True)
        self._content_scroll.set_vexpand(True)
        paned.set_end_child(self._content_scroll)

        # Build pages from registry
        self._build_pages()

        self._sidebar.connect("row-selected", self._on_row_selected)
        first = self._sidebar.get_row_at_index(0)
        if first is not None:
            self._sidebar.select_row(first)

    def _build_pages(self) -> None:
        from .pages import ALL_PAGES

        for icon_name, label, page_cls in ALL_PAGES:
            row = self._build_sidebar_row(icon_name, label)
            self._sidebar.append(row)

            page = page_cls(self._store, self._event_bus)
            widget = page.build()
            self._stack.add_named(widget, label)
            self._page_names.append(label)
            self._pages.append(page)

    @staticmethod
    def _build_sidebar_row(icon_name: str, label: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16)
        icon.add_css_class("category-icon")
        box.append(icon)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.add_css_class("category-label")
        lbl.set_hexpand(True)
        box.append(lbl)
        row.set_child(box)
        return row

    def _on_row_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if row is None:
            return
        idx = row.get_index()
        if 0 <= idx < len(self._page_names):
            self._stack.set_visible_child_name(self._page_names[idx])
            adj = self._content_scroll.get_vadjustment()
            if adj:
                adj.set_value(0)

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text().lower().strip()
        if not text:
            self._sidebar.set_filter_func(None)
            return

        matching: set[int] = set()
        for i, page in enumerate(self._pages):
            for group, setting in page.search_keywords:
                if text in group.lower() or text in setting.lower():
                    matching.add(i)
                    break

        self._sidebar.set_filter_func(lambda row: row.get_index() in matching)

    def toggle_search(self) -> None:
        active = self._search_bar.get_search_mode()
        self._search_bar.set_search_mode(not active)
        if not active:
            self._search_entry.grab_focus()
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/window.py
git commit -m "feat: implement SettingsWindow with sidebar, search, and toast overlay"
```

---

### Task 7: Implement App Entry Point and Thin Launcher

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/app.py`
- Modify: `files/usr/bin/adwaita-lite-settings`

- [ ] **Step 1: Create app.py**

Create `files/usr/lib/adwaita-lite/settings/app.py`:

```python
from pathlib import Path

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from .events import EventBus
from .settings_store import SettingsStore
from .window import SettingsWindow

APP_ID = "org.adwaitabluelite.Settings"
CSS_PATH = Path(__file__).parent / "css" / "style.css"


class SettingsApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self._store = SettingsStore()
        self._event_bus = EventBus()

    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_path(str(CSS_PATH))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        win = SettingsWindow(self, self._store, self._event_bus)
        win.present()

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        self.set_accels_for_action("win.search", ["<Control>f"])


def main() -> None:
    app = SettingsApp()
    app.run([])
```

- [ ] **Step 2: Replace the monolith with a thin launcher**

Replace the entire contents of `files/usr/bin/adwaita-lite-settings` with:

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, "/usr/lib/adwaita-lite")
from settings.app import main
main()
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/app.py files/usr/bin/adwaita-lite-settings
git commit -m "feat: create app entry point and replace monolith with thin launcher"
```

---

### Task 8: Implement NetworkManager D-Bus Helper

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`

This task uses the same `NM.Client` GI bindings pattern as the setup wizard (`files/usr/bin/adwaita-lite-setup-wizard`). Reference it for consistency.

- [ ] **Step 1: Create dbus_helpers.py with NetworkManagerHelper**

Create `files/usr/lib/adwaita-lite/settings/dbus_helpers.py`:

```python
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field

import gi

gi.require_version("NM", "1.0")
from gi.repository import Gio, GLib, NM

from .events import EventBus


# ---------------------------------------------------------------------------
#  Data types
# ---------------------------------------------------------------------------

@dataclass
class AccessPointInfo:
    path: str
    ssid: str
    strength: int
    secured: bool
    active: bool


@dataclass
class ConnectionInfo:
    name: str
    type: str
    ip_address: str
    gateway: str
    dns: str


@dataclass
class BluetoothDevice:
    path: str
    name: str
    paired: bool
    connected: bool
    icon: str
    address: str


# ---------------------------------------------------------------------------
#  NetworkManager helper
# ---------------------------------------------------------------------------

class NetworkManagerHelper:
    """Wraps NM.Client. Publishes events: nm-ready, network-changed,
    network-connect-success, network-connect-error."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._client: NM.Client | None = None
        self._wifi_device: NM.DeviceWifi | None = None
        NM.Client.new_async(None, self._on_client_ready)

    def _on_client_ready(self, _source: object, result: Gio.AsyncResult) -> None:
        try:
            self._client = NM.Client.new_finish(result)
        except Exception:
            return
        for dev in self._client.get_devices():
            if isinstance(dev, NM.DeviceWifi):
                self._wifi_device = dev
                break
        self._client.connect("notify::wireless-enabled", lambda *_: self._publish("network-changed"))
        if self._wifi_device is not None:
            self._wifi_device.connect("access-point-added", lambda *_: self._publish("network-changed"))
            self._wifi_device.connect("access-point-removed", lambda *_: self._publish("network-changed"))
        self._client.connect("active-connection-added", lambda *_: self._publish("network-changed"))
        self._client.connect("active-connection-removed", lambda *_: self._publish("network-changed"))
        self._publish("nm-ready")

    def _publish(self, event: str, data=None) -> None:
        self._event_bus.publish(event, data)

    # -- Queries --

    @property
    def ready(self) -> bool:
        return self._client is not None

    def is_wifi_enabled(self) -> bool:
        return self._client.wireless_get_enabled() if self._client else False

    def set_wifi_enabled(self, enabled: bool) -> None:
        if self._client:
            self._client.wireless_set_enabled(enabled)

    def get_access_points(self) -> list[AccessPointInfo]:
        if self._wifi_device is None:
            return []
        aps = self._wifi_device.get_access_points()
        seen: dict[str, NM.AccessPoint] = {}
        for ap in aps:
            ssid_bytes = ap.get_ssid()
            if ssid_bytes is None:
                continue
            ssid = ssid_bytes.get_data().decode("utf-8", errors="replace")
            if not ssid:
                continue
            if ssid not in seen or ap.get_strength() > seen[ssid].get_strength():
                seen[ssid] = ap
        active_ssid = self._get_active_wifi_ssid()
        result: list[AccessPointInfo] = []
        for ssid, ap in sorted(seen.items(), key=lambda x: -x[1].get_strength()):
            flags = ap.get_wpa_flags() | ap.get_rsn_flags()
            result.append(AccessPointInfo(
                path=ap.get_path(),
                ssid=ssid,
                strength=ap.get_strength(),
                secured=flags != 0,
                active=ssid == active_ssid,
            ))
        return result

    def request_scan(self) -> None:
        if self._wifi_device is not None:
            self._wifi_device.request_scan_async(None, self._on_scan_done)

    def _on_scan_done(self, device: NM.DeviceWifi, result: Gio.AsyncResult) -> None:
        try:
            device.request_scan_finish(result)
        except Exception:
            pass
        self._publish("network-changed")

    def get_active_connection_info(self) -> ConnectionInfo | None:
        if self._client is None:
            return None
        for ac in self._client.get_active_connections():
            ip4 = ac.get_ip4_config()
            if ip4 is None:
                continue
            addresses = ip4.get_addresses()
            nameservers = ip4.get_nameservers()
            return ConnectionInfo(
                name=ac.get_id(),
                type=ac.get_connection_type(),
                ip_address=addresses[0].get_address() if addresses else "N/A",
                gateway=ip4.get_gateway() or "N/A",
                dns=", ".join(str(ns) for ns in nameservers) if nameservers else "N/A",
            )
        return None

    def has_wired(self) -> bool:
        if self._client is None:
            return False
        return any(isinstance(d, NM.DeviceEthernet) for d in self._client.get_devices())

    def is_wired_connected(self) -> bool:
        if self._client is None:
            return False
        return any(
            ac.get_connection_type() == "802-3-ethernet"
            for ac in self._client.get_active_connections()
        )

    # -- Actions --

    def connect_wifi(self, ssid: str, password: str | None, hidden: bool = False) -> None:
        if self._client is None or self._wifi_device is None:
            return
        conn = NM.SimpleConnection.new()
        s_con = NM.SettingConnection.new()
        s_con.set_property("type", "802-11-wireless")
        s_con.set_property("id", ssid)
        conn.add_setting(s_con)
        s_wifi = NM.SettingWireless.new()
        s_wifi.set_property("ssid", GLib.Bytes.new(ssid.encode("utf-8")))
        if hidden:
            s_wifi.set_property("hidden", True)
        conn.add_setting(s_wifi)
        if password:
            s_sec = NM.SettingWirelessSecurity.new()
            s_sec.set_property("key-mgmt", "wpa-psk")
            s_sec.set_property("psk", password)
            conn.add_setting(s_sec)
        self._client.add_and_activate_connection_async(
            conn, self._wifi_device, None, None, self._on_connect_done,
        )

    def _on_connect_done(self, client: NM.Client, result: Gio.AsyncResult) -> None:
        try:
            client.add_and_activate_connection_finish(result)
            self._publish("network-connect-success")
        except Exception as exc:
            err = str(exc)
            if "802-11-wireless-security.psk" in err:
                self._publish("network-connect-error", "Wrong password.")
            else:
                self._publish("network-connect-error", f"Connection failed: {err}")

    def disconnect_wifi(self) -> None:
        if self._client is None:
            return
        for ac in self._client.get_active_connections():
            if ac.get_connection_type() == "802-11-wireless":
                self._client.deactivate_connection_async(ac, None, None)
                break

    def forget_connection(self, ssid: str) -> None:
        if self._client is None:
            return
        for conn in self._client.get_connections():
            s_con = conn.get_setting_connection()
            if s_con and s_con.get_id() == ssid:
                conn.delete_async(None, None)
                break

    def _get_active_wifi_ssid(self) -> str | None:
        if self._client is None:
            return None
        for ac in self._client.get_active_connections():
            if ac.get_connection_type() == "802-11-wireless":
                return ac.get_id()
        return None


# ---------------------------------------------------------------------------
#  BlueZ helper
# ---------------------------------------------------------------------------

class BlueZHelper:
    """Wraps BlueZ D-Bus API via Gio.DBusProxy. Publishes event: bluetooth-changed."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        self._adapter_path: str | None = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error:
            return
        self._find_adapter()
        self._subscribe_signals()

    def _find_adapter(self) -> None:
        try:
            result = self._bus.call_sync(
                "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                None, GLib.VariantType("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            objects = result.unpack()[0]
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    self._adapter_path = path
                    break
        except GLib.Error:
            pass

    @property
    def available(self) -> bool:
        return self._adapter_path is not None

    def is_powered(self) -> bool:
        if not self.available:
            return False
        try:
            result = self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.bluez.Adapter1", "Powered")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            return result.unpack()[0]
        except GLib.Error:
            return False

    def set_powered(self, enabled: bool) -> None:
        if not self.available:
            return
        try:
            self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.freedesktop.DBus.Properties", "Set",
                GLib.Variant("(ssv)", ("org.bluez.Adapter1", "Powered", GLib.Variant("b", enabled))),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass

    def get_devices(self) -> list[BluetoothDevice]:
        if self._bus is None:
            return []
        try:
            result = self._bus.call_sync(
                "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                None, GLib.VariantType("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE, -1, None,
            )
            objects = result.unpack()[0]
        except GLib.Error:
            return []
        devices: list[BluetoothDevice] = []
        for path, interfaces in objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            props = interfaces["org.bluez.Device1"]
            devices.append(BluetoothDevice(
                path=path,
                name=props.get("Name", props.get("Alias", props.get("Address", "Unknown"))),
                paired=props.get("Paired", False),
                connected=props.get("Connected", False),
                icon=props.get("Icon", "bluetooth-symbolic"),
                address=props.get("Address", ""),
            ))
        return devices

    def start_discovery(self) -> None:
        if not self.available:
            return
        try:
            self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.bluez.Adapter1", "StartDiscovery",
                None, None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass

    def stop_discovery(self) -> None:
        if not self.available:
            return
        try:
            self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.bluez.Adapter1", "StopDiscovery",
                None, None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass

    def pair_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        self._bus.call(
            "org.bluez", device_path,
            "org.bluez.Device1", "Pair",
            None, None, Gio.DBusCallFlags.NONE, 60000, None,
            self._on_pair_done,
        )

    def _on_pair_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
            self._event_bus.publish("bluetooth-pair-success")
        except GLib.Error as e:
            self._event_bus.publish("bluetooth-pair-error", str(e))

    def connect_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        self._bus.call(
            "org.bluez", device_path,
            "org.bluez.Device1", "Connect",
            None, None, Gio.DBusCallFlags.NONE, 30000, None,
            self._on_generic_done,
        )

    def disconnect_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        try:
            self._bus.call_sync(
                "org.bluez", device_path,
                "org.bluez.Device1", "Disconnect",
                None, None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass
        self._event_bus.publish("bluetooth-changed")

    def remove_device(self, device_path: str) -> None:
        if not self.available:
            return
        try:
            self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.bluez.Adapter1", "RemoveDevice",
                GLib.Variant("(o)", (device_path,)),
                None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass
        self._event_bus.publish("bluetooth-changed")

    def _on_generic_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error:
            pass
        self._event_bus.publish("bluetooth-changed")

    def _subscribe_signals(self) -> None:
        if self._bus is None:
            return
        self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.ObjectManager",
            "InterfacesAdded", "/", None,
            Gio.DBusSignalFlags.NONE, self._on_changed, None,
        )
        self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.ObjectManager",
            "InterfacesRemoved", "/", None,
            Gio.DBusSignalFlags.NONE, self._on_changed, None,
        )
        self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.Properties",
            "PropertiesChanged", None, None,
            Gio.DBusSignalFlags.NONE, self._on_props_changed, None,
        )

    def _on_changed(self, *_args) -> None:
        self._event_bus.publish("bluetooth-changed")

    def _on_props_changed(self, _conn, _sender, _path, _iface, _signal, params, _data) -> None:
        iface_name = params.unpack()[0]
        if iface_name in ("org.bluez.Adapter1", "org.bluez.Device1"):
            self._event_bus.publish("bluetooth-changed")
```

- [ ] **Step 2: Verify import**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.dbus_helpers import NetworkManagerHelper, BlueZHelper
print('D-Bus helpers imported OK')
"
```

Expected: `D-Bus helpers imported OK`

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/dbus_helpers.py
git commit -m "feat: implement NetworkManager and BlueZ D-Bus helpers with event publishing"
```

---

### Task 9: Migrate Appearance Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/appearance.py`

Reference: `files/usr/bin/adwaita-lite-settings` lines 183–297 (original `AppearancePage`).

Migration pattern (same for all pages):
1. Inherit `BasePage` instead of standalone class
2. Replace `self.win.settings.get(...)` → `self.store.get(...)`
3. Replace `self.win.save_and_apply(...)` → `self.store.save_and_apply(...)`
4. Replace `self.win._make_*` → `self.make_*`
5. Move page-specific constants into the page file
6. Add `search_keywords` property
7. Use `self.make_page_box()` for the outer container

- [ ] **Step 1: Create appearance.py**

Create `files/usr/lib/adwaita-lite/settings/pages/appearance.py`:

```python
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from ..base import BasePage

BACKGROUNDS_ROOT = Path("/usr/share/backgrounds")
WALLPAPER_EXTS = frozenset({".svg", ".jpg", ".jpeg", ".png", ".webp"})
ACCENT_COLORS = [
    ("blue", "#3584e4"), ("teal", "#2190a4"), ("green", "#3a944a"),
    ("yellow", "#c88800"), ("orange", "#ed5b00"), ("red", "#e62d42"),
    ("pink", "#d56199"), ("purple", "#9141ac"), ("slate", "#6f8396"),
]


class AppearancePage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Theme", "Light"), ("Theme", "Dark"),
            ("Accent color", "Color"),
            ("Wallpaper", "Background"),
        ]

    def build(self):
        page = self.make_page_box()

        # -- Theme group --
        page.append(self.make_group_label("Theme"))
        page.append(self.make_toggle_cards(
            [("light", "Light"), ("dark", "Dark")],
            self.store.get("theme", "light"),
            lambda v: self.store.save_and_apply("theme", v),
        ))

        # -- Accent color group --
        page.append(self.make_group_label("Accent color"))
        accent_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        accent_buttons: list[Gtk.ToggleButton] = []
        current_accent = self.store.get("accent", "blue")

        def _on_accent_toggled(btn, name):
            if not btn.get_active():
                return
            for other in accent_buttons:
                if other is not btn and other.get_active():
                    other.set_active(False)
            self.store.save_and_apply("accent", name)

        for name, _hex in ACCENT_COLORS:
            btn = Gtk.ToggleButton()
            btn.add_css_class("accent-circle")
            btn.add_css_class(f"accent-{name}")
            btn.set_active(name == current_accent)
            btn.connect("toggled", _on_accent_toggled, name)
            accent_buttons.append(btn)
            accent_box.append(btn)
        page.append(accent_box)

        # -- Wallpaper group --
        page.append(self.make_group_label("Wallpaper"))
        flow = Gtk.FlowBox()
        flow.set_max_children_per_line(4)
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_column_spacing(8)
        flow.set_row_spacing(8)
        wallpaper_buttons: list[tuple[Gtk.ToggleButton, str]] = []
        current_wallpaper = self.store.get("wallpaper", "")

        def _on_wallpaper_toggled(btn, path):
            if not btn.get_active():
                return
            for other_btn, _ in wallpaper_buttons:
                if other_btn is not btn and other_btn.get_active():
                    other_btn.set_active(False)
            self.store.save_and_apply("wallpaper", path)

        wallpaper_paths: list[Path] = []
        if BACKGROUNDS_ROOT.is_dir():
            for p in sorted(BACKGROUNDS_ROOT.rglob("*")):
                if p.is_file() and p.suffix.lower() in WALLPAPER_EXTS:
                    wallpaper_paths.append(p)

        for wp_path in wallpaper_paths:
            pic = Gtk.Picture.new_for_filename(str(wp_path))
            pic.set_content_fit(Gtk.ContentFit.COVER)
            pic.set_size_request(120, 80)
            btn = Gtk.ToggleButton()
            btn.add_css_class("toggle-card")
            btn.set_child(pic)
            btn.set_active(str(wp_path) == current_wallpaper)
            btn.connect("toggled", _on_wallpaper_toggled, str(wp_path))
            wallpaper_buttons.append((btn, str(wp_path)))
            flow.append(btn)

        def _on_custom_clicked(_btn):
            dialog = Gtk.FileDialog()
            dialog.set_title("Choose Wallpaper")
            image_filter = Gtk.FileFilter()
            image_filter.set_name("Images")
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.svg"):
                image_filter.add_pattern(ext)
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(image_filter)
            dialog.set_filters(filters)

            def _on_open_finish(d, result):
                try:
                    file = d.open_finish(result)
                    if file is not None:
                        path = file.get_path()
                        self.store.save_and_apply("wallpaper", path)
                        for other_btn, _ in wallpaper_buttons:
                            if other_btn.get_active():
                                other_btn.set_active(False)
                except Exception:
                    pass

            dialog.open(self._get_window(page), None, _on_open_finish)

        custom_btn = Gtk.Button(label="Custom...")
        custom_btn.connect("clicked", _on_custom_clicked)
        flow.append(custom_btn)
        page.append(flow)
        return page

    @staticmethod
    def _get_window(widget):
        root = widget.get_root()
        return root if isinstance(root, Gtk.Window) else None
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/appearance.py
git commit -m "feat: migrate AppearancePage to new package structure"
```

---

### Task 10: Migrate Display Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/display.py`

Reference: `files/usr/bin/adwaita-lite-settings` lines 300–436.

- [ ] **Step 1: Create display.py**

Create `files/usr/lib/adwaita-lite/settings/pages/display.py`:

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..base import BasePage

SCALE_OPTIONS = ["75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%"]
SCALE_VALUES = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]


class DisplayPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._scale_buttons: list[Gtk.ToggleButton] = []
        self._revert_timer_id: int | None = None
        self._revert_seconds: int = 15

    @property
    def search_keywords(self):
        return [("Display Scale", "Scale"), ("Display Scale", "Resolution")]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Display Scale"))

        options = [(str(v), label) for v, label in zip(SCALE_VALUES, SCALE_OPTIONS)]
        active = str(self.store.get("scale", 1.0))
        cards_box = self.make_toggle_cards(
            options, active, lambda v: self._apply_scale(float(v)),
        )
        child = cards_box.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ToggleButton):
                self._scale_buttons.append(child)
            child = child.get_next_sibling()
        page.append(cards_box)
        return page

    def _apply_scale(self, new_scale):
        old_scale = self.store.get("scale", 1.0)
        self._set_scale(new_scale)
        self._show_revert_dialog(old_scale, new_scale)

    def _set_scale(self, scale):
        try:
            result = subprocess.run(["wlr-randr"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if line and not line[0].isspace():
                    output_name = line.split()[0]
                    subprocess.run(
                        ["wlr-randr", "--output", output_name, "--scale", str(scale)],
                        check=False,
                    )
        except FileNotFoundError:
            pass

    def _show_revert_dialog(self, old_scale, new_scale):
        dialog = Gtk.Window(title="Confirm Scale", modal=True)
        dialog.set_default_size(400, 150)
        dialog.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        self._revert_seconds = 15
        label = Gtk.Label(label=f"Keep this display scale?\nReverting in {self._revert_seconds}s...")
        label.set_wrap(True)
        box.append(label)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        revert_btn = Gtk.Button(label="Revert")
        revert_btn.connect("clicked", lambda _: self._revert(dialog, old_scale))
        btn_box.append(revert_btn)
        keep_btn = Gtk.Button(label="Keep")
        keep_btn.add_css_class("suggested-action")
        keep_btn.connect("clicked", lambda _: self._keep(dialog, new_scale))
        btn_box.append(keep_btn)
        box.append(btn_box)
        dialog.set_child(box)
        self._revert_timer_id = GLib.timeout_add_seconds(
            1, self._tick_revert, label, dialog, old_scale,
        )
        dialog.connect("close-request", lambda _: self._revert(dialog, old_scale) or True)
        dialog.present()

    def _tick_revert(self, label, dialog, old_scale):
        self._revert_seconds -= 1
        if self._revert_seconds <= 0:
            self._revert(dialog, old_scale)
            return GLib.SOURCE_REMOVE
        label.set_text(f"Keep this display scale?\nReverting in {self._revert_seconds}s...")
        return GLib.SOURCE_CONTINUE

    def _revert(self, dialog, old_scale):
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        self._set_scale(old_scale)
        self._sync_buttons(old_scale)
        dialog.destroy()

    def _keep(self, dialog, new_scale):
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        self.store.save_and_apply("scale", new_scale)
        self._sync_buttons(new_scale)
        dialog.destroy()

    def _sync_buttons(self, scale):
        scale_str = str(scale)
        value_to_label = {str(v): lbl for v, lbl in zip(SCALE_VALUES, SCALE_OPTIONS)}
        target_label = value_to_label.get(scale_str, "")
        for btn in self._scale_buttons:
            active = btn.get_label() == target_label
            if btn.get_active() != active:
                btn.set_active(active)
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/display.py
git commit -m "feat: migrate DisplayPage to new package structure"
```

---

### Task 11: Migrate Panel Page

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/panel.py`

Reference: `files/usr/bin/adwaita-lite-settings` lines 438–703. This is the most complex migration due to module layout and pinned apps state.

- [ ] **Step 1: Create panel.py**

Create `files/usr/lib/adwaita-lite/settings/pages/panel.py`:

```python
import copy

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage

MODULE_NAMES = {
    "custom/launcher": "Apps", "wlr/taskbar": "Window list",
    "pulseaudio": "Volume", "backlight": "Brightness", "battery": "Battery",
    "clock": "Clock", "custom/power": "Power", "tray": "System tray",
}
DEFAULT_LAYOUT = {
    "start": ["custom/launcher"],
    "center": ["wlr/taskbar"],
    "end": ["pulseaudio", "backlight", "battery", "clock", "custom/power", "tray"],
}
HORIZONTAL_LABELS = {"start": "Left", "center": "Center", "end": "Right"}
VERTICAL_LABELS = {"start": "Top", "center": "Center", "end": "Bottom"}
SECTION_ORDER = ["start", "center", "end"]


class PanelPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._layout_data: dict = {}
        self._section_boxes: dict = {}
        self._pinned_data: list = []
        self._pinned_list: Gtk.ListBox | None = None

    @property
    def search_keywords(self):
        return [
            ("Position", "Panel"), ("Density", "Compact"),
            ("Module Layout", "Modules"), ("Pinned Apps", "Pinned"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Position"))
        page.append(self.make_toggle_cards(
            [("bottom", "Bottom"), ("top", "Top"), ("left", "Left"), ("right", "Right")],
            self.store.get("edge", "bottom"),
            lambda v: self.store.save_and_apply("edge", v),
        ))
        page.append(self.make_group_label("Density"))
        page.append(self.make_toggle_cards(
            [("normal", "Normal"), ("compact", "Compact")],
            self.store.get("density", "normal"),
            lambda v: self.store.save_and_apply("density", v),
        ))
        page.append(self.make_group_label("Module Layout"))
        page.append(self._build_module_layout())
        page.append(self.make_group_label("Pinned Apps"))
        page.append(self._build_pinned_apps())
        reset_btn = Gtk.Button(label="Reset layout to defaults")
        reset_btn.set_halign(Gtk.Align.START)
        reset_btn.connect("clicked", lambda _: self._reset_layout())
        page.append(reset_btn)
        return page

    # -- Module layout --

    def _build_module_layout(self):
        self._layout_data = self._load_layout()
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        self._section_boxes = {}
        edge = self.store.get("edge", "bottom")
        labels = HORIZONTAL_LABELS if edge in ("top", "bottom") else VERTICAL_LABELS
        for section in SECTION_ORDER:
            section_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            section_box.set_hexpand(True)
            header = Gtk.Label(label=labels[section], xalign=0)
            header.add_css_class("group-title")
            section_box.append(header)
            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            self._section_boxes[section] = listbox
            section_box.append(listbox)
            container.append(section_box)
        self._refresh_module_lists()
        return container

    def _load_layout(self):
        saved = self.store.get("layout")
        if isinstance(saved, dict) and all(k in saved for k in SECTION_ORDER):
            return {k: list(saved[k]) for k in SECTION_ORDER}
        return copy.deepcopy(DEFAULT_LAYOUT)

    def _refresh_module_lists(self):
        for section in SECTION_ORDER:
            listbox = self._section_boxes[section]
            while (child := listbox.get_row_at_index(0)) is not None:
                listbox.remove(child)
            for mod_key in self._layout_data.get(section, []):
                listbox.append(self._build_module_row(mod_key, section))

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
        sec_idx = SECTION_ORDER.index(section)
        if sec_idx > 0:
            btn = Gtk.Button(label="\u25C2")
            btn.set_tooltip_text(f"Move to {SECTION_ORDER[sec_idx - 1]}")
            btn.connect("clicked", lambda _, k=mod_key, s=section: self._move_module(
                k, s, SECTION_ORDER[SECTION_ORDER.index(s) - 1]))
            box.append(btn)
        if sec_idx < len(SECTION_ORDER) - 1:
            btn = Gtk.Button(label="\u25B8")
            btn.set_tooltip_text(f"Move to {SECTION_ORDER[sec_idx + 1]}")
            btn.connect("clicked", lambda _, k=mod_key, s=section: self._move_module(
                k, s, SECTION_ORDER[SECTION_ORDER.index(s) + 1]))
            box.append(btn)
        row.set_child(box)
        return row

    def _move_module(self, mod_key, from_section, to_section):
        if mod_key in self._layout_data.get(from_section, []):
            self._layout_data[from_section].remove(mod_key)
        self._layout_data.setdefault(to_section, []).append(mod_key)
        self._refresh_module_lists()
        self.store.save_and_apply("layout", self._layout_data)

    # -- Pinned apps --

    def _build_pinned_apps(self):
        self._pinned_data = list(self.store.get("pinned", []))
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._pinned_list = Gtk.ListBox()
        self._pinned_list.set_selection_mode(Gtk.SelectionMode.NONE)
        vbox.append(self._pinned_list)
        add_btn = Gtk.Button(label="Add pinned app")
        add_btn.set_halign(Gtk.Align.START)
        add_btn.set_margin_top(8)
        add_btn.connect("clicked", lambda _: self._show_add_pinned_dialog())
        vbox.append(add_btn)
        self._refresh_pinned_list()
        return vbox

    def _refresh_pinned_list(self):
        if self._pinned_list is None:
            return
        while (child := self._pinned_list.get_row_at_index(0)) is not None:
            self._pinned_list.remove(child)
        for idx, app in enumerate(self._pinned_data):
            self._pinned_list.append(self._build_pinned_row(app, idx))

    def _build_pinned_row(self, app, idx):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(4)
        box.set_margin_end(4)
        icon = Gtk.Image.new_from_icon_name(app.get("icon", "application-x-executable-symbolic"))
        icon.set_pixel_size(20)
        box.append(icon)
        name_label = Gtk.Label(label=app.get("name", app.get("command", "Unknown")), xalign=0)
        name_label.set_hexpand(True)
        box.append(name_label)
        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", lambda _, i=idx: self._remove_pinned(i))
        box.append(remove_btn)
        row.set_child(box)
        return row

    def _remove_pinned(self, idx):
        if 0 <= idx < len(self._pinned_data):
            self._pinned_data.pop(idx)
            self._refresh_pinned_list()
            self.store.save_and_apply("pinned", self._pinned_data)

    def _show_add_pinned_dialog(self):
        dialog = Gtk.Window(title="Add Pinned App", modal=True)
        dialog.set_default_size(360, 220)
        dialog.set_resizable(False)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        outer.set_margin_top(24)
        outer.set_margin_bottom(24)
        outer.set_margin_start(24)
        outer.set_margin_end(24)
        grid = Gtk.Grid()
        grid.set_row_spacing(8)
        grid.set_column_spacing(12)

        def _entry(row_idx, label_text, placeholder):
            lbl = Gtk.Label(label=label_text, xalign=1)
            entry = Gtk.Entry()
            entry.set_placeholder_text(placeholder)
            entry.set_hexpand(True)
            grid.attach(lbl, 0, row_idx, 1, 1)
            grid.attach(entry, 1, row_idx, 1, 1)
            return entry

        name_entry = _entry(0, "Name:", "e.g. Files")
        cmd_entry = _entry(1, "Command:", "e.g. nautilus")
        icon_entry = _entry(2, "Icon:", "e.g. folder-symbolic")
        outer.append(grid)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda _: dialog.destroy())
        btn_box.append(cancel_btn)
        add_btn = Gtk.Button(label="Add")
        add_btn.add_css_class("suggested-action")

        def _on_add(_btn):
            name = name_entry.get_text().strip()
            cmd = cmd_entry.get_text().strip()
            icon_name = icon_entry.get_text().strip() or "application-x-executable-symbolic"
            if not name or not cmd:
                return
            self._pinned_data.append({"name": name, "command": cmd, "icon": icon_name})
            self._refresh_pinned_list()
            self.store.save_and_apply("pinned", self._pinned_data)
            dialog.destroy()

        add_btn.connect("clicked", _on_add)
        btn_box.append(add_btn)
        outer.append(btn_box)
        dialog.set_child(outer)
        dialog.present()

    def _reset_layout(self):
        self._layout_data = copy.deepcopy(DEFAULT_LAYOUT)
        self._refresh_module_lists()
        self.store.save_and_apply("layout", self._layout_data)
        self._pinned_data = list(self.store.get("pinned", []))
        self._refresh_pinned_list()
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/panel.py
git commit -m "feat: migrate PanelPage to new package structure"
```

---

### Task 12: Migrate Mouse/Touchpad, Keyboard, and Sound Pages

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py`
- Create: `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`
- Create: `files/usr/lib/adwaita-lite/settings/pages/sound.py`

- [ ] **Step 1: Create mouse_touchpad.py**

Create `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage


class MouseTouchpadPage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Touchpad", "Tap to click"), ("Touchpad", "Natural scrolling"),
            ("Touchpad", "Pointer speed"), ("Touchpad", "Scroll speed"),
            ("Mouse", "Natural scrolling"), ("Mouse", "Pointer speed"),
            ("Mouse", "Acceleration"),
        ]

    def build(self):
        page = self.make_page_box()

        # -- Touchpad --
        page.append(self.make_group_label("Touchpad"))

        tp_tap = Gtk.Switch()
        tp_tap.set_active(self.store.get("touchpad_tap_to_click", True))
        tp_tap.connect("state-set", lambda _, s: self.store.save_and_apply("touchpad_tap_to_click", s) or False)
        page.append(self.make_setting_row("Tap to click", "", tp_tap))

        tp_natural = Gtk.Switch()
        tp_natural.set_active(self.store.get("touchpad_natural_scroll", False))
        tp_natural.connect("state-set", lambda _, s: self.store.save_and_apply("touchpad_natural_scroll", s) or False)
        page.append(self.make_setting_row("Natural scrolling", "Content moves with your fingers", tp_natural))

        tp_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        tp_speed.set_value(self.store.get("touchpad_pointer_speed", 0.0))
        tp_speed.set_size_request(200, -1)
        tp_speed.set_draw_value(False)
        tp_speed.connect("value-changed", lambda s: self.store.save_debounced(
            "touchpad_pointer_speed", round(s.get_value(), 1)))
        page.append(self.make_setting_row("Pointer speed", "", tp_speed))

        tp_scroll = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1.0, 10.0, 1.0)
        tp_scroll.set_value(self.store.get("touchpad_scroll_speed", 5))
        tp_scroll.set_size_request(200, -1)
        tp_scroll.set_draw_value(False)
        tp_scroll.connect("value-changed", lambda s: self.store.save_debounced(
            "touchpad_scroll_speed", int(s.get_value())))
        page.append(self.make_setting_row("Scroll speed", "", tp_scroll))

        # -- Mouse --
        page.append(self.make_group_label("Mouse"))

        mouse_natural = Gtk.Switch()
        mouse_natural.set_active(self.store.get("mouse_natural_scroll", False))
        mouse_natural.connect("state-set", lambda _, s: self.store.save_and_apply("mouse_natural_scroll", s) or False)
        page.append(self.make_setting_row("Natural scrolling", "", mouse_natural))

        mouse_speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        mouse_speed.set_value(self.store.get("mouse_pointer_speed", 0.0))
        mouse_speed.set_size_request(200, -1)
        mouse_speed.set_draw_value(False)
        mouse_speed.connect("value-changed", lambda s: self.store.save_debounced(
            "mouse_pointer_speed", round(s.get_value(), 1)))
        page.append(self.make_setting_row("Pointer speed", "", mouse_speed))

        page.append(self.make_setting_row("Acceleration", "", self.make_toggle_cards(
            [("adaptive", "Adaptive"), ("flat", "Flat")],
            self.store.get("mouse_accel_profile", "adaptive"),
            lambda v: self.store.save_and_apply("mouse_accel_profile", v),
        )))
        return page
```

- [ ] **Step 2: Create keyboard.py**

Create `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`:

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage

LAYOUT_NAMES = {
    "us": "English (US)", "gb": "English (UK)", "de": "German",
    "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "ru": "Russian", "jp": "Japanese", "kr": "Korean", "cn": "Chinese",
    "ar": "Arabic", "br": "Portuguese (Brazil)", "ca": "Canadian",
    "dk": "Danish", "fi": "Finnish", "nl": "Dutch", "no": "Norwegian",
    "pl": "Polish", "se": "Swedish", "ch": "Swiss", "tr": "Turkish",
    "ua": "Ukrainian", "in": "Indian", "il": "Hebrew", "th": "Thai",
    "cz": "Czech", "hu": "Hungarian", "ro": "Romanian", "sk": "Slovak",
    "hr": "Croatian", "si": "Slovenian", "bg": "Bulgarian", "gr": "Greek",
}


class KeyboardPage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Layout", "Keyboard layout"), ("Layout", "Variant"),
            ("Repeat", "Repeat delay"), ("Repeat", "Repeat rate"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Layout"))

        layout_codes = self._get_layouts()
        display_names = [LAYOUT_NAMES.get(c, c) for c in layout_codes]
        current_layout = self.store.get("keyboard_layout", "us")
        try:
            layout_idx = layout_codes.index(current_layout)
        except ValueError:
            layout_idx = 0

        layout_dropdown = Gtk.DropDown.new(Gtk.StringList.new(display_names), None)
        layout_dropdown.set_selected(layout_idx)
        layout_dropdown.set_size_request(240, -1)

        current_variant = self.store.get("keyboard_variant", "")
        variant_codes: list[str] = []

        variant_dropdown = Gtk.DropDown.new(Gtk.StringList.new(["(Default)"]), None)
        variant_dropdown.set_size_request(240, -1)
        variant_row = self.make_setting_row("Variant", "", variant_dropdown)

        def _build_variant_dropdown(layout_code):
            variants = self._get_variants(layout_code)
            variant_codes.clear()
            variant_codes.append("")
            variant_codes.extend(variants)
            variant_dropdown.set_model(Gtk.StringList.new(["(Default)"] + variants))
            variant_row.set_visible(bool(variants))
            try:
                sel = variant_codes.index(current_variant if layout_code == current_layout else "")
            except ValueError:
                sel = 0
            variant_dropdown.set_selected(sel)

        def _on_variant_changed(dd, _pspec):
            idx = dd.get_selected()
            if idx == Gtk.INVALID_LIST_POSITION or not variant_codes:
                return
            code = variant_codes[idx] if idx < len(variant_codes) else ""
            self.store.save_and_apply("keyboard_variant", code)

        variant_dropdown.connect("notify::selected", _on_variant_changed)

        def _on_layout_changed(dd, _pspec):
            idx = dd.get_selected()
            if idx == Gtk.INVALID_LIST_POSITION or idx >= len(layout_codes):
                return
            code = layout_codes[idx]
            self.store.save_dict_and_apply({"keyboard_layout": code, "keyboard_variant": ""})
            _build_variant_dropdown(code)

        layout_dropdown.connect("notify::selected", _on_layout_changed)
        page.append(self.make_setting_row("Keyboard layout", "", layout_dropdown))
        _build_variant_dropdown(current_layout)
        page.append(variant_row)

        # -- Repeat --
        page.append(self.make_group_label("Repeat"))

        delay_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 150, 1000, 50)
        delay_scale.set_value(self.store.get("keyboard_repeat_delay", 300))
        delay_scale.set_size_request(200, -1)
        delay_scale.set_draw_value(True)
        delay_scale.set_format_value_func(lambda _s, v: f"{v:.0f} ms")
        delay_scale.connect("value-changed", lambda s: self.store.save_debounced(
            "keyboard_repeat_delay", int(s.get_value())))
        page.append(self.make_setting_row("Repeat delay", "", delay_scale))

        rate_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 80, 5)
        rate_scale.set_value(self.store.get("keyboard_repeat_rate", 40))
        rate_scale.set_size_request(200, -1)
        rate_scale.set_draw_value(True)
        rate_scale.set_format_value_func(lambda _s, v: f"{v:.0f}/s")
        rate_scale.connect("value-changed", lambda s: self.store.save_debounced(
            "keyboard_repeat_rate", int(s.get_value())))
        page.append(self.make_setting_row("Repeat rate", "", rate_scale))
        return page

    @staticmethod
    def _get_layouts():
        try:
            r = subprocess.run(["localectl", "list-x11-keymap-layouts"], capture_output=True, text=True)
            return [l.strip() for l in r.stdout.splitlines() if l.strip()]
        except FileNotFoundError:
            return ["us"]

    @staticmethod
    def _get_variants(layout):
        try:
            r = subprocess.run(["localectl", "list-x11-keymap-variants", layout], capture_output=True, text=True)
            return [v.strip() for v in r.stdout.splitlines() if v.strip()]
        except FileNotFoundError:
            return []
```

- [ ] **Step 3: Create sound.py**

Create `files/usr/lib/adwaita-lite/settings/pages/sound.py`:

```python
import json
import re
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage


class SoundPage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("Output", "Output device"), ("Output", "Volume"), ("Output", "Mute"),
            ("Input", "Input device"), ("Input", "Microphone"),
        ]

    def build(self):
        page = self.make_page_box()

        # -- Output --
        page.append(self.make_group_label("Output"))
        sinks = self._get_sinks()
        sink_names = [n for n, _ in sinks]
        sink_descs = [d for _, d in sinks]
        default_sink = self._get_default_sink()
        try:
            sink_idx = sink_names.index(default_sink)
        except ValueError:
            sink_idx = 0

        sink_dd = Gtk.DropDown.new(Gtk.StringList.new(sink_descs or ["(No output devices)"]), None)
        sink_dd.set_selected(sink_idx)
        sink_dd.set_size_request(240, -1)
        sink_dd.connect("notify::selected", lambda d, _: (
            subprocess.run(["pactl", "set-default-sink", sink_names[d.get_selected()]], capture_output=True)
            if sink_names and d.get_selected() < len(sink_names) else None
        ))
        page.append(self.make_setting_row("Output device", "", sink_dd))

        out_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        out_vol.set_value(self._get_volume("@DEFAULT_SINK@"))
        out_vol.set_size_request(200, -1)
        out_vol.set_draw_value(True)
        out_vol.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        out_vol.connect("value-changed", lambda s: subprocess.run(
            ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(s.get_value())}%"], capture_output=True))
        page.append(self.make_setting_row("Volume", "", out_vol))

        out_mute = Gtk.Switch()
        out_mute.set_active(self._get_mute("@DEFAULT_SINK@"))
        out_mute.connect("state-set", lambda _, s: subprocess.run(
            ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if s else "0"], capture_output=True) or False)
        page.append(self.make_setting_row("Mute", "", out_mute))

        # -- Input --
        page.append(self.make_group_label("Input"))
        sources = self._get_sources()
        source_names = [n for n, _ in sources]
        source_descs = [d for _, d in sources]
        default_source = self._get_default_source()
        try:
            source_idx = source_names.index(default_source)
        except ValueError:
            source_idx = 0

        source_dd = Gtk.DropDown.new(Gtk.StringList.new(source_descs or ["(No input devices)"]), None)
        source_dd.set_selected(source_idx)
        source_dd.set_size_request(240, -1)
        source_dd.connect("notify::selected", lambda d, _: (
            subprocess.run(["pactl", "set-default-source", source_names[d.get_selected()]], capture_output=True)
            if source_names and d.get_selected() < len(source_names) else None
        ))
        page.append(self.make_setting_row("Input device", "", source_dd))

        in_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        in_vol.set_value(self._get_volume("@DEFAULT_SOURCE@", is_source=True))
        in_vol.set_size_request(200, -1)
        in_vol.set_draw_value(True)
        in_vol.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        in_vol.connect("value-changed", lambda s: subprocess.run(
            ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{int(s.get_value())}%"], capture_output=True))
        page.append(self.make_setting_row("Volume", "", in_vol))

        in_mute = Gtk.Switch()
        in_mute.set_active(self._get_mute("@DEFAULT_SOURCE@", is_source=True))
        in_mute.connect("state-set", lambda _, s: subprocess.run(
            ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1" if s else "0"], capture_output=True) or False)
        page.append(self.make_setting_row("Mute", "", in_mute))
        return page

    @staticmethod
    def _get_sinks():
        try:
            r = subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True, text=True)
            return [(s["name"], s.get("description", s["name"])) for s in json.loads(r.stdout)]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _get_default_sink():
        try:
            return subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return ""

    @staticmethod
    def _get_sources():
        try:
            r = subprocess.run(["pactl", "-f", "json", "list", "sources"], capture_output=True, text=True)
            return [(s["name"], s.get("description", s["name"]))
                    for s in json.loads(r.stdout) if ".monitor" not in s["name"]]
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _get_default_source():
        try:
            return subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return ""

    @staticmethod
    def _get_volume(target, is_source=False):
        cmd = "get-source-volume" if is_source else "get-sink-volume"
        try:
            r = subprocess.run(["pactl", cmd, target], capture_output=True, text=True)
            m = re.search(r"(\d+)%", r.stdout)
            return int(m.group(1)) if m else 50
        except FileNotFoundError:
            return 50

    @staticmethod
    def _get_mute(target, is_source=False):
        cmd = "get-source-mute" if is_source else "get-sink-mute"
        try:
            return "yes" in subprocess.run(["pactl", cmd, target], capture_output=True, text=True).stdout.lower()
        except FileNotFoundError:
            return False
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py files/usr/lib/adwaita-lite/settings/pages/keyboard.py files/usr/lib/adwaita-lite/settings/pages/sound.py
git commit -m "feat: migrate Mouse/Touchpad, Keyboard, and Sound pages"
```

---

### Task 13: Migrate Power/Lock, Default Apps, and About Pages

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`
- Create: `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`
- Create: `files/usr/lib/adwaita-lite/settings/pages/about.py`

- [ ] **Step 1: Create power_lock.py**

Create `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`:

```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage

TIMEOUT_OPTIONS = [
    ("1 minute", 60), ("2 minutes", 120), ("5 minutes", 300),
    ("10 minutes", 600), ("15 minutes", 900), ("30 minutes", 1800), ("Never", 0),
]


class PowerLockPage(BasePage):
    @property
    def search_keywords(self):
        return [("Lock & Display", "Lock screen"), ("Lock & Display", "Display off")]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Lock & Display"))
        labels = [l for l, _ in TIMEOUT_OPTIONS]
        seconds = [s for _, s in TIMEOUT_OPTIONS]

        lock_dd = Gtk.DropDown.new_from_strings(labels)
        current_lock = self.store.get("lock_timeout", 300)
        try:
            lock_dd.set_selected(seconds.index(current_lock))
        except ValueError:
            lock_dd.set_selected(2)
        lock_dd.connect("notify::selected", lambda d, _:
            self.store.save_and_apply("lock_timeout", seconds[d.get_selected()]))
        page.append(self.make_setting_row("Lock screen after", "", lock_dd))

        dpms_dd = Gtk.DropDown.new_from_strings(labels)
        current_dpms = self.store.get("display_off_timeout", 600)
        try:
            dpms_dd.set_selected(seconds.index(current_dpms))
        except ValueError:
            dpms_dd.set_selected(2)
        dpms_dd.connect("notify::selected", lambda d, _:
            self.store.save_and_apply("display_off_timeout", seconds[d.get_selected()]))
        page.append(self.make_setting_row("Turn off display after", "", dpms_dd))
        return page
```

- [ ] **Step 2: Create default_apps.py**

Create `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`:

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk

from ..base import BasePage

APP_MIME_TYPES = [
    ("Web Browser", "x-scheme-handler/http"),
    ("File Manager", "inode/directory"),
    ("Terminal", None),
    ("Text Editor", "text/plain"),
    ("Media Player", "video/x-matroska"),
]


class DefaultAppsPage(BasePage):
    @property
    def search_keywords(self):
        return [("Default Applications", label) for label, _ in APP_MIME_TYPES]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Default Applications"))
        for label, mime_type in APP_MIME_TYPES:
            apps = self._get_apps_for_mime(mime_type)
            if not apps:
                continue
            desktop_ids = [did for did, _ in apps]
            display_names = [name for _, name in apps]
            dropdown = Gtk.DropDown.new_from_strings(display_names)
            current = self._get_default_app(mime_type)
            try:
                dropdown.set_selected(desktop_ids.index(current))
            except ValueError:
                dropdown.set_selected(0)
            if mime_type:
                dropdown.connect("notify::selected", lambda d, _, mt=mime_type, ids=desktop_ids:
                    subprocess.run(["xdg-mime", "default", ids[d.get_selected()], mt], check=False))
            page.append(self.make_setting_row(label, "", dropdown))
        return page

    @staticmethod
    def _get_apps_for_mime(mime_type):
        if mime_type is None:
            apps, seen = [], set()
            for app in Gio.AppInfo.get_all():
                did = app.get_id()
                if not did or did in seen:
                    continue
                cats = app.get_categories() or ""
                if "TerminalEmulator" in cats:
                    seen.add(did)
                    apps.append((did, app.get_display_name()))
            return apps
        seen, apps = set(), []
        for app in Gio.AppInfo.get_all_for_type(mime_type):
            did = app.get_id()
            if not did or did in seen:
                continue
            seen.add(did)
            apps.append((did, app.get_display_name()))
        return apps

    @staticmethod
    def _get_default_app(mime_type):
        if mime_type is None:
            return ""
        try:
            return subprocess.run(["xdg-mime", "query", "default", mime_type],
                                  capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            return ""
```

- [ ] **Step 3: Create about.py**

Create `files/usr/lib/adwaita-lite/settings/pages/about.py`:

```python
import os
import socket
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")

from ..base import BasePage


class AboutPage(BasePage):
    @property
    def search_keywords(self):
        return [
            ("About", "Operating System"), ("About", "Hostname"),
            ("About", "Processor"), ("About", "Memory"), ("About", "Disk"),
            ("About", "Desktop"),
        ]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("About"))

        os_name = "Adwaita-Lite"
        os_version = ""
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("VERSION_ID="):
                    os_version = line.split("=", 1)[1].strip('"')
        except OSError:
            pass
        page.append(self.make_info_row("Operating System", f"{os_name} {os_version}".strip()))
        page.append(self.make_info_row("Hostname", socket.gethostname()))

        cpu = "Unknown"
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
        except OSError:
            pass
        page.append(self.make_info_row("Processor", cpu))

        ram = "Unknown"
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    ram = f"{int(line.split()[1]) / 1048576:.1f} GB"
                    break
        except (OSError, ValueError):
            pass
        page.append(self.make_info_row("Memory", ram))

        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            used = (st.f_blocks - st.f_bfree) * st.f_frsize
            page.append(self.make_info_row("Disk", f"{used / 1073741824:.1f} GB used of {total / 1073741824:.1f} GB"))
        except OSError:
            pass

        labwc_ver = "unknown"
        try:
            labwc_ver = subprocess.run(["labwc", "--version"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            pass
        page.append(self.make_info_row("Desktop", f"labwc {labwc_ver}"))
        return page
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/power_lock.py files/usr/lib/adwaita-lite/settings/pages/default_apps.py files/usr/lib/adwaita-lite/settings/pages/about.py
git commit -m "feat: migrate Power/Lock, Default Apps, and About pages"
```

---

### Task 14: Register All Pages

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/__init__.py`

- [ ] **Step 1: Write the page registry**

Replace `files/usr/lib/adwaita-lite/settings/pages/__init__.py` with:

```python
from .about import AboutPage
from .appearance import AppearancePage
from .bluetooth import BluetoothPage
from .default_apps import DefaultAppsPage
from .display import DisplayPage
from .keyboard import KeyboardPage
from .mouse_touchpad import MouseTouchpadPage
from .network import NetworkPage
from .panel import PanelPage
from .power_lock import PowerLockPage
from .sound import SoundPage

ALL_PAGES = [
    ("display-brightness-symbolic", "Appearance", AppearancePage),
    ("video-display-symbolic", "Display", DisplayPage),
    ("network-wireless-symbolic", "Network", NetworkPage),
    ("bluetooth-symbolic", "Bluetooth", BluetoothPage),
    ("view-app-grid-symbolic", "Panel", PanelPage),
    ("input-mouse-symbolic", "Mouse & Touchpad", MouseTouchpadPage),
    ("input-keyboard-symbolic", "Keyboard", KeyboardPage),
    ("audio-volume-high-symbolic", "Sound", SoundPage),
    ("system-shutdown-symbolic", "Power & Lock", PowerLockPage),
    ("application-x-executable-symbolic", "Default Apps", DefaultAppsPage),
    ("help-about-symbolic", "About", AboutPage),
]
```

Note: This imports `NetworkPage` and `BluetoothPage` which don't exist yet. They will be created in Tasks 15 and 16. **Create stub files first** so the import doesn't fail:

Create `files/usr/lib/adwaita-lite/settings/pages/network.py`:
```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage


class NetworkPage(BasePage):
    @property
    def search_keywords(self):
        return [("WiFi", "Network"), ("Wired", "Ethernet")]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Network"))
        page.append(Gtk.Label(label="Network page — coming in next task"))
        return page
```

Create `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py`:
```python
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from ..base import BasePage


class BluetoothPage(BasePage):
    @property
    def search_keywords(self):
        return [("Bluetooth", "Bluetooth")]

    def build(self):
        page = self.make_page_box()
        page.append(self.make_group_label("Bluetooth"))
        page.append(Gtk.Label(label="Bluetooth page — coming in next task"))
        return page
```

- [ ] **Step 2: Verify full app imports work**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.pages import ALL_PAGES
print(f'{len(ALL_PAGES)} pages registered')
for icon, label, cls in ALL_PAGES:
    print(f'  {label}: {cls.__name__}')
"
```

Expected: 11 pages listed.

- [ ] **Step 3: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/
git commit -m "feat: register all pages including Network and Bluetooth stubs"
```

---

### Task 15: Build Network Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/network.py` (replace stub)

- [ ] **Step 1: Implement full NetworkPage**

Replace `files/usr/lib/adwaita-lite/settings/pages/network.py` with:

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..base import BasePage


class NetworkPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._nm = None
        self._wifi_list: Gtk.ListBox | None = None
        self._wifi_toggle: Gtk.Switch | None = None
        self._active_box: Gtk.Box | None = None
        self._wired_label: Gtk.Label | None = None
        self._status_label: Gtk.Label | None = None

    @property
    def search_keywords(self):
        return [
            ("WiFi", "WiFi"), ("WiFi", "Network"), ("WiFi", "Wireless"),
            ("WiFi", "Hidden network"), ("WiFi", "Password"),
            ("Wired", "Ethernet"), ("Connection", "IP address"),
        ]

    def build(self):
        from ..dbus_helpers import NetworkManagerHelper
        self._nm = NetworkManagerHelper(self.event_bus)

        page = self.make_page_box()

        # -- WiFi header with toggle --
        wifi_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        wifi_header.append(self.make_group_label("WiFi"))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        wifi_header.append(spacer)
        self._wifi_toggle = Gtk.Switch()
        self._wifi_toggle.set_valign(Gtk.Align.CENTER)
        self._wifi_toggle.connect("state-set", self._on_wifi_toggled)
        wifi_header.append(self._wifi_toggle)
        page.append(wifi_header)

        # Status label (for connection feedback)
        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("setting-subtitle")
        self._status_label.set_visible(False)
        page.append(self._status_label)

        # WiFi networks list
        self._wifi_list = Gtk.ListBox()
        self._wifi_list.set_selection_mode(Gtk.SelectionMode.NONE)
        page.append(self._wifi_list)

        # Buttons row
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scan_btn = Gtk.Button(label="Scan")
        scan_btn.connect("clicked", lambda _: self._nm.request_scan() if self._nm else None)
        btn_row.append(scan_btn)
        hidden_btn = Gtk.Button(label="Connect to Hidden Network...")
        hidden_btn.connect("clicked", lambda _: self._show_hidden_dialog())
        btn_row.append(hidden_btn)
        page.append(btn_row)

        # -- Active Connection --
        page.append(self.make_group_label("Active Connection"))
        self._active_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        page.append(self._active_box)

        # -- Wired --
        page.append(self.make_group_label("Wired"))
        self._wired_label = Gtk.Label(label="Checking...", xalign=0)
        page.append(self._wired_label)

        # Advanced button
        adv_btn = Gtk.Button(label="Advanced...")
        adv_btn.set_halign(Gtk.Align.START)
        adv_btn.connect("clicked", lambda _: subprocess.Popen(
            ["nm-connection-editor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        page.append(adv_btn)

        # Subscribe to events
        self.event_bus.subscribe("nm-ready", self._on_nm_ready)
        self.event_bus.subscribe("network-changed", lambda _: self._refresh_all())
        self.event_bus.subscribe("network-connect-success", self._on_connect_success)
        self.event_bus.subscribe("network-connect-error", self._on_connect_error)

        return page

    def _on_nm_ready(self, _data):
        self._wifi_toggle.set_active(self._nm.is_wifi_enabled())
        self._refresh_all()

    def _on_wifi_toggled(self, _switch, state):
        if self._nm:
            self._nm.set_wifi_enabled(state)
        return False

    def _refresh_all(self):
        self._refresh_networks()
        self._refresh_active()
        self._refresh_wired()

    def _refresh_networks(self):
        if self._wifi_list is None or self._nm is None:
            return
        while (child := self._wifi_list.get_row_at_index(0)) is not None:
            self._wifi_list.remove(child)
        if not self._nm.ready:
            return
        self._wifi_toggle.set_active(self._nm.is_wifi_enabled())
        for ap in self._nm.get_access_points():
            self._wifi_list.append(self._build_network_row(ap))

    def _build_network_row(self, ap):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        if ap.strength >= 75:
            icon_name = "network-wireless-signal-excellent-symbolic"
        elif ap.strength >= 50:
            icon_name = "network-wireless-signal-good-symbolic"
        elif ap.strength >= 25:
            icon_name = "network-wireless-signal-ok-symbolic"
        else:
            icon_name = "network-wireless-signal-weak-symbolic"
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16)
        box.append(icon)

        if ap.secured:
            lock = Gtk.Image.new_from_icon_name("channel-secure-symbolic")
            lock.set_pixel_size(16)
            box.append(lock)

        name = Gtk.Label(label=ap.ssid, xalign=0)
        name.set_hexpand(True)
        box.append(name)

        if ap.active:
            status = Gtk.Label(label="Connected")
            status.add_css_class("setting-subtitle")
            box.append(status)
            forget = Gtk.Button(label="Forget")
            forget.connect("clicked", lambda _, s=ap.ssid: self._forget(s))
            box.append(forget)
        else:
            connect = Gtk.Button(label="Connect")
            connect.connect("clicked", lambda _, a=ap: self._connect(a))
            box.append(connect)

        row.set_child(box)
        return row

    def _connect(self, ap):
        if ap.secured:
            self._show_password_dialog(ap)
        else:
            self._status_label.set_text(f"Connecting to {ap.ssid}...")
            self._status_label.set_visible(True)
            self._nm.connect_wifi(ap.ssid, None)

    def _show_password_dialog(self, ap):
        dialog = Gtk.Window(title=f"Connect to {ap.ssid}", modal=True)
        dialog.set_default_size(360, 180)
        dialog.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        pw_entry = Gtk.PasswordEntry()
        pw_entry.set_show_peek_icon(True)
        pw_entry.set_placeholder_text("Password")
        box.append(pw_entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _: dialog.destroy())
        btn_box.append(cancel)
        connect = Gtk.Button(label="Connect")
        connect.add_css_class("suggested-action")

        def _do_connect(_btn):
            pw = pw_entry.get_text()
            if not pw:
                return
            self._status_label.set_text(f"Connecting to {ap.ssid}...")
            self._status_label.set_visible(True)
            self._nm.connect_wifi(ap.ssid, pw)
            dialog.destroy()

        connect.connect("clicked", _do_connect)
        pw_entry.connect("activate", _do_connect)
        btn_box.append(connect)
        box.append(btn_box)
        dialog.set_child(box)
        dialog.present()

    def _show_hidden_dialog(self):
        dialog = Gtk.Window(title="Connect to Hidden Network", modal=True)
        dialog.set_default_size(360, 260)
        dialog.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)

        ssid_entry = Gtk.Entry()
        ssid_entry.set_placeholder_text("Network name (SSID)")
        box.append(ssid_entry)

        sec_dd = Gtk.DropDown.new_from_strings(["None", "WPA/WPA2", "WPA3"])
        box.append(self.make_setting_row("Security", "", sec_dd))

        pw_entry = Gtk.PasswordEntry()
        pw_entry.set_show_peek_icon(True)
        pw_entry.set_placeholder_text("Password")
        box.append(pw_entry)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.END)
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _: dialog.destroy())
        btn_box.append(cancel)
        connect = Gtk.Button(label="Connect")
        connect.add_css_class("suggested-action")

        def _do_connect(_btn):
            ssid = ssid_entry.get_text().strip()
            if not ssid:
                return
            pw = pw_entry.get_text() if sec_dd.get_selected() > 0 else None
            self._status_label.set_text(f"Connecting to {ssid}...")
            self._status_label.set_visible(True)
            self._nm.connect_wifi(ssid, pw, hidden=True)
            dialog.destroy()

        connect.connect("clicked", _do_connect)
        btn_box.append(connect)
        box.append(btn_box)
        dialog.set_child(box)
        dialog.present()

    def _forget(self, ssid):
        self._nm.forget_connection(ssid)

    def _on_connect_success(self, _data):
        self._status_label.set_text("Connected successfully")
        self._status_label.set_visible(True)
        GLib.timeout_add_seconds(3, lambda: self._status_label.set_visible(False) or GLib.SOURCE_REMOVE)

    def _on_connect_error(self, message):
        self._status_label.set_text(str(message))
        self._status_label.set_visible(True)

    def _refresh_active(self):
        if self._active_box is None or self._nm is None:
            return
        while (child := self._active_box.get_first_child()) is not None:
            self._active_box.remove(child)
        info = self._nm.get_active_connection_info()
        if info is None:
            self._active_box.append(Gtk.Label(label="Not connected", xalign=0))
            return
        self._active_box.append(self.make_info_row("Network", info.name))
        self._active_box.append(self.make_info_row("Type", info.type))
        self._active_box.append(self.make_info_row("IP Address", info.ip_address))
        self._active_box.append(self.make_info_row("Gateway", info.gateway))
        self._active_box.append(self.make_info_row("DNS", info.dns))

    def _refresh_wired(self):
        if self._wired_label is None or self._nm is None:
            return
        if not self._nm.has_wired():
            self._wired_label.set_text("No wired adapter detected")
        elif self._nm.is_wired_connected():
            self._wired_label.set_text("Connected")
        else:
            self._wired_label.set_text("Disconnected")
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/network.py
git commit -m "feat: implement Network page with WiFi scan, connect, and hidden network support"
```

---

### Task 16: Build Bluetooth Page

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py` (replace stub)

- [ ] **Step 1: Implement full BluetoothPage**

Replace `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py` with:

```python
import subprocess

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from ..base import BasePage


class BluetoothPage(BasePage):
    def __init__(self, store, event_bus):
        super().__init__(store, event_bus)
        self._bt = None
        self._toggle: Gtk.Switch | None = None
        self._paired_list: Gtk.ListBox | None = None
        self._found_list: Gtk.ListBox | None = None
        self._scan_btn: Gtk.Button | None = None
        self._scan_timer: int | None = None
        self._status_label: Gtk.Label | None = None

    @property
    def search_keywords(self):
        return [
            ("Bluetooth", "Bluetooth"), ("Bluetooth", "Pair"),
            ("Bluetooth", "Wireless"), ("Bluetooth", "Device"),
        ]

    def build(self):
        from ..dbus_helpers import BlueZHelper
        self._bt = BlueZHelper(self.event_bus)

        page = self.make_page_box()

        # -- Header with toggle --
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.append(self.make_group_label("Bluetooth"))
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)
        self._toggle = Gtk.Switch()
        self._toggle.set_valign(Gtk.Align.CENTER)
        self._toggle.set_active(self._bt.is_powered())
        self._toggle.connect("state-set", self._on_toggle)
        header.append(self._toggle)
        page.append(header)

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("setting-subtitle")
        self._status_label.set_visible(False)
        page.append(self._status_label)

        if not self._bt.available:
            page.append(Gtk.Label(label="No Bluetooth adapter found", xalign=0))
            return page

        # -- Paired devices --
        page.append(self.make_group_label("Paired Devices"))
        self._paired_list = Gtk.ListBox()
        self._paired_list.set_selection_mode(Gtk.SelectionMode.NONE)
        page.append(self._paired_list)

        # -- Found devices --
        page.append(self.make_group_label("Available Devices"))
        self._found_list = Gtk.ListBox()
        self._found_list.set_selection_mode(Gtk.SelectionMode.NONE)
        page.append(self._found_list)

        self._scan_btn = Gtk.Button(label="Search for devices")
        self._scan_btn.set_halign(Gtk.Align.START)
        self._scan_btn.connect("clicked", self._on_scan_clicked)
        page.append(self._scan_btn)

        # Advanced
        adv_btn = Gtk.Button(label="Advanced...")
        adv_btn.set_halign(Gtk.Align.START)
        adv_btn.connect("clicked", lambda _: subprocess.Popen(
            ["blueman-manager"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        page.append(adv_btn)

        # Subscribe
        self.event_bus.subscribe("bluetooth-changed", lambda _: self._refresh_devices())
        self.event_bus.subscribe("bluetooth-pair-success", self._on_pair_success)
        self.event_bus.subscribe("bluetooth-pair-error", self._on_pair_error)

        self._refresh_devices()
        return page

    def _on_toggle(self, _switch, state):
        self._bt.set_powered(state)
        return False

    def _on_scan_clicked(self, btn):
        self._bt.start_discovery()
        btn.set_sensitive(False)
        btn.set_label("Scanning...")
        self._scan_timer = GLib.timeout_add_seconds(30, self._stop_scan)

    def _stop_scan(self):
        self._bt.stop_discovery()
        if self._scan_btn:
            self._scan_btn.set_sensitive(True)
            self._scan_btn.set_label("Search for devices")
        self._scan_timer = None
        return GLib.SOURCE_REMOVE

    def _refresh_devices(self):
        if self._paired_list is None or self._found_list is None:
            return
        self._toggle.set_active(self._bt.is_powered())
        # Clear lists
        for lb in (self._paired_list, self._found_list):
            while (child := lb.get_row_at_index(0)) is not None:
                lb.remove(child)
        for dev in self._bt.get_devices():
            row = self._build_device_row(dev)
            if dev.paired:
                self._paired_list.append(row)
            else:
                self._found_list.append(row)

    def _build_device_row(self, dev):
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        icon = Gtk.Image.new_from_icon_name(dev.icon or "bluetooth-symbolic")
        icon.set_pixel_size(16)
        box.append(icon)

        name = Gtk.Label(label=dev.name, xalign=0)
        name.set_hexpand(True)
        box.append(name)

        if dev.paired:
            if dev.connected:
                status = Gtk.Label(label="Connected")
                status.add_css_class("setting-subtitle")
                box.append(status)
                dc_btn = Gtk.Button(label="Disconnect")
                dc_btn.connect("clicked", lambda _, p=dev.path: self._bt.disconnect_device(p))
                box.append(dc_btn)
            else:
                conn_btn = Gtk.Button(label="Connect")
                conn_btn.connect("clicked", lambda _, p=dev.path: self._bt.connect_device(p))
                box.append(conn_btn)
            forget_btn = Gtk.Button(label="Forget")
            forget_btn.connect("clicked", lambda _, p=dev.path: self._bt.remove_device(p))
            box.append(forget_btn)
        else:
            pair_btn = Gtk.Button(label="Pair")
            pair_btn.connect("clicked", lambda _, p=dev.path: self._pair(p))
            box.append(pair_btn)

        row.set_child(box)
        return row

    def _pair(self, device_path):
        self._status_label.set_text("Pairing...")
        self._status_label.set_visible(True)
        self._bt.pair_device(device_path)

    def _on_pair_success(self, _data):
        self._status_label.set_text("Paired successfully")
        self._status_label.set_visible(True)
        GLib.timeout_add_seconds(3, lambda: self._status_label.set_visible(False) or GLib.SOURCE_REMOVE)

    def _on_pair_error(self, message):
        self._status_label.set_text(f"Pairing failed: {message}")
        self._status_label.set_visible(True)
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
git commit -m "feat: implement Bluetooth page with device discovery, pairing, and management"
```

---

### Task 17: Update build.sh

**Files:**
- Modify: `build_files/build.sh`

- [ ] **Step 1: Read current build.sh to find the dnf install section**

Read `build_files/build.sh` and locate the `dnf5 install` command block.

- [ ] **Step 2: Add new packages to the install list**

Add these packages to the existing `dnf5 install` command (in alphabetical order within the list):
- `gammastep`
- `nm-connection-editor`
- `wdisplays`

- [ ] **Step 3: Add the settings package directory to the file copy section**

Find where the build script copies files from `files/` into the image. Ensure `files/usr/lib/adwaita-lite/` is included. If the build uses a broad copy like `cp -r files/* /`, this is already handled. If it copies specific directories, add `/usr/lib/adwaita-lite/`.

- [ ] **Step 4: Commit**

```bash
git add build_files/build.sh
git commit -m "feat: add gammastep, wdisplays, nm-connection-editor to image"
```

---

### Task 18: Integration Verification

- [ ] **Step 1: Run all unit tests**

```bash
cd /var/home/race/ublue-mike && python -m pytest tests/ -v
```

Expected: All tests pass (SettingsStore + EventBus).

- [ ] **Step 2: Verify the app can be imported end-to-end**

```bash
cd /var/home/race/ublue-mike && python -c "
import sys; sys.path.insert(0, 'files/usr/lib/adwaita-lite')
from settings.app import SettingsApp
print('Full app import chain OK')
print('App ID:', 'org.adwaitabluelite.Settings')
from settings.pages import ALL_PAGES
print(f'{len(ALL_PAGES)} pages registered:')
for _, label, cls in ALL_PAGES:
    kw = cls.__new__(cls)
    # Can't call build() without GTK display, but verify class exists
    print(f'  {label} ({cls.__name__})')
"
```

Expected: 11 pages listed, no import errors.

- [ ] **Step 3: Verify old monolith is replaced**

```bash
head -5 files/usr/bin/adwaita-lite-settings
```

Expected: The thin launcher (5 lines), not the old 1609-line monolith.

- [ ] **Step 4: Verify all page files exist**

```bash
ls -la files/usr/lib/adwaita-lite/settings/pages/*.py | wc -l
```

Expected: 12 files (11 pages + `__init__.py`).

- [ ] **Step 5: Commit any final fixes, then tag**

```bash
git add -A && git status
# If there are changes:
git commit -m "fix: integration fixes for settings v2 phase 1"
```
