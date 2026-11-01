# Settings App — Phase 5 Audit Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Dispatch follows a two-wave sequence: one atomic Sonnet commit, then a six-agent parallel fanout (5 Opus + 2 Sonnet). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Close every Critical, Important, Adaptive, Accessibility, and Architecture finding from the post-Phase-4 audit (`docs/superpowers/specs/2026-04-20-settings-adwaita-audit.md`). Principle: **match GNOME HIG**. Keep the single 700sp collapse breakpoint; replace non-standard fixed-width widgets with patterns that libadwaita's native adaptive layout handles automatically. The app must render correctly on 1366×768 Chromebook screens at up to 200% Large Text scaling, which lands near 683×384 logical px.

**Architecture:** Two waves, three classes of agent work:

1. **Wave A — Critical atomic commit (1 Sonnet agent).** The five type-check bugs + one subprocess timeout. Mechanical, low risk, fast. Must land before any other Wave-5 agent because it touches files that later agents edit.
2. **Wave B — Parallel fanout (5 Opus + 2 Sonnet).**
   - 5 Opus agents, one per page that has judgment-intensive adaptive work (mouse_touchpad, sound, display, appearance, panel).
   - 1 Sonnet agent for architectural cleanup (outer ScrolledWindow removal + CSS touch-ups).
   - 1 Sonnet agent for the mechanical toast-on-silent-failure sweep across 5 pages.

**Tech stack:** Python 3.13, PyGObject, GTK 4, libadwaita.

**References:**
- Audit: `docs/superpowers/specs/2026-04-20-settings-adwaita-audit.md` (commit `570eaaa`)
- Reference pack: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`
- Design: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Wave-2 nav-push pattern: `docs/superpowers/plans/2026-04-20-settings-adwaita-phase-2.md`

---

## Shared expectations

Same rules as every prior wave. Re-stated compactly:

1. Every page still inherits `(BasePage, Adw.PreferencesPage)` with dual explicit `__init__`.
2. `build()` returns the root widget that goes into `window.py`'s `Gtk.Stack`. This may be `self`, `self._nav`, an `Adw.ToolbarView` wrapping `self`, or (in the D-Bus-failure and no-displays paths) a bare `Adw.StatusPage`. All are legal `Gtk.Widget` children of the stack.
3. No `self.make_*` factories remain (verified in Phase 4).
4. Every `store.save_and_apply` / `store.save_debounced` / `subscribe` / `setup_cleanup` call from the pre-remediation file is preserved.
5. `setup_cleanup` targets the widget that actually leaves the visible tree when navigating away (usually `self`; `self._nav` when the page wraps itself in a `NavigationView`; the ToolbarView wrapper when the page wraps in one).
6. Agents may push back on specific recommendations with written rationale in their DONE report.

---

## Agent dispatch table

| Agent | Phase | Model | Files | Scope |
|---|---|---|---|---|
| **A** | 5A | Sonnet | `bluetooth.py`, `language.py`, `network.py`, `users.py`, `display.py`, `default_apps.py` | C1–C5 + I1 atomic |
| **B1** | 5B | Sonnet | `window.py`, `css/style.css` | AR1 outer-scroll removal + AC1 em-sizing + AC2 padding + AC3 accent-circle min-size |
| **B2** | 5B | Sonnet | `users.py`, `bluetooth.py`, `network.py`, `datetime.py`, `keyboard.py` | I2 toast-on-silent-failure sweep (one-line adds) |
| **C1** | 5B | Opus | `mouse_touchpad.py` | A1 — three 200px `Gtk.Scale` suffixes → let libadwaita flex |
| **C2** | 5B | Opus | `sound.py` | A1 — two 200px volume `Gtk.Scale` suffixes + I3 (refresh comment) |
| **C3** | 5B | Opus | `display.py` | A1 — night-light temperature `Gtk.Scale` + revisit night-light group layout |
| **C4** | 5B | Opus | `appearance.py` | A2 accent HBox → `FlowBox` + A3 wallpaper-grid narrow-width behaviour |
| **C5** | 5B | Opus | `panel.py` | A4 — module editor adaptive collapse + preserve drag/move semantics |

Wave 5A (Agent A) runs solo. Wave 5B (B1, B2, C1–C5) runs with **7 agents in parallel** after A lands.

**Model allocation rationale** (Opus:Sonnet = 5:3, 62.5% Opus):
- Opus: per-page adaptive work where GNOME HIG-adherent alternatives require judgment (Scale vs SpinRow vs row-layout; FlowBox column counts; vertical-collapse UX choices; per-page regression analysis). Not wasteful — these agents make non-obvious UX decisions holding full page context.
- Sonnet: mechanical work. Critical-bug type fixes, window.py scroll removal, CSS 4-line tweaks, and the 5-file toast sweep are all grep-pattern changes. Opus here would be waste.

---

## Pre-flight audits

Before dispatching anything, confirm the audit's assumed state still holds.

- [ ] **Step 1: Verify the 5 Critical bugs are still present**

```bash
echo "=== Critical sites audit ==="
grep -nE '^\s*self\.add\((banner|self\._banner|status)\)' \
    files/usr/lib/adwaita-lite/settings/pages/{bluetooth,language,network,users}.py
grep -nE 'group\.add\(status\)' \
    files/usr/lib/adwaita-lite/settings/pages/display.py
```

Expected: 5 hits total, matching the audit.

- [ ] **Step 2: Verify the 200px Scale sites are still present**

```bash
grep -nE 'set_size_request\(200, -1\)' \
    files/usr/lib/adwaita-lite/settings/pages/*.py
```

Expected: 6 hits (display×1, mouse_touchpad×3, sound×2).

- [ ] **Step 3: Verify the outer ScrolledWindow pattern is still in `window.py`**

```bash
grep -nE '_content_scroll|Gtk\.ScrolledWindow' \
    files/usr/lib/adwaita-lite/settings/window.py
```

Expected: matches the audit's description.

If any audit assumption has shifted (someone else fixed partially, or a page was touched), adjust the per-agent briefings accordingly before dispatching.

---

## Wave 5A — Critical + I1 (Sonnet, atomic)

**Agent A scope:** six files, six fixes, one commit.

### Fix detail per bug

**C1–C3 — banner wrapping** (bluetooth, language, network)

The canonical fix is to wrap the `Adw.PreferencesPage` in an `Adw.ToolbarView` so the banner can live as a top bar. Build at the end of `build()` and return the wrapper instead of `self`:

```python
# For bluetooth and language:
wrapper = Adw.ToolbarView()
self._banner = Adw.Banner.new(_("No Bluetooth adapter found"))  # or appropriate text
self._banner.set_revealed(not self._bt.available)
wrapper.add_top_bar(self._banner)
wrapper.set_content(self)
self.setup_cleanup(wrapper)
return wrapper

# For network, which already has self._nav:
root_toolbar = Adw.ToolbarView()
self._banner = Adw.Banner.new(_("No network adapter"))
self._banner.set_revealed(not self._nm.ready)
root_toolbar.add_top_bar(self._banner)
root_toolbar.set_content(self)

self._nav = Adw.NavigationView()
root_page = Adw.NavigationPage()
root_page.set_title(_("Network"))
root_page.set_child(root_toolbar)   # was: .set_child(self)
self._nav.add(root_page)
# ...
self.setup_cleanup(self._nav)
return self._nav
```

Banner reference stays on `self._banner` so event handlers (`_on_nm_ready`, `_refresh_all`, etc.) can still call `self._banner.set_revealed(...)`.

**C4 — users D-Bus failure returns StatusPage directly**

```python
except GLib.Error:
    status = Adw.StatusPage()
    status.set_icon_name("dialog-error-symbolic")
    status.set_title(_("Could not connect to AccountsService"))
    status.set_description(_("User account settings are unavailable."))
    return status   # changed from: self.add(status); return self
```

Bare `Adw.StatusPage` is a legal `Gtk.Widget` child of the content stack. No wrapping needed.

**C5 — display no-displays returns StatusPage directly from build()**

Restructure `build()` to short-circuit when there are no displays:

```python
def build(self):
    displays = self._get_displays()
    if not displays:
        status = Adw.StatusPage()
        status.set_icon_name("video-display-symbolic")
        status.set_title(_("No displays detected"))
        status.set_description(
            _("Connect a display and reopen Settings."))
        return status

    # Normal path: four groups.
    self.add(self._build_scale_group())
    self.add(self._build_resolution_group(displays))  # pass displays in
    self.add(self._build_night_light_group())
    self.add(self._build_advanced_group())
    self.setup_cleanup(self)
    self.connect("unmap", lambda _w: self._cleanup_dialogs())
    return self
```

Adjust `_build_resolution_group` to accept `displays` as an argument rather than re-calling `_get_displays()`. The no-displays branch inside `_build_resolution_group` goes away.

**I1 — default_apps xdg-mime timeout**

```python
subprocess.run(
    ["xdg-mime", "default", ids[r.get_selected()], mt],
    check=False,
    timeout=5,   # added
)
```

Wrap with `try/except (subprocess.TimeoutExpired, OSError): pass` since the current call doesn't handle failures, just skipped with `check=False`. For consistency add the exception guards.

### Commit

Single atomic commit:

```
fix(settings): close Critical audit findings — banners, StatusPages, timeout

Addresses audit items C1-C5 and I1:

C1/C2/C3: bluetooth, language, network banners wrapped in AdwToolbarView
  as a top bar. Previously passed directly to AdwPreferencesPage.add(),
  which type-checks for AdwPreferencesGroup and silently no-ops
  otherwise. Banners now actually render when their condition fires.

C4: users D-Bus-failure returns Adw.StatusPage directly from build()
  rather than self.add(status). Fallback page now renders with the
  intended error messaging; previously rendered blank.

C5: display no-displays returns Adw.StatusPage directly from build()
  rather than group.add(status). The no-displays branch previously
  rendered a PreferencesGroup with a misplaced StatusPage child.

I1: default_apps xdg-mime subprocess now has timeout=5 plus exception
  handling. Previously a hanging xdg-mime could block the GTK main
  loop.

Audit: docs/superpowers/specs/2026-04-20-settings-adwaita-audit.md

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

### Wave 5A verification (controller, post-agent)

- [ ] `python3 -c "import ast; [ast.parse(open(f).read()) for f in ['files/usr/lib/adwaita-lite/settings/pages/{bluetooth,language,network,users,display,default_apps}.py'.replace('{', '').replace('}', '')]]; print('OK')"` — six files parse
- [ ] No remaining `self\.add\(banner\)` / `self\.add\(status\)` / `group\.add\(status\)` in those six files
- [ ] Spec reviewer dispatched on the commit (one Sonnet agent against the audit C1–C5 + I1 expectations)
- [ ] Quality reviewer dispatched on the commit
- [ ] Merge to main

---

## Wave 5B — Parallel fanout (7 agents)

All seven agents dispatched together. Dependency: Wave 5A must have landed on main so agents pull fresh state.

### Agent B1 — window.py architecture + CSS polish (Sonnet)

**Files:**
- `files/usr/lib/adwaita-lite/settings/window.py`
- `files/usr/lib/adwaita-lite/settings/css/style.css`

**AR1 — remove outer `Gtk.ScrolledWindow`**

Current structure (from window.py):
```python
self._stack = Gtk.Stack()
self._content_scroll = Gtk.ScrolledWindow()
self._content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
self._content_scroll.set_child(self._stack)
self._content_scroll.add_css_class("content-area")
# ...
content_toolbar.set_content(self._content_scroll)
```

Replacement: drop the ScrolledWindow entirely. Each page's `AdwPreferencesPage` scrolls internally; wrappers returning `AdwToolbarView` have their own layout; bare `Adw.StatusPage` is non-scrolling (and doesn't need to be, since it's the whole fallback viewport).

```python
self._stack = Gtk.Stack()
self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
self._stack.set_transition_duration(150)
self._stack.add_css_class("content-area")
# ...
content_toolbar.set_content(self._stack)
```

Remove the `self._content_scroll` attribute entirely. Remove `_show_page`'s scroll-reset:

```python
def _show_page(self, idx: int, label: str) -> None:
    self._stack.set_visible_child_name(label)
    self._content_page.set_title(self._page_labels[idx])
    # Previously: self._content_scroll.get_vadjustment().set_value(0)
    # Removed — each page's internal scroll persists per Phase 5 decision.
    self._split_view.set_show_content(True)
```

**AC1 — `.group-title` em-sizing**

```css
.group-title {
    font-size: 0.85em;     /* was: 13px */
    font-weight: bold;
    opacity: 0.8;
    margin-bottom: 6px;
    margin-start: 4px;
}
```

`em` scales with the container's computed font-size, which responds to Large Text accessibility setting.

**AC2 — sidebar row padding em-sizing**

```css
.sidebar row {
    padding: 0.75em 1em;    /* was: 12px 16px */
    margin: 2px 8px;
    border-radius: 8px;
}
.sidebar row {
    /* keep the rest */
}
.sidebar .category-label {
    font-size: 0.95em;       /* was: 14px */
}
```

**AC3 — accent-circle hit targets**

```css
.accent-circle {
    min-width: 32px;
    min-height: 32px;
    /* ... existing rules ... */
}
```

If the class already has min-sizes, leave them; otherwise add them at the top of the rule block.

### Agent B2 — toast-on-silent-failure sweep (Sonnet)

**Files (5):** `users.py`, `bluetooth.py`, `network.py`, `datetime.py`, `keyboard.py`

Audit I2. The `except GLib.Error: pass` and similar silent swallow sites:

**users.py** — `_on_name_activate`, `_on_autologin_set`:
```python
except GLib.Error as exc:
    self.store.show_toast(
        _("Could not save: {msg}").format(msg=exc.message), True)
```

**bluetooth.py** — in `_on_toggle`, wrap the BlueZHelper call so a D-Bus failure surfaces:
```python
try:
    self._bt.set_powered(row.get_active())
except Exception as exc:
    self.store.show_toast(
        _("Could not change Bluetooth state: {msg}").format(msg=str(exc)), True)
```

Only wrap if `set_powered` can raise; if `BlueZHelper` absorbs errors internally, add this at the helper layer instead (out of scope — flag to controller).

**network.py** — `_open_connection_editor` already has a toast. Other direct-NM calls via `self._nm.*` — leave as-is unless `NetworkManagerHelper` surfaces exceptions.

**datetime.py** — `_set_timezone` and `_set_ntp` already toast on failure. Verify each path and add toast to any silent branch.

**keyboard.py** — `_save_and_reconfigure` calls `self.store.apply()`. The store's reconciler toasts internally on apply failure. Verify by reading the store's `_on_apply_done` path; if the flow is already covered, no change needed. If there's a silent `_save_user_keybindings` failure (e.g., `OSError` from the tempfile+rename), toast it:
```python
try:
    _save_user_keybindings(save_data)
except OSError as exc:
    self.store.show_toast(
        _("Failed to save shortcuts: {msg}").format(msg=str(exc)), True)
    return
self.store.apply()
```

**Agent B2 is allowed to skip any site that is already instrumented.** Report the final list of sites touched in DONE.

### Agent C1 — mouse_touchpad adaptive (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py`

Three `Gtk.Scale` widgets are each set to `set_size_request(200, -1)` as `AdwActionRow` suffixes. At 360px viewport, the 200px suffix dominates the row and leaves too little room for title/subtitle under translation + Large Text.

**Audit recommendation (A1):** two options — (1) drop the size_request and let the scale flex, (2) replace with `Adw.SpinRow`. Opus agent picks per-row based on UX.

Guidance for this page:
- `touchpad_pointer_speed` (-1.0..1.0 step 0.1) — continuous values, slider feel is natural. Drop the 200 px min; set a sensible natural width (e.g. `set_size_request(120, -1)`) so it doesn't collapse to unusable.
- `touchpad_scroll_speed` (1..10 step 1) — integer, 10 steps. Consider `Adw.SpinRow` instead. SpinRow rows adapt natively; value is typed as a discrete number.
- `mouse_pointer_speed` (-1.0..1.0 step 0.1) — same as touchpad_pointer_speed.

Agent may argue for or against SpinRow for scroll_speed; recommend SpinRow by default.

If choosing SpinRow:
```python
scroll_row = Adw.SpinRow.new_with_range(1.0, 10.0, 1.0)
scroll_row.set_title(_("Scroll speed"))
scroll_row.set_value(float(self.store.get("touchpad_scroll_speed", 5)))
scroll_row.connect("notify::value", lambda r, _p:
    self.store.save_debounced("touchpad_scroll_speed", int(r.get_value())))
touchpad_group.add(scroll_row)
```

If keeping Scale with relaxed sizing:
```python
scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
scale.set_size_request(120, -1)   # down from 200
scale.set_draw_value(False)
scale.set_valign(Gtk.Align.CENTER)
scale.set_hexpand(True)   # let it take available suffix width
# ...
row.add_suffix(scale)
```

**Preserve:**
- All 7 store keys and their save_and_apply/save_debounced cadence
- Tap-to-click SwitchRow with its "Content moves with your fingers" subtitle on natural-scroll
- Accel profile ComboRow (adaptive)

**Verify:** `grep -c 'set_size_request(200' file` → 0 after agent's change (if picking relaxed Scale, verify new size is documented).

### Agent C2 — sound adaptive (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/sound.py`

Similar to mouse_touchpad: two 200px volume Scales. Volume is 0..100 integer — strong candidate for `Adw.SpinRow` with a % suffix format, OR a relaxed `Gtk.Scale` that flexes.

Default recommendation: keep the `Gtk.Scale` but drop `set_size_request(200, -1)` → `set_size_request(150, -1)` (still ergonomic, leaves more room). Keep `set_draw_value(True)` + the `{v:.0f}%` format (users want to see the percentage). Keep all `_refresh`, `_updating`, and pactl wiring.

Also (audit I3): add a one-line clarifying comment above `_refresh` explaining that the method is main-loop-only and the `_updating` guard protects handler reentry, not thread concurrency.

### Agent C3 — display adaptive (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/display.py`

One 200px temperature `Gtk.Scale` (3500..6500 step 100). Drop to `set_size_request(150, -1)`. The value-display (`{v:.0f}K`) is important for users setting a specific color temp — keep `set_draw_value(True)`.

Side opportunity: the night-light group currently has `AdwSwitchRow` + `AdwActionRow-with-Scale` + `AdwComboRow(schedule)` + `AdwExpanderRow(custom schedule)`. When night light is OFF, the temperature / schedule / custom-schedule rows are visible but irrelevant. Opus agent: consider wrapping the non-enable rows in an `AdwExpanderRow("Night Light")` with `set_show_enable_switch(True)` — flips the whole group section OFF at once. Agent may push back if this feels worse than the current always-visible layout.

Don't touch the revert-dialog logic (Phase 3 work).

### Agent C4 — appearance adaptive (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/appearance.py`

**A2 — accent picker HBox → FlowBox**

```python
accent_flow = Gtk.FlowBox()
accent_flow.set_selection_mode(Gtk.SelectionMode.NONE)
accent_flow.set_max_children_per_line(9)
accent_flow.set_min_children_per_line(3)
accent_flow.set_homogeneous(True)
accent_flow.set_column_spacing(8)
accent_flow.set_row_spacing(8)
# ... create 9 toggle buttons with .accent-circle .accent-<name> ...
# accent_flow.append(btn)
accent_row = Adw.ActionRow()
accent_row.set_activatable(False)
accent_row.add_suffix(accent_flow)
```

At narrow widths the FlowBox wraps to 3 per row × 3 rows, still fits comfortably. At wide widths all 9 fit horizontally.

**A3 — wallpaper grid narrow-width**

Current: `flow.set_min_children_per_line(2)` + `TILE_W = 160`. At 360px viewport the 2 tiles fit tightly. Agent considers:
- Lower `min_children_per_line` to 1 — at very narrow widths, one tile per line, easier to see.
- Reduce `TILE_W` to 140 under a breakpoint — unfortunately we chose not to add secondary breakpoints. Skip.

Default recommendation: `set_min_children_per_line(1)`. Keeps the wallpaper picker functional on phone-narrow viewports.

Preserve all wallpaper methods (`_populate_wallpapers`, `_make_wallpaper_tile`, etc.) and all 4+ `save_and_apply` sites.

### Agent C5 — panel adaptive (Opus, biggest single piece)

**File:** `files/usr/lib/adwaita-lite/settings/pages/panel.py`

**A4 — module layout editor vertical collapse**

Current: 3-column `Gtk.Box` (horizontal) with per-column `Gtk.ListBox`es, inside a horizontal `Gtk.ScrolledWindow`. Each module has arrow buttons to move between sections and reorder.

Proposed replacement: **single vertical list with section headers**. Each module is a row; each row has the same arrow buttons as today. Section headers (`Start / Center / End` or edge-aware labels) are rendered as Adwaita `.group-title`-styled labels interleaved in the list.

```python
def _build_module_layout(self):
    self._layout_data = self._load_layout()
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    outer.set_hexpand(True)
    self._section_boxes = {}
    self._section_labels = {}

    edge = self.store.get("edge", "bottom")
    labels = HORIZONTAL_LABELS if edge in ("top", "bottom") else VERTICAL_LABELS

    for section in SECTION_ORDER:
        header = Gtk.Label(label=labels[section], xalign=0)
        header.add_css_class("group-title")
        header.set_margin_top(4)
        self._section_labels[section] = header
        outer.append(header)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        self._section_boxes[section] = listbox
        outer.append(listbox)

    self._refresh_module_lists()
    return outer
```

Now there's no horizontal scroll, no 3-column HBox. Adapts to any width.

But wait — the `.boxed-list` CSS class was deleted in Phase 4. The agent needs to re-add a small bespoke class (e.g. `.panel-section-list`) with the same styling the old boxed-list had, OR rely on `AdwPreferencesGroup` — which means each of the three section listboxes becomes an `AdwPreferencesGroup` with the section header as the group title.

Cleaner path: **three `AdwPreferencesGroup`s, one per section**, instead of a Gtk.Box with headers. Section title = edge-aware label. Module rows inside each group. This naturally gets the boxed-list styling and group-title rendering that the user expects.

```python
def _build_module_layout_groups(self):
    edge = self.store.get("edge", "bottom")
    labels = HORIZONTAL_LABELS if edge in ("top", "bottom") else VERTICAL_LABELS
    self._section_groups = {}
    for section in SECTION_ORDER:
        group = Adw.PreferencesGroup()
        group.set_title(labels[section])
        self._section_groups[section] = group
    self._refresh_module_lists()
    return list(self._section_groups.values())

def _refresh_module_lists(self):
    for section, group in self._section_groups.items():
        # Clear existing rows (collect first, then remove)
        rows = []
        child = group.get_first_child()
        # ... walk and collect Adw.ActionRow children ...
        # Actually easier: keep track of rows via self._section_rows[section]
        for row in self._section_rows.get(section, []):
            group.remove(row)
        self._section_rows[section] = []
        for mod_key in self._layout_data.get(section, []):
            row = self._build_module_row(mod_key, section)
            group.add(row)
            self._section_rows[section].append(row)
```

And `build()` adds all three groups as top-level `self.add(group)` calls. The page gets three boxed-list groups stacked vertically, each with arrow-button rows.

**Module rows** become `Adw.ActionRow`s with title = module-display-name and the arrow buttons added via `add_suffix(button)` × (2–4 depending on position). Arrow semantics unchanged from pre-migration.

Update `_update_section_labels` to call `group.set_title(labels[section])` on edge change. Update `_on_edge_changed` to trigger both label and order refresh.

**AC1 on this page (if `.group-title` class is still used anywhere in panel.py after the rework):** confirm the CSS has been moved to em-sizing by Agent B1 (`.group-title { font-size: 0.85em; ... }`). If the panel uses any other fixed-px styling via the bespoke approach, switch to em.

**Preserve:**
- All store keys: `edge`, `density`, `panel_twilight`, `layout`, `pinned`.
- All constants unchanged.
- `_load_layout`, `_reorder_module`, `_move_module`, `_reset_layout` logic unchanged.
- `_add_app_from_info` icon-extraction + `%u` strip.
- Nav-push for add-pinned dialog.
- Pinned Apps group with `+` header-suffix.

**Verification:** no `Gtk.ScrolledWindow` usage in panel.py after the change. Each section is an `AdwPreferencesGroup`. Rows are `AdwActionRow`.

---

## Wave 5B validation

After all 7 agents report DONE:

- [ ] Spec reviewer on each commit (7 parallel Sonnet reviewers) — verify per-agent task sections match commit
- [ ] Quality reviewer on each commit (7 parallel Sonnet reviewers) — verify widget-tree type contracts hold
- [ ] Fix loops until both reviews pass per commit
- [ ] Push batch
- [ ] Hardware smoke test:

**Focus on these scenarios:**
1. **No Bluetooth adapter** — toggle disabled, banner visible above the group.
2. **No language-change side effect** — banner always visible above Language & Region groups.
3. **No network adapter / airplane mode** — banner above Network groups.
4. **D-Bus failure on Users** — simulate with `systemctl stop accounts-daemon` then open Users; verify StatusPage renders.
5. **No displays** — detach external displays; open Display; verify StatusPage renders.
6. **Narrow-width rendering**: resize window below 700sp; verify sidebar collapses to push-nav. Resize further to 500sp; verify pages still render without clipping. Resize to minimum (360×300); verify titles/subtitles don't overlap suffixes.
7. **Large Text 150% / 200%** accessibility: open Settings → Accessibility (if there's a Large Text toggle) or via system accessibility panel; verify every page scales labels; verify .group-title in panel scales with the rest; verify sidebar rows have enough padding at 200%.
8. **Scroll persistence**: on Display or Keyboard (long scroll pages), scroll down, switch to another page, switch back; verify scroll position is preserved (new behaviour per AR1).
9. **Panel module editor** at narrow width: open Panel; verify three sections render as stacked `AdwPreferencesGroup`s (not horizontally scrolling HBox); verify arrow buttons still move modules between sections.

---

## Completion criteria

- All 5 Critical bugs fixed (C1–C5).
- All Important-bucket audit items addressed or explicitly deferred with rationale (I1 fixed; I2 swept; I3 commented; I4 acceptable).
- All Adaptive-bucket items addressed or deferred (A1 × 6 sites adapted; A2 accent FlowBox; A3 wallpaper narrow; A4 panel module editor; A5 explicitly skipped per "match GNOME HIG" decision; A6 RTL deferred as post-ship).
- All Accessibility items addressed (AC1 em-sizing; AC2 sidebar padding; AC3 accent-circle hit target).
- Architecture AR1 resolved (outer ScrolledWindow removed); AR2 deferred as documentation/tracking.
- Hardware smoke test passes all 9 scenarios.
- Settings app renders correctly at 683×384 (Chromebook at 2.0× scale) and at 546×307 (2.5×).
- No Gtk-CRITICAL warnings in `journalctl --user -b | grep adwaita-lite-settings` after page rotation.

---

## Post-Phase-5 backlog (not this phase)

Items deliberately punted:

- **A5** (secondary breakpoint below 700sp): explicitly off-the-table per "match GNOME HIG" decision.
- **A6** (RTL pass): low priority, defer until a concrete RTL deployment is on the roadmap.
- **I4** (about thread + GLib.idle_add lifecycle): not a bug, cosmetic clean-up.
- **AR2** (consistent toast routing): tracking doc only, no code change.
- **AC3 hit target for wallpaper tiles**: current 160×100 is fine on desktop; defer touch-target audit for when a touchscreen Chromebook is in-scope.
