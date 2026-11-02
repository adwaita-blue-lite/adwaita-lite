"""Tests for the Adwaita-Lite start menu stylesheet."""

import importlib.machinery
import importlib.util
import json
import os
import signal
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-app-menu"
_PALETTE = (
    Path(__file__).resolve().parents[1]
    / "files/usr/share/adwaita-lite/palette.json"
)
_loader = importlib.machinery.SourceFileLoader("app_menu", str(_SCRIPT))
_spec = importlib.util.spec_from_loader("app_menu", _loader, origin=str(_SCRIPT))
app_menu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app_menu)


class _FakeApp:
    def __init__(self, display_name: str):
        self._display_name = display_name

    def get_display_name(self) -> str:
        return self._display_name


def _css(settings=None) -> str:
    settings = settings or {"theme": "light", "accent": "blue"}
    palette = json.loads(_PALETTE.read_text(encoding="utf-8"))
    return app_menu._build_css(
        settings,
        palettes=palette,
        palette_paths=(_PALETTE,),
    ).decode("utf-8")


def test_app_item_carries_filterable_metadata_outside_widgets():
    item = app_menu.AppItem(_FakeApp("System Monitor"))

    assert isinstance(item, app_menu.GObject.Object)
    assert item.primary == "System Monitor"
    assert item.secondary == ""
    assert item.accessible_name == "System Monitor"
    assert item.category == "Other"
    assert item.search_text == "system monitor"
    assert app_menu._app_item_matches(item, "All Apps", "sys mon")
    assert not app_menu._app_item_matches(item, "Internet", "")

    item.category = "System"
    assert app_menu._app_item_matches(item, "System", "monitor")


def test_app_item_can_back_gtk_filter_models():
    store = app_menu.Gio.ListStore.new(app_menu.AppItem)
    terminal = app_menu.AppItem(_FakeApp("Terminal"))
    browser = app_menu.AppItem(_FakeApp("Web Browser"))
    browser.category = "Internet"
    store.splice(0, 0, [terminal, browser])

    state = {"category": "All Apps", "query": "web"}
    filt = app_menu.Gtk.CustomFilter.new(
        lambda item, _data=None: app_menu._app_item_matches(
            item,
            state["category"],
            state["query"],
        ),
        None,
    )
    filtered = app_menu.Gtk.FilterListModel.new(store, filt)

    assert filtered.get_n_items() == 1
    assert filtered.get_item(0) is browser

    state["category"] = "Internet"
    state["query"] = ""
    filt.changed(app_menu.Gtk.FilterChange.DIFFERENT)
    assert filtered.get_n_items() == 1
    assert filtered.get_item(0) is browser


def test_start_menu_defines_user_accent_tokens_from_settings():
    css = _css({"theme": "light", "accent": "yellow"})

    assert "@define-color accent_color #c88800;" in css
    assert "@define-color accent_fg_color #1e1e1e;" in css
    assert "@define-color accent_color #3584e4;" not in css


def test_load_settings_prefers_exported_session_snapshot(monkeypatch, tmp_path):
    live_settings = tmp_path / "settings.json"
    live_settings.write_text(json.dumps({"edge": "bottom"}), encoding="utf-8")
    session_settings = tmp_path / "session-settings.json"
    session_settings.write_text(json.dumps({"edge": "top"}), encoding="utf-8")

    monkeypatch.setattr(app_menu, "SETTINGS_PATH", live_settings)
    monkeypatch.setenv("ADWAITA_LITE_SESSION_SETTINGS", str(session_settings))

    assert app_menu._load_settings()["edge"] == "top"


def test_load_settings_uses_runtime_session_snapshot_before_live_file(monkeypatch, tmp_path):
    live_settings = tmp_path / "settings.json"
    live_settings.write_text(json.dumps({"edge": "bottom"}), encoding="utf-8")
    runtime_dir = tmp_path / "runtime"
    session_settings = runtime_dir / "adwaita-lite/session-settings.json"
    session_settings.parent.mkdir(parents=True)
    session_settings.write_text(json.dumps({"edge": "left"}), encoding="utf-8")

    monkeypatch.setattr(app_menu, "SETTINGS_PATH", live_settings)
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    assert app_menu._load_settings()["edge"] == "left"


def test_start_menu_high_contrast_defines_strong_surface_tokens():
    css = _css({"theme": "light", "accent": "purple", "high_contrast": True})

    assert "@define-color window_bg_color #000000;" in css
    assert "@define-color window_fg_color #ffffff;" in css
    assert "@define-color borders #ffffff;" in css
    assert "@define-color accent_color #9141ac;" in css


def test_start_menu_uses_waybar_aligned_theme_tokens():
    css = _css()
    assert 'font-family: "Roboto", "Adwaita Sans", sans-serif' in css
    assert "background-color: alpha(@window_bg_color, 0.90)" in css
    assert "background-color: transparent" in css
    assert "border-radius: 24px" in css
    assert ".app-menu-surface-compact {" in css
    assert "border-radius: 18px" in css
    assert ".app-menu-surface-ultra {" in css
    assert "window.app-menu.app-menu-ultra .app-menu-tile" in css
    assert "background: alpha(@window_fg_color, 0.08)" in css
    assert "background: alpha(@accent_color, 0.14)" in css
    assert ".app-menu-search:focus,\n.app-menu-search:focus-visible," in css
    assert "box-shadow: 0 0 0 2px alpha(@accent_color, 0.20);" in css
    assert ".app-menu-search text selection" in css
    assert "background: @accent_color;" in css
    assert "color: @accent_fg_color;" in css


def test_start_menu_borders_use_adwaita_border_token():
    css = _css()
    assert "border: 1px solid @borders" in css
    assert "border-top: 1px solid @borders" in css
    assert "border: 1px solid alpha(@window_fg_color" not in css
    assert "border-top: 1px solid alpha(@window_fg_color" not in css


def test_secondary_text_keeps_light_theme_contrast_headroom():
    css = _css()
    assert "color: alpha(@window_fg_color, 0.70)" in css
    assert "color: alpha(@window_fg_color, 0.72)" in css


def test_app_tiles_are_flat_until_interaction():
    css = _css()
    assert "padding: 4px 2px 6px 2px;" in css
    assert ".app-menu-grid {\n    background: transparent;\n    color: @window_fg_color;" in css
    assert ".app-menu-grid > child," in css
    assert ".app-menu-tile {\n    background: transparent;" in css
    assert "color: @window_fg_color;" in css
    assert ".app-menu-tile-name {\n    font-size: 12px;\n    font-weight: 500;\n    color: inherit;" in css
    assert "border: 1px solid transparent;" in css
    assert ".app-menu-tile:hover,\n.app-menu-tile:focus," in css
    assert ".app-menu-grid > child.activatable:hover .app-menu-tile" in css
    assert "background: alpha(@accent_color, 0.10)" in css
    assert "0 0 0 2px alpha(@accent_color, 0.20)" in css
    assert ".app-menu-tile:active,\n.app-menu-grid > child.activatable:active" in css
    assert "color: @accent_fg_color;" in css


def test_start_menu_has_vm_renderer_guard_before_gtk_import_without_style_fork():
    source = _SCRIPT.read_text(encoding="utf-8")

    guard_idx = source.index("if _detect_virtualized_session():")
    gtk_idx = source.index('gi.require_version("Gtk", "4.0")')
    reexec_idx = source.index("os.execv(sys.executable")
    assert guard_idx < reexec_idx < gtk_idx
    assert 'os.environ.setdefault("GSK_RENDERER", "gl")' in source
    assert "UL_APP_MENU_STABLE_RENDERING" not in source
    assert "app-menu-stable-rendering" not in source


def test_twilight_mode_chooses_opposite_menu_palette():
    assert app_menu._shell_theme_class({"theme": "light"}) is None
    assert app_menu._shell_theme_class(
        {"theme": "light", "panel_twilight": True}
    ) == "app-menu-shell-dark"
    assert app_menu._shell_theme_class(
        {"theme": "dark", "panel_twilight": True}
    ) == "app-menu-shell-light"


def test_twilight_menu_palette_matches_waybar_surface_tokens():
    css = _css()
    palette = json.loads(_PALETTE.read_text(encoding="utf-8"))
    dark = app_menu._twilight_palette_tokens(palette["dark"])
    light = app_menu._twilight_palette_tokens(palette["light"])

    assert "window.app-menu.app-menu-shell-dark .app-menu-surface" in css
    assert f"background-color: {dark['surface']}" in css
    assert f"color: {dark['fg']}" in css
    assert f"border: 1px solid {dark['border']}" in css
    assert f"window.app-menu.app-menu-shell-dark .app-menu-tile {{\n    background: transparent;\n    color: {dark['fg']};" in css
    assert f"window.app-menu.app-menu-shell-dark .app-menu-tile-name {{\n    color: {dark['fg']};" in css
    assert "window.app-menu.app-menu-shell-dark .app-menu-grid,\nwindow.app-menu.app-menu-shell-dark .app-menu-grid > child" in css
    assert f"color: {dark['fg']};" in css
    assert "window.app-menu.app-menu-shell-light .app-menu-surface" in css
    assert f"background-color: {light['surface']}" in css
    assert f"color: {light['fg']}" in css
    assert f"border: 1px solid {light['border']}" in css


def test_twilight_css_is_generated_from_palette_values():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert "background-color: rgba(34, 34, 38, 0.90)" not in source
    assert "background-color: rgba(250, 250, 250, 0.90)" not in source

    css = app_menu._build_twilight_css({
        "dark": {
            "window_bg": "#010203",
            "fg": "#f0e0d0",
        },
        "light": {
            "window_bg": "#f9f8f7",
            "fg": "#102030",
        },
    })

    assert "background-color: rgba(1, 2, 3, 0.90)" in css
    assert "color: #f0e0d0" in css
    assert "border: 1px solid rgba(240, 224, 208, 0.14)" in css
    assert "background-color: rgba(249, 248, 247, 0.90)" in css
    assert "color: #102030" in css
    assert "border: 1px solid rgba(16, 32, 48, 0.10)" in css


def test_start_menu_metrics_fit_1024x600_bottom_panel():
    metrics = app_menu._menu_metrics(
        {"density": "comfortable", "font_size": 11},
        {"edge": "bottom", "section": "start"},
        (1024, 600),
    )

    assert metrics["width"] == app_menu.MENU_WIDTH_IDEAL
    assert metrics["height"] == 496
    assert metrics["columns"] == app_menu.GRID_COLUMNS_MAX
    assert metrics["mode"] == "popover"
    assert metrics["show_frequent"] is True


def test_start_menu_metrics_scale_tiles_and_reduce_columns_for_large_text():
    metrics = app_menu._menu_metrics(
        {"density": "comfortable", "font_size": 24},
        {"edge": "bottom", "section": "start"},
        (1024, 600),
    )

    assert metrics["height"] <= 600 - 56 - round(48 * 1.35)
    assert metrics["tile_width"] > app_menu.TILE_WIDTH_BASE
    assert metrics["tile_height"] > app_menu.TILE_HEIGHT_BASE
    assert metrics["columns"] < app_menu.GRID_COLUMNS_MAX
    assert metrics["mode"] == "popover"


def test_start_menu_metrics_fit_1360x768_at_200_percent_scale():
    # GDK widget sizes are in logical/application pixels. A 1360x768
    # output at 200% scale leaves a 680x384 logical viewport; the menu
    # must fit that viewport, not the raw physical mode.
    metrics = app_menu._menu_metrics(
        {"density": "comfortable", "font_size": 11},
        {"edge": "bottom", "section": "start"},
        (680, 384),
    )

    assert metrics["mode"] == "compact"
    assert metrics["show_frequent"] is False
    assert metrics["surface_margin"] == app_menu.COMPACT_INSET
    assert metrics["width"] == 680 - (2 * app_menu.COMPACT_INSET)
    assert metrics["height"] <= 384 - (
        2 * app_menu.COMPACT_INSET
    ) - app_menu._panel_extent({"density": "comfortable", "font_size": 11}, "bottom")
    assert metrics["columns"] == app_menu.GRID_COLUMNS_MAX


def test_start_menu_metrics_use_ultra_mode_when_scaled_viewport_is_short():
    metrics = app_menu._menu_metrics(
        {"density": "comfortable", "font_size": 11},
        {"edge": "bottom", "section": "start"},
        (512, 300),
    )

    assert metrics["mode"] == "ultra"
    assert metrics["surface_margin"] == app_menu.ULTRA_INSET
    assert metrics["show_frequent"] is False
    assert metrics["show_filter"] is False
    assert metrics["show_section_labels"] is False
    assert metrics["show_power"] is False
    assert metrics["height"] == 300 - app_menu._panel_extent(
        {"density": "comfortable", "font_size": 11}, "bottom"
    ) - (2 * app_menu.ULTRA_INSET)
    assert metrics["grid_height"] >= app_menu.ULTRA_GRID_HEIGHT_MIN


def test_start_menu_metrics_allow_single_column_when_panel_makes_view_narrow():
    metrics = app_menu._menu_metrics(
        {"density": "comfortable", "font_size": 16},
        {"edge": "left", "section": "start"},
        (320, 240),
    )

    assert metrics["mode"] == "ultra"
    assert metrics["columns"] == 1
    assert metrics["width"] == 320 - app_menu._panel_extent(
        {"density": "comfortable", "font_size": 16}, "left"
    ) - (2 * app_menu.ULTRA_INSET)
    assert metrics["tile_width"] <= metrics["content_width"]


def test_display_size_normalization_uses_configured_output_scale_once():
    assert app_menu._logical_display_size(1360, 768, 2.0) == (680, 384)
    assert app_menu._logical_display_size(640, 480, 2.0) == (320, 240)
    assert app_menu._logical_display_size(680, 384, 2.0) == (680, 384)


def test_toggle_or_lock_replaces_foreign_live_pid_without_signalling(monkeypatch, tmp_path):
    lock = tmp_path / "adwaita-lite-app-menu.pid"
    lock.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(app_menu, "PID_LOCK_PATH", lock)
    monkeypatch.setattr(app_menu, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(app_menu, "_process_matches_lock_identity", lambda pid: False)

    def fail_kill(pid, sig):
        raise AssertionError(f"unexpected signal {sig} to pid {pid}")

    monkeypatch.setattr(app_menu.os, "kill", fail_kill)

    assert app_menu._toggle_or_lock() is True
    assert lock.read_text(encoding="utf-8") == str(os.getpid())
    app_menu._release_lock()


def test_toggle_or_lock_signals_verified_app_menu_process(monkeypatch, tmp_path):
    lock = tmp_path / "adwaita-lite-app-menu.pid"
    lock.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(app_menu, "PID_LOCK_PATH", lock)
    monkeypatch.setattr(app_menu, "_pid_exists", lambda pid: True)
    monkeypatch.setattr(app_menu, "_process_matches_lock_identity", lambda pid: True)

    sent = []

    def record_kill(pid, sig):
        sent.append((pid, sig))

    monkeypatch.setattr(app_menu.os, "kill", record_kill)

    assert app_menu._toggle_or_lock() is False
    assert sent == [(12345, signal.SIGTERM)]
