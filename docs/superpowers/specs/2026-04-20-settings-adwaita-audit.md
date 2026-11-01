# Settings App (post-Adwaita migration) — Comprehensive Audit

**Date:** 2026-04-20
**Scope:** Every file in `files/usr/lib/adwaita-lite/settings/`, post-Phase-4. Focus on **adaptive layout at low resolution + high scale + Large Text**, plus runtime correctness.

---

## Executive summary

Phases 0–4 of the migration moved 16 pages onto `Adw.PreferencesPage` and eliminated every pre-migration `Gtk.Window` modal. The architecture is sound and matches the GNOME Settings pattern. However, this audit found:

- **5 Critical bugs** where widgets are silently dropped by libadwaita's type-checked `add()` methods, including the D-Bus failure fallback on `users` and the banners on `network` / `bluetooth` / `language`. None would be caught by a plain app launch; they only surface when the specific edge case triggers (missing adapter, no language-change-pending, D-Bus unavailable). **Every spec + quality review missed these because none of the reviews actually verified runtime rendering of the banner/status-page paths.**
- **4 Important correctness issues**, primarily silent D-Bus error swallows that were pre-existing but worth flagging.
- **6 Adaptive-layout concerns** — fixed-pixel suffix widgets (5× `Gtk.Scale` at 200px + wallpaper 160×100 tiles + accent-picker HBox), no secondary breakpoint below the 700sp collapse, and one truly layout-hostile widget (panel's 3-column module editor).
- **3 Accessibility / Large Text concerns** around touch targets and fixed font sizes that bypass the accessibility scaling.
- **2 Architectural hygiene items** around double-scrolling and toast routing.

Overall posture: app will run and look fine at 900×600 with default scale + default text. Adaptive compliance degrades gradually below ~500 logical pixels or above ~150% Large Text. Ship-blocking bugs are the 5 Critical items.

---

## Critical: libadwaita type-checked `add()` silently dropping children

libadwaita's preference containers have strict type assertions at runtime:

- `adw_preferences_page_add(page, group)` → `g_return_if_fail (ADW_IS_PREFERENCES_GROUP (group))`. Non-group widgets emit a `Gtk-CRITICAL` to stderr and **do not render**.
- `adw_preferences_group_add(group, row)` — accepts any `GtkWidget` but only renders `AdwPreferencesRow` / `GtkListBoxRow` descendants inside the boxed list. Non-rows get shunted to an internal box and render visually detached from the group's styling.

Our pages hit both.

### C1. `bluetooth.py:48` — banner silently dropped

```python
banner = Adw.Banner.new(_("No Bluetooth adapter found"))
banner.set_revealed(not self._bt.available)
self.add(banner)   # ← Adw.Banner is not an AdwPreferencesGroup
```

Effect: on a device with no Bluetooth adapter, the user sees the Bluetooth toggle row (disabled) but no banner explaining why. The page looks broken rather than offline.

**Fix:** Banners belong outside the PreferencesPage. Wrap the whole page in an `Adw.ToolbarView` with the banner as a top bar, and return that toolbar view instead of `self` from `build()`:

```python
def build(self):
    # populate self (the PreferencesPage) with groups as usual...
    self.add(toggle_group)
    # ...

    # Wrap in a ToolbarView so the banner sits above the page.
    wrapper = Adw.ToolbarView()
    self._banner = Adw.Banner.new(_("No Bluetooth adapter found"))
    self._banner.set_revealed(not self._bt.available)
    wrapper.add_top_bar(self._banner)
    wrapper.set_content(self)
    return wrapper
```

### C2. `language.py:30` — banner silently dropped

Same pattern. The "Changes take effect after logging out" advisory never shows. Users may not know a logout is required after changing language/format.

**Fix:** same ToolbarView wrap.

### C3. `network.py:71` — banner silently dropped

Same pattern, but with an extra complication: the page already returns `self._nav` (an `Adw.NavigationView`). The banner needs to live inside the root `AdwNavigationPage`'s toolbar, not added to `self`:

```python
def build(self):
    # ... populate self with groups ...

    self._banner = Adw.Banner.new(_("No network adapter"))
    self._banner.set_revealed(not self._nm.ready)

    # Root navigation page with a ToolbarView holding banner + page.
    root_toolbar = Adw.ToolbarView()
    root_toolbar.add_top_bar(self._banner)
    root_toolbar.set_content(self)

    self._nav = Adw.NavigationView()
    root_page = Adw.NavigationPage()
    root_page.set_title(_("Network"))
    root_page.set_child(root_toolbar)
    self._nav.add(root_page)
    # ...
    return self._nav
```

### C4. `users.py:85` — D-Bus-failure StatusPage silently dropped

```python
except GLib.Error:
    status = Adw.StatusPage()
    status.set_icon_name("dialog-error-symbolic")
    status.set_title(_("Could not connect to AccountsService"))
    status.set_description(_("User account settings are unavailable."))
    self.add(status)    # ← StatusPage is not a group
    return self
```

Effect: when `accounts-daemon` is unavailable (rare but possible — a broken upgrade, a misconfigured container), the Users page renders **blank**. The user has no feedback about why there are no account settings.

**Fix:** Return the StatusPage as the page's child directly — page classes in `window.py` are put into a `Gtk.Stack`, which accepts any widget. Shortest fix:

```python
except GLib.Error:
    status = Adw.StatusPage()
    # ...
    return status   # not `self` — a bare AdwPreferencesPage can't hold a StatusPage
```

`window.py`'s `_ensure_page_built` treats the return value as a stack child. Returning `Adw.StatusPage` directly is legal.

Trade-off: the stack's `add_named` won't be the same type for all pages (usually PreferencesPage, here StatusPage in the error path). No functional issue; minor inconsistency.

### C5. `display.py:105` — StatusPage wrapped in PreferencesGroup, non-row child

```python
if not displays:
    group = Adw.PreferencesGroup()
    status = Adw.StatusPage()
    status.set_icon_name("video-display-symbolic")
    status.set_title(_("No displays detected"))
    group.add(status)   # ← StatusPage is not an AdwPreferencesRow
    return group
```

This is the "fix" from commit `b69e131` that moved the bug from `PreferencesPage.add(StatusPage)` down to `PreferencesGroup.add(StatusPage)`. `AdwPreferencesGroup.add()` accepts non-rows but places them in the "title row" slot or as a trailing widget, not inside the boxed list. Rendering is inconsistent across libadwaita versions and looks non-native.

**Fix:** Same pattern as C4 — return `Adw.StatusPage` directly from `build()` when there are no displays. But since `build()` already `self.add(group)`s multiple groups and returns self, the clean fix is to pre-check in `build()` and branch the top-level build path:

```python
def build(self):
    displays = self._get_displays()
    if not displays:
        # Whole-page empty state.
        status = Adw.StatusPage()
        status.set_icon_name("video-display-symbolic")
        status.set_title(_("No displays detected"))
        status.set_description(_("Connect a display and reopen Settings."))
        return status

    # Normal path: four groups.
    self.add(self._build_scale_group())
    self.add(self._build_resolution_group())
    self.add(self._build_night_light_group())
    self.add(self._build_advanced_group())
    self.setup_cleanup(self)
    return self
```

Alternatively, keep the normal groups and render the empty-state inline as an `AdwActionRow` with the `.property` class (title = "No displays detected", no subtitle) — less eye-catching but renders correctly within the group layout.

---

## Important: correctness

### I1. `default_apps.py` `xdg-mime` subprocess has no timeout

```python
subprocess.run(["xdg-mime", "default", ids[r.get_selected()], mt],
               check=False)   # ← no timeout
```

If `xdg-mime` hangs (stuck on a D-Bus call to xdg-desktop-portal, for instance), this blocks the GTK main loop indefinitely. Add `timeout=5`.

### I2. Silent `except GLib.Error: pass` on D-Bus writes

Pages affected: `users.py` (3 sites — name, auto-login, password), `bluetooth.py` (set_powered errors are eaten by `_updating` logic). Users who hit a D-Bus permission error see no feedback — the switch appears to toggle successfully but the backend refused.

Not a regression (was the same before the migration). Worth adding a toast on failure:

```python
except GLib.Error as exc:
    self.store.show_toast(
        _("Could not save: {msg}").format(msg=exc.message), True)
```

### I3. `_refresh` + event-bus subscription race (`sound.py`)

`_refresh` is called on `audio-changed` events. The `_updating` guard on handlers protects the user-interaction handlers, but nothing prevents two concurrent `_refresh` calls from firing interleaved `pactl` queries and clobbering each other. In practice `_refresh` is synchronous and runs on the main loop, so interleaving can't happen. Not a real bug, but the current code reads as if it were unsafe. Add a one-line comment noting this.

### I4. `about.py` `_check_updates` uses `threading.Thread` with no cancellation

If the user leaves the About page (or closes the window) while the 60s `uupd update-check` subprocess is running, the thread finishes and calls `GLib.idle_add(self._update_label.set_subtitle, …)`. If the ActionRow was destroyed, this is a no-op — GLib handles dead object references gracefully. Not a bug, but worth noting for future review that the idle-add references aren't checked for widget validity.

---

## Adaptive layout: low-resolution + high-scale concerns

Window chrome is sound: the 700sp `AdwBreakpoint` on `AdwNavigationSplitView` correctly collapses the sidebar into push-nav at narrow widths. Below 700sp, pages have to render their content into the content column's width — which can be as low as 360 logical px (`self.set_size_request(360, 300)`). The following pages have widgets whose natural size exceeds comfortable rendering at those widths.

### A1. 5× fixed-width `Gtk.Scale` suffix (200 px minimum)

Files:
- `display.py:164` — night light temperature scale
- `mouse_touchpad.py:63,77,104` — touchpad pointer, touchpad scroll, mouse pointer
- `sound.py:67,109` — output volume, input volume

Each `AdwActionRow` hosting a 200px-wide Gtk.Scale in its suffix leaves approximately **160 logical px** for title+subtitle at a 360-wide window. This fits the English labels but:

- German / French translations are longer. "Lautstärke" fits; "Ausgabegerät" is close to the edge.
- At Large Text 150%, the same 360-wide window loses ~40px of title room. At 200% Large Text, titles truncate.

**Options for fix, in increasing effort:**
1. Reduce scale size_request to `150` or drop the explicit request and let it flex. (Lowest effort; scales may become ergonomically small.)
2. Replace the Scale with `Adw.SpinRow` for the integer-valued ones (volume 0–100, temperature steps of 100). SpinRow is row-native and adapts. Night-light temperature is naturally a slider because it's continuous; volume/speed could plausibly be either.
3. Under a secondary breakpoint (e.g. `max-width: 450sp`), move the Scale OUT of the row's suffix and into its own row underneath the title. Requires `AdwPreferencesPage` breakpoint setters or manual hex-switching in a `notify::default-width` handler.

### A2. `appearance.py` accent picker — 9 circles × ~32 px = ~320 px minimum HBox

```python
accent_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
# 9 iterations of: toggle button with .accent-circle + .accent-<name>
accent_row.add_suffix(accent_box)
```

9 × 32 + 8 × 8 = 352 px. Plus row padding. On a 360-px window this overflows horizontally into the row's clip area.

**Fix:** replace `Gtk.Box` with `Gtk.FlowBox` — 9 children flow onto two rows when space tightens:

```python
accent_flow = Gtk.FlowBox()
accent_flow.set_selection_mode(Gtk.SelectionMode.NONE)
accent_flow.set_max_children_per_line(9)
accent_flow.set_min_children_per_line(3)
accent_flow.set_homogeneous(True)
accent_flow.set_column_spacing(8)
accent_flow.set_row_spacing(8)
# ... append to flow instead of accent_box ...
accent_row.add_suffix(accent_flow)
```

FlowBox adapts cleanly. The accent_row won't force horizontal overflow.

### A3. `appearance.py` wallpaper grid — 160 × 100 tiles, min 2/line

Grid min width: 2 × 160 + 12 gap + 2 × 8 row padding = 348 px. On a 360-wide window the tiles fit but the row's title slot has **zero room**. Fine since the row has no title. But text for custom-wallpaper-remove × overlay on the tile (if overlay is shown) may not be readable at high scale.

**Minor fix**: lower `TILE_W` to 120 at narrow widths under a breakpoint, or set the FlowBox's min children per line to 1 so a very narrow window can show one tile at a time.

### A4. `panel.py` module layout editor — 3-column fixed HBox inside horizontal-scroll `ScrolledWindow`

```python
inner = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
# three section_box columns, each with listbox of module rows
scrolled = Gtk.ScrolledWindow()
scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
scrolled.set_child(inner)
return scrolled  # placed in row.add_suffix
```

This is the single most layout-hostile widget in the app. On a narrow window, the user has to horizontally scroll to see all three sections, then scroll back to move a module across. Functional; not pretty.

**Proper fix:** collapse the 3-column layout into a single-column list-with-section-headers under a breakpoint. Each module row still has its move-between-section buttons; the "section headers" become dividers. This is substantial work — flag as post-ship polish.

### A5. No secondary breakpoint below 700sp

`window.py` defines only `max-width: 700sp` as the collapse threshold. Below that, the sidebar is drawered and the content column takes the full window width. But there's no further simplification for, e.g., 360-wide or "Large Text + narrow viewport" edge cases.

**Recommendation:** add a second breakpoint at `max-width: 450sp` that sets per-page "compact" flags. Pages that can adapt (e.g. the mouse_touchpad scales) register for the flag and switch layouts. Meaningful effort; defer.

### A6. No RTL testing

Every page uses `xalign=0` on the occasional raw `Gtk.Label` (panel.py's module layout section headers, mouse_touchpad hypothetical subtitle labels). In RTL locales these render left-aligned where they should right-align. `Adw.*Row` handles RTL natively; raw Gtk.Labels we add do not. Low-priority (app is English-first today) but worth noting for future i18n.

---

## Accessibility / Large Text

### AC1. `.group-title` CSS uses fixed `font-size: 13px`

```css
.group-title {
    font-size: 13px;
    font-weight: bold;
    opacity: 0.8;
    margin-bottom: 6px;
    margin-start: 4px;
}
```

This class is used by `panel.py`'s custom module-layout section headers. Fixed-px font size doesn't scale with the user's text-size accessibility setting. At 200% Large Text, every other label is bigger except these.

**Fix:** change to `font-size: 0.85em` (relative to the container's computed font size, which Adwaita scales with accessibility).

### AC2. Sidebar row padding

```css
.sidebar row {
    padding: 12px 16px;
    ...
}
```

Fixed-px padding doesn't scale. On high-DPI displays with Large Text, sidebar rows may feel cramped relative to their labels. Minor. Consider `padding: 0.75em 1em` for scaling, or accept the fixed-px look.

### AC3. Hit target sizes for the accent picker and wallpaper tiles

- Accent circles: `.accent-circle` is a `Gtk.ToggleButton`. Its natural size is tiny (icon-like). Touch target on a Chromebook screen at default DPI might be ~32 × 32 px — below the 44 × 44 recommended minimum.
- Wallpaper tiles: 160 × 100 is ergonomically fine on a desktop, but on a high-scale small-screen device the touch target gets small too (not in logical px but in physical). Unlikely to matter.

**Recommendation:** ensure accent-circle has `min-width: 32px; min-height: 32px` or a larger minimum and double-check the CSS for it.

---

## Architecture / hygiene

### AR1. Double-scroll between `window.py` outer `Gtk.ScrolledWindow` and each `AdwPreferencesPage`'s internal scroll

`window.py` wraps `self._stack` (which holds each page) in a `Gtk.ScrolledWindow` so `_show_page` can reset scroll via `adj.set_value(0)`. But every `AdwPreferencesPage` already has its own internal scrolled window. This creates nested scrolling:

- When the inner AdwPreferencesPage's content fits the viewport, the outer scroll takes over (harmless).
- When both have overflow, scroll wheel events may hit the inner first; when inner reaches top/bottom, outer starts scrolling. Behaviour is non-deterministic depending on pointer position and which widget claims the scroll event.

**Fix:** remove the outer `Gtk.ScrolledWindow`. To preserve the scroll-reset on page change, use `Adw.PreferencesPage`'s internal scroll APIs — it doesn't expose a `set_value(0)` for its internal scrolled window, but we can walk the widget hierarchy (`page.get_first_child()` to find the internal box, then its parent scrolled) and reset that. Or accept scroll-position persistence per page (a UX win; pages remember where the user scrolled).

Recommendation: remove the outer scroll, accept scroll-position persistence. Net simplification.

### AR2. Toast routes only through `store.save_and_apply`; direct D-Bus actions don't fire toast callbacks automatically

The settings store fires "Settings applied" / "Failed to apply" toasts via the apply-settings reconciler. Pages that bypass the store (users, bluetooth, network, datetime's timedatectl calls, keyboard's localectl/labwc reconfigure) don't get automatic toasts — they must call `self.store.show_toast(...)` manually. Today most pages do this on failure paths, but not consistently on success.

**Recommendation:** audit each direct D-Bus / subprocess action for success-toast parity with the store's "Settings applied" behaviour.

---

## Per-page summary

| Page | Inheritance | Nav push | Critical | Important | Adaptive |
|---|---|---|---|---|---|
| about | ✅ | ✅ | — | — | — |
| accessibility | ✅ | — | — | — | — |
| appearance | ✅ | — | — | — | **A2** (accent picker), A3 (wallpaper) |
| bluetooth | ✅ | — | **C1** | I2 (set_powered silent) | — |
| datetime | ✅ | — | — | — | — |
| default_apps | ✅ | — | — | **I1** (no xdg-mime timeout) | — |
| display | ✅ | — | **C5** | — | **A1** (temp slider) |
| keyboard | ✅ | ✅ | — | — | — |
| language | ✅ | — | **C2** | — | — |
| mouse_touchpad | ✅ | — | — | — | **A1** (3× speed sliders) |
| network | ✅ | ✅ | **C3** | — | — |
| panel | ✅ | ✅ | — | — | **A4** (module editor) |
| power_lock | ✅ | — | — | — | — |
| sound | ✅ | — | — | **I3** (refresh comment only) | **A1** (2× volume sliders) |
| users | ✅ | ✅ | **C4** | I2 (3× silent DBus) | — |

---

## Recommended fix priority

**Ship-blocking (fix before deploy):**
1. C1, C2, C3 — the 3 banner bugs. Without these the user never sees adapter-absent / change-takes-effect-after-logout warnings. Concrete UX regression.
2. C4 — users page blank on D-Bus failure. Rare but severe when it hits.
3. C5 — display "no displays" fallback. Currently partially broken visually; affects users who disconnect an external display.

**High-value polish (fix soon):**
- A1 — reduce Scale size_request from 200 to 150 across the 5 affected rows. Single-line change per site, measurable narrow-width improvement.
- A2 — convert accent_box to Gtk.FlowBox. Ten lines. Significant narrow-width win.
- I1 — add `timeout=5` to xdg-mime call in default_apps.

**Future (post-deploy):**
- AR1 — remove outer ScrolledWindow; accept scroll-position persistence.
- AC1 — change `.group-title` to `em`-based sizing.
- A4 — panel module editor vertical-collapse under a breakpoint (substantial work).
- A5 — secondary breakpoint at 450sp for further simplification.
- I2 — toast-on-D-Bus-failure for users / bluetooth / datetime / keyboard direct calls.
- RTL i18n pass (A6).

**Low-priority:**
- A6, AC2, AC3 — hit targets, RTL, fixed padding. Nice-to-have.

---

## How the reviews missed the Critical bugs

Wave-2 spec + quality reviews for `bluetooth`, `language`, `network`, `users`, and the `display` fix for C5 all passed. They missed the bugs because:

1. **Reviewers verified *code pattern*, not *runtime rendering*.** The pattern "banner added to page" is a natural-language description that the reviewer matched against the code. Whether `page.add(banner)` is semantically legal was taken on faith, not verified against libadwaita's API contract.
2. **No integration test harness.** Spec reviewers can't run the app; they grep. Runtime assertions (`g_return_if_fail`) are invisible at that layer.
3. **The audit prompts didn't call out type-strictness on `.add()`.** The reference pack noted "AdwPreferencesPage rejects non-groups" as an anti-pattern, but reviewers treated that as prescriptive for the implementer, not as a post-hoc verification step.

**Structural fix for future reviews:** add a grep-based type check in the spec reviewer's script — `grep -n 'self\.add(' | …` and cross-reference each argument's type. Or, more robustly, add a `python3 -c "from ... import SomePage; SomePage._probe_widget_tree()"` runtime smoke step to each page's verification that exercises at least `build()` without a compositor.

---

## Next steps

1. **Immediate**: fix C1–C5 before the next hardware smoke test. Five targeted patches, each scoped to one file.
2. **Short-term**: address A1 (Scale widths), A2 (accent FlowBox), I1 (xdg-mime timeout) — low-risk wins.
3. **Medium-term**: AR1 double-scroll cleanup, AC1 em-sized group-title, A4 module-editor responsive, A5 secondary breakpoint, I2 consistent toasts.
4. **Long-term**: RTL pass, formal accessibility audit with Large Text at 200%, touch-target validation.
