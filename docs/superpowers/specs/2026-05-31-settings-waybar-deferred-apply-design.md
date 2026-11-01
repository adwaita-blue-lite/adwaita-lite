# Settings Waybar Deferred Apply Design

Date: 2026-05-31

## Purpose

Prevent Settings from closing the terminal, Waybar, or other session clients when users change panel-related settings.

Manual testing proved that `pkill -U "$UID" -USR2 -x waybar` is unsafe in this labwc session: it closes the terminal and reloads Waybar. This means the remaining fix must stop live-reloading Waybar from Settings instead of trying more subprocess isolation or Settings respawn behavior.

## User Outcomes

- Users can change panel position, density, twilight colors, layout, pinned apps, and accent color without triggering Waybar live reload.
- Settings saves the requested values and writes Waybar config/CSS safely.
- The UI clearly tells users that panel changes apply after restarting the session.
- The restart-session message is available in every supported Settings language.
- Non-Waybar settings keep their existing live-apply behavior where safe.

## Current Context And Evidence

- `SettingsStore.save_and_apply(..., mode="waybar")` is used by panel controls in `files/usr/lib/adwaita-lite/settings/pages/panel.py` and by accent changes in `files/usr/lib/adwaita-lite/settings/pages/appearance.py`.
- `SettingsStore` already detaches `mode="waybar"` apply dispatch from the GTK process.
- `adwaita-lite-apply-settings --mode waybar` writes Waybar files transactionally through `apply_waybar_transaction(tokens)`.
- `apply_waybar_transaction(tokens)` still calls `reload_waybar()` after changed writes.
- Full/live apply still calls `reload_waybar()` from `_sync_live_session()` when `_write_config_files()` reports `waybar_changed`.
- `reload_waybar()` sends `SIGUSR2` to user Waybar processes and spawns Waybar when none are running.
- User testing showed both Settings and terminal/start-menu launch paths close during Waybar-related Settings changes, and the manual `SIGUSR2` command closes the terminal too. The signal/reload path is unsafe independently of the Settings process.
- Settings gettext sources and catalogs live under `po/settings`; `tests/test_translation_catalogs.py` requires every release entry to be translated and non-fuzzy for all supported languages.

## Scope

- Keep transactional Waybar config/CSS generation and atomic writes.
- Remove Waybar signal/reload/respawn side effects from Settings-driven applies.
- Ensure full/live apply does not reload Waybar when the only Waybar files changed.
- Add a localized restart-session notice to the Settings UI for panel-related controls.
- Update `po/settings/adwaita-lite-settings.pot` and every `po/settings/*.po` catalog.
- Add focused regression tests for no live reload and restart-session messaging.

## Non-Goals

- Do not add a daemon, systemd user unit, or background coalescing service.
- Do not keep experimenting with subprocess/session isolation around `SIGUSR2`.
- Do not respawn Settings after apply; the terminal also closes, so that only hides one victim.
- Do not change Waybar's startup ownership in labwc autostart.
- Do not redesign panel layout, app pinning, or accent picker UI beyond the restart-session notice.

## Options Considered

### Option 1: Keep `SIGUSR2` And Further Isolate The Worker

This keeps live panel updates, but it is rejected because the manual `SIGUSR2` command closes unrelated clients. More detachment would not make the Waybar reload safe.

### Option 2: Restart Waybar Instead Of Signaling It

This avoids `SIGUSR2`, but it still tears down a layer-shell client from a Settings action. It risks compositor focus/session side effects, duplicate panels, and visible flicker. It also still asks Settings to own Waybar lifecycle.

### Option 3: Defer Waybar Apply Until Session Restart

Settings writes the requested config and stops there. The existing session keeps its current Waybar process and config in memory; the next session start uses the saved files. This is the selected design because it removes the proven unsafe operation while preserving durable user settings.

## Selected Design

Waybar-related Settings changes become save-and-defer operations. Settings persists `settings.json`, dispatches the existing Waybar-only writer as needed, and shows a restart-session message. The writer renders and atomically replaces `~/.config/waybar/config.jsonc` and `~/.config/waybar/style.css`, then exits without signaling, killing, or spawning Waybar.

`reload_waybar()` can remain available for non-Settings callers only if tests prove no Settings path reaches it. The safer implementation is to remove its call sites from `apply_waybar_transaction()` and `_sync_live_session()` so both `--mode waybar` and full/live Settings applies avoid Waybar lifecycle changes.

Full/live apply should still write Waybar files, because theme/accent and other settings can affect generated CSS. It must not interpret `waybar_changed` as permission to reload Waybar. Other live sync operations, such as GTK settings, wallpaper swap, mako reload, labwc reconfigure, night light, and swayidle restart, stay unchanged.

## Component Boundaries

- Panel and Appearance pages own user-facing restart-session notices.
- `SettingsStore` owns the toast text for Waybar-only saves and dispatches the file writer.
- `adwaita-lite-apply-settings` owns sanitized settings, Waybar rendering, validation, atomic writes, and diagnostics.
- labwc autostart remains responsible for starting Waybar in a new session.
- Waybar remains an external process and is not controlled by Settings.

## Data And Control Flow

For a Waybar-only setting:

1. The UI handler calls `store.save_and_apply(..., mode="waybar")`.
2. `SettingsStore` writes `~/.config/adwaita-lite/settings.json` atomically.
3. `SettingsStore` starts `adwaita-lite-apply-settings --mode waybar` detached, or reports an immediate launch error if spawning fails.
4. `SettingsStore` shows a localized message: `Panel changes saved. Restart your session to apply them.`
5. The writer obtains the apply lock, sanitizes settings, renders Waybar config/CSS, validates generated content, atomically writes changed files, and exits.
6. The writer does not call `reload_waybar()`, `pkill`, `pgrep`, `waybar`, or any other Waybar lifecycle command.

For full/live apply:

1. The writer still updates Waybar config/CSS as part of `_write_config_files()`.
2. `_sync_live_session()` ignores `waybar_changed` for lifecycle purposes.
3. All existing non-Waybar live sync behavior remains in place.

## UX And Translation

The primary message is:

`Panel changes saved. Restart your session to apply them.`

This text should be used for Waybar-only success toasts. The Panel page should also include a persistent group description or notice so users understand why panel edits do not visibly change immediately. Appearance should surface the same idea near accent color because accent changes affect Waybar styling.

The message must be marked for gettext extraction with `_()`. The settings POT and every supported Settings PO file must include a non-empty translation. Tests already reject untranslated or fuzzy release entries, so the catalog update is part of the implementation rather than a follow-up.

## Error Handling And Edge Cases

- If Settings cannot write `settings.json`, it keeps the existing write-error toast behavior and does not claim the panel change was saved.
- If the detached Waybar file writer cannot spawn, Settings shows the existing immediate error path, updated to avoid promising live application.
- If the writer fails validation or file writes, it logs the failure and exits non-zero. Settings remains open because the worker is detached.
- If no Waybar process is running, Settings still writes files and does not spawn Waybar.
- Rapid panel changes may spawn multiple short-lived writers; the existing apply lock serializes them and the final files converge to the latest settings.

## Testing And Verification Strategy

- Add a failing test proving `apply_waybar_transaction(tokens)` writes changed files but does not call `reload_waybar()`.
- Add a failing test proving `_sync_live_session()` does not call `reload_waybar()` when `changes["waybar_changed"]` is true.
- Add or update SettingsStore tests so `mode="waybar"` reports the restart-session message instead of a live-apply success message.
- Add UI logic tests proving Panel and Appearance expose the restart-session copy.
- Add translation tests or rely on existing catalog tests after updating POT/PO files.
- Run focused Settings/apply tests, translation catalog tests, full `pytest -q`, and `git diff --check` before completion.

## Acceptance Criteria

- No Settings-driven code path sends `SIGUSR2` to Waybar.
- No Settings-driven code path kills or spawns Waybar.
- Waybar config/CSS writes remain transactional and validated.
- Panel and accent changes tell users to restart the session to apply panel updates.
- The restart-session message is translated in every supported Settings locale.
- Existing non-Waybar live apply behavior remains covered and working.
- Manual verification on the affected desktop no longer closes terminal or Settings when changing panel settings.

## Remaining Risks

- Users lose immediate visual feedback for panel changes until they restart the session.
- Detached writer failures after spawn are logged but not shown immediately in Settings.
- Translations may need native-speaker review, but all catalogs must be populated to keep release builds complete.
