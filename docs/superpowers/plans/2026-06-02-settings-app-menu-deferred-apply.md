# Settings App Menu Deferred Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the start menu use a session-start settings snapshot so deferred panel settings do not affect the menu until the next session.

**Architecture:** `adwaita-lite-session` creates a runtime-only snapshot of `settings.json` after the pre-labwc config apply and exports its path. `adwaita-lite-app-menu` resolves settings from that snapshot first, falling back to live `settings.json` outside a normal Adwaita-Lite session or if the snapshot is unreadable.

**Tech Stack:** Bash session launcher, Python 3 app-menu script, GTK4/libadwaita, pytest.

---

## File Structure

- Modify `files/usr/bin/adwaita-lite-app-menu`: add a small settings path resolver and route `_load_settings()` through it. This file remains responsible for rendering and positioning the GTK start menu.
- Modify `files/usr/libexec/adwaita-lite-session`: create `${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json` after `adwaita-lite-apply-settings --mode=config` and export `ADWAITA_LITE_SESSION_SETTINGS` before `exec labwc`.
- Modify `tests/test_app_menu_css.py`: add focused tests for app-menu settings source precedence.
- Modify `tests/test_apply_settings.py`: add a session wrapper contract test for snapshot creation/export ordering.

---

### Task 1: Start Menu Reads Session Snapshot First

**Files:**
- Modify: `files/usr/bin/adwaita-lite-app-menu`
- Test: `tests/test_app_menu_css.py`

- [ ] **Step 1: Write the failing tests**

Add these tests after `test_start_menu_defines_user_accent_tokens_from_settings` in `tests/test_app_menu_css.py`:

```python
def test_load_settings_prefers_exported_session_snapshot(monkeypatch, tmp_path):
    live_settings = tmp_path / "settings.json"
    live_settings.write_text(json.dumps({"edge": "bottom"}), encoding="utf-8")
    session_settings = tmp_path / "session-settings.json"
    session_settings.write_text(json.dumps({"edge": "top"}), encoding="utf-8")

    monkeypatch.setattr(app_menu, "SETTINGS_PATH", live_settings)
    monkeypatch.setenv("ADWAITA_LITE_SESSION_SETTINGS", str(session_settings))

    assert app_menu._load_settings()["edge"] == "top"


def test_load_settings_uses_runtime_session_snapshot_before_live_file(monkeypatch, tmp_path):
    live_settings = tmp_path / "settings.json"
    live_settings.write_text(json.dumps({"edge": "bottom"}), encoding="utf-8")
    runtime_dir = tmp_path / "runtime"
    session_settings = runtime_dir / "adwaita-lite/session-settings.json"
    session_settings.parent.mkdir(parents=True)
    session_settings.write_text(json.dumps({"edge": "left"}), encoding="utf-8")

    monkeypatch.setattr(app_menu, "SETTINGS_PATH", live_settings)
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))

    assert app_menu._load_settings()["edge"] == "left"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
pytest -q tests/test_app_menu_css.py::test_load_settings_prefers_exported_session_snapshot tests/test_app_menu_css.py::test_load_settings_uses_runtime_session_snapshot_before_live_file
```

Expected: both tests fail because `_load_settings()` only reads `SETTINGS_PATH`.

- [ ] **Step 3: Implement the settings source resolver**

In `files/usr/bin/adwaita-lite-app-menu`, replace the single-path `_load_settings()` implementation with this resolver. Keep `SETTINGS_PATH` unchanged.

```python
SESSION_SETTINGS_ENV = "ADWAITA_LITE_SESSION_SETTINGS"
SESSION_SETTINGS_NAME = "session-settings.json"


def _runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")


def _settings_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    session_settings = os.environ.get(SESSION_SETTINGS_ENV)
    if session_settings:
        candidates.append(Path(session_settings))
    candidates.append(_runtime_dir() / "adwaita-lite" / SESSION_SETTINGS_NAME)
    candidates.append(SETTINGS_PATH)
    return tuple(candidates)


def _load_settings() -> dict:
    for path in _settings_candidates():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return {}
```

Update the existing PID lock runtime directory line to use the same `_runtime_dir()` helper:

```python
_XDG_RUNTIME_DIR = str(_runtime_dir())
PID_LOCK_PATH = Path(_XDG_RUNTIME_DIR) / "adwaita-lite-app-menu.pid"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
pytest -q tests/test_app_menu_css.py::test_load_settings_prefers_exported_session_snapshot tests/test_app_menu_css.py::test_load_settings_uses_runtime_session_snapshot_before_live_file
```

Expected: both tests pass.

- [ ] **Step 5: Run existing app-menu tests**

Run:

```bash
pytest -q tests/test_app_menu_css.py
```

Expected: all tests in `tests/test_app_menu_css.py` pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add files/usr/bin/adwaita-lite-app-menu tests/test_app_menu_css.py
git commit -m "fix(app-menu): read session settings snapshot"
```

---

### Task 2: Session Wrapper Creates and Exports Snapshot

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-session`
- Test: `tests/test_apply_settings.py`

- [ ] **Step 1: Write the failing session contract test**

Add this test after `test_session_startup_uses_config_then_autostart_uses_live_mode` in `tests/test_apply_settings.py`:

```python
def test_session_exports_app_menu_settings_snapshot_after_config_apply():
    root = Path(__file__).resolve().parents[1]
    session = (root / "files/usr/libexec/adwaita-lite-session").read_text(
        encoding="utf-8"
    )

    config_idx = session.index("adwaita-lite-apply-settings --mode=config")
    snapshot_path_idx = session.index(
        '_session_settings="${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json"'
    )
    copy_idx = session.index('cp "$_settings_file" "$_session_settings"')
    export_idx = session.index("export ADWAITA_LITE_SESSION_SETTINGS")
    exec_idx = session.index("exec labwc")

    assert config_idx < snapshot_path_idx < copy_idx < export_idx < exec_idx
    assert '_settings_file="${XDG_CONFIG_HOME:-$HOME/.config}/adwaita-lite/settings.json"' in session
    assert 'mkdir -p "$_session_settings_dir"' in session
    assert 'ADWAITA_LITE_SESSION_SETTINGS="$_session_settings"' in session
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_session_exports_app_menu_settings_snapshot_after_config_apply
```

Expected: FAIL with a missing substring error because the session wrapper does not create or export a snapshot yet.

- [ ] **Step 3: Implement snapshot creation in the session wrapper**

In `files/usr/libexec/adwaita-lite-session`, insert this block after the existing `adwaita-lite-apply-settings --mode=config` command and before `exec labwc`:

```bash
# Snapshot the session-start settings for runtime consumers that must
# not observe deferred Settings changes until the next login.
_settings_file="${XDG_CONFIG_HOME:-$HOME/.config}/adwaita-lite/settings.json"
_session_settings="${XDG_RUNTIME_DIR:-/run/user/$UID}/adwaita-lite/session-settings.json"
_session_settings_dir="$(dirname "$_session_settings")"
if mkdir -p "$_session_settings_dir" && [ -f "$_settings_file" ]; then
    cp "$_settings_file" "$_session_settings" || \
        echo "adwaita-lite-session: failed to snapshot settings; continuing to labwc" >&2
else
    echo "adwaita-lite-session: settings snapshot unavailable; continuing to labwc" >&2
fi
export ADWAITA_LITE_SESSION_SETTINGS="$_session_settings"
```

- [ ] **Step 4: Run the session contract test**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_session_exports_app_menu_settings_snapshot_after_config_apply
```

Expected: PASS.

- [ ] **Step 5: Run nearby session/apply contract tests**

Run:

```bash
pytest -q tests/test_apply_settings.py::test_session_startup_uses_config_then_autostart_uses_live_mode tests/test_apply_settings.py::test_session_exports_app_menu_settings_snapshot_after_config_apply tests/test_apply_settings.py::test_session_renderer_policy_is_conditional_not_global_gl tests/test_apply_settings.py::test_session_makes_libadwaita_use_gsettings_for_color_scheme
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

Run:

```bash
git add files/usr/libexec/adwaita-lite-session tests/test_apply_settings.py
git commit -m "fix(session): snapshot app menu settings"
```

---

### Task 3: Final Verification

**Files:**
- Verify: `files/usr/bin/adwaita-lite-app-menu`
- Verify: `files/usr/libexec/adwaita-lite-session`
- Verify: `tests/test_app_menu_css.py`
- Verify: `tests/test_apply_settings.py`

- [ ] **Step 1: Run focused regression tests**

Run:

```bash
pytest -q tests/test_app_menu_css.py::test_load_settings_prefers_exported_session_snapshot tests/test_app_menu_css.py::test_load_settings_uses_runtime_session_snapshot_before_live_file tests/test_apply_settings.py::test_session_exports_app_menu_settings_snapshot_after_config_apply
```

Expected: all focused regression tests pass.

- [ ] **Step 2: Run affected test files**

Run:

```bash
pytest -q tests/test_app_menu_css.py tests/test_apply_settings.py
```

Expected: both affected test files pass.

- [ ] **Step 3: Run the full test suite**

Run:

```bash
pytest -q
```

Expected: full suite passes. The existing `PyGIDeprecationWarning` is acceptable if it remains the only warning.

- [ ] **Step 4: Check whitespace and final status**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` prints no output. `git status --short` is clean after commits.

- [ ] **Step 5: Manual desktop verification**

In a Adwaita-Lite session, change Panel position or layout in Settings. Without restarting the session, open the start menu from the launcher and the keyboard shortcut. Expected: the menu keeps using the old session position/layout and is not broken. Restart the session and open the menu again. Expected: the menu uses the new position/layout.
