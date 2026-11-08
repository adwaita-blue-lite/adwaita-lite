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
- Static status placeholders (network/volume/battery) with accessible names.

Not implemented yet (see the design spec's waves):

- Status services (PulseAudio, UPower, NetworkManager, backlight).
- Per-output task filtering (the model already keeps toplevel output events).
- SNI tray.
- Layout start/center/end module ordering.

## Build

```
meson setup build
meson compile -C build
```

Dependencies: `gtk4-devel`, `gtk4-layer-shell-devel`, `json-glib-devel`,
`meson`, `ninja-build`.

## Run

```
GSK_RENDERER is forced to cairo inside the binary. Run it inside a
labwc session; it places itself on every monitor.
```

## Open item: popup keyboard focus

The Wave 0 spike showed that labwc delivers keys to a layer-shell popup only
when the parent panel is `KEYBOARD_MODE_EXCLUSIVE` at startup. Changing the
panel mode after mapping does not take effect, and a popup created from an
`ON_DEMAND` panel does not receive Escape. The production panel must not grab
the keyboard permanently, so Wave 1 needs one of:

- a dedicated keyboard layer surface created while the popup is open,
- a borderless normal toplevel for keyboard-interactive menus, or
- a labwc-specific focus workaround that can be proven in the VM gate.

The clock popup remains pointer-accessible for now.

## Performance notes

The Wave 0 spike measured ~39-42 MB RSS / ~31-33 MB Pss, 65-93 ms startup and
0 idle CPU for this stack on labwc. The budget is ≤48 MB RSS / ≤40 MB Pss with
a veto above 56/46; see the design spec.
