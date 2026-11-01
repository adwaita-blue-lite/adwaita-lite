# Adwaita-Lite GTK4 Panel Research

**Date:** 2026-05-18
**Status:** Research
**Direction:** Build a Adwaita-Lite-native GTK4 panel. Existing panels are reference implementations, not adoption targets.

## Summary

Adwaita-Lite's current Waybar setup is deeply integrated with our settings, theme, accent, layout, and pinned-app model. Ironbar is the closest conceptual off-the-shelf GTK4 replacement, but it has no official Fedora RPM and still does not fit Adwaita-Lite's arbitrary pinned-command model cleanly. Other Fedora-packaged panels either stay on GTK3, target another compositor or desktop, use QtQuick, or do not align with Adwaita/GTK4 goals.

The most promising path is to build a small Adwaita-Lite panel around the exact contracts we already own:

- GTK4 + gtk4-layer-shell for the visible panel surface.
- `wlr-foreign-toplevel-management` for taskbar/window control.
- StatusNotifier/AppIndicator over D-Bus for tray icons.
- UPower, NetworkManager, logind, PulseAudio/PipeWire compatibility, and sysfs for status modules.
- Existing Adwaita-Lite settings JSON, palette tokens, accents, high contrast, twilight, density, edge, layout, and pinned apps.

The panel should start as a conservative replacement for current Waybar behavior, not a general-purpose shell framework. The research below captures the parts worth learning from Waybar, Ironbar, sfwbar, nwg-panel, wf-shell, quickshell, and labwc-oriented experiments.

## Why Not Adopt Another Panel

| Project | Fedora Package | Toolkit | Useful Lessons | Fit As Dependency |
|---|---:|---|---|---|
| Waybar | yes | GTK3/gtkmm3 | Mature module contracts, wlr taskbar behavior, SNI watcher implementation | Current solution, but not GTK4/Adwaita-native |
| Ironbar | no official Fedora RPM | GTK4/Rust | Launcher grouping, GTK4 tray migration, CSS selectors, config shape | Good reference, packaging and model mismatch |
| sfwbar | yes | GTK3/C | Broad module coverage, taskbar grouping, manual SNI/DBusMenu | Feature-rich but GTK3 and config model mismatch |
| nwg-panel | yes | GTK3/Python | Config UI, pinned launchers, taskbars for compositor-specific APIs | GTK3 and Sway/Hyprland-centric |
| wf-shell | yes | GTK4/gtkmm4 | Layer-shell mechanics, dock/panel architecture, autohide cautions | Wayfire-oriented, not Adwaita-Lite/labwc-native |
| quickshell | yes | QtQuick | Declarative shell architecture, service-backed widgets | Toolkit/theme mismatch |
| yambar | yes | non-GTK | Efficient status polling/event model | Not a taskbar/tray/adwaita panel |

There is one packaged GTK4 candidate, `wf-shell`, but it is Wayfire-oriented. Depending on it would import another desktop's assumptions into Adwaita-Lite. Building our own lets us keep the panel small, Adwaita-aligned, and driven by our existing settings model.

## Current Adwaita-Lite Contract To Preserve

Adwaita-Lite currently generates `~/.config/waybar/config.jsonc` and `~/.config/waybar/style.css` from `files/usr/libexec/adwaita-lite-apply-settings`. A native panel should preserve the settings contract, not the Waybar file format.

Settings and defaults:

- `edge`: `top`, `bottom`, `left`, or `right`; default `bottom`.
- `density`: `normal` or `compact`.
- `layout`: `start`, `center`, `end` sections.
- Default layout: `custom/launcher` in start, `wlr/taskbar` in center, `pulseaudio`, `backlight`, `battery`, `clock`, `tray` in end.
- `pinned`: app entries with `name`, `command`, `icon`, and optional `desktop_id`, `app_id`, `startup_wm_class`.
- Theme inputs: `theme`, `accent`, `high_contrast`, `reduce_motion`, `font_size`, `cursor_size`, `panel_twilight`, `clock_24h`.

Behavior to preserve:

- Launcher button opens `adwaita-lite-app-menu`.
- Taskbar is icon-only, per-output by default, and supports activate/minimize behavior.
- Middle-click close is expected if we keep Waybar parity.
- Pinned apps appear next to the launcher and should merge with running app buttons when possible.
- Volume is icon-only, muted-aware, tooltip shows percent, scroll changes volume by 5%, click opens `pavucontrol` or the Adwaita-Lite sound page later.
- Brightness is icon-only, tooltip shows percent, scroll changes brightness by 5%.
- Battery is icon-only, charging-aware, warning at 25%, critical at 12%, tooltip shows capacity.
- Clock supports 12/24h; vertical 12h mode can split time and AM/PM if needed.
- Tray is separate from the grouped status pill.
- Horizontal and vertical panel modes must remain first-class.
- Theme, accent, high contrast, and twilight changes should update the panel without requiring logout.

## Implementation Language Direction

Prefer Rust + Relm4 for the first serious implementation.

Rationale:

- Relm4 provides a model/message/component structure that fits a long-running panel with many independent state sources.
- Rust is a safer fit than C for D-Bus tray handling, app identity matching, Wayland protocol state, and async service updates.
- The result is still a native binary, avoiding a permanent Python interpreter in the always-running panel path.
- Fedora packages the core Rust GTK stack, including `rust-relm4-devel`, `rust-relm4-macros-devel`, `rust-relm4-components-devel`, `rust-gtk4-devel`, `rust-gio-devel`, `rust-glib-devel`, `rust-zbus-devel`, and `rust-wayland-client-devel`.
- Fedora packages the C `gtk4-layer-shell` runtime and development library.

Expected Rust stack:

- `relm4` for top-level app and component structure.
- `gtk4-rs`, `gio`, and `glib` for GTK and GLib integration.
- `gtk4-layer-shell` Rust bindings for layer-shell, backed by Fedora's packaged C `gtk4-layer-shell` library.
- `zbus` for UPower, NetworkManager, logind, StatusNotifier, and DBusMenu.
- `wayland-client` plus generated protocol bindings for `wlr-foreign-toplevel-management`.
- Plain `gtk4-rs` code where Relm4 abstractions make low-level panel work harder.

Known caveat: Fedora does not appear to package the Rust `gtk4-layer-shell` crate today. The panel may need a pinned crates.io dependency in `Cargo.lock` while using Fedora's packaged C library at build and runtime. If that becomes unacceptable or awkward, native C/C++ with `gtk4-layer-shell-devel` is the fallback.

Keep C/C++ as the escape hatch, not the primary plan. It has the cleanest all-Fedora system-library story, but Rust + Relm4 should give us better correctness and maintainability for the hard parts.

## Architecture Recommendation

Use a model-view split so protocol and D-Bus state can be tested independently from GTK widgets.

```text
AdwaitaLitePanelApp
  SettingsStore
  ThemeTokens
  PanelManager
    PanelWindow per monitor
      start box
      center box
      end box
  Services
    ToplevelService
    DesktopAppIndex
    TrayService
    AudioService
    BrightnessService
    BatteryService
    ClockService
    NetworkService (later or optional)
```

Avoid a Python GI prototype unless we need a throwaway spike. Python would be fast to iterate on, but it adds an interpreter to an always-running component and does not reflect the likely production architecture. Rust + Relm4 should be the prototype and production candidate unless early layer-shell or protocol experiments prove it unsuitable.

## Relm4 Feasibility Notes

Relm4 is a practical fit for a panel because the UI is mostly a set of dynamic collections fed by long-lived services. The most relevant Relm4 abstraction is `FactoryVecDeque`, which can represent task buttons, tray icons, pinned app buttons, and start/center/end layout sections without rebuilding the whole panel after every update.

Recommended Relm4 usage:

- Use top-level `Component` instances for the shell, each monitor's panel window, taskbar, tray, and status groups.
- Use `FactoryVecDeque` for dynamic lists: task groups, tray items, and section items.
- Use Relm4 commands or service-owned Tokio tasks for async streams.
- Keep GTK widget mutation on the GLib main thread.
- Use plain `gtk4-rs` directly for low-level details that do not benefit from Relm4 macros.

Areas where plain `gtk4-rs` should be preferred:

- `gtk4-layer-shell` window setup.
- GDK monitor enumeration and hotplug signals.
- CSS providers and live stylesheet replacement.
- Gesture controllers for right click, middle click, and scroll.
- `GtkPopover`, `GtkPopoverMenu`, and focus handling.
- Icon theme lookup, pixbuf/texture conversion, and tray icon rendering.
- Widget allocation reads for minimize rectangles.

Wayle is the strongest reference that Rust + GTK4 + Relm4 + gtk4-layer-shell is viable for a shell-style app. It uses one bar per monitor, `FactoryVecDeque` for sections and tray items, service-backed modules, live config, and Tokio tasks. Adwaita-Lite should copy those architecture lessons, not Wayle's broader shell scope.

GLib/Tokio boundary rule:

- GTK and Relm4 updates run on the main thread.
- D-Bus streams, protocol workers, subprocess watchers, and expensive IO run in services.
- Services emit normalized snapshots or small diffs to Relm4 senders.
- Widgets never open their own D-Bus/protocol connections independently.

## Build And Packaging Strategy

The final panel should be shipped as an internal RPM built in CI. A prototype may build directly from the repo, but long-term image builds should not run live online Cargo resolution.

Recommended path:

| Phase | Build Strategy | Notes |
|---|---|---|
| Prototype | `cargo build --release --locked --offline` from committed source and lockfile | Acceptable if crates are vendored or available from a pinned CI artifact |
| Testing image | CI-built per-arch binary or RPM, installed by checksum or signed internal repo | Keeps bootc image builds faster and less network-sensitive |
| Steady state | Internal `adwaita-lite-panel` RPM | Best install paths, dependency metadata, signing, SBOM, and rollback behavior |
| Upstream-quality | Fedora-style Rust RPM packaging for missing crates | Higher maintenance; useful if the panel becomes reusable outside this image |

Avoid:

- `cargo install` during the image build.
- Online `cargo build` during the image build.
- Depending on crates.io registry state for reproducible bootc builds.

Minimum controls:

- Commit `Cargo.lock`.
- Build with `--locked` and preferably `--offline` or `--frozen`.
- Use `cargo vendor` or a pinned vendor artifact for image builds.
- Review `Cargo.lock` diffs as supply-chain changes.
- Run `cargo audit` and license checks in CI.
- Build native artifacts per architecture rather than cross-compiling GTK/Wayland code unless necessary.
- Dynamically link Fedora system libraries such as GTK4 and `gtk4-layer-shell` rather than vendoring C libraries.

Suggested install layout for an RPM:

```text
/usr/bin/adwaita-lite-panel
/usr/share/adwaita-lite-panel/
/usr/share/applications/adwaita-lite-panel.desktop
/usr/lib/systemd/user/adwaita-lite-panel.service
/usr/share/licenses/adwaita-lite-panel/
/usr/share/doc/adwaita-lite-panel/
```

Use `/usr/libexec/adwaita-lite-panel-*` only for helper binaries that users should not invoke directly. Keep runtime state under `$XDG_RUNTIME_DIR`, `$XDG_STATE_HOME`, or `$XDG_CACHE_HOME`, not `/usr`.

## Protocol Risk Notes

The taskbar should use `zwlr_foreign_toplevel_manager_v1` first because labwc supports the practical control surface we need today. It is still an unstable wlroots protocol, so the panel must feature-detect globals and tolerate compositor-specific behavior.

Risks and mitigations:

| Risk | Mitigation |
|---|---|
| `wlr-foreign-toplevel-management` is unstable and versioned | Bind advertised version and gate optional behavior by version |
| Parent toplevel events require version 3 | Use parent only as an enhancement for dialog suppression |
| `activate`, `close`, and minimize are compositor requests, not guarantees | Request action, then wait for protocol state before updating UI state |
| `app_id` is unreliable for XWayland, Electron, Flatpaks, Chrome PWAs, and some native Wayland apps | Use a layered desktop-file resolver and user override map |
| Multiple windows can share the same `app_id` | Track protocol handles as window identity and group separately by app identity |
| Output enter/leave events have had labwc and XWayland regressions | Model output membership as a set and provide an all-outputs fallback/debug mode |
| Minimize rectangle is only a hint and can protocol-error if invalid | Send only after widget allocation is valid and clear when widgets disappear |
| Layer-shell exclusive-zone behavior depends on anchors and protocol version | Anchor across the full edge and prefer gtk4-layer-shell auto exclusive zone |
| Layer-shell popups/tooltips can be toolkit/compositor-sensitive | Use real GTK popovers attached to panel widgets and keep menus simple |

Future-facing protocols:

- `ext-foreign-toplevel-list-v1` is useful for cleaner listing and stable identifiers, but it is list-only and does not replace wlr control today.
- `xdg-activation-v1` should be used for app launch handoff, not as a replacement for activating existing foreign toplevels.
- Any future `ext` control/state protocol should be runtime-detected, not assumed.

## Accessibility And User-Facing Quality

This panel is always visible and central to the session, so accessibility and polish are release blockers, not follow-ups.

Requirements:

- Use real GTK controls such as `GtkButton`, `GtkMenuButton`, `GtkPopover`, `GtkPopoverMenu`, and `GtkListBox` where possible.
- Every icon-only control must have a localized accessible label.
- Tooltips are not a substitute for accessible labels.
- Pointer-only actions must also be keyboard-reachable.
- `Tab` and `Shift+Tab` should move through controls in logical order.
- `Return` activates buttons, `Space` toggles/taps, `Esc` closes popovers, and `Menu` or `Shift+F10` opens context menus where relevant.
- Popovers should move focus inside when opened and return focus to the trigger when closed.
- Dynamic values such as volume, battery, network, and clock should expose updated accessible text without stealing focus.
- High contrast must use token pairs with adequate contrast and must not rely on color alone.
- Reduced motion must disable non-essential transitions, pulsing, sliding, and blinking.
- Touch targets should remain comfortable even in compact density.
- All user-visible strings, tooltips, accessible labels, notices, and action names must be translatable.
- RTL locales should use GTK start/end direction rather than hard-coded left/right assumptions.

Migration quality requirements:

- Users should keep panel edge, density, theme, accent, high contrast, twilight, clock mode, pinned apps, and module order.
- Existing Adwaita-Lite-generated Waybar files should not be destroyed without backup.
- User-modified Waybar files should be preserved.
- If a behavior changes, show one concise first-login notice rather than repeated warnings.
- A panel crash must not kill labwc or the settings app.
- The panel should run under a systemd user unit with restart policy and backoff.
- Repeated crash loops should leave a clear journal trail and allow a Waybar fallback during testing.

Logging requirements:

- Log startup, version, git/build revision, config path, settings parse failures, migration decisions, D-Bus failures, tray item failures, protocol availability, and crash causes.
- Do not log secrets, full environment dumps, or noisy stack traces unless debug logging is enabled.
- Use stable component names so users can find logs with `journalctl --user -u adwaita-lite-panel`.

## Testing Strategy

Most tests should not require a compositor or visible display. The Rust crate should be split into pure model modules and thin GTK/Wayland/D-Bus adapters.

Recommended layers:

| Layer | What To Test |
|---|---|
| Pure unit tests | settings validation, theme tokens, layout normalization, app identity, status reducers |
| Protocol model tests | toplevel event batching, output sets, parent/dialog handling, grouping, action requests |
| D-Bus mock tests | UPower battery, StatusNotifier watcher/items, logind brightness, NetworkManager if added |
| GTK tests | CSS parser, widget construction, classes, accessible labels, keyboard focus basics |
| Optional compositor smoke | labwc or Weston nested startup, layer-shell surfaces, edge/orientation behavior |
| Performance checks | idle CPU, RSS/PSS, startup time, event-churn stability |

Taskbar protocol tests should use internal events that mirror foreign-toplevel events:

```text
Created
Title
AppId
State
OutputEnter
OutputLeave
Parent
Done
Closed
```

Important assertions:

- Property events do not update visible model until `Done`.
- Activate/minimize/close enqueue adapter requests but do not mutate state until compositor confirmation.
- Pinned apps merge with running app groups.
- Dialog children do not become primary taskbar buttons when parent data is available.
- Per-output filtering includes windows visible on multiple outputs.

D-Bus testing options:

- Use `zbus::ObjectServer` for in-process mock services.
- Use `dbusmock` private or P2P buses for tests that need bus-like behavior.
- Mock UPower display device, StatusNotifier watcher/items, DBusMenu layout, logind `SetBrightness`, and NetworkManager later.

GTK/CSS tests:

- Use `gtk4::CssProvider` and fail on `parsing-error`.
- Keep CSS tests GTK4-specific; the existing repo's GTK3 CSS parser helper is only relevant to Waybar.
- Skip display-backed tests cleanly when GTK cannot initialize.
- Use deterministic render settings for smoke tests where possible.

Compositor smoke tests:

- Make them optional or nightly at first.
- Weston headless can validate basic Wayland startup behavior.
- Nested labwc is the real target and should become the meaningful integration smoke once stable.
- Cage is useful for one-app startup checks but less representative for a desktop panel.

Performance gates should be based on real hardware eventually, especially 2 GB Chromebook-class devices. Track RSS/PSS, idle CPU, startup time, and memory growth over event churn.

## Source-Code Review Lessons

The docs and protocol references are not enough. The actual source code of Wayle, Waybar, sfwbar, Ironbar, gtk4-layer-shell examples, and wf-shell shows several implementation patterns that should directly shape Adwaita-Lite's design.

### Wayle

Wayle is the closest architecture reference for a Rust + GTK4 + Relm4 shell, but it is broader than Adwaita-Lite should be.

Useful patterns:

- Keep CLI startup separate from GUI shell startup. Wayle's CLI starts the same binary in a shell mode and detaches stdio, while the shell path owns Tokio, tracing, services, and Relm4.
- Use an owner/root component that is not the visible bar. Wayle keeps a root shell controller and launches one bar controller per monitor.
- Key bars by connector name, not transient monitor indexes.
- Treat GDK monitor connector availability as racy. Wayle retries monitor synchronization when monitor count and connector metadata disagree.
- Use one `FactoryVecDeque` per bar section and another factory inside dynamic modules such as tray.
- Rebuild sections by moving/removing/inserting only what changed, not by clearing the whole section. This preserves stateful modules.
- Treat services as optional and degrade modules when a service is unavailable.
- Bootstrap services in parallel, then pass shared service handles to modules.
- Bind watchers to component shutdown or cancellation tokens.
- After CSS reload, be prepared to force a layer-shell reconfigure if GTK/layer-shell sizing does not update naturally.

Pitfalls to avoid:

- Do not make a physical panel window the app root.
- Do not assume GDK monitors have connector names immediately.
- Do not leave factory-child watchers running after a tray item/task button is removed.
- Do not let config watchers duplicate initial setup events without guarding or intentionally handling first emissions.

### Waybar

Waybar is the strongest reference for mature wlroots taskbar and StatusNotifier behavior.

Useful taskbar patterns:

- Bind `zwlr_foreign_toplevel_manager_v1` and `wl_seat` separately; degrade if either is missing.
- Clamp the protocol version to what the client bindings support.
- Gate optional protocol requests by server version.
- Treat taskbar membership as output-specific unless all-outputs mode is enabled.
- Maintain stable synthetic task IDs for UI bookkeeping.
- Apply title, app ID, state, and output changes on protocol `done`, not on each individual event.
- Use `set_rectangle` before minimize to hint compositor animation origin.
- Remove the task only when `closed` arrives.
- Include app-id mapping/override support because real apps report inconsistent IDs.
- Log missing icons and fall back; never make icon lookup fatal.

Useful SNI/tray patterns:

- Implement both watcher and host. Waybar owns `org.kde.StatusNotifierWatcher` and creates host names per tray instance.
- Accept SNI item registration in both bus-name and object-path forms.
- Ignore duplicate item registration.
- Watch item bus names and remove vanished items.
- Read cached properties first, then subscribe to signals.
- Treat missing required item properties as invalid item data, not panel failure.
- Debounce item update signals before fetching changed properties.
- Support `Active`, `Passive`, and `NeedsAttention` states as CSS classes.
- Hide passive items unless configured otherwise, but do not remove them.
- Icon priority should cover attention icons, icon names/files, icon pixmaps, and fallback icons.
- Convert SNI pixmaps from ARGB to RGBA and support overlay icons.
- Follow SNI click conventions: left activate or menu, middle secondary activate, right context menu, scroll calls `Scroll`.

Useful status module patterns:

- PulseAudio should be event-driven and reconnect-capable.
- Backlight should read sysfs but write through logind `SetBrightness`.
- Battery handling must tolerate multiple batteries, missing capacity files, odd units, negative current, and repeated event suppression.
- Clock updates should align to interval boundaries rather than ticking wastefully.
- CSS reload should watch imports and symlinks deliberately if we support external CSS files.

Pitfalls to avoid:

- Do not mutate UI from backend callbacks; send typed messages to the UI thread.
- Do not assume `app_id` arrives before title.
- Do not assume every compositor supports every toplevel request.
- Do not treat broken tray clients as fatal.
- Do not do real reload work inside signal handlers.
- Do not leak old monitor handlers, D-Bus watches, file monitors, or worker threads on reload.

### sfwbar

sfwbar is GTK3/C/GPL-3 and not a source to copy directly, but its architecture is valuable.

Useful patterns:

- Normalize compositor-specific window data into a central model layer, then let taskbar UI listen to model events.
- Keep runtime identity as the protocol handle or model object, not the app ID.
- Treat grouping as a pluggable view strategy over the same window model.
- `ext-foreign-toplevel-list-v1` can provide stable IDs for future use, but it does not replace wlr toplevel control.
- Treat app-id changes as a model migration that may require removing/readding UI grouping state.
- Implement SNI watcher/host compatibility for both KDE and freedesktop namespaces if testing proves it necessary.
- DBusMenu should call `AboutToShow`, then `GetLayout` when refresh is requested.
- Use cancellable async D-Bus calls and cancel them when tray items disappear.
- Backlight policy should keep hardware values and UI step/min/max policy separate.
- Layer-shell anchor and exclusive-zone logic should be centralized in panel window code.
- Popups/menus need lifetime tracking so autohide or focus changes do not collapse the bar unexpectedly.

Pitfalls to avoid:

- Do not directly port GTK3 event boxes, menus, or event masks to GTK4. Use GTK4 gestures, controllers, and popovers.
- Do not assume DBusMenu incremental updates are optional forever; full refresh is a first phase, not complete parity.
- Do not let mirrored or per-monitor panels duplicate global state incorrectly.

### Ironbar

Ironbar is the closest off-the-shelf conceptual match, and its GTK4 tray migration is especially useful.

Useful patterns:

- Keep GTK on the GLib main thread and push IO/client work into Tokio tasks.
- Give every module explicit service-to-UI and UI-to-service message types.
- Inject shared clients/services through a context object rather than letting modules create global state independently.
- Preseed launcher favorites as persistent closed items, then merge running windows into them.
- Build a `StartupWMClass` to favorite/app-id map from desktop files.
- Keep favorite buttons after the last window closes; clear open/focused classes instead of removing the button.
- Cache tray menu connect/menu payloads so later tray instances or reloads can hydrate correctly.
- Build GTK4 tray menus using `gio::MenuModel`, action groups, or custom popovers rather than GTK3 DBusMenu assumptions.
- Load tray icons asynchronously into stable `Picture` widgets so the widget tree does not churn.
- Use rolling file logs, environment-controlled verbosity, panic hooks, and GLib log bridging.
- Keep IPC/reload typed and structured; reload bars/config while preserving the process where possible.

Pitfalls to avoid:

- Do not rely on app IDs alone; normalize through desktop files and Flatpak/XWayland heuristics.
- Do not rebuild tray state from only the latest event; late subscribers need cached menu/item state.
- Do not let CSS hot reload append unbounded providers or watchers.
- Do not silently hide config failures during development; production fallback should still log clearly.

### gtk4-layer-shell And wf-shell

The exact layer-shell call order matters.

Recommended setup order:

1. Create `gtk::ApplicationWindow`.
2. Call `init_layer_shell()` before first realize/map/present.
3. Set namespace, monitor, layer, keyboard mode, anchors, margins, and exclusive zone before present.
4. Set child widgets.
5. Present the window.

For a horizontal bottom panel:

```rust
window.init_layer_shell();
window.set_namespace(Some("adwaita-lite-panel"));
window.set_monitor(Some(&monitor));
window.set_layer(gtk4_layer_shell::Layer::Top);
window.set_keyboard_mode(gtk4_layer_shell::KeyboardMode::None);
window.set_anchor(gtk4_layer_shell::Edge::Bottom, true);
window.set_anchor(gtk4_layer_shell::Edge::Left, true);
window.set_anchor(gtk4_layer_shell::Edge::Right, true);
window.auto_exclusive_zone_enable();
```

Important caveats:

- The C `gtk4-layer-shell` library must load before `libwayland-client` because it shims Wayland symbols.
- If the Rust app also links `wayland-client` directly, verify load order with `ldd` or `LD_DEBUG=libs` during spikes.
- Use `LD_PRELOAD=libgtk4-layer-shell.so` only as a diagnostic or temporary workaround.
- Autohide should not reserve a normal exclusive zone while hidden.
- `set_monitor(Some(&monitor))` should happen before presenting; remapping a mapped layer-shell window can be compositor-sensitive.

## Implementation Rules From Source Review

- Centralize external state in services and models; widgets are views/controllers, not backend owners.
- All backend callbacks must cross into Relm4 through typed messages.
- Preserve model state across layout/CSS reloads where possible.
- Use snapshots for simple services and diffs for high-churn identity-sensitive collections such as taskbar and tray.
- Define CSS class names early and treat them as a stable API.
- Treat Wayland globals, D-Bus services, tray clients, PulseAudio, batteries, backlights, and monitors as disappearing/reappearing resources.
- Debounce bursty sources: tray property signals, config file changes, CSS reloads, smooth scroll, and battery/audio events.
- Make cleanup deterministic: protocol objects, D-Bus watches, file monitors, popovers, menu actions, accelerators, Tokio tasks, and factory children all need ownership and drop/cancel paths.
- Build a debug surface for app identity matching and tray failures early; these are the areas users will report as “wrong icon” or “tray app missing.”

The panel should expose stable CSS classes rather than relying on deep GTK widget selectors:

- `.adwaita-lite-panel`
- `.section-start`, `.section-center`, `.section-end`
- `.launcher-button`
- `.taskbar`, `.task-button`, `.task-button.open`, `.task-button.focused`, `.task-button.minimized`, `.task-button.pinned`, `.task-button.multi-window`
- `.status-group`, `.status-button`, `.volume`, `.brightness`, `.battery`, `.clock`, `.tray`
- `.needs-attention`, `.warning`, `.critical`, `.muted`

## Layer-Shell Lessons

Use `gtk4-layer-shell` directly.

Default geometry:

- Layer: `top`.
- Keyboard mode: `none`.
- Horizontal bottom panel: anchors `bottom`, `left`, `right`.
- Horizontal top panel: anchors `top`, `left`, `right`.
- Vertical left panel: anchors `left`, `top`, `bottom`.
- Vertical right panel: anchors `right`, `top`, `bottom`.
- Enable auto exclusive zone for an always-visible panel.
- Create one panel window per monitor.
- Set the target monitor explicitly before presenting the window.

Avoid using labwc `<margin>` for the panel. That setting is a workaround for clients that do not support layer-shell. A real layer-shell panel should reserve its own exclusive zone.

Python GI load-order warning:

```python
from ctypes import CDLL
CDLL("libgtk4-layer-shell.so")

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
```

This mirrors gtk4-layer-shell's guidance: the layer-shell shim must load before Wayland client usage. A native implementation should link `gtk4-layer-shell` correctly rather than relying on `LD_PRELOAD`.

## Taskbar Lessons

Use `zwlr_foreign_toplevel_manager_v1` as the primary labwc/wlroots taskbar protocol. It provides toplevel creation/removal, title, `app_id`, output membership, state, parent, activation, minimize/maximize/fullscreen/close, and minimize rectangle hints.

Model:

```text
Toplevel
  handle
  raw_app_id
  resolved_app_id
  desktop_id
  title
  outputs
  parent
  children
  state: active/minimized/maximized/fullscreen

AppGroup
  resolved_app_id
  desktop metadata
  windows
  pinned
```

Recommendations:

- Batch protocol events and update UI on `done`, not every individual field update.
- Resolve app identity through a desktop-file index.
- Group windows by resolved app identity from day one.
- Hide or nest child dialogs under their parent rather than rendering every dialog as a primary taskbar button.
- Keep one visible group per app per output, unless an `all_outputs` setting is introduced.
- Set the minimize rectangle from the GTK widget allocation before minimize/unminimize requests.
- Treat protocol actions as requests; wait for compositor state events before assuming success.

App matching order:

1. User override map from raw `app_id` or WM class to desktop ID.
2. Exact desktop ID: `app_id.desktop`.
3. Exact `StartupWMClass`.
4. Case-insensitive desktop basename.
5. Reverse-DNS suffix fallback, such as `org.mozilla.firefox` to `firefox`.
6. Flatpak desktop ID forms.
7. Icon lookup by raw `app_id`.
8. Generic app icon and title fallback.

Default click behavior to test:

- Pinned app with no windows: launch.
- Inactive app with one or more windows: activate most recent or first non-focused window.
- Focused app with a single window: minimize.
- Grouped app with multiple windows: open a small window picker popover, then activate selected window.
- Middle click: close focused/selected window if parity with Waybar remains desired, or launch a new instance if we intentionally choose Ironbar-like behavior.

## Pinned Apps

Adwaita-Lite pins are richer than Ironbar favorites because they support arbitrary command strings plus icon metadata. A native panel can preserve this while improving behavior.

Recommendation:

- Keep the existing `pinned` settings schema.
- Build pinned app groups from `desktop_id`, `app_id`, `startup_wm_class`, and command-derived fallback identity.
- Merge a pinned app button with running windows when identity matches.
- Use `Gio.DesktopAppInfo` and existing command/icon metadata for launch.
- Store match reason in debug logs so bad Flatpak/Electron/XWayland matching can be fixed with overrides.

This eliminates Waybar's redundant separate pinned image modules when the app is running.

## Tray Lessons

Tray support is D-Bus, not a Wayland protocol. A panel usually needs to be both a `StatusNotifierHost` and, in minimal labwc sessions, a `StatusNotifierWatcher` if no other watcher exists.

Protocols and interfaces:

- `org.kde.StatusNotifierWatcher`
- `org.kde.StatusNotifierHost-*`
- `org.kde.StatusNotifierItem`
- `com.canonical.dbusmenu`

Implementation phases:

1. Own/export `org.kde.StatusNotifierWatcher` only if no watcher exists.
2. Register a panel host and track registered items.
3. Render basic icons from `IconName` or `IconPixmap`.
4. Hide `Passive` items and style `NeedsAttention` items.
5. Forward left, middle, right, and scroll events to SNI methods.
6. Add DBusMenu rendering with a GTK4 `GtkPopover`.
7. Add `AboutToShow`, `LayoutUpdated`, check/radio/separator/submenu support.

Defer advanced DBusMenu behavior until after the basic tray is useful:

- menu item icons next to labels
- keyboard accelerators
- unusual vendor extensions
- perfect `ItemPropertiesUpdated` handling
- duplicate `org.freedesktop.*` namespace compatibility

GTK4 caveat: there is no GTK4 equivalent to `libdbusmenu-gtk3`. Waybar's GTK3 menu path is not portable. Ironbar's GTK4 migration and sfwbar's manual DBusMenu code suggest a custom GTK4 popover is the safer path.

## Status Module Lessons

Use event-driven services where practical. Avoid frequent polling and repeated process spawning.

| Module | Backend | Update Model | MVP |
|---|---|---|---|
| Launcher | existing `adwaita-lite-app-menu` | none | button launches current app menu |
| Audio | `pactl subscribe` first, libpulse async later | event stream, coalesced updates | icon, muted state, percent tooltip, scroll 5%, click `pavucontrol` |
| Brightness | `/sys/class/backlight` read, logind `SetBrightness` write | file monitor or low-rate fallback | icon, percent tooltip, scroll 5% |
| Battery | UPower `DisplayDevice` | D-Bus `PropertiesChanged` | icon, charging, warning/critical, percent tooltip |
| Clock | GLib time | one timeout aligned to minute | 12/24h text, date tooltip, optional calendar popover |
| Tray | SNI/DBusMenu | D-Bus | basic icons and input forwarding first |
| Network | NetworkManager D-Bus or lazy `NM.Client` | D-Bus | optional later, current Adwaita-Lite does not default-show it |

## GTK4 CSS Guidelines

Stay inside a conservative GTK4-compatible subset:

- Use `@define-color`, hex colors, `rgb()`, and `rgba()`.
- Use `background-color`, `color`, `border`, `border-radius`, `padding`, `margin`, `min-width`, `min-height`, `font-family`, `font-size`, `font-weight`.
- Use simple selectors: class, ID, GTK node, descendant, child, `:hover`, `:checked`, `:disabled`, `:first-child`, `:last-child`.
- Use transitions sparingly and verify with GTK4 on the target image.
- Use transforms only for tested cases such as vertical text/icon rotation.

Avoid:

- Browser layout CSS such as `display`, `flex`, `grid`, `position`, `z-index`.
- Browser pseudo-elements such as `::before` and `::after`.
- CSS variables if compatibility below GTK 4.16 matters.
- Media queries if compatibility below GTK 4.20 matters.
- Unquoted `url()` values.
- Deep selectors that depend on GTK internals rather than our named widgets/classes.

## Minimal Viable Panel Phases

### Phase 1: Static Shell

- Start under labwc.
- Create one gtk4-layer-shell panel per monitor.
- Read Adwaita-Lite settings and theme tokens.
- Render start/center/end sections from the existing layout model.
- Implement launcher, clock, and static inactive widgets that reserve the status/tray/taskbar slots.

### Phase 2: Status Modules

- Implement audio, brightness, battery, clock tooltip/calendar, and settings refresh.
- Match current icon-only behavior first.
- Apply accent, high contrast, twilight, compact/normal density, and horizontal/vertical geometry.

### Phase 3: Taskbar And Pins

- Implement foreign-toplevel tracking.
- Implement desktop app identity resolver.
- Merge pins with running app groups.
- Implement activate/minimize/close/window picker behavior.

### Phase 4: Tray

- Implement SNI watcher/host and basic icons.
- Add input forwarding.
- Add DBusMenu popovers progressively.

### Phase 5: Replace Waybar In Testing

- Add a panel backend setting or testing-only switch.
- Preserve a Waybar fallback until the GTK4 panel survives real hardware testing.
- Compare memory, CPU, startup time, and behavior against Waybar.

## Open Decisions

- Confirm Rust + Relm4 can initialize gtk4-layer-shell cleanly and create one panel surface per monitor.
- Decide whether to vendor/pin the Rust `gtk4-layer-shell` binding via Cargo or package it separately later.
- Whether middle-click should close windows for Waybar parity or launch new instances like Ironbar.
- Whether multi-window app groups open a picker on left click, hover, or secondary click.
- Whether to implement tray before taskbar or vice versa.
- Whether to keep a hidden Waybar fallback in testing images during the transition.
- Whether the settings UI should expose `panel_backend` while the experiment is underway.

## Source References

Taskbar and layer-shell:

- Waybar wlr taskbar: https://github.com/Alexays/Waybar/blob/master/src/modules/wlr/taskbar.cpp
- Waybar taskbar header: https://github.com/Alexays/Waybar/blob/master/include/modules/wlr/taskbar.hpp
- Waybar taskbar app-id discussion: https://github.com/Alexays/Waybar/pull/692
- Waybar protocol v3 parent discussion: https://github.com/Alexays/Waybar/pull/934
- Ironbar launcher docs: https://ironb.ar/modules/launcher
- Ironbar launcher source: https://github.com/JakeStanger/ironbar/blob/master/src/modules/launcher/mod.rs
- Ironbar launcher item model: https://github.com/JakeStanger/ironbar/blob/master/src/modules/launcher/item.rs
- Ironbar launcher open state: https://github.com/JakeStanger/ironbar/blob/master/src/modules/launcher/open_state.rs
- sfwbar foreign toplevel source: https://github.com/LBCrion/sfwbar/blob/main/src/ipc/foreign-toplevel.c
- sfwbar ext foreign toplevel source: https://github.com/LBCrion/sfwbar/blob/main/src/ipc/ext-ftl.c
- sfwbar window model: https://github.com/LBCrion/sfwbar/blob/main/src/wintree.c
- sfwbar taskbar shell: https://github.com/LBCrion/sfwbar/blob/main/src/gui/taskbarshell.c
- sfwbar taskbar source: https://github.com/LBCrion/sfwbar/blob/main/src/gui/taskbaritem.c
- sfwbar taskbar popup: https://github.com/LBCrion/sfwbar/blob/main/src/gui/taskbarpopup.c
- wf-shell window-list source: https://github.com/WayfireWM/wf-shell/blob/master/src/panel/widgets/window-list/toplevel.cpp
- wf-shell app/monitor lifecycle: https://github.com/WayfireWM/wf-shell/blob/master/src/util/wf-shell-app.cpp
- wf-shell autohide behavior: https://github.com/WayfireWM/wf-shell/blob/master/src/util/wf-autohide-window.cpp
- wlr foreign toplevel protocol: https://wayland.app/protocols/wlr-foreign-toplevel-management-unstable-v1
- wlr layer shell protocol: https://wayland.app/protocols/wlr-layer-shell-unstable-v1
- gtk4-layer-shell docs: https://wmww.github.io/gtk4-layer-shell/gtk4-layer-shell-GTK4-Layer-Shell.html
- gtk4-layer-shell simple C example: https://github.com/wmww/gtk4-layer-shell/blob/main/examples/simple-example.c

Tray:

- Waybar SNI watcher: https://github.com/Alexays/Waybar/blob/master/src/modules/sni/watcher.cpp
- Waybar SNI host: https://github.com/Alexays/Waybar/blob/master/src/modules/sni/host.cpp
- Waybar SNI item: https://github.com/Alexays/Waybar/blob/master/src/modules/sni/item.cpp
- Waybar SNI tray: https://github.com/Alexays/Waybar/blob/master/src/modules/sni/tray.cpp
- Ironbar GTK4 migration notes: https://ironb.ar/guides/gtk4
- Ironbar tray docs: https://ironb.ar/modules/tray
- Ironbar tray client: https://github.com/JakeStanger/ironbar/blob/master/src/clients/tray.rs
- Ironbar tray module: https://github.com/JakeStanger/ironbar/blob/master/src/modules/tray/mod.rs
- Ironbar tray interface: https://github.com/JakeStanger/ironbar/blob/master/src/modules/tray/interface.rs
- Ironbar tray icon handling: https://github.com/JakeStanger/ironbar/blob/master/src/modules/tray/icon.rs
- SFWBar SNI source: https://github.com/LBCrion/sfwbar/blob/main/src/sni.c
- SFWBar SNI item source: https://github.com/LBCrion/sfwbar/blob/main/src/sniitem.c
- SFWBar DBusMenu source: https://github.com/LBCrion/sfwbar/blob/main/src/snimenu.c
- SFWBar tray item source: https://github.com/LBCrion/sfwbar/blob/main/src/gui/trayitem.c
- GTK4 PopoverMenu: https://docs.gtk.org/gtk4/class.PopoverMenu.html
- Ayatana appindicator GLib: https://github.com/AyatanaIndicators/libayatana-appindicator-glib

Status modules and APIs:

- UPower D-Bus: https://upower.freedesktop.org/docs/UPower.html
- NetworkManager D-Bus: https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html
- systemd-logind D-Bus: https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html
- GIO DBusProxy: https://docs.gtk.org/gio/class.DBusProxy.html
- GTK4 Calendar: https://docs.gtk.org/gtk4/class.Calendar.html
- GLib timeout: https://docs.gtk.org/glib/func.timeout_add_seconds.html
- GioUnix DesktopAppInfo: https://docs.gtk.org/gio-unix/class.DesktopAppInfo.html
- Waybar PulseAudio module: https://github.com/Alexays/Waybar/wiki/Module:-PulseAudio
- Waybar PulseAudio source: https://github.com/Alexays/Waybar/blob/master/src/modules/pulseaudio.cpp
- Waybar audio backend: https://github.com/Alexays/Waybar/blob/master/src/util/audio_backend.cpp
- Waybar Backlight module: https://github.com/Alexays/Waybar/wiki/Module:-Backlight
- Waybar backlight source: https://github.com/Alexays/Waybar/blob/master/src/modules/backlight.cpp
- Waybar backlight backend: https://github.com/Alexays/Waybar/blob/master/src/util/backlight_backend.cpp
- Waybar Battery module: https://github.com/Alexays/Waybar/wiki/Module:-Battery
- Waybar battery source: https://github.com/Alexays/Waybar/blob/master/src/modules/battery.cpp
- Waybar Clock module: https://github.com/Alexays/Waybar/wiki/Module:-Clock
- Waybar clock source: https://github.com/Alexays/Waybar/blob/master/src/modules/clock.cpp
- sfwbar backlight config source: https://github.com/LBCrion/sfwbar/blob/main/config/backlight.source
- sfwbar battery config source: https://github.com/LBCrion/sfwbar/blob/main/config/battery.source
- sfwbar network widget: https://github.com/LBCrion/sfwbar/blob/main/config/network.widget
- sfwbar PulseAudio module: https://github.com/LBCrion/sfwbar/blob/main/modules/pulsectl.c

Rust, Relm4, and packaging:

- Relm4 book: https://relm4.org/book/stable/
- Relm4 factory collections: https://relm4.org/book/stable/efficient_ui/factory.html
- Relm4 commands and async: https://relm4.org/book/stable/threads_and_async/commands.html
- Relm4 API docs: https://relm4.org/docs/stable/relm4/
- Rust gtk4-layer-shell crate: https://docs.rs/crate/gtk4-layer-shell/latest
- gtk4-layer-shell Rust example: https://github.com/pentamassiv/gtk4-layer-shell-gir/blob/main/gtk4-layer-shell/examples/simple-example.rs
- Relm4 layer-shell example: https://github.com/pentamassiv/relm4_layer_shell_example
- Wayle shell reference: https://github.com/wayle-rs/wayle
- Wayle shell startup: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/lib.rs
- Wayle shell root: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/mod.rs
- Wayle monitor handling: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/helpers/monitors.rs
- Wayle bar component: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/bar/mod.rs
- Wayle bar factories: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/bar/factory.rs
- Wayle bar layout methods: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/bar/methods.rs
- Wayle watcher helpers: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-widgets/src/watchers.rs
- Wayle systray module: https://github.com/wayle-rs/wayle/blob/master/crates/wayle-shell/src/shell/bar/modules/systray/mod.rs
- Cargo lockfile guidance: https://doc.rust-lang.org/cargo/guide/cargo-toml-vs-cargo-lock.html
- Cargo vendor: https://doc.rust-lang.org/cargo/commands/cargo-vendor.html
- Cargo source replacement: https://doc.rust-lang.org/cargo/reference/source-replacement.html
- Cargo offline/frozen behavior: https://doc.rust-lang.org/cargo/commands/cargo-fetch.html
- Fedora Rust packaging guidelines: https://docs.fedoraproject.org/en-US/packaging-guidelines/Rust/
- bootc image build guidance: https://bootc-dev.github.io/bootc/building/guidance.html

Accessibility, UX, and tests:

- GTK4 accessibility overview: https://docs.gtk.org/gtk4/section-accessibility.html
- GTK accessible properties: https://docs.gtk.org/gtk4/enum.AccessibleProperty.html
- GTK reduced motion: https://docs.gtk.org/gtk4/property.Settings.gtk-interface-reduced-motion.html
- GNOME HIG accessibility: https://developer.gnome.org/hig/guidelines/accessibility.html
- GNOME HIG keyboard: https://developer.gnome.org/hig/guidelines/keyboard.html
- GNOME HIG pointer and touch: https://developer.gnome.org/hig/guidelines/pointer-touch.html
- GNOME HIG popovers: https://developer.gnome.org/hig/patterns/containers/popovers.html
- GTK CssProvider parsing errors: https://docs.gtk.org/gtk4/signal.CssProvider.parsing-error.html
- zbus object server: https://docs.rs/zbus/latest/zbus/object_server/index.html
- dbusmock: https://docs.rs/dbusmock/latest/dbusmock/
- Weston headless backend: https://wayland.pages.freedesktop.org/weston/toc/running-weston.html
- insta snapshot testing: https://github.com/mitsuhiko/insta
- hyperfine benchmarking: https://github.com/sharkdp/hyperfine

Packaging/reference panels:

- Ironbar repository: https://github.com/JakeStanger/ironbar
- wf-shell repository: https://github.com/WayfireWM/wf-shell
- sfwbar repository: https://github.com/LBCrion/sfwbar
- nwg-panel repository: https://github.com/nwg-piotr/nwg-panel
- quickshell: https://quickshell.org/
