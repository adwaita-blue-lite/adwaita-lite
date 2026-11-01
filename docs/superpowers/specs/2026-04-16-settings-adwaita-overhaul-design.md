# Settings App Adwaita Overhaul — Design Spec

## Goal

Make the settings app visually indistinguishable from a GNOME/Adwaita app
at a glance, using only GTK 4 (no libadwaita). Add minimize/maximize/close
buttons (Windows-style, right side) to all GTK CSD apps system-wide.

## Reference

GNOME Settings (gnome-control-center) — sidebar navigation, boxed-list
groups on a recessed background, headerbar with search toggle.

---

## A. HeaderBar

**File:** `settings/window.py`

Add a `Gtk.HeaderBar` as the window's titlebar:

- Title label: "Settings" (centered by default in Adwaita)
- Search toggle button on the right (magnifying glass icon `system-search-symbolic`)
- Window buttons rendered by GTK CSD: `minimize,maximize,close` on the right
- The headerbar inherits `@headerbar_bg_color` from Adwaita automatically
- Remove the current `Gtk.SearchBar` from the sidebar; the search entry
  moves into the headerbar area (a `Gtk.SearchBar` attached below the
  headerbar, toggled by the header button — same pattern as GNOME Settings)

## B. Background Color Hierarchy

**File:** `settings/css/style.css`

GNOME Settings uses a 3-tier color system that gives visual depth:

| Element | Adwaita variable | Light value | Dark value |
|---------|-----------------|-------------|------------|
| Sidebar | `@headerbar_bg_color` | `#f0f0f0` | `#303030` |
| Content area | `@window_bg_color` | `#fafafa` | `#242424` |
| Group cards | `@card_bg_color` | `#ffffff` | `#383838` |

Currently the content area has no explicit background (falls through to
whatever GTK gives it) and settings rows float without a card container.

**Changes:**
- Content scrolled area: explicit `background-color: @window_bg_color`
- Sidebar: keep `@headerbar_bg_color` + add 1px right border `alpha(@borders, 0.3)`
- Group cards get `@card_bg_color` (see section C)

## C. Boxed-List Group Pattern

**Files:** `settings/base.py`, `settings/css/style.css`

This is the biggest structural change. Every settings group currently looks like:

```
group_label("Position")
toggle_cards(...)
group_label("Density")
toggle_cards(...)
```

It will become:

```
make_group("Position", [toggle_cards(...)])
make_group("Density", [toggle_cards(...)])
```

### New `make_group()` helper in `BasePage`

Returns a `Gtk.Box(VERTICAL)` containing:
1. **Title label** — above the card, styled with `group-title` class
   (13px, `font-weight: bold`, `alpha(@theme_fg_color, 0.8)`, 4px bottom margin)
2. **Card container** — a `Gtk.Box(VERTICAL)` with CSS class `boxed-list`:
   - `background: @card_bg_color`
   - `border-radius: 12px`
   - `border: 1px solid alpha(@borders, 0.3)`
   - Children separated by 1px `alpha(@borders, 0.15)` horizontal lines (CSS
     `border-top` on `.boxed-list > *:not(:first-child)`)
   - Internal padding: each child gets `12px 16px` padding

When a group has a single widget that isn't a setting-row (e.g. toggle-cards,
FlowBox for wallpapers), it's placed directly inside the card.

### Updated `make_setting_row()`

Keep the existing layout (left label+subtitle, right control) but ensure it
works inside a boxed-list card: remove the current standalone `padding: 8px 0`
and let the card's internal padding handle it. `min-height: 48px` stays.

## D. Content Width Clamping

**File:** `settings/base.py` (in `make_page_box()`)

GNOME Settings clamps content to ~600px so it doesn't stretch across wide
screens. Achieved via CSS on the page box:

```css
.content-page {
    max-width: 640px;
    margin-left: auto;
    margin-right: auto;
}
```

The existing `make_page_box()` already sets 40px horizontal margins. Replace
those with the CSS class approach: the 40px margin becomes a minimum (via
`padding`) and the `max-width` caps the content at 640px.

## E. Sidebar Refinement

**File:** `settings/css/style.css`

Minor tweaks to bring the sidebar closer to GNOME Settings:

- Add `border-right: 1px solid alpha(@borders, 0.3)` to the sidebar container
  (separates sidebar from content area visually)
- Icon size stays at 16px, opacity stays at 0.8
- Row padding/radius/spacing remain as-is (already close to GNOME)
- Selected-row accent highlight is already correct

## F. System-Wide Window Buttons

**File:** `files/usr/libexec/adwaita-lite-apply-settings`

In `write_gtk_settings()`, add a line to both GTK 3 and GTK 4 `settings.ini`:

```
gtk-decoration-layout=menu:minimize,maximize,close
```

This gives all CSD-using GTK apps (Thunar, GNOME Text Editor, Evince, etc.)
minimize/maximize/close buttons on the right side (Windows layout).

The settings app's own headerbar will inherit this automatically.

## G. Page Migration

**Files:** all 15 files in `settings/pages/`

Every page's `build()` method is updated to use `make_group()` instead of
raw `make_group_label()` + widget appends. The migration is mechanical:

**Before:**
```python
page.append(self.make_group_label(_("Theme")))
page.append(self.make_toggle_cards(...))
```

**After:**
```python
page.append(self.make_group(_("Theme"), [self.make_toggle_cards(...)]))
```

For groups with multiple rows (common in Mouse/Touchpad, Power, Accessibility):

```python
page.append(self.make_group(_("Touchpad"), [
    self.make_setting_row(_("Tap to click"), ..., switch),
    self.make_setting_row(_("Natural scrolling"), ..., switch),
    self.make_setting_row(_("Pointer speed"), ..., slider),
]))
```

### Pages and their group counts (for scope estimation):

| Page | Groups |
|------|--------|
| Appearance | 4 (Theme, Accent, Font, Wallpaper) |
| Display | 2-3 (Scale, Refresh rate, Night light) |
| Network | 1-2 |
| Bluetooth | 1-2 |
| Panel | 5 (Position, Density, Twilight, Module Layout, Pinned Apps) |
| Mouse & Touchpad | 2-3 |
| Keyboard | 2-3 |
| Sound | 1-2 |
| Power & Lock | 2-3 |
| Accessibility | 2-3 |
| Date & Time | 1-2 |
| Users | 1-2 |
| Language & Region | 1 |
| Default Apps | 1-2 |
| About | 1-2 (system info, not really grouped) |

---

## CSS Summary

Complete `style.css` rewrite. Final classes:

```
.sidebar                — headerbar_bg, right border
.sidebar row            — padding, radius, margin
.sidebar row:selected   — accent alpha highlight
.category-icon          — margin, opacity
.category-label         — 14px
.content-page           — max-width: 640px, margin auto, padding 32px top/bottom
.group-title            — 13px, bold, alpha 0.8, margin-bottom 4px
.boxed-list             — card_bg, border, radius 12px
.boxed-list > *:not(:first-child) — 1px top border (separator)
.setting-row            — min-height 48px, horizontal layout
.setting-subtitle       — 12px, alpha 0.6
.toggle-card            — 2px border, radius 12px, no bg
.toggle-card:checked    — accent border + alpha bg
.accent-circle          — 32px circle
.accent-circle:checked  — accent ring
.accent-{name}          — 9 hard-coded accent colors
.toast / .toast-error   — unchanged
.dialog-overlay/card    — unchanged
.destructive-button     — red text, red alpha hover
```

## What This Does NOT Change

- No libadwaita dependency
- No responsive sidebar collapse (stays fixed at 220px)
- No changes to settings logic or store
- No changes to the apply-settings token/waybar system
- No changes to page functionality — only visual wrapping

## Verification

- Build and test in GNOME Boxes VM
- Check light mode AND dark mode
- Check that the sidebar, group cards, and content area have visually
  distinct backgrounds forming a 3-tier hierarchy
- Check that minimize/maximize/close buttons appear on the settings app
  AND on Thunar/GNOME Text Editor (GTK CSD apps)
- Check that the headerbar title and search toggle work
- Check that content is clamped at ~640px in a maximized window
