# Settings Adwaita Migration — Phase 3 (Wave 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Four Opus agents run **concurrently**, one per page. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Convert the four wave-3 pages — `display`, `network`, `panel`, `keyboard` — to `Adw.PreferencesPage`. These are the heavy-custom pages of the settings app: two have countdown revert dialogs, two have modal dialogs that become navigation-push sub-pages, one has a drag-and-drop layout editor that stays custom, and one has an in-place keyboard capture flow that also becomes a navigation-push sub-page. All four get Opus because the judgment calls on what to convert vs. preserve are non-trivial per page.

**Architecture:** Same subagent-driven pattern as waves 1–2. Each agent:

1. Reads the pilot (`power_lock.py`) and at least one converted wave-2 page similar to their target for pattern examples (wave-2 introduced `AdwNavigationView`, `AdwBanner`, `AdwStatusPage`, and the navigation-push sub-page pattern, which wave 3 reuses heavily)
2. Reads the reference pack (`docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`)
3. Reads their per-page task section in this plan
4. Rewrites their assigned page, commits as a single-file commit, does not push

Controller runs spec + quality reviewers per commit after all four finish, addresses issues, then pushes the batch.

**Tech stack:** Python 3.13, PyGObject, GTK 4, libadwaita. `BasePage.make_*` factories still in place until Phase 4.

**References:**
- Pilot: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py` (commit `7f9473f`)
- Wave-1: `files/usr/lib/adwaita-lite/settings/pages/sound.py` (dynamic widget refs + lifecycle)
- Wave-2: `files/usr/lib/adwaita-lite/settings/pages/about.py` (AdwNavigationView + sub-page with AdwSwitchRows + handler_block_by_func)
- Wave-2: `files/usr/lib/adwaita-lite/settings/pages/users.py` (AdwNavigationView + navigation-push sub-page with password entries + apply)
- Wave-2: `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py` (dynamic list rebuild + device rows + scan lifecycle)
- Wave-2: `files/usr/lib/adwaita-lite/settings/pages/appearance.py` (custom Gtk widgets wrapped in `Adw.ActionRow` via `add_suffix`)
- Design: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Reference pack: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`

---

## Shared expectations for every wave-3 agent

Same as wave 2 (carried forward). Highlights for agents skimming:

1. **Inheritance** — `class XyzPage(BasePage, Adw.PreferencesPage)` with dual explicit `__init__`.
2. **build() return** — Returns `self` if no navigation push, or `self._nav` (an `Adw.NavigationView`) if the page needs sub-pages. See the "Navigation pattern" in the wave-2 plan for the exact structure.
3. **`setup_cleanup(self)`** called unconditionally at the end of `build()` — even without subscriptions today.
4. **`enable_escape_close`** — any remaining plain Gtk.Window dialog uses `from ..utils import enable_escape_close` rather than `BasePage.enable_escape_close`. But wave-3 should aim to eliminate plain Gtk.Window dialogs entirely: replace with `Adw.AlertDialog` (for confirmations) or navigation-push sub-pages (for input flows).
5. **`notify::active` / `notify::selected` / `apply`** — the Adwaita signal names replace `state-set` / the old `changed`.
6. **Omit empty subtitles.**
7. **Every store call preserved** (save_and_apply, save_debounced, subscribe, apply).
8. **No `self.make_*` calls.**
9. **Commit message format**:
    ```
    feat(settings): convert <page> to Adw.PreferencesPage (wave 3)

    <2-3 sentence description>

    Preserves: <wiring kept intact>.

    Part of the Adwaita migration wave 3. See
    docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md.

    Co-Authored-By: Claude <model> <noreply@anthropic.com>
    ```

### Pattern: replacing a countdown revert dialog with `AdwAlertDialog`

Both `display.py`'s scale and resolution flows currently use plain `Gtk.Window` with a manually-ticked countdown label + Keep/Revert buttons, auto-reverting at 0s. Convert to `Adw.AlertDialog`:

```python
def _show_revert_dialog(self, old_scale, new_scale):
    dialog = Adw.AlertDialog.new(
        _("Confirm display scale"),
        _("Keep this display scale?"),
    )
    dialog.add_response("revert", _("Revert"))
    dialog.add_response("keep", _("Keep"))
    dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("keep")
    dialog.set_close_response("revert")  # Escape or back gesture reverts

    self._revert_dialog = dialog
    self._revert_seconds = 15
    # body text doubles as the countdown. update it via set_body() on
    # a 1 Hz timer; expiry calls dialog.response("revert") to auto-revert.
    self._update_countdown_body(dialog, old_scale)

    dialog.connect("response", self._on_revert_response, old_scale, new_scale)
    dialog.present(parent_widget)

def _update_countdown_body(self, dialog, old_scale):
    dialog.set_body(_("Reverting in {seconds}s…").format(seconds=self._revert_seconds))
    self._revert_timer_id = GLib.timeout_add_seconds(1, self._tick, dialog, old_scale)

def _tick(self, dialog, old_scale):
    self._revert_seconds -= 1
    if self._revert_seconds <= 0:
        dialog.response("revert")  # auto-trigger the revert response
        return GLib.SOURCE_REMOVE
    dialog.set_body(_("Reverting in {seconds}s…").format(seconds=self._revert_seconds))
    return GLib.SOURCE_CONTINUE

def _on_revert_response(self, _dialog, response_id, old_scale, new_scale):
    if self._revert_timer_id is not None:
        GLib.source_remove(self._revert_timer_id)
        self._revert_timer_id = None
    self._revert_dialog = None
    if response_id == "keep":
        self.store.save_and_apply("scale", new_scale)
        self._sync_<control>_to(new_scale)
    else:
        self._set_scale(old_scale)
        self._sync_<control>_to(old_scale)
```

- `dialog.response("revert")` programmatically fires the response signal; equivalent to the old `_revert()` call.
- `present(parent_widget)` — pass a Gtk.Widget whose toplevel is the window (e.g., `self._scale_row.get_root()`).
- Escape / back gesture / close are all handled by `set_close_response`.

### Pattern: capture-style input in a sub-page

For `keyboard.py`'s shortcut capture, instead of attaching a `Gtk.EventControllerKey` to the main window and swapping the button label in place, push a navigation page dedicated to capture. The capture page owns its own `Gtk.EventControllerKey`; pressing a key validates + saves + pops back.

```python
def _push_capture_page(self, index):
    sub = Adw.NavigationPage()
    sub.set_title(_("Press new shortcut"))

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())  # automatic back button

    status = Adw.StatusPage()
    status.set_icon_name("input-keyboard-symbolic")
    status.set_title(_("Press the new shortcut"))
    status.set_description(
        _("Press the desired key combination. Press Escape to cancel.")
    )
    toolbar.set_content(status)

    sub.set_child(toolbar)

    controller = Gtk.EventControllerKey()
    controller.connect("key-pressed", self._on_capture_keypress, index, sub)
    sub.add_controller(controller)  # controller on the page, not the window

    self._nav.push(sub)

def _on_capture_keypress(self, _ctrl, keyval, _kc, state, index, sub):
    # Same _build_key_string / _find_conflict / _apply_new_key logic as
    # the in-place implementation - only the dismissal path changes:
    # on success or conflict-decline, self._nav.pop() instead of
    # swapping the button label.
    ...
```

The conflict AdwAlertDialog stays the same (it's already Adw in the pre-migration code).

---

## File plan

| Page | File | Model | Key complexity |
|---|---|---|---|
| Display | `files/usr/lib/adwaita-lite/settings/pages/display.py` | Opus | Two countdown revert dialogs (scale + resolution), conditionally-visible custom schedule entries, wlr-randr subprocess flows |
| Network | `files/usr/lib/adwaita-lite/settings/pages/network.py` | Opus | Dynamic WiFi list, password + hidden-network nav pushes, .property info rows for active connection, wired status |
| Panel | `files/usr/lib/adwaita-lite/settings/pages/panel.py` | Opus | Drag-button layout editor (stays custom), pinned apps nav-push picker with search |
| Keyboard | `files/usr/lib/adwaita-lite/settings/pages/keyboard.py` | Opus | Layout + variant combos, shortcut list with capture-page nav push, conflict AdwAlertDialog (already Adw) |

---

## Task: Agent 1 — `display` (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/display.py`

### Groups (top-down)

1. **Display Scale** — `Adw.ComboRow` (not toggle-cards). Options: `"75%"` … `"250%"`, stored values `0.75` … `2.5` (parallel lists `SCALE_OPTIONS` and `SCALE_VALUES` preserved). Selection change calls `self._apply_scale(new_value)` which triggers the countdown revert flow.
    - Agent may push back in favour of keeping toggle-cards if the tactile choice feels better on a touchpad-Chromebook. Default: ComboRow (narrower layout, consistent with wave 2's power_profile pattern).
2. **Resolution & Refresh Rate** — one `Adw.ExpanderRow` per display. When there's only one display, expand by default (`set_expanded(True)`); with ≥ 2 displays, collapse by default. Each expander contains one `Adw.ComboRow` child row titled `_("Mode")` with the mode strings. No displays detected → replace this group with an `Adw.StatusPage`:
    ```python
    if not displays:
        status = Adw.StatusPage()
        status.set_icon_name("video-display-symbolic")
        status.set_title(_("No displays detected"))
        self.add(status)
    ```
3. **Night Light** —
    - `Adw.SwitchRow` titled `_("Night Light")`, subtitle `_("Reduce blue light to help with sleep")`.
    - `Adw.ActionRow` titled `_("Temperature")`, subtitle `_("3500K (warm) to 6500K (cool)")`, suffix = existing `Gtk.Scale` (3500..6500 step 100, `set_draw_value(True)` + format function `"{v:.0f}K"`).
    - `Adw.ComboRow` titled `_("Schedule")` with options Sunset to Sunrise / Custom. Stored values `"sunset-sunrise"` / `"custom"`.
    - **Custom schedule** — wrap the two time entries in an `Adw.ExpanderRow` titled `_("Custom schedule")`. `set_expanded(current_schedule == "custom")` at build time. Two child `Adw.EntryRow`s (Start / End) with `set_show_apply_button(True)` + `apply` signal firing `_validate_and_save_time`. When the schedule ComboRow changes, call `expander.set_expanded(new == "custom")` — the expander row replaces the old `custom_box.set_visible(...)` logic.
4. **Advanced** — `Adw.ActionRow` titled `_("Advanced display settings")`, subtitle `_("Arrange and configure displays visually")`, chevron suffix, `activated` → `subprocess.Popen(["wdisplays"], ...)`.

### Revert dialog conversions

Both `_show_revert_dialog` (scale) and `_show_res_revert_dialog` (resolution) become `Adw.AlertDialog` per the pattern above. Specifics:

- **Scale revert**: `_apply_scale(new_scale)` calls `_set_scale(new_scale)` (wlr-randr), then presents the AlertDialog with the "Keep / Revert" responses + 15s countdown in the body. On `"revert"`: call `_set_scale(old_scale)`, update the scale ComboRow selection back to `old_scale`'s index (new method `_sync_scale_row_to(value)` replaces `_sync_buttons`). On `"keep"`: `self.store.save_and_apply("scale", new_scale)` + sync row.
- **Resolution revert**: `_on_resolution_changed` applies the new mode via wlr-randr, then presents AlertDialog. On `"revert"`: apply old mode, reset the `Adw.ComboRow`'s `set_selected` back to the old index. On `"keep"`: `self.store.save_and_apply(f"resolution_{output_name}", new_mode)`.
- Both dialogs must handle the page being unmapped mid-countdown. `_cleanup_dialogs` on unmap calls `dialog.force_close()` on any active AlertDialog and cancels any timer. `Adw.AlertDialog` has a `force_close()` method for this exact scenario.

### Preservation checklist

- `SCALE_OPTIONS` + `SCALE_VALUES` + `SCHEDULE_LABELS` + `SCHEDULE_VALUES` constants unchanged.
- `_get_displays` / `_set_scale` / `_apply_resolution` subprocess helpers unchanged.
- `_validate_and_save_time` regex check + `.error` CSS class add/remove preserved (it works on `Adw.EntryRow`, which supports the same style class).
- All 4 night-light `save_and_apply` / `save_debounced` call sites preserved: `night_light_enabled`, `night_light_temp` (debounced), `night_light_schedule`, `night_light_start`/`night_light_end`.
- `resolution_<output>` store key preserved on keep-response.
- All 5 `wlr-randr` subprocess calls preserved (`_get_displays`, `_set_scale` x2, `_apply_resolution`).

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/display.py').read()); print('OK')"
grep -cE 'wlr-randr' files/usr/lib/adwaita-lite/settings/pages/display.py
# Expected: >= 4
grep -cE 'save_and_apply|save_debounced' files/usr/lib/adwaita-lite/settings/pages/display.py
# Expected: >= 5 (scale, night_light_enabled, night_light_temp debounced, night_light_schedule, night_light_start, night_light_end, resolution_)
grep -cE 'Adw\.AlertDialog|Gtk\.Window' files/usr/lib/adwaita-lite/settings/pages/display.py
# Expected: >= 2 AlertDialog, 0 Gtk.Window
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/display.py
# Expected: 0
```

### Commit

Template summary: *"Five groups: Display Scale (AdwComboRow with countdown-revert via AdwAlertDialog), Resolution & Refresh Rate (one AdwExpanderRow per display with an inner AdwComboRow, or AdwStatusPage when none), Night Light (AdwSwitchRow + temperature Scale suffix + schedule AdwComboRow + custom-schedule AdwExpanderRow with two AdwEntryRows), Advanced (chevron row launching wdisplays). Two Gtk.Window dialogs replaced by AdwAlertDialog with programmatic `dialog.response()` at countdown expiry."*

Preservation line: *"5 wlr-randr subprocess flows, scale + resolution revert timing and dialog cleanup on unmap, all 5+ save_and_apply/debounced call sites, HH:MM regex validation with .error class, resolution_<output> per-display store keys."*

---

## Task: Agent 2 — `network` (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/network.py`

### Top-level structure

Returns an `Adw.NavigationView` wrapping self (navigation pushes for password entry and hidden-network connection). Root NavigationPage titled `_("Network")`.

### Groups (top-down, on the root preferences page)

1. **WiFi group** (no title, or title `_("WiFi")`):
    - Header-suffix `AdwSwitchRow` — actually, no: the power toggle is a regular `Adw.SwitchRow` in the group, not a header-suffix. Title `_("WiFi")`. `notify::active` handler.
    - Scan button as the group's `set_header_suffix(scan_btn)` — a `Gtk.Button` with `.flat` class and icon `view-refresh-symbolic`.
    - Hidden network: a chevron-suffix `Adw.ActionRow("Connect to hidden network")` below the switch row, activated → `self._push_hidden_network()`.
2. **Network list group** (title `_("Available Networks")` or empty; agent decides):
    - Dynamic — populated by `_refresh_networks` with one `Adw.ActionRow` per AP. Each row:
        - Signal-strength icon as prefix (4 icon-name levels based on `ap.strength`, same thresholds as today).
        - Secondary lock icon via a second `add_prefix` when `ap.secured`.
        - Title = `ap.ssid`.
        - Subtitle = `_("Connected")` when `ap.active`, else empty.
        - Suffix = `Connect` button (unsecured or not active) or `Forget` button (active, with adjacent status subtitle already).
    - Empty state: `group.set_description(_("No networks found"))` when the list is empty.
    - Banner pattern instead: When `self._nm` isn't ready (adapter absent, airplane mode), show an `Adw.Banner.new(_("No network adapter"))` revealed conditionally. Banner is a direct child of the page (NOT wrapped in a group), added before the first group.
3. **Active Connection group** — dynamic via `_refresh_active`. Each info line (Network, Type, IP, Gateway, DNS) becomes an `Adw.ActionRow` with the value in the subtitle and the `.property` style class (same pattern as about's info rows). When not connected, set `group.set_description(_("Not connected"))` and remove all rows.
4. **Wired group** — one `Adw.ActionRow` titled `_("Ethernet")` with subtitle reflecting the state (`_("No wired adapter detected")` / `_("Connected")` / `_("Disconnected")`).
5. **Advanced group** — one `Adw.ActionRow` titled `_("Advanced network settings")`, chevron suffix, activated → `subprocess.Popen(["nm-connection-editor"], ...)`. On `FileNotFoundError`, `self.store.show_toast(_("Connection editor not found"), True)`.

### Navigation push for password entry

Replaces `_show_password_dialog`. Method `_push_password_page(ap)`:

```python
def _push_password_page(self, ap):
    sub = Adw.NavigationPage()
    sub.set_title(_("Connect to {ssid}").format(ssid=ap.ssid))

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    inner = Adw.PreferencesPage()
    group = Adw.PreferencesGroup()
    group.set_description(_("Enter the Wi-Fi password."))

    pw_row = Adw.PasswordEntryRow()
    pw_row.set_title(_("Password"))
    group.add(pw_row)
    inner.add(group)

    connect_group = Adw.PreferencesGroup()
    connect_row = Adw.ActionRow()
    connect_btn = Gtk.Button(label=_("Connect"))
    connect_btn.add_css_class("suggested-action")
    connect_btn.set_valign(Gtk.Align.CENTER)
    connect_btn.connect("clicked", lambda _b: self._do_password_connect(ap, pw_row))
    connect_row.add_suffix(connect_btn)
    connect_group.add(connect_row)
    inner.add(connect_group)

    toolbar.set_content(inner)
    sub.set_child(toolbar)
    self._nav.push(sub)
```

`_do_password_connect` validates non-empty via toast, calls `self._nm.connect_wifi(ap.ssid, pw_row.get_text())`, pops.

### Navigation push for hidden network

Replaces `_show_hidden_dialog`. Similar structure: sub-page with a group containing SSID `Adw.EntryRow`, Security `Adw.ComboRow` (None / WPA/WPA2 / WPA3), Password `Adw.PasswordEntryRow`. Action group with Connect button. On connect: `self._nm.connect_wifi(ssid, pw_or_None, hidden=True)`.

### Status feedback

`_status_label` goes away. All "Connecting…", "Connected successfully", and error-message calls become `self.store.show_toast(...)`. The 3-second auto-hide of success messages is naturally handled by toast timeout — no explicit timer needed.

### Preservation checklist

- `NetworkManagerHelper` lazy instantiation inside `build()` preserved.
- All 4 event subscriptions: `nm-ready`, `network-changed`, `network-connect-success`, `network-connect-error`.
- `self._updating` guard on WiFi toggle.
- Signal-strength icon thresholds (75 / 50 / 25).
- `_refresh_networks` / `_refresh_active` / `_refresh_wired` logic — preserved, widget types swapped.
- `_forget` / `_nm.connect_wifi` call signatures unchanged.
- `setup_cleanup(self)`.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/network.py').read()); print('OK')"
grep -cE 'NetworkManagerHelper|nm-ready|network-changed|network-connect' files/usr/lib/adwaita-lite/settings/pages/network.py
# Expected: >= 6 (helper import + instantiation + 4 subscriptions)
grep -cE 'Gtk\.Window' files/usr/lib/adwaita-lite/settings/pages/network.py
# Expected: 0
grep -cE '_status_label' files/usr/lib/adwaita-lite/settings/pages/network.py
# Expected: 0 (removed in favour of toasts)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/network.py
# Expected: 0
```

### Commit

Template summary: *"Five groups: WiFi (AdwSwitchRow + scan button as group header-suffix + hidden-network chevron row), network list (dynamic AdwActionRows with signal-strength prefix icons and Connect/Forget suffix buttons, group description for empty state), Active Connection (.property info rows), Wired (single status row), Advanced (chevron to nm-connection-editor). Two modal Gtk.Window dialogs (password, hidden-network) become navigation-push sub-pages with AdwPasswordEntryRow + AdwComboRow inputs. Status label replaced by toasts."*

Preservation line: *"NetworkManagerHelper lazy init, _updating guard, all 4 event subscriptions, signal-strength icon thresholds, refresh-networks/active/wired logic, connect_wifi + forget_connection calls, setup_cleanup."*

---

## Task: Agent 3 — `panel` (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/panel.py`

### Top-level structure

Returns `Adw.NavigationView` wrapping self (for the pinned-apps add-dialog navigation push). Root NavigationPage titled `_("Panel")`.

### Groups (top-down)

1. **Position** — `Adw.ComboRow` with options Bottom / Top / Left / Right. Stored values `"bottom"`/`"top"`/`"left"`/`"right"`. `notify::selected` → `self._on_edge_changed(value)` — preserves the existing method semantics (save + update section labels + refresh module lists).
    - Agent may push back in favour of toggle-cards if 4 edges feel more spatial. Default: ComboRow.
2. **Density** — `Adw.ComboRow` with options Normal / Compact. Stored values `"normal"`/`"compact"`.
3. **Twilight** — `Adw.SwitchRow` titled `_("Twilight")`, subtitle `_("Invert panel colors from the system theme")`.
4. **Module Layout** — the existing 3-column custom editor (a `Gtk.ScrolledWindow` wrapping an HBox of 3 section columns, each with header label + ListBox of module rows) STAYS AS THE CUSTOM WIDGET. Wrap in an `Adw.PreferencesGroup` titled `_("Module Layout")`, with the scrolled window added via a wrapping `Adw.ActionRow` (`set_activatable(False)`, widget added via `add_suffix(scrolled)`) — same pattern as appearance.py's wallpaper grid.
5. **Pinned Apps** — `Adw.PreferencesGroup` titled `_("Pinned Apps")`, with `set_header_suffix(add_btn)` where `add_btn` is a flat `Gtk.Button.new_from_icon_name("list-add-symbolic")` that pushes the add-dialog sub-page. Pinned rows become `Adw.ActionRow` per app with icon prefix (`add_prefix`), name as title, `Forget`-style Remove button in the suffix (`.flat` or `.destructive-action`). `_refresh_pinned_list` rebuilds the group's children.
6. **Reset** — don't add a group; drop the reset button into the bottom of the Module Layout group (via a trailing Adw.ActionRow with a destructive suffix button). Title `_("Reset layout to defaults")`, subtitle omitted.

### Navigation push for add-pinned dialog

Replaces `_show_add_pinned_dialog`. `_push_add_pinned_page`:

```python
def _push_add_pinned_page(self):
    sub = Adw.NavigationPage()
    sub.set_title(_("Add Pinned App"))

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    inner = Adw.PreferencesPage()

    # Search as group description + a Gtk.SearchEntry suffix in the
    # header might be cleaner, but simpler: a dedicated group with a
    # search entry as its only row, plus an apps group below with one
    # AdwActionRow per .desktop app (icon prefix, name, Add button in
    # suffix).
    search_group = Adw.PreferencesGroup()
    # ... search entry that filters the apps group below ...

    apps_group = Adw.PreferencesGroup()
    apps_group.set_title(_("Applications"))
    # Populate from Gio.AppInfo.get_all() + should_show(), sorted.
    # Filter callback bound to the search entry.

    inner.add(search_group)
    inner.add(apps_group)
    toolbar.set_content(inner)
    sub.set_child(toolbar)
    self._nav.push(sub)
```

Each app row's Add button calls `_add_app_from_info(app_info)` and then `self._nav.pop()`.

### Preservation checklist

- `MODULE_NAMES`, `DEFAULT_LAYOUT`, `HORIZONTAL_LABELS`, `VERTICAL_LABELS`, `SECTION_ORDER` constants unchanged.
- `_load_default_layout`, `_load_layout`, all layout-mutation methods (`_reorder_module`, `_move_module`, `_refresh_module_lists`, `_build_module_row`) preserved — these drive the bespoke module layout editor, which stays custom.
- `_update_section_labels` called when edge changes.
- `_refresh_pinned_list` / `_build_pinned_row` — the row widget changes to `Adw.ActionRow`, but the list-mutation + `save_and_apply("pinned", ...)` logic is preserved.
- `_add_app_from_info` preserves the ThemedIcon/FileIcon icon-name extraction, `%u` arg stripping, empty-command toast.
- `_reset_layout` preserved.
- Store keys preserved: `edge`, `density`, `panel_twilight`, `layout`, `pinned`.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/panel.py').read()); print('OK')"
grep -cE 'save_and_apply' files/usr/lib/adwaita-lite/settings/pages/panel.py
# Expected: >= 5 (edge, density, panel_twilight, layout, pinned)
grep -cE 'MODULE_NAMES|DEFAULT_LAYOUT|HORIZONTAL_LABELS|VERTICAL_LABELS' files/usr/lib/adwaita-lite/settings/pages/panel.py
# Expected: >= 4 (each constant referenced at least once)
grep -cE 'Gtk\.Window' files/usr/lib/adwaita-lite/settings/pages/panel.py
# Expected: 0
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/panel.py
# Expected: 0
```

### Commit

Template summary: *"Six groups: Position (AdwComboRow), Density (AdwComboRow), Twilight (AdwSwitchRow), Module Layout (custom 3-column editor wrapped in an AdwActionRow suffix + reset row), Pinned Apps (dynamic AdwActionRow list with + header-suffix button for add, Remove suffix per row). The modal add-pinned Gtk.Window becomes an AdwNavigationPage push with a search entry and an AdwActionRow per installed .desktop app."*

Preservation line: *"all 5 save_and_apply call sites, MODULE_NAMES / DEFAULT_LAYOUT / HORIZONTAL_LABELS / VERTICAL_LABELS / SECTION_ORDER constants, the entire custom module-layout editor logic (_build_module_row, _reorder_module, _move_module, _refresh_module_lists, _update_section_labels), _load_layout, _load_default_layout, _add_app_from_info icon-extraction + %-arg stripping, _reset_layout."*

---

## Task: Agent 4 — `keyboard` (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`

### Top-level structure

Returns `Adw.NavigationView` wrapping self (for the shortcut capture navigation push). Root NavigationPage titled `_("Keyboard")`.

### Groups (top-down)

1. **Layout** —
    - `Adw.ComboRow` titled `_("Keyboard layout")`, model from `LAYOUT_NAMES` values for the codes returned by `_get_layouts()`. Keep the parallel `layout_codes` list; on selected change, save `keyboard_layout`+`keyboard_variant` via `store.save_dict_and_apply` (current atomic pattern).
    - `Adw.ComboRow` titled `_("Variant")`, dynamically rebuilt by `_build_variant_dropdown(layout_code)` when the layout changes. `set_visible(bool(variants))` preserved. If the variant list is empty, hide the row entirely.
2. **Repeat** —
    - `Adw.SpinRow.new_with_range(150.0, 1000.0, 50.0)` titled `_("Repeat delay")`, subtitle `_("Milliseconds before keys begin repeating")`. `set_value` seeded from `self.store.get("keyboard_repeat_delay", 300)`. `notify::value` → `save_debounced`.
    - `Adw.SpinRow.new_with_range(10.0, 80.0, 5.0)` titled `_("Repeat rate")`, subtitle `_("Keys per second when held")`. Same save pattern.
    - Agent may push back toward `Adw.ActionRow` + `Gtk.Scale` suffix (like mouse_touchpad's speed sliders) if SpinRow feels less discoverable. Default: SpinRow. Both are valid; SpinRow is marginally closer to the design spec's "spinner" note.
3. **Caps Lock** — `Adw.ComboRow` titled `_("Caps Lock key")`, subtitle `_("Remap Caps Lock to another function")`. Options: Default / Ctrl / Escape / Disabled. Values: `"default"`/`"ctrl"`/`"escape"`/`"disabled"`.
4. **Keyboard Shortcuts** — `Adw.PreferencesGroup` titled `_("Keyboard Shortcuts")`. One `Adw.ActionRow` per binding in `self._bindings`:
    - Title: `binding["display_name"]`
    - Subtitle: `_human_key_label(binding["key"])` — the shortcut rendered in the row's subtitle.
    - Suffix: if the binding differs from default, a `.flat` `Gtk.Button.new_from_icon_name("edit-undo-symbolic")` that calls `_reset_shortcut(index)` to revert this one shortcut.
    - `set_activatable(True)`; `activated` signal → `self._push_capture_page(index)`.

    Reset-all is a trailing `Adw.ActionRow` inside the same group with a destructive-styled button in the suffix, or a separate small group with just the reset-all action row. Either reads fine.

### Navigation push for shortcut capture

Replaces the in-place `_start_capture` / `_cancel_capture` flow. `_push_capture_page(index)` builds an `Adw.NavigationPage` containing an `Adw.StatusPage` with icon `"input-keyboard-symbolic"`, title `_("Press the new shortcut")`, description explaining Escape to cancel. The `Gtk.EventControllerKey` attaches to the sub-page (not the window). On key captured:
- Validate via the existing `_build_key_string` + `_find_conflict`.
- On conflict: reuse the existing `Adw.AlertDialog` flow (which already exists; the `_show_conflict_dialog` method). The flow still presents the dialog on the capture page's window; Reassign response applies the new key and pops the capture page.
- On success (no conflict): call `_apply_new_key(index, new_key)` (which updates `self._bindings[index]["key"]`, sets the binding's ActionRow subtitle to the new human-readable label, and `_save_and_reconfigure`), then `self._nav.pop()`.

The `_shortcut_buttons` list that cached capture-button refs goes away. Instead, cache a list `self._shortcut_rows` of the `Adw.ActionRow` instances so `_apply_new_key` / `_reset_shortcut` can update their subtitles.

### Preservation checklist

- `LAYOUT_NAMES`, `SYSTEM_RC_XML`, `USER_KEYBINDINGS`, `SHORTCUT_NAMES`, `_SKIP_KEYS`, `_MODIFIER_KEYVALS` constants unchanged.
- Module-level helpers unchanged: `_human_key_label`, `_get_action_name`, `_parse_system_keybindings`, `_load_user_keybindings`, `_save_user_keybindings`.
- Class-level: `self._default_bindings` (from system rc.xml), `self._bindings` (merged with user overrides) — preserved.
- `_get_default_key`, `_build_key_string`, `_find_conflict`, `_apply_new_key`, `_reset_shortcut`, `_reset_all_shortcuts`, `_save_and_reconfigure` — preserved with only the widget-update lines changed (subtitle on AdwActionRow instead of button label).
- Existing `Adw.AlertDialog` conflict flow preserved as-is (already Adw-native).
- `store.save_dict_and_apply` atomic save for `{keyboard_layout, keyboard_variant}` preserved.
- All 4 `localectl list-x11-keymap-*` subprocess calls preserved.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/keyboard.py').read()); print('OK')"
grep -cE '_parse_system_keybindings|_load_user_keybindings|_save_user_keybindings' files/usr/lib/adwaita-lite/settings/pages/keyboard.py
# Expected: >= 4 (definitions + call sites)
grep -cE 'SHORTCUT_NAMES|LAYOUT_NAMES|_MODIFIER_KEYVALS' files/usr/lib/adwaita-lite/settings/pages/keyboard.py
# Expected: >= 3
grep -cE 'localectl' files/usr/lib/adwaita-lite/settings/pages/keyboard.py
# Expected: >= 2 (list-x11-keymap-layouts + list-x11-keymap-variants)
grep -cE 'save_and_apply|save_debounced|save_dict_and_apply' files/usr/lib/adwaita-lite/settings/pages/keyboard.py
# Expected: >= 4 (repeat_delay debounced, repeat_rate debounced, capslock, keyboard_layout+variant dict)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/keyboard.py
# Expected: 0
```

### Commit

Template summary: *"Four groups: Layout (AdwComboRow for layout + dynamically-built variant AdwComboRow hidden when empty), Repeat (two AdwSpinRows for delay + rate), Caps Lock (AdwComboRow), Keyboard Shortcuts (AdwActionRow per binding with per-row reset suffix and activated-row → capture navigation push). The in-place capture via a window-level EventControllerKey is replaced by an AdwNavigationPage with an AdwStatusPage + its own EventControllerKey."*

Preservation line: *"LAYOUT_NAMES / SHORTCUT_NAMES / SYSTEM_RC_XML / USER_KEYBINDINGS / _MODIFIER_KEYVALS constants, all module-level parsers and writers, _build_key_string / _find_conflict / _apply_new_key / _reset_shortcut / _reset_all_shortcuts / _save_and_reconfigure logic, the existing AdwAlertDialog conflict flow, save_dict_and_apply atomic layout+variant write, both localectl subprocess helpers."*

---

## Controller tasks after agents finish

- [ ] **Step 1: Confirm 4 commits locally**

```bash
git log --oneline HEAD~4..HEAD
```

Expected: four `feat(settings): convert <page> to Adw.PreferencesPage (wave 3)` commits.

- [ ] **Step 2: Spec-compliance reviews (parallel)** — one per commit, each with the per-page task section + pilot + one wave-2 reference.

- [ ] **Step 3: Code-quality reviews (parallel, after spec passes)** — one per commit, each with the pre-migration version + reference pack.

- [ ] **Step 4: Push**

```bash
git push
```

- [ ] **Step 5: Hardware smoke test**

After CI build completes, update target and verify each page:

- **Display** — Scale ComboRow triggers AdwAlertDialog with live-updating countdown in the body; clicking Revert restores the previous scale; auto-revert at 0s also restores. Resolution per-display expander expands/collapses; mode change triggers the same revert flow. Night Light toggle + temperature slider work; custom schedule expander reveals/hides start/end time rows. Open wdisplays row launches the app.
- **Network** — WiFi switch toggles adapter; network list populates after scan; connect on open network goes straight through; connect on secured network pushes the password sub-page and back-gestures correctly. Hidden network push works. Connecting toast appears, success toast appears, forget-button works on active connection. Wired status row updates. Advanced row launches nm-connection-editor.
- **Panel** — Position / Density combos apply live. Twilight switch flips. Module layout editor's arrow buttons move modules between sections and within sections; reset-layout restores defaults. Pinned Apps "+" header suffix pushes the app picker with working search; Remove suffix removes from the list.
- **Keyboard** — Layout combo populates variants on change without spurious polkit. Repeat-delay / repeat-rate spin rows debounce-save. Caps Lock combo applies. Tapping a shortcut row pushes the capture page; pressing a shortcut there returns with the new key shown as subtitle; Escape on capture page cancels and pops. Conflict dialog still appears when choosing a taken key. Reset-All restores defaults.

If any page misbehaves, `git revert <sha>` and re-dispatch the agent.

---

## Completion criteria

- Four commits on `origin/main`, each converting one wave-3 page.
- All four pages inherit from `BasePage` + `Adw.PreferencesPage`.
- `base.py` factories still intact (Phase 4 removes them).
- Zero plain `Gtk.Window` dialog classes remaining in any page (both Display's revert windows → AlertDialog, Network's password + hidden → nav pushes, Panel's add-pinned → nav push, Keyboard's capture → nav push).
- Hardware smoke test passes for every converted page.
- Wave 3 complete — Phase 4 (CSS cleanup + BasePage slim) is next.
