# Display Scaling — Design Spec

**Date:** 2026-03-27
**Status:** Approved

## Overview

Add a Display Scale control to the Adwaita-Lite settings app so users can change the compositor output scale (75%–250%) with immediate live preview and a revert dialog.

## Scope

Display scale only (compositor output scale via `wlr-randr`). Text/font scaling and cursor size are explicitly out of scope — those can be controlled via dconf by users who need them. Cursor sizing in Wayland is automatic at the compositor level once output scale is set.

## Data Model

### settings.json

New key added to the schema:

```json
{ "scale": 1.0 }
```

- Type: float
- Default: `1.0`
- Valid values: `{0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5}` (75%–250% in 25% steps)
- Falls back to `1.0` if missing or invalid

### apply-settings

Three additions only — no structural changes:

1. `VALID_SCALE = {0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5}` constant alongside existing `VALID_EDGES` etc.
2. `ensure_settings()` reads `data.get("scale", 1.0)`, validates against `VALID_SCALE`, falls back to `1.0`, adds `"scale": scale` to `normalized`
3. `_build_tokens()` passes `"scale": settings["scale"]` through (no existing `write_*` function consumes it — compositor scale handles physical sizing automatically)

`apply-settings` does **not** call `wlr-randr`. It is purely the validation and persistence layer for scale.

## Settings App UI

### New "Display" tab

A new tab added alongside Appearance and Layout containing a single control:

| Label | Widget | Values |
|---|---|---|
| Display scale | `Gtk.DropDown` | "75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%" |

Uses `Gtk.DropDown.new_from_strings(...)` consistent with the existing edge/density/theme/accent controls. Strings map to floats: `{"75%": 0.75, "100%": 1.0, …, "250%": 2.5}`.

The Display tab has its own **Apply** button that only triggers the scale flow — it does not re-apply theme/waybar/etc.

### Live-apply + revert flow

When the user clicks Apply on the Display tab:

1. Record `prev_scale` (current active scale)
2. Call `wlr-randr` to apply the new scale to all active outputs immediately
3. Show a modal revert dialog:
   - Title: "Keep this display scale?"
   - Body: "Reverting in 15 seconds…" (countdown label updated every second via `GLib.timeout_add`)
   - Buttons: **Keep Settings** / **Revert**
4. **Keep**: write settings.json (call `apply-settings`), close dialog
5. **Revert** or 15s timeout: call `wlr-randr` to restore `prev_scale`, reset dropdown to `prev_scale`, close dialog — settings.json is not written

### wlr-randr calls from the settings app

Output enumeration:
```python
result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=False)
outputs = [line.split()[0] for line in result.stdout.splitlines()
           if line and not line[0].isspace()]
```

Apply scale:
```python
for output in outputs:
    subprocess.run(["wlr-randr", "--output", output, "--scale", str(scale)],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
```

Failures are silenced — environments without `wlr-output-management` support (e.g. some VMs) get a no-op rather than a crash.

## Session-Start Apply (autostart)

Added to the `ADWAITA_LITE=1` gated block of `/etc/xdg/labwc/autostart`, after the wallpaper line:

```sh
_scale=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('scale', 1.0))" "$_settings" 2>/dev/null || echo "1.0")
if [ "$_scale" != "1.0" ]; then
    wlr-randr | awk '/^[A-Za-z]/{print $1}' | while IFS= read -r _out; do
        wlr-randr --output "$_out" --scale "$_scale" 2>/dev/null || true
    done
fi
```

Skips all wlr-randr calls at `1.0` (default — no-op). Tolerates failures silently.

## Package Dependency

`wlr-randr` must be added to the `dnf5 install` list in `build_files/build.sh`.

## Files Changed

| File | Change |
|---|---|
| `files/usr/libexec/adwaita-lite-apply-settings` | Add `VALID_SCALE`, scale validation in `ensure_settings()`, pass through in `_build_tokens()` |
| `files/usr/bin/adwaita-lite-settings` | Add Display tab, scale dropdown, revert dialog logic |
| `files/usr/share/adwaita-lite/defaults/settings.json` | Add `"scale": 1.0` |
| `files/etc/xdg/labwc/autostart` | Add session-start wlr-randr apply block |
| `build_files/build.sh` | Add `wlr-randr` to dnf5 install |
