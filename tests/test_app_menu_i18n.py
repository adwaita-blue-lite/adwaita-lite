import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-app-menu"
MAKEFILE = ROOT / "po/Makefile"


def _source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_app_menu_declares_separate_gettext_domain():
    source = _source()

    assert "import gettext" in source
    assert 'TEXTDOMAIN = "adwaita-lite-app-menu"' in source
    assert 'LOCALEDIR = "/usr/share/locale"' in source
    assert 'gettext.bindtextdomain(TEXTDOMAIN, LOCALEDIR)' in source
    assert 'gettext.textdomain(TEXTDOMAIN)' in source
    assert "_ = gettext.gettext" in source


def test_app_menu_shell_strings_are_gettext_wrapped():
    source = _source()
    expected_literals = [
        "All Apps",
        "Accessories",
        "Development",
        "Games",
        "Graphics",
        "Internet",
        "Multimedia",
        "Settings",
        "System",
        "Other",
        "Search apps…",
        "Search apps",
        "Filter by category",
        "Frequent",
        "Lock",
        "Log Out",
        "Restart",
        "Shut Down",
        "Cancel",
        "Confirm",
        "Log out now?",
        "Restart the computer?",
        "Shut down the computer?",
        "Launch {app}",
    ]

    for literal in expected_literals:
        assert f'_("{literal}")' in source, f"{literal!r} is not wrapped"

    assert 'f"Launch {item.accessible_name}"' not in source


def test_app_menu_uses_stable_power_action_ids_for_logic():
    source = _source()

    assert "POWER_ACTIONS" in source
    assert '"lock"' in source
    assert '"logout"' in source
    assert '"restart"' in source
    assert '"shutdown"' in source
    assert 'if action_id == "lock":' in source
    assert 'if action_id in {"restart", "shutdown"}:' in source
    assert "def _prompt_confirm(self, action_id: str, label: str, cmd: list[str])" in source


def test_makefile_has_app_menu_gettext_targets():
    makefile = MAKEFILE.read_text(encoding="utf-8")

    expected_lines = [
        "APP_MENU_DOMAIN = adwaita-lite-app-menu",
        "APP_MENU_SOURCE = ../files/usr/bin/adwaita-lite-app-menu",
        "APP_MENU_POT = app-menu/$(APP_MENU_DOMAIN).pot",
        "APP_MENU_PO = $(LANGUAGES:%=app-menu/%.po)",
        "APP_MENU_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo)",
        "pot-app-menu: $(APP_MENU_POT)",
        "po-app-menu: $(APP_MENU_PO)",
        "mo-app-menu: $(APP_MENU_MO)",
        "pot: pot-wizard pot-settings pot-app-menu",
        "po: po-wizard po-settings po-app-menu",
        "mo: mo-wizard mo-settings mo-app-menu",
    ]

    for line in expected_lines:
        assert line in makefile


def test_makefile_dry_runs_app_menu_targets():
    result = subprocess.run(
        ["make", "-n", "-B", "pot-app-menu", "po-app-menu", "mo-app-menu"],
        cwd=ROOT / "po",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "xgettext" in result.stdout
    assert "adwaita-lite-app-menu" in result.stdout
    assert "msgmerge" in result.stdout or "msginit" in result.stdout
    assert "msgfmt" in result.stdout
