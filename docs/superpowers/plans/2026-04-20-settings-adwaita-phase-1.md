# Settings Adwaita Migration — Phase 1 (Wave 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Tasks run **concurrently** — each of the six agents converts one page file, then the controller reviews and commits six separate commits (one per page). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the six "clean-map" pages of the settings app to `Adw.PreferencesPage` + stock `Adw.*Row` widgets, following the patterns established by the `power_lock` pilot in Phase 0.

**Architecture:** Six parallel Sonnet subagents, one per page. Each agent:

1. Reads the pilot (`files/usr/lib/adwaita-lite/settings/pages/power_lock.py`) as reference
2. Reads the reference pack (`docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`) for patterns
3. Reads their page-specific task section in this plan for target row types, preservation checklist, and UX touches
4. Rewrites their assigned page, commits as a single-file commit with the exact message template provided, does not push

After all six agents finish, the **controller** runs spec + quality reviewers per page, addresses issues, then pushes the batch. `BasePage.make_*` widget factories stay in place — other pages (waves 2 & 3) still use them.

**Tech Stack:** Python 3.13, PyGObject, GTK 4, libadwaita.

**References:**
- Pilot: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py` (commit `842a98b`, annotated in `7f9473f`)
- Design: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Reference pack: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`
- Phase 0 plan (for context on the conversion pattern): `docs/superpowers/plans/2026-04-20-settings-adwaita-phase-0.md`

---

## Shared expectations for every wave-1 agent

All six agents must do these things in addition to their page-specific work:

1. **Inheritance pattern** — Inherit from both `BasePage` and `Adw.PreferencesPage`. Initialise each explicitly:
   ```python
   def __init__(self, store, event_bus):
       BasePage.__init__(self, store, event_bus)
       Adw.PreferencesPage.__init__(self)
   ```
2. **build() returns self** — Populate the page via `self.add(group)` and `return self`. `window.py`'s lazy-build machinery uses the return value as the widget to stack; since our page *is* the widget, returning self works.
3. **Imports** — Replace `from gi.repository import ... Gtk` with `from gi.repository import Adw, ... Gtk`, add `gi.require_version("Adw", "1")` beside the `Gtk` version requirement.
4. **No `self.make_*` calls** — Delete every call to `make_page_box`, `make_group`, `make_setting_row`, `make_info_row`, `make_toggle_cards`. Replace with `Adw.PreferencesGroup` / the correct `Adw.*Row`.
5. **Signal semantics** — For switches, use `notify::active` instead of `state-set`. The return-value contract from `state-set` (`return False`) is gone; `notify::active` has no return value.
6. **Preserve every `store.save_and_apply` / `store.save_debounced` / `self.subscribe` call** from the pre-migration file, targeting the same keys, with the same transforms. The spec-compliance reviewer will verify.
7. **Preserve `setup_cleanup(self)`** wherever the pre-migration code called `self.setup_cleanup(page)` — except pass `self` instead of `page` because the page *is* the widget now. If the pre-migration code didn't call it, don't add it.
8. **Omit empty subtitles** — `row.set_subtitle("")` is not a no-op and wastes a row of visual space. Just don't call `set_subtitle` if the text would be empty.
9. **Do not introduce navigation-push flows.** The design spec's more aggressive UX recommendations (push a timezone list, push a language picker) are out of scope for wave 1. Those pages stay as `AdwComboRow` or `AdwEntryRow` for now. Agents who push back on this can do so in their report, but default is: keep it flat in wave 1.
10. **Commit message format** — Each agent commits once with this template (filled in per page):
    ```
    feat(settings): convert <page> to Adw.PreferencesPage (wave 1)

    <2-3 sentence description of what changed, row-type mapping>

    Preserves: <comma-separated list of wiring kept intact>.

    Part of the Adwaita migration wave 1. See
    docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md.

    Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
    ```

---

## File plan

Six pages modified. `base.py`, `window.py`, `pages/__init__.py` are untouched.

| Page | File | Complexity | Agent |
|---|---|---|---|
| Mouse & Touchpad | `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py` | Low (switches + scales + toggle-cards) | Agent 1 |
| Accessibility | `files/usr/lib/adwaita-lite/settings/pages/accessibility.py` | Low-Med (switches + dropdown + stateful large-text toggle) | Agent 2 |
| Date & Time | `files/usr/lib/adwaita-lite/settings/pages/datetime.py` | Med (entry + switches + live-updating time label + subprocess timezone) | Agent 3 |
| Default Apps | `files/usr/lib/adwaita-lite/settings/pages/default_apps.py` | Low-Med (dynamic dropdowns with loading guard) | Agent 4 |
| Language & Region | `files/usr/lib/adwaita-lite/settings/pages/language.py` | Low-Med (two dropdowns + info banner + loading guard) | Agent 5 |
| Sound | `files/usr/lib/adwaita-lite/settings/pages/sound.py` | Med-High (dropdowns + scales + switches, live pactl events, updating flag) | Agent 6 |

---

## Task: Agent 1 — `mouse_touchpad`

**File:** `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py`

### Row mapping

| Setting (store key) | Current widget | Target row |
|---|---|---|
| `touchpad_tap_to_click` | `Gtk.Switch` | `Adw.SwitchRow` |
| `touchpad_natural_scroll` | `Gtk.Switch` | `Adw.SwitchRow` |
| `touchpad_pointer_speed` | `Gtk.Scale` (-1.0..1.0 step 0.1) | `Adw.ActionRow` + `Gtk.Scale` as suffix (pattern in reference pack, "Row with custom suffix widget") |
| `touchpad_scroll_speed` | `Gtk.Scale` (1..10 step 1) | `Adw.ActionRow` + `Gtk.Scale` as suffix |
| `mouse_natural_scroll` | `Gtk.Switch` | `Adw.SwitchRow` |
| `mouse_pointer_speed` | `Gtk.Scale` (-1.0..1.0 step 0.1) | `Adw.ActionRow` + `Gtk.Scale` as suffix |
| `mouse_accel_profile` | toggle-cards (adaptive/flat) | `Adw.ComboRow` (options: Adaptive, Flat; stored values `"adaptive"`, `"flat"`) |

### Two groups

1. **Touchpad** — containing tap-to-click (SwitchRow), natural-scroll (SwitchRow), pointer-speed (ActionRow+Scale), scroll-speed (ActionRow+Scale).
2. **Mouse** — containing natural-scroll (SwitchRow), pointer-speed (ActionRow+Scale), acceleration (ComboRow).

### Preservation checklist

- All 7 `save_and_apply` / `save_debounced` calls (one per key above). Pointer-speed uses `save_debounced` (1 Hz), not `save_and_apply` — preserve that distinction. Scroll speed uses `save_debounced` too.
- Subtitle on natural-scroll (touchpad): `_("Content moves with your fingers")`.
- No `subscribe` calls in the current file; none to add.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py').read()); print('OK')"
grep -cE 'save_and_apply|save_debounced' files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py
# Expected: 7
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py
# Expected: 0
```

### Commit

Template summary for this page: *"Two groups (Touchpad / Mouse) using AdwSwitchRow for boolean toggles, AdwActionRow with Gtk.Scale suffix for the four speed sliders, and AdwComboRow for the mouse acceleration profile (Adaptive / Flat)."*

Preservation line: *"all 7 save_and_apply/save_debounced calls, the pointer-speed debounced-save cadence, the natural-scroll subtitle on the touchpad row."*

---

## Task: Agent 2 — `accessibility`

**File:** `files/usr/lib/adwaita-lite/settings/pages/accessibility.py`

### Row mapping

| Setting | Current widget | Target row |
|---|---|---|
| Large text (switches `font_size` between `self._prev_font_size` and 15) | `Gtk.Switch` | `Adw.SwitchRow` |
| `cursor_size` | `Gtk.DropDown` (Default/Large/Larger) | `Adw.ComboRow` |
| `high_contrast` | `Gtk.Switch` | `Adw.SwitchRow` |
| `reduce_motion` | `Gtk.Switch` | `Adw.SwitchRow` |

### One group

All four rows in a single `Adw.PreferencesGroup` titled `_("Accessibility")`.

### Preservation checklist

- **Stateful large-text toggle** — the current handler:
  - On toggle ON: records current font_size if < 15, then saves font_size=15.
  - On toggle OFF: restores `self._prev_font_size` if < 15, else 11.
  - The `self._prev_font_size` attribute set in `__init__` and updated on each ON transition must survive the conversion. Replace `state-set` with `notify::active`; the logic is otherwise identical.
- Row subtitles preserved:
  - Large text: `_("Increases font size for better readability")`
  - High contrast: `_("Forces dark theme with stronger borders")`
  - Reduce motion: `_("Disables animations throughout the interface")`
- All 4 `save_and_apply` calls preserved (font_size, cursor_size, high_contrast, reduce_motion).

### UX touch: deferred

The design spec suggested `AdwBanner` when high-contrast is active but the adw-gtk3 theme failed to apply. **Skip this for wave 1** — detecting the failure requires reading theme state, which isn't instrumented today. Leave as a Phase 5 polish item.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/accessibility.py').read()); print('OK')"
grep -cE 'save_and_apply' files/usr/lib/adwaita-lite/settings/pages/accessibility.py
# Expected: 4
grep -cE '_prev_font_size' files/usr/lib/adwaita-lite/settings/pages/accessibility.py
# Expected: >= 3 (init, read inside _on_large_text, write inside _on_large_text)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/accessibility.py
# Expected: 0
```

### Commit

Template summary: *"One Accessibility group; three SwitchRows (large text, high contrast, reduce motion) and one ComboRow (cursor size). The large-text toggle's font-size swap logic and `self._prev_font_size` memoisation preserved exactly."*

Preservation line: *"all 4 save_and_apply calls, the stateful large-text font-size swap (preserves user's previous font size on toggle-off), and row subtitles."*

---

## Task: Agent 3 — `datetime`

**File:** `files/usr/lib/adwaita-lite/settings/pages/datetime.py`

### Row mapping

| Setting | Current widget | Target row |
|---|---|---|
| Live-updating time label | `Gtk.Label` with `.group-title` class, inside the group's row area | Either `Adw.ActionRow` with the time as subtitle (updated via `set_subtitle`), or as the group's description via `group.set_description()` (updated via the same 1Hz timer) — agent's call. Description-style is cleaner; ActionRow-with-subtitle is more explicit. |
| Timezone | `Gtk.Entry` with placeholder + Enter-to-apply | `Adw.EntryRow` with `set_show_apply_button(True)` — on `apply` signal, call `self._set_timezone(row.get_text().strip(), row)` |
| Automatic time (NTP) | `Gtk.Switch` | `Adw.SwitchRow` |
| 24-hour clock | `Gtk.Switch` | `Adw.SwitchRow` |

### One group

Single `Adw.PreferencesGroup` titled `_("Date & Time")`.

### Preservation checklist

- **Live time label** — The 1Hz GLib timer + map/unmap lifecycle (setting `self._mapped = True/False`, adding a timer via `GLib.timeout_add_seconds(1, self._update_time)`, cancelling via `GLib.source_remove(self._timer_id)`) **must be preserved**. The map/unmap signals are connected to `page` in the old code; connect them to `self` in the new version (the page *is* the widget now).
- The `_update_time` method checks `self._mapped` at the top and returns `SOURCE_REMOVE` if unmapped. Keep that guard.
- Clock format depends on `self.store.get("clock_24h", False)` — preserved.
- `self._set_timezone` and `self._set_ntp` subprocess+thread flows preserved verbatim.
- Error CSS class: the old code adds `error` to the Entry on failure, removes on success. With `Adw.EntryRow`, the `.error` style class works the same way. Preserve.

### UX touches deferred

- Design spec wanted timezone as a navigation-push to a searchable timezone list. **Skip for wave 1** — that's a ~300-line nav view with search entry and scrolling list. Keep the EntryRow for now; flag as Phase 5 polish.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/datetime.py').read()); print('OK')"
grep -cE '_timer_id|_mapped|_update_time' files/usr/lib/adwaita-lite/settings/pages/datetime.py
# Expected: >= 6 (timer + mapped + update_time each appear in setter, reader, and teardown)
grep -cE 'timedatectl' files/usr/lib/adwaita-lite/settings/pages/datetime.py
# Expected: 4 (Timezone get, NTP get, Timezone set, NTP set)
grep -cE 'save_and_apply' files/usr/lib/adwaita-lite/settings/pages/datetime.py
# Expected: 1 (only clock_24h persists through the store; timezone/ntp persist via timedatectl)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/datetime.py
# Expected: 0
```

### Commit

Template summary: *"One Date & Time group. Timezone uses AdwEntryRow with apply-button; NTP and 24-hour clock are AdwSwitchRows. The live-updating time label is rendered as the group's description (refreshed on the existing 1 Hz timer), with the map/unmap lifecycle rewired to self."*

Preservation line: *"clock_24h save_and_apply, timedatectl subprocess flows for timezone + NTP, 1 Hz live-clock timer with map/unmap-driven lifecycle, entry error styling on invalid timezone."*

---

## Task: Agent 4 — `default_apps`

**File:** `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`

### Row mapping

- For each `(label, mime_type)` in `APP_MIME_TYPES` where `_get_apps_for_mime(mime_type)` returns a non-empty list: one `Adw.ComboRow` per handler.
- Single `Adw.PreferencesGroup` titled `_("Default Applications")`.

### Preservation checklist

- **The `_loading` guard flag** — The current code uses a mutable `_loading = [True]` closure to skip the initial `set_selected` triggering `notify::selected`. PyGObject's Adw.ComboRow does *not* fire `notify::selected` when `set_selected` is called with the same index as the current selection, but it *does* fire when the initial state differs (e.g. index 0 → index 3). Keep the guard pattern for safety.
- **Terminal special-case** — `mime_type is None` triggers the `_set_terminal_by_id` wrapper that writes a custom `terminal.desktop` file. Preserved verbatim.
- **xdg-mime subprocess call** on selection change, preserved.
- `APP_MIME_TYPES` and the static helpers (`_set_terminal_by_id`, `_set_terminal`, `_get_apps_for_mime`, `_get_default_app`) are unchanged — copy them across.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/default_apps.py').read()); print('OK')"
grep -cE 'xdg-mime' files/usr/lib/adwaita-lite/settings/pages/default_apps.py
# Expected: 2 (one read, one write)
grep -cE '_set_terminal' files/usr/lib/adwaita-lite/settings/pages/default_apps.py
# Expected: >= 4 (def _set_terminal_by_id, def _set_terminal, call site inside handler, + internal ref)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/default_apps.py
# Expected: 0
```

### Commit

Template summary: *"One Default Applications group with one AdwComboRow per handler (Web Browser, File Manager, Terminal, Text Editor, Image Viewer, PDF Viewer, Media Player, Email Client). Rows are generated dynamically from `APP_MIME_TYPES` and `_get_apps_for_mime`."*

Preservation line: *"xdg-mime read/write for each non-terminal handler, the custom terminal.desktop writer for the terminal special-case, and the loading-flag guard that prevents the initial set_selected from firing the handler."*

---

## Task: Agent 5 — `language`

**File:** `files/usr/lib/adwaita-lite/settings/pages/language.py`

### Row mapping

| Setting | Current widget | Target row |
|---|---|---|
| "Changes take effect after logging out" info | `Gtk.Label` with `.setting-subtitle` class | `Adw.Banner` at the top of the page (called BEFORE `self.add(group)`; banners live outside groups) |
| System language | `Gtk.DropDown` | `Adw.ComboRow` |
| Regional formats | `Gtk.DropDown` | `Adw.ComboRow` |

### One group + one banner

- `Adw.Banner.new(_("Changes take effect after logging out"))`, `set_revealed(True)`, added directly to the page via `self.add(banner)` (PreferencesPage accepts banners as direct children).
- `Adw.PreferencesGroup` titled `_("Language & Region")` containing the two ComboRows.

### Preservation checklist

- **The `loaded` flag** — Same pattern as default_apps: mutable `loaded = [False]` closure, flipped to True AFTER both `set_selected` calls in `build()`. Preserve. Without this, the initial load fires `localectl` + polkit.
- Both `_set_locale` and `_set_format` methods preserved verbatim.
- `_get_locales`, `_get_current_locale`, `_get_current_format` unchanged.

### UX touches deferred

- Design spec wanted a navigation-push language picker. **Skip for wave 1** — too heavy for a clean-map wave. Keep the ComboRow. Flag as Phase 5 polish.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/language.py').read()); print('OK')"
grep -cE 'localectl' files/usr/lib/adwaita-lite/settings/pages/language.py
# Expected: 5 (list-locales, status x2, set-locale x2)
grep -cE 'loaded\[0\]' files/usr/lib/adwaita-lite/settings/pages/language.py
# Expected: >= 4 (definition, write-True at end of build, guard in lang handler, guard in format handler)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/language.py
# Expected: 0
```

### Commit

Template summary: *"One Language & Region group with two AdwComboRows (System language, Regional formats). The 'Changes take effect after logging out' info becomes an AdwBanner at the top of the page."*

Preservation line: *"localectl subprocess flows for both setters, the loaded-flag guard that prevents the initial set_selected from triggering polkit, and the regional-formats subtitle."*

---

## Task: Agent 6 — `sound`

**File:** `files/usr/lib/adwaita-lite/settings/pages/sound.py`

### Row mapping

| Setting | Current widget | Target row |
|---|---|---|
| Output device | `Gtk.DropDown` | `Adw.ComboRow` (model + selected wired the same way as in the pilot's power-profile pattern) |
| Output volume | `Gtk.Scale` 0..100 | `Adw.ActionRow` with `Gtk.Scale` as suffix (same pattern as mouse_touchpad speed sliders) |
| Output mute | `Gtk.Switch` | `Adw.SwitchRow` |
| Input device | `Gtk.DropDown` | `Adw.ComboRow` |
| Input volume | `Gtk.Scale` 0..100 | `Adw.ActionRow` with `Gtk.Scale` as suffix |
| Input mute | `Gtk.Switch` | `Adw.SwitchRow` |

Volume scales keep `set_draw_value(True)` + `set_format_value_func(lambda _s, v: f"{v:.0f}%")` for the percentage display, unlike mouse_touchpad's suffix scales which hide the value.

### Two groups

1. **Output** — sink ComboRow, volume ActionRow+Scale, mute SwitchRow.
2. **Input** — source ComboRow, volume ActionRow+Scale, mute SwitchRow.

### Preservation checklist

- **`self._updating` flag** — guards every user-interaction handler and `_refresh()`. Prevents handler feedback loops when `_refresh` rewrites widget state during an external PulseAudio event. Must be preserved with the identical `if self._updating: return` gate at the top of every handler.
- **Widget refs held on `self`** — the six widgets (`self._sink_dd`, `self._out_vol`, `self._out_mute`, `self._source_dd`, `self._in_vol`, `self._in_mute`) and two name-list refs (`self._sink_names`, `self._source_names`) are rewritten by `_refresh()`. After the conversion, these refs point at `Adw.ComboRow` / `Adw.SwitchRow` / the inner `Gtk.Scale`, not the old `Gtk.DropDown` / `Gtk.Switch`. Update `_refresh()`'s code accordingly — it calls `set_model`, `set_selected`, `set_value`, `set_active`, all of which exist on the new types.
- **Map/unmap lifecycle** — `page.connect("map", _on_map)` / `page.connect("unmap", _on_unmap)` in the old code manages `PulseAudioSubscriber` lifetime. Rewire to `self.connect("map", ...)` / `self.connect("unmap", ...)`.
- **`self.subscribe("audio-changed", ...)`** — preserved. `setup_cleanup(self)` preserved.
- **All 6 `pactl` subprocess calls** — preserved verbatim (set-default-sink, set-sink-volume, set-sink-mute, set-default-source, set-source-volume, set-source-mute).
- **Empty-device-list fallback strings** — `_("(No output devices)")` and `_("(No input devices)")` preserved. If the list is empty we pass a single-item StringList containing the fallback.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/sound.py').read()); print('OK')"
grep -cE 'self\._updating' files/usr/lib/adwaita-lite/settings/pages/sound.py
# Expected: >= 10 (init, set True / False in _refresh's try/finally, guard at top of 6 handlers)
grep -cE 'pactl' files/usr/lib/adwaita-lite/settings/pages/sound.py
# Expected: >= 10 (6 setters + 4 getters in static helpers)
grep -cE 'self\.subscribe|setup_cleanup|PulseAudioSubscriber' files/usr/lib/adwaita-lite/settings/pages/sound.py
# Expected: >= 3 (subscribe, setup_cleanup, PulseAudioSubscriber instantiation)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/sound.py
# Expected: 0
```

### Commit

Template summary: *"Two groups (Output / Input) each with an AdwComboRow for device selection, an AdwActionRow with a Gtk.Scale suffix for volume (draw_value=True with percentage formatting), and an AdwSwitchRow for mute. The audio-changed event-bus subscription, _refresh's widget-state rewrite, and the PulseAudioSubscriber map/unmap lifetime are all preserved."*

Preservation line: *"6 pactl setters, audio-changed subscription, PulseAudioSubscriber lazy start/stop on map/unmap, _refresh reapplication logic, and the _updating reentrancy guard on all handlers."*

---

## Controller tasks after agents finish

Agents work in parallel; after all six have reported DONE, the controller runs reviews sequentially.

- [ ] **Step 1: Confirm all six commits exist locally**

```bash
git log --oneline HEAD~6..HEAD
```

Expected: six commits, each `feat(settings): convert <page> to Adw.PreferencesPage (wave 1)`.

If any commit is missing, re-dispatch the agent whose page didn't land.

- [ ] **Step 2: For each commit, run spec-compliance review**

Dispatch the spec-compliance reviewer subagent with: commit SHA, this plan's per-page task section, the pilot's file path. Reviewer verifies the commit matches the task section. Fix loop until ✅.

- [ ] **Step 3: For each commit (after spec ✅), run code-quality review**

Dispatch the code-quality reviewer subagent with: commit SHA, the pre-migration version at `git show HEAD~6:<path>` (for the first commit; adjust offset per position), the reference pack. Reviewer verifies signal wiring, lifecycle, no regressions. Fix loop until ✅.

- [ ] **Step 4: After all six reviews are ✅, push**

```bash
git push
```

Expected: six commits land on `origin/main`. CI build triggers.

- [ ] **Step 5: Hardware smoke test**

After the CI build completes, update the target machine and verify each page in the settings app:

- **Mouse & Touchpad** — two groups visible, switches toggle live, pointer-speed slider moves and its value persists (check `~/.config/adwaita-lite/settings.json`), accel dropdown switches.
- **Accessibility** — four rows; toggling Large Text up and then back down restores the original font size (not permanently set to 11).
- **Date & Time** — live time updates every second; timezone entry accepts input and shows error on invalid; NTP / 24-hour switches toggle.
- **Default Apps** — each of the 8 handler rows renders; changing the Web Browser entry updates `xdg-settings get default-web-browser`.
- **Language & Region** — banner shows at top; dropdowns do not prompt polkit on page load; changing language triggers the polkit dialog once.
- **Sound** — volume slider moves live with system audio; changing default sink via command line (`pactl set-default-sink ...`) updates the dropdown within ~1 second; mute toggle takes effect immediately.

If any smoke test fails, `git revert` the specific commit and re-dispatch that agent.

---

## Completion criteria

- All six pages in `files/usr/lib/adwaita-lite/settings/pages/` inherit from both `BasePage` and `Adw.PreferencesPage`.
- `base.py`'s `make_*` factories are still present (waves 2 & 3 need them).
- All six commits are on `origin/main`.
- Hardware smoke test passes for every converted page.
- Wave 1 reference material (the six committed files) is ready to serve as additional pattern context for waves 2 and 3.
