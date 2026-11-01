# Wizard Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the installer wizard against current GTK/PyGObject API drift and release-risk runtime traps without a large startup refactor.

**Architecture:** Keep the wizard as a single script for this release, but add focused helpers for alert display and accessibility announcements. Add static GTK compatibility tests plus small method-level tests for GLib source lifecycle and install-state recovery. Defer lazy page construction until after these concrete risks are fixed and VM smoke testing has evidence that startup still blocks.

**Tech Stack:** Python 3, PyGObject GTK 4, GLib, pytest, AST-based compatibility tests.

---

## File Structure

- Modify `files/usr/bin/adwaita-lite-setup-wizard`: fix GLib source ID lifecycle, install preflight state handling, current GTK alert API, and current accessibility announcement API.
- Modify `tests/test_setup_wizard_app_selection.py`: extend AST-based GTK compatibility checks for deprecated/missing GTK APIs.
- Modify `tests/test_installer_mount_handling.py`: add focused method tests for `_enable_rescan()` and `_on_setup_clicked()` hash-failure recovery.
- Create `tests/test_setup_wizard_gtk_smoke.py`: best-effort real-GTK startup smoke test that skips when no GTK display/runtime is available and never runs destructive install steps.

---

### Task 1: Static GTK Compatibility Tests

**Files:**
- Modify: `tests/test_setup_wizard_app_selection.py`
- Test: `tests/test_setup_wizard_app_selection.py`

- [ ] **Step 1: Add failing tests for deprecated/missing GTK patterns**

Append these tests after `test_password_entries_avoid_missing_activates_default_api`:

```python

def test_wizard_avoids_removed_accessibility_live_region_api():
    source = WIZARD.read_text()

    assert "Gtk.AccessibleProperty.LIVE" not in source
    assert "Gtk.AccessibleLive" not in source
    assert ".announce(" in source


def test_wizard_uses_current_alert_dialog_api():
    source = WIZARD.read_text()

    assert "Gtk.MessageDialog" not in source
    assert "Gtk.AlertDialog" in source
```

- [ ] **Step 2: Run tests to verify they fail for the expected reason**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py::test_wizard_avoids_removed_accessibility_live_region_api tests/test_setup_wizard_app_selection.py::test_wizard_uses_current_alert_dialog_api
```

Expected: both tests fail because the wizard still contains `Gtk.AccessibleProperty.LIVE`, `Gtk.AccessibleLive`, and `Gtk.MessageDialog`, and does not yet call `.announce()`.

- [ ] **Step 3: Do not implement yet**

Leave these tests red. Task 3 will make them pass with the accessibility and alert changes.

---

### Task 2: GLib Source Lifecycle and Install-State Recovery Tests

**Files:**
- Modify: `tests/test_installer_mount_handling.py`
- Test: `tests/test_installer_mount_handling.py`

- [ ] **Step 1: Add test helpers**

Append these helpers near the existing helper code in `tests/test_installer_mount_handling.py`:

```python

class _FakeButton:
    def __init__(self, active=True, text=""):
        self.active = active
        self.text = text
        self.sensitive = None

    def get_active(self):
        return self.active

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text

    def set_sensitive(self, sensitive):
        self.sensitive = sensitive


class _FakeDropdown:
    def __init__(self, selected=0):
        self.selected = selected

    def get_selected(self):
        return self.selected
```

- [ ] **Step 2: Add failing test for rescan timeout cleanup**

Append this test:

```python

def test_enable_rescan_clears_completed_source_id():
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._rescan_timer_id = 123
    window._rescan_button = _FakeButton()

    result = setup_wizard.SetupWizardWindow._enable_rescan(window)

    assert result == setup_wizard.GLib.SOURCE_REMOVE
    assert window._rescan_timer_id == 0
    assert window._rescan_button.sensitive is True
```

- [ ] **Step 3: Add failing test for install hash failure recovery**

Append this test:

```python

def test_setup_hash_failure_does_not_leave_installing_stuck(monkeypatch):
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._installing = False
    window._drive_dropdown = _FakeDropdown(0)
    window._drives = [{"name": "/dev/vda"}]
    window._fs_dropdown = _FakeDropdown(0)
    window._swap_strategy_dropdown = _FakeDropdown(0)
    window._password_entry = _FakeButton(text="secret")
    window._root_password_entry = _FakeButton(text="")
    window._fullname_entry = _FakeButton(text="Jane Doe")
    window._username_entry = _FakeButton(text="jane")
    window._hostname_entry = _FakeButton(text="adwaita-lite")
    window._admin_check = _FakeButton(active=True)
    statuses = []
    window._set_status = lambda message, error=True: statuses.append((message, error))

    def fail_hash(_password):
        raise OSError("openssl missing")

    monkeypatch.setattr(setup_wizard, "_hash_password", fail_hash)

    setup_wizard.SetupWizardWindow._on_setup_clicked(window)

    assert getattr(window, "_installing", False) is False
    assert statuses
    assert "Failed to hash password" in statuses[-1][0]
```

- [ ] **Step 4: Run tests to verify they fail for the expected reason**

Run:

```bash
pytest -q tests/test_installer_mount_handling.py::test_enable_rescan_clears_completed_source_id tests/test_installer_mount_handling.py::test_setup_hash_failure_does_not_leave_installing_stuck
```

Expected: first test fails because `_rescan_timer_id` remains `123`; second test fails because `_installing` remains `True` after hash failure.

---

### Task 3: Implement Source Lifecycle, Install Recovery, Alerts, and Announcements

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:966-983`
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2172-2174`
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2447-2454`
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:2846-2852`
- Modify: `files/usr/bin/adwaita-lite-setup-wizard:4127-4161`
- Test: `tests/test_setup_wizard_app_selection.py`, `tests/test_installer_mount_handling.py`

- [ ] **Step 1: Replace the close warning dialog path**

Replace `_on_close_request()` lines 966-985 with:

```python
    def _show_install_in_progress_alert(self) -> None:
        alert = Gtk.AlertDialog()
        alert.set_modal(True)
        alert.set_message(_("Install in progress"))
        alert.set_detail(_(
            "An install is running. Wait for it to finish "
            "before closing this window."))
        alert.show(self)

    def _on_close_request(self, _window) -> bool:
        # Block close during an active install so the user can't orphan
        # a half-written target disk with a stray Esc or window-manager
        # close keybinding.
        if getattr(self, "_installing", False) and self._current_page == PAGE_PROGRESS:
            self._show_install_in_progress_alert()
            return True
        self._cleanup_mounts()
        return False
```

- [ ] **Step 2: Clear one-shot rescan source ID**

Replace `_enable_rescan()` with:

```python
    def _enable_rescan(self) -> bool:
        self._rescan_timer_id = 0
        self._rescan_button.set_sensitive(True)
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 3: Replace inert live-region helper with current announce helper**

Replace `_mark_live_assertive()` with these two helpers:

```python
    def _mark_live_assertive(self, _widget) -> None:
        """Compatibility shim; status announcements happen in _announce_status."""
        return

    def _announce_status(self, message: str) -> None:
        """Ask assistive tech to announce visible status text when supported."""
        if not message:
            return
        try:
            priority = Gtk.AccessibleAnnouncementPriority.MEDIUM
            self._status_label.announce(message, priority)
        except (AttributeError, TypeError, RuntimeError):
            pass
```

- [ ] **Step 4: Announce status updates from the central status path**

Replace `_set_status()` with:

```python
    def _set_status(self, message: str, error: bool = True) -> None:
        self._status_label.set_text(message)
        self._status_label.remove_css_class("status-error")
        self._status_label.remove_css_class("status-success")
        if message:
            self._status_label.add_css_class("status-error" if error else "status-success")
            self._announce_status(message)
```

- [ ] **Step 5: Make password-hash failure leave install retryable**

In `_on_setup_clicked()`, remove this line near the top:

```python
        self._installing = True
```

Then insert this line after the password entries are cleared and before the system/app/language values are captured:

```python
        self._installing = True
```

The resulting section must look like this:

```python
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            self._set_status(_("Failed to hash password: {err}").format(err=exc))
            self._installing = False
            return
        finally:
            root_pw = ""
            del root_pw
        self._password_entry.set_text("")
        self._root_password_entry.set_text("")
        self._installing = True

        # System page
```

- [ ] **Step 6: Run targeted tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py::test_wizard_avoids_removed_accessibility_live_region_api tests/test_setup_wizard_app_selection.py::test_wizard_uses_current_alert_dialog_api tests/test_installer_mount_handling.py::test_enable_rescan_clears_completed_source_id tests/test_installer_mount_handling.py::test_setup_hash_failure_does_not_leave_installing_stuck
```

Expected: all four tests pass.

- [ ] **Step 7: Commit task changes**

Run:

```bash
git add files/usr/bin/adwaita-lite-setup-wizard tests/test_setup_wizard_app_selection.py tests/test_installer_mount_handling.py
git commit -m "fix(wizard): harden GTK startup helpers"
```

---

### Task 4: Add Best-Effort Real GTK Startup Smoke Test

**Files:**
- Create: `tests/test_setup_wizard_gtk_smoke.py`
- Test: `tests/test_setup_wizard_gtk_smoke.py`

- [ ] **Step 1: Add smoke test file**

Create `tests/test_setup_wizard_gtk_smoke.py` with:

```python
import importlib.machinery
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-setup-wizard"


def _load_wizard_module():
    loader = importlib.machinery.SourceFileLoader("setup_wizard_smoke", str(SCRIPT))
    spec = importlib.util.spec_from_loader("setup_wizard_smoke", loader, origin=str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SCRIPT)
    spec.loader.exec_module(module)
    return module


def test_setup_wizard_window_constructs_with_real_gtk(monkeypatch):
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    try:
        if hasattr(Gtk, "init_check") and not Gtk.init_check():
            pytest.skip("GTK could not initialize a display for smoke testing")
    except RuntimeError as exc:
        pytest.skip(f"GTK display unavailable: {exc}")

    module = _load_wizard_module()
    monkeypatch.setattr(module, "_load_timezones", lambda: ["America/New_York"])
    monkeypatch.setattr(module, "_load_keyboard_layouts", lambda: [("us", "English (US)")])
    monkeypatch.setattr(module, "_load_drives", lambda: [{
        "name": "/dev/vda",
        "size": str(64 * 1024**3),
        "model": "Test Disk",
        "tran": "virtio",
    }])

    def fake_run(cmd, *args, **kwargs):
        class Result:
            returncode = 0
            stdout = "America/New_York\n"
            stderr = ""
        return Result()

    app = Gtk.Application(application_id="org.adwaitabluelite.SetupWizard.Test")
    app.register(None)

    with patch.object(module.subprocess, "run", side_effect=fake_run), \
         patch.object(module.NM.Client, "new_async", lambda *args, **kwargs: None):
        window = module.SetupWizardWindow(app)

    assert window is not None
    window.destroy()
```

- [ ] **Step 2: Run smoke test**

Run:

```bash
pytest -q tests/test_setup_wizard_gtk_smoke.py
```

Expected: PASS when a GTK display is available, or SKIP with a clear display/runtime reason. It must not fail because of wizard construction, deprecated dialog use, inaccessible APIs, or page-builder crashes.

- [ ] **Step 3: Commit smoke test**

Run:

```bash
git add tests/test_setup_wizard_gtk_smoke.py
git commit -m "test(wizard): smoke test GTK construction"
```

---

### Task 5: Final Verification and Release Notes

**Files:**
- No planned file modifications.
- Test: full suite

- [ ] **Step 1: Run wizard-specific tests**

Run:

```bash
pytest -q tests/test_setup_wizard_app_selection.py tests/test_installer_mount_handling.py tests/test_wizard_i18n.py tests/test_setup_wizard_gtk_smoke.py
```

Expected: all non-skipped tests pass; smoke test may skip only for unavailable GTK display/runtime.

- [ ] **Step 2: Run syntax check**

Run:

```bash
python -m py_compile files/usr/bin/adwaita-lite-setup-wizard
```

Expected: exit code 0, no output.

- [ ] **Step 3: Run full suite**

Run:

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended wizard/test files are modified; untracked `scribbles/` remains untouched.

- [ ] **Step 5: Confirm no verification-only edits are pending**

Run:

```bash
git status --short
```

Expected: no new tracked-file modifications from Task 5. Do not create an empty commit.

---

## Manual VM Verification After Push/Rebuild

- Boot the rebuilt raw image in the VM.
- Confirm labwc starts and the wizard window appears automatically.
- Navigate through language, account, system, apps, and confirm pages.
- Verify `/tmp/wizard-crash.log` has no traceback. Non-fatal portal warnings are acceptable.
- If the wizard still shows a blank screen, capture `cat /tmp/wizard-crash.log`, `journalctl -b -u greetd --no-pager`, and `ps -ef | grep -E 'greetd|labwc|setup-wizard|cage' | grep -v grep` before changing code again.

---

## Self-Review Notes

- Spec coverage: all six findings from `docs/superpowers/specs/2026-05-05-wizard-release-hardening-design.md` map to Tasks 1-5.
- Placeholder scan: no placeholder markers remain; each implementation step names exact files, code, and verification commands.
- Type consistency: helper names in tests and implementation match existing `SetupWizardWindow` methods and existing module-level names.
