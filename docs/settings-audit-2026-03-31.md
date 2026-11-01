# Settings App Audit & Fixes — 2026-03-31

Audit of the GTK4 settings app (`files/usr/lib/adwaita-lite/settings/`).
Four parallel agents reviewed all 17 source files across the infrastructure,
network/system, display/hardware, and UI/info layers.

---

## Changes Made

### 1. `settings/settings_store.py` — Startup crash on missing defaults file

**Bug:** Two unguarded `_defaults_path.read_text()` calls in `_load()`. A
missing `/usr/share/adwaita-lite/defaults/settings.json` (partial install,
developer checkout) raised `FileNotFoundError` before any window opened.

**Fix:** Extracted `_load_defaults()` helper that wraps all reads in
`try/except OSError` and `try/except json.JSONDecodeError`. App now degrades
to empty settings instead of crashing.

---

### 2. `settings/pages/display.py` — Resolution changes always silently fail

**Bug:** `_apply_resolution` had a dead `--mode` branch. `len(parts) > 1` was
always `True` (mode strings are always `"WxH@RHz"`), so every call used
`--custom-mode`. wlr-randr rejects `--custom-mode` for standard advertised
modes.

**Fix:** Single `--mode mode_arg` call, stripping the `"Hz"` suffix
(`"1920x1080@60.0Hz"` → `"1920x1080@60.0"`).

---

### 3. `settings/pages/default_apps.py` — Page open clobbers MIME defaults

**Bug:** The `notify::selected` handler was connected after `set_selected()`
but the timing depended on GTK's initial selection value for `GtkDropDown`.
If the dropdown initialised at `GTK_INVALID_LIST_POSITION` (which varies by
GTK build), `set_selected(0)` in the `except ValueError` path would fire
`xdg-mime default <app[0]> <mime>` during construction, overwriting the user's
current MIME defaults.

**Fix:** Per-row `_loading = [True]` flag cleared to `False` after
initialisation. Signal handlers are no-ops while loading.

---

### 4. `settings/dbus_helpers.py` — Duplicate NM connection profiles accumulate

**Bug:** Every "Connect" click called `add_and_activate_connection_async` with
a freshly constructed `SimpleConnection`, never checking existing saved
profiles. Users accumulated duplicate profiles per SSID.

**Fix:**
- Added `_find_connection_by_ssid()` — matches by SSID bytes (not display name).
- Added `_on_activate_done()` — uses `activate_connection_finish()` for the
  reuse path.
- `connect_wifi()` now calls `activate_connection_async` on an existing saved
  profile when no new password/hidden flag is supplied; creates a new profile
  otherwise.

---

### 5. `settings/base.py` — Toggle cards fire `save_and_apply` twice per click

**Bug:** Deactivating the previous button triggered its `toggled` handler,
which re-activated it via `set_active(True)`, re-entering `_on_toggled` with
`get_active()==True` and calling `callback(value)` a second time — doubling
apply-script invocations on every theme, scale, or panel-position change.

**Fix:** `_updating = [False]` reentrancy guard (mutable list for closure
mutability). All `set_active` calls inside the mutual-exclusion loop are
ignored by the handler.

---

### 6. `settings/pages/accessibility.py` — Large Text clobbers Appearance font size

**Bug:** Turning Large Text OFF always wrote `font_size=11`, discarding any
intermediate size (10, 13) the user had intentionally set on the Appearance
page.

**Fix:** ON path saves `_large_text_prev_font = current font_size` (if `< 15`)
before overriding to 15. OFF path restores from that key (fallback: 11). The
`_large_text_prev_font` key is internal metadata — the apply-settings script
ignores unknown keys.

---

### 7. `settings/pages/about.py` — labwc version always blank

**Bug:** `subprocess.run(["labwc", "--version"]).stdout.strip()` — labwc
writes its version to `stderr`, not `stdout`. The Desktop row always displayed
"labwc ".

**Fix:** `(r.stderr.strip() or r.stdout.strip()) or "unknown"` — reads stderr
first, falls back to stdout for forward compatibility.

---

### Tests: `tests/test_settings_store.py` — Two new regression tests

- `test_missing_defaults_file_returns_empty` — constructs `SettingsStore` with
  a nonexistent defaults path; asserts no crash and `get()` returns the
  fallback value.
- `test_corrupted_file_with_missing_defaults_returns_empty` — corrupt user
  file + missing defaults; same assertion.

---

## Unverified in This Environment

| Item | Why unverified |
|------|----------------|
| All test files | `pytest` not installed on the host; install blocked to avoid package breakage |
| `_apply_resolution` wlr-randr `--mode` format | No compositor available to test against |
| `connect_wifi` reuse path | Requires a live NM session with saved connections |
| `_loading` guard in default_apps | GTK version-dependent; the underlying race could not be reproduced without a display |
| `make_toggle_cards` double-callback | Requires GTK to confirm signal re-entrancy depth |
| `accessibility.py` prev-font restore | Round-trip requires a live settings apply run |

---

## What To Do Next (Unconstrained Dev Environment)

1. **Run the full test suite** — `python3 -m pytest tests/ -v`. Confirm the
   two new settings-store tests pass and no existing tests regressed.

2. **Verify resolution changes** — On a live Wayland session, open the Display
   page and confirm mode changes actually take effect. Check `wlr-randr` output
   before and after to confirm the correct mode was selected.

3. **Smoke-test toggle cards** — Open Appearance, click through scale options
   and themes. Confirm the apply-settings script fires once (not twice) per
   click. A quick check: count `pkill` events or log lines from the apply
   script.

4. **Verify NM dedup** — Connect to a saved network twice. Confirm only one
   profile exists in `nmcli connection show` after both connects.

5. **Verify labwc version** — On a running labwc session, open About. Confirm
   the Desktop row shows a real version string instead of "labwc ".

6. **Test Large Text round-trip** — Set font size to 13 on Appearance. Go to
   Accessibility, toggle Large Text ON then OFF. Confirm font size returns to
   13, not 11.

7. **Audit the remaining Medium/Low items** from the full audit report (not
   fixed in this session):
   - `dbus_helpers.py` NM client failure not surfaced to UI (`nm-unavailable` event)
   - `window.py` page build failure crashes entire window (no per-page guard)
   - `events.py` dead-callback delivery after page destroy
   - `bluetooth.py` orphaned scan timer and no BlueZ pairing agent
   - `users.py` blocking D-Bus call in `_ensure_dbus()`
   - `display.py` stale revert timer on rapid scale/resolution changes
   - `power_lock.py` `pkexec` fire-and-forget (store committed before write completes)
   - `datetime.py` silent timezone validation failure
   - `sound.py` PulseAudioSubscriber no reconnect after audio server restart

---

## Files Changed

```
files/usr/lib/adwaita-lite/settings/settings_store.py
files/usr/lib/adwaita-lite/settings/base.py
files/usr/lib/adwaita-lite/settings/pages/display.py
files/usr/lib/adwaita-lite/settings/pages/default_apps.py
files/usr/lib/adwaita-lite/settings/pages/accessibility.py
files/usr/lib/adwaita-lite/settings/pages/about.py
files/usr/lib/adwaita-lite/settings/dbus_helpers.py
tests/test_settings_store.py
```
