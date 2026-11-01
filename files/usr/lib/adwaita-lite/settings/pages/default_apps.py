import os
import shlex
import shutil
import subprocess
import threading
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from ..base import BasePage

APP_MIME_TYPES = [
    (_("Web Browser"), (
        "x-scheme-handler/http",
        "x-scheme-handler/https",
        "text/html",
    )),
    (_("File Manager"), ("inode/directory",)),
    (_("Terminal"), None),
    (_("Text Editor"), ("text/plain",)),
    (_("Image Viewer"), (
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/svg+xml",
    )),
    (_("PDF Viewer"), ("application/pdf",)),
    (_("Media Player"), (
        "video/x-matroska",
        "video/mp4",
        "audio/mpeg",
        "audio/ogg",
    )),
    (_("Email Client"), ("x-scheme-handler/mailto",)),
]


class DefaultAppsPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)

    @property
    def search_keywords(self):
        return [(_("Default Applications"), label) for label, _mime in APP_MIME_TYPES]

    def build(self):
        group = Adw.PreferencesGroup()
        group.set_title(_("Default Applications"))

        for label, mime_type in APP_MIME_TYPES:
            apps = self._get_apps_for_mime(mime_type)
            if not apps:
                continue
            desktop_ids = [did for did, _ in apps]
            display_names = [name for _, name in apps]

            row = Adw.ComboRow()
            row.set_title(label)
            row.set_model(Gtk.StringList.new(display_names))

            _loading = [True]
            current = self._get_default_app(mime_type)
            try:
                row.set_selected(desktop_ids.index(current))
            except ValueError:
                row.set_selected(0)
            _loading[0] = False

            if mime_type is None:
                # Terminal: write a wrapper desktop file so the choice takes effect
                def _set_terminal_default(r, _, ids=desktop_ids,
                                          _l=_loading, _store=self.store):
                    if _l[0]:
                        return
                    idx = r.get_selected()
                    if 0 <= idx < len(ids) and not self._set_terminal_by_id(ids[idx]):
                        _store.show_toast(_("Could not change default terminal"), True)

                row.connect("notify::selected", _set_terminal_default)
            else:
                def _set_default(r, _, mts=mime_type, ids=desktop_ids,
                                 _l=_loading, _store=self.store):
                    if _l[0]:
                        return
                    # xdg-mime shells out to gio/update-desktop-database and
                    # can stall the whole UI on a wedged session bus. Run it
                    # off the main thread; surface failures via idle_add so
                    # the toast lives on the GTK thread.
                    selected_id = ids[r.get_selected()]

                    def _worker():
                        try:
                            result = subprocess.run(
                                ["xdg-mime", "default", selected_id, *mts],
                                check=False, timeout=5,
                                capture_output=True, text=True,
                            )
                            if result.returncode != 0:
                                GLib.idle_add(
                                    lambda: (_store.show_toast(
                                        _("Could not change default app"),
                                        True), False)[1])
                        except (subprocess.TimeoutExpired,
                                FileNotFoundError, OSError):
                            GLib.idle_add(
                                lambda: (_store.show_toast(
                                    _("Could not change default app"),
                                    True), False)[1])

                    threading.Thread(target=_worker, daemon=True).start()
                row.connect("notify::selected", _set_default)

            group.add(row)

        self.add(group)
        return self

    @staticmethod
    def _set_terminal_by_id(desktop_id):
        app_info = Gio.DesktopAppInfo.new(desktop_id)
        if app_info:
            return DefaultAppsPage._set_terminal(app_info)
        return False

    @staticmethod
    def _set_terminal(app_info):
        cmd = app_info.get_commandline() or app_info.get_executable() or ""
        name = app_info.get_display_name() or "Terminal"

        # Sanitize: .desktop format uses newlines as field separators
        # and = as key-value delimiter — strip both from values
        name = name.replace("\n", " ").replace("\r", " ")
        cmd = cmd.replace("\n", " ").replace("\r", " ")

        # Reject invalid/empty commands. The previous implementation
        # used a character whitelist that rejected any legitimate path
        # containing a dot (e.g. /usr/libexec/foot-wrapper.sh or
        # /usr/bin/python3.12 -m foo), silently no-op'ing the terminal
        # selection. Use shlex to split correctly and resolve the
        # executable via shutil.which / Path.is_file instead.
        if not cmd:
            return False
        try:
            argv = shlex.split(cmd)
        except ValueError:
            return False
        if not argv:
            return False
        exe = argv[0]
        resolved = shutil.which(exe) if "/" not in exe else exe
        if not resolved or not Path(resolved).is_file():
            return False

        desktop_dir = Path.home() / ".local/share/applications"
        dest = desktop_dir / "terminal.desktop"
        tmp = dest.with_suffix(".desktop.tmp")
        content = (
            "[Desktop Entry]\n"
            f"Name={name}\n"
            f"Exec={cmd}\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Categories=TerminalEmulator;\n"
        )
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, dest)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        return True

    @staticmethod
    def _get_apps_for_mime(mime_type):
        if mime_type is None:
            apps, seen = [], set()
            for app in Gio.AppInfo.get_all():
                did = app.get_id()
                if not did or did in seen:
                    continue
                cats = app.get_categories() or ""
                if "TerminalEmulator" in cats:
                    seen.add(did)
                    apps.append((did, app.get_display_name()))
            return apps
        primary_mime = mime_type[0]
        seen, apps = set(), []
        for app in Gio.AppInfo.get_all_for_type(primary_mime):
            did = app.get_id()
            if not did or did in seen:
                continue
            seen.add(did)
            apps.append((did, app.get_display_name()))
        return apps

    @staticmethod
    def _get_default_app(mime_type):
        if mime_type is None:
            return ""
        primary_mime = mime_type[0]
        try:
            # xdg-mime is a shell script that calls into gio /
            # update-desktop-database / dbus, all of which can hang if
            # the session bus or a desktop-file handler is wedged.
            # Without timeout the page would freeze indefinitely on
            # the first cold build — this function is called once per
            # APP_MIME_TYPES entry on the main thread during build().
            return subprocess.run(
                ["xdg-mime", "query", "default", primary_mime],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return ""
