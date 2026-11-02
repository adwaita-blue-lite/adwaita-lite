"""Regression tests for app-menu hardening."""

import importlib.machinery
import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-app-menu"
_loader = importlib.machinery.SourceFileLoader("app_menu_hardening", str(_SCRIPT))
_spec = importlib.util.spec_from_loader(
    "app_menu_hardening", _loader, origin=str(_SCRIPT)
)
app_menu = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app_menu)


def test_high_contrast_wins_over_twilight():
    assert app_menu._shell_theme_class(
        {"panel_twilight": True, "theme": "light", "high_contrast": True}
    ) is None
    assert app_menu._shell_theme_class(
        {"panel_twilight": True, "theme": "light", "high_contrast": False}
    ) == "app-menu-shell-dark"


def test_font_scale_css_grows_with_font_size():
    small = app_menu._font_scale_css({"font_size": 10})
    large = app_menu._font_scale_css({"font_size": 15})

    small_input = int(
        re.search(r"\.app-menu-search \{ font-size: (\d+)px; \}", small).group(1)
    )
    large_input = int(
        re.search(r"\.app-menu-search \{ font-size: (\d+)px; \}", large).group(1)
    )

    assert large_input > small_input
    assert small_input >= 8


def test_reduce_motion_zeroes_power_transition():
    assert app_menu._power_transition_duration({"reduce_motion": True}) == 0
    assert app_menu._power_transition_duration({"reduce_motion": False}) == 120
    assert app_menu._power_transition_duration({}) == 120


def test_launch_failure_does_not_record_or_close(monkeypatch):
    recorded = []

    class _FailingApp:
        def launch(self, files, context):
            return False

    class _DummyMenu:
        closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(app_menu, "_record_launch", lambda desktop_id: recorded.append(desktop_id))

    item = SimpleNamespace(app=_FailingApp(), desktop_id="broken.desktop")
    menu = _DummyMenu()
    app_menu.AppMenu._launch_item(menu, item)

    assert recorded == []
    assert menu.closed is False


def test_launch_success_records_and_closes(monkeypatch):
    recorded = []

    class _WorkingApp:
        def launch(self, files, context):
            return True

    class _DummyMenu:
        closed = False

        def close(self):
            self.closed = True

    monkeypatch.setattr(app_menu, "_record_launch", lambda desktop_id: recorded.append(desktop_id))

    item = SimpleNamespace(app=_WorkingApp(), desktop_id="good.desktop")
    menu = _DummyMenu()
    app_menu.AppMenu._launch_item(menu, item)

    assert recorded == ["good.desktop"]
    assert menu.closed is True


def test_pid_lock_creation_is_exclusive(monkeypatch, tmp_path):
    lock = tmp_path / "adwaita-lite-app-menu.pid"
    lock.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(app_menu, "PID_LOCK_PATH", lock)

    assert app_menu._try_create_pid_lock() is False
    assert lock.read_text(encoding="utf-8") == "12345"


def test_palette_falls_back_when_malformed(monkeypatch, tmp_path):
    bad = tmp_path / "palette.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(app_menu, "PALETTE_PATH", bad)
    monkeypatch.setattr(app_menu, "_REPO_PALETTE_PATH", tmp_path / "missing.json")

    palette = app_menu._load_palettes()

    assert "accents" in palette
    assert "blue" in palette["accents"]


def test_malformed_twilight_palette_is_disabled():
    assert app_menu._build_twilight_css({"light": None, "dark": None}) == ""
