# Release Translation Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update all release translation catalogs and add a separate translated start menu domain so non-English users can complete first-run setup and basic desktop navigation.

**Architecture:** Keep gettext domain ownership explicit: wizard strings stay in `adwaita-lite-setup-wizard`, settings and greeter stay in `adwaita-lite-settings`, and start menu shell strings move into a new `adwaita-lite-app-menu` domain. Shared source/build/test changes are done by the coordinator; locale file updates are split by non-overlapping language groups so subagents do not edit the same files.

**Tech Stack:** Python 3, GTK4 via PyGObject, GNU gettext (`xgettext`, `msgmerge`, `msginit`, `msgfmt`), `make`, `pytest`.

---

## File Structure

- Modify `files/usr/bin/adwaita-lite-app-menu`: add gettext setup, wrap start-menu shell UI strings, and change power/category data so translated display labels do not become logic keys.
- Modify `po/Makefile`: add `adwaita-lite-app-menu` extraction, merge, and compile targets under `po/app-menu/`.
- Create `po/app-menu/`: source PO files for the new app-menu domain.
- Create `tests/test_app_menu_i18n.py`: focused tests that prove gettext wiring and Makefile app-menu targets exist.
- Create `tests/test_translation_catalogs.py`: release checks for PO existence, syntax, fuzzy entries, untranslated entries, and compiled `.mo` coverage.
- Modify wizard PO files: `po/am.po`, `po/ar.po`, `po/de.po`, `po/es.po`, `po/fa.po`, `po/fr.po`, `po/ha.po`, `po/hi.po`, `po/it.po`, `po/ja.po`, `po/ko.po`, `po/nl.po`, `po/pl.po`, `po/pt.po`, `po/ru.po`, `po/sv.po`, `po/sw.po`, `po/th.po`, `po/tr.po`, `po/vi.po`, `po/yo.po`, `po/zh.po`.
- Modify settings/greeter PO files: `po/settings/am.po`, `po/settings/ar.po`, `po/settings/de.po`, `po/settings/es.po`, `po/settings/fa.po`, `po/settings/fr.po`, `po/settings/ha.po`, `po/settings/hi.po`, `po/settings/it.po`, `po/settings/ja.po`, `po/settings/ko.po`, `po/settings/nl.po`, `po/settings/pl.po`, `po/settings/pt.po`, `po/settings/ru.po`, `po/settings/sv.po`, `po/settings/sw.po`, `po/settings/th.po`, `po/settings/tr.po`, `po/settings/vi.po`, `po/settings/yo.po`, `po/settings/zh.po`.
- Create or modify app-menu PO files: `po/app-menu/am.po`, `po/app-menu/ar.po`, `po/app-menu/de.po`, `po/app-menu/es.po`, `po/app-menu/fa.po`, `po/app-menu/fr.po`, `po/app-menu/ha.po`, `po/app-menu/hi.po`, `po/app-menu/it.po`, `po/app-menu/ja.po`, `po/app-menu/ko.po`, `po/app-menu/nl.po`, `po/app-menu/pl.po`, `po/app-menu/pt.po`, `po/app-menu/ru.po`, `po/app-menu/sv.po`, `po/app-menu/sw.po`, `po/app-menu/th.po`, `po/app-menu/tr.po`, `po/app-menu/vi.po`, `po/app-menu/yo.po`, `po/app-menu/zh.po`.
- Modify compiled `.mo` catalogs under `files/usr/share/locale/am/LC_MESSAGES/`, `files/usr/share/locale/ar/LC_MESSAGES/`, `files/usr/share/locale/de/LC_MESSAGES/`, `files/usr/share/locale/es/LC_MESSAGES/`, `files/usr/share/locale/fa/LC_MESSAGES/`, `files/usr/share/locale/fr/LC_MESSAGES/`, `files/usr/share/locale/ha/LC_MESSAGES/`, `files/usr/share/locale/hi/LC_MESSAGES/`, `files/usr/share/locale/it/LC_MESSAGES/`, `files/usr/share/locale/ja/LC_MESSAGES/`, `files/usr/share/locale/ko/LC_MESSAGES/`, `files/usr/share/locale/nl/LC_MESSAGES/`, `files/usr/share/locale/pl/LC_MESSAGES/`, `files/usr/share/locale/pt/LC_MESSAGES/`, `files/usr/share/locale/ru/LC_MESSAGES/`, `files/usr/share/locale/sv/LC_MESSAGES/`, `files/usr/share/locale/sw/LC_MESSAGES/`, `files/usr/share/locale/th/LC_MESSAGES/`, `files/usr/share/locale/tr/LC_MESSAGES/`, `files/usr/share/locale/vi/LC_MESSAGES/`, `files/usr/share/locale/yo/LC_MESSAGES/`, and `files/usr/share/locale/zh/LC_MESSAGES/`. Regenerate these files only; never hand-edit them.

Supported non-English languages are exactly:

```text
am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh
```

---

### Task 1: Add App Menu i18n Tests

**Files:**
- Create: `tests/test_app_menu_i18n.py`
- Read: `files/usr/bin/adwaita-lite-app-menu`
- Read: `po/Makefile`

- [ ] **Step 1: Create a failing gettext wiring test**

Create `tests/test_app_menu_i18n.py` with this content:

```python
import re
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
        ["make", "-n", "pot-app-menu", "po-app-menu", "mo-app-menu"],
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
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```bash
python -m pytest tests/test_app_menu_i18n.py -v
```

Expected: FAIL. At minimum, `test_app_menu_declares_separate_gettext_domain`, `test_app_menu_shell_strings_are_gettext_wrapped`, and `test_makefile_has_app_menu_gettext_targets` fail because app-menu gettext wiring and Makefile targets do not exist yet.

- [ ] **Step 3: Commit the failing tests**

Run:

```bash
git add tests/test_app_menu_i18n.py
git commit -m "test: define app menu i18n expectations"
```

Expected: commit succeeds. Do not skip hooks.

---

### Task 2: Wire App Menu to gettext

**Files:**
- Modify: `files/usr/bin/adwaita-lite-app-menu`
- Test: `tests/test_app_menu_i18n.py`
- Test: `tests/test_app_menu_css.py`

- [ ] **Step 1: Add gettext setup before translated constants**

In `files/usr/bin/adwaita-lite-app-menu`, add `import gettext` in the import block after `import json`, then add this setup before `SETTINGS_PATH`:

```python
TEXTDOMAIN = "adwaita-lite-app-menu"
LOCALEDIR = "/usr/share/locale"

gettext.bindtextdomain(TEXTDOMAIN, LOCALEDIR)
gettext.textdomain(TEXTDOMAIN)
_ = gettext.gettext
```

The nearby imports should look like this:

```python
import gettext
import json
import signal
import time
from pathlib import Path
```

- [ ] **Step 2: Translate category labels and filter labels**

Replace the category and filter constants with this exact structure:

```python
CATEGORIES: list[tuple[str, frozenset[str]]] = [
    (_("Accessories"), frozenset({"Utility", "Accessories", "Core"})),
    (_("Development"), frozenset({"Development", "IDE", "Building"})),
    (_("Games"),       frozenset({"Game"})),
    (_("Graphics"),    frozenset({"Graphics", "2DGraphics", "3DGraphics", "Photography",
                                  "RasterGraphics", "VectorGraphics", "Viewer"})),
    (_("Internet"),    frozenset({"Network", "WebBrowser", "Email", "InstantMessaging",
                                  "FileTransfer", "P2P", "Chat", "IRCClient"})),
    (_("Multimedia"),  frozenset({"AudioVideo", "Audio", "Video", "Player", "Recorder",
                                  "Music", "TV"})),
    (_("Settings"),    frozenset({"Settings", "DesktopSettings", "HardwareSettings",
                                  "ControlCenter"})),
    (_("System"),      frozenset({"System", "PackageManager", "Security", "Monitor",
                                  "TerminalEmulator", "FileManager"})),
]

ALL_APPS_LABEL = _("All Apps")
OTHER_CATEGORY_LABEL = _("Other")
CATEGORY_FILTER_LABELS: list[str] = (
    [ALL_APPS_LABEL] + [c[0] for c in CATEGORIES] + [OTHER_CATEGORY_LABEL]
)
```

In `_category_for`, replace `return "Other"` with:

```python
    return OTHER_CATEGORY_LABEL
```

In `_app_item_matches`, replace `category_filter != "All Apps"` with:

```python
        and category_filter != ALL_APPS_LABEL
```

In `_on_filter_changed`, replace the fallback assignment `self._category_filter = "All Apps"` with:

```python
            self._category_filter = ALL_APPS_LABEL
```

In `_update_frequent_visibility`, replace `self._category_filter == "All Apps"` with:

```python
        is_default = (self._category_filter == ALL_APPS_LABEL
```

- [ ] **Step 3: Translate power action labels without using labels as logic keys**

Replace `POWER_ACTIONS` with stable action IDs plus translated labels:

```python
POWER_ACTIONS = [
    ("lock",     _("Lock"),      "system-lock-screen", ["swaylock", "-f"]),
    ("logout",   _("Log Out"),   "system-log-out",     ["labwc", "--exit"]),
    ("restart",  _("Restart"),   "system-reboot",      ["systemctl", "reboot"]),
    ("shutdown", _("Shut Down"), "system-shutdown",    ["systemctl", "poweroff"]),
]
```

Then update `_build_power_bar` so the power loop starts like this:

```python
        for action_id, label, icon_name, cmd in POWER_ACTIONS:
            btn = Gtk.Button()
            btn.set_tooltip_text(label)
            _set_accessible_label(btn, label)
            btn.add_css_class("app-menu-power-btn")
            if action_id in {"restart", "shutdown"}:
                btn.add_css_class("destructive")
            img = Gtk.Image.new_from_icon_name(icon_name)
            img.set_pixel_size(22)
            btn.set_child(img)
            if action_id == "lock":
                btn.connect("clicked", lambda _b, c=cmd: self._run_command(c))
            else:
                btn.connect(
                    "clicked",
                    lambda _b, a=action_id, l=label, c=cmd: self._prompt_confirm(a, l, c),
                )
            normal.append(btn)
```

Replace `_prompt_confirm` with this implementation:

```python
    def _prompt_confirm(self, action_id: str, label: str, cmd: list[str]) -> None:
        prompts = {
            "logout":   (_("Log out now?"),            _("Log Out")),
            "restart":  (_("Restart the computer?"),   _("Restart")),
            "shutdown": (_("Shut down the computer?"), _("Shut Down")),
        }
        prompt, btn_label = prompts.get(action_id, (_("{action}?").format(action=label), label))
        self._confirm_label.set_label(prompt)
        self._confirm_action.set_label(btn_label)
        self._pending_cmd = cmd
        self._power_stack.set_visible_child_name("confirm")
```

- [ ] **Step 4: Translate widget labels, tooltips, placeholders, and accessibility labels**

Make these exact replacements in `files/usr/bin/adwaita-lite-app-menu`:

```python
self._search.set_placeholder_text(_("Search apps…"))
_set_accessible_label(self._search, _("Search apps"))
self._filter.set_tooltip_text(_("Filter by category"))
_set_accessible_label(self._filter, _("Filter by category"))
freq_label = Gtk.Label(label=_("Frequent"), xalign=0)
all_label = Gtk.Label(label=ALL_APPS_LABEL, xalign=0)
_set_accessible_label(btn, _("Launch {app}").format(app=item.accessible_name))
_set_accessible_label(tile, _("Launch {app}").format(app=item.accessible_name))
list_item.set_accessible_label(_("Launch {app}").format(app=item.accessible_name))
cancel = Gtk.Button(label=_("Cancel"))
self._confirm_action = Gtk.Button(label=_("Confirm"))
```

There are two existing `Launch {item.accessible_name}` call sites: one in `_make_tile` and one in `_on_grid_item_bind`. Both must use `_("Launch {app}").format(app=item.accessible_name)`.

- [ ] **Step 5: Run app menu i18n tests**

Run:

```bash
python -m pytest tests/test_app_menu_i18n.py -v
```

Expected: FAIL only on Makefile target tests if Task 3 has not been completed yet. All source-wrapping tests should PASS.

- [ ] **Step 6: Run existing app menu tests**

Run:

```bash
python -m pytest tests/test_app_menu_css.py -v
```

Expected: PASS. The default locale returns English strings, so tests that compare `All Apps`, `Other`, or category names should keep passing.

- [ ] **Step 7: Commit app menu gettext source wiring**

Run:

```bash
git add files/usr/bin/adwaita-lite-app-menu
git commit -m "feat: add gettext wiring to app menu"
```

Expected: commit succeeds. Do not commit `tests/test_app_menu_i18n.py` here because it was committed in Task 1.

---

### Task 3: Add App Menu gettext Build Targets

**Files:**
- Modify: `po/Makefile`
- Create: `po/app-menu/` through Makefile execution
- Test: `tests/test_app_menu_i18n.py`

- [ ] **Step 1: Add app-menu variables to `po/Makefile`**

After the settings domain variables, add:

```make
# --- App menu domain ---
APP_MENU_DOMAIN = adwaita-lite-app-menu
APP_MENU_SOURCE = ../files/usr/bin/adwaita-lite-app-menu
APP_MENU_POT = app-menu/$(APP_MENU_DOMAIN).pot
APP_MENU_PO = $(LANGUAGES:%=app-menu/%.po)
APP_MENU_MO = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo)
```

- [ ] **Step 2: Add app-menu targets to `po/Makefile`**

After the settings targets and before the combined targets, add:

```make
# --- App menu targets ---
pot-app-menu: $(APP_MENU_POT)

$(APP_MENU_POT): $(APP_MENU_SOURCE)
	@mkdir -p app-menu
	xgettext --language=Python --keyword=_ --keyword=N_ \
	    --output=$(APP_MENU_POT) --from-code=UTF-8 \
	    --package-name="$(APP_MENU_DOMAIN)" \
	    $(APP_MENU_SOURCE)

po-app-menu: $(APP_MENU_PO)

app-menu/%.po: $(APP_MENU_POT)
	@mkdir -p app-menu
	@if [ -f $@ ]; then \
	    msgmerge --update --no-fuzzy-matching $@ $(APP_MENU_POT); \
	else \
	    msginit --input=$(APP_MENU_POT) --output=$@ --locale=$* --no-translator; \
	fi

mo-app-menu: $(APP_MENU_MO)

$(LOCALEDIR)/%/LC_MESSAGES/$(APP_MENU_DOMAIN).mo: app-menu/%.po
	@mkdir -p $(dir $@)
	msgfmt --output=$@ $<
```

The leading indentation before recipe commands must be tabs, not spaces.

- [ ] **Step 3: Update combined targets and clean target**

Replace the combined target block with:

```make
# --- Combined targets ---
pot: pot-wizard pot-settings pot-app-menu
po: po-wizard po-settings po-app-menu
mo: mo-wizard mo-settings mo-app-menu

clean:
	rm -f $(WIZARD_POT) $(SETTINGS_POT) $(APP_MENU_POT)
	rm -f $(WIZARD_MO) $(SETTINGS_MO) $(APP_MENU_MO)

all: pot po mo
```

- [ ] **Step 4: Run Makefile tests**

Run:

```bash
python -m pytest tests/test_app_menu_i18n.py -v
```

Expected: PASS.

- [ ] **Step 5: Dry-run all translation build commands**

Run:

```bash
make -n all
```

Run from `po/`.

Expected: output includes `xgettext` commands for wizard, settings, and app-menu; `msgmerge` or `msginit` commands for all 22 languages in all domains; and `msgfmt` commands for all three domains.

- [ ] **Step 6: Commit Makefile app-menu targets**

Run:

```bash
git add po/Makefile tests/test_app_menu_i18n.py
git commit -m "build: add app menu translation targets"
```

Expected: commit succeeds.

---

### Task 4: Generate and Merge Translation Templates

**Files:**
- Modify: `po/adwaita-lite-setup-wizard.pot`
- Modify: `po/settings/adwaita-lite-settings.pot`
- Create: `po/app-menu/adwaita-lite-app-menu.pot`
- Modify: `po/*.po`
- Modify: `po/settings/*.po`
- Create: `po/app-menu/*.po`

- [ ] **Step 1: Regenerate POT files**

Run from `po/`:

```bash
make pot
```

Expected: command exits 0 and writes these templates:

```text
po/adwaita-lite-setup-wizard.pot
po/settings/adwaita-lite-settings.pot
po/app-menu/adwaita-lite-app-menu.pot
```

- [ ] **Step 2: Verify app-menu POT contains required strings**

Run from repository root:

```bash
python - <<'PY'
from pathlib import Path

pot = Path("po/app-menu/adwaita-lite-app-menu.pot").read_text(encoding="utf-8")
required = [
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
missing = [s for s in required if f'msgid "{s}"' not in pot]
if missing:
    raise SystemExit(f"Missing app-menu msgids: {missing}")
print(f"app-menu POT contains {len(required)} required msgids")
PY
```

Expected: prints `app-menu POT contains 24 required msgids`.

- [ ] **Step 3: Merge POT changes into PO files**

Run from `po/`:

```bash
make po
```

Expected: command exits 0 and creates all 22 app-menu PO files: `po/app-menu/am.po`, `po/app-menu/ar.po`, `po/app-menu/de.po`, `po/app-menu/es.po`, `po/app-menu/fa.po`, `po/app-menu/fr.po`, `po/app-menu/ha.po`, `po/app-menu/hi.po`, `po/app-menu/it.po`, `po/app-menu/ja.po`, `po/app-menu/ko.po`, `po/app-menu/nl.po`, `po/app-menu/pl.po`, `po/app-menu/pt.po`, `po/app-menu/ru.po`, `po/app-menu/sv.po`, `po/app-menu/sw.po`, `po/app-menu/th.po`, `po/app-menu/tr.po`, `po/app-menu/vi.po`, `po/app-menu/yo.po`, and `po/app-menu/zh.po`.

- [ ] **Step 4: Check for new app-menu PO files**

Run from repository root:

```bash
python - <<'PY'
from pathlib import Path

langs = "am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh".split()
missing = [lang for lang in langs if not Path(f"po/app-menu/{lang}.po").exists()]
if missing:
    raise SystemExit(f"Missing app-menu PO files: {missing}")
print(f"found {len(langs)} app-menu PO files")
PY
```

Expected: prints `found 22 app-menu PO files`.

- [ ] **Step 5: Commit generated templates and merged PO skeletons**

Run:

```bash
git add po/adwaita-lite-setup-wizard.pot po/settings/adwaita-lite-settings.pot po/app-menu po/*.po po/settings/*.po
git commit -m "chore: refresh translation templates"
```

Expected: commit succeeds. Do not add `*.po~` files; they are ignored by `.gitignore` and should remain untracked.

---

### Task 5: Add Release Catalog Validation Tests

**Files:**
- Create: `tests/test_translation_catalogs.py`

- [ ] **Step 1: Create catalog validation tests**

Create `tests/test_translation_catalogs.py` with this content:

```python
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
```

- [ ] **Step 2: Run catalog tests and verify current failures**

Run:

```bash
python -m pytest tests/test_translation_catalogs.py -v
```

Expected before translation completion: FAIL. The expected failures are untranslated entries in `po/app-menu/*.po` and missing compiled `adwaita-lite-app-menu.mo` files until app-menu translations are completed and `make mo-app-menu` runs.

- [ ] **Step 3: Commit catalog validation tests**

Run:

```bash
git add tests/test_translation_catalogs.py
git commit -m "test: validate release translation catalogs"
```

Expected: commit succeeds.

---

### Task 6: Dispatch Language Translation Subagents

**Files:**
- Modify by assigned language only: the exact `po/*.po`, `po/settings/*.po`, and `po/app-menu/*.po` files listed in Steps 2-7 of this task.

**Coordinator rule:** Do not let two subagents edit the same language. Do not let language subagents edit source code, `po/Makefile`, tests, POT files, `.mo` files, or docs.

- [ ] **Step 1: Prepare the shared subagent instruction header**

Use this exact header at the start of every language subagent prompt:

```markdown
You are updating release translations for Adwaita-Lite. Edit only the language files explicitly assigned in this prompt.

Goal: make first-run setup and basic desktop navigation understandable for non-English users.

You may edit only the exact `po/*.po`, `po/settings/*.po`, and `po/app-menu/*.po` files for the languages explicitly assigned in the rest of this prompt.

Do not edit source code, tests, POT files, Makefiles, `.mo` files, docs, or other languages.

Rules:
- Preserve every `msgid` exactly.
- Preserve placeholders exactly, including `{username}`, `{layout}`, `{ssid}`, `{exc}`, `{detail}`, `{name}`, `{app}`, and any other brace-delimited placeholder.
- Preserve escape sequences and line breaks.
- Keep `Adwaita-Lite` unchanged.
- Do not translate command names, paths, environment variables, package names, or project names unless the string is clearly a descriptive UI label.
- Remove fuzzy markers only when you have made the translation match the current `msgid`.
- Prefer simple, clear UI wording over literal technical phrasing.
- Keep these terms consistent within each language: Settings, Apps, Install, Password, Back, Next, Restart, Shut Down, Log Out, Search, Language.

Validation before returning:
- Run `msgfmt --check --statistics --output-file=/dev/null` on every PO file you edited.
- Search your edited files for `#, fuzzy` and empty `msgstr ""` entries outside the header.

Return:
- Languages updated.
- Files edited.
- Any entries you were uncertain about.
- Exact validation commands run and their results.
```

- [ ] **Step 2: Dispatch Group A subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `de es fr it nl pt sv`

Files you may edit:
- `po/de.po`, `po/es.po`, `po/fr.po`, `po/it.po`, `po/nl.po`, `po/pt.po`, `po/sv.po`
- `po/settings/de.po`, `po/settings/es.po`, `po/settings/fr.po`, `po/settings/it.po`, `po/settings/nl.po`, `po/settings/pt.po`, `po/settings/sv.po`
- `po/app-menu/de.po`, `po/app-menu/es.po`, `po/app-menu/fr.po`, `po/app-menu/it.po`, `po/app-menu/nl.po`, `po/app-menu/pt.po`, `po/app-menu/sv.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels.
```

- [ ] **Step 3: Dispatch Group B subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `pl ru tr`

Files you may edit:
- `po/pl.po`, `po/ru.po`, `po/tr.po`
- `po/settings/pl.po`, `po/settings/ru.po`, `po/settings/tr.po`
- `po/app-menu/pl.po`, `po/app-menu/ru.po`, `po/app-menu/tr.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels.
```

- [ ] **Step 4: Dispatch Group C subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `ja ko zh`

Files you may edit:
- `po/ja.po`, `po/ko.po`, `po/zh.po`
- `po/settings/ja.po`, `po/settings/ko.po`, `po/settings/zh.po`
- `po/app-menu/ja.po`, `po/app-menu/ko.po`, `po/app-menu/zh.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels. Use natural UI terminology for Japanese, Korean, and Simplified Chinese rather than literal English word order.
```

- [ ] **Step 5: Dispatch Group D subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `ar fa hi`

Files you may edit:
- `po/ar.po`, `po/fa.po`, `po/hi.po`
- `po/settings/ar.po`, `po/settings/fa.po`, `po/settings/hi.po`
- `po/app-menu/ar.po`, `po/app-menu/fa.po`, `po/app-menu/hi.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels. Preserve placeholders exactly in right-to-left strings and do not introduce directional control characters unless already necessary in the file style.
```

- [ ] **Step 6: Dispatch Group E subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `am ha sw yo`

Files you may edit:
- `po/am.po`, `po/ha.po`, `po/sw.po`, `po/yo.po`
- `po/settings/am.po`, `po/settings/ha.po`, `po/settings/sw.po`, `po/settings/yo.po`
- `po/app-menu/am.po`, `po/app-menu/ha.po`, `po/app-menu/sw.po`, `po/app-menu/yo.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels. Prefer clear, common UI wording; if a technical term is hard to localize, use a simple borrowed/common term rather than an obscure literal translation.
```

- [ ] **Step 7: Dispatch Group F subagent**

Prompt body after the shared header:

```markdown
Assigned languages: `th vi`

Files you may edit:
- `po/th.po`, `po/vi.po`
- `po/settings/th.po`, `po/settings/vi.po`
- `po/app-menu/th.po`, `po/app-menu/vi.po`

Focus especially on wizard setup strings, account/password wording, network setup, install confirmation, greeter login strings, settings page names, and start-menu search/power labels. Use concise UI wording where possible because start-menu labels have limited space.
```

- [ ] **Step 8: Review subagent file ownership before integration**

Run from repository root after all subagents return:

```bash
git status --short
```

Expected: modified files are limited to `po/*.po`, `po/settings/*.po`, and `po/app-menu/*.po`. If any subagent edited source code, tests, POT files, Makefiles, docs, or `.mo` files, inspect the diff and revert only the subagent's out-of-scope changes after confirming they are not user changes.

- [ ] **Step 9: Commit integrated language source updates**

Run:

```bash
git add po/*.po po/settings/*.po po/app-menu/*.po
git commit -m "chore: update release translations"
```

Expected: commit succeeds after language updates validate.

---

### Task 7: Compile Catalogs and Fix Validation Failures

**Files:**
- Modify existing wizard `.mo` files under `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` for the 22 supported languages.
- Modify existing settings `.mo` files under `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-settings.mo` for the 22 supported languages.
- Create app-menu `.mo` files under `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-app-menu.mo` for the 22 supported languages.
- Modify PO files reported by validation failures, limited to `po/*.po`, `po/settings/*.po`, and `po/app-menu/*.po` for the 22 supported languages.

- [ ] **Step 1: Compile all gettext catalogs**

Run from `po/`:

```bash
make mo
```

Expected: command exits 0 and writes `.mo` files for all 22 languages and all three domains.

- [ ] **Step 2: Run release catalog tests**

Run from repository root:

```bash
python -m pytest tests/test_translation_catalogs.py -v
```

Expected after translation completion and compilation: PASS.

- [ ] **Step 3: If catalog tests fail, fix the exact reported entries**

For each failure reported by `tests/test_translation_catalogs.py`, edit only the reported PO file and entry. Then validate every PO file so no repaired file is missed:

```bash
for f in po/*.po po/settings/*.po po/app-menu/*.po; do msgfmt --check --statistics --output-file=/dev/null "$f" || exit 1; done
```

Expected: command exits 0 for every file. Re-run:

```bash
python -m pytest tests/test_translation_catalogs.py -v
```

Expected: PASS before moving on.

- [ ] **Step 4: Verify compiled app-menu catalogs exist**

Run from repository root:

```bash
python - <<'PY'
from pathlib import Path

langs = "am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh".split()
domain = "adwaita-lite-app-menu"
missing = []
for lang in langs:
    path = Path("files/usr/share/locale") / lang / "LC_MESSAGES" / f"{domain}.mo"
    if not path.exists():
        missing.append(str(path))
if missing:
    raise SystemExit("Missing app-menu MO files:\n" + "\n".join(missing))
print(f"found {len(langs)} compiled app-menu catalogs")
PY
```

Expected: prints `found 22 compiled app-menu catalogs`.

- [ ] **Step 5: Commit compiled catalogs**

Run:

```bash
git add files/usr/share/locale po/*.po po/settings/*.po po/app-menu/*.po
git commit -m "chore: compile release translation catalogs"
```

Expected: commit succeeds. This commit may include `.po` fixes made in Step 3 and generated `.mo` files.

---

### Task 8: Final Verification and Release Notes

**Files:**
- Read: `docs/superpowers/specs/2026-04-29-release-translation-audit-design.md`
- Read: `po/Makefile`
- Read: `files/usr/bin/adwaita-lite-app-menu`
- Test: `tests/test_app_menu_i18n.py`
- Test: `tests/test_translation_catalogs.py`
- Test: `tests/test_language_names.py`
- Test: `tests/test_wizard_i18n.py`
- Test: `tests/test_app_menu_css.py`

- [ ] **Step 1: Run targeted test suite**

Run from repository root:

```bash
python -m pytest tests/test_language_names.py tests/test_wizard_i18n.py tests/test_app_menu_css.py tests/test_app_menu_i18n.py tests/test_translation_catalogs.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full translation build**

Run from `po/`:

```bash
make all
```

Expected: command exits 0. It may update POT, PO, and MO file timestamps or source references; inspect any resulting diff before committing.

- [ ] **Step 3: Run targeted test suite again after `make all`**

Run from repository root:

```bash
python -m pytest tests/test_language_names.py tests/test_wizard_i18n.py tests/test_app_menu_css.py tests/test_app_menu_i18n.py tests/test_translation_catalogs.py -v
```

Expected: PASS.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: any remaining changes are limited to translation source files, compiled catalogs, tests, `po/Makefile`, and `files/usr/bin/adwaita-lite-app-menu` from this plan.

- [ ] **Step 5: Commit final generated updates if `make all` changed files**

If Step 4 shows changes, run:

```bash
git add files/usr/bin/adwaita-lite-app-menu po/Makefile po/*.po po/settings/*.po po/app-menu files/usr/share/locale tests/test_app_menu_i18n.py tests/test_translation_catalogs.py
git commit -m "chore: finalize release translation audit"
```

Expected: commit succeeds. If Step 4 shows no changes, do not create an empty commit.

- [ ] **Step 6: Record any human localization review concerns**

If any subagent reported uncertain translations, append a concise note to the implementation summary in the final response. Use this format in the final response, not in a code file:

```markdown
Human review recommended for: am ha yo - subagents reported uncertainty around technical storage and power-action wording.
```

If no subagent reported uncertainties, state:

```markdown
No subagent-reported translation uncertainties remain.
```

---

## Self-Review Checklist

- Spec coverage: Tasks 1-4 implement separate app-menu gettext infrastructure; Task 6 updates existing wizard/settings and new app-menu translations; Task 7 compiles catalogs; Task 8 verifies tests/build and records human-review concerns.
- Placeholder safety: Task 5 validates fuzzy and untranslated entries; Task 6 prompts require exact placeholder preservation; Task 7 requires per-file `msgfmt --check` after fixes.
- Domain separation: Wizard, settings/greeter, and app-menu stay in separate domains throughout the plan.
- File ownership: Task 6 gives each subagent non-overlapping language files and forbids shared infrastructure edits.
- Release criteria: Task 8 reruns the targeted tests after `make all` and requires compiled `.mo` coverage for all 22 languages and all three domains.
