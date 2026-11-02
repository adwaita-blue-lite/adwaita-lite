import json
import os
import subprocess
import threading
import time
from gettext import gettext as _
from pathlib import Path

from gi.repository import GLib


SESSION_SETTINGS_ENV = "ADWAITA_LITE_SESSION_SETTINGS"
SESSION_SETTINGS_NAME = "session-settings.json"
DEFERRED_SESSION_KEYS = frozenset({
    # These settings are carried into the live session via the snapshot
    # and consumed by the panel and app menu. Changing any of them needs
    # a session restart for the shell surfaces to match Settings, even
    # when GTK apps update immediately.
    "edge",
    "layout",
    "density",
    "pinned",
    "panel_twilight",
    "accent",
    "theme",
    "high_contrast",
    "font_size",
    "scale",
})


class SettingsStore:
    """JSON settings persistence with atomic writes, debounce, and apply feedback."""

    APPLY_TIMEOUT_SEC = 30
    APPLY_MODES = {"config", "live", "full", "waybar"}

    def __init__(self, settings_path=None, defaults_path=None, apply_script=None):
        self._path = Path(
            settings_path
            or Path.home() / ".config/adwaita-lite/settings.json"
        )
        self._defaults_path = Path(
            defaults_path
            or "/usr/share/adwaita-lite/defaults/settings.json"
        )
        self._apply_script = str(
            apply_script or "/usr/libexec/adwaita-lite-apply-settings"
        )
        self._debounce_timers: dict[str, int] = {}
        self._debounce_pending: dict[str, object] = {}
        self._toast_callback = None
        self._deferred_changes_callback = None
        self._data = self._load()
        self._apply_running = False
        self._apply_pending = False
        self._apply_pending_mode: str | None = None
        self._apply_wait_source: int | None = None
        self._last_apply_spawn_failed: bool = False

    def _load(self) -> dict:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Keep the app alive even if ~/.config/adwaita-lite is a
            # file, read-only, or temporarily mis-owned. Later writes
            # will surface an error toast once the window exists.
            return self._load_defaults(write_to_user=False)
        if not self._path.exists():
            return self._load_defaults(write_to_user=True)
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._load_invalid_defaults()
        except OSError:
            return self._load_defaults(write_to_user=False)
        if not isinstance(data, dict):
            return self._load_invalid_defaults()
        return self._sanitize_loaded_data(data)

    def _invalid_backup_path(self) -> Path:
        base = self._path.with_name(self._path.name + ".invalid")
        if not base.exists():
            return base
        for idx in range(1, 100):
            candidate = self._path.with_name(f"{self._path.name}.invalid.{idx}")
            if not candidate.exists():
                return candidate
        stamp = int(time.time())
        idx = 0
        while True:
            suffix = f"{stamp}" if idx == 0 else f"{stamp}.{idx}"
            candidate = self._path.with_name(f"{self._path.name}.invalid.{suffix}")
            if not candidate.exists():
                return candidate
            idx += 1

    def _load_invalid_defaults(self) -> dict:
        """Preserve an invalid settings file before recreating defaults.

        Invalid JSON or a non-object top-level value used to be replaced
        in-place by factory defaults, which made a truncated or hand-edited
        file unrecoverable. Move it aside first; if that fails, use defaults
        only in memory rather than overwriting the original.
        """
        try:
            self._path.replace(self._invalid_backup_path())
        except OSError:
            return self._load_defaults(write_to_user=False)
        return self._load_defaults(write_to_user=True)

    def _load_defaults(self, write_to_user: bool = False) -> dict:
        try:
            default_text = self._defaults_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            data = json.loads(default_text)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        if write_to_user:
            try:
                tmp = self._path.with_suffix(".tmp")
                tmp.write_text(default_text, encoding="utf-8")
                os.replace(tmp, self._path)
            except OSError:
                pass
        return data

    def _sanitize_loaded_data(self, data: dict) -> dict:
        """Replace invalid known-key value types with factory defaults.

        The apply-settings reconciler validates ranges and closed sets,
        but the GTK pages read directly from SettingsStore before the
        next apply. A hand-edited settings.json with e.g.
        ``{"font_size": "large"}`` should not crash Accessibility or
        Appearance before the user has a chance to repair it.
        """
        defaults = self._load_defaults()
        if not defaults:
            return data

        cleaned = dict(data)
        for key, default in defaults.items():
            if key not in cleaned or not self._compatible_type(cleaned[key], default):
                cleaned[key] = default
        return cleaned

    @staticmethod
    def _compatible_type(value, default) -> bool:
        if isinstance(default, bool):
            return isinstance(value, bool)
        if isinstance(default, int) and not isinstance(default, bool):
            return isinstance(value, int) and not isinstance(value, bool)
        if isinstance(default, float):
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if isinstance(default, str):
            return isinstance(value, str)
        if isinstance(default, list):
            return isinstance(value, list)
        if isinstance(default, dict):
            return isinstance(value, dict)
        return isinstance(value, type(default))

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def get_defaults(self) -> dict:
        """Load and return the factory defaults from the image."""
        return self._load_defaults()

    def restore_keys(
        self,
        keys: list[str],
        defaults: dict,
        *,
        remove_predicate=None,
        apply_now: bool = True,
    ) -> bool:
        """Overwrite specified keys with defaults, then optionally apply."""
        next_data = dict(self._data)
        if remove_predicate is not None:
            for key in [k for k in next_data if remove_predicate(k)]:
                next_data.pop(key, None)
        for key in keys:
            if key in defaults:
                next_data[key] = defaults[key]
            else:
                next_data.pop(key, None)
        if not self._write_data(next_data):
            return False  # disk error; _write_data toasted the reason
        self._data = next_data
        self._notify_deferred_changes_changed()
        if apply_now:
            self._run_apply()
        return True

    def remove_keys_matching(self, predicate) -> None:
        """Drop every key for which *predicate* returns True. No apply side-effect.

        Intended for Restore Defaults to clear runtime-discovered keys
        (e.g. per-output ``resolution_*`` entries) that aren't listed in
        CATEGORY_KEYS. The caller triggers apply via restore_keys.
        """
        for key in [k for k in self._data if predicate(k)]:
            self._data.pop(key, None)

    def save_and_apply(self, key: str, value, *, mode: str = "full") -> None:
        self._data[key] = value
        if not self._write():
            return  # disk error; _write toasted the reason
        self._notify_deferred_changes_changed()
        self._run_apply(mode)

    def save_dict_and_apply(self, updates: dict) -> None:
        self._data.update(updates)
        if not self._write():
            return
        self._notify_deferred_changes_changed()
        self._run_apply()

    def apply(self) -> None:
        """Trigger apply-settings without modifying stored values.

        Used when a page writes to an out-of-band file (e.g. user
        keybindings JSON) and needs the reconciler to re-read it.

        On completion, fires the toast callback ("Settings applied" or an
        error message) exactly as save_and_apply() would.
        """
        self._run_apply()

    def save_debounced(self, key: str, value, delay_ms: int = 300) -> None:
        if key in self._debounce_timers:
            GLib.source_remove(self._debounce_timers[key])
        self._debounce_pending[key] = value

        def _apply():
            self._debounce_timers.pop(key, None)
            value_to_apply = self._debounce_pending.pop(key, value)
            self.save_and_apply(key, value_to_apply)
            return GLib.SOURCE_REMOVE

        self._debounce_timers[key] = GLib.timeout_add(delay_ms, _apply)

    def set_toast_callback(self, callback) -> None:
        self._toast_callback = callback

    def show_toast(self, message: str, is_error: bool = False) -> None:
        if self._toast_callback is not None:
            self._toast_callback(message, is_error)

    def set_deferred_changes_callback(self, callback) -> None:
        self._deferred_changes_callback = callback

    def _runtime_dir(self) -> Path:
        return Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")

    def _session_settings_candidates(self) -> tuple[Path, ...]:
        session_settings = os.environ.get(SESSION_SETTINGS_ENV)
        if session_settings:
            return (Path(session_settings),)
        return (self._runtime_dir() / "adwaita-lite" / SESSION_SETTINGS_NAME,)

    def _load_session_settings_snapshot(self) -> dict | None:
        for path in self._session_settings_candidates():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
        return None

    def has_deferred_session_changes(self) -> bool:
        snapshot = self._load_session_settings_snapshot()
        if snapshot is None:
            return False
        for key in DEFERRED_SESSION_KEYS:
            if self._data.get(key) != snapshot.get(key):
                return True
        return False

    def _notify_deferred_changes_changed(self) -> None:
        if self._deferred_changes_callback is not None:
            self._deferred_changes_callback(self.has_deferred_session_changes())

    def flush_and_detach(self) -> None:
        """Cancel pending debounces and detach the toast callback.

        Called from SettingsWindow.close-request. Without this, a user
        who changes a setting and closes the window within ~300 ms
        leaves a debounce timer scheduled; when it fires it runs
        save_and_apply, which spawns apply-settings, which completes
        on a background thread and calls self._toast_callback(...) ->
        self._show_toast on a freed Adw.ToastOverlay. Also detaches
        the callback so a pending apply from the old window doesn't
        toast on a new window's overlay after reopen.
        """
        pending_debounces = dict(self._debounce_pending)
        for source_id in self._debounce_timers.values():
            GLib.source_remove(source_id)
        self._debounce_timers.clear()
        self._debounce_pending.clear()

        flushed_debounces = False
        if pending_debounces:
            self._data.update(pending_debounces)
            if self._write():
                flushed_debounces = True
                self._notify_deferred_changes_changed()
                if self._apply_running:
                    self._apply_pending = True
                    self._apply_pending_mode = self._merge_apply_modes(
                        self._apply_pending_mode, "full"
                    )
                else:
                    self._apply_pending = False
                    self._apply_pending_mode = None
                    self._run_apply()

        if self._apply_wait_source is not None:
            GLib.source_remove(self._apply_wait_source)
            self._apply_wait_source = None
        self._toast_callback = None

    def has_apply_work(self) -> bool:
        """Return True while an apply is running or queued."""
        return self._apply_running or self._apply_pending

    def _write_data(self, data: dict) -> bool:
        """Persist *data* atomically. Returns True on success.

        Failures (ENOSPC on a 2 GB Chromebook, read-only bind mount on
        ~/.config, wrong ownership after a chown) previously propagated
        out of save_and_apply as unhandled exceptions through GTK signal
        handlers — the user's click flipped back with no toast. Now the
        error is caught, toasted, and the caller is informed so it can
        skip the doomed apply run.

        Uses fsync before rename so an abrupt power loss can't leave a
        truncated settings.json that would be replaced with defaults on
        next boot — losing every previously-saved preference.
        """
        tmp = self._path.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
            return True
        except OSError as exc:
            if self._toast_callback is not None:
                self._toast_callback(
                    _("Could not save settings: {reason}").format(reason=exc.strerror or str(exc)),
                    True,
                )
            # Clean up the tmp file if it exists; ignore secondary failure.
            try:
                tmp.unlink()
            except OSError:
                pass
            return False

    def _write(self) -> bool:
        """Persist self._data atomically. Returns True on success."""
        return self._write_data(self._data)

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
                    _(
                        "Panel changes saved, but panel files could not be updated: {detail}"
                    ).format(detail=detail),
                    True,
                )
            return
        self._last_apply_spawn_failed = False
        if self._toast_callback:
            self._toast_callback(
                _("Panel changes saved. Restart your session to apply them."),
                False,
            )

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
        self._apply_running = True
        command = [self._apply_script]
        if mode != "full":
            command.extend(["--mode", mode])

        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            # Any OS-level failure to launch the apply script would
            # otherwise leave _apply_running stuck True, silently
            # disabling every future save-and-apply for the session.
            # ENOMEM on 2 GB hardware, a transient bootc overlay swap
            # making the script briefly unreadable, or a permission
            # glitch during a rebase all hit this path. Also reset
            # _apply_pending so the retry-loop in _on_apply_done doesn't
            # attempt to re-enter this same broken state immediately.
            self._apply_running = False
            self._apply_pending = False
            self._apply_pending_mode = None
            # Record the spawn failure so wait_for_apply's restart
            # callback can choose to skip rather than os.execv against
            # a system whose on-disk configs don't reflect the new
            # settings.json (since apply-settings never ran). Cleared
            # on the next successful spawn.
            self._last_apply_spawn_failed = True
            if self._toast_callback:
                detail = str(exc) or exc.__class__.__name__
                self._toast_callback(
                    _("Failed to apply settings: {detail}").format(detail=detail),
                    True,
                )
            return
        self._last_apply_spawn_failed = False

        def _wait():
            try:
                _, stderr = proc.communicate(timeout=self.APPLY_TIMEOUT_SEC)
                rc = proc.returncode
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    _, stderr = proc.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    stderr = b""
                rc = -1  # sentinel for timeout
            GLib.idle_add(self._on_apply_done, rc, stderr)

        threading.Thread(target=_wait, daemon=True).start()

    @staticmethod
    def _merge_apply_modes(current: str | None, incoming: str) -> str:
        if current is None or current == incoming:
            return incoming
        return "full"

    def _on_apply_done(self, returncode: int, stderr_bytes: bytes) -> bool:
        self._apply_running = False
        if self._toast_callback is not None:
            if returncode == 0:
                self._toast_callback(_("Settings applied"), False)
            elif returncode == -1:
                msg = _("Apply timed out after {n}s").format(n=self.APPLY_TIMEOUT_SEC)
                self._toast_callback(msg, True)
            else:
                err = stderr_bytes.decode("utf-8", errors="replace").strip()
                if err:
                    msg = _("Failed to apply: {err}").format(err=err[:80])
                else:
                    msg = _("Failed to apply settings")
                self._toast_callback(msg, True)
        if self._apply_pending:
            mode = self._apply_pending_mode or "full"
            self._apply_pending = False
            self._apply_pending_mode = None
            self._run_apply(mode)
        return GLib.SOURCE_REMOVE

    def wait_for_apply(self, callback) -> None:
        """Call callback once the current apply-settings finishes.
        If no apply is running, calls immediately via idle_add.

        The poll source ID is tracked on the store so flush_and_detach
        can cancel it when the window closes; previously, a user
        clicking Restart from About and then closing the window while
        the apply was still running would leave a 50 ms poll firing
        until the 30 s APPLY_TIMEOUT_SEC expired (or the apply
        finished), at which point the callback would invoke _do_restart
        on a dead window.
        """
        if not self._apply_running:
            GLib.idle_add(callback)
            return

        def _poll():
            if self._apply_running:
                return GLib.SOURCE_CONTINUE
            self._apply_wait_source = None
            callback()
            return GLib.SOURCE_REMOVE
        self._apply_wait_source = GLib.timeout_add(50, _poll)
