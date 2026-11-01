import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GREETER = ROOT / "files/usr/bin/adwaita-lite-greeter"


def _load_greeter_module():
    loader = importlib.machinery.SourceFileLoader("adwaita_lite_greeter", str(GREETER))
    spec = importlib.util.spec_from_loader(
        "adwaita_lite_greeter", loader, origin=str(GREETER)
    )
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(GREETER)
    spec.loader.exec_module(module)
    return module


def test_greeter_imports_without_flatpak_gate():
    module = _load_greeter_module()

    assert hasattr(module, "GreeterWindow")


def test_greeter_has_no_prelogin_flatpak_gate_or_copy():
    source = GREETER.read_text()

    forbidden = [
        "FLATPAK_DONE_PATH",
        "FLATPAK_SKIP_PATH",
        "FLATPAK_PROGRESS_PATH",
        "FLATPAK_LOGIN_READY_PATH",
        "FLATPAK_SKIP_HELPER",
        "_is_setup_in_progress",
        "_poll_setup_progress",
        "_apply_flatpak_setup_skip",
        "flatpak-setup.done",
        "flatpak-setup.skip",
        "flatpak-login-ready",
        "Finishing setup",
        "Installing your selected apps before you log in",
    ]
    for text in forbidden:
        assert text not in source
