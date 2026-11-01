import os
import subprocess
import threading
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from ..base import BasePage


def _hash_password(plaintext: str) -> str:
    """Return a SHA-512 crypt(3) hash suitable for AccountsService.SetPassword.

    Uses openssl which produces the $6$salt$hash format required by
    /etc/shadow.  The stdlib crypt module was removed in Python 3.13.
    """
    result = subprocess.run(
        ["openssl", "passwd", "-6", "-stdin"],
        input=plaintext,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout.strip()


class UsersPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._bus = None
        self._user_path = None
        self._nav = None

    @property
    def search_keywords(self):
        return [
            (_("Users"), _("Display name")),
            (_("Users"), _("Password")),
            (_("Users"), _("Auto-login")),
            (_("Users"), _("Account")),
        ]

    _DBUS_TIMEOUT_MS = 5000

    def _ensure_dbus(self):
        """Lazily connect to the system bus and find the current user's object path."""
        if self._bus is not None:
            return
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        uid = os.getuid()
        result = self._bus.call_sync(
            "org.freedesktop.Accounts",
            "/org/freedesktop/Accounts",
            "org.freedesktop.Accounts",
            "FindUserById",
            GLib.Variant("(x)", (uid,)),
            GLib.VariantType("(o)"),
            Gio.DBusCallFlags.NONE, self._DBUS_TIMEOUT_MS, None,
        )
        self._user_path = result.unpack()[0]

    def _get_property(self, prop_name):
        """Get a property from the AccountsService User interface."""
        result = self._bus.call_sync(
            "org.freedesktop.Accounts", self._user_path,
            "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", ("org.freedesktop.Accounts.User", prop_name)),
            GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, self._DBUS_TIMEOUT_MS, None,
        )
        return result.unpack()[0]

    def build(self):
        try:
            self._ensure_dbus()
        except GLib.Error:
            status = Adw.StatusPage()
            status.set_icon_name("dialog-error-symbolic")
            status.set_title(_("Could not connect to AccountsService"))
            status.set_description(_("User account settings are unavailable."))
            return status  # CHANGED: was self.add(status); return self

        # Account group
        group = Adw.PreferencesGroup()
        group.set_title(_("Account"))

        # Display name — AdwEntryRow with explicit apply button
        real_name = ""
        try:
            real_name = self._get_property("RealName")
        except GLib.Error:
            pass
        name_row = Adw.EntryRow()
        name_row.set_title(_("Display name"))
        name_row.set_text(real_name)
        name_row.set_show_apply_button(True)
        name_row.connect("apply", self._on_name_activate)
        group.add(name_row)

        # Password — navigation row with chevron suffix
        pw_row = Adw.ActionRow()
        pw_row.set_title(_("Password"))
        pw_row.set_subtitle(_("Set a new password for your account"))
        pw_row.set_activatable(True)
        pw_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        pw_row.connect("activated", self._push_change_password)
        group.add(pw_row)

        # Automatic login — AdwSwitchRow
        auto_login = False
        try:
            auto_login = self._get_property("AutomaticLogin")
        except GLib.Error:
            pass
        auto_row = Adw.SwitchRow()
        auto_row.set_title(_("Automatic login"))
        auto_row.set_subtitle(_("Log in without a password at startup"))
        auto_row.set_active(auto_login)
        auto_row.connect("notify::active", self._on_autologin_set)
        group.add(auto_row)

        self.add(group)

        # Wrap self in an AdwNavigationView so _push_change_password can push
        self._nav = Adw.NavigationView()
        root_page = Adw.NavigationPage()
        root_page.set_title(_("Users"))
        root_page.set_child(self)  # self IS the PreferencesPage
        self._nav.add(root_page)

        setup_cleanup_target = self._nav
        self.setup_cleanup(setup_cleanup_target)
        return self._nav

    def _on_name_activate(self, row):
        new_name = row.get_text().strip()
        if not new_name:
            return

        # SetRealName is a PolicyKit-guarded D-Bus call, so it can block
        # the UI for up to _DBUS_TIMEOUT_MS (5s) waiting for authentication
        # or a stalled accounts-daemon. Dispatch to a worker thread and
        # surface any failure via idle_add so the Users page stays
        # responsive.
        def _worker():
            try:
                self._bus.call_sync(
                    "org.freedesktop.Accounts", self._user_path,
                    "org.freedesktop.Accounts.User", "SetRealName",
                    GLib.Variant("(s)", (new_name,)),
                    None, Gio.DBusCallFlags.NONE, self._DBUS_TIMEOUT_MS, None,
                )
            except GLib.Error as exc:
                msg = exc.message
                GLib.idle_add(
                    lambda m=msg: (self.store.show_toast(
                        _("Could not save name: {msg}").format(msg=m), True),
                        False)[1])

        threading.Thread(target=_worker, daemon=True).start()

    def _on_autologin_set(self, row, _pspec):
        if getattr(self, "_autologin_updating", False):
            return

        # SetAutomaticLogin is a PolicyKit-guarded D-Bus call. Run it in
        # a background thread so the switch-animated main loop stays
        # responsive; on failure, reconcile the switch back to the
        # pre-click state from the UI thread.
        desired = row.get_active()

        def _worker():
            try:
                self._bus.call_sync(
                    "org.freedesktop.Accounts", self._user_path,
                    "org.freedesktop.Accounts.User", "SetAutomaticLogin",
                    GLib.Variant("(b)", (desired,)),
                    None, Gio.DBusCallFlags.NONE, self._DBUS_TIMEOUT_MS, None,
                )
            except GLib.Error:
                GLib.idle_add(self._on_autologin_error, row, desired)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_autologin_error(self, row, attempted):
        self.store.show_toast(_("Could not change auto-login"), True)
        # Flip the switch back to the pre-click state. GTK already
        # animated to the new position before our signal handler
        # fired, so without reconciliation the switch lies about
        # the actual daemon state until the user clicks again.
        # The _autologin_updating guard prevents the reconciling
        # set_active from re-entering this handler and re-trying
        # the failing call.
        self._autologin_updating = True
        try:
            row.set_active(not attempted)
        finally:
            self._autologin_updating = False
        return False

    def _push_change_password(self, *_):
        sub = Adw.NavigationPage()
        sub.set_title(_("Change Password"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

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

        # Apply button as a suggested-action row below the entries
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
        # Stash the apply button so the async password worker can
        # re-enable it from the UI thread when the D-Bus call returns.
        self._apply_btn = apply_btn

        toolbar.set_content(inner)
        sub.set_child(toolbar)
        self._nav.push(sub)

    def _apply_password_change(self, new_pw, confirm_pw, sub):
        pw = new_pw.get_text()
        cpw = confirm_pw.get_text()
        if not pw:
            self.store.show_toast(_("Password cannot be empty"), True)
            return
        if pw != cpw:
            self.store.show_toast(_("Passwords do not match"), True)
            return

        # openssl passwd -6 takes ~200-500ms and AccountsService SetPassword
        # can block up to the full 5s D-Bus timeout when accounts-daemon is
        # queued behind PolicyKit — do both off the UI thread so the window
        # stays responsive. The apply button is disabled for the duration so
        # a frustrated user can't queue a second hash while the first is in
        # flight.
        apply_btn = getattr(self, "_apply_btn", None)
        if apply_btn is not None:
            apply_btn.set_sensitive(False)

        def _worker():
            try:
                hashed = _hash_password(pw)
                self._bus.call_sync(
                    "org.freedesktop.Accounts", self._user_path,
                    "org.freedesktop.Accounts.User", "SetPassword",
                    GLib.Variant("(ss)", (hashed, "")),
                    None, Gio.DBusCallFlags.NONE, self._DBUS_TIMEOUT_MS, None,
                )
                GLib.idle_add(self._on_password_success, sub)
            except (GLib.Error, subprocess.CalledProcessError,
                    subprocess.TimeoutExpired, FileNotFoundError, OSError):
                # FileNotFoundError covers the case where openssl is absent
                # from PATH (rare on a Fedora bootc image, but defensive on
                # a stripped-down build); OSError covers permission issues
                # on the openssl binary or accounts-daemon bus drop.
                GLib.idle_add(self._on_password_error)
            finally:
                if apply_btn is not None:
                    GLib.idle_add(
                        lambda: (apply_btn.set_sensitive(True), False)[1])

        threading.Thread(target=_worker, daemon=True).start()

    def _on_password_success(self, _sub):
        self.store.show_toast(_("Password changed"))
        if self._nav is not None:
            self._nav.pop()
        return False

    def _on_password_error(self):
        self.store.show_toast(_("Failed to set password"), True)
        return False
