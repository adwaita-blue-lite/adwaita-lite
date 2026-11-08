# Native GTK4 Panel Design

**Status:** implemented through Wave 3 (PRs #13–#20). Wave 6 cutover is on
hold: the 2 GB VM gate found that the published image is unbootable because
the image-build `dracut` step failed and was masked by `|| true`. See
[`docs/operations/gtk4-panel-vm-gate.md`](../../operations/gtk4-panel-vm-gate.md)
for the checkpoint and fix plan.

## Current status (2026-11-08)

| Area | State |
|---|---|
| Shelf, four edges, density, themes, HC/twilight | implemented |
| App-centric taskbar, pins, window list | implemented |
| Clock/popups, keyboard focus, outside dismiss | implemented |
| Battery, volume, backlight, passive network | implemented |
| Image integration + `panel_backend` dispatcher | merged; Waybar default |
| SNI tray | not implemented |
| Per-output task filtering, layout ordering | not implemented |
| Orca/AT-SPI verification | not done |
| 2 GB VM gate | **blocked — image initramfs is broken** |

The blocker is not the panel. `build_files/build.sh` runs `dracut` to
regenerate `/usr/lib/modules/$kver/initramfs.img`; that command fails
(`dracut-install: ERROR: installing '/root'`) and `|| true` lets the image
publish. The deployed initramfs is missing the `ostree` and `bootc` dracut
modules, so `initrd-switch-root` fails before the panel can run. Fix the
initramfs build, add a presence check, republish, then resume the gate.

## Context

Adwaita-Lite currently runs Waybar by default, with an sfwbar preview backend added in PR #12 and a ChromeOS/Adwaita shelf redesign in PR #13. Both are third-party panels with their own configuration languages, theming limits and memory profiles. The next step is a first-party panel built on GTK4 and `gtk4-layer-shell` that carries the shelf design and supports every panel feature exposed in Settings.

Target device: 2 GB x86_64 Chromebook, 1366×768, eMMC, labwc, keyboard + touchpad. Panel changes currently require a session restart; the new panel is expected to apply them live.

## Goals

- First-party GTK4 + layer-shell panel with the merged ChromeOS/Adwaita shelf language.
- Full parity with the panel features currently exposed in Settings.
- Hyper-efficient on 2 GB: no GL renderer, no polling, no frame-loop animation, one panel process.
- Live application of panel/appearance/accessibility/datetime settings.
- App-centric taskbar with pinned/running merge, multi-window access, keyboard and screen-reader operation.
- Multi-monitor support with per-output task filtering, sharing one process.
- Keep Waybar and sfwbar installed as fallback backends until cutover.

## Non-goals

- Quick Settings, a control center, overview mode, or a second settings application.
- Window thumbnails, blur, translucency, or large animated shadows.
- Replacing the internal app grid in Wave 0/1; the existing Python `adwaita-lite-app-menu` remains the launcher until the in-panel grid is ready.
- Per-output configuration UI (all outputs share global controls; tasks are filtered per output).
- Touch-mode targets: compact density remains pointer-oriented.
- Changing the Waybar default before the GTK4 panel passes the VM gate.

## Measured evidence

A minimal GTK4 layer-shell panel was compiled and run in the Fedora 44 container lab: sway 1.11 headless, 1280×720, GTK 4.22.5, `gtk4-layer-shell` 1.3.0. RSS/Pss read after 3–4 s idle; startup timed from process launch to the first `present`; idle CPU sampled over 2 s. Three runs, stable values.

| Stack | RSS | Pss | Startup | Idle CPU |
|---|---:|---:|---:|---:|
| C + default GL | ~165 MB | ~156 MB | 230–280 ms | 0 |
| C + `GSK_RENDERER=ngl` | ~136 MB | ~127 MB | 230 ms | 0 |
| **C + Cairo** | **~39 MB** | **~31 MB** | **64–70 ms** | **0** |
| **Vala + Cairo** | **~39 MB** | **~31 MB** | **72–80 ms** | **0** |
| Python + Cairo | ~65 MB | ~55 MB | 224–278 ms | 0 |
| Python + default GL | ~175 MB | ~164 MB | — | 0 |
| C + Cairo, 12 buttons + clock | ~39 MB | ~31 MB | 69–75 ms | 0 |
| sfwbar (current preview) | ~38 MB | — | — | — |
| Waybar (current default) | ~56 MB | — | — | — |

The widget count was effectively free at 48 px; the renderer and runtime dominate. GTK4's GL renderers consume 7–8% of a 2 GB machine before any panel feature exists, so they are disqualifying. Cairo is the only viable renderer.

Caveat: these numbers are from sway, a minimal widget tree and 1280×720. The target is labwc at 1366×768 with the full module set; Wave 0 must re-measure the populated panel.

## Fusion decision log

### Panel A — architecture

- C11 + GLib/GObject/GIO; C is the only measured stack near sfwbar. Python is already over budget before features; Vala is admissible only with measured parity; Rust is unmeasured.
- Enforce Cairo in three places: `g_setenv` before GTK init, `Environment=GSK_RENDERER=cairo` in the user unit, and a runtime assertion with `--require-cairo` for CI.
- One process with one layer-shell window per output; shared models/services/CSS/icon cache; never one process per output.
- Event-driven services: wlr-foreign-toplevel, SNI + DBusMenu over GDBus, libpulse GLib mainloop, UPower, NetworkManager, logind/sysfs backlight, a minute-aligned clock timer, and a debounced config file monitor.
- No polling, no frame callbacks, no worker pool, no periodic `GetAll`, no per-widget CSS providers.
- Budget: ≤45 MB RSS / ≤38 MB Pss; veto >55/45. First paint ≤120 ms.
- Strongest disagreement: fold the app grid into the panel process and refuse a 60 MB budget.

### Panel B — UX

- The shelf is quiet, opaque, stable, app-centric and keyboard-complete without focus theft.
- App grouping from the first release; pinned/running merge by `desktop_id → app_id → startup_wm_class`, never guessing on conflict; exact pinned commands preserved.
- One-window left click raises/minimizes; multiple windows open a text-only window list; middle click closes only a single-window group; right click opens app/window actions.
- Metrics follow PR #13: 48/40, 16 px inset, 32/24 app icons, 12/10 radii, circular launcher, flat status, 8/16/12% states, Adwaita Sans, 500 clock.
- Popup: 320 px wide, max 384 px tall, 8 px gap, r12 opaque, 44/40 rows, 32 px actions; no thumbnails.
- Keyboard: Tab/Shift+Tab between groups, arrows within, Home/End, Enter/Space, Shift+F10/Menu, Escape; ON_DEMAND keyboard mode; accessible names and Orca.
- Performance constraints are design constraints: no blur, translucency, thumbnails, large shadows, continuous animation, polling, seconds clock, or refresh timers.
- Strongest disagreement: do not defer app-centric grouping; it determines identity, merge, activation, popup, focus, accessibility and overflow.

### Arbiter verdict

- **Runtime:** C11 + Cairo. Vala + Cairo was later measured equal (~39 MB, 72–80 ms) and remains a documented alternative, but C is selected for direct `wayland-scanner` protocol code and the absence of vapi maintenance.
- **Process:** one process, one layer-shell window per output.
- **App grid:** fold into the panel as an on-demand surface at cutover; keep the Python app menu through the transition.
- **Grouping:** ship grouped-by-default in Wave 1, with `panel.taskbar_grouping = app | window` and a tooltip fallback if the popup spike fails.
- **Budget:** target ≤48 MB RSS / ≤40 MB Pss; veto >56/46; +4 MB per output; +1 MB per 10 windows.
- **Status parity:** volume click opens `pavucontrol` in Wave 1 (current behavior); in-panel slider later opt-in. Network is passive and off by default; tray is a later wave. No quick settings.
- **Naming/backend:** new C binary takes `/usr/bin/adwaita-lite-panel`; Python preview becomes `adwaita-lite-panel-preview`; dispatcher `adwaita-lite-session-panel` reads `panel.backend` (`gtk4|waybar|sfwbar`), default unchanged until cutover.

## Selected architecture

### Runtime and renderer

- C11, GLib/GObject/GIO, GTK4, `gtk4-layer-shell`.
- No libadwaita, GTK3, libdbusmenu, libappindicator or libwnck in the panel process.
- Cairo only:
  1. `g_setenv("GSK_RENDERER", "cairo", TRUE)` as the first statement in `main()`.
  2. `Environment=GSK_RENDERER=cairo` in the systemd user unit and session dispatcher.
  3. Runtime renderer assertion; `--require-cairo` makes it fatal for benchmarks/CI.
- The session currently exports `GSK_RENDERER=gl` for GTK apps (`adwaita-lite-session`, labwc autostart). The panel's own unit/environment must override it; the panel must not change the session-wide value for other apps.

### Process and windows

```
adwaita-lite-panel (single process, one GLib main loop)
├── app/        GApplication, single-instance lock, CLI
├── config/     JSON load/validate, GFileMonitor + debounce
├── theme/      token → CSS text → one GtkCssProvider
├── shell/      monitor manager, PanelSurface, region layout, module registry
├── modules/    launcher, taskbar, clock, volume, backlight, battery, network, tray
├── model/      PanelModel, AppGroup, WindowItem, IndicatorState
├── services/   foreigntoplevel, sni, audio, power, network, backlight, clock
└── platform/   wlr protocol wrappers, GDBus helpers, logind/sysfs helpers
```

- One `GtkWindow` per monitor; shared model/services/CSS/icon cache.
- Monitor hotplug via `GdkDisplay` monitors; create/destroy surfaces; taskbar filtered by output.
- Single-instance lock in `$XDG_RUNTIME_DIR`; `--replace` for explicit restarts.
- Target ≤48 MB RSS with one output, 20 windows, 8 mock tray items; ≤+4 MB per extra output.

### Event sources

| Source | Mechanism | Rules |
|---|---|---|
| Windows | `zwlr_foreign_toplevel_manager_v1` | Add/remove, title/app_id, output enter/leave, state; requests activate/minimize/close. Tolerate late metadata and re-key groups. |
| Tray | SNI watcher/host + per-item proxies + DBusMenu | GDBus only; cache proxies; cap icon pixmaps; never block first paint. |
| Audio | libpulse via `pa_glib_mainloop` | Subscribe to sink/server events; scroll ±5%; keyboard ±5%. |
| Power | UPower `DisplayDevice` properties | No timers; state classes for 25/12 thresholds. |
| Network | NetworkManager DBus | Passive state only; off by default until `panel.network` exists. |
| Backlight | logind `SetBrightness` + inotify reads | Permission path validated in the image. |
| Clock | One minute-aligned GLib timer | Date tooltip on demand; no seconds. |
| Config | `GFileMonitor` + 50–100 ms debounce | Keep last good config on parse errors; one CSS swap per change. |

All DBus calls async; no `*_sync` on the main loop. `.desktop` lookups only for pinned entries, never a full app-info scan in the panel hot path. Icons cached; tile updates incremental, never a full rebuild.

### App identity and grouping

Identity order for pinned/running merge:

1. `desktop_id` (strip `.desktop`)
2. `app_id`
3. `startup_wm_class`

If identifiers conflict, are missing, or match multiple distinct pinned commands, the running group stays unpinned. Two pins never collapse because their identifiers look similar. Pinned order is settings order; unpinned groups use first-seen order and never reorder on focus. A pinned group always renders; a running window merges into its pinned tile.

### Settings and live reload

- The panel owns a `GFileMonitor` on `~/.config/adwaita-lite/settings.json`, debounced, tolerant of partial/unknown keys and atomic renames.
- All appearance/accessibility/datetime/panel keys apply live: edge, density, twilight, layout, pinned, theme, accent, font size, high contrast, reduce motion, 12/24h clock.
- Geometry/module changes dismiss any popup whose anchor disappears; focus moves to the nearest surviving control.
- New keys: `panel.backend`, `panel.taskbar_grouping`, `panel.network`, `panel.multi_output`.
- Settings copy changes from “restart your session” to “applies immediately” for hot-reloadable keys; backend changes still require restart.

### Naming and backend selection

- New binary: `/usr/bin/adwaita-lite-panel` (C).
- Existing Python generator: rename to `/usr/bin/adwaita-lite-panel-preview`.
- Dispatcher: `/usr/bin/adwaita-lite-session-panel` reads `panel.backend` and execs one backend.
- labwc autostart calls the dispatcher instead of `waybar`.
- Default backend remains Waybar until Wave 6 acceptance.
- systemd user unit: `PartOf=graphical-session.target`, `Restart=on-failure`, `Environment=GSK_RENDERER=cairo`, `MemoryHigh=64M`, `MemoryMax=128M`.

## UX specification

### Shelf and metrics

| Metric | Normal | Compact |
|---|---:|---:|
| Horizontal height / vertical width | 48 px | 40 px |
| Content-facing separator | 1 px | 1 px |
| Outer main-axis inset | 16 px | 16 px |
| App/pinned/task tile | 48×48 r12 | 40×40 r10 |
| App icon | 32×32 | 24×24 |
| Launcher | 48×48 r999 | 40×40 r999 |
| Launcher glyph | 24×24 | 20×20 |
| Status tile | 40×48 r12 | 40×40 r10 |
| Status/tray icon | 20×20 | 16×16 |
| App gap | 4 px | 4 px |
| Status gap | 4 px | 4 px |
| Launcher gap | 8 px | 4 px |
| Module gap | 12 px | 8 px |

Vertical shelves keep text horizontal. Status tiles rotate their box to 48×40 normal / 40×40 compact; app tiles stay square. The horizontal clock has a minimum 64/56 px width plus 12/8 px padding and grows for 15 px text. The vertical clock stacks hours, minutes and AM/PM without rotation.

### States

- Hover: 8% foreground.
- Pressed: 16% foreground.
- Active window: 12% accent fill + a 3 px screen-edge bar, 24 px long normal / 20 px compact.
- Running unfocused: one 4 px dot on the screen edge, 40% foreground.
- Multiple windows: tooltip/accessible name/window list only; no rows of dots.
- Urgent: static 12% warning fill, no pulse; keep the active bar if focused.
- Keyboard focus: separate 2 px inset outline, 2 px from the icon.
- HC opaque, solid system colors, visible outlines; active/running/urgent distinguishable without hue.
- Twilight changes the shelf palette only.
- 120 ms state transitions; zero under reduce motion/HC.

### Taskbar interactions

| State | Left click / Enter |
|---|---|
| Pinned, not running | Launch exact configured command |
| One inactive/minimized window | Raise/focus |
| One active window | Minimize |
| Multiple windows | Open window list |

- Middle click closes only a single-window group; multi-window middle click opens the list.
- Right click / Shift+F10 / Menu opens app/window actions. No easy “close all” initially.
- Window list rows: 44/40 px, 20/16 icon, ellipsized title, active/minimized state, 32×32 minimize/close. Width 320 px, max height 384 px, 8 px shelf gap, r12 opaque, 8 px padding.
- Overflow: launcher/pins/status keep geometry; task region scrolls or shows an overflow popup; never wraps or shrinks icons.
- No thumbnails, live previews, or animated reordering.

### Status, launcher, tray

- Order: tray → network → volume → backlight → battery → clock.
- Launcher: internal app grid; tooltip “Applications”; Super+Space unchanged.
- Volume: mute-aware, tooltip %, scroll ±5, keyboard ±5, click `pavucontrol` in Wave 1. Optional in-panel slider later behind `volume.popup`.
- Backlight: tooltip only.
- Battery: charging ladder, warning 25, critical 12, tooltip; static.
- Clock: 12/24h, weight 500, date tooltip; calendar later, not parity.
- Network: passive icon and tooltip; no click; off by default until settings exposes it.
- Tray: SNI names/icons/activation/menus; empty tray collapses completely. No invented actions.
- No monolithic status capsules, no quick settings.

### Keyboard and accessibility

- Layer-shell keyboard mode `ON_DEMAND`; the panel must not steal keys.
- Tab/Shift+Tab move between module groups; arrows within; Home/End; Enter/Space; Shift+F10/Menu; Escape closes popups and returns focus.
- A session-level “Focus Shelf” accelerator is required; the exact binding must be reconciled with labwc (proposal: `Super+Shift+P`).
- Accessible names include app name, window count, active/minimized/urgent state; status names include values/units; clock is not an assertive live region.
- 15 px text and large-text tests; titles ellipsize visually but remain full in AT-SPI.
- Orca traversal into the layer surface must be proven in Wave 0; a normal toplevel fallback is required if it fails.

## Performance budget

| Metric | Target | Veto |
|---|---:|---:|
| Idle RSS, 1 output, 20 windows, 8 tray items | ≤48 MB | >56 MB |
| Idle Pss, same | ≤40 MB | >46 MB |
| First paint | ≤120 ms | >150 ms |
| Fully populated | ≤400 ms | >800 ms |
| Idle CPU | 0 ticks / 10 s | any sub-second timer |
| Wakeups | ≤3/min | >10/min |
| Hover/press repaint | ≤16 ms | >33 ms |
| Popup open | ≤100 ms | >200 ms |
| Per extra output | ≤+4 MB | >+8 MB |
| Per +10 windows | ≤+1 MB | >+2.5 MB |
| 8 h soak drift | ≤+2 MB | >+5 MB |

Measurement uses the existing container lab: `ps`/`smaps_rollup`, self-timed first `present`, `/proc/$pid/stat` for idle CPU/wakeups, `strace -c` and `dbus-monitor` to prove no polling, `grim` for geometry/state captures, and 100-cycle reload/popup/toplevel soak tests. CI benchmark fails on veto thresholds.

## Feature parity matrix

| Feature | Existing settings/behavior | Native panel | Notes |
|---|---|---|---|
| Edge top/bottom/left/right | yes | Wave 2 | layer anchors; vertical text horizontal |
| Density normal/compact | yes | Wave 1 | live |
| Twilight | yes | Wave 1 | live |
| Start/center/end layout | yes | Wave 2 | all module ids + `network` |
| Pinned apps | yes, exact commands | Wave 1 | merge, preserve command |
| Taskbar | one tile/window | Wave 1 | grouped default, legacy mode |
| Launcher/app menu | internal Python app menu | Wave 1 | keep existing menu; fold later |
| Volume | icon/tooltip/scroll/pavucontrol | Wave 1 | parity click |
| Backlight | tooltip | Wave 2 | logind/sysfs |
| Battery | ladder/25/12 | Wave 1 | UPower |
| Clock | 12/24 + date tooltip | Wave 1 | minute timer |
| Tray | SNI | Wave 4 | hardest module |
| Network | absent/off | Wave 3 | passive, opt-in |
| Theme/accent/font/HC/motion | yes | Wave 1 | live |
| Multi-monitor | per-output Waybar | Wave 5 | one process/N windows |
| Hot reload | restart required | Wave 1 | all hot-reloadable keys |
| Keyboard/Orca | partial/unverified | Wave 1/5 | acceptance requirement |

## Packaging and integration

- Meson + ninja; C11; `gtk4 >= 4.10`, `gtk4-layer-shell`, `wayland-client`, build-time `wayland-scanner`, GLib/GIO, libpulse.
- Vendor the wlr foreign-toplevel protocol XML; generate the binding in Meson.
- Build in `build_files/build.sh`; keep build-only deps out of the final image where possible.
- Install binary, systemd user unit, dispatcher, and protocol XML.
- Update `files/etc/xdg/labwc/autostart` to call the dispatcher; keep `waybar`/`sfwbar` installed for fallback.
- Settings changes: add `network` to the module list only when enabled; add `panel.backend`, `panel.taskbar_grouping`, `panel.network`, `panel.multi_output`; replace restart copy with live-apply copy; keep restart notice for backend changes.
- Documentation: update panel docs, settings copy, translations, and the status matrix/evidence ledger.

## Phases

### Wave 0 — spike (gating, no user-facing change)

1. C + Cairo layer-shell shelf on labwc, bottom edge, 48/40 geometry, PR #13 tokens.
2. Popup strategy: **resolved** — `GtkPopover` with `autohide=TRUE` for anchored menus; a full-screen `OVERLAY`/`EXCLUSIVE` layer surface only for the app grid. The panel starts `KEYBOARD_MODE_NONE` and switches to `ON_DEMAND` after first present to avoid map-time focus theft.
3. Foreign-toplevel identity fidelity on labwc: map pinned entries + 5 running apps via `desktop_id → app_id → startup_wm_class`.
4. Event fidelity: add/remove/property/output events; prove no polling.
5. Populated memory/startup re-measure with 20 windows and mock tray; go/no-go against the budget.
6. Orca traversal and keyboard focus onto the layer surface.

**Exit criteria:** ≤48 MB RSS/≤40 MB Pss in the populated spike (or a written scope reduction), ≤150 ms first paint, a working popup/keyboard path, and a verified identity map. Popup strategy is resolved; Orca remains the fallback risk.

### Wave 1 — first shippable `panel.backend=gtk4`

Bottom edge, normal/compact, launcher, ordered pins, grouped running tiles and pinned/running merge, single/multi-window behavior, clock/volume/battery, live appearance/density/twilight/clock format, keyboard/accessible names. Keep the Python app menu if the in-panel grid is not ready. `panel.taskbar_grouping=window` provides legacy behavior.

### Wave 2 — layout parity

Top/left/right edges, start/center/end layout, backlight, vertical clock, overflow hardening, legacy ungrouped mode.

### Wave 3 — status services

libpulse GLib mainloop, UPower, logind/sysfs backlight events, passive network behind `panel.network`, optional in-panel volume slider behind `volume.popup`.

### Wave 4 — tray

SNI host + DBusMenu renderer; themed icons and ARGB32 pixmaps; activation/menu/attention; empty collapse; fixture tests.

### Wave 5 — outputs, app grid, accessibility

Multi-monitor windows/hotplug/per-output groups, `panel.multi_output`; fold the app grid into the panel if the spike supports it; Orca/AT-SPI pass; overflow polish.

### Wave 6 — cutover

Default `panel.backend=gtk4` after the 2 GB VM gate, 8 h soak, and rollback rehearsal. Retire the Python app menu after grid parity; keep `adwaita-lite-panel-preview` for regression diffs; remove Waybar/sfwbar autostart only after one release of fallback.

## Acceptance criteria

- All current settings apply live without a session restart; malformed settings keep the last good state.
- Pinned exact commands launch; ambiguous identifiers never merge; one tile per app group.
- One-window and multi-window interactions match the taskbar table; no arbitrary window close/focus.
- Keyboard/Orca operations cover activate, minimize, close, volume, tray menus, and popups.
- All four edges, both densities, light/dark/HC/twilight, 15 px text and reduce motion pass screenshot and behavior checks.
- Performance targets met in the container lab with populated state; CI benchmark enforces veto thresholds.
- Waybar/sfwbar remain available as fallback until cutover; `panel.backend` selects exactly one panel.

## Risks

1. **Popup on layer-shell** — positioning/grab/keyboard/Orca unknown; Wave 0 spike and reusable layer-shell fallback.
2. **SNI + DBusMenu in C** — ecosystem variance and memory; isolate, fixture-test, late wave, backend fallback.
3. **Memory creep** — full panel, tray and two outputs can add 10–15 MB; stop scope, never raise the budget.
4. **labwc foreign-toplevel fidelity** — late/empty app_id, output events, urgent semantics; identity map and fallback rules.
5. **Keyboard/Orca on layer surfaces** — focus traps/focus theft; ON_DEMAND, Escape handling, normal-toplevel fallback.
6. **C maintenance cost** — protocol/DBus boilerplate; strict module seams, generated protocol code, ~6–8k LOC budget.

## Open questions

- GtkPopover vs reusable layer-shell popup (resolved in Wave 0: GtkPopover with autohide; panel starts NONE then ON_DEMAND).
- Timing of the in-panel app grid fold and whether to port the Python menu or build a leaner grid.
- Exact session-level “Focus Shelf” accelerator with labwc.
- Whether `panel.network` defaults on after the network module passes hardware tests.
- Volume slider opt-in timing.
- Whether Vala should replace C after a full-panel benchmark (measured equal at minimal size; C selected for protocol risk).
- Multi-monitor default and hotplug UX beyond “all outputs, local tasks”.
- Cutover release and removal schedule for Waybar/sfwbar.

## References

- PR #12: sfwbar preview backend.
- PR #13: ChromeOS/Adwaita sfwbar shelf redesign (design language and metrics).
- Settings panel: `files/usr/lib/adwaita-lite/settings/pages/panel.py`.
- Defaults: `files/usr/share/adwaita-lite/defaults/settings.json`.
- Session autostart: `files/etc/xdg/labwc/autostart`.
- Session environment: `files/usr/libexec/adwaita-lite-session`.
- App menu: `files/usr/bin/adwaita-lite-app-menu`.
- Build: `build_files/build.sh`.
