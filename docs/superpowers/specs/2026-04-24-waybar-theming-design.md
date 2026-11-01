# Waybar Theming: ChromeOS-Inspired Consistent Design

**Date:** 2026-04-24
**Status:** Approved

## Problem

Horizontal and vertical waybar modes have drifted into inconsistent theming:
- Horizontal uses 999px pill radius, vertical uses 10px rounded squares
- Common CSS hover rules (999px) get overridden in vertical mode (10px), proving the split is fragile
- No CSS transitions anywhere
- Active indicator uses `border-bottom`/`border-left`/`border-right` with an opaque accent line — visually heavy and not ChromeOS-like
- No visual hierarchy between launcher and other modules
- Status modules (clock, audio, brightness, battery) are individually styled — no ChromeOS-style grouping

## Design Decisions

| Element | Decision | Rationale |
|---|---|---|
| Bar shape | Floating pill (999px border-radius on window) | Current behavior, confirmed by user |
| Module shape | Pill everywhere (999px border-radius) | Consistency between orientations |
| Active indicator | Dot/pill underneath icon via `::after` | ChromeOS signature element |
| Launcher button | Circle (50% border-radius) with subtle bg | Visual anchor, ChromeOS-style |
| Status grouping | Shared background pill for clock/audio/brightness/battery | ChromeOS-style contiguous group |
| Transitions | 200ms ease on background-color | Smooth hover/active states |
| Color source | All colors from palette.json via design tokens | Adwaita adherence |

## CSS Architecture

### Layer 1: Common CSS (`_waybar_css_common`)

Handles the shared design language for **both** orientations. This is the single source of truth for visual consistency.

**Contains:**
- `*` reset: font-family (Roboto + Material Icons Outlined), font-size, border/box-shadow none
- `window#waybar`: background (rgba panel_surface, 0.95), color, border-radius: 999px, margin
- Material Icons glyph sizing for `#custom-launcher`, `#pulseaudio`, `#backlight`, `#battery`
- `#custom-launcher`: border-radius: 50%, background: rgba(fg, 0.08), hover state
- `#taskbar button.active::after`: accent-colored pill indicator (width: 16px, height: 3px, border-radius: 2px, background: accent_hex, positioned bottom-center)
- `#taskbar button::after`: inactive dot (width: 6px, height: 3px, background: rgba(fg, 0.25))
- Battery warning/critical color overrides
- Pulseaudio muted color
- Tooltip styling (card bg, border, text color)
- `transition: background-color 200ms ease` on all interactive elements (launcher, taskbar buttons, status modules)
- Hover: panel_hover background on launcher, clock, battery, backlight, pulseaudio, tray

**Does NOT contain** (moved to orientation layers):
- Window padding (different axes per orientation)
- Module padding (different axes per orientation)
- Module sizing (min-height vs min-width+min-height)
- Active indicator border direction (removed — replaced with `::after` dot)
- Grouped status pill border-radius (first/last child differs per orientation)

### Layer 2: Horizontal CSS (`_waybar_css_horizontal`)

Optimized for top/bottom positioning where the bar is wide and short.

**Contains:**
- Window: `padding: 0 {inset}px` (horizontal-only inset)
- Module sizing: `min-height: {panel_height}px` only (natural width from content)
- Module padding: `0 {pad}px` (horizontal-only padding)
- `#custom-launcher`: padding and min-height, inherits circle from common
- `#taskbar`: padding: 0
- `#taskbar button`: padding, border-radius: 999px, min-height — `::after` dot from common
- `#taskbar button.active::after`: wider pill (inherited from common, no override needed)
- `#taskbar button:hover`: background
- Pinned app image tiles: padding, min-height, border-radius: 999px, hover
- Status module group wrapper: `display: flex; align-items: center; background: rgba(fg, 0.06); border-radius: 999px; padding: 2px`
- Status module group items: first-child `border-radius: 999px 0 0 999px`, last-child `border-radius: 0 999px 999px 0`, middle items `border-radius: 0`
- `#clock, #battery, #backlight, #pulseaudio, #tray`: padding, min-height
- `#clock`: font-weight: bold

**Grouped status pill (horizontal):**
See "Grouped Status Pill: Implementation Strategy" below for the full approach.

### Layer 3: Vertical CSS (`_waybar_css_vertical`)

Optimized for left/right positioning where the bar is narrow and tall.

**Contains:**
- Window: `min-width: {panel_width}px`, `padding: {inset}px {inset/2}px` (both axes)
- Module sizing: `min-width: {btn_w}px; min-height: {btn_w}px` (constrained to bar width)
- Module padding: `{pad}px {inset}px` (both axes for centered icons in narrow bar)
- `#custom-launcher`: padding, min-width, min-height, inherits circle from common
- `#taskbar button`: padding, border-radius: 999px, min-width, min-height
- `#taskbar button:hover`: background
- Pinned app image tiles: padding, min-width, min-height, border-radius: 999px, hover
- Status module group: vertical stacking — first-child rounds top, last-child rounds bottom
- `#clock, #battery, #backlight, #pulseaudio, #tray`: padding, min-width, min-height, border-radius: 999px
- `#clock`: font-weight: bold

**Grouped status pill (vertical):**
See "Grouped Status Pill: Implementation Strategy" below. Same modules stacked vertically with rotated border-radius.

## Active Indicator: `::after` Pseudo-Element

Replace the current `border-bottom`/`border-left`/`border-right: 3px solid accent` with a centered dot/pill using `::after`.

**Common CSS (both orientations):**
```css
#taskbar button {
    position: relative;
}
#taskbar button::after {
    content: "";
    position: absolute;
    bottom: 2px;
    left: 50%;
    transform: translateX(-50%);
    width: 6px;
    height: 3px;
    border-radius: 2px;
    background: rgba(fg, 0.25);
    transition: width 200ms ease, background-color 200ms ease;
}
#taskbar button.active::after {
    width: 16px;
    background: accent_hex;
}
```

This is orientation-agnostic — the dot always sits at the bottom center of the button regardless of bar direction. It removes the need for `border-bottom`/`border-left`/`border-right` switching entirely.

**Pinned apps (`#image.pin-N`):** Waybar renders pinned apps as `<image>` elements inside the bar. GTK CSS does support `::after` on image elements in some contexts, but waybar's image module may not. If `::after` doesn't work on pinned app images, they simply won't show the dot indicator — this is acceptable since pinned apps (not running) would show the inactive dot anyway, which is barely visible. The active dot only matters for `#taskbar button.active` which is confirmed to work.

## Color Tokens

All colors continue to flow through `_build_tokens()`. No new tokens needed. Existing tokens used:

| Token | Usage |
|---|---|
| `panel_surface` | Window background (95% opacity) |
| `panel_fg` | Window text color |
| `panel_secondary_fg` | Muted pulseaudio |
| `panel_hover` | Hover backgrounds (rgba(fg, 0.08)) |
| `accent_hex` | Active dot indicator |
| `color_warning` | Battery warning state |
| `color_error` | Battery critical state |
| `surface_card` | Tooltip background |
| `border_default` | Tooltip border |
| `text_primary` | Tooltip text |

New token usage:
| Usage | Source |
|---|---|
| `rgba(fg, 0.08)` for launcher circle background | Derived from `panel_fg` |
| `rgba(fg, 0.06)` for grouped status pill background | Derived from `panel_fg` |
| `rgba(fg, 0.25)` for inactive taskbar dot | Derived from `panel_fg` |

These are computed inline in the CSS builder, not added as separate tokens.

## Geometry Changes

No changes to the sizing/spacing system (`panel_height`, `panel_width`, `panel_margin`, `panel_bar_inset`, `panel_pad_module`, `panel_pad_launcher`, `panel_pad_pin`). These scale correctly with `font_size` already.

## Grouped Status Pill: Implementation Strategy

The status modules (pulseaudio, backlight, battery, clock) appear in the order defined by the user's layout. The tray module is always excluded from the group.

**Approach: Waybar `group` module wrapper**

Use waybar's built-in `group` module type to wrap the status modules in a parent container. This gives us a single element (`#group-status` or similar) to style as the grouped pill background. Inside it, each module retains individual hover behavior, but the outer container provides the contiguous background.

**Config change:** In `write_waybar_config`, wrap the status modules in a `group/status` entry:
```jsonc
"group/status": {
    "orientation": "horizontal",  // or "vertical"
    "modules": ["pulseaudio", "backlight", "battery", "clock"]
}
```

The actual module list comes from the user's layout, filtered to known status module IDs. Modules not in the status group (e.g., tray) remain outside.

**CSS:**
```css
/* Grouped status container */
#group-status {
    background: rgba(fg, 0.06);
    border-radius: 999px;
    padding: 2px;
}

/* Status modules inside the group get no individual radius — the group handles it */
#group-status > * {
    border-radius: 0;
    background: transparent;
}
/* Hover restores individual highlight */
#group-status > *:hover {
    background: panel_hover;
    border-radius: 999px;
}
```

This is clean, handles any module ordering, and gives the seamless ChromeOS look. The group element itself gets the pill background, modules inside are transparent until hovered.

## Files Modified

| File | Changes |
|---|---|
| `files/usr/libexec/adwaita-lite-apply-settings` | Refactor `_waybar_css_common`, `_waybar_css_horizontal`, `_waybar_css_vertical`; add `group/status` to waybar config in `write_waybar_config` |
| `tests/test_apply_settings.py` | Update expected CSS and config assertions |

## Out of Scope

- Changes to `palette.json` color values
- Changes to settings UI or module layout configuration
- Changes to waybar `config.jsonc` generation (module definitions, formats)
- Changes to panel sizing/spacing geometry system
