# Settings App Menu Deferred Apply Design

## Context

Panel-related Settings changes now defer Waybar reloads until session restart. That fixed Settings crashes caused by live Waybar reloads, but exposed a related start menu bug: `adwaita-lite-app-menu` reads `~/.config/adwaita-lite/settings.json` every time it starts. Settings writes future panel values to that file immediately, while the running Waybar panel keeps its old in-memory geometry until the next session. The start menu can therefore anchor, size, or theme itself from new values against an old live panel, producing a broken menu.

The start menu currently consumes these Settings values:

- `edge`
- `layout`
- `density`
- `panel_twilight`
- `theme`
- `accent`
- `high_contrast`
- `font_size`
- `scale`

## Approaches Considered

1. Session-start snapshot for start-menu inputs. Create a per-session copy of `settings.json` before labwc starts and teach `adwaita-lite-app-menu` to read it when available. This is the selected approach because it keeps Settings persistence simple and guarantees the menu matches the live panel for the whole session.

2. Keep unsafe panel settings out of `settings.json` until restart. This would make `settings.json` represent the live session, but it requires pending-setting storage, Settings UI reconciliation, restore-defaults changes, and more failure modes.

3. Filter only panel-coupled keys inside the start menu. The menu would read some values from a stable source and some from live `settings.json`. This is smaller than approach 2 but still risks mixed theme/geometry state and is harder to explain.

## Selected Design

Each Adwaita-Lite session has a stable start-menu settings snapshot. `adwaita-lite-session` continues running `adwaita-lite-apply-settings --mode=config` before starting labwc. After that config pass, it copies `~/.config/adwaita-lite/settings.json` to `${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json` and exports the path as `ADWAITA_LITE_SESSION_SETTINGS` before `exec labwc`.

`adwaita-lite-app-menu` resolves its settings path in this order:

1. `ADWAITA_LITE_SESSION_SETTINGS`, if set and readable.
2. `${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json`, if readable.
3. `~/.config/adwaita-lite/settings.json` as a fallback outside a normal Adwaita-Lite session.

The menu continues loading settings at startup, but those settings now represent the session-start state. Settings can still write new panel values and dispatch the existing detached Waybar config writer. The visible panel and the start menu both stay on the same session state until logout/login or restart.

## Data Flow

Session start:

1. `adwaita-lite-session` runs `adwaita-lite-apply-settings --mode=config`.
2. The config pass ensures and sanitizes `settings.json` and writes static session config files.
3. `adwaita-lite-session` copies the resulting `settings.json` to the runtime session snapshot.
4. `adwaita-lite-session` exports `ADWAITA_LITE_SESSION_SETTINGS` and starts labwc.
5. Waybar and labwc-launched `adwaita-lite-app-menu` inherit the snapshot path.

Settings change during the session:

1. Settings writes new values to `settings.json`.
2. Deferred panel/Waybar paths update future Waybar files but do not reload Waybar.
3. The start menu keeps reading the session snapshot, so it does not switch to future panel geometry or theme early.
4. The next session start creates a fresh snapshot from the updated `settings.json`.

## Error Handling

- If snapshot creation fails, `adwaita-lite-session` logs to stderr and continues to labwc so login is never blocked.
- If the exported snapshot path is missing or invalid, the start menu falls back to the existing `settings.json` behavior.
- Invalid JSON handling remains unchanged: `_load_settings()` returns `{}` and existing defaults in menu geometry/theme helpers apply.

## Tests

- Add a failing app-menu test proving `_load_settings()` prefers `ADWAITA_LITE_SESSION_SETTINGS` over the live settings file.
- Add a failing app-menu test proving the runtime snapshot fallback is used before `settings.json` when no environment variable is set.
- Add a launcher/session script test proving `adwaita-lite-session` exports `ADWAITA_LITE_SESSION_SETTINGS` and creates the snapshot after the config apply pass but before `exec labwc`.
- Keep existing app-menu CSS and metrics tests green.

## Non-Goals

- Do not delay writes to `settings.json`.
- Do not add a pending-settings model.
- Do not live-reload Waybar or restart the start menu.
- Do not change the user-facing restart-session language unless tests show the existing copy is inaccurate.
