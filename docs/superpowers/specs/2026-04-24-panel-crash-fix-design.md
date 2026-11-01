# Panel Page Crash Fix Design

## Problem

The settings app crashes (silent window disappearance / GTK segfault) when
changing panel position, especially right after opening the app. The crash is
intermittent but reliably reproducible.

## Root Cause

`panel.py` connects `notify::selected` / `notify::active` handlers on
ComboRow/SwitchRow widgets that call `save_and_apply` synchronously. The
position handler additionally calls `_refresh_module_lists()`, which removes
and re-adds widget rows to Adw PreferencesGroups.

During `group.add(row)`, GTK/Adwaita can run a synchronous layout pass that
causes the ComboRow to re-emit `notify::selected`. This re-enters the handler
while `_refresh_module_lists` is mid-execution, corrupting the widget tree
(stale references, double-removes) and triggering a C-level segfault.

Seven other pages in the codebase already guard against this exact pattern
(keyboard, appearance, bluetooth, power_lock, sound, network, datetime) but
panel.py does not.

## Solution

Add re-entrancy and construction guards to `PanelPage`, matching the existing
`_updating` / `_updating_variant` / `_group_updating` pattern used throughout
the codebase.

### Changes (single file: `files/usr/lib/adwaita-lite/settings/pages/panel.py`)

1. **Add guard flags to `__init__`:** `_updating: bool` and `_built: bool`
2. **Guard all three signal handlers** (position, density, twilight) with
   the `_updating` / `_built` flags
3. **Set `self._built = True`** at the end of `build()`
4. **Wrap `_on_edge_changed`** body in the `_updating` guard

### What this doesn't change

- No timing/UX changes (settings still apply immediately)
- No changes to any other file
- No changes to the widget hierarchy or build order
