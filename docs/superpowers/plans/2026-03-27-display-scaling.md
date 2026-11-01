# Display Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Display tab to the settings app with a scale dropdown (75%–250%), immediate wlr-randr apply, 15-second revert dialog, and session-start persistence via autostart.

**Architecture:** `settings.json` is the single source of truth — `apply-settings` validates/persists, the settings app drives `wlr-randr` directly for live preview, and `autostart` re-applies scale at session start. No XML manipulation; no changes to labwc rc.xml.

**Tech Stack:** Python 3, GTK4 (gi.repository), GLib.timeout_add, wlr-randr CLI, POSIX shell (autostart)

---

### Task 1: Add `wlr-randr` package and `scale` default

**Files:**
- Modify: `build_files/build.sh`
- Modify: `files/usr/share/adwaita-lite/defaults/settings.json`

- [ ] **Step 1: Add wlr-randr to dnf5 install list**

In `build_files/build.sh`, add `wlr-randr \` on the line after `waybar \` (line 68):

```bash
    waybar \
    wlr-randr \
```

- [ ] **Step 2: Add scale to the defaults file**

Replace the contents of `files/usr/share/adwaita-lite/defaults/settings.json`:

```json
{
  "edge": "bottom",
  "density": "normal",
  "theme": "light",
  "accent": "blue",
  "scale": 1.0,
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

- [ ] **Step 3: Commit**

```bash
git add build_files/build.sh files/usr/share/adwaita-lite/defaults/settings.json
git commit -m "feat: add wlr-randr dep and scale default to settings schema"
```

---

### Task 2: Validate and persist `scale` in apply-settings

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add VALID_SCALE constant**

In `files/usr/libexec/adwaita-lite-apply-settings`, after the `VALID_ACCENT` line (line 33), add:

```python
VALID_SCALE = {0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5}
```

- [ ] **Step 2: Add scale validation in ensure_settings()**

In `ensure_settings()`, after the `accent` validation block (after `if accent not in VALID_ACCENT: accent = "blue"`), add:

```python
    scale = data.get("scale", 1.0)
    if scale not in VALID_SCALE:
        scale = 1.0
```

Then add `"scale": scale,` to the `normalized` dict (after `"accent": accent,`):

```python
    normalized = {
        "edge": edge,
        "density": density,
        "theme": theme,
        "wallpaper": wallpaper,
        "accent": accent,
        "scale": scale,
        "layout": layout,
        "pinned": pinned,
    }
```

- [ ] **Step 3: Pass scale through _build_tokens()**

In `_build_tokens()`, the `return { **settings, ... }` already spreads all of `settings` into tokens — since `scale` is now in `settings`, it will be passed through automatically. No change needed here. Verify by checking that the return starts with `**settings`.

- [ ] **Step 4: Verify manually**

```bash
cd /var/home/race/ublue-mike
python3 -c "
import sys; sys.path.insert(0, 'files/usr/libexec')
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location('apply', 'files/usr/libexec/adwaita-lite-apply-settings')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
# Valid scale passes through
assert 1.5 in m.VALID_SCALE
assert 0.75 in m.VALID_SCALE
assert 2.5 in m.VALID_SCALE
assert 3.0 not in m.VALID_SCALE
print('VALID_SCALE OK')
"
```

Expected output: `VALID_SCALE OK`

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: add scale validation and persistence to apply-settings"
```

---

### Task 3: Add session-start scale apply to autostart

**Files:**
- Modify: `files/etc/xdg/labwc/autostart`

- [ ] **Step 1: Add scale apply block after wallpaper line**

In `files/etc/xdg/labwc/autostart`, after the wallpaper line (`[ -n "$_wallpaper" ] && swaybg ...`) and before the `waybar` line, insert:

```sh
# Apply display scale to all active outputs (no-op at default 1.0).
_scale=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('scale', 1.0))" "$_settings" 2>/dev/null || echo "1.0")
if [ "$_scale" != "1.0" ]; then
    wlr-randr | awk '/^[A-Za-z]/{print $1}' | while IFS= read -r _out; do
        wlr-randr --output "$_out" --scale "$_scale" 2>/dev/null || true
    done
fi
```

The full updated UL-gated section should read:

```sh
# Only start Adwaita-Lite daemons in a Adwaita-Lite session.
[ "${ADWAITA_LITE:-}" = "1" ] || exit 0

# Read wallpaper path from user settings and start the wallpaper daemon.
_settings="${XDG_CONFIG_HOME:-$HOME/.config}/adwaita-lite/settings.json"
_wallpaper=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('wallpaper',''))" "$_settings" 2>/dev/null || true)
[ -n "$_wallpaper" ] && swaybg -i "$_wallpaper" -m fill >/dev/null 2>&1 &

# Apply display scale to all active outputs (no-op at default 1.0).
_scale=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('scale', 1.0))" "$_settings" 2>/dev/null || echo "1.0")
if [ "$_scale" != "1.0" ]; then
    wlr-randr | awk '/^[A-Za-z]/{print $1}' | while IFS= read -r _out; do
        wlr-randr --output "$_out" --scale "$_scale" 2>/dev/null || true
    done
fi

waybar >/dev/null 2>&1 &
mako >/dev/null 2>&1 &
pgrep -x nm-applet  >/dev/null 2>&1 || nm-applet --indicator >/dev/null 2>&1 &
pgrep -x xfce-polkit >/dev/null 2>&1 || xfce-polkit >/dev/null 2>&1 &
swayidle -w \
  timeout 300  'swaylock -f' \
  timeout 600  'wlopm --off "*"' resume 'wlopm --on "*"' \
  before-sleep 'swaylock -f' \
  >/dev/null 2>&1 &
pgrep -x Thunar >/dev/null 2>&1 || Thunar --daemon >/dev/null 2>&1 &
```

- [ ] **Step 2: Commit**

```bash
git add files/etc/xdg/labwc/autostart
git commit -m "feat: apply display scale at session start via autostart"
```

---

### Task 4: Add Display tab to settings app

**Files:**
- Modify: `files/usr/bin/adwaita-lite-settings`

This task adds the Display tab, scale dropdown, wlr-randr helper, revert dialog, and wires everything up.

- [ ] **Step 1: Add GLib import**

At the top of `files/usr/bin/adwaita-lite-settings`, after the `gi.require_version("Gtk", "4.0")` line, add:

```python
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gtk  # noqa: E402
```

Replace the existing `from gi.repository import Gtk` line with the above.

- [ ] **Step 2: Add SCALE_OPTIONS constant**

After the `SECTION_ORDER` constant (line 47), add:

```python
SCALE_OPTIONS = ["75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%"]
SCALE_VALUES = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]
```

- [ ] **Step 3: Add _apply_scale() helper method**

In the `SettingsWindow` class, add this method after `_set_dropdown()` (around line 545):

```python
def _apply_scale(self, scale: float) -> None:
    """Apply scale to all active wlr-output-management outputs. Silent on failure."""
    result = subprocess.run(
        ["wlr-randr"], capture_output=True, text=True, check=False
    )
    outputs = [
        line.split()[0]
        for line in result.stdout.splitlines()
        if line and not line[0].isspace()
    ]
    for output in outputs:
        subprocess.run(
            ["wlr-randr", "--output", output, "--scale", str(scale)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
```

- [ ] **Step 4: Add on_apply_scale() with revert dialog**

Add this method after `_apply_scale()`:

```python
def on_apply_scale(self, _button: Gtk.Button) -> None:
    selected = self.scale.get_selected()
    new_scale = SCALE_VALUES[selected]
    prev_scale = self.settings.get("scale", 1.0)

    if new_scale == prev_scale:
        self.scale_status.set_text("No change.")
        return

    self._apply_scale(new_scale)

    # --- Revert dialog ---
    dialog = Gtk.Window(title="Keep this display scale?", modal=True, transient_for=self)
    dialog.set_default_size(320, -1)
    dialog.set_resizable(False)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_margin_top(20)
    box.set_margin_bottom(20)
    box.set_margin_start(20)
    box.set_margin_end(20)
    dialog.set_child(box)

    countdown_label = Gtk.Label(label="Reverting in 15 seconds\u2026", xalign=0)
    box.append(countdown_label)

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
    box.append(btn_box)

    revert_btn = Gtk.Button(label="Revert")
    keep_btn = Gtk.Button(label="Keep Settings")
    keep_btn.add_css_class("suggested-action")
    btn_box.append(revert_btn)
    btn_box.append(keep_btn)

    remaining = [15]
    timer_id = [0]

    def _revert(_widget=None):
        if timer_id[0]:
            GLib.source_remove(timer_id[0])
            timer_id[0] = 0
        self._apply_scale(prev_scale)
        self._set_scale_dropdown(prev_scale)
        self.scale_status.set_text("Reverted.")
        dialog.destroy()

    def _keep(_widget=None):
        if timer_id[0]:
            GLib.source_remove(timer_id[0])
            timer_id[0] = 0
        self.settings["scale"] = new_scale
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        payload["scale"] = new_scale
        SETTINGS_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        subprocess.run(APPLY_SCRIPT, check=False)
        self.scale_status.set_text("Applied.")
        dialog.destroy()

    def _tick():
        remaining[0] -= 1
        if remaining[0] <= 0:
            timer_id[0] = 0
            _revert()
            return GLib.SOURCE_REMOVE
        countdown_label.set_text(f"Reverting in {remaining[0]} seconds\u2026")
        return GLib.SOURCE_CONTINUE

    timer_id[0] = GLib.timeout_add(1000, _tick)
    revert_btn.connect("clicked", _revert)
    keep_btn.connect("clicked", _keep)
    dialog.connect("close-request", lambda _: _revert() or False)
    dialog.present()
```

- [ ] **Step 5: Add _set_scale_dropdown() helper**

Add this method alongside `_set_dropdown()`:

```python
def _set_scale_dropdown(self, scale: float) -> None:
    try:
        idx = SCALE_VALUES.index(scale)
    except ValueError:
        idx = SCALE_VALUES.index(1.0)
    self.scale.set_selected(idx)
```

- [ ] **Step 6: Add _build_display_tab() method**

Add this method after `_build_appearance_tab()`:

```python
def _build_display_tab(self) -> Gtk.Widget:
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
    outer.set_margin_top(20)
    outer.set_margin_bottom(20)
    outer.set_margin_start(20)
    outer.set_margin_end(20)

    title = Gtk.Label(xalign=0)
    title.set_markup("<span size='x-large' weight='bold'>Display</span>")
    outer.append(title)

    subtitle = Gtk.Label(xalign=0, wrap=True)
    subtitle.set_text(
        "Set the display scale. A preview is shown immediately — "
        "confirm within 15 seconds or the change will be reverted."
    )
    outer.append(subtitle)

    grid = Gtk.Grid(column_spacing=12, row_spacing=12)
    outer.append(grid)

    self.scale = Gtk.DropDown.new_from_strings(SCALE_OPTIONS)
    self._set_scale_dropdown(self.settings.get("scale", 1.0))

    apply_btn = Gtk.Button(label="Apply")
    apply_btn.connect("clicked", self.on_apply_scale)

    self.scale_status = Gtk.Label(xalign=0)

    grid.attach(Gtk.Label(label="Display scale", xalign=0), 0, 0, 1, 1)
    grid.attach(self.scale, 1, 0, 1, 1)
    grid.attach(apply_btn, 1, 1, 1, 1)
    grid.attach(self.scale_status, 0, 2, 2, 1)

    return outer
```

- [ ] **Step 7: Register the Display tab in __init__**

In `SettingsWindow.__init__()`, after the Layout tab lines:

```python
        # -- Display tab --
        display_page = self._build_display_tab()
        notebook.append_page(display_page, Gtk.Label(label="Display"))
```

- [ ] **Step 8: Include scale in the Appearance Apply payload**

In `on_apply()`, the payload must include the current scale so it isn't lost when the user applies appearance changes. Update the payload dict:

```python
        payload = {
            "edge": edge,
            "density": density,
            "theme": theme,
            "accent": accent,
            "wallpaper": wallpaper,
            "scale": self.settings.get("scale", 1.0),
            "layout": {k: list(v) for k, v in self.layout_data.items()},
            "pinned": [dict(p) for p in self.pinned_data],
        }
```

- [ ] **Step 9: Smoke-test the import**

```bash
cd /var/home/race/ublue-mike
python3 -c "
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('GLib', '2.0')
from gi.repository import GLib, Gtk
print('GTK4 + GLib import OK')
"
```

Expected: `GTK4 + GLib import OK`

- [ ] **Step 10: Commit**

```bash
git add files/usr/bin/adwaita-lite-settings
git commit -m "feat: add Display tab with scale dropdown and revert dialog"
```

---

### Task 5: Code review and push

- [ ] **Step 1: Run spec compliance review**

Use `superpowers:requesting-code-review` to review the implementation against the spec at `docs/superpowers/specs/2026-03-27-display-scaling-design.md`. Check:

- `VALID_SCALE` constant present and correct values
- `ensure_settings()` validates scale with fallback to 1.0
- `_build_tokens()` passes scale through (via `**settings` spread)
- Display tab renders with `Gtk.DropDown` using SCALE_OPTIONS
- `on_apply_scale()` calls `_apply_scale()` before showing dialog
- Revert path calls `_apply_scale(prev_scale)` and resets dropdown
- Keep path writes `scale` to settings.json and calls apply-settings
- `on_apply()` includes `scale` in payload so appearance Apply doesn't erase scale
- autostart block reads scale and calls wlr-randr only when scale != 1.0
- `wlr-randr` added to dnf5 install in build.sh

- [ ] **Step 2: Push**

```bash
git push
```
