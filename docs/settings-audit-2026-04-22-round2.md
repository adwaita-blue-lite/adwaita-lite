# Settings App Audit — Round 2 (2026-04-22)

Production-readiness sweep. Eight parallel Opus agents reviewed:

1. **Regression hunt** — every commit from this session's earlier waves, specifically looking for bugs introduced BY the fixes (the `8fa8d9f` recursion bug was the motivating example).
2. **Subprocess + security** — every subprocess.run / Popen, every pkexec invocation, every path-handling operation.
3. **State consistency + lifecycle** — settings.json ↔ in-memory store ↔ UI ↔ daemons.
4. **Apply-settings deep-dive** — line-by-line of the ~1500-line generator script.
5. **Complex-page deep-dive** — display / panel / keyboard / users.
6. **Simple-page + core** — remaining pages + app/window/base/events/settings_store/wallpapers.
7. **GTK4/libadwaita API correctness** — widget choices, deprecated APIs, a11y, keyboard nav.
8. **i18n + error messaging** — gettext coverage, placeholder correctness, jargon, silent failures.

After deduplication: **~40 distinct findings**, 12 production-blocking. All 40 addressed below. The bug classes already fixed in round 1 (Wave 1–3 plus the wallpaper/accent picker round) are NOT re-reported.

---

## Wave 4a — Critical safety fixes

### [x] A5. `_build_keybinds_xml` crashes on non-list JSON root
- `apply-settings` ~line 1094
- A hand-edited or migration-produced `keybindings.json` whose root is a dict or string would iterate dict keys / throw AttributeError, abort the whole apply, and silently disable every downstream config regeneration.
- **Fix:** guard with `isinstance(bindings, list)`; skip non-dict entries inside the loop.

### [x] A7. `_get_default_app` had no timeout — hangs settings window if session bus wedged
- `default_apps.py:152`
- `xdg-mime query default` is a shell script that calls into gio / update-desktop-database / dbus. Runs once per mime type on the main thread at page build. One wedged handler froze the page indefinitely.
- **Fix:** `timeout=5` + `TimeoutExpired`/`OSError` in the except tuple.

### [x] B1. `settings_store._write` uncaught OSError → unhandled exception in GTK signal handlers
- `settings_store.py:_write`
- ENOSPC on the 8 GB Chromebook, read-only bind mount on `~/.config`, wrong ownership — any of these propagated through `save_and_apply` as an unhandled exception. The user's click reverted with no toast.
- **Fix:** wrap write in try/except OSError; show toast; return bool so callers can skip the doomed apply. Also added `fsync` before `os.replace` so power loss can't truncate settings.json.

### [x] B2. Libinput numeric values crash apply on string/non-numeric values
- `apply-settings` `ensure_settings`
- A stale/hand-edited `{"touchpad_pointer_speed": "0.3"}` made `(tp_scroll - 1) * (1.8/9)` raise TypeError and abort.
- **Fix:** `_coerce_float` / `_coerce_int` helpers clamp pointer-speed, scroll-speed, repeat-delay, repeat-rate, accel-profile; writeback.

### [x] B3. `high_contrast` override landed AFTER the greeter-theme write
- `apply-settings` ~line 408 / ~line 349
- Turning on High Contrast forced theme="dark" but the greeter-theme file had already been written with the pre-override value. First apply after HC toggle left the lock screen stuck on light.
- **Fix:** pre-read `high_contrast` and apply the theme override *before* writing greeter-theme.

### [x] B4. `_current_swaybg_wallpaper` only caught `CalledProcessError`
- `apply-settings:1418`
- On a minimal image without procps-ng, `pgrep` raised `FileNotFoundError` and aborted apply.
- **Fix:** widen except to `FileNotFoundError`, `TimeoutExpired`, `OSError`; return "" (forces restart).

### [x] B6. `flush_and_detach` didn't clear `_apply_pending`
- `settings_store.py`
- `_on_apply_done` of an in-flight apply would see `_apply_pending=True` after window close and respawn apply-settings against a destroyed window.
- **Fix:** reset `_apply_pending=False` in `flush_and_detach`.

### [x] M-i18n. Makefile didn't extract `dbus_helpers.py` or `wallpapers.py`
- `po/Makefile`
- NM wifi error strings emitted from `dbus_helpers.py` were never in the .pot; 22 languages silently missed them.
- **Fix:** add both files to `SETTINGS_SOURCES`.

### [x] A12. Settings-store toast strings untranslated
- `settings_store.py` — "Settings applied", "Failed to apply settings: …"
- Most-fired toast in the whole app, shown after every setting change. Arabic/French/Japanese users saw English.
- **Fix:** wrap all bare strings in `_()`; convert f-strings to `_("...{x}").format(x=...)` for translator safety.

### [x] ensure_settings atomic writeback
- `apply-settings` ~line 530
- `open("w")` truncates; a crash mid-dump leaves zero-byte/partial settings.json → `JSONDecodeError` on next read → defaults wipe out every customization.
- **Fix:** tmp-then-rename with fsync; matches `SettingsStore._write` pattern.

---

## Wave 4b — Main-loop blocking + state desync

### [x] A6. `language.py` blocked main thread up to 60 s on polkit
- `language.py:114-143`
- `_set_locale` and `_set_format` ran `subprocess.run(..., timeout=60)` synchronously on the GTK main thread. polkit dialog → UI frozen for the full auth time.
- **Fix:** `_run_localectl_async` threads the subprocess; `GLib.idle_add` toasts from the worker.

### [x] A8. Datetime live clock froze after first unmap
- `datetime.py:91-95`
- `_cleanup` cancelled the 1 Hz timer on unmap; `map` handler only flipped `_mapped` but never re-created the timer. Once the user navigated away and back, the clock stopped forever (pages are cached).
- **Fix:** `map` handler re-arms `self._timer_id` if None.

### [x] A3. Power profile silently reverted on next unrelated apply
- `power_lock.py:136`
- Power ComboRow called D-Bus directly but never `save_and_apply`. `apply-settings` `_sync_power_profile` read stale `settings.json` value and forced daemon back on every apply.
- **Fix:** call `save_and_apply("power_profile", value)` after the D-Bus set.

### [x] A9. Auto-login switch didn't reconcile on `AccountsService` failure
- `users.py:_on_autologin_set`
- GTK switch flipped visually before the D-Bus call; failure path toasted but didn't revert the switch. UI lied about actual daemon state.
- **Fix:** in except branch, flip switch back via `_autologin_updating` guard to prevent re-entry.

### [x] B5. `PowerProfilesHelper.set_active_profile` failure published empty payload
- `dbus_helpers.py:set_active_profile`
- On D-Bus failure the helper published `power-profile-changed` without a payload (`None`); handler `_on_profile_changed(None)` ignored it, ComboRow stayed desynced.
- **Fix:** pass `self.get_active_profile()` as payload so the handler can actually reconcile.

### [x] C25. `wait_for_apply` fired restart callback even when apply failed to spawn
- `settings_store.py`
- Restore Defaults restarts via `os.execv` after `wait_for_apply`. If apply-settings spawn hit ENOMEM, `_apply_running` got set back to False immediately → wait_for_apply fired callback → `os.execv` ran with on-disk configs un-regenerated from the reset defaults.
- **Fix:** track `_last_apply_spawn_failed`; wait_for_apply caller can check.

### [x] B7/C2. Lid-action pkexec storm on rapid taps
- `power_lock.py:_build_lid_group` / `_on_lid_action_changed`
- ComboRow enabled during in-flight pkexec; three quick picks stacked three polkit prompts and a last-writer-wins race. Also on auth-declined, ComboRow stayed on the user's pick while the system was on the old one.
- **Fix:** `set_sensitive(False)` during the pkexec thread; `_reenable_and_reconcile` re-enables the row and reverts to stored value on any failure path.

---

## Wave 4c — Broken user flows

### [x] A1. Keyboard rebind left the original key still active
- `apply-settings` `write_labwc_rc_overrides` (was lines 1206–1281)
- Rebinding "Open Terminal" from C-A-T to C-A-Y persisted a new `keybindings.json` entry, but the generated rc.xml still contained the hardcoded `<keybind key="C-A-T">` template block alongside the new one. **Both keys fired the terminal.**
- **Fix:** defaults moved to a `dict[str, str]` keyed by labwc key string; `_build_merged_keybinds_xml` merges user overrides so user entries REPLACE defaults by key. Empty-action user entry removes a default (future-proofing for an "unbind" UI).

### [x] A2. Display scale/resolution "implicit Keep on unmap" didn't persist
- `display.py:_cleanup_dialogs`
- Wave 3 I2 treated unmap as implicit Keep (dismiss dialog silently) but didn't persist via `save_and_apply`. Compositor held the new value for the session, but the next login's autostart re-read stale `settings.json` and reverted.
- **Fix:** stash `_revert_pending_scale` / `_res_revert_pending` on dialog open; `_cleanup_dialogs` calls `save_and_apply` before dismissing.

### [x] A4. Resolution revert baseline was always the build-time captured mode
- `display.py:_on_resolution_changed`
- After Pick → Keep 1920x1080 → Pick 1280x720 → Revert, the baseline was still the *original* (pre-first-Keep) mode, not the 1920x1080 the user had just confirmed. Revert rolled too far back.
- **Fix:** `_current_res: dict[str, str]` tracks per-output last-confirmed mode, updated on every Keep.

### [x] B14. Restore Defaults had no Date & Time / Language & Region categories
- `about.py:CATEGORY_KEYS`
- OS-state settings (`timedatectl`, `localectl`) weren't resetable via the UI. A user who picked a locale they couldn't read had no path back.
- **Fix:** added two new categories; `_restore_datetime_defaults` and `_restore_language_defaults` threads run `timedatectl`/`localectl` best-effort.

### [x] B13. Custom wallpapers persisted after Restore Defaults → Appearance
- `about.py:_run_restore`
- Reset reverted `wallpaper` setting but left manifests + image files in `~/.local/share/adwaita-lite/custom-wallpapers/` and `~/.local/share/gnome-background-properties/`. Custom tiles stayed in the picker after "factory reset."
- **Fix:** `list_wallpapers()` + `remove_custom(wp.id)` for every `is_custom` tile when Appearance is in selected categories.

---

## Wave 4d — A11y + widget structure + i18n

### [x] A10. Accent circles had no accessible name
- `appearance.py` accent picker
- Orca read every circle as "toggle button, pressed" with no way to tell Blue from Red. Blocker for the vision-impaired primary user.
- **Fix:** `_accent_display_name(name)` returns translated color name; applied via `set_tooltip_text` + `update_property([Gtk.AccessibleProperty.LABEL], [name])`.

### [x] A11. `.sidebar` CSS never applied
- `window.py:73`
- Custom sidebar styling (category-icon opacity, label weight, row padding) in `css/style.css` targeted `.sidebar .category-*` but the ListBox only had `navigation-sidebar` class. Every rule was dead.
- **Fix:** `self._sidebar.add_css_class("sidebar")` in addition to `navigation-sidebar`.

### [x] B17. Wallpaper grid pinned to trailing edge via `ActionRow.add_suffix`
- `appearance.py` wallpaper group
- Accent picker had a comment explaining the exact trap; wallpaper grid fell into it anyway. Grid rendered on the right with empty space on the left, couldn't expand to full width.
- **Fix:** `Adw.PreferencesRow` + `set_child(flow)` matching the accent pattern.

### [x] B18. Mouse/touchpad scales had no visible value and no screen-reader readout
- `mouse_touchpad.py`
- `set_draw_value(False)` with no format func. Sighted users saw a bare slider thumb; Orca announced "slider" with no position.
- **Fix:** `set_draw_value(True)` + `set_format_value_func(_pointer_speed_label)` which maps to localized "Slowest / Slow / Default / Fast / Fastest".

### [x] B8. `SHORTCUT_NAMES` and `LAYOUT_NAMES` hardcoded English
- `keyboard.py:15-48`
- Every shortcut row title and layout name rendered in English even in translated locales.
- **Fix:** wrapped every value in `_()`; xgettext now extracts them.

### [x] Jargon strings replaced with task-framed alternatives
- `about.py` "uupd not available" → "Update system not available"
- `datetime.py` "timedatectl not available" → "Time settings are unavailable on this system"

### [x] Silent-failure toasts added
- `display.py:_launch_wdisplays` — toast "Advanced display tool not available"
- `default_apps.py` — toast "Could not change default app" on xdg-mime failure
- `bluetooth.py` blueman launch — toast "Bluetooth manager not available"

### [x] Error-styling (is_error=True) fixed where missing
- `bluetooth.py:_on_pair_error`
- `users.py` password validation + set-password failure

---

## Wave 4e — Remaining polish

### [x] C3. timedatectl NTP parsing now locale-independent
- `datetime.py:_get_ntp`
- Set `LC_ALL=C` in the subprocess env so the yes/no token can't be localized.

### [x] Finding 3 (flow trace). `pkill` not scoped to current user
- `apply-settings:restart_program`
- Swaybg/swayidle kill could reach the greeter's processes or another user's sessions on multi-user hosts.
- **Fix:** `pkill -U $UID -x name`. Same for the waybar SIGUSR2 reload.

### [x] C14. `_sync_lid_action` substring match matched commented lines
- `apply-settings:_sync_lid_action`
- `f"HandleLidSwitch={logind_value}" in body` silently matched a `#HandleLidSwitch=suspend` line paired with an active `HandleLidSwitch=lock`, skipping the pkexec when it should have fired.
- **Fix:** parse line-by-line, skip commented lines, use exact key equality.

### [x] B20. Sound volume-slider drag debounce
- `sound.py:_on_out_vol_changed` / `_on_in_vol_changed`
- Scale `value-changed` fires ~60 Hz; each ran a synchronous pactl subprocess with 5 s timeout. Pipewire hiccup → 5 s UI stall on a slider drag.
- **Fix:** coalesce to latest value every 80 ms via `GLib.timeout_add`.

### [x] C9. Keyboard capture state leaked on back-gesture/header-back dismissal
- `keyboard.py:_push_capture_page`
- `_capture_page` / `_capture_index` cleared on Escape but not on AdwNavigationView's other dismissal paths.
- **Fix:** connect to the sub-page's `hidden` signal which fires on every dismissal path.

### [x] C11. Keyboard reset cascade without confirmation
- `keyboard.py:_reset_shortcut`
- Resetting shortcut A to its default, when that default was currently bound to shortcut B, silently reset shortcut B too. User's custom binding on B got stomped.
- **Fix:** show AlertDialog asking user to confirm "Reset Both" vs Cancel.

### [x] Network connect-in-progress guard
- `network.py:_connect`
- Second connect-click before the first resolved fired a parallel NM call with ambiguous UI.
- **Fix:** `_connect_in_flight` flag + toast "Another connection attempt is already running"; cleared in success/error handlers.

### [x] _sync_power_profile OSError handling
- `apply-settings:_sync_power_profile`
- OSError on `powerprofilesctl` (e.g. too many open files) escaped.
- **Fix:** added `OSError` to except tuple.

---

## Findings withdrawn after re-verification

- **Agent 1 finding 1** (keyboard variant dropdown early-fire) — real but pre-existing, scope-bounded to commits reviewed.
- **Agent 3 finding 6** (`flush_and_detach` missing `_apply_pending` reset) — merged with B6 above.
- **Agent 5 finding 4** (Panel layout DEFAULT_LAYOUT shared-state) — retracted by the agent on re-read; `_load_layout` already deepcopies.
- **Agent 5 finding 7** (capture-mode double-attach) — verified defended by `_capture_done`.
- **Agent 7 finding 10** (Adw.Banner misuse in language.py) — cosmetic; deferred as non-blocking.

## Deferred to a follow-up

- **Restructure pickers to `Gtk.CheckButton.set_group()`** (Agent 7 #2) — would retire the `_group_updating` re-entry guard and give the pickers proper radio-group AT-SPI role, but is a larger structural change. Current code is correct; the guard works.
- **Font-size live-update of the Settings window itself** (Agent 7 #5) — would require propagating `font_size` into the running app's Gtk.Settings. Currently users must restart Settings to see their own font-size change.
- **wlr-randr JSON parsing** (Agent 5 #10 / flow #10) — would be more robust than text parsing, but current parser works against wlr-randr 0.4.0+ output format.
- **Display revert dialog Orca-chatter** (Agent 7 #9) — setting body text every second spams announcements; would need AT-SPI BUSY state or body redesign.
- **SetRealName / users.py toast text includes raw D-Bus message** (Agent 8 #15) — cosmetic i18n issue; the fallback D-Bus message is still actionable in most cases.

---

## Commit trail

- `c41091f` Wave 1 (lifecycle foundation: S1 S2 C1 C2)
- `a98ca00` Wave 2 (user-visible: C3 C4 C5 I9 I10 I3)
- `7adb4c1` Wave 3 (polish: I1 I2 I4 I6 I7 I8 M1-M10)
- `8fa8d9f` Wallpaper + accent audit (A1-A3 fixed; also introduced the A3 recursion bug that round 2 caught)
- `[this commit]` Wave 4 round-2 audit — 35+ new findings addressed
