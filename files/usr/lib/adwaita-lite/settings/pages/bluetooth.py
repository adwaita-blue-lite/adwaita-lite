import subprocess
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage


class BluetoothPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._bt = None
        self._toggle_row: Adw.SwitchRow | None = None
        self._paired_group: Adw.PreferencesGroup | None = None
        self._available_group: Adw.PreferencesGroup | None = None
        self._scan_btn: Gtk.Button | None = None
        self._scan_timer: int | None = None
        self._updating = False
        self._pairing_in_flight: bool = False

    @property
    def search_keywords(self):
        return [
            (_("Bluetooth"), _("Bluetooth")), (_("Bluetooth"), _("Pair")),
            (_("Bluetooth"), _("Wireless")), (_("Bluetooth"), _("Device")),
        ]

    def build(self):
        from ..dbus_helpers import BlueZHelper
        self._bt = BlueZHelper(self.event_bus)

        # -- Group 1: Main toggle (no title) --
        toggle_group = Adw.PreferencesGroup()
        self._toggle_row = Adw.SwitchRow()
        self._toggle_row.set_title(_("Bluetooth"))
        self._toggle_row.set_active(self._bt.is_powered())
        self._toggle_row.connect("notify::active", self._on_toggle)
        toggle_group.add(self._toggle_row)
        self.add(toggle_group)

        # -- Banner: no adapter --
        self._banner = Adw.Banner.new(_("No Bluetooth adapter found"))
        self._banner.set_revealed(not self._bt.available)

        # -- Group 2: Paired devices --
        self._paired_group = Adw.PreferencesGroup()
        self._paired_group.set_title(_("Paired Devices"))
        self._paired_group.set_description(_("No paired devices"))
        self.add(self._paired_group)

        # -- Group 3: Available devices with scan button as header-suffix --
        self._available_group = Adw.PreferencesGroup()
        self._available_group.set_title(_("Available Devices"))
        self._available_group.set_description(_("Tap 'Search' to find nearby devices"))

        self._scan_btn = Gtk.Button(label=_("Search for devices"))
        self._scan_btn.add_css_class("flat")
        self._scan_btn.connect("clicked", self._on_scan_clicked)
        self._available_group.set_header_suffix(self._scan_btn)

        # Without an adapter, start_discovery() is a no-op in the
        # helper. The scan button would still visually disable for 30 s
        # ("Scanning..."), then revert, implying a search actually
        # happened. Disable the scan and toggle controls up front so
        # the user can't trigger the phantom state.
        if not self._bt.available:
            self._scan_btn.set_sensitive(False)
            self._toggle_row.set_sensitive(False)

        self.add(self._available_group)

        # -- Group 4: Advanced --
        advanced_group = Adw.PreferencesGroup()
        adv_row = Adw.ActionRow()
        adv_row.set_title(_("Advanced"))
        adv_row.set_activatable(True)
        adv_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        adv_row.connect("activated", self._on_advanced_activated)
        advanced_group.add(adv_row)
        self.add(advanced_group)

        # -- Subscriptions --
        self.subscribe("bluetooth-changed", lambda _: self._refresh_devices())
        self.subscribe("bluetooth-pair-success", self._on_pair_success)
        self.subscribe("bluetooth-pair-error", self._on_pair_error)

        self._refresh_devices()

        wrapper = Adw.ToolbarView()
        wrapper.add_top_bar(self._banner)
        wrapper.set_content(self)
        wrapper.connect("unrealize", self._cleanup)
        self.setup_cleanup(wrapper)
        return wrapper

    def _on_advanced_activated(self, _row):
        try:
            subprocess.Popen(
                ["blueman-manager"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            self.store.show_toast(
                _("Bluetooth manager not available"), True)

    def _on_toggle(self, row, _pspec):
        if self._updating:
            return
        self._updating = True
        try:
            self._bt.set_powered(row.get_active())
        finally:
            self._updating = False

    def _on_scan_clicked(self, btn):
        self._bt.start_discovery()
        btn.set_sensitive(False)
        btn.set_label(_("Scanning..."))
        self._available_group.set_description(_("Scanning for devices..."))
        self._scan_timer = GLib.timeout_add_seconds(30, self._stop_scan)

    def _stop_scan(self):
        self._bt.stop_discovery()
        if self._scan_btn:
            self._scan_btn.set_sensitive(True)
            self._scan_btn.set_label(_("Search for devices"))
        if self._available_group:
            self._available_group.set_description(_("Tap 'Search' to find nearby devices"))
        self._scan_timer = None
        return GLib.SOURCE_REMOVE

    def _refresh_devices(self):
        if self._bt is None:
            return
        if self._paired_group is None or self._available_group is None:
            return
        self._updating = True
        self._toggle_row.set_active(self._bt.is_powered())
        self._updating = False

        # Clear paired group rows
        paired_rows = []
        child = self._paired_group.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesRow):
                paired_rows.append(child)
            child = nxt
        for row in paired_rows:
            self._paired_group.remove(row)

        # Clear available group rows
        available_rows = []
        child = self._available_group.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesRow):
                available_rows.append(child)
            child = nxt
        for row in available_rows:
            self._available_group.remove(row)

        # Repopulate
        has_paired = False
        has_available = False
        for dev in self._bt.get_devices():
            row = self._build_device_row(dev)
            if dev.paired:
                self._paired_group.add(row)
                has_paired = True
            else:
                self._available_group.add(row)
                has_available = True

        # Update empty-state descriptions
        if not has_paired:
            self._paired_group.set_description(_("No paired devices"))
        else:
            self._paired_group.set_description("")

        # Only update available description if not currently scanning
        if not has_available and self._scan_btn and self._scan_btn.get_sensitive():
            self._available_group.set_description(_("Tap 'Search' to find nearby devices"))
        elif has_available:
            self._available_group.set_description("")

    def _build_device_row(self, dev):
        row = Adw.ActionRow()
        row.set_use_markup(False)
        row.set_title(dev.name or _("Unknown device"))

        icon = Gtk.Image.new_from_icon_name(dev.icon or "bluetooth-symbolic")
        icon_label = dev.name or _("Bluetooth device")
        icon.set_tooltip_text(icon_label)
        try:
            icon.update_property([Gtk.AccessibleProperty.LABEL], [icon_label])
        except Exception:
            pass
        row.add_prefix(icon)

        if dev.paired:
            if dev.connected:
                row.set_subtitle(_("Connected"))
                dc_btn = Gtk.Button(label=_("Disconnect"))
                dc_btn.set_valign(Gtk.Align.CENTER)
                dc_btn.connect("clicked", lambda _, p=dev.path: self._bt.disconnect_device(p))
                row.add_suffix(dc_btn)
            else:
                conn_btn = Gtk.Button(label=_("Connect"))
                conn_btn.set_valign(Gtk.Align.CENTER)
                conn_btn.connect("clicked", lambda _, p=dev.path: self._bt.connect_device(p))
                row.add_suffix(conn_btn)

            forget_btn = Gtk.Button(label=_("Forget"))
            forget_btn.set_valign(Gtk.Align.CENTER)
            forget_btn.add_css_class("flat")
            forget_btn.connect("clicked", lambda _, p=dev.path: self._bt.remove_device(p))
            row.add_suffix(forget_btn)
        else:
            pair_btn = Gtk.Button(label=_("Pair"))
            pair_btn.set_valign(Gtk.Align.CENTER)
            pair_btn.connect("clicked", lambda _, p=dev.path: self._pair(p))
            row.add_suffix(pair_btn)

        return row

    def _pair(self, device_path):
        if self._pairing_in_flight:
            return
        self._pairing_in_flight = True
        self.store.show_toast(_("Pairing..."))
        self._bt.pair_device(device_path)

    def _on_pair_success(self, _data):
        self._pairing_in_flight = False
        self.store.show_toast(_("Paired successfully"))

    def _on_pair_error(self, message):
        self._pairing_in_flight = False
        # is_error=True paints the toast red; without it, users see a
        # pair failure as a neutral informational toast. The {message}
        # is a D-Bus error string from BlueZ — translators can't
        # localize it, but it's the only actionable hint we have.
        self.store.show_toast(_("Pairing failed: {message}").format(message=message), True)

    def _cleanup(self, *_args):
        if self._bt is not None:
            if self._scan_timer is not None:
                GLib.source_remove(self._scan_timer)
                self._scan_timer = None
            self._bt.stop_discovery()
            if hasattr(self._bt, "teardown"):
                self._bt.teardown()
            self._bt = None
        if self._scan_btn:
            self._scan_btn.set_sensitive(True)
            self._scan_btn.set_label(_("Search for devices"))
