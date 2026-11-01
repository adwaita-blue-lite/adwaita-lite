# Settings Adwaita Migration — Phase 2 (Wave 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Four agents run **concurrently**, one per page. Mix of Sonnet and Opus (see model column in the file plan). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Convert the four wave-2 pages — `about`, `bluetooth`, `users`, `appearance` — to `Adw.PreferencesPage`. Each page has standard rows plus at least one bespoke widget (wallpaper grid, accent picker, device list, restore-defaults dialog, password dialog) that stays custom and gets wrapped in an `Adw.PreferencesGroup`.

**Architecture:** Same subagent-driven pattern as wave 1. Each agent:

1. Reads the pilot (`power_lock.py`) and at least one converted wave-1 page similar to their target as reference
2. Reads the reference pack (`docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`)
3. Reads their per-page task section in this plan
4. Rewrites their assigned page, commits as a single-file commit, does not push

Controller runs spec + quality reviewers per commit after all four finish, addresses issues, then pushes the batch.

**Tech stack:** Python 3.13, PyGObject, GTK 4, libadwaita. `BasePage.make_*` factories still in place (waves 1–3 don't delete them; Phase 4 does).

**References:**
- Pilot: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py` (commit `7f9473f`)
- Wave-1 reference (similar-complexity conversions for patterns):
  - `files/usr/lib/adwaita-lite/settings/pages/sound.py` (complex widget refs + lifecycle)
  - `files/usr/lib/adwaita-lite/settings/pages/datetime.py` (entry + switches + live timer + subprocess)
  - `files/usr/lib/adwaita-lite/settings/pages/language.py` (banner + guarded dropdowns)
- Design: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Reference pack: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`

---

## Shared expectations for every wave-2 agent

These are the same rules as wave 1 — agents familiar with wave 1 can skim. New items for wave 2 are marked ★.

1. **Inheritance pattern** — `class XyzPage(BasePage, Adw.PreferencesPage)` with dual explicit `__init__` calls.
2. **build() returns self** — populate via `self.add(group)` and `return self`.
3. **Imports** — replace Gtk-only imports with `from gi.repository import Adw, ... Gtk`, add `gi.require_version("Adw", "1")`.
4. **No `self.make_*` calls**.
5. **Signal semantics** — `notify::active` for switches, `notify::selected` for combos, `apply` for entry rows.
6. **Preserve every store call, subscription, and lifecycle hook** from the pre-migration file exactly.
7. **Preserve `setup_cleanup(self)`** wherever the pre-migration code called `setup_cleanup(page)`. If the pre-migration code didn't call it, add it anyway (consistency with pilot + future-proofing; the wave-1 reviewer pulled this into the standard during mouse_touchpad's follow-up).
8. **Omit empty subtitles** — don't call `set_subtitle("")`.
9. ★ **Custom widgets wrap in an `Adw.PreferencesGroup`** — every page in wave 2 has at least one. Give the group a title that reads naturally above the bespoke widget (e.g. `_("Wallpaper")` for the grid, `_("Accent color")` for the picker). The group containing a custom widget typically has that widget as its sole child — pass `None` as `set_header_suffix` unless the design spec says otherwise.
10. ★ **Navigation push replaces modal dialogs** where the design spec calls for it (about's Restore Defaults, users' Change Password). See the "Navigation pattern" section below for the exact structure.
11. ★ **`enable_escape_close` extraction** — any remaining `BasePage.enable_escape_close(dialog)` call on a *plain* `Gtk.Window` (not Adw.AlertDialog or Adw.Dialog) should import from `settings.utils` instead: `from ..utils import enable_escape_close; enable_escape_close(dialog)`. This is the module-level helper we extracted in Phase 0 exactly so wave agents stop threading things through BasePage.
12. **Commit message format**:
    ```
    feat(settings): convert <page> to Adw.PreferencesPage (wave 2)

    <2-3 sentence description + row-type mapping + UX touches>

    Preserves: <comma-separated list of wiring kept intact>.

    Part of the Adwaita migration wave 2. See
    docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md.

    Co-Authored-By: Claude <model> <noreply@anthropic.com>
    ```

## Navigation pattern (reusable by multiple agents)

When a page needs to push a sub-page (Change Password, Restore Defaults), its `build()` returns an `AdwNavigationView` wrapping the PreferencesPage as the root, instead of returning `self` directly.

```python
def build(self):
    # Root page is the usual preferences content. The page class is
    # still Adw.PreferencesPage so all your group-adds work normally
    # on `self` - then we wrap self in a NavigationView before return.
    self.add(group_one)
    self.add(group_two)

    self._nav = Adw.NavigationView()

    root_page = Adw.NavigationPage()
    root_page.set_title(_("Current page title — matches sidebar row"))
    root_page.set_child(self)  # self IS the PreferencesPage

    self._nav.add(root_page)
    return self._nav  # NOT `return self`
```

To push a sub-page, e.g. the password change flow:

```python
def _push_change_password(self, *_):
    sub = Adw.NavigationPage()
    sub.set_title(_("Change Password"))

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())  # automatic back button

    inner = Adw.PreferencesPage()
    group = Adw.PreferencesGroup()
    # ... build rows (AdwPasswordEntryRow, etc.) ...
    inner.add(group)
    toolbar.set_content(inner)

    sub.set_child(toolbar)
    self._nav.push(sub)
```

The back button and Escape both pop automatically.

---

## File plan

| Page | File | Complexity | Model |
|---|---|---|---|
| About | `files/usr/lib/adwaita-lite/settings/pages/about.py` | High (info rows + updates flow + restore-defaults nav-push with category checkboxes) | Opus |
| Bluetooth | `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py` | Med (dynamic device list, banner, status page, scan lifecycle) | Sonnet |
| Users | `files/usr/lib/adwaita-lite/settings/pages/users.py` | Med (entry + switch + button, password nav-push) | Sonnet |
| Appearance | `files/usr/lib/adwaita-lite/settings/pages/appearance.py` | Med (2 bespoke widgets in groups + theme + font size) | Sonnet |

---

## Task: Agent 1 — `about` (Opus)

**File:** `files/usr/lib/adwaita-lite/settings/pages/about.py`

### Overview

Largest wave-2 page. Three groups at top-level (About, Updates, Troubleshooting) + a sub-page for Restore Defaults pushed via navigation.

### Top-level structure

The page returns an `AdwNavigationView` (see "Navigation pattern" above) because it needs to push Restore Defaults as a sub-page.

### About group → info rows

Each system-info row becomes an `Adw.ActionRow` with the `.property` style class:

```python
row = Adw.ActionRow()
row.set_title(_("Operating System"))
row.set_subtitle(f"{os_name} {os_version}".strip())
row.set_subtitle_selectable(True)
row.add_css_class("property")
group.add(row)
```

Rows (in this order):
- Operating System — `{os_name} {os_version}`
- Hostname — `socket.gethostname()`
- Processor — from `/proc/cpuinfo` `model name`
- Memory — from `/proc/meminfo` `MemTotal`
- Disk — from `os.statvfs("/")` (only if the call succeeds; see `disk_row` handling)
- Graphics — from `lspci` (VGA/3D/Display lines)
- Desktop — `labwc <version>` from `labwc --version`

Preserve the exact subprocess / file-read patterns including their `except` clauses.

### Updates group

`Adw.PreferencesGroup` titled `_("Updates")`. One `AdwActionRow`:

- Title: dynamic — starts at `_("Click to check for updates")`, updates via `self._update_label = row.set_subtitle(...)` inside the existing `_check_updates` flow. Wait — `ActionRow` has title + subtitle; use `set_subtitle(...)` for the status text so the row's title remains constant. Retitle the ROW `_("Status")`, use subtitle for the progress messages.
- Suffix: a `Gtk.Button` labelled `_("Check for Updates")` (initial), plus a second `Gtk.Button` labelled `_("Update now…")` with `.suggested-action` class, hidden by default, revealed on status=77.

Because you have two buttons, use `row.add_suffix(check_btn)` twice with both buttons — the row renders them in order. Preserve all existing `_check_updates`, `_set_update_button_visible`, and `_run_update` methods; only the widget references change (`self._update_label` now references the row for `set_subtitle` calls, `self._update_btn` references the update button).

### Troubleshooting group

`Adw.PreferencesGroup` titled `_("Troubleshooting")`. One `AdwActionRow`:

- Title: `_("Restore Defaults")`
- Subtitle: `_("Reset settings to factory defaults")`
- `set_activatable(True)`
- Suffix: `[go-next-symbolic]` `Gtk.Image`
- Connect `"activated"` signal to `self._push_restore_defaults`

### Restore Defaults sub-page

The `RestoreDefaultsDialog` class is removed. Its logic moves into a method `self._push_restore_defaults(*_)` that builds an `AdwNavigationPage` and pushes it onto `self._nav`.

Sub-page structure:

```python
sub = Adw.NavigationPage()
sub.set_title(_("Restore Defaults"))

toolbar = Adw.ToolbarView()
toolbar.add_top_bar(Adw.HeaderBar())  # auto back button

inner = Adw.PreferencesPage()

# Description group with only a description (no rows).
intro_group = Adw.PreferencesGroup()
intro_group.set_description(_("Select which settings to reset to factory defaults."))
inner.add(intro_group)

# Categories group with one AdwSwitchRow per category + a header-suffix "select all" toggle.
cat_group = Adw.PreferencesGroup()
cat_group.set_title(_("Categories"))

# ... Select All switch in header suffix ...
# ... one AdwSwitchRow per CATEGORY_KEYS entry ...
inner.add(cat_group)

# Action group with the Reset button.
action_group = Adw.PreferencesGroup()
reset_btn = Gtk.Button(label=_("Reset"))
reset_btn.add_css_class("destructive-action")
reset_btn.set_sensitive(False)
reset_btn.connect("clicked", self._on_reset_clicked)
reset_row = Adw.ActionRow()
reset_row.add_suffix(reset_btn)
action_group.add(reset_row)
inner.add(action_group)

toolbar.set_content(inner)
sub.set_child(toolbar)
self._nav.push(sub)
```

Category selection state + the select-all toggle guard logic (using `handler_block_by_func`) both preserved.

The `_on_reset_clicked` method:
- Preserve the `selected` → `keys` merging logic.
- Preserve the "Keyboard" side-effect (`keybindings.json` unlink) and the "Display" side-effect (`remove_keys_matching("resolution_")`).
- Preserve the `wait_for_apply` + `GLib.timeout_add_seconds(10, ...)` fallback + `os.execv` restart.
- Instead of `self.close()` on the dialog, pop the sub-page: `self._nav.pop()`.

### Preservation checklist

- All 7 system-info lookups (OS, hostname, CPU, RAM, disk, GPU, labwc version).
- `_check_updates` with its `threading.Thread` + `subprocess.run(["uupd", "update-check"], ...)` + exit-code handling (77 = update available, 0 = up to date).
- `_run_update` with `subprocess.Popen(["foot", "-e", "ujust", "update"], ...)`.
- `CATEGORY_KEYS` constant — unchanged.
- All `self._store.get_defaults()`, `restore_keys`, `remove_keys_matching`, `wait_for_apply` calls.
- `os.execv` restart dance with `restarted = [False]` guard.

### UX touches from design spec

- System-info rows use the `.property` Adwaita style class (emphasises subtitle over title). This is the concrete UX win for about — no custom CSS needed.
- Restore Defaults becomes a navigation push rather than an overlay dialog. This is the GNOME-native pattern.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/about.py').read()); print('OK')"
grep -cE 'CATEGORY_KEYS|wait_for_apply|remove_keys_matching|keybindings.json' files/usr/lib/adwaita-lite/settings/pages/about.py
# Expected: >= 5
grep -cE 'uupd|ujust|foot' files/usr/lib/adwaita-lite/settings/pages/about.py
# Expected: >= 3
grep -cE 'RestoreDefaultsDialog|class.*Dialog' files/usr/lib/adwaita-lite/settings/pages/about.py
# Expected: 0 (dialog class removed, logic moves into methods)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/about.py
# Expected: 0
```

### Commit

Template summary: *"Three top-level groups (About / Updates / Troubleshooting) using AdwActionRow with the .property class for system-info rows, suffix buttons in the Updates row, and a chevron-suffix Restore Defaults row that pushes an AdwNavigationPage containing the category checkboxes + destructive Reset button. Page returns an AdwNavigationView wrapping self."*

Preservation line: *"all 7 system-info probes, uupd check / ujust update-in-foot flow, CATEGORY_KEYS, the keybindings.json unlink and resolution_ remove-keys-matching side effects, wait_for_apply + os.execv restart dance."*

---

## Task: Agent 2 — `bluetooth` (Sonnet)

**File:** `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py`

### Groups (top-down)

1. **Main toggle group** (no title) — one `AdwSwitchRow`:
   - Title: `_("Bluetooth")`
   - State: `self._bt.is_powered()`
   - Handler: `self._on_toggle(row, _pspec)` → read `row.get_active()`, preserve the `_updating` guard.
   - Replace `state-set` with `notify::active` — the handler return value is no longer needed (`notify::active` has no return).
2. **No-adapter banner** — `Adw.Banner.new(_("No Bluetooth adapter found"))`, `set_revealed(not self._bt.available)`. Add via `self.add(banner)` between the toggle group and the device groups. Revealed conditionally — when revealed, the device groups below are empty or hidden.
3. **Paired devices group** — `Adw.PreferencesGroup` titled `_("Paired Devices")`. Populated dynamically via `_refresh_devices`. Each device becomes an `Adw.ActionRow` (see device-row pattern below).
4. **Available devices group** — `Adw.PreferencesGroup` titled `_("Available Devices")`, header-suffix is the scan button. Scan button is:
   - Label `_("Search for devices")` → `_("Scanning...")` while active.
   - Disabled during scan.
   - Clicking triggers `self._on_scan_clicked`.
   Populated dynamically via `_refresh_devices`.
5. **Advanced group** — one `AdwActionRow` titled `_("Advanced")`, chevron suffix, activated → `subprocess.Popen(["blueman-manager"], ...)`.

### Status / empty-state

Replace the inline `self._status_label` with toast calls via `self.store.show_toast(...)` for one-off feedback (pairing started, paired successfully, pairing failed). For empty device groups:
- Paired group: no `StatusPage`; just leave the group empty (it renders with a placeholder line in libadwaita) or `group.set_description(_("No paired devices"))`.
- Available group: if the group is empty while scanning, `group.set_description(_("Scanning for devices..."))`. If empty and not scanning, `group.set_description(_("Tap 'Search' to find nearby devices"))`.

Use `group.set_description(...)` instead of bringing in `AdwStatusPage` for these, because `StatusPage` takes over the whole page and we have other groups visible.

### Device row pattern

```python
def _build_device_row(self, dev):
    row = Adw.ActionRow()
    row.set_title(dev.name or _("Unknown device"))
    icon = Gtk.Image.new_from_icon_name(dev.icon or "bluetooth-symbolic")
    row.add_prefix(icon)

    if dev.paired:
        if dev.connected:
            row.set_subtitle(_("Connected"))
            dc_btn = Gtk.Button(label=_("Disconnect"))
            dc_btn.set_valign(Gtk.Align.CENTER)
            dc_btn.connect("clicked", lambda _, p=dev.path: self._bt.disconnect_device(p))
            row.add_suffix(dc_btn)
        else:
            conn_btn = Gtk.Button(label=_("Connect"))
            conn_btn.set_valign(Gtk.Align.CENTER)
            conn_btn.connect("clicked", lambda _, p=dev.path: self._bt.connect_device(p))
            row.add_suffix(conn_btn)

        forget_btn = Gtk.Button(label=_("Forget"))
        forget_btn.set_valign(Gtk.Align.CENTER)
        forget_btn.add_css_class("flat")
        forget_btn.connect("clicked", lambda _, p=dev.path: self._bt.remove_device(p))
        row.add_suffix(forget_btn)
    else:
        pair_btn = Gtk.Button(label=_("Pair"))
        pair_btn.set_valign(Gtk.Align.CENTER)
        pair_btn.connect("clicked", lambda _, p=dev.path: self._pair(p))
        row.add_suffix(pair_btn)

    return row
```

`_refresh_devices` walks `group` children and removes each one (use `group.remove(row)` — `Adw.PreferencesGroup` supports `.remove`), then re-adds rows for the current `self._bt.get_devices()` output.

### Preservation checklist

- `self._updating` guard on `_on_toggle`.
- `_on_scan_clicked` → `start_discovery()` + 30-second `GLib.timeout_add_seconds` to auto-stop.
- `_stop_scan` restoring the button state and returning `GLib.SOURCE_REMOVE`.
- `_cleanup` on unmap: cancel the scan timer, call `stop_discovery()`.
- Three subscriptions: `bluetooth-changed` → `_refresh_devices`, `bluetooth-pair-success`, `bluetooth-pair-error`.
- `setup_cleanup(self)` at end of `build()`.
- All `BlueZHelper` method calls preserved (`is_powered`, `set_powered`, `available`, `start_discovery`, `stop_discovery`, `get_devices`, `pair_device`, `connect_device`, `disconnect_device`, `remove_device`).

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/bluetooth.py').read()); print('OK')"
grep -cE 'BlueZHelper|bluetooth-changed|bluetooth-pair' files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
# Expected: >= 5 (import, instantiation, 3 subscribe calls)
grep -cE 'start_discovery|stop_discovery' files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
# Expected: >= 4
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/bluetooth.py
# Expected: 0
```

### Commit

Template summary: *"AdwSwitchRow for the power toggle, AdwBanner for no-adapter state, two AdwPreferencesGroups (Paired / Available) populated dynamically with AdwActionRow per device, Advanced button as a chevron-suffix row. Scan button lives as a header-suffix on the Available group."*

Preservation line: *"_updating guard on the toggle, 30-second scan auto-stop, scan-timer cleanup on unmap, all 3 bluetooth-* subscriptions, all 9 BlueZHelper calls."*

---

## Task: Agent 3 — `users` (Sonnet)

**File:** `files/usr/lib/adwaita-lite/settings/pages/users.py`

### Groups

Note: this page represents only the current user — it's not a multi-user list. No "add user" header-suffix button needed (the design spec anticipated a list; reality is a single-user page).

1. **Account group** (`_("Account")`):
   - `AdwEntryRow` titled `_("Display name")`:
     - `set_show_apply_button(True)`
     - Initial text: `self._get_property("RealName")`
     - `apply` signal → `self._on_name_activate(row)` (rename to `_on_name_applied` for signal accuracy, OK to keep)
   - `AdwActionRow` titled `_("Password")`:
     - `set_activatable(True)`
     - Subtitle: `_("Set a new password for your account")`
     - Add `[go-next-symbolic]` suffix
     - `activated` signal → `self._push_change_password`
   - `AdwSwitchRow` titled `_("Automatic login")`:
     - Subtitle: `_("Log in without a password at startup")`
     - Active: `self._get_property("AutomaticLogin")`
     - `notify::active` → `self._on_autologin_set`

### D-Bus error path

If `_ensure_dbus` raises `GLib.Error`, skip the Account group and show an `Adw.StatusPage` filling the page:

```python
status = Adw.StatusPage()
status.set_icon_name("dialog-error-symbolic")
status.set_title(_("Could not connect to AccountsService"))
status.set_description(_("User account settings are unavailable."))
self.add(status)
return self
```

(StatusPage is legal as a direct child of PreferencesPage; it takes the whole visible area.)

### Password change: navigation push

`_on_change_password` (formerly created a Gtk.Window dialog) becomes `_push_change_password`. The password sub-page uses `AdwPasswordEntryRow` for both fields (pattern in the reference pack):

```python
def _push_change_password(self, *_):
    sub = Adw.NavigationPage()
    sub.set_title(_("Change Password"))

    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    inner = Adw.PreferencesPage()
    group = Adw.PreferencesGroup()
    group.set_description(_("Enter a new password for your account."))

    new_pw = Adw.PasswordEntryRow()
    new_pw.set_title(_("New password"))
    group.add(new_pw)

    confirm_pw = Adw.PasswordEntryRow()
    confirm_pw.set_title(_("Confirm password"))
    group.add(confirm_pw)

    inner.add(group)

    # Apply button as a suggested-action row below the entries.
    action_group = Adw.PreferencesGroup()
    apply_row = Adw.ActionRow()
    apply_btn = Gtk.Button(label=_("Apply"))
    apply_btn.add_css_class("suggested-action")
    apply_btn.set_valign(Gtk.Align.CENTER)
    apply_btn.connect("clicked", lambda _b: self._apply_password_change(
        new_pw, confirm_pw, sub))
    apply_row.add_suffix(apply_btn)
    action_group.add(apply_row)
    inner.add(action_group)

    toolbar.set_content(inner)
    sub.set_child(toolbar)
    self._nav.push(sub)
```

`_apply_password_change(new_pw, confirm_pw, sub)`:
- Validate: empty check, mismatch check (show an `Adw.Toast` via `self.store.show_toast(...)` for errors instead of an inline error label, so the sub-page stays clean).
- On success: compute `_hash_password(pw)`, call `SetPassword` via D-Bus, then `self._nav.pop()`.
- On failure: show toast `_("Failed to set password")`.

### Top-level structure

Returns an `AdwNavigationView` because of the password push. Root `AdwNavigationPage` title = `_("Users")`.

### Preservation checklist

- `_hash_password` function unchanged (openssl passwd -6 subprocess).
- `_ensure_dbus`, `_get_property`, `_DBUS_TIMEOUT_MS` unchanged.
- All three D-Bus `call_sync` sites preserved: FindUserById (in `_ensure_dbus`), SetRealName (in name handler), SetAutomaticLogin (in auto-login handler), SetPassword (in password change apply).
- The exact exception handling on each D-Bus call.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/users.py').read()); print('OK')"
grep -cE 'call_sync|FindUserById|SetRealName|SetAutomaticLogin|SetPassword' files/usr/lib/adwaita-lite/settings/pages/users.py
# Expected: >= 5
grep -cE 'openssl|_hash_password' files/usr/lib/adwaita-lite/settings/pages/users.py
# Expected: >= 3
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/users.py
# Expected: 0
```

### Commit

Template summary: *"Account group with AdwEntryRow (Display name + apply button), AdwActionRow (Password) pushing an AdwNavigationPage with two AdwPasswordEntryRows + Apply button, and AdwSwitchRow for Automatic login. D-Bus connection failures render as an AdwStatusPage covering the full page."*

Preservation line: *"_hash_password openssl subprocess, all 4 D-Bus call_sync sites (FindUserById, SetRealName, SetAutomaticLogin, SetPassword), _DBUS_TIMEOUT_MS constant, _ensure_dbus lazy-connect pattern."*

---

## Task: Agent 4 — `appearance` (Sonnet)

**File:** `files/usr/lib/adwaita-lite/settings/pages/appearance.py`

### Groups (top-down)

1. **Theme group** (`_("Theme")`):
   - `AdwSwitchRow` titled `_("Dark mode")`:
     - Subtitle: none (omit)
     - Active: `self.store.get("theme", "light") == "dark"`
     - Handler (`notify::active`): `self.store.save_and_apply("theme", "dark" if row.get_active() else "light")`
   - If `self.store.get("high_contrast", False)`, set `group.set_description(_("Theme is set to Dark by High Contrast mode"))`. (Replaces the inline subtitle label; description appears right below the group title.)
2. **Accent color group** (`_("Accent color")`):
   - Contains the existing accent picker `Gtk.Box` (`.accent-circle` toggle buttons) as a sole child. The box stays custom; wrap it in an `AdwActionRow` with no title and the box added via `add_suffix(accent_box)` — OR just add the box directly to the group. Prefer direct add: `group.add(accent_box)`. But `Adw.PreferencesGroup.add` expects a row; if it rejects a plain Gtk.Box, wrap in a `Adw.ActionRow` and `row.add_suffix(accent_box)` (centre the box). See what the Adwaita reference allows; if group.add(box) errors at runtime (the reference pack's anti-patterns section notes `Don't put rows directly inside AdwPreferencesPage without an AdwPreferencesGroup` — group.add of a non-row is likely similar). Default to wrapping in an `Adw.ActionRow` with `row.set_activatable(False)` and `row.add_suffix(accent_box)`.
3. **Font size group** (`_("Font size")`):
   - `AdwComboRow` titled `_("Font size")`, subtitle `_("Affects all text throughout the interface")`:
     - Options: Small (10), Default (11), Large (13), Larger (15)
     - Current: `str(self.store.get("font_size", 11))`
     - `notify::selected` → `self.store.save_and_apply("font_size", int(font_values[idx]))`
4. **Wallpaper group** (`_("Wallpaper")`):
   - Contains the existing wallpaper `Gtk.FlowBox` as a sole child, wrapped the same way as the accent picker (inside an `Adw.ActionRow` via `add_suffix`, or directly if `group.add` accepts). The whole `_populate_wallpapers`, `_make_wallpaper_tile`, `_make_add_tile`, `_on_wallpaper_toggled`, `_on_custom_clicked`, `_on_remove_custom` chain preserved verbatim.
   - Wallpaper load failures still fall back to a message. Use `group.set_description(_("Wallpaper picker unavailable"))` instead of an inline label.

### Preservation checklist

- `ACCENT_COLORS`, `TILE_W`, `TILE_H`, `THUMB_MAX` constants unchanged.
- `_load_thumbnail` function unchanged.
- All three `save_and_apply` call sites preserved: theme, accent, font_size. Plus wallpaper saves via `save_and_apply("wallpaper", wp.id)` — also preserved.
- The `high_contrast` subtitle note moves from an inline Label to `group.set_description(...)` on the Theme group. Still conditional on `self.store.get("high_contrast", False)`.
- Accent toggle logic (`_on_accent_toggled` preventing multiple active) preserved.
- All wallpaper manifest handling (`list_wallpapers`, `add_custom`, `remove_custom`, path-for-theme, current-mapping from legacy absolute path) preserved.

### Verification

```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/appearance.py').read()); print('OK')"
grep -cE 'save_and_apply' files/usr/lib/adwaita-lite/settings/pages/appearance.py
# Expected: >= 4 (theme, accent, font_size, wallpaper x2 via toggle and on-custom-clicked)
grep -cE 'list_wallpapers|add_custom|remove_custom|Wallpaper' files/usr/lib/adwaita-lite/settings/pages/appearance.py
# Expected: >= 5
grep -cE 'ACCENT_COLORS' files/usr/lib/adwaita-lite/settings/pages/appearance.py
# Expected: 2 (definition + usage)
grep -cE 'self\.make_' files/usr/lib/adwaita-lite/settings/pages/appearance.py
# Expected: 0
```

### Commit

Template summary: *"Four groups: Theme (AdwSwitchRow 'Dark mode' with high-contrast note as group description), Accent color (existing toggle-button picker wrapped in an AdwActionRow suffix), Font size (AdwComboRow), Wallpaper (existing FlowBox wrapped in an AdwActionRow suffix). Custom widgets are preserved verbatim; only the outer chrome changes."*

Preservation line: *"save_and_apply for theme / accent / font_size / wallpaper, all wallpaper manifest handling (list_wallpapers / add_custom / remove_custom), _load_thumbnail, accent single-active guard, high-contrast note (now group description)."*

---

## Controller tasks after agents finish

Same as wave 1: confirm commits exist, run spec review per commit, run quality review per commit after spec passes, push the batch, smoke-test on hardware.

- [ ] **Step 1: Confirm four commits locally**

```bash
git log --oneline HEAD~4..HEAD
```

Expected: four `feat(settings): convert <page> to Adw.PreferencesPage (wave 2)` commits.

- [ ] **Step 2: Spec-compliance reviews (parallel)**

Dispatch one spec reviewer subagent per commit with: commit SHA, the per-page task section in this plan, the pilot file.

- [ ] **Step 3: Code-quality reviews (parallel, after spec passes)**

Dispatch one quality reviewer subagent per commit with: commit SHA, the pre-migration version at `git show HEAD~<offset>:<path>`, the reference pack.

- [ ] **Step 4: Push**

```bash
git push
```

- [ ] **Step 5: Hardware smoke test**

After CI build completes, update target machine and verify each page:

- **About** — all 7 system-info rows render with correct values. "Check for Updates" button fires the uupd check. "Restore Defaults" pushes a sub-page with category switches; back gesture works. Selecting "Keyboard" + Reset triggers the keybindings.json unlink and process restart.
- **Bluetooth** — toggle turns adapter on/off, banner appears when no adapter, paired/available lists populate after a scan. Pair → status feedback via toast. Advanced opens blueman-manager.
- **Users** — Display name entry's apply button persists the change over D-Bus. Change Password pushes a sub-page; mismatch / empty show toasts; success pops the page. Auto-login switch takes effect after next logout.
- **Appearance** — Dark mode switch flips the theme (adw-gtk3 reloads). Accent circles still select with single-active behavior. Font size combo applies. Wallpaper tiles still select and persist. "Add picture…" tile opens the file dialog.

If any page misbehaves, `git revert <sha>` that specific commit and re-dispatch.

---

## Completion criteria

- Four commits on `origin/main`, each converting one wave-2 page.
- All four pages inherit from `BasePage` + `Adw.PreferencesPage`.
- `base.py` factories still intact.
- Hardware smoke test passes for every converted page.
- Wave 2 reference material ready for wave 3 agents.
