"""Tests for the panel backend dispatcher."""

import importlib.machinery
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "files/usr/bin/adwaita-lite-session-panel"


def _load():
    loader = importlib.machinery.SourceFileLoader("session_panel", str(_SCRIPT))
    spec = importlib.util.spec_from_loader("session_panel", loader, origin=str(_SCRIPT))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(_SCRIPT)
    spec.loader.exec_module(module)
    return module


panel = _load()


def test_waybar_is_the_default(monkeypatch):
    monkeypatch.setattr(panel.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert panel.resolve_backend({}) == ("waybar", "/usr/bin/waybar")


def test_gtk4_backend_can_be_overridden(monkeypatch):
    monkeypatch.setenv("ADWAITA_LITE_PANEL_BIN", "/tmp/adwaita-lite-panel")
    monkeypatch.setattr(panel.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert panel.resolve_backend({"panel_backend": "gtk4"}) == (
        "gtk4", "/tmp/adwaita-lite-panel"
    )


def test_unknown_backend_falls_back_to_waybar(monkeypatch):
    monkeypatch.setattr(panel.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert panel.resolve_backend({"panel_backend": "nope"})[0] == "waybar"


def test_missing_gtk4_binary_falls_back_to_waybar(monkeypatch):
    def which(name):
        return "/usr/bin/waybar" if name == "waybar" else None

    monkeypatch.delenv("ADWAITA_LITE_PANEL_BIN", raising=False)
    monkeypatch.setattr(panel.shutil, "which", which)
    assert panel.resolve_backend({"panel_backend": "gtk4"}) == (
        "waybar", "/usr/bin/waybar"
    )
