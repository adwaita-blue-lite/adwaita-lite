# Wizard Adwaita-Dark Theming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the plain GTK4 setup wizard always render as a consistent dark, Adwaita-compatible installer UI with no light-theme leakage in nested GTK controls.

**Architecture:** Keep the wizard as a non-libadwaita GTK4 application. Add a guarded GTK dark-preference hook, introduce semantic dark palette tokens, and expand the application CSS provider to cover the GTK CSS nodes used by the wizard. Tests enforce the dark-only CSS contract statically, while the existing GTK smoke test continues to verify construction.

**Tech Stack:** Python 3, PyGObject, GTK4, pytest, GTK CSS.

---

## File Structure

- Modify `files/usr/bin/adwaita-lite-setup-wizard`
  - Add guarded dark preference helper.
  - Add semantic dark palette tokens.
  - Convert the stylesheet to use `string.Template` token substitution.
  - Add comprehensive dark CSS coverage for entries, dropdown popovers, search entries, list/listview rows, check controls, scrollbars, popovers, textview/log view, and symbolic icons.
- Modify `tests/test_setup_wizard_app_selection.py`
  - Add CSS parsing helpers for static contract tests.
  - Replace the narrow dropdown-only regression with comprehensive dark-theme contract tests.
- Keep `tests/test_setup_wizard_gtk_smoke.py` unchanged unless implementation breaks construction.

## Task 1: Add Failing Dark Theme Contract Tests

**Files:**
- Modify: `tests/test_setup_wizard_app_selection.py`

- [ ] **Step 1: Add CSS parsing helpers after `_load_wizard_helpers()`**

Add these helpers after the existing `_load_wizard_helpers` function:

```python
def _css_blocks(css: str) -> list[tuple[list[str], str]]:
    blocks = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, flags=re.DOTALL):
        selectors = [s.strip() for s in match.group(1).split(",")]
        body = match.group(2)
        blocks.append((selectors, body))
    return blocks


def _css_body_for_selector(css: str, selector: str) -> str:
    bodies = [body for selectors, body in _css_blocks(css) if selector in selectors]
    assert bodies, f"Missing CSS selector: {selector}"
    return "\n".join(bodies)


def _assert_selector_has_properties(css: str, selector: str, properties: set[str]) -> None:
    body = _css_body_for_selector(css, selector)
    missing = [prop for prop in sorted(properties) if not re.search(rf"\b{re.escape(prop)}\s*:", body)]
    assert not missing, f"{selector} missing CSS properties: {missing}"
```

- [ ] **Step 2: Replace the narrow dropdown test with comprehensive contract tests**

Replace `test_wizard_dropdowns_force_dark_theme_foregrounds` with these tests:

```python
def test_wizard_forces_dark_theme_without_libadwaita(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)
    source = WIZARD.read_text()

    assert "gi.require_version(\"Adw\"" not in source
    assert "from gi.repository import Adw" not in source
    assert "_force_dark_theme" in module
    assert "Gtk.Settings.get_default" in source
    assert "gtk-application-prefer-dark-theme" in source


def test_wizard_css_declares_adwaita_dark_palette(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)
    colors = module["DARK_THEME_COLORS"]

    required = {
        "window_bg",
        "card_bg",
        "control_bg",
        "control_hover_bg",
        "subtle_bg",
        "border",
        "border_subtle",
        "primary_fg",
        "secondary_fg",
        "disabled_fg",
        "accent_bg",
        "accent_hover_bg",
        "accent_active_bg",
        "focus_border",
        "error_fg",
        "success_fg",
        "selection_bg",
        "selection_fg",
    }
    assert required <= set(colors)

    for name in required:
        value = colors[name]
        assert value.startswith(("#", "rgba(")), f"{name} has non-color token value {value!r}"


def test_wizard_css_covers_dark_gtk_control_nodes(monkeypatch):
    css = _load_wizard_helpers(monkeypatch)["CSS"]

    required_selectors = {
        "window": {"background-color", "color"},
        "*": {"color", "-gtk-icon-palette"},
        ".card": {"background-color", "color", "border"},
        "entry": {"background-color", "color", "border", "caret-color"},
        "entry text": {"background-color", "color"},
        "entry image": {"color"},
        "entry.search": {"background-color", "color", "border"},
        "selection": {"background-color", "color"},
        "dropdown": {"color"},
        "dropdown button": {"background-color", "color", "border"},
        "dropdown button label": {"color"},
        "dropdown button arrow": {"color"},
        "dropdown popover": {"background-color", "color"},
        "dropdown popover contents": {"background-color", "color"},
        "dropdown popover entry.search": {"background-color", "color", "border"},
        "dropdown popover listview": {"background-color", "color"},
        "dropdown popover row": {"background-color", "color"},
        "dropdown popover row:selected": {"background-color", "color"},
        "dropdown popover label": {"color"},
        "popover.background": {"background-color", "color"},
        "popover contents": {"background-color", "color", "border"},
        "popover arrow": {"background-color", "border"},
        "list": {"background-color", "color"},
        "listbox": {"background-color", "color"},
        "row": {"background-color", "color"},
        "row:selected": {"background-color", "color"},
        "checkbutton": {"color"},
        "checkbutton label": {"color"},
        "checkbutton check": {"background-color", "border"},
        "scrolledwindow": {"background-color"},
        "viewport": {"background-color"},
        "scrollbar slider": {"background-color"},
        "textview": {"background-color", "color"},
        "textview text": {"background-color", "color"},
        ".log-view": {"background-color", "color"},
    }

    for selector, properties in required_selectors.items():
        _assert_selector_has_properties(css, selector, properties)


def test_wizard_css_does_not_define_light_control_surfaces(monkeypatch):
    css = _load_wizard_helpers(monkeypatch)["CSS"]
    light_surface = re.compile(
        r"background(?:-color)?\s*:\s*(?:white|#fff(?:fff)?|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))",
        flags=re.IGNORECASE,
    )

    assert not light_surface.search(css)
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py -k 'dark_theme or dark_palette or dark_gtk_control_nodes or light_control_surfaces'
```

Expected: failures for missing `_force_dark_theme`, missing `DARK_THEME_COLORS`, and missing CSS selectors such as `entry`, `dropdown popover contents`, `entry.search`, `popover contents`, `scrollbar slider`, and `textview`.

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/test_setup_wizard_app_selection.py
git commit -m "test(wizard): define dark theming contract"
```

## Task 2: Add Dark Preference Hook and Palette Tokens

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`
- Test: `tests/test_setup_wizard_app_selection.py`

- [ ] **Step 1: Import `Template`**

In `files/usr/bin/adwaita-lite-setup-wizard`, add this import near the other standard library imports:

```python
from string import Template
```

- [ ] **Step 2: Add dark palette tokens before `CSS`**

Insert this block immediately before `CSS =`:

```python
DARK_THEME_COLORS = {
    "window_bg": "#222226",
    "card_bg": "#1d1d20",
    "control_bg": "#36363a",
    "control_hover_bg": "#404044",
    "control_active_bg": "#2f2f33",
    "subtle_bg": "rgba(255, 255, 255, 0.04)",
    "selected_bg": "rgba(255, 255, 255, 0.08)",
    "border": "#444444",
    "border_subtle": "rgba(255, 255, 255, 0.12)",
    "primary_fg": "#ffffff",
    "secondary_fg": "#aaaaaa",
    "tertiary_fg": "#888888",
    "disabled_fg": "#888888",
    "accent_bg": "#3584e4",
    "accent_hover_bg": "#62a0ea",
    "accent_active_bg": "#1c71d8",
    "focus_border": "#62a0ea",
    "destructive_bg": "#c01c28",
    "destructive_hover_bg": "#e01b24",
    "destructive_active_bg": "#a51d2d",
    "error_fg": "#ff6b6b",
    "success_fg": "#57e389",
    "selection_bg": "#3584e4",
    "selection_fg": "#ffffff",
    "log_bg": "#1a1a1a",
    "log_fg": "#cccccc",
}
```

- [ ] **Step 3: Convert `CSS` to a `Template` string**

Change the start of the CSS assignment from:

```python
CSS = """\
```

to:

```python
CSS = Template("""\
```

Change the end of the CSS assignment from:

```python
"""
```

to:

```python
""").substitute(DARK_THEME_COLORS)
```

Do not escape CSS braces; `string.Template` uses `$token` syntax and leaves CSS braces unchanged.

- [ ] **Step 4: Add guarded dark preference helper after the CSS block**

Add this function immediately after the CSS assignment:

```python
def _force_dark_theme() -> None:
    """Request a dark GTK preference without depending on libadwaita."""
    try:
        settings = Gtk.Settings.get_default()
    except (AttributeError, RuntimeError, TypeError):
        return
    if settings is None:
        return
    try:
        settings.set_property("gtk-application-prefer-dark-theme", True)
    except (AttributeError, RuntimeError, TypeError):
        return
```

- [ ] **Step 5: Call dark preference before loading CSS**

In `SetupWizardApp.do_activate`, change:

```python
    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
```

to:

```python
    def do_activate(self) -> None:
        _force_dark_theme()
        provider = Gtk.CssProvider()
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py -k 'dark_theme or dark_palette'
```

Expected: dark hook and palette tests pass. The comprehensive node coverage test should still fail until Task 3.

- [ ] **Step 7: Run syntax check**

Run:

```bash
python -m py_compile files/usr/bin/adwaita-lite-setup-wizard
```

Expected: exits 0 with no output.

- [ ] **Step 8: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "fix(wizard): force dark GTK preference"
```

## Task 3: Expand CSS Node Coverage

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`
- Test: `tests/test_setup_wizard_app_selection.py`

- [ ] **Step 1: Replace existing color literals in the top CSS blocks with palette tokens**

In the `CSS = Template("""...` body, update the existing top-level blocks to use token names. The beginning of the stylesheet should look like this:

```css
window {
    background-color: $window_bg;
    color: $primary_fg;
}

* {
    color: $primary_fg;
    -gtk-icon-palette: success $success_fg, warning #f6d32d, error $error_fg;
}

selection {
    background-color: $selection_bg;
    color: $selection_fg;
}

label {
    color: $primary_fg;
}

checkbutton {
    color: $primary_fg;
}

checkbutton label {
    color: $primary_fg;
}

checkbutton check {
    background-color: $control_bg;
    border: 1px solid $border_subtle;
    color: $primary_fg;
}

checkbutton check:checked {
    background-color: $accent_bg;
    border: 1px solid $accent_bg;
}
```

- [ ] **Step 2: Add generic dark entry/search-entry rules after `.form-entry:focus`**

Insert this block after the existing `.form-entry:focus` rule:

```css
entry,
entry.search,
.form-entry {
    background-color: $control_bg;
    color: $primary_fg;
    border: 1px solid $border_subtle;
    border-radius: 8px;
    caret-color: $primary_fg;
    box-shadow: none;
}

entry:focus,
entry.search:focus,
.form-entry:focus {
    border: 1px solid $focus_border;
}

entry text,
entry.search text {
    background-color: $control_bg;
    color: $primary_fg;
    selection-background-color: $selection_bg;
    selection-color: $selection_fg;
}

entry image,
entry.search image {
    color: $secondary_fg;
}

entry:disabled,
entry text:disabled {
    color: $disabled_fg;
}
```

- [ ] **Step 3: Replace the existing dropdown rules with comprehensive dropdown/popover rules**

Replace the current `dropdown ...` block with this block:

```css
dropdown {
    color: $primary_fg;
}

dropdown button {
    background-color: $control_bg;
    color: $primary_fg;
    border: 1px solid $border_subtle;
    border-radius: 8px;
    box-shadow: none;
}

dropdown button:hover {
    background-color: $control_hover_bg;
}

dropdown button:active {
    background-color: $control_active_bg;
}

dropdown button:focus,
dropdown button:focus-visible {
    border: 1px solid $focus_border;
}

dropdown button label {
    color: $primary_fg;
}

dropdown button arrow {
    color: $primary_fg;
}

dropdown popover {
    background-color: $card_bg;
    color: $primary_fg;
}

dropdown popover contents {
    background-color: $card_bg;
    color: $primary_fg;
    border: 1px solid $border;
    border-radius: 12px;
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.45);
}

dropdown popover entry.search {
    background-color: $control_bg;
    color: $primary_fg;
    border: 1px solid $focus_border;
}

dropdown popover listview {
    background-color: $card_bg;
    color: $primary_fg;
}

dropdown popover row {
    background-color: $card_bg;
    color: $primary_fg;
    border-radius: 6px;
}

dropdown popover row:hover {
    background-color: $subtle_bg;
}

dropdown popover row:selected {
    background-color: $selected_bg;
    color: $primary_fg;
}

dropdown popover label {
    color: $primary_fg;
}
```

- [ ] **Step 4: Add popover/list/scroll/textview rules before `.dark-list`**

Insert this block before the existing `.dark-list` rule:

```css
popover.background {
    background-color: transparent;
    color: $primary_fg;
}

popover contents {
    background-color: $card_bg;
    color: $primary_fg;
    border: 1px solid $border;
    border-radius: 12px;
}

popover arrow {
    background-color: $card_bg;
    border: 1px solid $border;
}

list,
listbox {
    background-color: transparent;
    color: $primary_fg;
}

row {
    background-color: transparent;
    color: $primary_fg;
}

row:hover {
    background-color: $subtle_bg;
}

row:selected {
    background-color: $selected_bg;
    color: $primary_fg;
}

scrolledwindow,
viewport {
    background-color: transparent;
}

scrollbar {
    background-color: transparent;
}

scrollbar trough {
    background-color: transparent;
}

scrollbar slider {
    background-color: $control_hover_bg;
    border-radius: 999px;
    min-width: 6px;
    min-height: 6px;
}

textview,
textview text {
    background-color: $log_bg;
    color: $log_fg;
    caret-color: $primary_fg;
}
```

- [ ] **Step 5: Update existing custom class blocks to use palette tokens**

Within existing rules, replace these literal colors with tokens:

```text
#222226 -> $window_bg
#1d1d20 -> $card_bg
#36363a -> $control_bg
#404044 -> $control_hover_bg
#3a3a3e -> $border_subtle
#444444 -> $border
#ffffff -> $primary_fg
#dddddd -> $primary_fg
#aaaaaa -> $secondary_fg
#999999 -> $secondary_fg
#888888 -> $disabled_fg
#3584e4 -> $accent_bg
#62a0ea -> $accent_hover_bg
#1c71d8 -> $accent_active_bg
#c01c28 -> $destructive_bg
#e01b24 -> $destructive_hover_bg
#a51d2d -> $destructive_active_bg
#ff6b6b -> $error_fg
#57e389 -> $success_fg
#1a1a1a -> $log_bg
#cccccc -> $log_fg
```

Keep `rgba(255,255,255,...)` tints only when they represent subtle dark-mode overlays, not base surfaces.

- [ ] **Step 6: Run the comprehensive CSS contract tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py -k 'dark_theme or dark_palette or dark_gtk_control_nodes or light_control_surfaces'
```

Expected: all selected tests pass.

- [ ] **Step 7: Run wizard-focused tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py
```

Expected: pass. The smoke test may skip only if GTK/display runtime is unavailable.

- [ ] **Step 8: Run syntax check**

Run:

```bash
python -m py_compile files/usr/bin/adwaita-lite-setup-wizard
```

Expected: exits 0 with no output.

- [ ] **Step 9: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard tests/test_setup_wizard_app_selection.py
git commit -m "fix(wizard): enforce dark GTK control styling"
```

## Task 4: Review and Final Verification

**Files:**
- Review: `files/usr/bin/adwaita-lite-setup-wizard`
- Review: `tests/test_setup_wizard_app_selection.py`
- Review: `tests/test_setup_wizard_gtk_smoke.py`

- [ ] **Step 1: Inspect the final diff**

Run:

```bash
git diff 7cd6bf1...HEAD -- files/usr/bin/adwaita-lite-setup-wizard tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py
```

Expected: diff includes tests, guarded dark preference, palette tokens, CSS node coverage, and no libadwaita import.

- [ ] **Step 2: Run wizard-focused tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py
```

Expected: pass. The smoke test may skip only for unavailable GTK/display runtime.

- [ ] **Step 3: Run full syntax check**

Run:

```bash
python -m py_compile files/usr/bin/adwaita-lite-setup-wizard
```

Expected: exits 0 with no output.

- [ ] **Step 4: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Request code review**

Ask a review subagent to check only Critical/Important issues for:

```text
Scope: comprehensive dark-only GTK4 setup wizard theming.
Base: 7cd6bf1 docs(wizard): design dark-only theming hardening
Focus: GTK CSS selector correctness, startup safety, libadwaita avoidance, regression test meaning, unintended broad styling risk.
```

- [ ] **Step 6: Address review findings**

If the reviewer requests Critical or Important changes, fix them with TDD where behavior changes are required, then re-run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py
python -m py_compile files/usr/bin/adwaita-lite-setup-wizard
pytest -q
```

Commit review follow-up with:

```bash
git add files/usr/bin/adwaita-lite-setup-wizard tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py
git commit -m "fix(wizard): address dark theming review"
```

- [ ] **Step 7: Record manual rebuild acceptance gap**

In the final handoff, report that automated tests passed and that rebuild/VM visual acceptance still needs checking:

```text
Manual acceptance after image rebuild: open every wizard page, open each dropdown/search popover, verify no white surfaces or black text remain.
```

Do not claim the VM visual pass was completed unless it was actually run.
