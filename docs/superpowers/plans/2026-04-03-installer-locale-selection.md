# Installer Locale Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Language page (Page 0) to the installer wizard that lets users pick their language, re-renders the entire wizard in that language, and writes the selected locale to the installed system.

**Architecture:** gettext-based i18n with runtime catalog switching. A `_retranslate()` method re-applies `_()` to all stored widget references when the language changes. A CLDR-sourced 23×23 JSON matrix provides native/translated language names for the picker UI.

**Tech Stack:** Python gettext, GNU gettext tools (xgettext, msgfmt), GTK4 (via PyGObject), Unicode CLDR data

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `po/language-names.json` | Create | 23×23 language name matrix (native + translated names) |
| `po/generate-language-names.py` | Create | Script to build language-names.json from CLDR JSON data |
| `files/usr/bin/adwaita-lite-setup-wizard` | Modify | Add gettext, Language page, retranslation, page shift |
| `tests/test_language_names.py` | Create | Validate language name data structure |
| `tests/test_wizard_i18n.py` | Create | Test gettext plumbing and retranslation registry |
| `po/adwaita-lite-setup-wizard.pot` | Create | Extracted source template |
| `po/*.po` | Create | One per language (22 files) |
| `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` | Create | Compiled message catalogs (22 directories) |
| `po/Makefile` | Create | POT extraction, PO update, MO compilation |

---

### Task 1: Language Name Data File

**Files:**
- Create: `po/generate-language-names.py`
- Create: `po/language-names.json`
- Test: `tests/test_language_names.py`

This task creates the 23×23 matrix of language names sourced from Unicode CLDR. Each language's name is provided in all 23 languages (e.g., "German" in English, "Deutsch" in German, "ドイツ語" in Japanese, etc.).

The 23 languages are: am, ar, de, en, es, fa, fr, ha, hi, it, ja, ko, nl, pl, pt, ru, sv, sw, th, tr, vi, yo, zh.

- [ ] **Step 1: Write the test for language name data structure**

```python
# tests/test_language_names.py
import json
from pathlib import Path

LANGUAGES = [
    "am", "ar", "de", "en", "es", "fa", "fr", "ha", "hi", "it",
    "ja", "ko", "nl", "pl", "pt", "ru", "sv", "sw", "th", "tr",
    "vi", "yo", "zh",
]

def _load():
    path = Path(__file__).resolve().parents[1] / "po" / "language-names.json"
    with open(path) as f:
        return json.load(f)


def test_all_languages_present():
    data = _load()
    assert set(data.keys()) == set(LANGUAGES)


def test_each_language_has_all_translations():
    data = _load()
    for lang_code, names in data.items():
        for target in LANGUAGES:
            assert target in names, f"{lang_code} missing translation for {target}"
            assert isinstance(names[target], str)
            assert len(names[target]) > 0, f"{lang_code}[{target}] is empty"


def test_native_names_are_correct():
    """Spot-check that each language's self-name matches known values."""
    data = _load()
    expected_native = {
        "am": "አማርኛ",
        "ar": "العربية",
        "de": "Deutsch",
        "en": "English",
        "es": "Español",
        "fa": "فارسی",
        "fr": "Français",
        "ha": "Hausa",
        "hi": "हिन्दी",
        "it": "Italiano",
        "ja": "日本語",
        "ko": "한국어",
        "nl": "Nederlands",
        "pl": "Polski",
        "pt": "Português",
        "ru": "Русский",
        "sv": "Svenska",
        "sw": "Kiswahili",
        "th": "ไทย",
        "tr": "Türkçe",
        "vi": "Tiếng Việt",
        "yo": "Yorùbá",
        "zh": "中文",
    }
    for code, native in expected_native.items():
        assert data[code][code] == native, (
            f"{code} native name: expected {native!r}, got {data[code][code]!r}"
        )


def test_matrix_is_complete():
    """23 languages × 23 translations = 529 entries."""
    data = _load()
    total = sum(len(v) for v in data.values())
    assert total == 23 * 23
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_language_names.py -v`
Expected: FAIL — `po/language-names.json` does not exist.

- [ ] **Step 3: Create the CLDR generation script**

This script downloads CLDR JSON locale data and extracts the 23 relevant language names from each locale. CLDR is the authoritative source for all language name translations, including the low-confidence languages (Amharic, Hausa, Swahili, Yoruba).

```python
#!/usr/bin/env python3
"""Generate po/language-names.json from Unicode CLDR data.

Downloads CLDR JSON locale data for each of our 23 supported languages
and extracts the language display names into a 23×23 matrix.

Usage:
    python po/generate-language-names.py
"""

import json
import sys
import urllib.request
from pathlib import Path

CLDR_BASE = (
    "https://raw.githubusercontent.com/unicode-cldr/"
    "cldr-localenames-full/master/main/{locale}/languages.json"
)

LANGUAGES = [
    "am", "ar", "de", "en", "es", "fa", "fr", "ha", "hi", "it",
    "ja", "ko", "nl", "pl", "pt", "ru", "sv", "sw", "th", "tr",
    "vi", "yo", "zh",
]

# CLDR native self-names (used as fallback verification)
NATIVE_NAMES = {
    "am": "አማርኛ",
    "ar": "العربية",
    "de": "Deutsch",
    "en": "English",
    "es": "Español",
    "fa": "فارسی",
    "fr": "Français",
    "ha": "Hausa",
    "hi": "हिन्दी",
    "it": "Italiano",
    "ja": "日本語",
    "ko": "한국어",
    "nl": "Nederlands",
    "pl": "Polski",
    "pt": "Português",
    "ru": "Русский",
    "sv": "Svenska",
    "sw": "Kiswahili",
    "th": "ไทย",
    "tr": "Türkçe",
    "vi": "Tiếng Việt",
    "yo": "Yorùbá",
    "zh": "中文",
}


def fetch_cldr_languages(locale: str) -> dict[str, str]:
    """Fetch CLDR language display names for a given locale."""
    url = CLDR_BASE.format(locale=locale)
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"  WARNING: failed to fetch {locale}: {exc}", file=sys.stderr)
        return {}

    # Navigate CLDR JSON structure
    locale_data = data.get("main", {}).get(locale, {})
    names = locale_data.get("localeDisplayNames", {}).get("languages", {})
    return names


def build_matrix() -> dict[str, dict[str, str]]:
    """Build the 23×23 language name matrix."""
    matrix: dict[str, dict[str, str]] = {}

    for source_lang in LANGUAGES:
        print(f"Fetching CLDR data for: {source_lang}")
        cldr_names = fetch_cldr_languages(source_lang)

        translations = {}
        for target_lang in LANGUAGES:
            name = cldr_names.get(target_lang, "")
            if not name:
                # Fallback: use native name if we can't find the translation
                name = NATIVE_NAMES.get(target_lang, target_lang)
                print(
                    f"  Using fallback for {source_lang}->{target_lang}: {name}",
                    file=sys.stderr,
                )
            translations[target_lang] = name

        matrix[source_lang] = translations

    return matrix


def main() -> None:
    matrix = build_matrix()

    # Verify completeness
    missing = []
    for src in LANGUAGES:
        for tgt in LANGUAGES:
            if not matrix.get(src, {}).get(tgt):
                missing.append(f"{src}->{tgt}")
    if missing:
        print(f"WARNING: {len(missing)} missing entries: {missing}", file=sys.stderr)

    out_path = Path(__file__).resolve().parent / "language-names.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matrix, f, ensure_ascii=False, indent=2, sort_keys=True)
    print(f"Wrote {out_path} ({sum(len(v) for v in matrix.values())} entries)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the generation script**

Run: `cd /var/home/race/ublue-mike && python po/generate-language-names.py`
Expected: `Wrote po/language-names.json (529 entries)` — one message per locale fetch, no warnings.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_language_names.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add po/language-names.json po/generate-language-names.py tests/test_language_names.py
git commit -m "feat(i18n): add CLDR-sourced 23×23 language name matrix"
```

---

### Task 2: gettext Plumbing and String Wrapping

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1-36` (imports)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:259-283` (constants)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:355-427` (init + shared UI)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:432-833` (all page builders)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1188-1205` (helpers)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1243-1268` (navigation)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1283-1341` (validation)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1347-1381` (summary)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1801-1858` (install steps)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1926-1954` (progress messages)
- Test: `tests/test_wizard_i18n.py`

This is the largest task. It wraps every user-facing string in `_()`, stores widget references for retranslation, and adds the `_retranslate()` method.

**Retranslation strategy:** A list `self._retranslatable` stores `(setter_callable, english_string)` tuples. A helper `self._tr(widget, text, method="set_label")` applies the translation immediately and registers the widget for later retranslation. `_retranslate()` iterates the list and re-applies `_()`.

- [ ] **Step 1: Write tests for the retranslation registry**

```python
# tests/test_wizard_i18n.py
"""Test the i18n plumbing without requiring GTK."""

import gettext
import json
from pathlib import Path
from unittest.mock import MagicMock


def test_retranslate_calls_all_setters():
    """Simulate the retranslatable list and verify _retranslate logic."""
    # This tests the core algorithm, not GTK widgets
    retranslatable = []

    def tr(setter, text):
        setter(text)
        retranslatable.append((setter, text))

    # Simulate registering widgets
    mock_label = MagicMock()
    mock_button = MagicMock()
    tr(mock_label.set_text, "Full Name")
    tr(mock_button.set_label, "Next")

    # Verify initial call
    mock_label.set_text.assert_called_with("Full Name")
    mock_button.set_label.assert_called_with("Next")

    # Simulate retranslate with identity function (no actual translation)
    def retranslate(translate_fn):
        for setter, english in retranslatable:
            setter(translate_fn(english))

    # Use a mock translator that uppercases
    retranslate(str.upper)
    mock_label.set_text.assert_called_with("FULL NAME")
    mock_button.set_label.assert_called_with("NEXT")


def test_gettext_fallback_returns_english():
    """When no .mo file exists, gettext returns the original string."""
    t = gettext.translation(
        "adwaita-lite-setup-wizard",
        localedir="/nonexistent",
        languages=["en"],
        fallback=True,
    )
    assert t.gettext("Next") == "Next"
    assert t.gettext("Full Name") == "Full Name"


def test_language_names_loadable():
    """The language names JSON can be loaded at runtime."""
    path = Path(__file__).resolve().parents[1] / "po" / "language-names.json"
    with open(path) as f:
        data = json.load(f)
    # Verify the "en" view: all 23 languages have English names
    en_names = data["en"]
    assert en_names["de"] == "German"
    assert en_names["ja"] == "Japanese"
    assert en_names["en"] == "English"
```

- [ ] **Step 2: Run tests to verify they fail appropriately**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_wizard_i18n.py -v`
Expected: `test_language_names_loadable` may fail if Task 1 not yet done; the mock-based tests should PASS since they don't depend on the wizard code.

- [ ] **Step 3: Add gettext imports and translation setup**

At the top of `files/usr/bin/adwaita-lite-setup-wizard`, add `import gettext` to the imports and set up the translation plumbing after the existing imports:

```python
import gettext
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("NM", "1.0")
from gi.repository import Gtk, Gdk, GLib, Gio, NM, Pango  # noqa: E402

APP_ID = "org.adwaitabluelite.SetupWizard"
TEXTDOMAIN = "adwaita-lite-setup-wizard"
LOCALEDIR = "/usr/share/locale"

# Initialize gettext — English fallback when no .mo file found
_translation = gettext.translation(
    TEXTDOMAIN, localedir=LOCALEDIR, languages=["en"], fallback=True
)
_ = _translation.gettext
```

- [ ] **Step 4: Wrap constant strings in _()**

The `SWAP_STRATEGIES` list and other module-level strings need wrapping. Because these are evaluated at import time (before language switching), they must be stored as English and translated at display time. Use a no-op marker `N_()` for extraction, then translate at runtime:

```python
# No-op marker for xgettext extraction (translated at display time)
def N_(s):
    return s

SWAP_STRATEGIES = [
    N_("Compressed RAM only (zram) — fast, but apps may close if memory fills"),
    N_("Compressed RAM + disk backup (zswap) — slower overflow to disk, apps stay open"),
]

SWAP_SIZES = ["2 GB", "4 GB", "8 GB", N_("Custom")]

FILESYSTEMS = ["ext4", "xfs", "btrfs"]  # Technical names — not translated
```

- [ ] **Step 5: Add retranslation infrastructure to SetupWizardWindow.__init__**

Add the `_retranslatable` list and `_tr` helper method at the start of `__init__`:

```python
class SetupWizardWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Adwaita-Lite Setup Wizard")
        self.set_default_size(800, 600)
        self.fullscreen()

        # Retranslation registry: (setter_callable, english_string) tuples
        self._retranslatable: list[tuple[callable, str]] = []
        self._selected_locale = "en_US.UTF-8"
        self._selected_lang = "en"
```

And the helper methods (add as instance methods after `__init__`):

```python
    def _tr(self, setter: callable, text: str) -> None:
        """Apply translated text and register for retranslation."""
        setter(_(text))
        self._retranslatable.append((setter, text))

    def _make_translated_label(self, text: str, css_class: str = "form-label") -> Gtk.Label:
        """Create a label with translatable text, registered for retranslation."""
        lbl = Gtk.Label(label=_(text))
        lbl.add_css_class(css_class)
        lbl.set_halign(Gtk.Align.START)
        self._retranslatable.append((lbl.set_label, text))
        return lbl

    def _retranslate(self) -> None:
        """Re-apply _() to every registered widget."""
        for setter, english in self._retranslatable:
            setter(_(english))
        # Re-apply dynamic texts
        self._update_navigation()
```

- [ ] **Step 6: Wrap all page builder strings**

Convert each `_build_*_page()` method to use `_()` and `self._tr()`. Here is the pattern for each page. Every hardcoded user-facing string gets wrapped.

**_build_account_page** — titles, subtitles, labels, placeholders:
```python
    def _build_account_page(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_halign(Gtk.Align.CENTER)
        wrapper.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(480, -1)

        self._account_title = Gtk.Label(label=_("Welcome to Adwaita-Lite"))
        self._account_title.add_css_class("welcome-title")
        self._account_title.set_halign(Gtk.Align.CENTER)
        card.append(self._account_title)
        self._retranslatable.append((self._account_title.set_label, "Welcome to Adwaita-Lite"))

        self._account_subtitle = Gtk.Label(label=_("Create your account to get started."))
        self._account_subtitle.add_css_class("welcome-subtitle")
        self._account_subtitle.set_halign(Gtk.Align.CENTER)
        card.append(self._account_subtitle)
        self._retranslatable.append((self._account_subtitle.set_label, "Create your account to get started."))

        card.append(self._make_translated_label("Full Name"))
        self._fullname_entry = Gtk.Entry()
        self._fullname_entry.set_placeholder_text(_("Jane Doe"))
        self._fullname_entry.add_css_class("form-entry")
        self._fullname_entry.set_hexpand(True)
        self._retranslatable.append((self._fullname_entry.set_placeholder_text, "Jane Doe"))
        card.append(self._fullname_entry)

        card.append(self._make_translated_label("Username"))
        self._username_entry = Gtk.Entry()
        self._username_entry.set_placeholder_text(_("janedoe"))
        self._username_entry.add_css_class("form-entry")
        self._username_entry.set_hexpand(True)
        card.append(self._username_entry)

        card.append(self._make_translated_label("Password"))
        self._password_entry = Gtk.PasswordEntry()
        self._password_entry.set_show_peek_icon(True)
        self._password_entry.add_css_class("form-entry")
        self._password_entry.set_hexpand(True)
        card.append(self._password_entry)

        card.append(self._make_translated_label("Confirm Password"))
        self._confirm_entry = Gtk.PasswordEntry()
        self._confirm_entry.set_show_peek_icon(True)
        self._confirm_entry.add_css_class("form-entry")
        self._confirm_entry.set_hexpand(True)
        self._confirm_entry.connect("activate", lambda _: self._go_next())
        card.append(self._confirm_entry)

        wrapper.append(card)
        scrolled.set_child(wrapper)
        return scrolled
```

Apply the same pattern to every page builder:

**_build_network_page:** Wrap `"Connect to Wi-Fi"`, `"Select a network to get online."`, `"Scanning for networks..."`, `"Rescan"`, `"Network Name (SSID)"`, `"Password"`, `"Connect"`, `"Join hidden network..."`. Store as `self._net_title`, `self._net_subtitle`, etc.

**_build_disk_page:** Wrap `"Choose Installation Disk"`, `"Select the target drive and installation options."`, `"Target drive"`, `"Filesystem"`, `"Memory management"`, `"Disk swap size"`, `"Custom size (GB)"`, `"zswap uses compressed RAM as a cache..."`, `"All data on the selected drive will be erased."`. Also translate the SWAP_STRATEGIES display strings with `_(s)` in the StringList population.

**_build_system_page:** Wrap `"System Setup"`, `"Timezone"`, `"Administrator account (sudo)"`, `"Root Password (optional)"`.

**_build_apps_page:** Wrap `"Install Apps"`, the subtitle text. App names/descriptions are not translated (they're Flatpak display names).

**_build_confirm_page:** Wrap `"Ready to Install"`, `"Review your settings and click Install to begin."`. Also update `_make_summary_row` to register its label for retranslation.

**_build_progress_page:** Wrap `"Installing..."`, `"Back"`, `"Skip"`, `"Retry"`, `"Reboot"`.

For the **Disk page** specifically, the SWAP_STRATEGIES StringList must be rebuilt on retranslation because `Gtk.StringList` does not support individual item updates. Store a reference to the dropdown model and rebuild it in `_retranslate()`.

- [ ] **Step 7: Update _make_label and _make_summary_row to support retranslation**

Replace the static `_make_label` helper. Since we now use `_make_translated_label` (an instance method), all existing `self._make_label("...")` calls should be changed to `self._make_translated_label("...")`.

Update `_make_summary_row` to register its label text:

```python
    def _make_summary_row(self, parent: Gtk.Box, label_text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=_(label_text))
        lbl.add_css_class("summary-row")
        lbl.set_halign(Gtk.Align.START)
        parent.append(lbl)
        self._retranslatable.append((lbl.set_label, label_text))

        value = Gtk.Label(label="—")
        value.add_css_class("summary-value")
        value.set_halign(Gtk.Align.START)
        parent.append(value)
        return value
```

Note: `_make_summary_row` is no longer `@staticmethod` — it's now an instance method (it already was called as `self._make_summary_row()`).

- [ ] **Step 8: Wrap navigation and validation strings**

In `_update_navigation()`:
```python
        self._next_button.set_label(
            _("Install") if self._current_page == PAGE_CONFIRM else _("Next")
        )
```

And the step indicator:
```python
        if not is_progress:
            self._step_label.set_text(_("Step {n} of {total}").format(
                n=visible_idx + 1, total=total
            ))
```

In all `_validate_*` methods, wrap every `self._set_status("...")` string:
```python
        self._set_status(_("Full name is required."))
        self._set_status(_("Username is required."))
        self._set_status(_("Username must be 32 characters or fewer."))
        self._set_status(_(
            "Username must start with a lowercase letter and contain "
            "only lowercase letters, numbers, and hyphens."
        ))
        self._set_status(_("Password is required."))
        self._set_status(_("Passwords do not match."))
        self._set_status(_(
            "Either enable administrator access or set a root password. "
            "Without one of these you will be locked out of system management."
        ))
        self._set_status(_("No target drives found. Connect a drive and restart the installer."))
        self._set_status(_("Custom swap size must be a positive whole number (in GB)."))
```

- [ ] **Step 9: Wrap summary and progress strings**

In `_populate_summary()`:
```python
        self._summary_network.set_text(_("Wired connection"))
        self._summary_network.set_text(_("No network (offline install)"))
        self._summary_memory.set_text(_("zram only (compressed RAM)"))
        self._summary_admin.set_text(_("Yes") if ... else _("No"))
        self._summary_root.set_text(_("Set") if ... else _("Not set"))
        self._summary_apps.set_text(_("No apps selected"))
```

In `_on_setup_clicked()`, wrap the install step labels:
```python
        self._steps: list[tuple[str, callable, str]] = [
            (_("Partitioning and installing"), self._step_bootc_install, "fatal"),
            (_("Configuring user account"), self._step_configure_user, "retry"),
            (_("Copying network configuration"), self._step_copy_network, "retry"),
        ]
        if self._setup_selected_apps:
            self._steps.append((
                _("Installing selected apps"),
                self._step_copy_flatpaks,
                "skippable",
            ))
        self._steps.append((_("Configuring memory management"), self._step_configure_memory, "retry"))
        self._steps.append((_("Finalizing"), self._step_finalize, "retry"))
```

In `_on_all_steps_done()`:
```python
        self._progress_title.set_text(_("Installation Complete!"))
```

In the reboot fallback:
```python
        self._progress_title.set_text(_("Reboot failed — please restart manually."))
```

In the network status messages:
```python
        self._wifi_empty_label.set_text(_("Scanning for networks..."))
        self._wifi_empty_label.set_text(_("No networks found."))
        self._net_status_label.set_text(_("Enter a network name."))
        self._net_status_label.set_text(_("Connected, but no internet access detected."))
```

The `"Connecting to {ssid}..."` and `"Connected to {ssid}!"` messages use f-strings with a variable — use `.format()` with gettext:
```python
        self._net_status_label.set_text(
            _("Connecting to {ssid}...").format(ssid=ssid)
        )
        self._net_status_label.set_text(
            _("Connected to {ssid}!").format(ssid=self._connected_ssid or "network")
        )
```

- [ ] **Step 10: Run tests**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_wizard_i18n.py tests/test_language_names.py -v`
Expected: All tests PASS.

- [ ] **Step 11: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard tests/test_wizard_i18n.py
git commit -m "feat(i18n): wrap all wizard strings in gettext, add retranslation registry"
```

---

### Task 3: Page Constant Shift and Language Page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:270-276` (page constants)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:355-421` (init, stack, navigation)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1211-1278` (navigation methods)

This task adds `PAGE_LANGUAGE = 0`, shifts all existing constants by 1, builds the Language page UI, and wires it into the navigation flow.

- [ ] **Step 1: Shift page constants**

```python
PAGE_LANGUAGE = 0
PAGE_NETWORK = 1
PAGE_DISK = 2
PAGE_ACCOUNT = 3
PAGE_SYSTEM = 4
PAGE_APPS = 5
PAGE_CONFIRM = 6
PAGE_PROGRESS = 7
```

- [ ] **Step 2: Load language names data in __init__**

Add to `__init__`, before the page stack creation:

```python
        # Load language name matrix
        _lang_names_path = Path("/usr/share/adwaita-lite/language-names.json")
        if not _lang_names_path.exists():
            # Dev fallback: load from source tree
            _lang_names_path = Path(__file__).resolve().parents[0] / "../../po/language-names.json"
            if not _lang_names_path.exists():
                _lang_names_path = Path("/var/home/race/ublue-mike/po/language-names.json")
        with open(_lang_names_path) as f:
            self._language_names = json.load(f)
```

Also update the `language-names.json` install path. Add to `build.sh`:
```bash
install -Dm644 /ctx/po/language-names.json /usr/share/adwaita-lite/language-names.json
```

- [ ] **Step 3: Build the Language page**

Add the `_build_language_page()` method. This creates a scrollable list where each row shows the language's native name (bold, left) and its name in the currently selected language (dimmer, right). Languages with regional variants expand on selection.

```python
    # Language page data: (lang_code, default_locale, [variant_locales])
    # Variants use (locale_code, display_label) tuples
    LANGUAGE_ENTRIES = [
        ("am", "am_ET.UTF-8", []),
        ("ar", "ar_EG.UTF-8", [
            ("ar_SA.UTF-8", "العربية (السعودية)"),
            ("ar_MA.UTF-8", "العربية (المغرب)"),
            ("ar_DZ.UTF-8", "العربية (الجزائر)"),
            ("ar_TN.UTF-8", "العربية (تونس)"),
            ("ar_IQ.UTF-8", "العربية (العراق)"),
            ("ar_JO.UTF-8", "العربية (الأردن)"),
            ("ar_LB.UTF-8", "العربية (لبنان)"),
            ("ar_SY.UTF-8", "العربية (سوريا)"),
        ]),
        ("de", "de_DE.UTF-8", [
            ("de_AT.UTF-8", "Deutsch (Österreich)"),
            ("de_CH.UTF-8", "Deutsch (Schweiz)"),
        ]),
        ("en", "en_US.UTF-8", [
            ("en_GB.UTF-8", "English (United Kingdom)"),
            ("en_AU.UTF-8", "English (Australia)"),
            ("en_CA.UTF-8", "English (Canada)"),
        ]),
        ("es", "es_ES.UTF-8", [
            ("es_MX.UTF-8", "Español (México)"),
            ("es_AR.UTF-8", "Español (Argentina)"),
            ("es_CO.UTF-8", "Español (Colombia)"),
            ("es_CL.UTF-8", "Español (Chile)"),
            ("es_PE.UTF-8", "Español (Perú)"),
        ]),
        ("fa", "fa_IR.UTF-8", []),
        ("fr", "fr_FR.UTF-8", [
            ("fr_CA.UTF-8", "Français (Canada)"),
            ("fr_BE.UTF-8", "Français (Belgique)"),
            ("fr_CH.UTF-8", "Français (Suisse)"),
        ]),
        ("ha", "ha_NG.UTF-8", []),
        ("hi", "hi_IN.UTF-8", []),
        ("it", "it_IT.UTF-8", []),
        ("ja", "ja_JP.UTF-8", []),
        ("ko", "ko_KR.UTF-8", []),
        ("nl", "nl_NL.UTF-8", [
            ("nl_BE.UTF-8", "Nederlands (België)"),
        ]),
        ("pl", "pl_PL.UTF-8", []),
        ("pt", "pt_BR.UTF-8", [
            ("pt_PT.UTF-8", "Português (Portugal)"),
        ]),
        ("ru", "ru_RU.UTF-8", []),
        ("sv", "sv_SE.UTF-8", []),
        ("sw", "sw_KE.UTF-8", [
            ("sw_TZ.UTF-8", "Kiswahili (Tanzania)"),
        ]),
        ("th", "th_TH.UTF-8", []),
        ("tr", "tr_TR.UTF-8", []),
        ("vi", "vi_VN.UTF-8", []),
        ("yo", "yo_NG.UTF-8", []),
        ("zh", "zh_CN.UTF-8", [
            ("zh_CN.UTF-8", "简体中文 (Simplified)"),
            ("zh_TW.UTF-8", "繁體中文 (Traditional)"),
            ("zh_HK.UTF-8", "繁體中文 (Hong Kong)"),
        ]),
    ]

    def _build_language_page(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_halign(Gtk.Align.CENTER)
        wrapper.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(480, -1)

        # Title — always "Language" in English since no language is selected yet
        self._lang_title = Gtk.Label(label="Language")
        self._lang_title.add_css_class("welcome-title")
        self._lang_title.set_halign(Gtk.Align.CENTER)
        card.append(self._lang_title)

        self._lang_subtitle = Gtk.Label(label=_("Select your language."))
        self._lang_subtitle.add_css_class("welcome-subtitle")
        self._lang_subtitle.set_halign(Gtk.Align.CENTER)
        card.append(self._lang_subtitle)
        self._retranslatable.append((self._lang_subtitle.set_label, "Select your language."))

        # Language list
        self._lang_list = Gtk.ListBox()
        self._lang_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._lang_list.set_vexpand(False)

        self._lang_rows: list[dict] = []  # Track rows for translated name updates

        for lang_code, default_locale, variants in self.LANGUAGE_ENTRIES:
            native_name = self._language_names[lang_code][lang_code]
            translated_name = self._language_names.get(
                self._selected_lang, {}
            ).get(lang_code, native_name)

            row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

            # Main language row
            main_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            main_row.add_css_class("wifi-row")
            main_row.set_margin_bottom(4)

            native_lbl = Gtk.Label(label=native_name)
            native_lbl.add_css_class("wifi-ssid")
            native_lbl.set_halign(Gtk.Align.START)
            native_lbl.set_hexpand(True)
            main_row.append(native_lbl)

            trans_lbl = Gtk.Label(label=translated_name)
            trans_lbl.add_css_class("wifi-detail")
            trans_lbl.set_halign(Gtk.Align.END)
            main_row.append(trans_lbl)

            row_box.append(main_row)

            # Variant sub-rows (hidden by default)
            variant_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            variant_box.set_visible(False)
            variant_box.set_margin_start(24)

            variant_buttons: list[tuple[Gtk.CheckButton, str]] = []
            if variants:
                # Default variant
                default_btn = Gtk.CheckButton(label=default_locale.replace(".UTF-8", ""))
                default_btn.set_active(True)
                default_btn.add_css_class("form-label")
                variant_box.append(default_btn)
                variant_buttons.append((default_btn, default_locale))

                for var_locale, var_label in variants:
                    btn = Gtk.CheckButton(label=var_label, group=default_btn)
                    btn.add_css_class("form-label")
                    variant_box.append(btn)
                    variant_buttons.append((btn, var_locale))

            row_box.append(variant_box)

            row_data = {
                "code": lang_code,
                "default_locale": default_locale,
                "translated_label": trans_lbl,
                "variant_box": variant_box,
                "variant_buttons": variant_buttons,
                "row_box": row_box,
                "main_row": main_row,
            }
            self._lang_rows.append(row_data)

            # Click handler
            gesture = Gtk.GestureClick()
            gesture.connect("released", self._on_language_row_clicked, row_data)
            main_row.add_controller(gesture)

            list_row = Gtk.ListBoxRow()
            list_row.set_child(row_box)
            list_row.set_activatable(False)
            self._lang_list.append(list_row)

        card.append(self._lang_list)

        # Highlight English as the default selection
        for row_data in self._lang_rows:
            if row_data["code"] == "en":
                row_data["main_row"].add_css_class("wifi-connected")
                break

        wrapper.append(card)
        scrolled.set_child(wrapper)
        return scrolled

    def _on_language_row_clicked(self, gesture, n_press, x, y, row_data: dict) -> None:
        """Handle language row selection."""
        lang_code = row_data["code"]
        variants = row_data["variant_buttons"]

        # Toggle variant expansion if this language has variants
        if variants:
            vbox = row_data["variant_box"]
            # Collapse all other variant boxes
            for other in self._lang_rows:
                if other["code"] != lang_code:
                    other["variant_box"].set_visible(False)
            vbox.set_visible(not vbox.get_visible())

        # Apply language selection
        self._selected_lang = lang_code
        if variants:
            # Use whichever variant radio is selected
            locale = row_data["default_locale"]
            for btn, var_locale in variants:
                if btn.get_active():
                    locale = var_locale
                    break
            self._selected_locale = locale
        else:
            self._selected_locale = row_data["default_locale"]

        # Highlight selected row
        for other in self._lang_rows:
            other["main_row"].remove_css_class("wifi-connected")
        row_data["main_row"].add_css_class("wifi-connected")

        # Switch language
        self._switch_language(lang_code)
```

- [ ] **Step 4: Wire the language page into the stack and navigation**

In `__init__`, insert the language page as the first page in the stack:

```python
        self._stack.add_named(self._build_language_page(), "language")
        self._stack.add_named(self._build_network_page(), "network")
        # ... rest stays the same
```

Update `_current_page` initial value:
```python
        self._current_page = PAGE_LANGUAGE  # Start at Language page
```

Update `_get_pages()`:
```python
    def _get_pages(self) -> list[str]:
        pages = ["language", "network", "disk", "account", "system", "apps", "confirm", "progress"]
        if self._network_skipped:
            pages.remove("network")
        return pages
```

Update `_get_first_page()`:
```python
    def _get_first_page(self) -> int:
        return PAGE_LANGUAGE
```

Update `_update_navigation()` — the page_names dict:
```python
    def _update_navigation(self) -> None:
        page_names = {
            PAGE_LANGUAGE: "language",
            PAGE_NETWORK: "network", PAGE_DISK: "disk",
            PAGE_ACCOUNT: "account", PAGE_SYSTEM: "system",
            PAGE_APPS: "apps", PAGE_CONFIRM: "confirm",
            PAGE_PROGRESS: "progress",
        }
```

Update the focus logic to include language page:
```python
        if self._current_page == PAGE_LANGUAGE:
            pass  # List box handles its own focus
        elif self._current_page == PAGE_DISK:
            self._drive_dropdown.grab_focus()
        elif self._current_page == PAGE_ACCOUNT:
            self._fullname_entry.grab_focus()
        elif self._current_page == PAGE_SYSTEM:
            self._tz_dropdown.grab_focus()
```

Update the step label to show "Step 1 of 7" (7 pages excluding progress):
```python
        self._step_label = Gtk.Label(label=_("Step {n} of {total}").format(n=1, total=7))
```

- [ ] **Step 5: Add _switch_language stub**

Task 4 will implement the full version, but the language page click handler needs it now:

```python
    def _switch_language(self, lang_code: str) -> None:
        """Stub — full implementation in Task 4."""
        pass
```

- [ ] **Step 6: Update _go_next to skip from language to disk when network is skipped**

The current `_go_next` increments `_current_page` by 1. Since network can be skipped, add:

```python
    def _go_next(self) -> None:
        if not self._validate_page(self._current_page):
            return

        if self._current_page == PAGE_CONFIRM:
            self._on_setup_clicked()
            return

        self._current_page += 1
        # Skip network page if no WiFi
        if self._current_page == PAGE_NETWORK and self._network_skipped:
            self._current_page += 1
        self._set_status("")
        self._update_navigation()

        if self._current_page == PAGE_CONFIRM:
            self._populate_summary()
```

Update `_go_back` similarly:
```python
    def _go_back(self) -> None:
        if self._current_page <= self._get_first_page():
            return
        self._current_page -= 1
        # Skip network page going backwards if skipped
        if self._current_page == PAGE_NETWORK and self._network_skipped:
            self._current_page -= 1
        self._set_status("")
        self._update_navigation()
```

- [ ] **Step 7: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard build_files/build.sh
git commit -m "feat(i18n): add Language page (Page 0), shift page constants"
```

---

### Task 4: Runtime Language Switching

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` (add `_switch_language` method)

When the user taps a language in the list, the wizard immediately re-renders all UI text.

- [ ] **Step 1: Implement _switch_language()**

```python
    def _switch_language(self, lang_code: str) -> None:
        """Switch the active translation and re-render all UI text."""
        global _, _translation

        try:
            _translation = gettext.translation(
                TEXTDOMAIN,
                localedir=LOCALEDIR,
                languages=[lang_code],
                fallback=True,
            )
        except Exception:
            _translation = gettext.NullTranslations()

        _ = _translation.gettext

        # Re-render all registered translatable widgets
        self._retranslate()

        # Update the translated name column in the language list
        self._update_language_list_translations()
```

- [ ] **Step 2: Implement _update_language_list_translations()**

```python
    def _update_language_list_translations(self) -> None:
        """Update the 'translated name' column in the language list."""
        lang_names = self._language_names.get(self._selected_lang, {})
        for row_data in self._lang_rows:
            code = row_data["code"]
            translated = lang_names.get(code, row_data["translated_label"].get_text())
            row_data["translated_label"].set_text(translated)
```

- [ ] **Step 3: Handle the SWAP_STRATEGIES StringList rebuild in _retranslate()**

The SWAP_STRATEGIES dropdown uses a `Gtk.StringList` which can't be updated in-place. Add this to `_retranslate()`:

```python
    def _retranslate(self) -> None:
        """Re-apply _() to every registered widget."""
        for setter, english in self._retranslatable:
            setter(_(english))

        # Rebuild swap strategy dropdown model (StringList not updatable in-place)
        current_swap = self._swap_strategy_dropdown.get_selected()
        new_model = Gtk.StringList.new([_(s) for s in SWAP_STRATEGIES])
        self._swap_strategy_dropdown.set_model(new_model)
        self._swap_strategy_dropdown.set_selected(current_swap)

        # Rebuild swap size dropdown model
        current_size = self._swap_size_dropdown.get_selected()
        new_size_model = Gtk.StringList.new(
            [s if s != "Custom" else _("Custom") for s in SWAP_SIZES]
        )
        self._swap_size_dropdown.set_model(new_size_model)
        self._swap_size_dropdown.set_selected(current_size)

        # Re-apply dynamic texts
        self._update_navigation()
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(i18n): implement runtime language switching with _retranslate()"
```

---

### Task 5: Write Selected Locale to Installed System

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1652-1658` (`_step_configure_user`)
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:1801-1820` (`_on_setup_clicked`)

- [ ] **Step 1: Capture selected locale in _on_setup_clicked()**

Add after the existing form value captures:

```python
        # Language (already stored from language page selection)
        self._setup_locale = self._selected_locale
```

- [ ] **Step 2: Update _step_configure_user() to write the selected locale**

Replace the hardcoded locale line:

```python
        # Set timezone and locale
        try:
            tz = self._setup_timezone
            localtime = Path(deploy) / "etc" / "localtime"
            localtime.unlink(missing_ok=True)
            localtime.symlink_to(f"/usr/share/zoneinfo/{tz}")
            (Path(deploy) / "etc" / "locale.conf").write_text(
                f"LANG={self._setup_locale}\n"
            )
        except OSError as exc:
            return f"Failed to configure timezone/locale: {exc}"
```

- [ ] **Step 3: Add Language to the summary page**

In `_build_confirm_page()`, add a Language summary row before the Network row:

```python
        self._summary_language = self._make_summary_row(card, "Language")
        self._summary_network = self._make_summary_row(card, "Network")
```

In `_populate_summary()`, add:

```python
        # Language
        native_name = self._language_names[self._selected_lang][self._selected_lang]
        locale_display = self._selected_locale.replace(".UTF-8", "")
        self._summary_language.set_text(f"{native_name} ({locale_display})")
```

- [ ] **Step 4: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat(i18n): write selected locale to installed system, show in summary"
```

---

### Task 6: Translation Files (POT, PO, MO)

**Files:**
- Create: `po/Makefile`
- Create: `po/adwaita-lite-setup-wizard.pot`
- Create: `po/*.po` (22 files)
- Create: `files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` (22 directories)

- [ ] **Step 1: Create po/Makefile**

```makefile
DOMAIN = adwaita-lite-setup-wizard
SOURCE = ../files/usr/bin/$(DOMAIN)
POTFILE = $(DOMAIN).pot
LOCALEDIR = ../files/usr/share/locale

LANGUAGES = am ar de es fa fr ha hi it ja ko nl pl pt ru sv sw th tr vi yo zh

PO_FILES = $(LANGUAGES:%=%.po)
MO_FILES = $(LANGUAGES:%=$(LOCALEDIR)/%/LC_MESSAGES/$(DOMAIN).mo)

.PHONY: pot po mo clean

pot: $(POTFILE)

$(POTFILE): $(SOURCE)
	xgettext --language=Python --keyword=_ --keyword=N_ \
	    --output=$(POTFILE) --from-code=UTF-8 \
	    --package-name="$(DOMAIN)" \
	    $(SOURCE)

po: $(PO_FILES)

%.po: $(POTFILE)
	@if [ -f $@ ]; then \
	    msgmerge --update --no-fuzzy-matching $@ $(POTFILE); \
	else \
	    msginit --input=$(POTFILE) --output=$@ --locale=$* --no-translator; \
	fi

mo: $(MO_FILES)

$(LOCALEDIR)/%/LC_MESSAGES/$(DOMAIN).mo: %.po
	@mkdir -p $(dir $@)
	msgfmt --output=$@ $<

clean:
	rm -f $(POTFILE)
	rm -f $(MO_FILES)

all: pot po mo
```

- [ ] **Step 2: Extract POT template**

Run: `cd /var/home/race/ublue-mike/po && make pot`
Expected: Creates `adwaita-lite-setup-wizard.pot` with all `_()` and `N_()` marked strings.

- [ ] **Step 3: Verify the POT file contains expected strings**

Run: `grep -c msgid /var/home/race/ublue-mike/po/adwaita-lite-setup-wizard.pot`
Expected: ~60-70 translatable strings (count will depend on exact wrapping).

Spot-check:
Run: `grep "Full Name" /var/home/race/ublue-mike/po/adwaita-lite-setup-wizard.pot`
Expected: `msgid "Full Name"`

- [ ] **Step 4: Initialize PO files**

Run: `cd /var/home/race/ublue-mike/po && make po`
Expected: Creates 22 `.po` files, one per non-English language.

- [ ] **Step 5: Generate translations for high-confidence languages**

For languages where Claude has strong comprehension (de, es, fr, it, ja, ko, nl, pl, pt, ru, sv, th, tr, vi, zh, hi, fa), generate translations by filling in the `msgstr` entries in each `.po` file.

This step is done by having Claude translate each PO file. Work through them one at a time. For each PO file:
1. Read the file
2. Fill in all `msgstr ""` entries with the translated text
3. Save the file

**Important translation notes:**
- Keep `{ssid}`, `{n}`, `{total}` and other format placeholders intact
- Keep technical terms untranslated: ext4, xfs, btrfs, zram, zswap, bootc, Flatpak, sudo
- Button labels should be concise (1-2 words)
- Error messages should be clear and direct

- [ ] **Step 6: Generate translations for low-confidence languages**

For Amharic (am), Hausa (ha), Swahili (sw), and Yoruba (yo), generate initial translations using web-assisted tools. These should be flagged for community review:
- Add a comment `# NEEDS-REVIEW` above each translated entry
- Use CLDR patterns and verified vocabulary as anchors

- [ ] **Step 7: Compile MO files**

Run: `cd /var/home/race/ublue-mike/po && make mo`
Expected: Creates 22 `.mo` files under `files/usr/share/locale/*/LC_MESSAGES/`.

Verify: `ls files/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo | wc -l`
Expected: `22`

- [ ] **Step 8: Commit**

```bash
git add po/ files/usr/share/locale/
git commit -m "feat(i18n): add POT, PO translations, and compiled MO files for 22 languages"
```

---

### Task 7: Build Integration

**Files:**
- Modify: `build_files/build.sh`
- Modify: `po/language-names.json` install path

- [ ] **Step 1: Update build.sh to install language data**

The `.mo` files are already in the correct location under `files/` and get installed via the existing `cp -a /ctx/files/. /` line. The only addition needed is installing `language-names.json`:

Add this line to `build_files/build.sh` after the `cp -a /ctx/files/. /` line:

```bash
# Install language name matrix for installer wizard
install -Dm644 /ctx/po/language-names.json /usr/share/adwaita-lite/language-names.json
```

- [ ] **Step 2: Update the wizard to use the installed path**

Verify that the `__init__` code in the wizard looks for `/usr/share/adwaita-lite/language-names.json` first (already done in Task 3 Step 2).

- [ ] **Step 3: Verify the build works**

Run: `cd /var/home/race/ublue-mike && podman build -t adwaita-lite-test .`
Expected: Build succeeds. The container has:
- `/usr/share/locale/*/LC_MESSAGES/adwaita-lite-setup-wizard.mo` (22 locales)
- `/usr/share/adwaita-lite/language-names.json`

- [ ] **Step 4: Run all tests**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add build_files/build.sh
git commit -m "build: install language names and locale data in container image"
```

---

## Task Dependency Graph

```
Task 1 (language names data)
    ↓
Task 2 (gettext + string wrapping)  ←  depends on Task 1 for test_language_names_loadable
    ↓
Task 3 (page shift + language page)  ←  depends on Task 2 for _() and retranslation
    ↓
Task 4 (runtime switching)  ←  depends on Task 3 for language page UI
    ↓
Task 5 (locale.conf writing)  ←  depends on Task 4 for _selected_locale
    ↓
Task 6 (translation files)  ←  depends on Task 2 for _() wrapped strings
    ↓
Task 7 (build integration)  ←  depends on Tasks 1, 5, 6
```

Tasks 1–5 are strictly sequential. Task 6 can start after Task 2 (POT extraction needs the wrapped strings). Task 7 is last.
