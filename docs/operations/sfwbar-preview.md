# sfwbar preview

**Status:** prototype. Waybar remains the default panel; nothing in the
session selects sfwbar automatically.

This branch adds the Fedora `sfwbar` package to the image and a generator that
renders `sfwbar.config` + `sfwbar.css` from the existing Adwaita-Lite settings.
It exists for a side-by-side comparison before any default changes.

## Why sfwbar

| Requirement | sfwbar 1.0~beta16.1 (Fedora 44) |
|---|---|
| License | GPL-3.0-only + MIT, shipped as a separate program |
| Edge / margin / layer / exclusive zone | yes, via `layout` bar properties + CSS |
| Start / center / end sections | yes (`layout "sfwbar"`, `"sfwbar:center"`, `"sfwbar:end"`) |
| Taskbar | ungrouped icon taskbar with output filtering and window actions |
| Tray | status-notifier tray |
| Clock / volume / backlight / battery | clock, PulseAudio, sysfs, sysfs scanners |
| Theming | GTK3 CSS, the same stack Waybar already uses |
| Live reload | `killall -SIGHUP sfwbar` |
| Launcher | executes the internal `adwaita-lite-app-menu` |
| Multi-monitor | `monitor` / `mirror` patterns |

The app grid, power bar, categories and search stay in the internal
`adwaita-lite-app-menu`; sfwbar's own start menu is not used.

## Design

The generator follows the current Waybar token contract:

- Floating bottom pill by default, `8 × scale` margin, `4 × scale` inset,
  999px radius, 1px border, 0.90 surface alpha, no shadow.
- Normal/compact sizes: 48/40 horizontal, 64/48 vertical, 24/16 icons,
  8/6 spacing, module padding 8, launcher padding 12, pinned padding 8.
- Adwaita palette, accent, high contrast (wins over twilight), twilight,
  font size, 12/24h clock, reduce-motion.
- `layout` start/center/end sections, launcher, pinned buttons, ungrouped
  icon taskbar, one status capsule per contiguous status run, separate tray.
- Active window indicator: 3px accent on the panel's screen-facing edge
  (matching the Waybar CSS: top→top, bottom→bottom, left→left, right→right).
- Taskbar: left click `TaskbarItemDefault()` (minimize/raise), middle click
  `Close()`, tooltips, `filter = output`.
- Volume: mute-aware icon, tooltip percentage, scroll ±5, click `pavucontrol`.
- Backlight and battery hide themselves when no device is present.
- Vertical bars flow center modules after start; sfwbar's GtkBox center widget
  otherwise stretches a lone taskbar item to the full free height. Vertical
  12h clocks use two fixed labels (`05:43` / `PM`) so the text cannot overflow
  the narrow bar.

No network module, no taskbar grouping, no extra modules or feature creep.

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

# Launch a preview (stops Waybar if requested)
adwaita-lite-panel preview --replace-waybar

# Re-render the preview assets and SIGHUP the running sfwbar
adwaita-lite-panel apply

# Return to Waybar
adwaita-lite-panel restore
```

## Lab evidence

Environment: Fedora 44 container, sway 1.11 headless at 1280×720, sfwbar
`1.0~beta16.1-3.fc44`, Adwaita icon theme, Roboto. This is a rendering and
protocol check, **not** the 2 GB hardware gate.

Verified:

- Config and CSS parse with no sfwbar errors for light, dark, compact,
  large-font, high-contrast, twilight, top, left, right and pinned/24h
  variants.
- Floating pill geometry, 8px margins, exclusive zone, and transparent
  corners render correctly.
- Ungrouped taskbar: one item per window, icon-only, tooltip, focused
  indicator, output filtering; `TaskbarItemDefault()` and `Close()` parse.
- SIGHUP reload keeps the bar, taskbar and status widgets and does not
  duplicate them.
- Restarting sfwbar with windows already open repopulates the taskbar.
- Pinned buttons launch the stored commands and preserve quoting.
- Volume and clock render in one status capsule; backlight and battery hide
  without hardware.
- Preview isolation works: the user's `~/.config/sfwbar` is not created or
  modified.

Idle RSS in the lab (same session, one foot window, 1280×720):

| Program | RSS |
|---|---|
| Waybar 0.5.x (generated Adwaita-Lite config) | ~55.7 MB |
| sfwbar 1.0~beta16.1 | ~36.7 MB |

Startup time was not measured reliably in the container.

### Known deviations and gaps

- **Floating vs edge-to-edge:** the Waybar CSS margin does not produce a
  floating panel in practice; the real Waybar bar is edge-to-edge. The
  sfwbar prototype intentionally keeps the documented floating-pill contract.
  This is a visible design change, not pixel parity, and needs an explicit
  product decision before the default flips.
- An empty tray renders an empty sfwbar pod; Waybar hides an empty tray.
  beta16.1 has no tray-count expression to hide it cleanly.
- The Waybar vertical active indicator is a crescent (border on the icon);
  sfwbar's is also a crescent via the button border. Both differ from a
  straight 3px line.
- sfwbar's `tooltips` taskbar property does not exist in beta16.1; tooltip
  behaviour is the taskbar default.
- GTK theme `background-image` must be reset explicitly (`background:`), or
  Adwaita's button gradient paints over the pods.
- Accessibility (Orca, keyboard focus rings), tray menus, real
  volume/brightness hardware, multi-monitor mirroring, and startup cost are
  not measured.
- No `panel_backend` setting yet. The session still starts Waybar.

## Comparison gate

Do not change the default panel until the following pass on the 2 GB labwc
target (VM or hardware):

1. Generated assets parse without warnings; no duplicate bars after SIGHUP.
2. Screenshots at light/dark/HC/twilight and top/bottom/left/right match the
   agreed contract, with the floating-pill deviation explicitly approved.
3. Taskbar: one item per window, no grouping, focus/minimize/close, output
   filtering, active indicator, tooltip.
4. Pinned buttons launch exact commands; no shell re-quoting bugs.
5. Volume/backlight/battery/clock behaviour and tooltips on real hardware.
6. Tray icons, menus, and the empty-tray case.
7. Launcher button and Super+Space open the internal app menu.
8. Idle RSS, startup time, and idle CPU are not worse than Waybar beyond
   noise; a resource regression vetoes the migration.
9. Orca and keyboard-only operation are at least as good as Waybar.

## License

sfwbar is GPL-3.0-only (plus MIT weather icons) and is shipped as a separate
program. The generated Adwaita-Lite config/CSS is GPL-3.0-or-later like the
rest of this repository.
