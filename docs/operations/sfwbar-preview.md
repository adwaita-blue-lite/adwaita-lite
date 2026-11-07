# sfwbar preview

**Status:** prototype. Waybar remains the default panel; nothing in the
session selects sfwbar automatically.

This branch adds the Fedora `sfwbar` package to the image and a generator that
renders `sfwbar.config` + `sfwbar.css` from the existing Adwaita-Lite settings.
It exists for a side-by-side comparison before any default changes.

## Design direction

The panel is a **ChromeOS shelf built from Adwaita material**:

- ChromeOS supplies structure: an edge-to-edge system bar, launcher at the
  leading edge, app strip, status area at the trailing edge, 48dp targets and
  16dp screen-edge padding.
- Adwaita supplies material: rounded rectangles, palette semantics,
  Adwaita Sans, restrained hover/pressed states, reduced motion, high-contrast
  behaviour.

The default shelf is **edge-to-edge**. A floating variant remains available
with `--float` for a future tablet/touch presentation; it is not the laptop
default.

### Metrics

| Element | Normal | Compact |
|---|---|---|
| Bar thickness | 48px | 40px |
| Vertical bar width | 64px | 48px |
| App / pinned / task tile | 48×48, r12 | 40×40, r10 |
| App glyph | 32px | 24px |
| Launcher | 48×48, r999, 24px glyph | 40×40, r999, 20px glyph |
| Status button | 40×48, r12, 20px glyph | 40×40, r10, 16px glyph |
| Clock | 13px / 500, 58px min + 10px pad | 12px / 500, 52px min + 8px pad |
| Edge inset | 16px | 16px |
| App gap | 4px | 2px |
| Status gap | 2px | 2px |

The launcher is the only circular control. The bar is square, app/status
targets are rounded rectangles, and the status area has no monolithic capsule.

### States

- Hover: foreground at 8%.
- Pressed: foreground at 16%.
- Focused window: accent at 12% fill plus a 3px accent bar on the screen-facing
  edge, drawn with an inset `box-shadow` so it does not curve around a pill.
- Urgent: static warning fill and 1px warning border; never blinking.
- Keyboard focus: visible ring on the launcher/pinned controls only. Keyboard
  reachability of taskbar items is unverified, so no focus ring is claimed for
  them.
- Running indicator: intentionally **not shipped** while the taskbar is
  ungrouped (one button per window). A ChromeOS-style app dot only becomes
  meaningful with app-centric grouping, which is the next gated wave.

### Layout

- `start`: launcher, pinned buttons, taskbar.
- `center`: empty, so the app strip stays at the leading edge instead of
  looking like a centered dock.
- `end`: tray, network, volume, battery, clock.
- The stored `layout` default still describes the Waybar panel. The sfwbar
  preview detects that legacy default and renders the shelf layout; a
  user-customised layout is honoured unchanged. This keeps the Waybar default
  stable until a proper `panel_backend` setting exists.
- Backlight is not in the default shelf (brightness keys already exist in the
  image and ChromeOS keeps brightness out of the shelf). It remains available
  if the layout explicitly includes it.
- The network indicator is passive: icon and tooltip only, no click target.

### Typography and motion

- Font stack: `"Adwaita Sans", "Inter", "Roboto", sans-serif`.
- Clock 500 weight, tabular figures; no 700-weight text.
- 120ms transitions for background/shadow only; `none` under reduce-motion or
  high contrast.
- High contrast is fully opaque with stronger borders; twilight uses the
  opposite palette.
- Tooltips use the card surface, 8px radius, 6×8 padding.

## Architecture

`adwaita-lite-panel` (installed at `/usr/bin/adwaita-lite-panel`) reads
`~/.config/adwaita-lite/settings.json` with the image defaults as fallback and
writes:

```
<XDG_RUNTIME_DIR>/adwaita-lite/sfwbar-preview/home/sfwbar/sfwbar.config
<XDG_RUNTIME_DIR>/adwaita-lite/sfwbar-preview/home/sfwbar/sfwbar.css
```

The preview uses an isolated `XDG_CONFIG_HOME` so it cannot clobber a user's
`~/.config/sfwbar`. Other top-level config entries (`gtk-3.0`, fonts) are
symlinked into that home so GTK settings and fontconfig still apply.

### Why not `-f` / `-c`

Fedora 44 ships `sfwbar-1.0~beta16.1-3.fc44`. Its `main` passes the original
`argv` to `g_application_run()` after `parse_command_line()` has already
copied the options, so `sfwbar -f … -c …` fails at runtime with
`Unknown option -f`, even though `--help` lists the flags. The preview
therefore relies on sfwbar's default config discovery and sets
`XDG_CONFIG_HOME` for the launched process only.

The packaged build also rejects a top-level `bar { … }` block; bar properties
must live inside a `layout "sfwbar" { … }` block. `size` is a string, `margin`
is a number, `layer` is a string, and the bar edge is set through the
`-GtkWidget-direction` CSS property on `window`. All of these were verified
against the packaged binary, not the upstream main docs.

### Commands

```bash
# Generate without launching
adwaita-lite-panel generate --output-dir /tmp/sfwbar-preview

# Launch the edge-to-edge shelf (stops Waybar if requested)
adwaita-lite-panel preview --replace-waybar

# Launch the opt-in floating shelf
adwaita-lite-panel preview --replace-waybar --float

# Re-render the preview assets and SIGHUP the running sfwbar
adwaita-lite-panel apply [--float]

# Return to Waybar
adwaita-lite-panel restore
```

## Lab evidence

Environment: Fedora 44 container, sway 1.11 headless at 1280×720, sfwbar
`1.0~beta16.1-3.fc44`, Adwaita icon theme, Adwaita Sans. This is a rendering
and protocol check, **not** the 2 GB hardware gate.

Verified:

- Config and CSS parse with no sfwbar or GTK warnings for light, dark,
  compact, high-contrast, twilight, top, left, right, 24h, pinned,
  backlight-opt-in and floating variants.
- Edge-to-edge shelf measures exactly 48/40 px with a 1px separator; the
  floating variant keeps 8px margins, 16px radius and 0.90 alpha.
- 32px app icons, 24px launcher, 20px status icons; compact 24/20/16.
- Focused tile uses accent fill plus the screen-facing 3px bar; hover on an
  unfocused tile shows the 8% fill.
- Network indicator renders from `NetInfo`/`NetStat` with wired and wireless
  icon states and a passive tooltip expression.
- Empty tray renders without a visible pod.
- Vertical left/right shelves measure 64px wide, center their 48px tiles, and
  pin the status area to the bottom with 16px inset.
- SIGHUP reload and restart repopulate the taskbar without duplicate bars.
- `fc-match "Adwaita Sans"` resolves to `AdwaitaSans-Regular.ttf`.
- Preview isolation works: the user's `~/.config/sfwbar` is not created or
  modified.

Idle RSS in the lab (same session, one foot window, 1280×720):

| Program | RSS |
|---|---|
| Waybar (generated Adwaita-Lite config) | ~55.7 MB |
| sfwbar shelf | ~38.2 MB |

Startup time was not measured reliably in the container.

### Known deviations and gaps

- **No app-centric grouping yet.** The taskbar is still one button per window,
  so a pinned app can appear twice when running. `group = popup` + validated
  app-id pins is Wave 2; it needs an exact-command migration and a keyboard
  popup check before it can ship.
- No running dot until grouping lands; a dot on per-window buttons would
  misrepresent the model.
- Compact targets are 40px, below the 48dp touch recommendation. Compact is a
  pointer-oriented density for this laptop target; it is not a touch mode.
- Keyboard focus/navigation of shelf items and group popups is unverified.
  The launcher grid remains the guaranteed keyboard path.
- Auto-hide, quick settings, interactive network controls, blur and dynamic
  badges are out of scope.
- The settings layout editor still targets the Waybar panel; the sfwbar preview
  uses the shelf layout when the stored layout is the legacy default. A
  `panel_backend` setting should replace this heuristic.
- Backlight is opt-in rather than default; verify brightness keys on the target
  before removing it permanently.

## Comparison gate

Do not change the default panel until the following pass on the 2 GB labwc
target (VM or hardware):

1. Generated assets parse without warnings; no duplicate bars after SIGHUP.
2. Screenshots at light/dark/HC/twilight, normal/compact, and all four edges
   match the agreed shelf contract.
3. Taskbar focus/minimize/close, output filtering, pinned commands and the
   hover/pressed/focused states behave correctly.
4. Network icon states and volume/battery/clock behaviour on real hardware.
5. Tray icons, menus, and the empty-tray case.
6. Launcher button and Super+Space open the internal app menu.
7. Idle RSS, startup time, and idle CPU are not worse than Waybar beyond
   noise; a resource regression vetoes the migration.
8. Orca and keyboard-only operation are at least as good as Waybar.
9. Wave 2 grouping: one tile per app, pinned/running merge, popup keyboard
   reach, and exact-command equivalence for every migrated pin.

## License

sfwbar is GPL-3.0-only (plus MIT weather icons) and is shipped as a separate
program. The generated Adwaita-Lite config/CSS is GPL-3.0-or-later like the
rest of this repository.
