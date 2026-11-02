import importlib.machinery
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-setup-wizard"


def _load_wizard_module():
    loader = importlib.machinery.SourceFileLoader("setup_wizard_smoke", str(SCRIPT))
    spec = importlib.util.spec_from_loader("setup_wizard_smoke", loader, origin=str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SCRIPT)
    spec.loader.exec_module(module)
    return module


def test_setup_wizard_window_constructs_with_real_gtk(monkeypatch, tmp_path):
    gi = pytest.importorskip("gi")
    try:
        gi.require_version("Gtk", "4.0")
    except (ValueError, ImportError, RuntimeError) as exc:
        pytest.skip(f"GTK 4 runtime unavailable for smoke testing: {exc}")
    from gi.repository import Gtk

    try:
        if hasattr(Gtk, "init_check") and not Gtk.init_check():
            pytest.skip("GTK could not initialize a display for smoke testing")
    except RuntimeError as exc:
        pytest.skip(f"GTK display unavailable: {exc}")

    module = _load_wizard_module()
    original_path = module.Path

    def sandbox_path(value, *args, **kwargs):
        if str(value) == "/tmp/adwaita-lite-installer.log":
            return tmp_path / "adwaita-lite-installer.log"
        return original_path(value, *args, **kwargs)

    monkeypatch.setattr(module, "Path", sandbox_path)
    monkeypatch.setattr(module, "_load_timezones", lambda: ["America/New_York"])
    monkeypatch.setattr(module, "_load_keyboard_layouts", lambda: [("us", "English (US)")])
    monkeypatch.setattr(module, "_load_drives", lambda: [{
        "name": "/dev/vda",
        "size": str(64 * 1024**3),
        "model": "Test Disk",
        "tran": "virtio",
    }])

    def fake_run(cmd, *args, **kwargs):
        class Result:
            returncode = 0
            stdout = "America/New_York\n"
            stderr = ""
        return Result()

    app = Gtk.Application(application_id="org.adwaitabluelite.SetupWizard.Test")
    try:
        app.register(None)
    except Exception as exc:
        pytest.skip(f"GTK application could not register for smoke testing: {exc}")

    with patch.object(module.subprocess, "run", side_effect=fake_run), \
         patch.object(module.atexit, "register", lambda *args, **kwargs: None), \
         patch.object(module.NM.Client, "new_async", lambda *args, **kwargs: None):
        window = module.SetupWizardWindow(app)

    assert window is not None
    window.destroy()
