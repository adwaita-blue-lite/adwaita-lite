# Settings App Audit — 2026-04-22

Comprehensive multi-agent (Opus) review of the Adwaita-Lite settings app. Five parallel agents, each scoped to a distinct slice of the codebase, produced 25 deduplicated findings. Audit scope excludes the two bug classes already fixed earlier in the same session:

- **Config generators that replace system defaults** (fixed: labwc rc.xml `Client` context missing in both static and generated copies — commits `2ceb161`, `326d1ad`).
- **`subprocess.Popen` without `start_new_session=True`** (fixed in `apply-settings` + 4 settings pages — commits `c79201a`, `c23f044`).

Findings below are organized by proposed fix wave. Check off each box as the fix lands.

---

## Wave 1 — Lifecycle foundation (do first; many downstream findings depend on these)

### [x] S1. Subscriptions wiped on first unmap, never re-registered

**Location:** `base.py:53-62` (root cause) + `window.py:142-146` (lazy page cache)
**Affects:** `network.py`, `bluetooth.py`, `sound.py`, and any page calling `setup_cleanup`
**Confidence:** High

**Scenario:** `unmap` fires on sidebar-back in collapsed mode, search-filter rebuilds, nav-view push, *and* window close — all treated as "tear down subscriptions". First such event nukes every event-bus subscription. Pages are cached in `_built`, so `subscribe()` never runs again. After the user navigates away from Network once, wifi AP updates stop flowing to the UI forever. Same for Bluetooth pair-success, hardware volume changes, power-profile-changed.

**Fix direction:** Subscribe on `map` and unsubscribe on `unmap` as a pair, *or* move cleanup to `destroy` / window `close-request` instead of `unmap`.

---

### [x] S2. `setup_cleanup(self)` wired to the wrong widget in nav-view pages

**Location:** `panel.py:100`, `keyboard.py:267`
**Confidence:** High

**Scenario:** Both pages wrap themselves in `AdwNavigationView`. `base.py`'s docstring explicitly says nav-view pages must pass `self._nav` — which `users.py:136` does correctly. Panel pushes "Add Pinned App" sub-page → the root `PreferencesPage` unmaps → `unsubscribe_all` fires while user is still mid-flow on Panel. Same for Keyboard-capture sub-pages.

**Fix direction:** Pass `self._nav` to `setup_cleanup` in both files. Two-line change each.

---

### [x] C1. `_run_apply` silently disables all future applies on transient Popen failure

**Location:** `settings_store.py:133-149`
**Confidence:** High

**Scenario:** Only `FileNotFoundError` is caught. `PermissionError` / generic `OSError` / ENOMEM during a bootc overlay swap propagates out, leaves `_apply_running=True` permanently. Every subsequent save silently no-ops with no toast. User flips toggles and nothing happens; only app restart recovers.

**Fix direction:** Widen except to `OSError`, reset `_apply_pending` in the except path, emit an error toast.

---

### [x] C2. Toast + debounce callbacks fire on a destroyed window

**Location:** `settings_store.py:107-116` (debounce), `122-177` (apply), `window.py:136` (toast cb registration)
**Confidence:** High

**Scenario:** User changes setting, closes window within the 300 ms debounce. Debounce timer fires → `save_and_apply` → subprocess runs on a background thread → `_on_apply_done` calls `self._toast_callback(...)` → `self._show_toast` on freed `Adw.ToastOverlay`. Next window instance overwrites the callback, so pending completions from the previous window toast on the *new* overlay.

**Fix direction:** On window close, call `store.flush_or_cancel()` that cancels pending debounces via `GLib.source_remove` and nulls the toast callback.

---

## Wave 2 — User-visible now

### [x] C3. BlueZ helper uses `call_sync(-1)` on main thread — 25 s UI freeze on wedged adapter

**Location:** `dbus_helpers.py:377-387` (`start_discovery`, `stop_discovery`, `set_powered`, `is_powered`, `get_devices`, `remove_device`)
**Confidence:** High

**Scenario:** Known wrinkle on Chromebooks where BlueZ hangs on `StartDiscovery` after resume/suspend. User taps scan, GTK main loop blocks for ~25 s (BlueZ internal timeout) because we pass `-1` to `call_sync`.

**Fix direction:** Bounded timeout (5 s) on all adapter-level calls, or convert to async `call(...)`.

---

### [x] C4. `_sync_lid_action` triggers pkexec on every apply when drop-in is missing

**Location:** `apply-settings:1404-1424`
**Confidence:** High

**Scenario:** Fresh install has no `/etc/systemd/logind.conf.d/lid-action.conf`. Code sets `body = ""` on `OSError`, then `f"HandleLidSwitch=..." in ""` is always False, so pkexec fires on *every* settings-apply — font size change, theme flip, accent click. Non-technical primary user gets an auth prompt storm on their first afternoon.

**Fix direction:** Write the drop-in at first-boot with the compile-time default, *or* gate `_sync_lid_action` on "settings differs from default AND drop-in is missing-or-different".

---

### [x] C5. `lock_timeout` / `display_off_timeout` never validated → corrupt JSON aborts apply silently

**Location:** `ensure_settings` in `apply-settings` (around lines 289-450), consumed at `apply-settings:1460`
**Confidence:** High

**Scenario:** `ensure_settings` validates `suspend_timeout` against a closed set but ignores `lock_timeout` and `display_off_timeout`. `int(settings.get(...))` on non-numeric stale/edited values raises, the top-level session handler swallows the error, exits 0 — user loses screen lock with no toast.

**Fix direction:** Add closed-set validation (`{0, 60, 120, 300, 600, 900, 1800}`) alongside `suspend_timeout` and write the coerced value back.

---

### [x] I9. xkb values in labwc rc.xml aren't XML-escaped

**Location:** `apply-settings:1034-1054, 1171`
**Confidence:** High

**Scenario:** `kb_layout`, `kb_variant`, `xkb_options` are interpolated directly into XML while `_build_keybinds_xml` above *does* use `escape`/`quoteattr`. A variant string containing `<` or `]]>` corrupts rc.xml → labwc falls back to defaults → possible keyboard layout lockout.

**Fix direction:** `xml.sax.saxutils.escape` on the three values before f-string insertion.

---

### [x] I10. Wallpaper / accent toggle-off leaves UI and settings.json desynced

**Location:** `appearance.py:103-109` (accent), `appearance.py:267-273` (wallpaper)
**Confidence:** High

**Scenario:** `Gtk.ToggleButton` lets users click the active tile to deactivate it. Both handlers early-return on `not btn.get_active()` — no tile shows as selected in the UI, but settings.json still has the old value. Any subsequent apply re-reads stale value; user is visually confused.

**Fix direction:** Force the button back to active, *or* switch to `Gtk.CheckButton.set_group()` which enforces single-selection.

---

### [x] I3. Set-failure in NM / BlueZ / PowerProfiles doesn't reconcile UI

**Location:** `dbus_helpers.py:112-114` (wifi), `335-346` (bluez powered), `535-546` (power profile)
**Confidence:** Medium-High

**Scenario:** GTK switch rows flip visually on user click. Helper issues the `Set` call, it fails (rfkill, auth policy, etc.), helper prints error and swallows. Switch stays visually "on" while hardware is off. User clicks again → no change.

**Fix direction:** On set-failure, publish the corresponding `-changed` event so the switch reconciles against actual daemon state.

---

## Wave 3 — Polish / edge cases

### [x] I1. Display revert-timer races on rapid second pick

**Location:** `display.py:316-318` (scale), `479-481` (resolution)
**Confidence:** High

**Scenario:** `force_close()` synchronously fires the response handler with *captured* old-value variables, briefly inverting the ComboRow display mid-countdown. Eventual state is correct, but the UI visibly shows the wrong value for a moment.

**Fix direction:** Disconnect old `response` handler (or null `_revert_dialog` and gate on identity) before `force_close`.

---

### [x] I2. Display revert triggers on category switch, not just timeout

**Location:** `display.py:76, 278-292`
**Confidence:** Medium

**Scenario:** Navigate away from Display → unmap → `_cleanup_dialogs` → force-close with "revert" → user loses the scale they chose and never saw a dialog.

**Fix direction:** Treat unmap as implicit Keep, or just drop the pending revert silently.

---

### [x] I4. `nm-unavailable` event has no subscriber

**Location:** `dbus_helpers.py:86`, `network.py` (subscribes to `nm-ready` only)
**Confidence:** High

**Scenario:** NM daemon not running when user opens Network. Helper publishes `nm-unavailable`, nothing listens, page looks frozen with WiFi toggle in default state.

**Fix direction:** Subscribe to `nm-unavailable` in `network.py` (reveal banner, disable controls), or fold into `nm-ready` with an `available` flag.

---

### [~] I5. `BlueZHelper` leaks three D-Bus signal subscriptions per page build — deferred

*Re-evaluated after Wave 1 S1 landed: pages are built lazily once per
window instance and cached (`window._built`), and `setup_cleanup` now
fires on `unrealize` (not `unmap`), so the helper is only instantiated
once per open-window session. Subscriptions only leak across explicit
close-and-reopen of the whole Settings window, which is uncommon
enough that adding a `stop()` method + page-side cleanup wiring isn't
justified. Revisit if profiling shows accumulating D-Bus handlers on
long-running sessions.*

**Location:** `dbus_helpers.py:462-479`
**Confidence:** Medium-High

**Scenario:** Each page rebuild adds three `signal_subscribe` registrations; none are unsubscribed. After N sidebar visits, `bluetooth-changed` emits N× per event → visible UI re-scan storm during pairing.

**Fix direction:** Store the `signal_subscribe` IDs, expose `stop()`, call from page cleanup.

---

### [x] I6. Phantom Bluetooth scan when adapter absent

**Location:** `bluetooth.py:107-112`
**Confidence:** High

**Scenario:** BlueZ running but no adapter (USB dongle unplugged). User taps scan; `start_discovery` bails silently; button disables for 30 s with "Scanning..." anyway.

**Fix direction:** Gate scan button on `self._bt.available` from `build()` and `_refresh_devices`.

---

### [x] I7. NetworkPage rebuilds whole list on every `access-point-added` — kills focus + screen-reader

**Location:** `network.py:211-244`
**Confidence:** Medium-High

**Scenario:** User scrolls to a weak-signal SSID, about to click Connect. `access-point-added` fires → full teardown and rebuild → focus lost, screen-reader announcement cut off, click may miss. Major a11y issue for the vision-impaired primary user.

**Fix direction:** Diff the AP list; preserve row identity for SSIDs still present.

---

### [x] I8. SoundPage `_refresh()` does 6–8 synchronous `pactl` calls with 5 s timeouts on main loop

**Location:** `sound.py:229-280`
**Confidence:** High

**Scenario:** `pactl subscribe` publishes `audio-changed` per volume tick. Each publish triggers full `_refresh` → six subprocess calls on main loop. Volume-key spam micro-freezes UI. If pipewire hiccups, up to 5 s stall.

**Fix direction:** Debounce `_refresh` 100 ms via `GLib.timeout_add`; coalesce `audio-changed` in `PulseAudioSubscriber`.

---

### [x] M1. `EventBus` `idle_add` delivery races with `unsubscribe_all`

**Location:** `events.py:21-29`
**Confidence:** High

**Scenario:** Events queued before unmap still execute after subscriber removal because `unsubscribe` only filters the list at publish time. Closure is already queued in idle loop.

**Fix direction:** Re-check subscriber membership inside `_deliver` before invoking, or dispatch synchronously when already on the main thread.

---

### [x] M2. Corrupt `keybindings.json` crashes Keyboard page build

**Location:** `keyboard.py:181-199` (loader), `459-460` (consumer)
**Confidence:** Medium-High

**Scenario:** Hand-edited or partially-written JSON missing `key` or `display_name` → KeyError during page build → whole Keyboard category fails to render. User has no UI to repair it.

**Fix direction:** Validate each entry on load (require `key` and `action`); drop or default-fill malformed rows.

---

### [x] M3. Keyboard capture silently collides with system-reserved keys

**Location:** `keyboard.py:51, 636-643`
**Confidence:** Medium

**Scenario:** `_SKIP_KEYS` filtered at parse time; `_find_conflict` only scans the filtered list → user captures a reserved key, no conflict reported, one or the other silently wins at runtime depending on merge order.

**Fix direction:** Include `_SKIP_KEYS` in the conflict check; show "reserved" dialog.

---

### [x] M4. `about.py` processor shows "Unknown" on ARM Chromebooks

**Location:** `about.py:114-121`
**Confidence:** High

**Scenario:** Large subset of target hardware is ARM (MT8173/8183, RK3399). `/proc/cpuinfo` on ARM has no `model name` field — uses `Hardware` / `Model` / `CPU implementer`.

**Fix direction:** After the x86 scan, fall back to scanning for ARM fields, or shell out to `lscpu`.

---

### [x] M5. `_hash_password` doesn't catch `FileNotFoundError`

**Location:** `users.py:20-28, 215`
**Confidence:** Medium-High

**Scenario:** Except tuple has `GLib.Error`, `CalledProcessError`, `TimeoutExpired` — misses `FileNotFoundError`. If openssl is missing from PATH, the sub-page shows a traceback and stays open with no toast.

**Fix direction:** Add `FileNotFoundError` / `OSError` to the except tuple.

---

### [x] M6. `default_apps.py` terminal validation rejects paths containing `.`

**Location:** `default_apps.py:100`
**Confidence:** Medium-High

**Scenario:** Whitelist (`isalnum()` after stripping `/`, `-`, `_`) blocks legitimate paths like `/usr/libexec/foot-wrapper.sh`. A valid terminal choice silently does nothing when selected.

**Fix direction:** Use `shutil.which()` / `Path.is_file()` instead of a character whitelist.

---

### [x] M7. `wlr-randr` parser picks wrong token when `wlr-randr` prints an `Outputs:` banner

**Location:** `display.py:336-345, 442-458`
**Confidence:** Medium

**Scenario:** `line.split()[0]` extracts a bogus output name → `wlr-randr --output Outputs --scale 1.25` fails silently (`check=False`). Scale change "succeeds" in settings.json but display never rescales; revert timer reverts the stored value with no feedback.

**Fix direction:** Reuse `_get_displays()` to enumerate outputs; verify return code; surface toast on failure.

---

### [x] M8. `wait_for_apply` poll source ID never stored → leaks on window close

**Location:** `settings_store.py:183-195`
**Confidence:** Medium

**Scenario:** About-page restart flow polls every 50 ms. If apply hangs (30 s timeout), poll keeps firing. If window closes mid-poll, poll continues until timeout. Interacts with C2 (callbacks on dead window).

**Fix direction:** Store source ID, cancel on window close.

---

### [x] M9. `datetime.py` error CSS class only removed on success

**Location:** `datetime.py:110-131`
**Confidence:** Medium-High

**Scenario:** Typo → red row → user fixes typo but row stays red until next successful apply. `TimeoutExpired`/`OSError` paths show toast but never clear the class either.

**Fix direction:** Remove the class at the start of `_run`, not only on success.

---

### [x] M10. `wallpapers.add_custom` runs unbounded file copy on main thread

**Location:** `wallpapers.py:190-237`
**Confidence:** Medium

**Scenario:** User picks a 900 MB video thinking it's a photo → UI freezes during copy → broken thumbnail permanently in picker. No size cap, no MIME sniff.

**Fix direction:** Stat source size (cap ~50 MB), validate via `Gio.File.query_info` or `imghdr`, run copy in a thread with an idle callback.

---

## Not reported (verified clean during audit)

- `_write` in `settings_store.py` uses atomic rename correctly.
- `_load` falls back safely on bad JSON.
- `_run_apply` concurrent-apply guard logic (running/pending flags) is correct except for the exception paths (C1).
- `wallpapers.remove_custom` correctly blocks path traversal out of `CUSTOM_WALLPAPER_DIR`.
- `settings_store._run_apply`'s non-detached Popen is intentional (captures stderr, kills on timeout).
- `dbus_helpers.PulseAudioSubscriber`'s non-detached Popen is intentional (lifetime bound to settings app).
- Capture-mode double-attach in `keyboard.py` is defended by `_capture_done` reset.
- No `shell=True` / `sh -c` user-string paths in any audited file.

## Withdrawn (agent self-corrected on re-read)

- `PowerProfilesHelper._on_props_changed` Variant unpacking — `GLib.Variant.unpack()` recursively unwraps.
- `get_access_points` stale paths — never consumed; SSIDs are re-resolved.
- `language.py` polkit double-prompt — connect order is actually safe.
- `about.py._check_subtitle` on unmapped widget — tolerated by GTK4.
