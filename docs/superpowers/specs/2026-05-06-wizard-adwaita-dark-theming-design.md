# Wizard Adwaita-Dark Theming Design

## Summary

The setup wizard is a plain GTK4 installer UI that intentionally does not use libadwaita. It should always present a dark, Adwaita-compatible installer experience regardless of the host GTK theme. The current styling paints large surfaces dark but leaves several complex GTK controls free to inherit light-theme defaults from GTK-created child nodes. This causes white popovers and dark text in dropdowns, search entries, and other nested controls.

This work will make the wizard's dark theme an explicit contract. The implementation should force dark preference where GTK exposes it and expand the app stylesheet to cover the GTK CSS nodes used by the wizard, including nested nodes created by controls such as `Gtk.DropDown`, `Gtk.SearchEntry`, `Gtk.Entry`, list rows, popovers, scroll containers, and symbolic icons.

## Goals

- Always force a dark installer wizard; there is no light-mode wizard path.
- Preserve the current plain GTK4 architecture and avoid a libadwaita migration in this release pass.
- Remove light-theme leakage from all wizard pages and control popovers.
- Make the theme easier to audit by using a small set of named dark palette tokens in the stylesheet.
- Add tests that guard the dark-only CSS contract and prevent narrow one-off fixes from regressing.

## Non-Goals

- Do not migrate the wizard to libadwaita.
- Do not redesign the wizard flow, page order, card layout, or installer behavior.
- Do not add support for a light wizard theme.
- Do not change system-wide GTK theme configuration outside the wizard process.

## Root Cause

The wizard currently uses an application CSS provider to style top-level surfaces and selected custom classes. Plain GTK controls, however, create internal CSS nodes whose styling is not fully covered by the app stylesheet. `Gtk.DropDown` is the visible example: GTK documents a `dropdown` node with `button` and `popover` children, and searchable dropdowns create entry/list descendants inside the popover. The previous dropdown fix covered part of that tree, but the same underlying problem applies to other GTK-created nodes.

The correct fix is not another one-selector patch. The wizard needs a complete dark-only app theme contract that covers root surfaces, text controls, popup surfaces, lists, rows, checks, scrollables, text views, and symbolic icons.

## Design

### Dark Preference

At app startup, the wizard should request dark styling from GTK settings when available. This is a belt-and-suspenders measure: the custom CSS remains authoritative, but GTK internals should not start from a light preference when the process supports a dark preference setting.

Implementation should use `Gtk.Settings.get_default()` after GTK/display initialization and set `gtk-application-prefer-dark-theme` to `True` when that property is available. GTK marks this property deprecated in 4.20, but it is present across the GTK 4.0 range the wizard targets and avoids a libadwaita dependency. The assignment must be guarded so missing settings or display initialization quirks do not stop the installer from starting.

### Palette Tokens

The CSS should define a dark palette near the top of the stylesheet. GTK custom properties require GTK 4.16, so the implementation should avoid relying on CSS variables unless the installer image's GTK version guarantees them. If compatibility is uncertain, keep tokens as Python constants and build the CSS string from them.

Required semantic colors:

- Window background: dark page shell.
- Card/surface background: darker content card.
- Raised/control background: entries, dropdown buttons, and subtle rows.
- Hover/active backgrounds: neutral Adwaita-like tints.
- Border color: low-contrast dark border.
- Primary foreground: near-white text.
- Secondary foreground: muted text.
- Disabled foreground: dim text.
- Accent blue: primary action/focus ring.
- Error/success colors: existing red/green semantics.
- Selection background and selection foreground.

The stylesheet should use these tokens consistently instead of adding more unrelated hex values.

### CSS Coverage

The stylesheet should cover these GTK nodes and classes used by the wizard:

- Root surfaces: `window`, generic widget foreground inheritance, cards, status labels, subtitles, summary labels.
- Text inputs: `.form-entry`, `entry`, `entry text`, `entry image`, `entry selection`, `entry:focus`, `entry.search`, and placeholder/secondary states where GTK supports selectors.
- Password inputs: style through the same `entry` and editable text nodes used by GTK internals; avoid relying on nonexistent `PasswordEntry`-specific CSS nodes unless verified.
- Dropdowns: `dropdown`, `dropdown button`, `dropdown button label`, `dropdown button arrow`, `dropdown popover`, `dropdown popover contents`, `dropdown popover entry.search`, `dropdown popover listview`, `dropdown popover row`, selected/hover row states, and popup labels.
- Popovers/dialog fallback: `popover.background`, `popover contents`, `popover arrow`, fallback `Gtk.Window` dialog labels and buttons.
- Lists and rows: `list`, `listbox`, `row`, `.dark-list`, `.wifi-row`, `.wifi-connected`, `.app-row`, check rows, hover and selected states.
- Controls: `checkbutton`, check/radio indicators, disabled buttons, destructive buttons, back buttons, primary buttons, keyboard toggle.
- Scrollables: `scrolledwindow`, `viewport`, `scrollbar`, scrollbar sliders/troughs.
- Text/log view: `.log-view`, `textview`, `textview text`, text selection, monospace log content.
- Symbolic icons: set `-gtk-icon-palette` and icon foreground where needed so search/clear/dropdown indicators are visible on dark controls.

The selectors may be broad within the wizard because the app is a dedicated installer process. They must remain inside the wizard's application CSS provider and must not alter system CSS files.

### Startup and Runtime Behavior

The wizard should still construct and run without libadwaita. If a GTK dark-preference setting is unavailable, the app should continue using the custom CSS without failing. Dark preference should be requested before loading the CSS provider. CSS provider loading must remain in `SetupWizardApp.do_activate()` before constructing or presenting the window.

### Testing

Tests should verify the contract rather than only one screenshot symptom.

Add or expand static tests that load the wizard CSS and assert:

- The wizard includes a dark-only startup/theme hook.
- Required GTK CSS node selectors exist for dropdown, popover, search entry, entry text, list/listview rows, checkbutton, scrollbar, textview/log view, and symbolic icons.
- Required selector blocks include foreground coverage, and surface-like blocks include background coverage.
- The stylesheet does not introduce light surface colors such as white backgrounds for wizard controls.

Keep the existing real GTK smoke test. It should continue constructing `SetupWizardWindow(app)` with patched environmental side effects.

Verification commands:

- `pytest -q tests/test_setup_wizard_app_selection.py tests/test_setup_wizard_gtk_smoke.py`
- `python -m py_compile files/usr/bin/adwaita-lite-setup-wizard`
- `pytest -q`

### Manual Acceptance

After a rebuild, verify the wizard visually:

- Every page remains dark-only.
- Dropdown buttons and opened dropdown/search popovers use dark backgrounds and light text.
- Search fields inside dropdown popovers are dark, including typed text, placeholder/secondary text, clear/search icons, focus ring, and text selection.
- List rows, app rows, Wi-Fi rows, check/radio controls, entries, password entries, log view, scrollbars, and fallback dialogs do not show white/light surfaces.
- There is no black text on dark surfaces and no white panel in the wizard.

## Risks

- GTK CSS node names can vary by widget and version. Use GTK docs for selectors and keep tests focused on nodes the wizard actually uses.
- Broad widget-node selectors can affect all instances of a control inside the wizard. This is acceptable because the wizard is dark-only, but selectors should avoid styling unrelated applications or system files.
- Static CSS tests cannot prove rendered contrast. The GTK smoke test and VM/manual visual pass remain necessary.

## Open Decisions

- None. The wizard is dark-only by design.
