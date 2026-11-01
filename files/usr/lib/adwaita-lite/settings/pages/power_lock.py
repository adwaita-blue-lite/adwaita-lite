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
TIMEOUT_VALUES = [secs for _label, secs in TIMEOUT_OPTIONS]

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


def _sanitize_timeout(value, default: int) -> int:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return default
    return seconds if seconds in TIMEOUT_VALUES else default


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
      - Event-bus subscriptions set up in build() and torn down when
        the page is destroyed.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        # Widgets we need to reach from outside build() (event-bus
        # handlers, test hooks) are held as attributes. Initialised
        # to None here; populated in build().
        self._profile_row: Adw.ComboRow | None = None
        self._updating_profile: bool = False
        self._reverting_lid: bool = False
        self._updating_suspend: bool = False

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

        # Tear down event-bus subscriptions and D-Bus signal watches
        # when the page is destroyed. Pages are cached across transient
        # unmaps, so helper teardown on unmap would silence external
        # power-profile updates until Settings is restarted.
        self.setup_cleanup(self)
        self.connect("unrealize", lambda _w: self._teardown_helpers())
        return self

    def _teardown_helpers(self) -> None:
        helper = getattr(self, "_power_helper", None)
        if helper is not None and hasattr(helper, "teardown"):
            try:
                helper.teardown()
            except Exception:
                pass

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
        # Lazy import: PowerProfilesHelper opens a D-Bus connection in
        # its __init__. Deferring the import to first build() avoids
        # making the connection at module load - window.py instantiates
        # every page class at startup but only calls build() on first
        # navigation, and we don't want 16 D-Bus connections for a
        # user who only opens Appearance.
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
        if not self._power_helper.available:
            row.set_sensitive(False)
            row.set_subtitle(_("Power profiles are unavailable on this system"))

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating_profile:
                return
            idx = r.get_selected()
            if 0 <= idx < len(values):
                value = values[idx]
                # Persist only after the daemon confirms the change via
                # power-profile-changed. Saving optimistically here made
                # settings.json claim "performance" even when
                # power-profiles-daemon was unavailable or rejected the
                # request.
                if not self._power_helper.set_active_profile(value):
                    self._on_profile_changed(
                        self.store.get("power_profile", "balanced")
                    )

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
        group.add(self._make_suspend_row())
        return group

    def _make_suspend_row(self) -> Adw.ComboRow:
        """Suspend timeout row with lock-timeout guard.

        If the user picks a suspend delay shorter than the configured
        lock delay, the machine would be asleep with the screen still
        unlocked — bail and toast instead of committing.
        """
        row = Adw.ComboRow()
        row.set_title(_("Suspend after"))
        labels = [label for label, _secs in TIMEOUT_OPTIONS]
        values = [secs for _label, secs in TIMEOUT_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = _sanitize_timeout(self.store.get("suspend_timeout", 0), 0)
        row.set_selected(values.index(current))

        def _on_suspend_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating_suspend:
                return
            idx = r.get_selected()
            if not (0 <= idx < len(values)):
                return
            new_val = values[idx]
            lock_val = _sanitize_timeout(self.store.get("lock_timeout", 300), 300)
            # new_val > 0 and lock_val > 0 filters out "Never" on either
            # side — no clamp makes sense when the comparison is against
            # an infinite delay.
            if new_val > 0 and lock_val > 0 and new_val < lock_val:
                self.store.show_toast(
                    _("Suspend delay must be at least as long as the lock delay."),
                    True,
                )
                stored = _sanitize_timeout(
                    self.store.get("suspend_timeout", 0), 0)
                stored_idx = values.index(stored)
                self._updating_suspend = True
                try:
                    r.set_selected(stored_idx)
                finally:
                    self._updating_suspend = False
                return
            self.store.save_and_apply("suspend_timeout", new_val)

        row.connect("notify::selected", _on_suspend_selected)
        return row

    def _build_lid_group(self) -> Adw.PreferencesGroup:
        row = Adw.ComboRow()
        row.set_title(_("When lid is closed"))

        labels = [label for _value, label in LID_OPTIONS]
        values = [value for value, _label in LID_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self.store.get("lid_close_action", "suspend")
        row.set_selected(values.index(current) if current in values else 0)
        self._lid_row = row
        self._lid_row_values = values

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._reverting_lid:
                return
            idx = r.get_selected()
            if not (0 <= idx < len(values)):
                return
            # Disable the row while pkexec is in flight. Rapid taps
            # would otherwise stack auth prompts and race the
            # save_and_apply callbacks; the last handler to win would
            # decide the stored value, regardless of what the user
            # ends up clicking Allow on.
            r.set_sensitive(False)
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

        current = _sanitize_timeout(self.store.get(key, default), default)
        row.set_selected(values.index(current))

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
            self._updating_profile = True
            try:
                self._profile_row.set_selected(idx)
            finally:
                self._updating_profile = False
        if self.store.get("power_profile", "balanced") != new_profile:
            self.store.save_and_apply("power_profile", new_profile)

    def _on_lid_action_changed(self, action: str) -> None:
        """Apply a new lid action via the privileged helper.

        Preserved verbatim from the pre-migration version: pkexec on
        a background thread; on success, persist via the store on the
        GLib main loop; on failure, show a toast.
        """
        def _reenable_and_reconcile(success: bool) -> bool:
            # Restore interactivity and — on failure — revert the
            # ComboRow to the stored value so the UI reflects actual
            # system state instead of the user's attempted pick.
            row = getattr(self, "_lid_row", None)
            if row is not None:
                if not success:
                    stored = self.store.get("lid_close_action", "suspend")
                    values = getattr(self, "_lid_row_values", [])
                    if stored in values:
                        idx = values.index(stored)
                        if row.get_selected() != idx:
                            # Guard with _reverting_lid so the notify::selected
                            # handler bails early instead of firing a second
                            # pkexec against the stored value.
                            self._reverting_lid = True
                            try:
                                row.set_sensitive(True)
                                row.set_selected(idx)
                            finally:
                                self._reverting_lid = False
                        else:
                            row.set_sensitive(True)
                    else:
                        row.set_sensitive(True)
                else:
                    row.set_sensitive(True)
            return False

        def _run() -> None:
            try:
                result = subprocess.run(
                    ["pkexec", "/usr/libexec/adwaita-lite-lid-action", action],
                    capture_output=True, timeout=60,
                )
            except subprocess.TimeoutExpired:
                GLib.idle_add(lambda: self.store.show_toast(
                    _("Lid action change timed out"), True) or False)
                GLib.idle_add(_reenable_and_reconcile, False)
                return
            except OSError:
                GLib.idle_add(lambda: self.store.show_toast(
                    _("Authentication tool not available"), True) or False)
                GLib.idle_add(_reenable_and_reconcile, False)
                return

            if result.returncode == 0:
                GLib.idle_add(lambda: self.store.save_and_apply(
                    "lid_close_action", action) or False)
                GLib.idle_add(_reenable_and_reconcile, True)
            elif result.returncode == 126:
                # Polkit auth declined — revert silently so the UI
                # matches reality without annoying the user with a
                # toast they already understand.
                GLib.idle_add(_reenable_and_reconcile, False)
            else:
                GLib.idle_add(lambda: self.store.show_toast(
                    _("Failed to change lid close action"), True) or False)
                GLib.idle_add(_reenable_and_reconcile, False)

        threading.Thread(target=_run, daemon=True).start()
