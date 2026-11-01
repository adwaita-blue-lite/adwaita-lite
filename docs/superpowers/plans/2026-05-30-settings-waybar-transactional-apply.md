# Settings Waybar Transactional Apply Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Waybar-related Settings changes fire-and-forget from the GTK process while applying Waybar config/CSS transactionally in a detached worker.

**Architecture:** `SettingsStore` keeps tracked apply behavior for full/live applies, but `mode="waybar"` writes JSON and dispatches `/usr/libexec/adwaita-lite-apply-settings --mode waybar` detached with no wait thread or completion callback. The apply script renders Waybar config/CSS into staging content, validates generated config, commits files only after staging succeeds, logs failures to a user-cache log, then reloads Waybar through the existing reload helper boundary.

**Tech Stack:** Python 3.14, GTK/GLib via PyGObject, pytest, existing `adwaita-lite-apply-settings` script, Waybar config JSON/CSS generation.

---

## File Map

- Modify `files/usr/lib/adwaita-lite/settings/settings_store.py`: add a detached Waybar apply path and route `mode="waybar"` through it before `_apply_running` state is touched.
- Modify `files/usr/libexec/adwaita-lite-apply-settings`: add persistent logging helpers, split Waybar rendering from file writes, validate generated Waybar config, add transactional Waybar file commit, and update `--mode waybar` to use the transaction.
- Modify `tests/test_settings_store.py`: replace the existing Waybar-mode test with detached-dispatch assertions and add coverage that full applies remain tracked.
- Modify `tests/test_apply_settings.py`: add logging, validation, transaction ordering, rollback, and reload-boundary tests.
- Use existing design doc `docs/superpowers/specs/2026-05-30-settings-waybar-transactional-apply-design.md` as the source of requirements.

---

### Task 1: Detach Waybar Applies From SettingsStore

**Files:**
- Modify: `tests/test_settings_store.py`
- Modify: `files/usr/lib/adwaita-lite/settings/settings_store.py`

- [ ] **Step 1: Replace the existing Waybar-mode test with a failing detached-dispatch test**

In `tests/test_settings_store.py`, replace `test_save_and_apply_can_request_waybar_only_apply` with:

```python
def test_save_and_apply_waybar_dispatches_detached_without_tracking(monkeypatch, tmp_path):
    calls = []
    idle_calls = []

    class Proc:
        returncode = 0

        def communicate(self, timeout=None):
            raise AssertionError("detached waybar apply must not be waited on")

    monkeypatch.setattr(
        "settings.settings_store.subprocess.Popen",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or Proc(),
    )
    monkeypatch.setattr(
        "settings.settings_store.GLib.idle_add",
        lambda callback, *args: idle_calls.append((callback, args)) or 1,
    )

    store = _make_store(tmp_path)
    store.save_and_apply("layout", {"start": [], "center": [], "end": []}, mode="waybar")

    assert calls == [(
        ["/bin/true", "--mode", "waybar"],
        {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "start_new_session": True,
        },
    )]
    assert idle_calls == []
    assert store.has_apply_work() is False
    assert store._apply_running is False
    assert store._apply_pending is False
    assert store._apply_pending_mode is None
```

- [ ] **Step 2: Add the missing import required by the test**

At the top of `tests/test_settings_store.py`, ensure `subprocess` is imported:

```python
import subprocess
```

- [ ] **Step 3: Run the focused failing test**

Run: `pytest -q tests/test_settings_store.py::test_save_and_apply_waybar_dispatches_detached_without_tracking`

Expected: FAIL because current `SettingsStore._run_apply("waybar")` uses `stderr=subprocess.PIPE`, starts a wait thread, and sets `_apply_running`.

- [ ] **Step 4: Add detached Waybar dispatch implementation**

In `files/usr/lib/adwaita-lite/settings/settings_store.py`, update `_run_apply` so the first lines are:

```python
    def _run_apply(self, mode: str = "full") -> None:
        if mode not in self.APPLY_MODES:
            raise ValueError(f"unknown apply mode: {mode}")
        if mode == "waybar":
            self._run_waybar_apply_detached()
            return
        if self._apply_running:
            self._apply_pending = True
            self._apply_pending_mode = self._merge_apply_modes(
                self._apply_pending_mode, mode
            )
            return
```

Add this method immediately before `_run_apply`:

```python
    def _run_waybar_apply_detached(self) -> None:
        command = [self._apply_script, "--mode", "waybar"]
        try:
            subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            self._last_apply_spawn_failed = True
            if self._toast_callback:
                detail = str(exc) or exc.__class__.__name__
                self._toast_callback(
                    _("Saved, but failed to apply panel changes: {detail}").format(
                        detail=detail
                    ),
                    True,
                )
            return
        self._last_apply_spawn_failed = False
```

- [ ] **Step 5: Run the focused test again**

Run: `pytest -q tests/test_settings_store.py::test_save_and_apply_waybar_dispatches_detached_without_tracking`

Expected: PASS.

- [ ] **Step 6: Add a regression test that full applies still use the tracked path**

Add this test to `tests/test_settings_store.py` after the Waybar detached test:

```python
def test_full_apply_still_uses_tracked_wait_path(monkeypatch, tmp_path):
    calls = []
    idle_calls = []

    class Proc:
        returncode = 0

        def communicate(self, timeout=None):
            return b"", b""

    monkeypatch.setattr(
        "settings.settings_store.subprocess.Popen",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or Proc(),
    )
    monkeypatch.setattr(
        "settings.settings_store.GLib.idle_add",
        lambda callback, *args: idle_calls.append((callback, args)) or 1,
    )
    monkeypatch.setattr(
        "settings.settings_store.threading.Thread",
        lambda target, daemon=True: type(
            "ThreadStub",
            (),
            {"start": lambda self: target()},
        )(),
    )

    store = _make_store(tmp_path)
    store.save_and_apply("theme", "dark")

    assert calls == [(
        ["/bin/true"],
        {"stdout": subprocess.DEVNULL, "stderr": subprocess.PIPE},
    )]
    assert len(idle_calls) == 1
```

- [ ] **Step 7: Run SettingsStore tests**

Run: `pytest -q tests/test_settings_store.py`

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```bash
git add files/usr/lib/adwaita-lite/settings/settings_store.py tests/test_settings_store.py
git commit -m "fix(settings): detach waybar apply dispatch"
```

---

### Task 2: Add Persistent Apply Diagnostics

**Files:**
- Modify: `tests/test_apply_settings.py`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add failing tests for the diagnostics logger**

Add this test near the mode tests in `tests/test_apply_settings.py`:

```python
def test_apply_logger_writes_timestamped_user_cache_entry(monkeypatch, tmp_path):
    log_path = tmp_path / "apply-settings.log"
    monkeypatch.setattr(apply_settings, "APPLY_LOG_PATH", log_path)

    apply_settings._log_apply_event("waybar", "reload", "pkill returned 1")

    content = log_path.read_text(encoding="utf-8")
    assert "mode=waybar" in content
    assert "phase=reload" in content
    assert "pkill returned 1" in content
    assert content.endswith("\n")
```

Add this second test after it:

```python
def test_apply_logger_does_not_raise_when_cache_unwritable(monkeypatch, tmp_path):
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("blocks mkdir", encoding="utf-8")
    monkeypatch.setattr(apply_settings, "APPLY_LOG_PATH", blocked_parent / "apply-settings.log")

    apply_settings._log_apply_event("waybar", "render", "failed safely")
```

- [ ] **Step 2: Run the focused failing logger tests**

Run: `pytest -q tests/test_apply_settings.py::test_apply_logger_writes_timestamped_user_cache_entry tests/test_apply_settings.py::test_apply_logger_does_not_raise_when_cache_unwritable`

Expected: FAIL because `APPLY_LOG_PATH` and `_log_apply_event` are not defined.

- [ ] **Step 3: Add logging constants and helper**

In `files/usr/libexec/adwaita-lite-apply-settings`, add these constants after `SWAYLOCK_DIR`:

```python
CACHE_HOME = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
APPLY_LOG_PATH = CACHE_HOME / "adwaita-lite/apply-settings.log"
```

Add this helper after `_close_apply_lock`:

```python
def _log_apply_event(mode: str, phase: str, message: str) -> None:
    try:
        APPLY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        line = f"{timestamp} mode={mode} phase={phase} {message}\n"
        with APPLY_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass
```

- [ ] **Step 4: Run the logger tests again**

Run: `pytest -q tests/test_apply_settings.py::test_apply_logger_writes_timestamped_user_cache_entry tests/test_apply_settings.py::test_apply_logger_does_not_raise_when_cache_unwritable`

Expected: PASS.

- [ ] **Step 5: Run apply-settings tests**

Run: `pytest -q tests/test_apply_settings.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "fix(settings): log detached apply diagnostics"
```

---

### Task 3: Split Waybar Rendering From Live File Writes

**Files:**
- Modify: `tests/test_apply_settings.py`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add failing tests for render-only Waybar file generation**

Add these tests near the existing Waybar config generation tests in `tests/test_apply_settings.py`:

```python
def test_render_waybar_files_returns_valid_config_and_css():
    config_text, css_text = apply_settings._render_waybar_files(_make_tokens())

    config = json.loads(config_text)
    assert config["position"] == "bottom"
    assert "modules-left" in config
    assert "window#waybar" in css_text


def test_write_waybar_config_uses_rendered_files(monkeypatch, tmp_path):
    reload_calls = []
    monkeypatch.setattr(apply_settings, "WAYBAR_DIR", tmp_path)
    monkeypatch.setattr(
        apply_settings,
        "_render_waybar_files",
        lambda tokens: ('{"layer": "top"}\n', "window#waybar {}\n"),
    )

    assert apply_settings.write_waybar_config(_make_tokens()) is True
    assert json.loads((tmp_path / "config.jsonc").read_text(encoding="utf-8")) == {"layer": "top"}
    assert (tmp_path / "style.css").read_text(encoding="utf-8") == "window#waybar {}\n"
    assert reload_calls == []
```

- [ ] **Step 2: Run the focused failing render tests**

Run: `pytest -q tests/test_apply_settings.py::test_render_waybar_files_returns_valid_config_and_css tests/test_apply_settings.py::test_write_waybar_config_uses_rendered_files`

Expected: FAIL because `_render_waybar_files` is not defined.

- [ ] **Step 3: Refactor `write_waybar_config` into render and write phases**

In `files/usr/libexec/adwaita-lite-apply-settings`, create a new function immediately before `write_waybar_config`:

```python
def _render_waybar_files(tokens: dict) -> tuple[str, str]:
    layout = tokens["layout"]
    pinned = tokens.get("pinned", [])
    is_vertical = tokens["is_vertical"]
    icon_size = tokens["panel_icon_size"]
    spacing = tokens["panel_spacing"]

    modules_left = list(layout["start"])
    modules_center = list(layout["center"])
    modules_right = list(layout["end"])

    # Move the existing config construction code from write_waybar_config here,
    # starting at the current `layout = tokens["layout"]` block and ending at
    # `new_config = json.dumps(config, indent=2) + "\n"`.
    # Keep every existing module config assignment unchanged.

    css = _waybar_css_common(tokens)
    if is_vertical:
        css += _waybar_css_vertical(tokens)
    else:
        css += _waybar_css_horizontal(tokens)

    return new_config, css
```

Then replace the body of `write_waybar_config` with:

```python
def write_waybar_config(tokens: dict) -> bool:
    """Write waybar config and CSS. Returns True if either file changed."""
    WAYBAR_DIR.mkdir(parents=True, exist_ok=True)
    old_config = _read_if_exists(WAYBAR_DIR / "config.jsonc")
    old_css = _read_if_exists(WAYBAR_DIR / "style.css")

    new_config, css = _render_waybar_files(tokens)

    try:
        _atomic_write_text(WAYBAR_DIR / "config.jsonc", new_config)
    except OSError as exc:
        print(f"apply-settings: failed to write {WAYBAR_DIR / 'config.jsonc'}: {exc}",
              file=sys.stderr)
        sys.exit(1)

    try:
        _atomic_write_text(WAYBAR_DIR / "style.css", css)
    except OSError as exc:
        print(f"apply-settings: failed to write {WAYBAR_DIR / 'style.css'}: {exc}",
              file=sys.stderr)
        sys.exit(1)

    return new_config != old_config or css != old_css
```

Important mechanical detail: when moving the existing config construction block, remove the old write calls from the moved code so `_render_waybar_files` does not touch `WAYBAR_DIR`.

- [ ] **Step 4: Run the focused render tests again**

Run: `pytest -q tests/test_apply_settings.py::test_render_waybar_files_returns_valid_config_and_css tests/test_apply_settings.py::test_write_waybar_config_uses_rendered_files`

Expected: PASS.

- [ ] **Step 5: Run existing Waybar generation tests**

Run: `pytest -q tests/test_apply_settings.py`

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "refactor(settings): split waybar rendering from writes"
```

---

### Task 4: Add Transactional Waybar Apply Path

**Files:**
- Modify: `tests/test_apply_settings.py`
- Modify: `files/usr/libexec/adwaita-lite-apply-settings`

- [ ] **Step 1: Add a failing validation test**

Add this test to `tests/test_apply_settings.py` near the render tests:

```python
def test_validate_waybar_files_rejects_invalid_json():
    with pytest.raises(ValueError, match="generated waybar config is invalid JSON"):
        apply_settings._validate_waybar_files("{invalid", "window#waybar {}\n")
```

- [ ] **Step 2: Add a failing transaction ordering test**

Add this test after the validation test:

```python
def test_waybar_transaction_validates_before_replacing_live_files(monkeypatch, tmp_path):
    monkeypatch.setattr(apply_settings, "WAYBAR_DIR", tmp_path)
    monkeypatch.setattr(
        apply_settings,
        "_render_waybar_files",
        lambda tokens: ("{invalid", "window#waybar {}\n"),
    )
    reload_calls = []
    monkeypatch.setattr(apply_settings, "reload_waybar", lambda: reload_calls.append(True))

    (tmp_path / "config.jsonc").write_text('{"old": true}\n', encoding="utf-8")
    (tmp_path / "style.css").write_text("old-css\n", encoding="utf-8")

    with pytest.raises(ValueError, match="generated waybar config is invalid JSON"):
        apply_settings.apply_waybar_transaction(_make_tokens())

    assert (tmp_path / "config.jsonc").read_text(encoding="utf-8") == '{"old": true}\n'
    assert (tmp_path / "style.css").read_text(encoding="utf-8") == "old-css\n"
    assert reload_calls == []
```

- [ ] **Step 3: Add a failing successful transaction test**

Add this test after the ordering test:

```python
def test_waybar_transaction_commits_then_reloads(monkeypatch, tmp_path):
    monkeypatch.setattr(apply_settings, "WAYBAR_DIR", tmp_path)
    monkeypatch.setattr(
        apply_settings,
        "_render_waybar_files",
        lambda tokens: ('{"layer": "top"}\n', "window#waybar {}\n"),
    )
    reload_calls = []
    monkeypatch.setattr(apply_settings, "reload_waybar", lambda: reload_calls.append(True))

    assert apply_settings.apply_waybar_transaction(_make_tokens()) is True
    assert json.loads((tmp_path / "config.jsonc").read_text(encoding="utf-8")) == {"layer": "top"}
    assert (tmp_path / "style.css").read_text(encoding="utf-8") == "window#waybar {}\n"
    assert reload_calls == [True]
```

- [ ] **Step 4: Run the focused failing transaction tests**

Run: `pytest -q tests/test_apply_settings.py::test_validate_waybar_files_rejects_invalid_json tests/test_apply_settings.py::test_waybar_transaction_validates_before_replacing_live_files tests/test_apply_settings.py::test_waybar_transaction_commits_then_reloads`

Expected: FAIL because `_validate_waybar_files` and `apply_waybar_transaction` are not defined.

- [ ] **Step 5: Add validation and transactional write helpers**

In `files/usr/libexec/adwaita-lite-apply-settings`, add these functions after `_render_waybar_files`:

```python
def _validate_waybar_files(config_text: str, css_text: str) -> None:
    try:
        config = json.loads(config_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"generated waybar config is invalid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("generated waybar config must be a JSON object")
    if "window#waybar" not in css_text:
        raise ValueError("generated waybar CSS is missing window#waybar selector")


def _restore_text(path: Path, existed: bool, content: str) -> None:
    try:
        if existed:
            _atomic_write_text(path, content)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        _log_apply_event("waybar", "rollback", f"failed to restore {path}: {exc}")


def _write_waybar_files_transactionally(config_text: str, css_text: str) -> bool:
    WAYBAR_DIR.mkdir(parents=True, exist_ok=True)
    config_path = WAYBAR_DIR / "config.jsonc"
    css_path = WAYBAR_DIR / "style.css"
    old_config_exists = config_path.exists()
    old_css_exists = css_path.exists()
    old_config = _read_if_exists(config_path)
    old_css = _read_if_exists(css_path)

    if config_text == old_config and css_text == old_css:
        return False

    config_replaced = False
    css_replaced = False
    try:
        _atomic_write_text(config_path, config_text)
        config_replaced = True
        _atomic_write_text(css_path, css_text)
        css_replaced = True
    except OSError:
        if config_replaced:
            _restore_text(config_path, old_config_exists, old_config)
        if css_replaced:
            _restore_text(css_path, old_css_exists, old_css)
        raise
    return True


def apply_waybar_transaction(tokens: dict) -> bool:
    config_text, css_text = _render_waybar_files(tokens)
    _validate_waybar_files(config_text, css_text)
    changed = _write_waybar_files_transactionally(config_text, css_text)
    if changed:
        reload_waybar()
    return changed
```

- [ ] **Step 6: Run the focused transaction tests again**

Run: `pytest -q tests/test_apply_settings.py::test_validate_waybar_files_rejects_invalid_json tests/test_apply_settings.py::test_waybar_transaction_validates_before_replacing_live_files tests/test_apply_settings.py::test_waybar_transaction_commits_then_reloads`

Expected: PASS.

- [ ] **Step 7: Add a failing test that `--mode waybar` uses the transaction**

Replace `test_waybar_mode_only_writes_and_reloads_waybar` in `tests/test_apply_settings.py` with:

```python
def test_waybar_mode_uses_transactional_apply(monkeypatch):
    settings = _make_settings()
    tokens = _make_tokens()
    calls = []

    monkeypatch.setattr(apply_settings, "ensure_settings", lambda: settings)
    monkeypatch.setattr(apply_settings, "_build_tokens", lambda s: tokens)
    monkeypatch.setattr(
        apply_settings,
        "apply_waybar_transaction",
        lambda t: calls.append(("transaction", t)) or True,
    )
    monkeypatch.setattr(
        apply_settings,
        "write_waybar_config",
        lambda t: calls.append(("legacy", t)) or True,
    )

    assert apply_settings._main_locked("waybar") == 0
    assert calls == [("transaction", tokens)]
```

- [ ] **Step 8: Run the failing mode-routing test**

Run: `pytest -q tests/test_apply_settings.py::test_waybar_mode_uses_transactional_apply`

Expected: FAIL because `_main_locked("waybar")` still calls `write_waybar_config` directly.

- [ ] **Step 9: Route waybar mode through the transaction**

In `_main_locked`, replace the current Waybar branch with:

```python
    if mode == "waybar":
        try:
            apply_waybar_transaction(tokens)
        except Exception as exc:
            _log_apply_event("waybar", "transaction", str(exc))
            print(f"apply-settings: waybar transaction failed: {exc}", file=sys.stderr)
            return 1
        return 0
```

- [ ] **Step 10: Run the mode-routing test again**

Run: `pytest -q tests/test_apply_settings.py::test_waybar_mode_uses_transactional_apply`

Expected: PASS.

- [ ] **Step 11: Add failure logging test for transaction exceptions**

Add this test after the mode-routing test:

```python
def test_waybar_mode_logs_transaction_failure(monkeypatch, tmp_path):
    settings = _make_settings()
    tokens = _make_tokens()
    log_path = tmp_path / "apply-settings.log"

    monkeypatch.setattr(apply_settings, "APPLY_LOG_PATH", log_path)
    monkeypatch.setattr(apply_settings, "ensure_settings", lambda: settings)
    monkeypatch.setattr(apply_settings, "_build_tokens", lambda s: tokens)

    def fail_transaction(_tokens):
        raise ValueError("broken generated config")

    monkeypatch.setattr(apply_settings, "apply_waybar_transaction", fail_transaction)

    assert apply_settings._main_locked("waybar") == 1
    content = log_path.read_text(encoding="utf-8")
    assert "mode=waybar" in content
    assert "phase=transaction" in content
    assert "broken generated config" in content
```

- [ ] **Step 12: Run apply-settings tests**

Run: `pytest -q tests/test_apply_settings.py`

Expected: PASS.

- [ ] **Step 13: Commit Task 4**

Run:

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "fix(settings): apply waybar config transactionally"
```

---

### Task 5: Regression Sweep And Manual Verification Prep

**Files:**
- Modify: `tests/test_settings_app_logic.py` only if existing expectations need wording updates
- No production changes unless a test exposes a direct contradiction

- [ ] **Step 1: Run all Settings-related tests**

Run: `pytest -q tests/test_settings_store.py tests/test_settings_app_logic.py tests/test_apply_settings.py`

Expected: PASS.

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`

Expected: PASS with the known `PyGIDeprecationWarning` only.

- [ ] **Step 3: Check whitespace**

Run: `git diff --check`

Expected: no output.

- [ ] **Step 4: Inspect final diff**

Run: `git diff --stat && git diff -- files/usr/lib/adwaita-lite/settings/settings_store.py files/usr/libexec/adwaita-lite-apply-settings tests/test_settings_store.py tests/test_apply_settings.py docs/superpowers/specs/2026-05-30-settings-waybar-transactional-apply-design.md docs/superpowers/plans/2026-05-30-settings-waybar-transactional-apply.md`

Expected: only the SettingsStore detached path, apply-settings transaction/logging path, tests, spec, and plan are changed.

- [ ] **Step 5: Commit docs if they were not included in earlier commits**

If the spec and plan are still uncommitted, run:

```bash
git add docs/superpowers/specs/2026-05-30-settings-waybar-transactional-apply-design.md docs/superpowers/plans/2026-05-30-settings-waybar-transactional-apply.md
git commit -m "docs: plan transactional waybar applies"
```

- [ ] **Step 6: Manual verification checklist on affected desktop**

Run the installed Settings app and verify each action keeps Settings open:

```text
1. Change Appearance -> Accent color.
2. Change Panel -> Panel position.
3. Change Panel -> Panel density.
4. Change Panel -> Twilight.
5. Move a panel module between sections.
6. Reorder a panel module within a section.
7. Add a pinned app.
8. Remove a pinned app.
9. Inspect ~/.cache/adwaita-lite/apply-settings.log if any panel update fails.
```

Expected: Settings remains open for every action. Waybar updates live when reload succeeds. If a reload failure occurs, the setting remains saved and the log contains `mode=waybar` details.

---

## Plan Self-Review Notes

- Spec coverage: the plan covers detached Settings dispatch, transactional Waybar generation/commit, failure logging, reload helper boundary, tests, and manual verification.
- Placeholder scan: no incomplete placeholder markers or unspecified implementation placeholders are left in this plan.
- Type consistency: planned function names are `_run_waybar_apply_detached`, `_log_apply_event`, `_render_waybar_files`, `_validate_waybar_files`, `_write_waybar_files_transactionally`, `_restore_text`, and `apply_waybar_transaction`; tests use the same names.
