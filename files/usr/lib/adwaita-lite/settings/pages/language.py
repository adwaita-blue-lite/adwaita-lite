import os
import subprocess
import threading
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage


class LanguagePage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)

    @property
    def search_keywords(self):
        return [
            (_("Language & Region"), _("Language")),
            (_("Language & Region"), _("Locale")),
            (_("Language & Region"), _("Regional format")),
        ]

    def build(self):
        # Info banner — lives outside the group, above it.
        self._banner = Adw.Banner.new(_("Changes take effect after logging out"))
        self._banner.set_revealed(True)

        loaded = [False]  # mutable so nested lambdas can read it
        # Placeholder list of locales used until the background thread
        # finishes enumerating them. Starting with the single canonical
        # en_US.UTF-8 avoids leaving an empty ComboRow (which renders
        # as a blank dropdown with no list popup).
        locales_ref: list[list[str]] = [["en_US.UTF-8"]]

        # System language row
        lang_row = Adw.ComboRow()
        lang_row.set_title(_("System language"))
        lang_row.set_model(Gtk.StringList.new(locales_ref[0]))
        lang_row.set_sensitive(False)
        lang_row.connect(
            "notify::selected",
            lambda r, _: None if not loaded[0] or not locales_ref[0]
            else self._set_locale(locales_ref[0][r.get_selected()]),
        )

        # Regional formats row
        fmt_row = Adw.ComboRow()
        fmt_row.set_title(_("Regional formats"))
        fmt_row.set_subtitle(_("Date, number, and currency format"))
        fmt_row.set_model(Gtk.StringList.new(locales_ref[0]))
        fmt_row.set_sensitive(False)
        fmt_row.connect(
            "notify::selected",
            lambda r, _: None if not loaded[0] or not locales_ref[0]
            else self._set_format(locales_ref[0][r.get_selected()]),
        )

        group = Adw.PreferencesGroup()
        group.set_title(_("Language & Region"))
        group.add(lang_row)
        group.add(fmt_row)
        self.add(group)

        # Three back-to-back localectl invocations (10s + 5s + 5s) used
        # to run on the main thread and froze the page for up to 20 s
        # before it ever appeared. Defer them to a worker and populate
        # the rows once all three have returned.
        def _load_worker():
            locales = self._get_locales()
            current_locale = self._get_current_locale()
            current_fmt = self._get_current_format()

            def _populate():
                if locales:
                    locales_ref[0] = locales
                    lang_row.set_model(Gtk.StringList.new(locales))
                    fmt_row.set_model(Gtk.StringList.new(locales))
                try:
                    lang_row.set_selected(locales_ref[0].index(current_locale))
                except (ValueError, IndexError):
                    lang_row.set_selected(0)
                try:
                    fmt_row.set_selected(locales_ref[0].index(current_fmt))
                except (ValueError, IndexError):
                    fmt_row.set_selected(0)
                lang_row.set_sensitive(True)
                fmt_row.set_sensitive(True)
                # Flip loaded AFTER set_selected so the initial
                # selections don't round-trip through localectl/polkit.
                loaded[0] = True
                return False

            GLib.idle_add(_populate)

        threading.Thread(target=_load_worker, daemon=True).start()

        wrapper = Adw.ToolbarView()
        wrapper.add_top_bar(self._banner)
        wrapper.set_content(self)
        return wrapper

    @staticmethod
    def _get_locales():
        try:
            r = subprocess.run(["localectl", "list-locales"],
                               capture_output=True, text=True, timeout=10)
            return [l.strip() for l in r.stdout.splitlines() if l.strip()]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return ["en_US.UTF-8"]

    @staticmethod
    def _get_current_locale():
        # Force C locale so the "System Locale: LANG=..." line label
        # isn't translated by the caller's session env; we parse
        # literal "LANG=" below.
        env = {**os.environ, "LC_ALL": "C"}
        try:
            r = subprocess.run(["localectl", "status"],
                               capture_output=True, text=True, timeout=5,
                               env=env)
            for line in r.stdout.splitlines():
                if "LANG=" in line:
                    return line.split("LANG=")[-1].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return "en_US.UTF-8"

    @staticmethod
    def _get_current_format():
        env = {**os.environ, "LC_ALL": "C"}
        try:
            r = subprocess.run(["localectl", "status"],
                               capture_output=True, text=True, timeout=5,
                               env=env)
            for line in r.stdout.splitlines():
                if "LC_TIME=" in line:
                    return line.split("LC_TIME=")[-1].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return LanguagePage._get_current_locale()

    def _set_locale(self, locale):
        # localectl talks to systemd-localed via D-Bus, which triggers a
        # polkit prompt. The subprocess doesn't return until the user
        # authenticates (or the 60s timeout expires). Running this
        # synchronously on the GTK main thread froze the settings
        # window — including the polkit agent's redraw path — for the
        # full duration; on a 2 GB Chromebook this looks like a hard
        # lockup. Threading keeps the UI responsive; idle_add posts
        # toasts back from the worker.
        self._run_localectl_async(
            ["localectl", "set-locale", f"LANG={locale}"],
            _("Failed to set language"),
            _("Language change timed out"),
        )

    def _set_format(self, locale):
        # systemd ≥ 246 unsets LANG when `localectl set-locale` is
        # called without one, so read the current LANG and pass it
        # through alongside the per-category overrides.
        current_lang = self._get_current_locale()
        self._run_localectl_async(
            ["localectl", "set-locale",
             f"LANG={current_lang}",
             f"LC_TIME={locale}",
             f"LC_NUMERIC={locale}",
             f"LC_MONETARY={locale}"],
            _("Failed to set regional format"),
            _("Format change timed out"),
        )

    def _run_localectl_async(self, argv, fail_msg, timeout_msg):
        def _worker():
            try:
                result = subprocess.run(
                    argv, capture_output=True, text=True, timeout=60,
                )
                if result.returncode != 0:
                    GLib.idle_add(
                        lambda: self.store.show_toast(fail_msg, True) or False)
            except FileNotFoundError:
                GLib.idle_add(lambda: self.store.show_toast(
                    _("Language settings are unavailable on this system"), True) or False)
            except subprocess.TimeoutExpired:
                GLib.idle_add(lambda: self.store.show_toast(timeout_msg, True) or False)
            except OSError as exc:
                msg = _("Language change failed: {reason}").format(
                    reason=str(exc))
                GLib.idle_add(lambda: self.store.show_toast(msg, True) or False)

        threading.Thread(target=_worker, daemon=True).start()
