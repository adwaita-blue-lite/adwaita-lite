# adwaita-lite-panel (Wave 1 scaffold)

First-party GTK4 + layer-shell panel for Adwaita-Lite. This is a **scaffold**:
it is not wired into the session, not installed by the image build, and
Waybar remains the default panel backend.

Design reference: `docs/superpowers/specs/2026-11-07-native-gtk4-panel-design.md`
and `docs/operations/gtk4-panel-wave0.md`.

## Status

Implemented in this scaffold:

- C11 + GTK4 + `gtk4-layer-shell`, Cairo renderer forced before GTK init.
- One process, one layer-shell window per monitor.
- All four shelf edges with the 48/40 geometry, 16px inset and 1px separator.
- Theme engine: light/dark/high-contrast/twilight, all nine accents,
  font-size scaling, compact density, reduce-motion.
- Settings loading from `/usr/share/adwaita-lite/defaults/settings.json`
  plus `~/.config/adwaita-lite/settings.json`, with live reload
  (debounced file monitor, CSS provider swap, shelf rebuild).
- Launcher button that spawns the existing `adwaita-lite-app-menu`.
- App-centric taskbar from `zwlr_foreign_toplevel_manager_v1`: one tile per
  app group, pinned/running merge, focused state, exact-command launch for
  idle pins, single-window minimize/raise, middle-click close, and a
  multi-window list popup.
- Clock with 12/24h formats, minute-aligned timer, full-date tooltip and a
  layer-shell popup (pointer Close works; keyboard focus is an open item,
  see below).
- Live status services:
  - UPower battery over GDBus: percentage, charging/discharging, 25/12
    warning classes, hide when no battery.
  - libpulse in-process (`pa_glib_mainloop`): default-sink volume/mute,
    scroll ±5, keyboard ±5, tooltip, click `pavucontrol`.
  - Passive NetworkManager status behind `panel_network` (default off):
    wired/wireless/offline icon and tooltip; no scanning or clicks.
  - Backlight percentage via sysfs read, lazy `query-tooltip`; hidden when
    no `/sys/class/backlight` device.

Not implemented yet (see the design spec's waves):

- Per-output task filtering (the model already keeps toplevel output events).
- SNI tray.
- Layout start/center/end module ordering.

## Build

```
meson setup build
meson compile -C build
```

Dependencies: `gtk4-devel`, `gtk4-layer-shell-devel`, `json-glib-devel`,
`pulseaudio-libs-devel`, `meson`, `ninja-build`. Runtime needs
`pulseaudio-libs-glib2`, `upower`, and (for network status)
NetworkManager. The panel degrades to hidden tiles when a service is
absent.

## Run

```
GSK_RENDERER is forced to cairo inside the binary. Run it inside a
labwc session; it places itself on every monitor.
```

## Popup and keyboard behaviour

The panel starts its layer surface with `KEYBOARD_MODE_NONE` and switches to
`ON_DEMAND` 500 ms after the first present. Starting in `ON_DEMAND` makes
labwc focus the surface at map time, which steals keyboard focus from the
active app; starting in `NONE` avoids that.

Anchored menus (clock, window list, future tray/calendar) use `GtkPopover`
with `autohide=TRUE`. GTK creates a layer-shell popup with an xdg_popup grab;
labwc then delivers Escape, outside-click dismissal and keyboard row
navigation, and returns focus to the previous app. The Wave 0 finding that
"only a keyboard-exclusive panel can host a keyboard popup" was a test-harness
key-injection race, not a compositor limitation. A full-screen app grid will
use one `OVERLAY`/`EXCLUSIVE` layer surface when it lands.

## Performance notes

The Wave 0 spike measured ~39-42 MB RSS / ~31-33 MB Pss, 65-93 ms startup and
0 idle CPU for this stack on labwc. The budget is ≤48 MB RSS / ≤40 MB Pss with
a veto above 56/46; see the design spec.
