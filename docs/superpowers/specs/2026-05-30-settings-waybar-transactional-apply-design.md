# Settings Waybar Transactional Apply Design

Date: 2026-05-30

## Purpose

Prevent the Settings application from closing or crashing when users change Waybar-related settings, while preserving live panel updates for position, density, twilight colors, module layout, pinned apps, and accent color.

The current Waybar-only path was intended to reduce blast radius by avoiding full session live sync, but user confirmation shows Settings still closes on all Waybar-relevant controls. The new design treats live Waybar application as an isolated, transactional side effect rather than work the GTK process actively waits on.

## User Outcomes

- Users can change Waybar-related settings without the Settings window closing.
- Panel updates remain live when safe, with no required logout or manual command for normal changes.
- If live panel reload fails, the user's saved setting remains intact and the system records a useful diagnostic instead of taking down Settings.
- Developers get an apply path that can be tested without launching GTK or Waybar.
- Maintainers get persistent failure evidence for post-release diagnosis.

## Current Context And Evidence

- `files/usr/lib/adwaita-lite/settings/settings_store.py` writes `settings.json`, starts `/usr/libexec/adwaita-lite-apply-settings`, waits in a background thread, and posts a GTK toast from `_on_apply_done` through `GLib.idle_add`.
- `SettingsStore.save_and_apply(..., mode="waybar")` is used by Waybar-related UI controls in `files/usr/lib/adwaita-lite/settings/pages/panel.py` and accent changes in `files/usr/lib/adwaita-lite/settings/pages/appearance.py`.
- `files/usr/libexec/adwaita-lite-apply-settings` already supports `--mode waybar`; that mode calls `write_waybar_config(tokens)` and then `reload_waybar()` when files changed.
- `reload_waybar()` currently sends `SIGUSR2` to all user Waybar processes via `pkill -USR2 -x waybar` and starts `waybar` in a new session if none is running.
- User report: Settings itself closes when changing Waybar-related controls. This means the issue is not only Waybar disappearing; it implicates either Settings-side apply completion/callback behavior or a compositor/Waybar reload interaction that affects the GTK client.
- Local checks did not show useful current crash evidence: `coredumpctl list adwaita-lite-settings` found no coredumps and user journal lookups for `adwaita-lite-settings`/`python3` had no relevant entries in this environment.
- Existing tests cover mode routing and Waybar config generation in `tests/test_settings_store.py`, `tests/test_settings_app_logic.py`, and `tests/test_apply_settings.py`, but they do not prove crash isolation from the GTK process.

## Scope

- Redesign the Waybar-only apply path so Settings persists user intent and triggers isolated background side effects without waiting on them.
- Add a transactional Waybar writer that stages generated config/CSS, validates what is practical, atomically commits files, and then requests a Waybar reload or restart.
- Add persistent diagnostics for Waybar apply failures.
- Keep full/live apply behavior for non-Waybar settings unless tests or investigation prove it shares the same crash path.
- Add tests for the new Settings-store behavior, transactional writer behavior, and reload strategy boundaries.

## Non-Goals

- Do not replace the whole settings system.
- Do not add a long-running daemon or systemd user service in the first iteration.
- Do not remove live Waybar updates entirely unless implementation evidence shows every reload strategy remains crashy.
- Do not redesign panel UI controls or Waybar visual styling.
- Do not change branch/CI stream automation as part of this work.

## Constraints And Assumptions

- The Settings GTK process must not import or execute Waybar reload logic directly.
- The apply worker must be one-shot and self-exiting to avoid lifecycle management complexity.
- User settings remain stored in `~/.config/adwaita-lite/settings.json` as the source of truth.
- Waybar config remains stored in `~/.config/waybar/config.jsonc` and CSS in `~/.config/waybar/style.css`.
- Atomic replacement is required so Waybar never sees partially-written config or CSS.
- The existing file lock in `adwaita-lite-apply-settings` can continue serializing concurrent apply runs.
- Waybar may not be installed or running in all test/dev environments; tests must mock process calls and paths.
- The crash may be caused by Settings-side callback behavior, Waybar `SIGUSR2`, or compositor interaction. The design isolates these paths and adds diagnostics rather than betting on a single unproven cause.

## Design Options Considered

### Option 1: Suppress Waybar Success Toasts Only

Settings would continue spawning and waiting on `adwaita-lite-apply-settings --mode waybar`, but would not show a success toast for Waybar applies.

This is small and might fix a crash caused by the completion callback. It does not isolate Settings from child process completion, stderr handling, or live Waybar reload timing. It also leaves the architecture fragile if the real failure is compositor/Waybar interaction.

### Option 2: Detached One-Shot Waybar Apply Worker

Settings would write JSON and spawn the existing apply script in detached mode, then stop tracking it. Failures would be logged instead of returned to the GTK process.

This isolates the Settings process well and is likely enough if the current crash is caused by apply completion callbacks. By itself, it does not improve the safety of the files Waybar reloads or provide a structured fallback if reload fails.

### Option 3: Transactional Detached Waybar Apply

Settings writes JSON, starts a detached one-shot worker, and does not wait for completion. The worker stages generated Waybar config/CSS, validates them, atomically commits them, logs failures, and requests Waybar reload through an isolated strategy.

This is the selected design because it addresses both suspected failure classes: Settings-side callback crashes and unsafe live Waybar reload behavior. It adds stronger invariants without introducing a permanent daemon.

## Selected Design

Waybar-related controls will use a fire-and-forget apply path. Settings remains responsible for persisting state and keeping its own UI responsive. A detached one-shot worker handles Waybar config generation, file commit, and panel reload.

The existing `adwaita-lite-apply-settings --mode waybar` command becomes the detached worker entry point. Internally it should call a Waybar transaction helper that reads sanitized settings, builds tokens, generates config/CSS into memory or staging files, validates generated JSON with `json.loads`, performs basic CSS/file sanity checks, writes staged files, and atomically renames them into place. Only after a successful commit does it request Waybar to reload.

Settings will not wait for Waybar-only apply completion, read stderr, or show a completion toast from that worker. The UI can show a synchronous confirmation such as "Saved" after JSON persistence succeeds, but it must not imply the panel reload completed.

The worker writes diagnostics through a small logging helper to a persistent user log such as `~/.cache/adwaita-lite/apply-settings.log`. The log should include timestamp, mode, phase, error message, and relevant command return code. This creates actionable evidence when user systems reproduce crashes that tests cannot.

The first reload strategy remains detached `SIGUSR2` because Waybar documents it as the standard config reload path. The implementation must keep this strategy behind a helper boundary so a later plan can switch to a safer replacement strategy if diagnostics or manual testing shows `SIGUSR2` itself closes Settings.

## Component Boundaries

- Settings UI pages own widget state, user interactions, and calls to `SettingsStore`.
- `SettingsStore` owns JSON persistence, full/live apply orchestration, and Waybar apply dispatch policy.
- The detached Waybar apply worker owns Waybar transaction execution and diagnostics.
- `adwaita-lite-apply-settings` owns settings sanitization, token generation, config rendering, atomic file writes, and external process signaling.
- Waybar remains an external consumer. It must only observe complete config/CSS files.

The critical new boundary is that Waybar-only applies do not call back into GTK after dispatch.

## Data And Control Flow

For a Waybar-related setting:

1. UI handler updates in-memory UI state and calls `store.save_and_apply(..., mode="waybar")`.
2. `SettingsStore` atomically writes `settings.json`.
3. `SettingsStore` starts `[apply_script, "--mode", "waybar"]` with detached process settings such as `start_new_session=True`, `stdout=DEVNULL`, `stderr=DEVNULL`, and no wait thread, then returns immediately.
4. The worker obtains the apply lock.
5. The worker sanitizes settings and builds tokens.
6. The worker generates Waybar config/CSS into staging content.
7. The worker validates generated content enough to catch programmer errors before replacing live files.
8. The worker atomically replaces `~/.config/waybar/config.jsonc` and `style.css` when content changed.
9. The worker requests Waybar reload through a reload helper.
10. The worker logs failures and exits.

For non-Waybar settings, existing full/live apply behavior remains unless implementation evidence shows the same Settings-side callback path is unsafe for all apply modes.

## UX Behavior

- Waybar controls should feel instant and should not block the UI.
- Success toasts for Waybar-only applies should either be removed or changed to a local persistence message such as "Saved".
- Error toasts from Waybar-only worker completion should not be shown because the worker is intentionally detached. Persistent logs provide diagnostics instead.
- If JSON persistence fails, Settings should still show the existing immediate error toast because that failure happens before worker dispatch.
- If Waybar reload fails, the user may see the panel update later, not update, or require a panel restart, but Settings must stay open.

## Error Handling And Edge Cases

- Invalid generated JSON: do not replace live config; log failure; exit non-zero.
- CSS generation failure or write failure: do not partially replace files; log failure; exit non-zero.
- Missing Waybar binary: write config/CSS, log that live reload was skipped or silently treat as non-fatal consistent with current behavior.
- No running Waybar: preserve current behavior of spawning Waybar, but keep spawn detached and logged.
- Concurrent Waybar applies: rely on the apply lock so the latest serialized settings are applied safely.
- Rapid UI changes: detached applies may be queued by lock serialization; final state should converge to the latest `settings.json`.
- Worker launch failure: Settings may show an immediate "saved but not applied" error if `Popen` fails synchronously.
- Worker crash: Settings remains unaffected; log may contain only pre-crash entries, and future applies can retry.

## Security, Privacy, Performance, And Accessibility

- Settings and Waybar apply continue running as the user; no new privileges are introduced.
- Logs must not include full environment variables or secrets. They may include local config paths and command names.
- Atomic file writes preserve config integrity across power loss or worker crashes.
- Fire-and-forget dispatch avoids blocking the GTK thread and reduces perceived latency on low-RAM hardware.
- Accessibility is preserved by keeping controls responsive and avoiding crash loops that affect screen-reader users.

## Testing And Verification Strategy

- Add tests proving `SettingsStore.save_and_apply(..., mode="waybar")` dispatches a detached worker and does not set `_apply_running`, start wait threads, or schedule completion callbacks.
- Add tests proving full/live modes continue to use tracked apply behavior.
- Add tests proving Waybar transactional writes do not replace live files when validation fails.
- Add tests proving successful transaction writes config/CSS atomically and calls the reload helper only after successful commit.
- Add tests proving staged config validation catches invalid generated JSON before live files are replaced.
- Add tests proving worker failures are logged.
- Add tests around rapid Waybar apply requests to ensure the dispatch behavior is non-blocking and does not merge into full apply unless a full apply is explicitly requested.
- Manual verification on the affected desktop is required: change panel position, density, twilight, module layout, pinned apps, and accent color while confirming Settings stays open.

## Open Decisions Resolved

- Use transactional detached Waybar apply rather than only suppressing toasts.
- Do not add a permanent daemon in this iteration.
- Keep live Waybar updates as the intended user experience.
- Keep `SIGUSR2` as the initial reload mechanism, but isolate it behind a helper boundary so it can be replaced if proven unsafe.
- Use persistent user-cache logging for detached worker diagnostics.

## Remaining Risks

- If the crash is caused by a compositor bug triggered merely by Waybar reload, detaching the worker may not fully solve Settings closing. The helper boundary allows changing reload strategy after evidence.
- If Waybar accepts invalid CSS without a practical validation command, tests can only validate generator invariants and file transaction behavior.
- Fire-and-forget behavior means users may not see immediate live-apply failure feedback. Persistent logs compensate for diagnostics, not UX discoverability.
- Rapid applies may spawn more short-lived workers than ideal. The lock serializes state, but a later optimization may coalesce Waybar requests.

## Acceptance Criteria

- Waybar-related Settings controls no longer use the tracked apply completion path.
- Settings remains open after changing panel position, density, twilight, module layout, pinned apps, and accent color in manual verification.
- Waybar config/CSS writes are transactional and never leave partially-written live files.
- Reload is requested only after successful staged generation and commit.
- Worker failures are logged in a persistent per-user diagnostic log.
- Existing non-Waybar apply behavior remains covered by tests.
- Full test suite passes before implementation is considered complete.
