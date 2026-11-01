# Desktop Theming Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Overhaul the desktop theming system with a centralized token system, icon-only Waybar modules, pinned app launchers, orientation-aware CSS, and a settings UI for managing pinned apps.

**Architecture:** A single `_build_tokens(settings)` function generates all derived color/geometry values. All `write_*` functions receive the tokens dict (superset of settings) and do no color math themselves. Waybar CSS is split into `_waybar_css_common()` + `_waybar_css_horizontal()` / `_waybar_css_vertical()` helpers, selected based on `tokens["is_vertical"]`.

**Tech Stack:** Python 3, GTK4 (gi/PyGObject), JSON, CSS (Waybar), INI-style config files

---

## File Map

| File | Change |
|------|--------|
| `files/usr/libexec/adwaita-lite-apply-settings` | Add `_build_tokens()`, update `ensure_settings()`, `main()`, and all `write_*` functions |
| `files/usr/share/adwaita-lite/defaults/settings.json` | Add `pinned` array |
| `files/usr/bin/adwaita-lite-settings` | Add pinned apps UI to Layout tab |
| `files/etc/xdg/fuzzel/fuzzel.ini` | Add `selection-match` field |
| `files/etc/xdg/swaylock/config` | Fix `inside-wrong-color` to match generated |
| `files/etc/greetd/gtkgreet.css` | Replace dark hardcode with Adwaita light |

(labwc themerc, mako config, and foot.ini static files already match what the updated generator will produce)

---

## Task 1: Token System + ensure_settings() pinned validation

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

### Overview

Add `_build_tokens(settings: dict) -> dict` after the existing helper functions. Update `ensure_settings()` to validate and normalize a `pinned` array. Update `main()` to call `_build_tokens()` and pass the result to all `write_*` functions.

Since tokens is `{**settings, ...derived_keys}`, all existing `write_*` functions continue to work unchanged — they access `tokens["theme"]`, `tokens["accent"]`, etc. identically to before.

- [ ] **Step 1: Add `_build_tokens()` after the existing `_rgba_css()` helper (line 147)**

Add this function:

```python
def _build_tokens(settings: dict) -> dict:
    """Build the full design token dict from validated settings."""
    palette = ADWAITA[settings["theme"]]
    accent_hex = ACCENTS[settings["accent"]]
    r, g, b = _hex_to_rgb_tuple(accent_hex)

    density = settings["density"]
    edge = settings["edge"]
    is_vertical = edge in ("left", "right")

    panel_height = 36 if density == "compact" else 46
    panel_width = 56 if density == "compact" else 64
    panel_spacing = 6 if density == "compact" else 10
    panel_icon_size = 14 if density == "compact" else 18

    if edge == "top":
        mako_anchor = "bottom-right"
    else:
        mako_anchor = "top-right"

    border_strong = "#666666" if settings["theme"] == "dark" else palette["border"]

    return {
        **settings,
        # Surfaces
        "surface_base": palette["window_bg"],
        "surface_card": palette["card_bg"],
        "surface_headerbar": palette["headerbar_bg"],
        "surface_overlay": palette["view_bg"],
        # Text
        "text_primary": palette["fg"],
        "text_secondary": palette["secondary_fg"],
        "text_disabled": palette["inactive_fg"],
        # Borders
        "border_default": palette["border"],
        "border_strong": border_strong,
        # Accent — pre-derived in all formats needed downstream
        "accent_hex": accent_hex,
        "accent_rgba_30": f"rgba({r}, {g}, {b}, 0.3)",
        "accent_rgba_15": f"rgba({r}, {g}, {b}, 0.15)",
        "accent_mako": accent_hex + "ff",
        "accent_fuzzel": _strip_hash(accent_hex) + "ff",
        # State backgrounds
        "state_hover": _rgba_css(palette["fg"], 0.08),
        "state_active": f"rgba({r}, {g}, {b}, 0.3)",
        # Status indicators
        "color_warning": ACCENTS["yellow"],
        "color_error": ACCENTS["red"],
        # Typography
        "font_ui": "Roboto",
        "font_mono": "Roboto Mono",
        "font_size_ui": 13,
        "font_size_mono": 11,
        # Panel geometry
        "panel_height": panel_height,
        "panel_width": panel_width,
        "panel_spacing": panel_spacing,
        "panel_icon_size": panel_icon_size,
        "is_vertical": is_vertical,
        # Notification anchor (opposite corner from panel)
        "mako_anchor": mako_anchor,
    }
```

- [ ] **Step 2: Update `ensure_settings()` to validate `pinned`**

In `ensure_settings()`, after the accent validation block (around line 173) and before the layout validation block, add:

```python
    # Validate pinned launchers
    raw_pinned = data.get("pinned", [])
    pinned: list[dict] = []
    if isinstance(raw_pinned, list):
        for entry in raw_pinned:
            if not isinstance(entry, dict):
                continue
            cmd = str(entry.get("command", "")).strip()
            if not cmd:
                continue
            name = str(entry.get("name", "")).strip() or cmd.split()[-1]
            icon = str(entry.get("icon", "")).strip() or "application-x-executable"
            pinned.append({"name": name, "command": cmd, "icon": icon})
```

Then add `"pinned": pinned,` to the `normalized` dict at the end of `ensure_settings()`:

```python
    normalized = {
        "edge": edge,
        "density": density,
        "theme": theme,
        "wallpaper": wallpaper,
        "accent": accent,
        "layout": layout,
        "pinned": pinned,
    }
```

- [ ] **Step 3: Update `main()` to build tokens and pass them to all `write_*` functions**

Replace the existing `main()` body:

```python
def main() -> int:
    settings = ensure_settings()
    tokens = _build_tokens(settings)
    write_waybar_config(tokens)
    write_gtk_settings(tokens)
    write_fuzzel_config(tokens)
    write_mako_config(tokens)
    write_foot_config(tokens)
    write_labwc_themerc(tokens)
    write_swaylock_config(tokens)

    if os.environ.get("WAYLAND_DISPLAY"):
        restart_program("swaybg", ["swaybg", "-i", tokens["wallpaper"], "-m", "fill"])
        restart_program("waybar", ["waybar"])
        subprocess.run(["makoctl", "reload"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["labwc", "--reconfigure"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return 0
```

- [ ] **Step 4: Verify — run apply-settings and confirm it exits cleanly**

```bash
python3 files/usr/libexec/adwaita-lite-apply-settings
echo "Exit code: $?"
```

Expected: `Exit code: 0`

Also check that the token keys are accessible by adding a quick sanity check (then remove):
```bash
python3 -c "
import sys; sys.path.insert(0, 'files/usr/libexec')
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('a', 'files/usr/libexec/adwaita-lite-apply-settings')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s = m.ensure_settings()
t = m._build_tokens(s)
assert 'surface_base' in t
assert 'accent_rgba_30' in t
assert 'is_vertical' in t
assert isinstance(t['pinned'], list)
print('tokens OK:', list(t.keys()))
"
```

Expected: prints `tokens OK:` with all keys, no AssertionError.

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: add _build_tokens() and pinned validation to apply-settings"
```

---

## Task 2: Waybar Config Rewrite

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

### Overview

Replace the existing `write_waybar_config()` with three CSS helper functions + a rewritten main function. Changes:
- Modules switch from text labels to icon-only via `format-icons`
- `custom/pin-N` modules generated from `tokens["pinned"]`, injected into `modules-left` after the launcher
- CSS split into common + orientation-specific helpers
- Vertical bar uses `min-width` + `width` config key; horizontal uses `min-height` + `height`

- [ ] **Step 1: Add the three CSS helper functions before `write_waybar_config()`**

Add these three functions. Place them immediately before the existing `write_waybar_config()` function:

```python
def _waybar_css_common(tokens: dict) -> str:
    r, g, b = _hex_to_rgb_tuple(tokens["surface_base"])
    return f"""\
* {{
    font-family: "{tokens["font_ui"]}", sans-serif;
    font-size: {tokens["font_size_ui"]}px;
    color: {tokens["text_primary"]};
    border: none;
    box-shadow: none;
}}

window#waybar {{
    background: rgba({r}, {g}, {b}, 0.95);
    border: 1px solid {tokens["border_strong"]};
    border-radius: 999px;
    margin: 8px;
}}

#custom-launcher {{
    background: {tokens["accent_hex"]};
    color: #ffffff;
    border-radius: 999px;
    font-weight: bold;
}}

#custom-launcher:hover {{ opacity: 0.85; }}

#battery.warning {{ color: {tokens["color_warning"]}; }}
#battery.critical {{ color: {tokens["color_error"]}; }}
#network.disconnected {{ color: {tokens["text_secondary"]}; }}
#pulseaudio.muted {{ color: {tokens["text_secondary"]}; }}

tooltip {{
    background: {tokens["surface_card"]};
    border: 1px solid {tokens["border_default"]};
    border-radius: 8px;
    color: {tokens["text_primary"]};
}}
"""


def _waybar_css_horizontal(tokens: dict) -> str:
    h = tokens["panel_height"]
    pinned = tokens.get("pinned", [])

    pin_css = ""
    if pinned:
        selectors = ", ".join(f"#custom-pin-{i}" for i in range(len(pinned)))
        hover_selectors = ", ".join(f"#custom-pin-{i}:hover" for i in range(len(pinned)))
        pin_css = f"""
{selectors} {{
    padding: 0 8px;
    min-height: {h}px;
    border-radius: 999px;
}}
{hover_selectors} {{ background: {tokens["state_hover"]}; }}
"""

    return f"""
#custom-launcher {{ padding: 0 16px; min-height: {h}px; }}

#taskbar {{ padding: 0; }}
#taskbar button {{
    padding: 0 8px;
    border-radius: 999px;
    min-height: {h}px;
}}
#taskbar button.active {{ background: {tokens["accent_rgba_30"]}; }}
#taskbar button:hover  {{ background: {tokens["state_hover"]}; }}
{pin_css}
#clock, #network, #battery, #backlight, #pulseaudio, #tray {{
    padding: 0 10px;
    min-height: {h}px;
}}

#clock {{ font-weight: bold; padding: 0 14px; }}
#tray  {{ padding: 0 6px; }}
"""


def _waybar_css_vertical(tokens: dict) -> str:
    w = tokens["panel_width"]
    pinned = tokens.get("pinned", [])

    pin_css = ""
    if pinned:
        selectors = ", ".join(f"#custom-pin-{i}" for i in range(len(pinned)))
        hover_selectors = ", ".join(f"#custom-pin-{i}:hover" for i in range(len(pinned)))
        pin_css = f"""
{selectors} {{
    padding: 8px 0;
    min-width: {w}px;
    border-radius: 999px;
}}
{hover_selectors} {{ background: {tokens["state_hover"]}; }}
"""

    return f"""
window#waybar {{ min-width: {w}px; }}

#custom-launcher {{
    padding: 12px 0;
    min-width: {w}px;
    margin-bottom: 4px;
}}

#taskbar {{ padding: 0; }}
#taskbar button {{
    padding: 8px 0;
    border-radius: 999px;
    min-width: {w}px;
}}
#taskbar button.active {{ background: {tokens["accent_rgba_30"]}; }}
#taskbar button:hover  {{ background: {tokens["state_hover"]}; }}
{pin_css}
#clock, #network, #battery, #backlight, #pulseaudio, #tray {{
    padding: 10px 0;
    min-width: {w}px;
}}

#clock {{ font-weight: bold; }}
#tray  {{ padding: 6px 0; }}
"""
```

- [ ] **Step 2: Replace `write_waybar_config()` entirely**

```python
def write_waybar_config(tokens: dict) -> None:
    WAYBAR_DIR.mkdir(parents=True, exist_ok=True)

    layout = tokens["layout"]
    pinned = tokens.get("pinned", [])
    is_vertical = tokens["is_vertical"]
    icon_size = tokens["panel_icon_size"]
    spacing = tokens["panel_spacing"]

    # Build modules-left: inject pin-N modules after the launcher
    modules_left = list(layout["start"])
    pin_ids = [f"custom/pin-{i}" for i in range(len(pinned))]
    if pin_ids:
        try:
            idx = modules_left.index("custom/launcher")
            modules_left = modules_left[:idx + 1] + pin_ids + modules_left[idx + 1:]
        except ValueError:
            modules_left = pin_ids + modules_left

    config: dict = {
        "layer": "top",
        "position": tokens["edge"],
        "spacing": spacing,
        "modules-left": modules_left,
        "modules-center": layout["center"],
        "modules-right": layout["end"],
    }

    if is_vertical:
        config["width"] = tokens["panel_width"]
    else:
        config["height"] = tokens["panel_height"]

    config["custom/launcher"] = {
        "format": " Apps ",
        "tooltip": False,
        "on-click": "wtype -M ctrl -k F12",
    }

    config["wlr/taskbar"] = {
        "format": "",
        "icon-size": icon_size,
        "all-outputs": False,
        "on-click": "activate",
        "on-click-middle": "close",
        "tooltip-format": "{title}",
    }

    config["network"] = {
        "format": "{icon}",
        "format-icons": {
            "wifi": [
                "network-wireless-signal-none-symbolic",
                "network-wireless-signal-weak-symbolic",
                "network-wireless-signal-ok-symbolic",
                "network-wireless-signal-good-symbolic",
                "network-wireless-signal-excellent-symbolic",
            ],
            "ethernet": "network-wired-symbolic",
            "disconnected": "network-offline-symbolic",
        },
        "tooltip-format": "{essid} — {ipaddr}",
        "tooltip-format-ethernet": "{ifname} — {ipaddr}",
        "tooltip-format-disconnected": "Disconnected",
    }

    config["pulseaudio"] = {
        "format": "{icon}",
        "format-muted": "{icon}",
        "format-icons": {
            "default": [
                "audio-volume-muted-symbolic",
                "audio-volume-low-symbolic",
                "audio-volume-medium-symbolic",
                "audio-volume-high-symbolic",
            ],
        },
        "tooltip-format": "{volume}%",
        "on-click": "pavucontrol",
        "scroll-step": 5,
    }

    config["backlight"] = {
        "format": "{icon}",
        "format-icons": ["display-brightness-symbolic"],
        "tooltip-format": "{percent}%",
    }

    config["battery"] = {
        "format": "{icon}",
        "format-charging": "{icon}",
        "format-icons": {
            "charging": [
                "battery-empty-charging-symbolic",
                "battery-caution-charging-symbolic",
                "battery-low-charging-symbolic",
                "battery-good-charging-symbolic",
                "battery-full-charging-symbolic",
            ],
            "default": [
                "battery-empty-symbolic",
                "battery-caution-symbolic",
                "battery-low-symbolic",
                "battery-good-symbolic",
                "battery-full-symbolic",
            ],
        },
        "states": {"warning": 25, "critical": 12},
        "tooltip-format": "{capacity}%",
    }

    config["clock"] = {
        "format": "{:%H:%M}",
        "tooltip-format": "{:%A, %B %-d, %Y}",
    }

    config["tray"] = {
        "icon-size": icon_size,
        "spacing": 8,
    }

    # Generate custom/pin-N modules for each pinned app
    for i, app in enumerate(pinned):
        icon = app.get("icon") or "application-x-executable"
        name = app.get("name") or app["command"].split()[-1]
        # json.dumps handles escaping; replace ' in result for shell safety
        exec_json = json.dumps({"icon": icon, "tooltip": name})
        exec_cmd = "echo '" + exec_json.replace("'", "'\\''") + "'"
        config[f"custom/pin-{i}"] = {
            "return-type": "json",
            "exec": exec_cmd,
            "interval": "once",
            "on-click": app["command"],
            "format": "{icon}",
        }

    with (WAYBAR_DIR / "config.jsonc").open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")

    css = _waybar_css_common(tokens)
    if is_vertical:
        css += _waybar_css_vertical(tokens)
    else:
        css += _waybar_css_horizontal(tokens)

    with (WAYBAR_DIR / "style.css").open("w", encoding="utf-8") as handle:
        handle.write(css)
```

- [ ] **Step 3: Verify — horizontal bar (default)**

```bash
python3 files/usr/libexec/adwaita-lite-apply-settings
```

Check `~/.config/waybar/config.jsonc` — confirm icon-only modules:
```bash
grep -E '"format": "\{icon\}"|"format": ""' ~/.config/waybar/config.jsonc
```
Expected: multiple matches (network, pulseaudio, backlight, battery, taskbar).

Check CSS uses `min-height`, not `min-width`:
```bash
grep "min-height" ~/.config/waybar/style.css | head -3
grep "min-width" ~/.config/waybar/style.css
```
Expected: `min-height` lines present, `min-width` absent (horizontal).

- [ ] **Step 4: Verify — vertical bar**

```bash
# Temporarily test vertical orientation
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.config/adwaita-lite/settings.json'
d = json.loads(p.read_text())
d['edge'] = 'left'
p.write_text(json.dumps(d, indent=2) + '\n')
"
python3 files/usr/libexec/adwaita-lite-apply-settings
grep "min-width" ~/.config/waybar/style.css | head -3
grep "min-height" ~/.config/waybar/style.css
# Restore
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.config/adwaita-lite/settings.json'
d = json.loads(p.read_text())
d['edge'] = 'bottom'
p.write_text(json.dumps(d, indent=2) + '\n')
"
python3 files/usr/libexec/adwaita-lite-apply-settings
```

Expected: when edge=left, `min-width` is present in CSS, `min-height` is absent.

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: rewrite write_waybar_config() with icons, pinned launchers, orientation-aware CSS"
```

---

## Task 3: Fuzzel, Mako, Foot

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

### Overview

Update three `write_*` functions to use tokens and add missing fields that exist in the static fallback configs.

- [ ] **Step 1: Replace `write_fuzzel_config()`**

```python
def write_fuzzel_config(tokens: dict) -> None:
    FUZZEL_DIR.mkdir(parents=True, exist_ok=True)

    width = 34 if tokens["density"] == "compact" else 40

    ini = f"""\
[main]
font={tokens["font_ui"]}:size=12
icons-enabled=yes
terminal=foot
layer=overlay
exit-on-keyboard-focus-loss=yes
width={width}
horizontal-pad=16
vertical-pad=12
inner-pad=8

[colors]
background={_hex_to_rgba(tokens["surface_base"])}
text={_hex_to_rgba(tokens["text_primary"])}
match={tokens["accent_fuzzel"]}
selection={tokens["accent_fuzzel"]}
selection-text={_hex_to_rgba("#ffffff")}
selection-match=ffffffff
border={_hex_to_rgba(tokens["accent_hex"])}

[border]
width=2
radius=12
"""

    with (FUZZEL_DIR / "fuzzel.ini").open("w", encoding="utf-8") as handle:
        handle.write(ini)
```

- [ ] **Step 2: Replace `write_mako_config()`**

```python
def write_mako_config(tokens: dict) -> None:
    MAKO_DIR.mkdir(parents=True, exist_ok=True)

    config = f"""\
font={tokens["font_ui"]} {tokens["font_size_mono"]}
background-color={_hex_to_mako(tokens["surface_base"])}
text-color={_hex_to_mako(tokens["text_primary"])}
border-color={tokens["accent_mako"]}
border-size=2
border-radius=12
padding=12
width=360
height=120
margin=12
default-timeout=5000
max-visible=3
layer=overlay
anchor={tokens["mako_anchor"]}
icon-location=left
max-icon-size=48
"""

    with (MAKO_DIR / "config").open("w", encoding="utf-8") as handle:
        handle.write(config)
```

- [ ] **Step 3: Update `write_foot_config()` — add `pad` to `[main]`**

In the existing `write_foot_config()` function, the `ini` f-string starts with:

```python
    ini = f"""\
[main]
font=Roboto Mono:size=11
```

Change it to:

```python
    ini = f"""\
[main]
font={tokens["font_mono"]}:size={tokens["font_size_mono"]}
pad=12x12 center
```

(The rest of the function body stays the same. Just update those two lines in `[main]`.)

- [ ] **Step 4: Verify**

```bash
python3 files/usr/libexec/adwaita-lite-apply-settings
grep "icons-enabled" ~/.config/fuzzel/fuzzel.ini
grep "layer=overlay" ~/.config/fuzzel/fuzzel.ini
grep "selection-match" ~/.config/fuzzel/fuzzel.ini
grep "anchor=" ~/.config/mako/config
grep "layer=overlay" ~/.config/mako/config
grep "pad=12x12" ~/.config/foot/foot.ini
```

Expected: all greps find their lines.

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: update fuzzel/mako/foot generators to use tokens and add missing fields"
```

---

## Task 4: Swaylock, Labwc

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

### Overview

Add missing swaylock fields (`indicator-radius`, `indicator-thickness`, `show-failed-attempts`). Add missing labwc menu border fields.

- [ ] **Step 1: Replace `write_swaylock_config()`**

```python
def write_swaylock_config(tokens: dict) -> None:
    SWAYLOCK_DIR.mkdir(parents=True, exist_ok=True)

    inside = _strip_hash(tokens["surface_card"])
    ring = _strip_hash(tokens["accent_hex"])
    bg = _strip_hash(tokens["surface_base"])
    fg = _strip_hash(tokens["text_primary"])
    wrong = "c01c28"
    transparent = "00000000"

    config = f"""\
color={bg}
indicator-radius=80
indicator-thickness=8
show-failed-attempts
inside-color={inside}
inside-clear-color={inside}
inside-ver-color={inside}
inside-wrong-color={inside}
ring-color={ring}
ring-clear-color={ring}
ring-ver-color={ring}
ring-wrong-color={wrong}
text-color={fg}
text-clear-color={fg}
text-ver-color={fg}
text-wrong-color={wrong}
line-color={transparent}
line-clear-color={transparent}
line-ver-color={transparent}
line-wrong-color={transparent}
key-hl-color={ring}
bs-hl-color={wrong}
separator-color={transparent}
"""

    with (SWAYLOCK_DIR / "config").open("w", encoding="utf-8") as handle:
        handle.write(config)
```

- [ ] **Step 2: Update `write_labwc_themerc()` — add menu border fields**

In `write_labwc_themerc()`, the menu section currently ends with `menu.separator.color`. Add two lines after it:

```python
    themerc = f"""\
...
menu.separator.color: {palette["border"]}
menu.border.width: 1
menu.border.color: {palette["border"]}
...
```

The full menu section in the `themerc` f-string becomes:

```python
# Menu
menu.items.bg: flat solid
menu.items.bg.color: {palette["window_bg"]}
menu.items.text.color: {palette["fg"]}
menu.items.active.bg: flat solid
menu.items.active.bg.color: {accent}
menu.items.active.text.color: #ffffff
menu.separator.color: {palette["border"]}
menu.border.width: 1
menu.border.color: {palette["border"]}
```

Note: `write_labwc_themerc()` still uses `palette` and `accent` derived locally — that's fine, no change needed there until a future cleanup. Just add the two new lines to the f-string.

- [ ] **Step 3: Verify**

```bash
python3 files/usr/libexec/adwaita-lite-apply-settings
grep "indicator-radius" ~/.config/swaylock/config
grep "show-failed-attempts" ~/.config/swaylock/config
grep "menu.border.width" ~/.config/labwc/themerc
```

Expected: all three lines found.

- [ ] **Step 4: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: update swaylock and labwc generators with missing fields"
```

---

## Task 5: gtkgreet CSS

**Files:**
- Modify: `files/etc/greetd/gtkgreet.css`

### Overview

Replace the hardcoded dark theme with Adwaita light values. The greeter is pre-user-session so it always uses the default/light theme. Use `ADWAITA["light"]` values directly.

- [ ] **Step 1: Replace `files/etc/greetd/gtkgreet.css` entirely**

```css
window {
    background-color: rgba(250, 250, 250, 0.85);
}

box#body {
    background-color: rgba(240, 240, 240, 0.95);
    border-radius: 12px;
    padding: 32px;
    border: 1px solid rgba(209, 209, 209, 0.8);
}

entry {
    background-color: #ffffff;
    color: #1e1e1e;
    border-radius: 8px;
    padding: 8px 12px;
    border: 1px solid #d1d1d1;
    font-family: "Roboto", sans-serif;
    font-size: 14px;
}

label {
    color: #1e1e1e;
    font-family: "Roboto", sans-serif;
    font-size: 14px;
}

button {
    background-color: #3584e4;
    color: #ffffff;
    border-radius: 999px;
    padding: 8px 24px;
    border: none;
    font-family: "Roboto", sans-serif;
    font-weight: 700;
}

button:hover {
    background-color: #62a0ea;
}

combobox {
    color: #1e1e1e;
    font-family: "Roboto", sans-serif;
}
```

- [ ] **Step 2: Verify the file looks correct**

```bash
head -5 files/etc/greetd/gtkgreet.css
```

Expected: first line is `window {`, background is the light `rgba(250, 250, 250, 0.85)` value.

- [ ] **Step 3: Commit**

```bash
git add files/etc/greetd/gtkgreet.css
git commit -m "fix: replace dark hardcode in gtkgreet.css with Adwaita light theme"
```

---

## Task 6: Static Fallback Files + Defaults

**Files:**
- Modify: `files/usr/share/adwaita-lite/defaults/settings.json`
- Modify: `files/etc/xdg/fuzzel/fuzzel.ini`
- Modify: `files/etc/xdg/swaylock/config`

### Overview

Sync the static fallback files to match what the updated generators now produce. Add the `pinned` array to defaults. The labwc themerc and mako config already match — no changes needed there.

- [ ] **Step 1: Add `pinned` to `defaults/settings.json`**

```json
{
  "edge": "bottom",
  "density": "normal",
  "theme": "light",
  "accent": "blue",
  "layout": {
    "start": ["custom/launcher"],
    "center": ["wlr/taskbar"],
    "end": ["network", "pulseaudio", "backlight", "battery", "clock", "tray"]
  },
  "wallpaper": "/usr/share/backgrounds/adwaita-lite/chrome-dawn.svg",
  "pinned": [
    {"name": "Chrome",  "command": "flatpak run com.google.Chrome", "icon": "com.google.Chrome"},
    {"name": "Bazaar",  "command": "flatpak run dev.bazaar.app",    "icon": "dev.bazaar.app"}
  ]
}
```

- [ ] **Step 2: Add `selection-match` to `files/etc/xdg/fuzzel/fuzzel.ini`**

In the `[colors]` section, add `selection-match=ffffffff` after `selection-text`:

```ini
[main]
font=Roboto:size=12
icons-enabled=yes
terminal=foot
layer=overlay
exit-on-keyboard-focus-loss=yes
width=40
horizontal-pad=16
vertical-pad=12
inner-pad=8

[colors]
background=fafafaff
text=1e1e1eff
match=3584e4ff
selection=3584e4ff
selection-text=ffffffff
selection-match=ffffffff
border=3584e4ff

[border]
width=2
radius=12
```

- [ ] **Step 3: Fix `inside-wrong-color` in `files/etc/xdg/swaylock/config`**

Change `inside-wrong-color=fbe9e7` to `inside-wrong-color=ffffff` to match generated output:

The full file:
```
color=fafafa
indicator-radius=80
show-failed-attempts
indicator-thickness=8
inside-color=ffffff
inside-clear-color=ffffff
inside-ver-color=ffffff
inside-wrong-color=ffffff
key-hl-color=3584e4
bs-hl-color=c01c28
ring-color=3584e4
ring-clear-color=3584e4
ring-ver-color=3584e4
ring-wrong-color=c01c28
line-color=00000000
line-clear-color=00000000
line-ver-color=00000000
line-wrong-color=00000000
separator-color=00000000
text-color=1e1e1e
text-clear-color=1e1e1e
text-ver-color=1e1e1e
text-wrong-color=c01c28
```

- [ ] **Step 4: Verify**

```bash
grep "pinned" files/usr/share/adwaita-lite/defaults/settings.json
grep "selection-match" files/etc/xdg/fuzzel/fuzzel.ini
grep "inside-wrong-color=ffffff" files/etc/xdg/swaylock/config
```

Expected: all three lines found.

- [ ] **Step 5: Commit**

```bash
git add files/usr/share/adwaita-lite/defaults/settings.json \
        files/etc/xdg/fuzzel/fuzzel.ini \
        files/etc/xdg/swaylock/config
git commit -m "feat: add pinned defaults and sync static fallback configs"
```

---

## Task 7: Settings App — Pinned Apps UI

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings`

### Overview

Add a "Pinned apps" subsection at the bottom of the Layout tab. Uses a `Gtk.ListBox` with single selection, ▲/▼ reorder buttons, a Remove button, and an Add button that opens a dialog. Changes apply immediately (save + run apply-settings on every mutation).

- [ ] **Step 1: Initialize `pinned_data` in `__init__`**

In `SettingsWindow.__init__`, after `self.layout_data = self._load_layout()`, add:

```python
        self.pinned_data: list[dict] = self._load_pinned()
```

- [ ] **Step 2: Add `_load_pinned()` method** (place with the other data helpers)

```python
    def _load_pinned(self) -> list[dict]:
        raw = self.settings.get("pinned", [])
        if isinstance(raw, list):
            return [dict(p) for p in raw if isinstance(p, dict)]
        return []
```

- [ ] **Step 3: Add `_save_pinned_and_apply()` method**

```python
    def _save_pinned_and_apply(self) -> None:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        data["pinned"] = [dict(p) for p in self.pinned_data]
        SETTINGS_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        subprocess.run(APPLY_SCRIPT, check=False)
```

- [ ] **Step 4: Add `_build_pinned_section()` and `_populate_pinned_listbox()` methods**

```python
    def _build_pinned_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(16)

        header = Gtk.Label(xalign=0)
        header.set_markup("<b>Pinned apps</b>")
        box.append(header)

        desc = Gtk.Label(label="These appear in the panel before the window list.", xalign=0, wrap=True)
        box.append(desc)

        frame = Gtk.Frame()
        box.append(frame)

        self.pinned_listbox = Gtk.ListBox()
        self.pinned_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        frame.set_child(self.pinned_listbox)
        self._populate_pinned_listbox()

        btn_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.append(btn_bar)

        up_btn = Gtk.Button(label="\u25b2")
        up_btn.set_tooltip_text("Move up")
        up_btn.connect("clicked", self._on_move_pinned_up)
        btn_bar.append(up_btn)

        down_btn = Gtk.Button(label="\u25bc")
        down_btn.set_tooltip_text("Move down")
        down_btn.connect("clicked", self._on_move_pinned_down)
        btn_bar.append(down_btn)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self._on_remove_pinned)
        btn_bar.append(remove_btn)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        btn_bar.append(spacer)

        add_btn = Gtk.Button(label="Add\u2026")
        add_btn.connect("clicked", self._on_add_pinned)
        btn_bar.append(add_btn)

        return box

    def _populate_pinned_listbox(self) -> None:
        while True:
            row = self.pinned_listbox.get_row_at_index(0)
            if row is None:
                break
            self.pinned_listbox.remove(row)
        for app in self.pinned_data:
            label = Gtk.Label(label=app.get("name", app["command"]), xalign=0)
            label.set_margin_start(6)
            label.set_margin_end(6)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            self.pinned_listbox.append(label)
```

- [ ] **Step 5: Add the pinned mutation handlers**

```python
    def _on_move_pinned_up(self, _button: Gtk.Button) -> None:
        row = self.pinned_listbox.get_selected_row()
        if row is None:
            return
        idx = row.get_index()
        if idx == 0:
            return
        self.pinned_data[idx - 1], self.pinned_data[idx] = self.pinned_data[idx], self.pinned_data[idx - 1]
        self._populate_pinned_listbox()
        self.pinned_listbox.select_row(self.pinned_listbox.get_row_at_index(idx - 1))
        self._save_pinned_and_apply()

    def _on_move_pinned_down(self, _button: Gtk.Button) -> None:
        row = self.pinned_listbox.get_selected_row()
        if row is None:
            return
        idx = row.get_index()
        if idx >= len(self.pinned_data) - 1:
            return
        self.pinned_data[idx], self.pinned_data[idx + 1] = self.pinned_data[idx + 1], self.pinned_data[idx]
        self._populate_pinned_listbox()
        self.pinned_listbox.select_row(self.pinned_listbox.get_row_at_index(idx + 1))
        self._save_pinned_and_apply()

    def _on_remove_pinned(self, _button: Gtk.Button) -> None:
        row = self.pinned_listbox.get_selected_row()
        if row is None:
            return
        idx = row.get_index()
        del self.pinned_data[idx]
        self._populate_pinned_listbox()
        self._save_pinned_and_apply()

    def _on_add_pinned(self, _button: Gtk.Button) -> None:
        dialog = Gtk.Dialog(title="Add pinned app", transient_for=self, modal=True)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Add", Gtk.ResponseType.OK)
        dialog.set_default_response(Gtk.ResponseType.OK)

        grid = Gtk.Grid(column_spacing=8, row_spacing=8)
        grid.set_margin_top(16)
        grid.set_margin_bottom(16)
        grid.set_margin_start(16)
        grid.set_margin_end(16)

        name_entry = Gtk.Entry()
        name_entry.set_placeholder_text("Display name (e.g. Chrome)")
        name_entry.set_size_request(300, -1)

        cmd_entry = Gtk.Entry()
        cmd_entry.set_placeholder_text("Command to run (e.g. flatpak run com.google.Chrome)")
        cmd_entry.set_size_request(300, -1)
        cmd_entry.set_activates_default(True)

        icon_entry = Gtk.Entry()
        icon_entry.set_placeholder_text("Icon name (e.g. com.google.Chrome)")
        icon_entry.set_size_request(300, -1)

        for row_idx, (lbl, widget) in enumerate([
            ("Name", name_entry),
            ("Command", cmd_entry),
            ("Icon", icon_entry),
        ]):
            grid.attach(Gtk.Label(label=lbl, xalign=0), 0, row_idx, 1, 1)
            grid.attach(widget, 1, row_idx, 1, 1)

        dialog.get_content_area().append(grid)
        dialog.connect("response", self._on_add_pinned_response, name_entry, cmd_entry, icon_entry)
        dialog.present()

    def _on_add_pinned_response(
        self,
        dialog: Gtk.Dialog,
        response: int,
        name_entry: Gtk.Entry,
        cmd_entry: Gtk.Entry,
        icon_entry: Gtk.Entry,
    ) -> None:
        if response == Gtk.ResponseType.OK:
            cmd = cmd_entry.get_text().strip()
            if cmd:
                name = name_entry.get_text().strip() or cmd.split()[-1]
                icon = icon_entry.get_text().strip() or "application-x-executable"
                self.pinned_data.append({"name": name, "command": cmd, "icon": icon})
                self._populate_pinned_listbox()
                self._save_pinned_and_apply()
        dialog.destroy()
```

- [ ] **Step 6: Append the pinned section to `_build_layout_tab()`**

In `_build_layout_tab()`, after the `reset_button` block and before `return outer`, add:

```python
        pinned_section = self._build_pinned_section()
        outer.append(pinned_section)
```

- [ ] **Step 7: Update `on_apply()` to include `pinned_data`**

In the `on_apply()` method, update the `payload` dict:

```python
        payload = {
            "edge": edge,
            "density": density,
            "theme": theme,
            "accent": accent,
            "wallpaper": wallpaper,
            "layout": {k: list(v) for k, v in self.layout_data.items()},
            "pinned": [dict(p) for p in self.pinned_data],
        }
```

- [ ] **Step 8: Verify — launch the settings app**

```bash
python3 files/usr/bin/adwaita-lite-settings
```

In the Layout tab: confirm "Pinned apps" section appears at the bottom with Chrome and Bazaar listed (if defaults were applied). Click Add…, enter `Command: foot`, click Add. Confirm foot appears in list and apply-settings runs. Check `~/.config/waybar/config.jsonc` for `custom/pin-2` or similar.

- [ ] **Step 9: Commit**

```bash
git add files/usr/bin/adwaita-lite-settings
git commit -m "feat: add pinned apps UI to settings app Layout tab"
```

---

## Post-Implementation Push

- [ ] **Push all commits**

```bash
git push
```

Expected: CI build triggers.

---

## Spec Coverage Check

| Spec Section | Covered by Task |
|---|---|
| Token system (`_build_tokens`) | Task 1 |
| `ensure_settings()` pinned validation | Task 1 |
| `write_waybar_config()` icon-only modules | Task 2 |
| Pinned launcher generation (`custom/pin-N`) | Task 2 |
| Orientation-aware CSS (horizontal vs vertical) | Task 2 |
| `border_strong` dark mode fix | Task 1 (`_build_tokens`) |
| `write_fuzzel_config()` missing fields | Task 3 |
| `write_mako_config()` missing fields + anchor | Task 3 |
| `write_foot_config()` pad | Task 3 |
| `write_swaylock_config()` missing fields | Task 4 |
| `write_labwc_themerc()` menu border | Task 4 |
| gtkgreet.css Adwaita light | Task 5 |
| `defaults/settings.json` pinned array | Task 6 |
| Static fallback sync | Task 6 |
| Settings app pinned apps UI | Task 7 |
| Settings app Add dialog | Task 7 |
| Settings app reorder + remove | Task 7 |
