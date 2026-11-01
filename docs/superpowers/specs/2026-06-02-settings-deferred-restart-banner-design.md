# Settings Deferred Restart Banner Design

## Context

Panel and start-menu settings are now deferred until session restart. Settings writes the future values immediately, while the live Waybar panel and app-menu session snapshot keep using session-start state. This prevents crashes and broken mixed-state UI, but users need a clear in-app action once deferred changes exist.

Current behavior only provides local page descriptions and transient toasts:

- Panel page description: `Panel changes apply after you restart your session.`
- Appearance accent description: same panel restart notice.
- Waybar save toast: `Panel changes saved. Restart your session to apply them.`

There is no persistent global action that survives closing and reopening Settings in the same session.

## Goals

- Show a modern Adwaita-style restart affordance only when deferred session changes are pending.
- Let users restart the current labwc session from Settings after confirmation.
- Keep the pending state robust across Settings app restarts in the same login session.
- Translate all new user-visible Settings strings and compile `.mo` catalogs.
- Avoid live-reloading Waybar or restarting only the Settings app.

## Approaches Considered

1. Global `Adw.Banner` in the Settings content area. This is the selected approach because Adwaita banners are designed for app-wide, actionable status. It is discoverable, works in wide and collapsed layouts, and avoids duplicating controls on individual pages.

2. Headerbar-only restart button. This is compact, but less discoverable and less explanatory. It also competes with search and window controls.

3. Per-page action rows on Panel and Appearance. This is clear locally, but duplicates UI, misses future deferred settings on other pages, and does not provide a single app-wide pending state.

## Selected Design

Add an app-wide `Adw.Banner` to `SettingsWindow`. Place it in the content `Adw.ToolbarView` below the header/search bars so it belongs to the active settings content, not the sidebar.

Banner copy:

- Title: `Restart your session to apply panel and start menu changes.`
- Button label: `Restart Session`

The banner is visible when current settings differ from the session-start snapshot for any deferred key. It is hidden when values match the snapshot again, so reverting a change removes the restart prompt. This comparison must not rely only on an in-memory flag so the banner remains correct if the user closes and reopens Settings before restarting the session.

Deferred keys:

- `edge`
- `layout`
- `density`
- `pinned`
- `panel_twilight`
- `accent`
- `theme`
- `high_contrast`
- `font_size`
- `scale`

The session snapshot source is the same file used by the app-menu work: `ADWAITA_LITE_SESSION_SETTINGS` if set, otherwise `${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json`. If no readable session snapshot exists, Settings treats this as no pending deferred changes so the banner does not show on non-Adwaita-Lite sessions or broken snapshot setups.

## Restart Flow

Clicking `Restart Session` opens an `Adw.AlertDialog` confirmation.

Dialog copy:

- Heading: `Restart Session?`
- Body: `This will close your apps and return you to the sign-in screen.`
- Cancel response: `Cancel`
- Confirm response: `Restart Session`

The confirm response uses destructive styling because it exits the user session. Confirming runs `labwc --exit` with stdin/stdout/stderr detached. This matches the app-menu logout action and restarts the session through the display manager rather than trying to reload Waybar or respawn Settings.

If `labwc --exit` cannot be started, Settings shows an error toast:

- `Could not restart session: {detail}`

Settings does not clear the banner after launching `labwc --exit`; the session should end. If it does not, the pending-state comparison remains accurate.

## Data Flow

1. `SettingsWindow` creates the banner during window construction and wires the action to the confirmation dialog.
2. `SettingsWindow` asks `SettingsStore` whether deferred session changes are pending.
3. `SettingsStore` compares current in-memory settings against the session-start snapshot for the deferred keys.
4. SettingsStore write paths refresh the deferred-change state after successful writes, including `save_and_apply()`, `save_dict_and_apply()`, `restore_keys()`, and flushed debounced writes.
5. When deferred Waybar-mode changes occur, the existing toast still appears and the banner becomes visible.
6. When Settings is reopened, the initial comparison recreates the same pending-state banner without requiring prior app state.

## Error Handling

- Missing or invalid session snapshot: hide the banner and continue normally.
- Missing current settings file: compare using the in-memory store data already loaded by Settings.
- Failure to start `labwc --exit`: show the error toast and keep Settings open.
- Any pending apply work from non-deferred settings remains governed by existing `wait_for_apply()` behavior; the restart-session button itself does not wait for unrelated applies because the deferred session files are already written by the detached Waybar path.

## Tests

- SettingsStore test: detects deferred changes by comparing current values to the session snapshot.
- SettingsStore test: hides pending state when current values match snapshot.
- SettingsStore test: invalid/missing snapshot does not report pending changes.
- SettingsWindow/source test: uses `Adw.Banner`, includes translated banner strings, and calls the pending-state refresh hook.
- SettingsWindow/source test: confirmation dialog uses `Adw.AlertDialog`, destructive confirm response, and `labwc --exit`.
- Translation catalog test: new strings exist in POT/PO/MO files with required placeholders preserved.

## Non-Goals

- Do not implement a general pending-settings queue.
- Do not delay writing `settings.json`.
- Do not live-reload Waybar.
- Do not restart only the Settings app.
- Do not add custom CSS for the banner; rely on Adwaita defaults.
