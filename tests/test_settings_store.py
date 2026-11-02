import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings.settings_store import SettingsStore


def _make_store(tmp_path, defaults=None, existing=None):
    defaults = defaults or {"theme": "light", "accent": "blue"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    settings_file = tmp_path / "settings.json"
    if existing is not None:
        settings_file.write_text(json.dumps(existing))
    return SettingsStore(
        settings_path=settings_file,
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )


def test_loads_defaults_when_no_file(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("theme") == "light"
    assert store.get("accent") == "blue"


def test_loads_existing_file(tmp_path):
    store = _make_store(tmp_path, existing={"theme": "dark", "accent": "red"})
    assert store.get("theme") == "dark"
    assert store.get("accent") == "red"


def test_get_with_default(tmp_path):
    store = _make_store(tmp_path)
    assert store.get("nonexistent", "fallback") == "fallback"


def test_save_and_apply_writes_json(tmp_path):
    store = _make_store(tmp_path)
    store.save_and_apply("theme", "dark")
    assert store.get("theme") == "dark"
    written = json.loads((tmp_path / "settings.json").read_text())
    assert written["theme"] == "dark"


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


def test_waybar_apply_reports_restart_session_message(monkeypatch, tmp_path):
    calls = []
    toasts = []

    class Proc:
        returncode = 0

        def communicate(self, timeout=None):
            raise AssertionError("detached waybar apply must not be waited on")

    monkeypatch.setattr(
        "settings.settings_store.subprocess.Popen",
        lambda cmd, **kwargs: calls.append((cmd, kwargs)) or Proc(),
    )

    store = _make_store(tmp_path)
    store.set_toast_callback(lambda message, is_error: toasts.append((message, is_error)))
    store.save_and_apply("layout", {"start": [], "center": [], "end": []}, mode="waybar")

    assert calls[0][0] == ["/bin/true", "--mode", "waybar"]
    assert toasts == [(
        "Panel changes saved. Restart your session to apply them.",
        False,
    )]


def test_waybar_apply_spawn_failure_reports_file_update_error(monkeypatch, tmp_path):
    toasts = []

    def fail_popen(_cmd, **_kwargs):
        raise OSError("boom")

    monkeypatch.setattr("settings.settings_store.subprocess.Popen", fail_popen)

    store = _make_store(tmp_path)
    store.set_toast_callback(lambda message, is_error: toasts.append((message, is_error)))
    store.save_and_apply("layout", {"start": [], "center": [], "end": []}, mode="waybar")

    assert toasts == [(
        "Panel changes saved, but panel files could not be updated: boom",
        True,
    )]
    assert store._last_apply_spawn_failed is True


def _write_session_snapshot(monkeypatch, tmp_path, data):
    runtime_dir = tmp_path / "runtime"
    snapshot = runtime_dir / "adwaita-lite/session-settings.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    return snapshot


def test_deferred_session_changes_detect_session_snapshot_difference(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom", "accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom", "accent": "blue"},
        existing={"edge": "top", "accent": "blue"},
    )

    assert store.has_deferred_session_changes() is True


def test_deferred_session_changes_hide_when_values_match_snapshot(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom", "accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom", "accent": "blue"},
        existing={"edge": "bottom", "accent": "blue"},
    )

    assert store.has_deferred_session_changes() is False


def test_deferred_session_changes_include_theme_font_high_contrast_scale(monkeypatch, tmp_path):
    _write_session_snapshot(
        monkeypatch,
        tmp_path,
        {
            "edge": "bottom",
            "accent": "blue",
            "theme": "light",
            "font_size": 11,
            "high_contrast": False,
            "scale": 1.0,
        },
    )
    store = _make_store(
        tmp_path,
        defaults={
            "edge": "bottom",
            "accent": "blue",
            "theme": "light",
            "font_size": 11,
            "high_contrast": False,
            "scale": 1.0,
        },
        existing={
            "edge": "bottom",
            "accent": "blue",
            "theme": "dark",
            "font_size": 15,
            "high_contrast": True,
            "scale": 1.25,
        },
    )

    assert store.has_deferred_session_changes() is True


def test_deferred_session_changes_ignore_missing_or_invalid_snapshot(monkeypatch, tmp_path):
    runtime_dir = tmp_path / "runtime"
    snapshot = runtime_dir / "adwaita-lite/session-settings.json"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_text("{invalid", encoding="utf-8")
    monkeypatch.delenv("ADWAITA_LITE_SESSION_SETTINGS", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_dir))
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom"},
        existing={"edge": "top"},
    )

    assert store.has_deferred_session_changes() is False

    snapshot.unlink()
    assert store.has_deferred_session_changes() is False


def test_deferred_session_changes_env_snapshot_does_not_fallback_to_runtime(monkeypatch, tmp_path):
    runtime_snapshot = _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom"})
    env_snapshot = runtime_snapshot.parent / "bad-session-settings.json"
    env_snapshot.write_text("{invalid", encoding="utf-8")
    monkeypatch.setenv("ADWAITA_LITE_SESSION_SETTINGS", str(env_snapshot))
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom"},
        existing={"edge": "top"},
    )

    assert store.has_deferred_session_changes() is False


def test_deferred_session_callback_runs_after_save_and_apply(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom"},
        existing={"edge": "bottom"},
    )
    states = []
    store.set_deferred_changes_callback(states.append)

    with patch.object(store, "_run_apply"):
        store.save_and_apply("edge", "top", mode="waybar")
        store.save_and_apply("edge", "bottom", mode="waybar")

    assert states == [True, False]


def test_deferred_session_callback_runs_after_save_dict_and_apply(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"edge": "bottom", "accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"edge": "bottom", "accent": "blue"},
        existing={"edge": "bottom", "accent": "blue"},
    )
    states = []
    store.set_deferred_changes_callback(states.append)

    with patch.object(store, "_run_apply"):
        store.save_dict_and_apply({"accent": "red"})

    assert states == [True]


def test_deferred_session_callback_runs_after_restore_keys_and_flush(monkeypatch, tmp_path):
    _write_session_snapshot(monkeypatch, tmp_path, {"accent": "blue"})
    store = _make_store(
        tmp_path,
        defaults={"accent": "blue"},
        existing={"accent": "red"},
    )
    states = []
    store.set_deferred_changes_callback(states.append)

    with patch.object(store, "_run_apply"):
        assert store.restore_keys(["accent"], {"accent": "blue"}) is True
    with patch("settings.settings_store.GLib.timeout_add", return_value=123), \
         patch("settings.settings_store.GLib.source_remove"), \
         patch.object(store, "_run_apply"):
        store.save_debounced("accent", "red")
        store.flush_and_detach()

    assert states == [False, True]


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


def test_pending_apply_uses_strongest_requested_mode(monkeypatch, tmp_path):
    commands = []

    class Proc:
        returncode = 0

        def communicate(self, timeout=None):
            return b"", b""

    store = _make_store(tmp_path)
    store._apply_running = True

    store._run_apply("waybar")
    store._run_apply("full")

    monkeypatch.setattr(
        "settings.settings_store.subprocess.Popen",
        lambda cmd, **kwargs: commands.append(cmd) or Proc(),
    )

    store._on_apply_done(0, b"")

    assert commands == [["/bin/true"]]


def test_save_dict_and_apply(tmp_path):
    store = _make_store(tmp_path)
    store.save_dict_and_apply({"theme": "dark", "accent": "red"})
    assert store.get("theme") == "dark"
    assert store.get("accent") == "red"


def test_atomic_write_creates_file(tmp_path):
    store = _make_store(tmp_path)
    store.save_and_apply("theme", "dark")
    assert (tmp_path / "settings.json").exists()
    assert not (tmp_path / "settings.json.tmp").exists()


def test_flush_and_detach_writes_latest_pending_debounce(tmp_path):
    store = _make_store(tmp_path)

    with patch("settings.settings_store.GLib.timeout_add", return_value=123), \
         patch("settings.settings_store.GLib.source_remove") as source_remove, \
         patch.object(store, "_run_apply") as run_apply:
        store.save_debounced("theme", "dark")
        store.save_debounced("theme", "blue")

        store.flush_and_detach()

    assert store.get("theme") == "blue"
    written = json.loads((tmp_path / "settings.json").read_text())
    assert written["theme"] == "blue"
    assert source_remove.call_count == 2
    run_apply.assert_called_once_with()


def test_flush_and_detach_keeps_apply_queued_for_flushed_debounce(tmp_path):
    store = _make_store(tmp_path)
    store._apply_running = True

    with patch("settings.settings_store.GLib.timeout_add", return_value=123), \
         patch("settings.settings_store.GLib.source_remove"):
        store.save_debounced("accent", "red")

        store.flush_and_detach()

    assert store.get("accent") == "red"
    assert store._apply_pending is True


def test_flush_and_detach_preserves_existing_queued_apply(tmp_path):
    store = _make_store(tmp_path)
    store._apply_running = True
    store._apply_pending = True

    store.flush_and_detach()

    assert store._apply_pending is True
    assert store.has_apply_work() is True


def test_load_with_unusable_config_parent_falls_back_to_defaults(tmp_path):
    defaults = {"theme": "light"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    bad_parent = tmp_path / "not-a-directory"
    bad_parent.write_text("blocking directory creation")

    store = SettingsStore(
        settings_path=bad_parent / "settings.json",
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )

    assert store.get("theme") == "light"


def test_corrupted_file_resets_to_defaults(tmp_path):
    defaults = {"theme": "light"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{invalid json")
    store = SettingsStore(
        settings_path=settings_file,
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )
    assert store.get("theme") == "light"
    assert (tmp_path / "settings.json.invalid").read_text() == "{invalid json"
    assert json.loads(settings_file.read_text()) == defaults


def test_non_object_file_resets_to_defaults(tmp_path):
    defaults = {"theme": "light"}
    defaults_file = tmp_path / "defaults.json"
    defaults_file.write_text(json.dumps(defaults))
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("[]")
    store = SettingsStore(
        settings_path=settings_file,
        defaults_path=defaults_file,
        apply_script="/bin/true",
    )
    assert store.get("theme") == "light"
    assert json.loads((tmp_path / "settings.json.invalid").read_text()) == []
    assert json.loads(settings_file.read_text()) == defaults


def test_restore_keys_can_defer_apply_and_remove_dynamic_keys(tmp_path):
    store = _make_store(
        tmp_path,
        defaults={"theme": "light"},
        existing={"theme": "dark", "resolution_eDP-1": "1024x768@60Hz"},
    )

    with patch.object(store, "_run_apply") as run_apply:
        ok = store.restore_keys(
            ["theme"],
            {"theme": "light"},
            remove_predicate=lambda key: key.startswith("resolution_"),
            apply_now=False,
        )

    assert ok is True
    assert store.get("theme") == "light"
    assert store.get("resolution_eDP-1") is None
    assert json.loads((tmp_path / "settings.json").read_text()) == {"theme": "light"}
    run_apply.assert_not_called()


def test_restore_keys_write_failure_does_not_mutate_memory(tmp_path):
    store = _make_store(tmp_path, existing={"theme": "dark"})

    with patch.object(store, "_write_data", return_value=False):
        ok = store.restore_keys(["theme"], {"theme": "light"})

    assert ok is False
    assert store.get("theme") == "dark"


def test_invalid_known_value_type_falls_back_but_unknown_keys_survive(tmp_path):
    defaults = {"font_size": 11, "theme": "light"}
    store = _make_store(
        tmp_path,
        defaults=defaults,
        existing={"font_size": "large", "theme": "dark", "resolution_eDP-1": "1024x768@60Hz"},
    )
    assert store.get("font_size") == 11
    assert store.get("theme") == "dark"
    assert store.get("resolution_eDP-1") == "1024x768@60Hz"


def test_missing_defaults_file_returns_empty(tmp_path):
    """App must not crash when the defaults file is absent."""
    missing_defaults = tmp_path / "nonexistent_defaults.json"
    settings_file = tmp_path / "settings.json"
    store = SettingsStore(
        settings_path=settings_file,
        defaults_path=missing_defaults,
        apply_script="/bin/true",
    )
    assert store.get("anything", "fallback") == "fallback"


def test_corrupted_file_with_missing_defaults_returns_empty(tmp_path):
    """Corrupt user file + missing defaults must not crash."""
    missing_defaults = tmp_path / "nonexistent_defaults.json"
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{invalid json")
    store = SettingsStore(
        settings_path=settings_file,
        defaults_path=missing_defaults,
        apply_script="/bin/true",
    )
    assert store.get("anything", "fallback") == "fallback"
