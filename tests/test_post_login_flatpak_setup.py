import importlib.machinery
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-app-setup"
HELPER = "/usr/libexec/adwaita-lite-app-setup-helper"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("app_setup", str(SCRIPT))
    spec = importlib.util.spec_from_loader("app_setup", loader, origin=str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SCRIPT)
    spec.loader.exec_module(module)
    return module


def test_app_setup_copy_and_visual_contract():
    source = SCRIPT.read_text()

    assert "Set up your apps" in source
    assert "Install the apps you selected during setup" in source
    assert "Install apps" in source
    assert "Not now" in source
    assert "Don't ask again" in source
    assert "first boot" not in source.lower()
    assert "max-width: 480px" in source
    assert "border-radius: 16px" in source
    assert ".primary-button" in source
    assert ".secondary-button" in source
    assert ".low-emphasis-button" in source


def test_app_setup_uses_undecorated_card_window():
    source = SCRIPT.read_text()

    assert "self.set_decorated(False)" in source
    assert "background-color: transparent" in source


def test_app_setup_does_not_render_empty_preview_label():
    source = SCRIPT.read_text()

    assert "if preview:" in source
    assert "card.append(self._preview)" in source


def test_should_show_prompt_requires_apps_without_done_or_skip(tmp_path):
    module = _load_module()
    apps = tmp_path / "flatpak-apps"
    done = tmp_path / "done"
    skip = tmp_path / "skip"

    apps.write_text("com.google.Chrome\n")
    assert module._should_show_prompt(apps, done, skip) is True

    done.touch()
    assert module._should_show_prompt(apps, done, skip) is False
    done.unlink()
    skip.touch()
    assert module._should_show_prompt(apps, done, skip) is False
    skip.unlink()
    apps.write_text("")
    assert module._should_show_prompt(apps, done, skip) is False


def test_should_complete_empty_selection_requires_empty_apps_without_done_or_skip(tmp_path):
    module = _load_module()
    apps = tmp_path / "flatpak-apps"
    done = tmp_path / "done"
    skip = tmp_path / "skip"

    assert module._should_complete_empty_selection(apps, done, skip) is False

    apps.write_text("")
    assert module._should_complete_empty_selection(apps, done, skip) is True

    done.touch()
    assert module._should_complete_empty_selection(apps, done, skip) is False
    done.unlink()
    skip.touch()
    assert module._should_complete_empty_selection(apps, done, skip) is False
    skip.unlink()
    apps.write_text("com.google.Chrome\n")
    assert module._should_complete_empty_selection(apps, done, skip) is False


def test_app_preview_limits_and_falls_back_to_ids(tmp_path):
    module = _load_module()
    apps = tmp_path / "flatpak-apps"
    apps.write_text("com.google.Chrome\nio.github.kolunmi.Bazaar\norg.example.Unknown\norg.more.App\n")

    preview = module._app_preview(apps, limit=3)

    assert preview == ["Google Chrome", "Bazaar", "org.example.Unknown", "+1 more"]


def test_helper_command_uses_noninteractive_sudo():
    module = _load_module()

    assert module._helper_command("install") == ["sudo", "-n", HELPER, "install"]
    assert module._helper_command("skip") == ["sudo", "-n", HELPER, "skip"]


def test_install_output_parser_reports_progress_and_failures():
    module = _load_module()
    events = module._parse_install_output(
        "PROGRESS 1 2 com.google.Chrome installing\n"
        "PROGRESS 1 2 com.google.Chrome installed\n"
        "FAILED io.github.kolunmi.Bazaar\n"
        "PARTIAL 1\n"
    )

    assert events.progress == (1, 2, "com.google.Chrome", "installed")
    assert events.failed == ["io.github.kolunmi.Bazaar"]
    assert events.complete is False


def test_success_output_parser_marks_complete():
    module = _load_module()
    events = module._parse_install_output("DONE\n")

    assert events.complete is True
    assert events.failed == []


def test_app_setup_uses_background_thread_for_install():
    source = SCRIPT.read_text()

    assert "threading.Thread" in source
    assert "GLib.idle_add" in source
    assert "Run in background" in source


def test_app_setup_holds_application_during_background_install():
    source = SCRIPT.read_text()

    assert "_install_app_hold" in source
    assert ".hold()" in source
    assert ".release()" in source


def test_app_setup_disconnects_install_handler_before_done_handler():
    source = SCRIPT.read_text()

    assert "_install_clicked_handler_id" in source
    assert "self._install_btn.disconnect(self._install_clicked_handler_id)" in source
    assert "self._install_clicked_handler_id = self._install_btn.connect" in source


def test_app_setup_hides_instead_of_closing_while_install_runs():
    source = SCRIPT.read_text()

    assert "def _dismiss(self)" in source
    assert "_install_running" in source
    assert "self.hide()" in source
    assert 'self._dismiss_btn.connect("clicked", lambda _btn: self._dismiss())' in source
