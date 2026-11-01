import ast
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = "am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh".split()
CATALOGS = [
    ("wizard", ROOT / "po", "adwaita-lite-setup-wizard"),
    ("settings", ROOT / "po/settings", "adwaita-lite-settings"),
    ("app-menu", ROOT / "po/app-menu", "adwaita-lite-app-menu"),
]


def _po_path(directory: Path, lang: str) -> Path:
    return directory / f"{lang}.po"


def _mo_path(lang: str, domain: str) -> Path:
    return ROOT / "files/usr/share/locale" / lang / "LC_MESSAGES" / f"{domain}.mo"


def _parse_po_entries(path: Path):
    entries = []
    current = None
    field = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip("\n")
        if not line.strip():
            if current is not None:
                entries.append(current)
                current = None
                field = None
            continue

        if line.startswith("#~"):
            continue

        if current is None:
            current = {"flags": set(), "msgid": [], "msgstr": []}

        if line.startswith("#, "):
            current["flags"].update(flag.strip() for flag in line[3:].split(","))
            continue

        if line.startswith("msgid "):
            field = "msgid"
            current[field].append(ast.literal_eval(line.split(" ", 1)[1]))
            continue

        if line.startswith("msgstr "):
            field = "msgstr"
            current[field].append(ast.literal_eval(line.split(" ", 1)[1]))
            continue

        if line.startswith("msgstr["):
            field = "msgstr"
            current[field].append(ast.literal_eval(line.split(" ", 1)[1]))
            continue

        if line.startswith('"') and field is not None:
            current[field].append(ast.literal_eval(line))

    if current is not None:
        entries.append(current)

    return entries


def test_all_po_files_exist():
    missing = []
    for _name, directory, _domain in CATALOGS:
        for lang in LANGUAGES:
            path = _po_path(directory, lang)
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))

    assert missing == []


def test_all_po_files_compile():
    failures = []
    for _name, directory, _domain in CATALOGS:
        for lang in LANGUAGES:
            path = _po_path(directory, lang)
            result = subprocess.run(
                ["msgfmt", "--check", "--statistics", "--output-file=/dev/null", str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if result.returncode != 0:
                failures.append(f"{path.relative_to(ROOT)}:\n{result.stderr}")

    assert failures == []


def test_no_fuzzy_or_untranslated_release_entries():
    failures = []
    for _name, directory, _domain in CATALOGS:
        for lang in LANGUAGES:
            path = _po_path(directory, lang)
            for entry in _parse_po_entries(path):
                msgid = "".join(entry["msgid"])
                msgstr = "".join(entry["msgstr"])
                if msgid == "":
                    continue
                if "fuzzy" in entry["flags"]:
                    failures.append(f"{path.relative_to(ROOT)} fuzzy: {msgid!r}")
                if msgstr.strip() == "":
                    failures.append(f"{path.relative_to(ROOT)} untranslated: {msgid!r}")

    assert failures == []


def test_all_compiled_mo_files_exist_after_build():
    missing = []
    for _name, _directory, domain in CATALOGS:
        for lang in LANGUAGES:
            path = _mo_path(lang, domain)
            if not path.exists():
                missing.append(str(path.relative_to(ROOT)))

    assert missing == []


def test_settings_deferred_restart_strings_are_translated():
    required = {
        "Restart your session to apply panel and start menu changes.": (),
        "Restart Session": (),
        "Restart Session?": (),
        "This will close your apps and return you to the sign-in screen.": (),
        "Could not restart session: {detail}": ("{detail}",),
    }
    pot_entries = {
        "".join(entry["msgid"])
        for entry in _parse_po_entries(ROOT / "po/settings/adwaita-lite-settings.pot")
    }
    for msgid in required:
        assert msgid in pot_entries

    for lang in LANGUAGES:
        entries = {
            "".join(entry["msgid"]): "".join(entry["msgstr"])
            for entry in _parse_po_entries(ROOT / "po/settings" / f"{lang}.po")
        }
        for msgid, placeholders in required.items():
            msgstr = entries.get(msgid, "")
            assert msgstr.strip(), f"{lang} missing translation for {msgid!r}"
            for placeholder in placeholders:
                assert placeholder in msgstr, f"{lang} missing {placeholder} in {msgid!r}"
