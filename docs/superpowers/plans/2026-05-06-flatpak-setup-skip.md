# First-Boot Flatpak Setup Skip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a visible, durable `Skip app setup` path to first-boot Flatpak installation while keeping complete-before-login as the default.

**Architecture:** Use `/var/lib/adwaita-lite/flatpak-setup.skip` as an explicit opt-out marker distinct from `/var/lib/adwaita-lite/flatpak-setup.done`. The greeter writes the marker after user confirmation and treats it as non-blocking; the install service and setup script both honor it so the automatic initial install is not retried after skip.

**Tech Stack:** Python 3, GTK4/PyGObject greeter, systemd unit conditions, Bash Flatpak setup script, pytest contract tests.

---

## File Structure

- Modify `files/usr/bin/adwaita-lite-greeter`
  - Add `FLATPAK_SKIP_PATH` beside the existing Flatpak state constants.
  - Add `Skip app setup` button to the setup overlay.
  - Add confirmation prompt using GTK4 `Gtk.AlertDialog` when available, with a non-dialog fallback for testability and older GTK behavior.
  - Add marker-writing helper that creates `/var/lib/adwaita-lite` and only reveals login after the marker is written.
  - Treat the skip marker as a non-blocking state in setup polling.
- Modify `files/usr/libexec/adwaita-lite-flatpak-setup`
  - Add `SKIP_STAMP=/var/lib/adwaita-lite/flatpak-setup.skip`.
  - Exit early if the skip marker exists before doing network or Flatpak work.
- Modify `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`
  - Add `ConditionPathExists=!/var/lib/adwaita-lite/flatpak-setup.skip`.
- Modify `tests/test_flatpak_setup_contract.py`
  - Extend existing Flatpak setup contract coverage for service and script skip behavior.
- Create `tests/test_flatpak_greeter_skip.py`
  - Add focused static and method-level tests for greeter skip state, skip copy, and skip failure behavior.

---

### Task 1: Contract Tests for Skip Marker Plumbing

**Files:**
- Modify: `tests/test_flatpak_setup_contract.py`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Add service path constant and failing contract tests**

Replace `tests/test_flatpak_setup_contract.py` with:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLATPAK_SETUP = ROOT / "files/usr/libexec/adwaita-lite-flatpak-setup"
FLATPAK_INSTALL_SERVICE = (
    ROOT / "files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service"
)
SKIP_MARKER = "/var/lib/adwaita-lite/flatpak-setup.skip"


def test_initial_install_completion_checks_apps_and_runtimes():
    script = FLATPAK_SETUP.read_text()

    assert "flatpak list --system --columns=application" in script
    assert "flatpak list --system --app --columns=application" not in script


def test_flatpak_install_service_is_gated_by_skip_marker():
    service = FLATPAK_INSTALL_SERVICE.read_text()

    assert f"ConditionPathExists=!{SKIP_MARKER}" in service


def test_flatpak_setup_script_honors_skip_marker_before_network_work():
    script = FLATPAK_SETUP.read_text()

    skip_definition = f"SKIP_STAMP={SKIP_MARKER}"
    skip_check = 'if [ -f "$SKIP_STAMP" ]; then'

    assert skip_definition in script
    assert skip_check in script
    assert script.index(skip_check) < script.index("if [ -f \"$STAMP\" ]; then")
```

- [ ] **Step 2: Run the tests and verify they fail for the expected reason**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py
```

Expected: the two new tests fail because the service does not yet contain `ConditionPathExists=!/var/lib/adwaita-lite/flatpak-setup.skip` and the script does not yet define or check `SKIP_STAMP`.

- [ ] **Step 3: Commit the failing contract tests**

Run:

```bash
git add tests/test_flatpak_setup_contract.py
git commit -m "test(flatpak): define first-boot skip contract"
```

---

### Task 2: Service and Script Skip Enforcement

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-flatpak-setup:19-27`
- Modify: `files/usr/libexec/adwaita-lite-flatpak-setup:56-59`
- Modify: `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service:11-16`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Add the skip marker constant to the setup script**

In `files/usr/libexec/adwaita-lite-flatpak-setup`, change the constants block to:

```bash
APPS_FILE=/var/lib/adwaita-lite/flatpak-apps
STAMP=/var/lib/adwaita-lite/flatpak-setup.done
SKIP_STAMP=/var/lib/adwaita-lite/flatpak-setup.skip
PROGRESS_DIR=/run/adwaita-lite
PROGRESS_FILE=$PROGRESS_DIR/flatpak-progress
LOGIN_READY_FILE=$PROGRESS_DIR/flatpak-login-ready
MAX_NET_WAIT=120
RETRIES=3
RETRY_DELAY=15
```

- [ ] **Step 2: Add the defensive early exit before update/install modes**

Insert this block immediately before the `# Mode 2: update existing Flatpaks` comment:

```bash
if [ -f "$SKIP_STAMP" ]; then
    echo "Flatpak setup was skipped by the user; not running automatic setup."
    exit 0
fi

```

- [ ] **Step 3: Gate the install service on the skip marker**

In `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`, update the condition block to:

```ini
ConditionPathExists=/var/lib/adwaita-lite/setup-done
ConditionPathExists=!/var/lib/adwaita-lite/flatpak-setup.done
ConditionPathExists=!/var/lib/adwaita-lite/flatpak-setup.skip
```

- [ ] **Step 4: Run focused verification**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py
bash -n files/usr/libexec/adwaita-lite-flatpak-setup
```

Expected: all `tests/test_flatpak_setup_contract.py` tests pass and `bash -n` exits with no output.

- [ ] **Step 5: Commit service and script enforcement**

Run:

```bash
git add files/usr/libexec/adwaita-lite-flatpak-setup \
        files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service
git commit -m "fix(flatpak): honor first-boot setup skip marker"
```

---

### Task 3: Greeter Skip Tests

**Files:**
- Create: `tests/test_flatpak_greeter_skip.py`
- Test: `tests/test_flatpak_greeter_skip.py`

- [ ] **Step 1: Create failing greeter tests**

Create `tests/test_flatpak_greeter_skip.py` with:

```python
import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GREETER = ROOT / "files/usr/bin/adwaita-lite-greeter"
SKIP_MARKER = "/var/lib/adwaita-lite/flatpak-setup.skip"


def _load_greeter_module():
    loader = importlib.machinery.SourceFileLoader("adwaita_lite_greeter", str(GREETER))
    spec = importlib.util.spec_from_loader(
        "adwaita_lite_greeter", loader, origin=str(GREETER)
    )
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(GREETER)
    spec.loader.exec_module(module)
    return module


class _FakeSpinner:
    def __init__(self):
        self.stopped = False

    def stop(self):
        self.stopped = True


class _FakeStack:
    def __init__(self):
        self.visible_child = None

    def set_visible_child_name(self, name):
        self.visible_child = name


class _FakeLabel:
    def __init__(self):
        self.text = ""

    def set_text(self, text):
        self.text = text



def test_greeter_defines_skip_marker_path():
    module = _load_greeter_module()

    assert str(module.FLATPAK_SKIP_PATH) == SKIP_MARKER


def test_greeter_setup_in_progress_treats_skip_marker_as_non_blocking(monkeypatch):
    module = _load_greeter_module()
    window = module.GreeterWindow.__new__(module.GreeterWindow)

    monkeypatch.setattr(module.SETUP_DONE_PATH, "exists", lambda: True)
    monkeypatch.setattr(module.FLATPAK_DONE_PATH, "exists", lambda: False)
    monkeypatch.setattr(module.FLATPAK_LOGIN_READY_PATH, "exists", lambda: False)
    monkeypatch.setattr(module.FLATPAK_SKIP_PATH, "exists", lambda: True)

    assert module.GreeterWindow._is_setup_in_progress(window) is False


def test_greeter_poll_reveals_login_when_skip_marker_exists(monkeypatch):
    module = _load_greeter_module()
    window = module.GreeterWindow.__new__(module.GreeterWindow)
    window._setup_spinner = _FakeSpinner()
    window._stack = _FakeStack()
    window._setup_elapsed_s = 0

    monkeypatch.setattr(module.FLATPAK_DONE_PATH, "exists", lambda: False)
    monkeypatch.setattr(module.FLATPAK_LOGIN_READY_PATH, "exists", lambda: False)
    monkeypatch.setattr(module.FLATPAK_SKIP_PATH, "exists", lambda: True)

    result = module.GreeterWindow._poll_setup_progress(window)

    assert result == module.GLib.SOURCE_REMOVE
    assert window._setup_spinner.stopped is True
    assert window._stack.visible_child == "login"


def test_greeter_skip_confirmation_copy_mentions_flatpak_not_bazaar():
    source = GREETER.read_text()

    assert "Selected apps will not be installed automatically" in source
    assert "flatpak from the terminal" in source
    assert "Bazaar" not in source[source.index("Selected apps will not be installed automatically") - 200:]


def test_apply_flatpak_skip_writes_marker_and_reveals_login(tmp_path, monkeypatch):
    module = _load_greeter_module()
    marker = tmp_path / "var/lib/adwaita-lite/flatpak-setup.skip"
    window = module.GreeterWindow.__new__(module.GreeterWindow)
    window._setup_spinner = _FakeSpinner()
    window._stack = _FakeStack()
    window._setup_progress_label = _FakeLabel()

    monkeypatch.setattr(module, "FLATPAK_SKIP_PATH", marker)


    module.GreeterWindow._apply_flatpak_setup_skip(window)

    assert marker.exists()
    assert window._setup_spinner.stopped is True
    assert window._stack.visible_child == "login"
    assert window._setup_progress_label.text == ""


def test_apply_flatpak_skip_failure_keeps_overlay_visible(tmp_path, monkeypatch):
    module = _load_greeter_module()
    marker_dir = tmp_path / "not-a-directory"
    marker_dir.write_text("blocks mkdir")
    marker = marker_dir / "flatpak-setup.skip"
    window = module.GreeterWindow.__new__(module.GreeterWindow)
    window._setup_spinner = _FakeSpinner()
    window._stack = _FakeStack()
    window._setup_progress_label = _FakeLabel()

    monkeypatch.setattr(module, "FLATPAK_SKIP_PATH", marker)

    module.GreeterWindow._apply_flatpak_setup_skip(window)

    assert window._setup_spinner.stopped is False
    assert window._stack.visible_child is None
    assert "Could not skip app setup" in window._setup_progress_label.text
```

- [ ] **Step 2: Run the greeter tests and verify they fail for the expected reason**

Run:

```bash
pytest -q tests/test_flatpak_greeter_skip.py
```

Expected: failures for missing `FLATPAK_SKIP_PATH`, missing `_apply_flatpak_setup_skip`, missing skip copy, and existing setup state not checking the skip marker.

- [ ] **Step 3: Commit the failing greeter tests**

Run:

```bash
git add tests/test_flatpak_greeter_skip.py
git commit -m "test(greeter): define Flatpak setup skip behavior"
```

---

### Task 4: Greeter Skip UI and State Handling

**Files:**
- Modify: `files/usr/bin/adwaita-lite-greeter:41-53`
- Modify: `files/usr/bin/adwaita-lite-greeter:608-614`
- Modify: `files/usr/bin/adwaita-lite-greeter:654-688`
- Test: `tests/test_flatpak_greeter_skip.py`

- [ ] **Step 1: Add the skip path constant**

In `files/usr/bin/adwaita-lite-greeter`, update the Flatpak state constants to:

```python
SETUP_DONE_PATH = Path("/var/lib/adwaita-lite/setup-done")
FLATPAK_DONE_PATH = Path("/var/lib/adwaita-lite/flatpak-setup.done")
FLATPAK_SKIP_PATH = Path("/var/lib/adwaita-lite/flatpak-setup.skip")
FLATPAK_PROGRESS_PATH = Path("/run/adwaita-lite/flatpak-progress")
FLATPAK_LOGIN_READY_PATH = Path("/run/adwaita-lite/flatpak-login-ready")
```

- [ ] **Step 2: Add the skip button to the setup overlay**

Immediately after `setup_card.append(self._setup_progress_label)`, insert:

```python
        self._setup_skip_btn = Gtk.Button(label=_("Skip app setup"))
        self._setup_skip_btn.add_css_class("switch-user")
        self._setup_skip_btn.set_halign(Gtk.Align.CENTER)
        self._setup_skip_btn.set_margin_top(16)
        self._setup_skip_btn.connect("clicked", lambda _: self._confirm_flatpak_setup_skip())
        setup_card.append(self._setup_skip_btn)
```

- [ ] **Step 3: Treat the skip marker as non-blocking**

Replace `_is_setup_in_progress()` with:

```python
    def _is_setup_in_progress(self) -> bool:
        """True while first-boot Flatpak setup is actively gating login."""
        return (
            SETUP_DONE_PATH.exists()
            and not FLATPAK_DONE_PATH.exists()
            and not FLATPAK_SKIP_PATH.exists()
            and not FLATPAK_LOGIN_READY_PATH.exists()
        )
```

- [ ] **Step 4: Add skip-aware poll completion**

In `_poll_setup_progress()`, replace the first condition with:

```python
        if (
            FLATPAK_DONE_PATH.exists()
            or FLATPAK_SKIP_PATH.exists()
            or FLATPAK_LOGIN_READY_PATH.exists()
        ):
            self._setup_spinner.stop()
            self._stack.set_visible_child_name("login")
            return GLib.SOURCE_REMOVE
```

- [ ] **Step 5: Add confirmation and marker-writing helpers**

Insert these methods after `_poll_setup_progress()`:

```python
    def _confirm_flatpak_setup_skip(self) -> None:
        message = _("Skip app setup?")
        detail = _(
            "Selected apps will not be installed automatically. "
            "You can install them later with flatpak from the terminal."
        )
        try:
            alert = Gtk.AlertDialog()
            alert.set_modal(True)
            alert.set_message(message)
            alert.set_detail(detail)
            alert.set_buttons([_("Cancel"), _("Skip app setup")])
            alert.set_cancel_button(0)
            alert.set_default_button(0)
            alert.choose(self, None, self._on_flatpak_skip_confirmed)
        except (AttributeError, TypeError, RuntimeError):
            self._setup_progress_label.set_text(detail)

    def _on_flatpak_skip_confirmed(self, dialog, result) -> None:
        try:
            choice = dialog.choose_finish(result)
        except (AttributeError, TypeError, RuntimeError):
            return
        if choice == 1:
            self._apply_flatpak_setup_skip()

    def _apply_flatpak_setup_skip(self) -> None:
        try:
            FLATPAK_SKIP_PATH.parent.mkdir(parents=True, exist_ok=True)
            FLATPAK_SKIP_PATH.touch(mode=0o644, exist_ok=True)
        except OSError as exc:
            self._setup_progress_label.set_text(
                _("Could not skip app setup: {error}").format(error=exc)
            )
            return
        self._setup_progress_label.set_text("")
        self._setup_spinner.stop()
        self._stack.set_visible_child_name("login")
```

- [ ] **Step 6: Run focused greeter tests**

Run:

```bash
pytest -q tests/test_flatpak_greeter_skip.py
python -m py_compile files/usr/bin/adwaita-lite-greeter
```

Expected: all greeter skip tests pass and `py_compile` exits with no output.

- [ ] **Step 7: Commit greeter skip UI**

Run:

```bash
git add files/usr/bin/adwaita-lite-greeter tests/test_flatpak_greeter_skip.py
git commit -m "feat(greeter): allow skipping first-boot app setup"
```

---

### Task 5: Final Verification

**Files:**
- Test: `tests/test_flatpak_setup_contract.py`
- Test: `tests/test_flatpak_greeter_skip.py`
- Verify: `files/usr/libexec/adwaita-lite-flatpak-setup`
- Verify: `files/usr/bin/adwaita-lite-greeter`
- Verify: `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`

- [ ] **Step 1: Run Flatpak and greeter skip tests**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py tests/test_flatpak_greeter_skip.py
```

Expected: all tests pass.

- [ ] **Step 2: Run syntax checks**

Run:

```bash
bash -n files/usr/libexec/adwaita-lite-flatpak-setup
python -m py_compile files/usr/bin/adwaita-lite-greeter
```

Expected: both commands exit with no output.

- [ ] **Step 3: Verify the systemd unit syntax**

Run:

```bash
systemd-analyze verify files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service
```

Expected: exit code 0. If it reports `/usr/libexec/adwaita-lite-flatpak-setup` missing on the development host, record that limitation and rely on the unit-file contract test plus image-build placement through `build_files/build.sh`.

- [ ] **Step 4: Run related existing tests**

Run:

```bash
pytest -q tests/test_iso_install_contract.py tests/test_translation_catalogs.py
```

Expected: all tests pass. Translation tests matter because the new greeter strings are wrapped in `_()` and share the settings text domain.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff -- files/usr/bin/adwaita-lite-greeter \
          files/usr/libexec/adwaita-lite-flatpak-setup \
          files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service \
          tests/test_flatpak_setup_contract.py \
          tests/test_flatpak_greeter_skip.py
```

Expected: only the skip-flow files from this plan are modified. Pre-existing unrelated staged docs may still appear in `git status`; do not include them unless the user explicitly requests it.

- [ ] **Step 6: Commit any final verification-only adjustments**

If Task 5 required no file changes, do not create a commit. If Task 5 required a small fix, commit only the files touched by that fix:

```bash
git add files/usr/bin/adwaita-lite-greeter \
        files/usr/libexec/adwaita-lite-flatpak-setup \
        files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service \
        tests/test_flatpak_setup_contract.py \
        tests/test_flatpak_greeter_skip.py
git commit -m "fix(flatpak): complete setup skip verification"
```

---

## Self-Review Notes

- Spec coverage: Tasks 1-4 cover the service condition, script defensive check, greeter skip marker, non-blocking setup state, confirmation copy, failure behavior, and tests. Task 5 covers final verification.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: The plan uses one path constant name, `FLATPAK_SKIP_PATH`, in tests and implementation; the Bash script uses `SKIP_STAMP`; the durable marker path is consistently `/var/lib/adwaita-lite/flatpak-setup.skip`.
