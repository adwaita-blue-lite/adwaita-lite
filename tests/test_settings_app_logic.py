import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))

from settings.pages import about, appearance, default_apps, keyboard, panel, power_lock  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_keyboard_binding_clone_does_not_mutate_default_baseline():
    defaults = [{"key": "C-A-T", "action": "Execute", "command": "foot"}]

    cloned = keyboard._clone_bindings(defaults)
    cloned[0]["key"] = "C-A-Y"

    assert defaults[0]["key"] == "C-A-T"


def test_keyboard_user_keybindings_coerce_malformed_optional_fields(
    monkeypatch, tmp_path
):
    path = tmp_path / "keybindings.json"
    path.write_text(
        """
        [
          {
            "key": "C-A-Y",
            "action": "Execute",
            "command": [],
            "direction": {},
            "menu": 12,
            "display_name": []
          }
        ]
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(keyboard, "USER_KEYBINDINGS", path)

    loaded = keyboard._load_user_keybindings()

    assert loaded == [{
        "key": "C-A-Y",
        "action": "Execute",
        "command": "",
        "direction": "",
        "menu": "",
        "display_name": "Execute",
    }]


def test_keyboard_layouts_fall_back_when_localectl_returns_empty(monkeypatch):
    monkeypatch.setattr(keyboard, "_layouts_cache", None)
    monkeypatch.setattr(
        keyboard.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=""),
    )

    assert keyboard.KeyboardPage._get_layouts() == ["us"]


def test_panel_sanitize_pinned_skips_invalid_entries():
    pinned = panel.PanelPage._sanitize_pinned([
        "bad",
        {"name": "No command"},
        {
            "name": "Files",
            "command": "Thunar",
            "icon": "",
            "desktop_id": "thunar.desktop",
            "app_id": "thunar",
            "startup_wm_class": "Thunar",
        },
        {"command": "foot"},
    ])

    assert pinned == [
        {
            "name": "Files",
            "command": "Thunar",
            "icon": "application-x-executable-symbolic",
            "desktop_id": "thunar.desktop",
            "app_id": "thunar",
            "startup_wm_class": "Thunar",
        },
        {
            "name": "foot",
            "command": "foot",
            "icon": "application-x-executable-symbolic",
        },
    ]


def test_panel_identity_fields_from_flatpak_desktop_app_info():
    class FakeAppInfo:
        def get_id(self):
            return "com.example.App.desktop"

        def get_startup_wm_class(self):
            return "example-app"

    fields = panel.PanelPage._identity_fields_from_app_info(
        FakeAppInfo(),
        "flatpak run com.example.App",
    )

    assert fields == {
        "desktop_id": "com.example.App.desktop",
        "app_id": "com.example.App",
        "startup_wm_class": "example-app",
    }


def test_panel_sanitize_layout_filters_unknowns_and_duplicates():
    raw = {
        "start": ["custom/launcher", "clock", "clock", "unknown"],
        "center": ["wlr/taskbar"],
        "end": ["battery"],
    }

    layout = panel.PanelPage._sanitize_layout(raw)

    assert layout == {
        "start": ["custom/launcher", "clock"],
        "center": ["wlr/taskbar"],
        "end": ["battery", "pulseaudio", "backlight", "tray"],
    }


def test_panel_page_shows_restart_session_notice():
    source = Path(panel.__file__).read_text(encoding="utf-8")
    position_body = source.split("def _build_position_group", 1)[1].split(
        "def _build_density_group", 1
    )[0]

    assert 'PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")' in source
    assert "group.set_description(PANEL_RESTART_NOTICE)" in position_body


def test_panel_edge_change_saves_and_relabels_sections():
    class Store:
        def __init__(self):
            self.data = {"edge": "bottom"}
            self.saved = []

        def get(self, key, default=None):
            return self.data.get(key, default)

        def save_and_apply(self, key, value, mode="full"):
            self.data[key] = value
            self.saved.append((key, value, mode))

    class Group:
        def __init__(self):
            self.title = None

        def set_title(self, title):
            self.title = title

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False
    page._section_groups = {section: Group() for section in panel.SECTION_ORDER}
    page._refresh_module_lists = lambda: None

    page._on_edge_changed("left")

    assert page.store.saved == [("edge", "left", "waybar")]
    assert [page._section_groups[s].title for s in panel.SECTION_ORDER] == [
        "Top", "Center", "Bottom",
    ]


def test_panel_twilight_change_applies_with_waybar_mode():
    class Store:
        def __init__(self):
            self.data = {"panel_twilight": False}
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.data[key] = value
            self.saved.append((key, value, mode))

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False

    page._on_twilight_changed(True)

    assert page.store.saved == [("panel_twilight", True, "waybar")]
    assert page._updating is False


def test_panel_density_change_applies_with_waybar_mode():
    class Store:
        def __init__(self):
            self.data = {"density": "normal"}
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.data[key] = value
            self.saved.append((key, value, mode))

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False

    page._on_density_changed("compact")

    assert page.store.saved == [("density", "compact", "waybar")]
    assert page._updating is False


def test_accent_change_applies_with_waybar_mode():
    source = Path(appearance.__file__).read_text(encoding="utf-8")

    assert 'save_and_apply("accent", name, mode="waybar")' in source


def test_appearance_accent_shows_panel_restart_session_notice():
    source = Path(appearance.__file__).read_text(encoding="utf-8")
    accent_body = source.split("# -- Group 2: Accent color --", 1)[1].split(
        "# -- Group 3: Font size --", 1
    )[0]

    assert 'PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")' in source
    assert "accent_group.set_description(PANEL_RESTART_NOTICE)" in accent_body


def test_panel_move_module_defers_refresh_and_applies_layout_with_waybar_mode(monkeypatch):
    class Store:
        def __init__(self):
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.saved.append((key, value, mode))

    callbacks = []
    monkeypatch.setattr(
        panel.GLib,
        "idle_add",
        lambda callback: callbacks.append(callback) or 42,
    )

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False
    page._module_refresh_source = None
    page._layout_data = {
        "start": ["custom/launcher"],
        "center": ["wlr/taskbar"],
        "end": [],
    }
    refreshed = []

    def _refresh_module_lists():
        if not callbacks:
            raise AssertionError("module rows refreshed synchronously")
        refreshed.append(True)

    page._refresh_module_lists = _refresh_module_lists

    page._move_module("custom/launcher", "start", "center")

    assert page._layout_data == {
        "start": [],
        "center": ["wlr/taskbar", "custom/launcher"],
        "end": [],
    }
    assert refreshed == []
    assert callbacks[0]() == panel.GLib.SOURCE_REMOVE
    assert refreshed == [True]
    assert page.store.saved == [("layout", page._layout_data, "waybar")]
    assert page._updating is False


def test_panel_move_module_ignores_stale_source_section():
    class Store:
        def __init__(self):
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.saved.append((key, value))

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False
    page._layout_data = {
        "start": [],
        "center": ["wlr/taskbar", "custom/launcher"],
        "end": [],
    }
    page._refresh_module_lists = lambda: (_ for _ in ()).throw(
        AssertionError("stale move refreshed rows")
    )

    page._move_module("custom/launcher", "start", "center")

    assert page._layout_data == {
        "start": [],
        "center": ["wlr/taskbar", "custom/launcher"],
        "end": [],
    }
    assert page.store.saved == []
    assert page._updating is False


def test_panel_reorder_module_defers_refresh_and_applies_layout_with_waybar_mode(monkeypatch):
    class Store:
        def __init__(self):
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.saved.append((key, value, mode))

    callbacks = []
    monkeypatch.setattr(
        panel.GLib,
        "idle_add",
        lambda callback: callbacks.append(callback) or 42,
    )

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._updating = False
    page._module_refresh_source = None
    page._layout_data = {
        "start": ["custom/launcher", "clock"],
        "center": [],
        "end": [],
    }
    refreshed = []

    def _refresh_module_lists():
        if not callbacks:
            raise AssertionError("module rows refreshed synchronously")
        refreshed.append(True)

    page._refresh_module_lists = _refresh_module_lists

    page._reorder_module("custom/launcher", "start", 1)

    assert page._layout_data == {
        "start": ["clock", "custom/launcher"],
        "center": [],
        "end": [],
    }
    assert refreshed == []
    assert callbacks[0]() == panel.GLib.SOURCE_REMOVE
    assert refreshed == [True]
    assert page.store.saved == [("layout", page._layout_data, "waybar")]
    assert page._updating is False


def test_panel_remove_pinned_defers_refresh_and_applies_with_waybar_mode(monkeypatch):
    class Store:
        def __init__(self):
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.saved.append((key, value, mode))

    callbacks = []
    monkeypatch.setattr(
        panel.GLib,
        "idle_add",
        lambda callback: callbacks.append(callback) or 42,
    )

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._pinned_refresh_source = None
    page._pinned_data = [
        {"name": "Files", "command": "Thunar", "icon": "folder"},
        {"name": "Terminal", "command": "foot", "icon": "terminal"},
    ]
    refreshed = []

    def _refresh_pinned_list():
        if not callbacks:
            raise AssertionError("pinned rows refreshed synchronously")
        refreshed.append(True)

    page._refresh_pinned_list = _refresh_pinned_list

    page._remove_pinned(0)

    assert page._pinned_data == [
        {"name": "Terminal", "command": "foot", "icon": "terminal"},
    ]
    assert refreshed == []
    assert callbacks[0]() == panel.GLib.SOURCE_REMOVE
    assert refreshed == [True]
    assert page.store.saved == [("pinned", page._pinned_data, "waybar")]


def test_panel_cancel_pending_refreshes_removes_module_and_pinned_idle(monkeypatch):
    removed = []
    monkeypatch.setattr(
        panel.GLib,
        "source_remove",
        lambda source_id: removed.append(source_id),
    )

    page = panel.PanelPage.__new__(panel.PanelPage)
    page._module_refresh_source = 10
    page._pinned_refresh_source = 11

    page._cancel_pending_refreshes()

    assert removed == [10, 11]
    assert page._module_refresh_source is None
    assert page._pinned_refresh_source is None


def test_panel_add_pinned_app_applies_with_waybar_mode():
    class Store:
        def __init__(self):
            self.saved = []

        def save_and_apply(self, key, value, mode="full"):
            self.saved.append((key, value, mode))

        def show_toast(self, *_args):
            pass

    class AppInfo:
        def get_display_name(self):
            return "Files"

        def get_commandline(self):
            return "Thunar %U"

        def get_icon(self):
            return None

    page = panel.PanelPage.__new__(panel.PanelPage)
    page.store = Store()
    page._pinned_data = []
    refreshed = []
    page._refresh_pinned_list = lambda: refreshed.append(True)

    page._add_app_from_info(AppInfo())

    assert page._pinned_data == [{
        "name": "Files",
        "command": "Thunar",
        "icon": "application-x-executable-symbolic",
    }]
    assert refreshed == [True]
    assert page.store.saved == [("pinned", page._pinned_data, "waybar")]


def test_terminal_desktop_write_is_atomic_and_reports_success(monkeypatch, tmp_path):
    class FakeAppInfo:
        def get_commandline(self):
            return "/bin/sh"

        def get_executable(self):
            return "/bin/sh"

        def get_display_name(self):
            return "Shell\nTerminal"

    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_apps.DefaultAppsPage._set_terminal(FakeAppInfo()) is True

    desktop = tmp_path / ".local/share/applications/terminal.desktop"
    assert desktop.exists()
    content = desktop.read_text(encoding="utf-8")
    assert "Name=Shell Terminal" in content
    assert "Exec=/bin/sh" in content
    assert not desktop.with_suffix(".desktop.tmp").exists()


def test_terminal_desktop_write_reports_invalid_command(monkeypatch, tmp_path):
    class FakeAppInfo:
        def get_commandline(self):
            return "/definitely/missing/terminal"

        def get_executable(self):
            return "/definitely/missing/terminal"

        def get_display_name(self):
            return "Missing"

    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_apps.DefaultAppsPage._set_terminal(FakeAppInfo()) is False


def test_default_apps_browser_row_covers_related_mime_types():
    groups = dict(default_apps.APP_MIME_TYPES)

    assert groups["Web Browser"] == (
        "x-scheme-handler/http",
        "x-scheme-handler/https",
        "text/html",
    )


def test_restore_defaults_category_titles_escape_markup_ampersands():
    assert about._row_title_text("Mouse & Touchpad") == "Mouse &amp; Touchpad"
    assert about._row_title_text("Date & Time") == "Date &amp; Time"


def test_restore_defaults_has_accessibility_category_separate_from_appearance():
    assert about.CATEGORY_KEYS["Appearance"] == ["theme", "accent", "wallpaper"]
    assert about.CATEGORY_KEYS["Accessibility"] == [
        "font_size", "cursor_size", "high_contrast", "reduce_motion",
    ]


def test_power_timeout_sanitizer_matches_apply_defaults():
    assert power_lock._sanitize_timeout(999, 300) == 300
    assert power_lock._sanitize_timeout("600", 300) == 600
    assert power_lock._sanitize_timeout("bad", 0) == 0


def test_settings_launcher_guards_vm_renderer_before_importing_gtk_app():
    source = (ROOT / "files/usr/bin/adwaita-lite-settings").read_text(
        encoding="utf-8"
    )

    guard_idx = source.index("_guard_gtk_renderer_for_virtualized_sessions()")
    import_idx = source.index("from settings.app import main")
    assert guard_idx < import_idx
    assert "systemd-detect-virt" in source
    assert 'os.environ["GSK_RENDERER"] = "gl"' in source


def test_power_lock_helper_survives_transient_unmap():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/pages/power_lock.py"
    ).read_text(encoding="utf-8")

    assert 'connect("unrealize", lambda _w: self._teardown_helpers())' in source
    assert 'connect("unmap", lambda _w: self._teardown_helpers())' not in source


def test_power_profile_set_uses_async_dbus_call():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/dbus_helpers.py"
    ).read_text(encoding="utf-8")
    body = source.split("def set_active_profile", 1)[1].split(
        "def _on_props_changed", 1
    )[0]

    assert "self._bus.call(" in body
    assert "call_sync(" not in body
    assert "def _on_set_active_profile_done" in body


def test_window_close_holds_application_until_apply_work_drains():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "if self._store.has_apply_work():" in source
    assert "app.hold()" in source
    assert "self._store.wait_for_apply(_release_app)" in source


def test_settings_window_uses_adw_banner_for_deferred_restart_prompt():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "self._deferred_restart_banner = Adw.Banner()" in source
    assert '_("Restart your session to apply panel and start menu changes.")' in source
    assert '_("Restart Session")' in source
    assert 'connect("button-clicked", self._on_restart_session_clicked)' in source
    assert "content_toolbar.add_top_bar(self._deferred_restart_banner)" in source
    assert "store.set_deferred_changes_callback(self._set_deferred_restart_banner_revealed)" in source
    assert "self._store.set_deferred_changes_callback(None)" in source
    assert "store.has_deferred_session_changes()" in source


def test_settings_window_confirms_and_runs_session_restart():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "def _on_restart_session_clicked" in source
    assert "Adw.AlertDialog.new" in source
    assert '_("Restart Session?")' in source
    assert '_("This will close your apps and return you to the sign-in screen.")' in source
    assert 'dialog.add_response("cancel", _("Cancel"))' in source
    assert 'dialog.add_response("restart", _("Restart Session"))' in source
    assert 'dialog.set_response_appearance("restart", Adw.ResponseAppearance.DESTRUCTIVE)' in source
    assert '["labwc", "--exit"]' in source
    assert "stdin=subprocess.DEVNULL" in source
    assert "stdout=subprocess.DEVNULL" in source
    assert "stderr=subprocess.DEVNULL" in source
    assert '_("Could not restart session: {detail}")' in source


def test_failed_page_build_unsubscribes_partial_subscriptions():
    source = (
        ROOT / "files/usr/lib/adwaita-lite/settings/window.py"
    ).read_text(encoding="utf-8")

    assert "page.unsubscribe_all()" in source
