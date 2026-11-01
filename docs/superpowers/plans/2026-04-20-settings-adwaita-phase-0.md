# Settings Adwaita Migration — Phase 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the pilot infrastructure for the settings-Adwaita migration: convert `power_lock` end-to-end as the reference template and extract `enable_escape_close` to `settings/utils.py`. All other pages stay on the existing `BasePage.make_*` widget factories (those get deleted only in Phase 4 after every page has migrated).

**Architecture:** Pages inherit from both `BasePage` (for the protocol contract — `search_keywords`, `build()`, `subscribe`, `setup_cleanup`) and `Adw.PreferencesPage` (for the GNOME-native UI). `build()` populates the page by calling `self.add(group)` and returns `self`. Existing lazy-build machinery in `window.py` (which treats `build()`'s return value as the widget to stack) keeps working unchanged because `self` *is* the widget.

**Tech Stack:** Python 3.13, PyGObject, GTK 4, libadwaita (already in the image via the earlier settings-shell migration).

**References:**
- Design spec: `docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md`
- Reference pack: `docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md`

**Ships as:** one git commit at the end of Task 4. No intermediate commits — Phase 0 is an atomic infrastructure change.

---

## File plan

| File | Change | Purpose |
|---|---|---|
| `files/usr/lib/adwaita-lite/settings/utils.py` | **Create** | Housing for standalone helpers (`enable_escape_close`) that don't belong on `BasePage`. New imports by wave agents land here instead of accruing on `BasePage`. |
| `files/usr/lib/adwaita-lite/settings/pages/power_lock.py` | **Rewrite** | Pilot conversion. Establishes the inheritance pattern, `AdwComboRow` usage, event-bus subscription preservation, and `setup_cleanup` wiring. |
| `files/usr/lib/adwaita-lite/settings/base.py` | No change | Widget factories stay for waves 1–3. Deleted in Phase 4. |
| `files/usr/lib/adwaita-lite/settings/pages/__init__.py` | No change | Registration tuple still references `PowerLockPage`. |

---

## Task 1: Create `settings/utils.py`

**Files:**
- Create: `files/usr/lib/adwaita-lite/settings/utils.py`

- [ ] **Step 1: Write the module with the extracted helper**

```python
"""Standalone helpers used across settings pages.

Home for utilities that don't belong as instance methods on
BasePage - they don't depend on page state, and threading them
through BasePage just so pages can call self.foo() is gratuitous.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk


def enable_escape_close(dialog: Gtk.Window) -> None:
    """Close *dialog* when the user presses Escape.

    GTK4's Gtk.Window does not wire Escape -> close by default
    (only the old Gtk.Dialog did). This matches the GNOME HIG
    expectation that every dialog is dismissible via the keyboard.

    For Adw.AlertDialog and Adw.Dialog, Escape-to-close is already
    built in - use this helper only on plain Gtk.Window instances
    (e.g. custom modal flows on pages that have not yet migrated to
    AdwNavigationView push navigation).
    """
    controller = Gtk.EventControllerKey()

    def _on_key(_c: Gtk.EventControllerKey, keyval: int, _kc: int,
                _state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            dialog.close()
            return True
        return False

    controller.connect("key-pressed", _on_key)
    dialog.add_controller(controller)
```

- [ ] **Step 2: Syntax check**

Run:
```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/utils.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Stage the file**

Run:
```bash
git add files/usr/lib/adwaita-lite/settings/utils.py
```

Do NOT commit yet. Phase 0 commits as one atomic change at the end of Task 4.

---

## Task 2: Convert `power_lock.py` to the new pattern

**Files:**
- Modify (full rewrite): `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`

**Design decisions specific to this page:**

1. **All four controls become `AdwComboRow`, not `AdwSpinRow`.** The spec's default was SpinRow for timeout-style settings, but `power_lock`'s timeouts are a fixed palette of named options (`1 minute`, `5 minutes`, `Never`, etc.) — the current dropdowns are semantically a discrete choice, not a continuous number. `AdwComboRow` with a `Gtk.StringList` model preserves the exact set of options the user is used to. The "rationale required if pushing back on the spec" rule covers this: rationale recorded here.
2. **Power profile keeps the special event-bus wiring.** `power-profile-changed` bus events must still move the selection when `power-profiles-daemon` reports a change from elsewhere (e.g. a command-line `powerprofilesctl set`). We wire this via the `AdwComboRow`'s `set_selected()` inside the bus handler.
3. **Lid action keeps the pkexec out-of-band flow.** That subprocess dance runs on a background thread, calls `self.store.save_and_apply` via `GLib.idle_add` on success, and shows a toast on failure. All preserved verbatim — only the widget the user interacts with changes.

- [ ] **Step 1: Write the full new page**

```python
import subprocess
import threading
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage

# Timeout palette shared by Lock, Display, and Suspend rows. Order is
# the order the options appear in the dropdown. The second element is
# the seconds value persisted in settings (0 = Never).
TIMEOUT_OPTIONS: list[tuple[str, int]] = [
    (_("1 minute"), 60),
    (_("2 minutes"), 120),
    (_("5 minutes"), 300),
    (_("10 minutes"), 600),
    (_("15 minutes"), 900),
    (_("30 minutes"), 1800),
    (_("Never"), 0),
]

PROFILE_OPTIONS: list[tuple[str, str]] = [
    ("balanced", _("Balanced")),
    ("power-saver", _("Power Saver")),
    ("performance", _("Performance")),
]

LID_OPTIONS: list[tuple[str, str]] = [
    ("suspend", _("Suspend")),
    ("lock", _("Lock")),
    ("nothing", _("Do Nothing")),
]


class PowerLockPage(BasePage, Adw.PreferencesPage):
    """Power-management settings: screen/display timeouts, power profile,
    suspend-on-idle, and lid close action.

    Adwaita pilot page. Every other page converted after this one
    inherits this file's patterns:

      - Dual inheritance: BasePage (page protocol) + Adw.PreferencesPage (UI).
      - __init__ is cheap (stores refs only). build() populates and
        returns self so window.py's lazy-build machinery is unchanged.
      - A ComboRow pattern where the on-disk value and the visible
        label are separate: keep a parallel `values` list, map
        get_selected() -> values[idx] on change, values.index(current)
        -> set_selected() on load / external update.
      - Event-bus subscriptions set up in build() and torn down via
        setup_cleanup(self) on unmap.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        # Widgets we need to reach from outside build() (event-bus
        # handlers, test hooks) are held as attributes. Initialised
        # to None here; populated in build().
        self._profile_row: Adw.ComboRow | None = None

    @property
    def search_keywords(self):
        return [
            (_("Lock & Display"), _("Lock screen")),
            (_("Lock & Display"), _("Display off")),
            (_("Power Profile"), _("Power")),
            (_("Power Profile"), _("Battery")),
            (_("Suspend on Idle"), _("Suspend")),
            (_("Suspend on Idle"), _("Idle")),
            (_("Lid Close Behavior"), _("Lid")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        self.add(self._build_lock_display_group())
        self.add(self._build_power_profile_group())
        self.add(self._build_suspend_group())
        self.add(self._build_lid_group())

        # Fire when power-profiles-daemon reports an external change.
        self.subscribe("power-profile-changed", self._on_profile_changed)

        # Tear down event-bus subscriptions on unmap.
        self.setup_cleanup(self)
        return self

    # -- group builders -------------------------------------------------

    def _build_lock_display_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Lock & Display"))

        group.add(self._make_timeout_row(
            title=_("Lock screen after"),
            key="lock_timeout",
            default=300,
        ))
        group.add(self._make_timeout_row(
            title=_("Turn off display after"),
            key="display_off_timeout",
            default=600,
        ))
        return group

    def _build_power_profile_group(self) -> Adw.PreferencesGroup:
        from ..dbus_helpers import PowerProfilesHelper
        self._power_helper = PowerProfilesHelper(self.event_bus)

        row = Adw.ComboRow()
        row.set_title(_("Power profile"))
        row.set_subtitle(_("Balance between performance and battery life"))

        labels = [label for _value, label in PROFILE_OPTIONS]
        values = [value for value, _label in PROFILE_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self._power_helper.get_active_profile()
        row.set_selected(
            values.index(current) if current in values else 0
        )

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self._power_helper.set_active_profile(values[idx])

        row.connect("notify::selected", _on_selected)
        self._profile_row = row

        group = Adw.PreferencesGroup()
        group.set_title(_("Power Profile"))
        group.add(row)
        return group

    def _build_suspend_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Suspend on Idle"))
        group.set_description(
            _("Put the computer to sleep after a period of inactivity.")
        )
        group.add(self._make_timeout_row(
            title=_("Suspend after"),
            key="suspend_timeout",
            default=0,  # Never, by default
        ))
        return group

    def _build_lid_group(self) -> Adw.PreferencesGroup:
        row = Adw.ComboRow()
        row.set_title(_("When lid is closed"))

        labels = [label for _value, label in LID_OPTIONS]
        values = [value for value, _label in LID_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self.store.get("lid_close_action", "suspend")
        row.set_selected(values.index(current) if current in values else 0)

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self._on_lid_action_changed(values[idx])

        row.connect("notify::selected", _on_selected)

        group = Adw.PreferencesGroup()
        group.set_title(_("Lid Close Behavior"))
        group.add(row)
        return group

    # -- row factory ----------------------------------------------------

    def _make_timeout_row(self, *, title: str, key: str,
                          default: int) -> Adw.ComboRow:
        row = Adw.ComboRow()
        row.set_title(title)

        labels = [label for label, _secs in TIMEOUT_OPTIONS]
        values = [secs for _label, secs in TIMEOUT_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self.store.get(key, default)
        row.set_selected(values.index(current) if current in values else 0)

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self.store.save_and_apply(key, values[idx])

        row.connect("notify::selected", _on_selected)
        return row

    # -- event handlers -------------------------------------------------

    def _on_profile_changed(self, new_profile: str) -> None:
        """Move the ComboRow selection to match an out-of-band profile change.

        Fires when power-profiles-daemon reports that the active
        profile changed via some mechanism other than our row (e.g.
        `powerprofilesctl set`). Guarded by an identity check against
        the current selection so we don't loop on our own save.
        """
        if self._profile_row is None:
            return
        values = [value for value, _label in PROFILE_OPTIONS]
        if new_profile not in values:
            return
        idx = values.index(new_profile)
        if self._profile_row.get_selected() != idx:
            self._profile_row.set_selected(idx)

    def _on_lid_action_changed(self, action: str) -> None:
        """Apply a new lid action via the privileged helper.

        Preserved verbatim from the pre-migration version: pkexec on
        a background thread; on success, persist via the store on the
        GLib main loop; on failure, show a toast.
        """
        def _run() -> None:
            try:
                result = subprocess.run(
                    ["pkexec", "/usr/libexec/adwaita-lite-lid-action", action],
                    capture_output=True, timeout=60,
                )
            except subprocess.TimeoutExpired:
                GLib.idle_add(
                    lambda: self.store.show_toast(
                        _("Lid action change timed out"), True) or False
                )
                return
            except OSError:
                GLib.idle_add(
                    lambda: self.store.show_toast(
                        _("pkexec not available"), True) or False
                )
                return

            if result.returncode == 0:
                GLib.idle_add(
                    lambda: self.store.save_and_apply(
                        "lid_close_action", action) or False
                )
            elif result.returncode == 126:
                # Polkit auth declined — silent, user already knows.
                pass
            else:
                GLib.idle_add(
                    lambda: self.store.show_toast(
                        _("Failed to change lid close action"), True) or False
                )

        threading.Thread(target=_run, daemon=True).start()
```

- [ ] **Step 2: Syntax check**

Run:
```bash
python3 -c "import ast; ast.parse(open('files/usr/lib/adwaita-lite/settings/pages/power_lock.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Preservation sanity check**

Run:
```bash
grep -c 'save_and_apply\|self.subscribe\|setup_cleanup\|PowerProfilesHelper\|pkexec' files/usr/lib/adwaita-lite/settings/pages/power_lock.py
```

Expected: ≥ 7 (three save_and_apply calls — lock_timeout, display_off_timeout, suspend_timeout, lid_close_action; one self.subscribe; one setup_cleanup; one PowerProfilesHelper; one pkexec).

If the count is lower, a signal handler was dropped during the rewrite. Review which wiring is missing and restore it before moving on.

- [ ] **Step 4: Stage the file**

Run:
```bash
git add files/usr/lib/adwaita-lite/settings/pages/power_lock.py
```

---

## Task 3: Local-build smoke verification

This task uses Podman / Docker to build the image and inspect the Python files as they land — no running compositor needed, and no real test infra exists for the settings app.

**Files:**
- None modified. Verification only.

- [ ] **Step 1: Verify `PowerLockPage` is still importable by the registration module**

Run:
```bash
python3 -c "
import ast, pathlib
src = pathlib.Path('files/usr/lib/adwaita-lite/settings/pages/__init__.py').read_text()
ast.parse(src)
assert 'PowerLockPage' in src, 'registration import missing'
print('registration OK')
"
```

Expected: `registration OK`

- [ ] **Step 2: Verify that `BasePage.make_*` factories are still intact (wave 1–3 pages still depend on them)**

Run:
```bash
grep -cE 'def make_(page_box|group|setting_row|info_row|toggle_cards)' files/usr/lib/adwaita-lite/settings/base.py
```

Expected: `5`

If the number is less than 5, someone deleted a factory prematurely. Phase 4 is where that deletion lives, not Phase 0. Restore it from `git show HEAD:files/usr/lib/adwaita-lite/settings/base.py` before continuing.

- [ ] **Step 3: Verify power_lock no longer uses the deprecated factories**

Run:
```bash
grep -cE 'self\.(make_page_box|make_group|make_setting_row|make_info_row|make_toggle_cards)' files/usr/lib/adwaita-lite/settings/pages/power_lock.py
```

Expected: `0`

If the number is > 0, a factory-style call slipped through. Replace with the Adwaita row pattern before continuing.

- [ ] **Step 4: Verify no other page was accidentally modified**

Run:
```bash
git diff --name-only HEAD
```

Expected output contains exactly these two paths (in any order):
```
files/usr/lib/adwaita-lite/settings/pages/power_lock.py
files/usr/lib/adwaita-lite/settings/utils.py
```

`utils.py` is a new file; `git diff --name-only HEAD` lists it once it has been staged via `git add`. If anything else shows up, inspect and revert unless intentional.

---

## Task 4: Atomic Phase 0 commit

**Files:**
- None modified. Commit only.

- [ ] **Step 1: Confirm both files are staged**

Run:
```bash
git diff --cached --name-only
```

Expected output (two lines, any order):
```
files/usr/lib/adwaita-lite/settings/pages/power_lock.py
files/usr/lib/adwaita-lite/settings/utils.py
```

If anything else is staged, unstage it with `git reset HEAD <path>` before committing.

- [ ] **Step 2: Create the Phase 0 commit**

Run:
```bash
git commit -m "$(cat <<'EOF'
feat(settings): Adwaita migration Phase 0 — pilot power_lock + utils

Infrastructure-only commit that unlocks the wave 1/2/3 agents:

  - Extracts enable_escape_close to settings/utils.py as a standalone
    function. BasePage's method is untouched so every existing caller
    keeps working; future wave agents import the helper directly
    from settings.utils instead of threading through BasePage.
  - Converts power_lock as the pilot page. It now inherits from both
    BasePage (for the page protocol) and Adw.PreferencesPage (for
    the GNOME-native UI), builds groups via self.add(Adw.Preferences
    Group()), and uses AdwComboRow for every control - including the
    three timeout rows, which the spec originally suggested as
    AdwSpinRow. Rationale: our timeout settings are a discrete
    palette of named options (1 min, 5 min, Never), not a continuous
    minutes-picker, so ComboRow is the semantically correct row type
    and preserves the exact UX users have today.

No other pages are touched. BasePage.make_* widget factories stay in
place so waves 1-3 can run; they get deleted in Phase 4.

All D-Bus wiring, event-bus subscriptions, the pkexec lid-action
flow, and the setup_cleanup teardown are preserved exactly.

Spec: docs/superpowers/specs/2026-04-20-settings-adwaita-migration-design.md
Reference: docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: standard git commit success output with the two file changes.

- [ ] **Step 3: Push**

Run:
```bash
git push
```

Expected: push completes, new HEAD visible on `main`.

- [ ] **Step 4: Post-build visual verification on real hardware**

After the GitHub Actions build completes (≈ 4 min, as per recent history), update the target machine via `uupd` (or a VM via rpm-ostree rebase), log in, open Settings, and verify:

1. Sidebar shows the "Power & Lock" category in its expected position.
2. Clicking "Power & Lock" renders four groups: *Lock & Display*, *Power Profile*, *Suspend on Idle*, *Lid Close Behavior*.
3. Each group shows AdwComboRow controls (rows clickable anywhere, dropdown popover opens on tap).
4. Changing "Lock screen after" to a new value triggers the lock timeout (wait it out, or check `cat ~/.config/adwaita-lite/settings.json` to confirm the key was written).
5. Changing "Power profile" updates the value live; running `powerprofilesctl get` in a terminal matches the selected profile.
6. Changing "When lid is closed" prompts for pkexec authorization (polkit popup).
7. Navigating away and back does not leak or duplicate event-bus subscriptions — do it 3 times and the page should build once (watch `journalctl --user` for any PowerProfilesHelper errors).

If any of these fail, note which and roll back the commit (`git revert HEAD && git push`) before launching wave 1.

---

## Completion criteria

- `utils.py` exists and exposes `enable_escape_close`.
- `power_lock.py` inherits from both `BasePage` and `Adw.PreferencesPage`.
- All other pages are unchanged.
- Commit lands on main as a single atomic change.
- Hardware smoke test passes.

When all criteria are met, the pilot is ready to serve as a reference file for the wave 1 agents.
