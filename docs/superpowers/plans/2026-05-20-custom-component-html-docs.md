# Custom Component HTML Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build contributor/agent-oriented static HTML documentation for every known Adwaita-Lite custom component area, starting with the setup wizard and ending with a complete linked component documentation set with strong visual quality and high information density.

**Architecture:** Add static files under `docs/components/` with no build system, packaging hook, runtime dependency, or generated output. Use page-specific HTML structures instead of a rigid template: flow strips, cards, source maps, state maps, callouts, and compact tables should be used where they make the component easier to understand. Use a small pytest file to verify the docs exist, link together, reference real source files, and include the source-navigation anchors future agents need.

**Tech Stack:** Static HTML/CSS, Python `pytest`, standard-library `html.parser`, existing repository source files.

---

## File Structure

- Create: `docs/components/index.html`
  - Landing page for future contributors/agents.
  - Owns the coverage table and links to all component docs.
- Create: `docs/components/setup-wizard.html`
  - Deep doc for `files/usr/bin/adwaita-lite-setup-wizard`.
  - Owns wizard flow, component map, CSS class map, state hooks, tests, and safe-edit guidance.
- Create: `docs/components/app-menu.html`
  - Deep doc for `files/usr/bin/adwaita-lite-app-menu`.
  - Owns layer-shell behavior, data model, grid/list rendering, sizing modes, search/filtering, power confirmation, and twilight theming.
- Create: `docs/components/greeter.html`
  - Deep doc for `files/usr/bin/adwaita-lite-greeter`.
  - Owns kiosk login layout, palette/accent loading, session selector, greetd IPC, login states, and safe-edit guidance.
- Create: `docs/components/settings.html`
  - Deep doc for `files/usr/lib/adwaita-lite/settings/`.
  - Owns settings app architecture and custom UI surfaces: wallpaper tiles, accent swatches, panel layout editor, pinned apps picker, keyboard shortcut capture, network sub-pages, display revert dialogs, and page-specific CSS.
- Create: `docs/components/theme-system.html`
  - Deep doc for shared palette/theme behavior.
  - Owns `palette.json`, `theme.py`, generated CSS, settings CSS, Waybar relationship, app-menu/greeter palette use, dark/light/high-contrast/twilight conventions.
- Create: `tests/test_component_docs.py`
  - Lightweight documentation contract tests using only Python standard library and pytest.
  - Verifies page presence, internal links, source path references, high-value component/source anchors, and visual-structure markers.

Do not modify runtime source, packaging, service files, `.po` files, or `README.md` for this feature.

---

### Task 1: Add Documentation Contract Tests

**Files:**
- Create: `tests/test_component_docs.py`
- Read-only references: `files/usr/bin/adwaita-lite-setup-wizard`, `files/usr/bin/adwaita-lite-app-menu`, `files/usr/bin/adwaita-lite-greeter`, `files/usr/lib/adwaita-lite/settings/`, `files/usr/lib/adwaita-lite/theme.py`, `files/usr/share/adwaita-lite/palette.json`

- [ ] **Step 1: Write the failing docs contract test**

Create `tests/test_component_docs.py` with this exact content:

```python
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/components"

PAGES = {
    "index": DOCS / "index.html",
    "setup-wizard": DOCS / "setup-wizard.html",
    "app-menu": DOCS / "app-menu.html",
    "greeter": DOCS / "greeter.html",
    "settings": DOCS / "settings.html",
    "theme-system": DOCS / "theme-system.html",
}

SOURCE_PATHS = [
    "files/usr/bin/adwaita-lite-setup-wizard",
    "files/usr/bin/adwaita-lite-app-menu",
    "files/usr/bin/adwaita-lite-greeter",
    "files/usr/lib/adwaita-lite/settings/",
    "files/usr/lib/adwaita-lite/settings/css/style.css",
    "files/usr/lib/adwaita-lite/theme.py",
    "files/usr/share/adwaita-lite/palette.json",
]

PAGE_SOURCE_PATHS = {
    "setup-wizard": ["files/usr/bin/adwaita-lite-setup-wizard"],
    "app-menu": ["files/usr/bin/adwaita-lite-app-menu"],
    "greeter": ["files/usr/bin/adwaita-lite-greeter"],
    "settings": [
        "files/usr/lib/adwaita-lite/settings/",
        "files/usr/lib/adwaita-lite/settings/css/style.css",
    ],
    "theme-system": [
        "files/usr/share/adwaita-lite/palette.json",
        "files/usr/lib/adwaita-lite/theme.py",
    ],
}

VISUAL_MARKERS = [
    "flow-strip",
    "component-grid",
    "source-map",
    "state-map",
    "safe-edit",
    "density-note",
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href")
        if href:
            self.links.append(href)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing docs page: {path}"
    return path.read_text(encoding="utf-8")


def _links(path: Path) -> list[str]:
    parser = LinkParser()
    parser.feed(_text(path))
    return parser.links


def test_component_docs_pages_exist():
    for name, path in PAGES.items():
        assert path.is_file(), f"missing docs page for {name}: {path}"


def test_component_docs_index_links_to_every_page():
    links = set(_links(PAGES["index"]))

    for name in ("setup-wizard", "app-menu", "greeter", "settings", "theme-system"):
        assert f"{name}.html" in links, f"index missing link to {name}.html"


def test_component_docs_pages_link_back_to_index():
    for name, path in PAGES.items():
        if name == "index":
            continue
        assert "index.html" in set(_links(path)), f"{name} does not link back to index"


def test_component_docs_reference_existing_source_paths():
    combined = "\n".join(_text(path) for path in PAGES.values())

    for source_path in SOURCE_PATHS:
        assert (ROOT / source_path).exists(), f"source path no longer exists: {source_path}"
        assert source_path in combined, f"docs do not reference {source_path}"


def test_component_pages_reference_their_own_source_paths():
    for page_name, source_paths in PAGE_SOURCE_PATHS.items():
        html = _text(PAGES[page_name])
        for source_path in source_paths:
            assert source_path in html, f"{page_name} doc does not reference {source_path}"


def test_component_docs_use_dense_visual_structures():
    for name, path in PAGES.items():
        html = _text(path)
        present = {marker for marker in VISUAL_MARKERS if marker in html}
        assert len(present) >= 2, (
            f"{name} should use at least two component-specific visual structures, "
            f"not plain Markdown-like prose; found: {sorted(present)}"
        )


def test_setup_wizard_doc_covers_major_ui_anchors():
    html = _text(PAGES["setup-wizard"])
    required = [
        "SetupWizardWindow",
        "_build_language_page",
        "_build_network_page",
        "_build_disk_page",
        "_build_account_page",
        "_build_system_page",
        "_build_apps_page",
        "_build_confirm_page",
        "_build_progress_page",
        "card",
        "welcome-title",
        "form-entry",
        "dark-list",
        "wifi-row",
        "keyboard-panel",
        "app-row",
        "log-view",
        "tests/test_setup_wizard_gtk_smoke.py",
        "tests/test_setup_wizard_app_selection.py",
    ]

    for term in required:
        assert term in html, f"setup wizard doc missing required anchor: {term}"


def test_app_menu_doc_covers_major_ui_anchors():
    html = _text(PAGES["app-menu"])
    required = [
        "AppMenu",
        "AppItem",
        "_build_css",
        "_menu_metrics",
        "_make_flowbox",
        "_make_gridview",
        "_build_power_bar",
        "Gtk4LayerShell",
        "app-menu-surface",
        "app-menu-grid",
        "app-menu-tile",
        "app-menu-power-bar",
        "tests/test_app_menu_css.py",
    ]

    for term in required:
        assert term in html, f"app menu doc missing required anchor: {term}"


def test_greeter_doc_covers_major_ui_anchors():
    html = _text(PAGES["greeter"])
    required = [
        "GreeterWindow",
        "GreetdClient",
        "_build_css",
        "_load_palettes",
        "_load_theme",
        "clock",
        "date",
        "card",
        "session-dropdown",
        "login-button",
        "switch-user",
    ]

    for term in required:
        assert term in html, f"greeter doc missing required anchor: {term}"


def test_settings_doc_covers_major_custom_surfaces():
    html = _text(PAGES["settings"])
    required = [
        "SettingsWindow",
        "BasePage",
        "AppearancePage",
        "PanelPage",
        "KeyboardPage",
        "NetworkPage",
        "DisplayPage",
        "wallpaper-tile",
        "accent-swatch",
        "Adw.NavigationView",
        "Adw.AlertDialog",
        "files/usr/lib/adwaita-lite/settings/css/style.css",
        "tests/test_settings_css.py",
        "docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md",
    ]

    for term in required:
        assert term in html, f"settings doc missing required anchor: {term}"


def test_theme_system_doc_covers_major_theme_anchors():
    html = _text(PAGES["theme-system"])
    required = [
        "files/usr/share/adwaita-lite/palette.json",
        "files/usr/lib/adwaita-lite/theme.py",
        "gtk_color_defines",
        "_build_accent_css",
        "_build_twilight_css",
        "DARK_THEME_COLORS",
        "@accent_color",
        "@window_bg_color",
        "panel_twilight",
        "high_contrast",
    ]

    for term in required:
        assert term in html, f"theme system doc missing required anchor: {term}"
```

- [ ] **Step 2: Run the new test and verify it fails for missing docs**

Run: `pytest tests/test_component_docs.py -v`

Expected: FAIL. The first failure should report missing files under `docs/components/`, because no component docs exist yet.

- [ ] **Step 3: Check the failure is the expected failure**

If the failure is an import error, syntax error, or path error in `tests/test_component_docs.py`, fix the test before continuing. The expected failure must be a missing-doc assertion such as `missing docs page for index`.

---

### Task 2: Create Component Documentation Index

**Files:**
- Create: `docs/components/index.html`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create the docs directory and index page**

Create `docs/components/index.html`. Use semantic static HTML. Include:

- `<title>Adwaita-Lite Component Documentation</title>`
- Header text: `Custom Component Documentation`
- A short explanation that these docs are for contributors and agents, not end users.
- A coverage table linking to:
  - `setup-wizard.html`
  - `app-menu.html`
  - `greeter.html`
  - `settings.html`
  - `theme-system.html`
- A source overview section containing every string from `SOURCE_PATHS` in `tests/test_component_docs.py`.
- A note that pages use adaptive HTML layouts rather than a rigid template.
- A visible information-density note using `density-note`.

Use this minimal structure and style baseline:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Adwaita-Lite Component Documentation</title>
  <style>
    :root { color-scheme: light dark; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #101014; color: #f4f4f5; line-height: 1.55; }
    main { max-width: 1120px; margin: 0 auto; padding: 40px 24px 64px; }
    a { color: #8ab4ff; }
    .lede { color: #c9c9d1; max-width: 760px; }
    table { width: 100%; border-collapse: collapse; margin-top: 24px; }
    th, td { border: 1px solid #34343c; padding: 12px; text-align: left; vertical-align: top; }
    th { background: #1d1d24; }
    code { background: #24242c; padding: 2px 5px; border-radius: 4px; }
    .status { color: #8ff0a4; font-weight: 700; }
    .density-note { border-left: 4px solid #8ab4ff; padding-left: 16px; color: #d7d7df; }
  </style>
</head>
<body>
<main>
  <h1>Custom Component Documentation</h1>
  <p class="lede">Contributor and agent reference for Adwaita-Lite's custom UI surfaces. These pages are intentionally HTML so each component can use the diagrams, tables, maps, and dense layouts that fit its structure.</p>
  <p class="density-note">Design rule: prefer dense visual structures over prose when they make ownership, flow, state, or safe-edit constraints faster to understand.</p>
  <table>
    <thead><tr><th>Area</th><th>Status</th><th>Source</th></tr></thead>
    <tbody>
      <tr><td><a href="setup-wizard.html">Setup wizard</a></td><td class="status">Planned</td><td><code>files/usr/bin/adwaita-lite-setup-wizard</code></td></tr>
      <tr><td><a href="app-menu.html">App menu</a></td><td class="status">Planned</td><td><code>files/usr/bin/adwaita-lite-app-menu</code></td></tr>
      <tr><td><a href="greeter.html">Greeter</a></td><td class="status">Planned</td><td><code>files/usr/bin/adwaita-lite-greeter</code></td></tr>
      <tr><td><a href="settings.html">Settings</a></td><td class="status">Planned</td><td><code>files/usr/lib/adwaita-lite/settings/</code></td></tr>
      <tr><td><a href="theme-system.html">Theme system</a></td><td class="status">Planned</td><td><code>files/usr/share/adwaita-lite/palette.json</code></td></tr>
    </tbody>
  </table>
</main>
</body>
</html>
```

- [ ] **Step 2: Run the docs test and verify the index-specific checks progress**

Run: `pytest tests/test_component_docs.py -v`

Expected: FAIL. `test_component_docs_pages_exist` should now fail on one of the remaining missing component pages, not on `index.html`.

---

### Task 3: Create Setup Wizard Component Documentation

**Files:**
- Create: `docs/components/setup-wizard.html`
- Reference: `files/usr/bin/adwaita-lite-setup-wizard`
- Reference: `tests/test_setup_wizard_gtk_smoke.py`
- Reference: `tests/test_setup_wizard_app_selection.py`
- Reference: `tests/test_wizard_i18n.py`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create `setup-wizard.html` with adaptive wizard-specific layout**

Create `docs/components/setup-wizard.html` with:

- Link back to `index.html`.
- Source reference: `files/usr/bin/adwaita-lite-setup-wizard`.
- Primary class reference: `SetupWizardWindow`.
- Flow map for all page builders:
  - `_build_language_page`
  - `_build_network_page`
  - `_build_disk_page`
  - `_build_account_page`
  - `_build_system_page`
  - `_build_apps_page`
  - `_build_confirm_page`
  - `_build_progress_page`
- Component map table covering:
  - `card`, `welcome-title`, `welcome-subtitle`
  - `form-entry`, `form-label`, `form-description`
  - `dark-list`, `wifi-row`, `wifi-ssid`, `wifi-detail`, `wifi-connected`
  - `keyboard-toggle`, `keyboard-panel`
  - `setting-row`, `app-row`, `app-name`, `app-description`
  - `warning-label`, `status-label`, `status-error`
  - `back-button`, `create-button`, `details-toggle`, `log-view`
- State/data section covering install config, Flatpak app selection, disk/filesystem/memory strategy, network state, page validation, skip behavior, async install execution, and atomic writes.
- Safe-edit section covering translation markers, low-memory safeguards, subprocess behavior, password limits, alert dialog compatibility, and accessibility announcements.
- Tests section linking by path to:
  - `tests/test_setup_wizard_gtk_smoke.py`
  - `tests/test_setup_wizard_app_selection.py`
  - `tests/test_wizard_i18n.py`
  - `tests/test_installer_mount_handling.py`
  - `tests/test_iso_install_contract.py`
  - `tests/test_flatpak_setup_contract.py`

Use visual structure that fits the wizard: a `flow-strip` page-flow strip, `component-grid` component cards, and a CSS ownership table. Do not copy large source blocks from the wizard.

- [ ] **Step 2: Run the docs test and verify setup wizard anchors pass**

Run: `pytest tests/test_component_docs.py::test_setup_wizard_doc_covers_major_ui_anchors -v`

Expected: PASS.

- [ ] **Step 3: Run the full docs test and verify remaining pages are the only failures**

Run: `pytest tests/test_component_docs.py -v`

Expected: FAIL. Remaining failures should be missing or incomplete `app-menu.html`, `greeter.html`, `settings.html`, and `theme-system.html`.

---

### Task 4: Create App Menu Component Documentation

**Files:**
- Create: `docs/components/app-menu.html`
- Reference: `files/usr/bin/adwaita-lite-app-menu`
- Reference: `tests/test_app_menu_css.py`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create `app-menu.html`**

Create `docs/components/app-menu.html` with:

- Link back to `index.html`.
- Source reference: `files/usr/bin/adwaita-lite-app-menu`.
- Architecture section explaining that `AppMenu` is a GTK window that prefers `Gtk4LayerShell` and falls back to a normal toplevel.
- Component/data map covering:
  - `AppMenu`
  - `AppItem`
  - `_build_css`
  - `_build_twilight_css`
  - `_menu_metrics`
  - `_make_flowbox`
  - `_make_gridview`
  - `_build_power_bar`
- UI ownership table covering:
  - `app-menu`
  - `app-menu-surface`
  - `app-menu-surface-compact`
  - `app-menu-surface-ultra`
  - `app-menu-search`
  - `app-menu-filter`
  - `app-menu-section-label`
  - `app-menu-grid`
  - `app-menu-tile`
  - `app-menu-tile-name`
  - `app-menu-tile-generic`
  - `app-menu-power-bar`
  - `app-menu-power-btn`
  - `app-menu-confirm-label`
- Behavior section covering PID lock/toggle behavior, app metadata loading, category filtering, search matching, frequent apps, grid activation, power confirmation, VM renderer guard, and sizing modes.
- Safe-edit section covering layer-shell preload ordering, low-resolution metrics, model/filter separation, accessibility names, and twilight palette behavior.
- Tests section linking to `tests/test_app_menu_css.py` and explaining the coverage it provides.

Use a compact `component-grid` for the model/rendering/power-action areas and a `state-map` or equivalent dense visual block for search/filter/category state.

- [ ] **Step 2: Run the app menu docs test**

Run: `pytest tests/test_component_docs.py::test_app_menu_doc_covers_major_ui_anchors -v`

Expected: PASS.

---

### Task 5: Create Greeter Component Documentation

**Files:**
- Create: `docs/components/greeter.html`
- Reference: `files/usr/bin/adwaita-lite-greeter`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create `greeter.html`**

Create `docs/components/greeter.html` with:

- Link back to `index.html`.
- Source reference: `files/usr/bin/adwaita-lite-greeter`.
- Architecture section explaining the kiosk greetd login flow.
- Component map covering:
  - `GreeterWindow`
  - `GreetdClient`
  - `_build_css`
  - `_load_palettes`
  - `_load_theme`
  - `_load_accent_name`
- UI ownership table covering:
  - `clock`
  - `date`
  - `card`
  - `gear-button`
  - `session-dropdown`
  - `greeting`
  - `form-entry`
  - `error-label`
  - `login-button`
  - `switch-user`
- Behavior section covering last-user loading, theme/accent files, session discovery, username/password entry, error states, login submission, user switching, and time/date refresh.
- Safe-edit section covering greetd IPC ordering, password handling, pre-login palette fallback, translation domain sharing with settings, and kiosk/display assumptions.

Use a `state-map` to show the greetd login flow from input fields through `GreetdClient` responses and UI error states.

- [ ] **Step 2: Run the greeter docs test**

Run: `pytest tests/test_component_docs.py::test_greeter_doc_covers_major_ui_anchors -v`

Expected: PASS.

---

### Task 6: Create Settings Component Documentation

**Files:**
- Create: `docs/components/settings.html`
- Reference: `files/usr/lib/adwaita-lite/settings/window.py`
- Reference: `files/usr/lib/adwaita-lite/settings/base.py`
- Reference: `files/usr/lib/adwaita-lite/settings/pages/appearance.py`
- Reference: `files/usr/lib/adwaita-lite/settings/pages/panel.py`
- Reference: `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`
- Reference: `files/usr/lib/adwaita-lite/settings/pages/network.py`
- Reference: `files/usr/lib/adwaita-lite/settings/pages/display.py`
- Reference: `files/usr/lib/adwaita-lite/settings/css/style.css`
- Reference: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`
- Reference: `tests/test_settings_css.py`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create `settings.html`**

Create `docs/components/settings.html` with:

- Link back to `index.html`.
- Source reference for the settings package: `files/usr/lib/adwaita-lite/settings/`.
- Architecture section covering `SettingsWindow`, `BasePage`, lazy page building, `Adw.NavigationSplitView`, `Adw.ToastOverlay`, search, and `BasePage.setup_cleanup`.
- Page map covering at least:
  - `AppearancePage`
  - `PanelPage`
  - `KeyboardPage`
  - `NetworkPage`
  - `DisplayPage`
- Custom surface table covering:
  - Appearance: `wallpaper-tile`, `wallpaper-grid`, `wallpaper-add`, `wallpaper-remove`, `accent-swatch`, `accent-swatch-grid`.
  - Panel: module layout editor, pinned apps rows, add-pinned-app navigation page.
  - Keyboard: custom shortcut rows, capture sub-page, reset buttons.
  - Network: `Adw.NavigationView` sub-pages, hidden network form, connect/forget rows.
  - Display: `Adw.AlertDialog` revert flows for scale and resolution.
- Styling section referencing `files/usr/lib/adwaita-lite/settings/css/style.css` and explaining that most styling should remain stock libadwaita while CSS is reserved for wallpaper tiles, accent swatches, and search focus.
- Safe-edit section covering event-bus cleanup, no `unmap` cleanup regression, navigation sub-pages, Adw row patterns, and the reference doc `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`.
- Tests section linking to `tests/test_settings_css.py`, `tests/test_settings_app_logic.py`, `tests/test_settings_appearance.py`, `tests/test_settings_store.py`, and `tests/test_event_bus.py`.

Use a `source-map` or dense page/surface matrix so future agents can jump from custom UI surface to owning source file and relevant tests.

- [ ] **Step 2: Run the settings docs test**

Run: `pytest tests/test_component_docs.py::test_settings_doc_covers_major_custom_surfaces -v`

Expected: PASS.

---

### Task 7: Create Theme System Component Documentation

**Files:**
- Create: `docs/components/theme-system.html`
- Reference: `files/usr/share/adwaita-lite/palette.json`
- Reference: `files/usr/lib/adwaita-lite/theme.py`
- Reference: `files/usr/lib/adwaita-lite/settings/app.py`
- Reference: `files/usr/lib/adwaita-lite/settings/css/style.css`
- Reference: `files/usr/bin/adwaita-lite-app-menu`
- Reference: `files/usr/bin/adwaita-lite-greeter`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Create `theme-system.html`**

Create `docs/components/theme-system.html` with:

- Link back to `index.html`.
- Source references:
  - `files/usr/share/adwaita-lite/palette.json`
  - `files/usr/lib/adwaita-lite/theme.py`
  - `files/usr/lib/adwaita-lite/settings/app.py`
  - `files/usr/lib/adwaita-lite/settings/css/style.css`
  - `files/usr/bin/adwaita-lite-app-menu`
  - `files/usr/bin/adwaita-lite-greeter`
- Token/data map covering:
  - `gtk_color_defines`
  - `_build_accent_css`
  - `_build_twilight_css`
  - `DARK_THEME_COLORS`
  - `@accent_color`
  - `@accent_fg_color`
  - `@window_bg_color`
  - `@window_fg_color`
  - `@borders`
- Behavior section covering light/dark palette, accent selection, high contrast, panel twilight, greeter pre-login theme propagation, app-menu shell palette inversion, and settings CSS use of GTK color tokens.
- Safe-edit section covering contrast, generated CSS ordering, palette fallback paths, and avoiding hardcoded duplicate palette values where generated tokens exist.

Use a `state-map` or token relationship diagram to show how palette data flows into GTK CSS, settings CSS, app-menu CSS, greeter CSS, and panel/twilight behavior.

- [ ] **Step 2: Run the theme docs test**

Run: `pytest tests/test_component_docs.py::test_theme_system_doc_covers_major_theme_anchors -v`

Expected: PASS.

---

### Task 8: Update Index Coverage And Verify Full Documentation Set

**Files:**
- Modify: `docs/components/index.html`
- Test: `tests/test_component_docs.py`

- [ ] **Step 1: Update `index.html` coverage status**

Update `docs/components/index.html` so every component page is marked documented, not planned. The coverage table should include at least these rows:

```html
<tr>
  <td><a href="setup-wizard.html">Setup wizard</a></td>
  <td class="status">Documented</td>
  <td>Installer flow, custom GTK pages, validation, progress/log UI.</td>
</tr>
<tr>
  <td><a href="app-menu.html">App menu</a></td>
  <td class="status">Documented</td>
  <td>Layer-shell launcher, app grid, search/filtering, power actions.</td>
</tr>
<tr>
  <td><a href="greeter.html">Greeter</a></td>
  <td class="status">Documented</td>
  <td>greetd login UI, session picker, palette/accent handling.</td>
</tr>
<tr>
  <td><a href="settings.html">Settings</a></td>
  <td class="status">Documented</td>
  <td>Adwaita settings shell plus custom page widgets.</td>
</tr>
<tr>
  <td><a href="theme-system.html">Theme system</a></td>
  <td class="status">Documented</td>
  <td>Shared palette, generated CSS, accent/high-contrast/twilight behavior.</td>
</tr>
```

- [ ] **Step 2: Run the full docs contract test**

Run: `pytest tests/test_component_docs.py -v`

Expected: PASS with all tests in `tests/test_component_docs.py` passing.

- [ ] **Step 3: Run related existing tests that are cheap and relevant**

Run: `pytest tests/test_component_docs.py tests/test_settings_css.py tests/test_app_menu_css.py tests/test_setup_wizard_app_selection.py tests/test_wizard_i18n.py -v`

Expected: PASS. If GTK/runtime imports cause environment-specific failures in existing tests, inspect the failure and report it accurately instead of changing production code.

- [ ] **Step 4: Check docs links and whitespace**

Run: `git diff --check -- docs/components tests/test_component_docs.py`

Expected: no output and exit 0.

- [ ] **Step 5: Review the final diff**

Run: `git diff -- docs/components tests/test_component_docs.py docs/superpowers/specs/2026-05-20-custom-component-html-docs-design.md docs/superpowers/plans/2026-05-20-custom-component-html-docs.md`

Expected: diff only includes documentation pages, the documentation contract test, the approved spec, and this plan.

- [ ] **Step 6: Commit only if explicitly approved**

Developer instruction requires explicit approval before committing. If and only if the user has explicitly approved commits for this work, run:

```bash
git add docs/components tests/test_component_docs.py docs/superpowers/specs/2026-05-20-custom-component-html-docs-design.md docs/superpowers/plans/2026-05-20-custom-component-html-docs.md
git commit -m "docs: add custom component HTML reference"
```

If commit approval has not been given, stop after verification and report the modified files.

---

## Self-Review Notes

Spec coverage:
- Setup wizard first: Task 3.
- Complete all known custom areas: Tasks 4-7 plus Task 8 index coverage.
- Static hand-authored HTML: Tasks 2-7.
- No runtime/package integration: file structure and Task 8 diff review.
- Source references and safe-edit guidance: Tasks 3-7.
- Visual quality and information density: Task 1 adds a visual-structure contract; Tasks 2-7 require component-specific dense structures.
- Verification without new dependencies: Task 1 and Task 8 use pytest plus standard library only.

Placeholder scan:
- No unresolved implementation placeholders are intended in this plan.
- Page tasks list exact required anchors and sections rather than vague documentation requests.

Type/path consistency:
- Test paths match existing repository paths inspected during planning.
- Page names in tests match the planned `docs/components/*.html` files.
- Source anchor names match current source identifiers and CSS classes found in the repo.
