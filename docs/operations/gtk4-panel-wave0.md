# GTK4 Panel Wave 0 Spike Report

**Status:** evidence collected. No user-facing change; the Waybar default is untouched.

This report records the gating spikes for the native GTK4 panel design in
`docs/superpowers/specs/2026-11-07-native-gtk4-panel-design.md`. The goal was
to test the architecture's highest-risk assumptions before writing the panel.

## Environment

- Fedora 44 container, labwc 0.9.6, headless wlroots backend, 1280×720.
- GTK 4.22.5, `gtk4-layer-shell` 1.3.0.
- C11 spike, `GSK_RENDERER=cairo` forced before GTK init.
- `wlrctl` for pointer input, `wtype` for keyboard input, `grim` for captures.

## Wayland protocol surface (labwc)

`wayland-info` confirms the panel can rely on Wayland-native protocols:

- `zwlr_layer_shell_v1` v4
- `zwlr_foreign_toplevel_manager_v1` v3 (actions: activate, close, minimize)
- `ext_foreign_toplevel_list_v1` v1 (standard enumeration)
- `ext_workspace_manager_v1` v1
- `xdg_activation_v1`
- `xdg_toplevel_icon_manager_v1`
- `zwlr_screencopy_manager_v1` v3 / `ext_image_copy_capture_manager_v1`
- `zwp_virtual_keyboard_manager_v1` / `zwlr_virtual_pointer_manager_v1` (test input)
- `ext_idle_notifier_v1`, `zwp_idle_inhibit_manager_v1`

The panel should use `zwlr_foreign_toplevel_manager_v1` for window actions and
may use the `ext` protocols for enumeration/workspaces where they fit. No X11
path is needed.

## Benchmark

The spike includes the shelf, launcher/task buttons, status icons, clock,
popover code and CSS.

| Metric | Result |
|---|---|
| Idle RSS | ~41.6 MB |
| Idle Pss | ~33.3 MB |
| Startup (process start → first present) | 78 ms |
| Idle CPU | 0 ticks / 2 s |

This is within the design target (≤48 MB RSS / ≤40 MB Pss) with headroom for
services. It is a static spike, not a populated taskbar/tray panel.

## Findings

### Layer shell and Cairo

- C + Cairo + `gtk4-layer-shell` renders correctly on labwc at the bottom edge
  with a 48 px shelf and 16 px inset.
- The CSS provider must be installed **after** GTK has a display. Calling
  `gtk_style_context_add_provider_for_display(gdk_display_get_default(), …)`
  before `GtkApplication` activation fails with
  `GDK_IS_DISPLAY` because there is no display yet.
- GTK4's default button theme needs `border: none; outline: none;
  box-shadow: none` on custom tiles; otherwise Adwaita outlines win over the
  shelf design.

### Tooltips

`GtkTooltip` works on the layer-shell surface. Hovering the volume button
showed `Volume, 42 percent` above the shelf. Tooltips are viable for the panel.

### Popovers vs layer-shell popups

- `GtkPopover` **renders** on the layer-shell surface (correctly anchored above
  the launcher), but keyboard input did not reach it: `wtype -k Escape` did
  not close it, and the panel's key controller never saw the key.
- A dedicated `GtkWindow` with `gtk4-layer-shell` (overlay layer, anchored above
  the shelf, `KEYBOARD_MODE_EXCLUSIVE`) renders correctly **and** receives
  keyboard input: `Escape` reached the popup's key controller and destroyed it.

**Decision:** use a reusable layer-shell popup surface for keyboard-interactive
UI (window list, tray menus, future app grid). `GtkTooltip` remains fine for
tooltips. Do not build the primary popup/menu model on `GtkPopover` unless a
later spike proves focus handling on this compositor.

### Focus

The initial GTK focus lands on a task tile and can show the keyboard focus ring
even when the user has not focused the shelf. The panel must explicitly clear
initial focus (`gtk_window_set_focus(win, NULL)`) and only show focus after
keyboard traversal; the spike still needs a clean verification of this.

## Remaining Wave 0 items

- Orca/AT-SPI traversal and accessible names on the layer surface.
- Foreign-toplevel identity map on labwc (`desktop_id` → `app_id` →
  `startup_wm_class`) with real apps and multiple windows.
- Populated memory/startup with 20 windows and mock tray items.
- Multi-output surface creation and taskbar filtering (single-output lab only).

## Next

Wave 1 scaffold: C11 + Cairo, settings/theme engine, layer-shell shelf,
launcher/clock/static status, reusable layer-shell popup, and the app-group
model. Keep Waybar as the default backend and the Python app menu in place
until the in-panel grid is ready.
