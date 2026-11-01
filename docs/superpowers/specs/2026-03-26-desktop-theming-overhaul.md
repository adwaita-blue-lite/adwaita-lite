# Desktop Theming Overhaul

**Date:** 2026-03-26
**Status:** Approved, ready for implementation

## Goal

Overhaul the desktop theming system to produce a modern, cohesive, Chrome OS-inspired desktop with strict Adwaita color compliance. The existing architecture (`apply-settings` generating all config at runtime) is correct — this spec improves the quality of what it generates.

Primary issues being fixed:
- Waybar CSS is completely broken when panel edge is `left` or `right`
- Status modules show verbose text labels (`VOL 45%`, `BAT 80%`) instead of icons
- No pinned app launchers in the panel
- Color derivation logic is scattered across individual `write_*` functions
- Generated configs are inconsistent with static fallback files

---

## Section 1 — Design Token System

### What changes

Replace scattered per-function color derivation with a single `_build_tokens(settings: dict) -> dict` function in `adwaita-lite-apply-settings`. All `write_*` functions receive the token dict and do zero color math themselves.

`ADWAITA` and `ACCENTS` dicts remain unchanged as the source data.

### Token schema

```python
{
    # Surfaces
    "surface_base":       str,   # panel/window bg     e.g. "#fafafa"
    "surface_card":       str,   # elevated surfaces   e.g. "#ffffff"
    "surface_headerbar":  str,   # titlebar bg
    "surface_overlay":    str,   # fuzzel/popup bg

    # Text
    "text_primary":       str,
    "text_secondary":     str,
    "text_disabled":      str,

    # Borders
    "border_default":     str,   # subtle border
    "border_strong":      str,   # always-visible border (used on panel)

    # Accent — pre-derived in all formats needed downstream
    "accent_hex":         str,   # "#3584e4"
    "accent_rgba_30":     str,   # "rgba(r, g, b, 0.3)"  — active bg
    "accent_rgba_15":     str,   # "rgba(r, g, b, 0.15)" — hover bg
    "accent_mako":        str,   # "#3584e4FF"           — mako format
    "accent_fuzzel":      str,   # "3584e4ff"            — fuzzel format

    # State backgrounds
    "state_hover":        str,   # "rgba(..., 0.08)"
    "state_active":       str,   # same as accent_rgba_30

    # Status indicators
    "color_warning":      str,   # battery warning color
    "color_error":        str,   # battery critical / wrong password

    # Typography
    "font_ui":            str,   # "Roboto"
    "font_mono":          str,   # "Roboto Mono"
    "font_size_ui":       int,   # 13
    "font_size_mono":     int,   # 11

    # Panel geometry (derived from density + edge)
    "panel_height":       int,   # px — used for horizontal bars
    "panel_width":        int,   # px — used for vertical bars
    "panel_spacing":      int,
    "panel_icon_size":    int,
    "is_vertical":        bool,  # True when edge is "left" or "right"

    # Notification anchor (opposite corner from panel)
    "mako_anchor":        str,   # e.g. "top-right"
}
```

`border_strong` is `border_default` in light theme and one step darker in dark theme — ensures panel outline is visible against any wallpaper.

`state_hover` is `rgba(text_primary, 0.08)` — Adwaita's standard hover opacity.

---

## Section 2 — Waybar Config & Modules

### Format strings

All status modules switch from text labels to icon-only display using Adwaita system theme icons via `format-icons`.

| Module | Old format | New format | Icon names |
|--------|-----------|------------|------------|
| `network` | `NET {essid}` | `{icon}` | `network-wireless-signal-excellent/good/ok/weak/none-symbolic`, `network-wired-symbolic`, `network-offline-symbolic` |
| `pulseaudio` | `VOL {volume}%` | `{icon}` | `audio-volume-high/medium/low/muted-symbolic` |
| `backlight` | `BRI {percent}%` | `{icon}` | `display-brightness-symbolic` |
| `battery` | `BAT {capacity}%` | `{icon}` | `battery-full/good/low/caution/empty-symbolic`, `battery-full/good/low/caution/empty-charging-symbolic` |
| `clock` | `{:%a %b %-d  %I:%M %p}` | `{:%H:%M}` | — |
| `wlr/taskbar` | `{title}` | `""` | icon-size driven, no text |

Tooltips carry the full detail: wifi SSID + IP, volume %, battery % + charging state, brightness %, current date for clock.

### Pinned launchers

`settings.json` gains a `pinned` array:

```json
"pinned": [
  {"name": "Chrome",  "command": "flatpak run com.google.Chrome", "icon": "com.google.Chrome"},
  {"name": "Bazaar",  "command": "flatpak run dev.bazaar.app",    "icon": "dev.bazaar.app"}
]
```

`defaults/settings.json` pre-populates Chrome and Bazaar (matching what first-boot installs).

`write_waybar_config()` generates a `custom/pin-N` module for each entry:

```json
"custom/pin-0": {
    "return-type": "json",
    "exec": "echo '{\"icon\":\"com.google.Chrome\",\"tooltip\":\"Chrome\"}'",
    "interval": "once",
    "on-click": "flatpak run com.google.Chrome",
    "format": "{icon}"
}
```

`interval: once` — runs once at startup, result cached. Zero polling overhead.

If `icon` is empty or blank, falls back to `application-x-executable`.

### Panel module order

Pinned modules are injected into `modules-left` automatically between the launcher button and the taskbar:

```
modules-left: [custom/launcher, custom/pin-0, custom/pin-1, ..., wlr/taskbar]
```

Pinned app order is independent of the layout section drag/reorder system.

---

## Section 3 — Waybar CSS

### Root cause of vertical bug

`write_waybar_config()` currently emits one CSS string with hardcoded `min-height`, horizontal `padding`, and `border-radius: 999px` on the full bar. A vertical bar (tall, narrow) breaks every one of these assumptions.

### Fix: orientation-aware CSS generation

`write_waybar_config()` calls one of two CSS builder functions based on `tokens["is_vertical"]`. Both share a `_waybar_css_common()` helper for rules that are orientation-independent.

#### Common rules (both orientations)

```css
* {
    font-family: {font_ui};
    font-size: {font_size_ui}px;
    color: {text_primary};
    border: none;
    box-shadow: none;
}

window#waybar {
    background: rgba({surface_base}, 0.95);
    border: 1px solid {border_strong};
    border-radius: 999px;
    margin: 8px;
}

#custom-launcher {
    background: {accent_hex};
    color: #ffffff;
    border-radius: 999px;
    font-weight: bold;
}

#battery.warning { color: {color_warning}; }
#battery.critical { color: {color_error}; }
#network.disconnected { color: {text_secondary}; }
#pulseaudio.muted { color: {text_secondary}; }

tooltip {
    background: {surface_card};
    border: 1px solid {border_default};
    border-radius: 8px;
    color: {text_primary};
}
```

#### Horizontal-specific rules (top/bottom)

```css
#custom-launcher { padding: 0 16px; min-height: {panel_height}px; }

#taskbar { padding: 0; }
#taskbar button {
    padding: 0 8px;
    border-radius: 999px;
    min-height: {panel_height}px;
}
#taskbar button.active { background: {accent_rgba_30}; }
#taskbar button:hover  { background: {state_hover}; }

/* pin-N modules — one rule generated per pinned app, e.g. #custom-pin-0 */
#custom-pin-0, #custom-pin-1, ... {
    padding: 0 8px;
    min-height: {panel_height}px;
    border-radius: 999px;
}
#custom-pin-0:hover, #custom-pin-1:hover, ... { background: {state_hover}; }
/* write_waybar_config() generates these selectors dynamically based on len(pinned) */

#clock, #network, #battery, #backlight, #pulseaudio, #tray {
    padding: 0 10px;
    min-height: {panel_height}px;
}

#clock { font-weight: bold; padding: 0 14px; }
#tray  { padding: 0 6px; }
```

#### Vertical-specific rules (left/right)

```css
window#waybar { min-width: {panel_width}px; }

#custom-launcher {
    padding: 12px 0;
    min-width: {panel_width}px;
    margin-bottom: 4px;
}

#taskbar { padding: 0; }
#taskbar button {
    padding: 8px 0;
    border-radius: 999px;
    min-width: {panel_width}px;
}
#taskbar button.active { background: {accent_rgba_30}; }
#taskbar button:hover  { background: {state_hover}; }

/* pin-N modules — generated dynamically, same as horizontal */
#custom-pin-0, #custom-pin-1, ... {
    padding: 8px 0;
    min-width: {panel_width}px;
    border-radius: 999px;
}
#custom-pin-0:hover, #custom-pin-1:hover, ... { background: {state_hover}; }

#clock, #network, #battery, #backlight, #pulseaudio, #tray {
    padding: 10px 0;
    min-width: {panel_width}px;
}

#clock { font-weight: bold; }
#tray  { padding: 6px 0; }
```

The vertical bar also sets `"height": null` in the JSON config (waybar ignores height for vertical bars) and uses `"width": panel_width` instead.

### Panel border visibility fix

Dark mode at 0.95 opacity on dark wallpapers makes `border_default` invisible. `border_strong` is computed as:
- Light: `border_default` (already visible)
- Dark: one step more opaque — `#666666` instead of `#4a4a4a`

---

## Section 4 — Settings App: Pinned Apps

### Location

New "Pinned apps" subsection at the bottom of the **Layout** tab, below the three section columns. No new tab.

### UI structure

```
─────────────────────────────
Pinned apps
These appear in the panel before the window list.

┌─────────────────────────────────────────┐
│  Google Chrome                          │
│  Bazaar                                 │
└─────────────────────────────────────────┘
  [▲] [▼]  [Remove]              [Add…]
```

`Gtk.ListBox` with single-selection. Same ▲/▼ reorder pattern as layout section columns.

### Add app dialog

`Gtk.Dialog` with three `Gtk.Entry` fields:

| Field | Placeholder | Required |
|-------|------------|----------|
| Name | `Display name (e.g. Chrome)` | No — defaults to command basename |
| Command | `Command to run (e.g. flatpak run com.google.Chrome)` | Yes |
| Icon | `Icon name (e.g. com.google.Chrome)` | No — defaults to `application-x-executable` |

Validation: command must be non-empty. All other fields have safe defaults.

### Data flow

On "Add" confirm: append to `settings["pinned"]`, save, call `apply-settings`.
On "Remove": remove selected entry, save, call `apply-settings`.
On ▲/▼: swap entries, save, call `apply-settings`.

Same immediate-apply pattern used by the rest of the settings app.

---

## Section 5 — Other Surfaces

All surfaces are now driven entirely from `_build_tokens()`. The changes below close gaps between what `write_*` functions generate and what the static fallback files contain.

### labwc themerc

Add missing fields to generated output:
- `menu.border.width: 1`
- `menu.border.color: {border_default}`
- `osd.border.color: {border_default}`

No other changes — existing themerc generation is correct.

### fuzzel

Generated config gains missing fields to match static fallback:
- `icons-enabled=yes`
- `terminal=foot`
- `layer=overlay`
- `exit-on-keyboard-focus-loss=yes`
- `width=480` (normal) / `width=400` (compact)
- `horizontal-pad=16`, `vertical-pad=12`, `inner-pad=8`
- `selection-match` color: `accent_fuzzel` on white

### mako

Generated config gains missing fields:
- `height=120`
- `padding=12`
- `icon-location=left`
- `max-icon-size=48`
- `max-visible=3`
- `margin=12`

`anchor` becomes orientation-aware:
- Panel `bottom` → `top-right`
- Panel `top` → `bottom-right`
- Panel `left` or `right` → `top-right`

Remove `indicator-thickness` and `show-failed-attempts` from mako static config (they're swaylock settings).

### swaylock

Generated config gains missing fields:
- `indicator-radius=80`
- `indicator-thickness=8`
- `show-failed-attempts`
- `inside-*-color` variants all set to `surface_card` stripped of `#`

### foot

Generated config gains:
- `pad=12x12 center`

### gtkgreet CSS

Replace hardcoded dark theme with Adwaita light values (`ADWAITA["light"]` + blue accent). Greeter is pre-user so it always uses the default theme — consistent with the out-of-box experience.

---

## Files Modified

| File | Change |
|------|--------|
| `files/usr/libexec/adwaita-lite-apply-settings` | Add `_build_tokens()`, update all `write_*` functions, add pinned launcher generation to `write_waybar_config()`, orientation-aware CSS |
| `files/usr/bin/adwaita-lite-setup-wizard` | No change |
| `files/usr/share/adwaita-lite/defaults/settings.json` | Add `pinned` array with Chrome + Bazaar defaults |
| `files/usr/bin/adwaita-lite-settings` | Add pinned apps UI to Layout tab |
| `files/etc/xdg/labwc/themes/Adwaita-Lite/themerc` | Sync with generated output |
| `files/etc/xdg/fuzzel/fuzzel.ini` | Sync with generated output |
| `files/etc/xdg/mako/config` | Sync with generated output, remove swaylock options |
| `files/etc/xdg/swaylock/config` | Sync with generated output |
| `files/etc/greetd/gtkgreet.css` | Replace dark hardcode with Adwaita light |

`files/etc/xdg/foot/foot.ini` and `files/etc/xdg/swaylock/config` are system-wide fallbacks only — users get the generated versions on login.

---

## Out of Scope

- New icon fonts or Nerd Fonts (Adwaita icon theme covers all modules)
- nwg-dock or any new package dependency
- `.desktop` file parsing for the add-app dialog
- Animation or blur effects
- Per-monitor waybar configuration
