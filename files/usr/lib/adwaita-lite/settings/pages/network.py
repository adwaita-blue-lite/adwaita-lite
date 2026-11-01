import subprocess
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ..base import BasePage


# Icon-name thresholds for WiFi signal strength rendering. The numeric
# cutoffs (75/50/25) match the pre-migration implementation.
_SIGNAL_ICONS: list[tuple[int, str]] = [
    (75, "network-wireless-signal-excellent-symbolic"),
    (50, "network-wireless-signal-good-symbolic"),
    (25, "network-wireless-signal-ok-symbolic"),
    (0, "network-wireless-signal-weak-symbolic"),
]

_HIDDEN_SECURITY_VALUES = ("open", "wpa-psk")


def _signal_icon(strength: int) -> str:
    for threshold, name in _SIGNAL_ICONS:
        if strength >= threshold:
            return name
    return _SIGNAL_ICONS[-1][1]


def _signal_label(strength: int) -> str:
    if strength >= 75:
        return _("Signal: excellent")
    if strength >= 50:
        return _("Signal: good")
    if strength >= 25:
        return _("Signal: fair")
    return _("Signal: weak")


class NetworkPage(BasePage, Adw.PreferencesPage):
    """Network settings: WiFi toggle + scan, available networks, active
    connection details, wired status, and a jump to nm-connection-editor.

    Adwaita wave-3 conversion. Returns an ``Adw.NavigationView`` so the
    password-entry and hidden-network flows can live as pushed sub-pages
    rather than modal top-level dialogs.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._nm = None
        self._nav: Adw.NavigationView | None = None
        self._wifi_toggle: Adw.SwitchRow | None = None
        self._banner: Adw.Banner | None = None
        self._networks_group: Adw.PreferencesGroup | None = None
        self._active_group: Adw.PreferencesGroup | None = None
        self._wired_row: Adw.ActionRow | None = None
        self._updating = False
        self._connect_in_flight: bool = False

    @property
    def search_keywords(self):
        return [
            (_("WiFi"), _("WiFi")), (_("WiFi"), _("Network")), (_("WiFi"), _("Wireless")),
            (_("WiFi"), _("Hidden network")), (_("WiFi"), _("Password")),
            (_("Wired"), _("Ethernet")), (_("Connection"), _("IP address")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        # Lazy instantiation: opening a NetworkManager client is a D-Bus
        # call. Only pay the cost when the user actually opens Network.
        from ..dbus_helpers import NetworkManagerHelper
        self._nm = NetworkManagerHelper(self.event_bus)

        # Banner sits above the first group and flags adapter absent /
        # airplane mode. Revealed dynamically from event handlers.
        self._banner = Adw.Banner.new(_("No network adapter"))
        self._banner.set_revealed(not self._nm.ready)

        self.add(self._build_wifi_group())
        self.add(self._build_networks_group())
        self.add(self._build_active_group())
        self.add(self._build_wired_group())
        self.add(self._build_advanced_group())

        # Wrap banner around self (PreferencesPage) so it actually renders.
        root_toolbar = Adw.ToolbarView()
        root_toolbar.add_top_bar(self._banner)
        root_toolbar.set_content(self)

        # Wrap in NavigationView so password + hidden-network sub-pages
        # can be pushed.
        self._nav = Adw.NavigationView()
        root_page = Adw.NavigationPage()
        root_page.set_title(_("Network"))
        root_page.set_child(root_toolbar)  # CHANGED: was .set_child(self)
        self._nav.add(root_page)

        # Subscriptions preserved from the pre-migration version.
        self.subscribe("nm-ready", self._on_nm_ready)
        # nm-unavailable fires when NM.Client.new_async failed outright
        # (NetworkManager daemon missing or masked). Without a handler,
        # the page looks frozen — wifi toggle stuck in default state,
        # no banner, no indication anything is wrong. Reveal the banner
        # and disable interaction.
        self.subscribe("nm-unavailable", lambda _d: self._on_nm_unavailable())
        self.subscribe("network-changed", lambda _d: self._refresh_all())
        self.subscribe("network-connect-success", self._on_connect_success)
        self.subscribe("network-connect-error", self._on_connect_error)

        self.setup_cleanup(self._nav)
        return self._nav

    # -- group builders -------------------------------------------------

    def _build_wifi_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("WiFi"))

        # Scan button as header-suffix (flat, refresh icon).
        scan_btn = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        scan_btn.add_css_class("flat")
        scan_btn.set_tooltip_text(_("Scan for networks"))
        try:
            scan_btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Scan for networks")]
            )
        except Exception:
            pass
        scan_btn.set_valign(Gtk.Align.CENTER)
        scan_btn.connect("clicked", lambda _b: self._nm.request_scan() if self._nm else None)
        group.set_header_suffix(scan_btn)

        # WiFi power toggle.
        self._wifi_toggle = Adw.SwitchRow()
        self._wifi_toggle.set_title(_("WiFi"))
        self._wifi_toggle.connect("notify::active", self._on_wifi_toggled)
        group.add(self._wifi_toggle)

        # Hidden-network push row.
        hidden_row = Adw.ActionRow()
        hidden_row.set_title(_("Connect to hidden network"))
        hidden_row.set_activatable(True)
        hidden_row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        hidden_row.connect("activated", lambda _r: self._push_hidden_network())
        group.add(hidden_row)

        return group

    def _build_networks_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Available Networks"))
        group.set_description(_("No networks found"))
        self._networks_group = group
        return group

    def _build_active_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Active Connection"))
        group.set_description(_("Not connected"))
        self._active_group = group
        return group

    def _build_wired_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Wired"))

        row = Adw.ActionRow()
        row.set_title(_("Ethernet"))
        row.set_subtitle(_("Checking..."))
        group.add(row)
        self._wired_row = row

        return group

    def _build_advanced_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Advanced"))

        row = Adw.ActionRow()
        row.set_title(_("Advanced network settings"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", self._open_connection_editor)
        group.add(row)

        return group

    def _open_connection_editor(self, _row) -> None:
        try:
            subprocess.Popen(
                ["nm-connection-editor"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            self.store.show_toast(_("Connection editor not found"), True)

    # -- event handlers -------------------------------------------------

    def _on_nm_ready(self, _data):
        if self._banner is not None:
            self._banner.set_revealed(not self._nm.ready)
        if self._wifi_toggle is not None:
            self._updating = True
            self._wifi_toggle.set_active(self._nm.is_wifi_enabled())
            self._updating = False
        self._refresh_all()
        if self._nm and hasattr(self._nm, "request_scan"):
            self._nm.request_scan()

    def _on_nm_unavailable(self):
        """NM.Client init failed — show the banner and lock the UI.

        Called from the nm-unavailable event. Flips the banner visible
        and disables the wifi switch so the user can't fire doomed
        toggle events into a daemon that isn't there.
        """
        if self._banner is not None:
            self._banner.set_title(_("NetworkManager is not available"))
            self._banner.set_revealed(True)
        if self._wifi_toggle is not None:
            self._wifi_toggle.set_sensitive(False)

    def _on_wifi_toggled(self, row, _pspec):
        if self._updating:
            return
        self._updating = True
        try:
            if self._nm:
                self._nm.set_wifi_enabled(row.get_active())
        finally:
            self._updating = False

    def _refresh_all(self):
        if self._banner is not None and self._nm is not None:
            self._banner.set_revealed(not self._nm.ready)
        self._refresh_networks()
        self._refresh_active()
        self._refresh_wired()

    # -- WiFi network list ---------------------------------------------

    def _refresh_networks(self):
        if self._networks_group is None or self._nm is None:
            return

        # Sync the WiFi switch without re-entering _on_wifi_toggled.
        if self._wifi_toggle is not None:
            self._updating = True
            self._wifi_toggle.set_active(self._nm.is_wifi_enabled())
            self._updating = False

        # Collect current rows indexed by the SSID they represent.
        # AdwPreferencesGroup exposes rows via the standard widget
        # iteration API. Each row stores its SSID in a ._ssid attribute
        # assigned in _build_network_row; rows that predate that field
        # (e.g. a static placeholder) are treated as orphan and removed.
        if not self._nm.ready:
            self._clear_network_rows()
            self._networks_group.set_description(_("No networks found"))
            return

        aps = self._nm.get_access_points()
        if not aps:
            self._clear_network_rows()
            self._networks_group.set_description(_("No networks found"))
            return

        self._networks_group.set_description("")

        # Diff: keep rows whose SSID is still in the AP list and move
        # them to the correct position; remove rows whose SSID is gone;
        # add new rows for SSIDs that weren't rendered before. This
        # preserves row identity (and thus keyboard focus / screen-
        # reader cursor) across scan updates, which matters for the
        # vision-impaired primary user who might be mid-click on a
        # weak-signal SSID when access-point-added fires.
        existing: dict[str, Adw.PreferencesRow] = {}
        child = self._networks_group.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesRow):
                ssid = getattr(child, "_ssid", None)
                if ssid is not None and ssid not in existing:
                    existing[ssid] = child
                else:
                    self._networks_group.remove(child)
            child = nxt

        seen_ssids: set[str] = set()
        for ap in aps:
            if ap.ssid in seen_ssids:
                continue
            seen_ssids.add(ap.ssid)
            if ap.ssid in existing:
                # Update in-place: subtitle (Connected), signal icon.
                row = existing.pop(ap.ssid)
                row.set_subtitle(_("Connected") if ap.active else "")
                signal_image = getattr(row, "_signal_image", None)
                if signal_image is not None:
                    signal_image.set_from_icon_name(
                        _signal_icon(ap.strength))
                    label = _signal_label(ap.strength)
                    signal_image.set_tooltip_text(label)
                    try:
                        signal_image.update_property(
                            [Gtk.AccessibleProperty.LABEL], [label])
                    except Exception:
                        pass
            else:
                self._networks_group.add(self._build_network_row(ap))

        # Remove rows for SSIDs that are no longer present.
        for leftover in existing.values():
            self._networks_group.remove(leftover)

    def _clear_network_rows(self) -> None:
        child = self._networks_group.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesRow):
                self._networks_group.remove(child)
            child = nxt

    def _build_network_row(self, ap) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_use_markup(False)
        # Stamp the SSID so _refresh_networks can diff rather than
        # rebuild on every network-changed event.
        row._ssid = ap.ssid
        row.set_title(ap.ssid)
        if ap.active:
            row.set_subtitle(_("Connected"))

        # Signal-strength icon (always present).
        signal = Gtk.Image.new_from_icon_name(_signal_icon(ap.strength))
        signal_label = _signal_label(ap.strength)
        signal.set_tooltip_text(signal_label)
        try:
            signal.update_property(
                [Gtk.AccessibleProperty.LABEL], [signal_label])
        except Exception:
            pass
        row.add_prefix(signal)
        # Stamp reference on the row so _refresh_networks can update the
        # icon in-place when a live scan changes the strength reading.
        row._signal_image = signal

        # Lock icon on secured networks (second prefix).
        if ap.secured:
            lock = Gtk.Image.new_from_icon_name("channel-secure-symbolic")
            lock.set_tooltip_text(_("Password protected"))
            try:
                lock.update_property(
                    [Gtk.AccessibleProperty.LABEL],
                    [_("Password protected")])
            except Exception:
                pass
            row.add_prefix(lock)

        if ap.active:
            forget_btn = Gtk.Button(label=_("Forget"))
            forget_btn.set_valign(Gtk.Align.CENTER)
            forget_btn.add_css_class("flat")
            forget_btn.connect("clicked", lambda _b, s=ap.ssid: self._forget(s))
            row.add_suffix(forget_btn)
        else:
            connect_btn = Gtk.Button(label=_("Connect"))
            connect_btn.set_valign(Gtk.Align.CENTER)
            connect_btn.connect("clicked", lambda _b, a=ap: self._connect(a))
            row.add_suffix(connect_btn)

        return row

    def _connect(self, ap):
        if self._connect_in_flight:
            # A previous connect is still pending. Firing a second
            # connect_wifi would race the first; NM would run both
            # and publish generic success/error for whichever settled
            # first with ambiguous UI feedback. Gate with a toast.
            self.store.show_toast(
                _("Another connection attempt is already running"), True)
            return
        if ap.secured:
            self._push_password_page(ap)
        else:
            self._connect_in_flight = True
            self.store.show_toast(
                _("Connecting to {ssid}…").format(ssid=ap.ssid)
            )
            self._nm.connect_wifi(ap.ssid, None)

    def _forget(self, ssid):
        dialog = Adw.AlertDialog.new(
            _("Forget network?"),
            _("This will remove the saved password for {ssid}.").format(
                ssid=ssid),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("forget", _("Forget"))
        dialog.set_response_appearance(
            "forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_forget_response, ssid)
        dialog.present(self.get_root())

    def _on_forget_response(self, _dialog, response, ssid):
        if response != "forget":
            return
        if self._nm:
            self._nm.forget_connection(ssid)

    # -- Password entry sub-page ---------------------------------------

    def _push_password_page(self, ap) -> None:
        sub = Adw.NavigationPage()
        sub.set_title(_("Connect to {ssid}").format(ssid=ap.ssid))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

        inner = Adw.PreferencesPage()

        group = Adw.PreferencesGroup()
        group.set_description(_("Enter the Wi-Fi password."))

        pw_row = Adw.PasswordEntryRow()
        pw_row.set_title(_("Password"))
        group.add(pw_row)
        inner.add(group)

        connect_group = Adw.PreferencesGroup()
        connect_row = Adw.ActionRow()
        connect_btn = Gtk.Button(label=_("Connect"))
        connect_btn.add_css_class("suggested-action")
        connect_btn.set_valign(Gtk.Align.CENTER)
        connect_btn.connect(
            "clicked", lambda _b: self._do_password_connect(ap, pw_row)
        )
        connect_row.add_suffix(connect_btn)
        connect_group.add(connect_row)
        inner.add(connect_group)

        toolbar.set_content(inner)
        sub.set_child(toolbar)
        self._nav.push(sub)

    def _do_password_connect(self, ap, pw_row) -> None:
        pw = pw_row.get_text()
        if not pw:
            self.store.show_toast(_("Password cannot be empty"), True)
            return
        if len(pw) < 8:
            self.store.show_toast(
                _("Password must be at least 8 characters"), True)
            return
        self.store.show_toast(
            _("Connecting to {ssid}...").format(ssid=ap.ssid)
        )
        if self._nm:
            self._connect_in_flight = True
            self._nm.connect_wifi(ap.ssid, pw)
        self._nav.pop()

    # -- Hidden network sub-page ---------------------------------------

    def _push_hidden_network(self) -> None:
        sub = Adw.NavigationPage()
        sub.set_title(_("Connect to Hidden Network"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

        inner = Adw.PreferencesPage()

        group = Adw.PreferencesGroup()
        group.set_description(
            _("Enter the network name and security details.")
        )

        ssid_row = Adw.EntryRow()
        ssid_row.set_title(_("Network name (SSID)"))
        group.add(ssid_row)

        sec_row = Adw.ComboRow()
        sec_row.set_title(_("Security"))
        sec_row.set_model(Gtk.StringList.new([
            _("None"), _("WPA/WPA2"),
        ]))
        sec_row.set_selected(1)  # default WPA/WPA2
        group.add(sec_row)

        pw_row = Adw.PasswordEntryRow()
        pw_row.set_title(_("Password"))
        group.add(pw_row)

        inner.add(group)

        connect_group = Adw.PreferencesGroup()
        connect_row = Adw.ActionRow()
        connect_btn = Gtk.Button(label=_("Connect"))
        connect_btn.add_css_class("suggested-action")
        connect_btn.set_valign(Gtk.Align.CENTER)
        connect_btn.connect(
            "clicked",
            lambda _b: self._do_hidden_connect(ssid_row, sec_row, pw_row),
        )
        connect_row.add_suffix(connect_btn)
        connect_group.add(connect_row)
        inner.add(connect_group)

        toolbar.set_content(inner)
        sub.set_child(toolbar)
        self._nav.push(sub)

    def _do_hidden_connect(self, ssid_row, sec_row, pw_row) -> None:
        ssid = ssid_row.get_text().strip()
        if not ssid:
            self.store.show_toast(_("Network name cannot be empty"), True)
            return
        try:
            ssid.encode("utf-8")
        except UnicodeEncodeError:
            self.store.show_toast(_("Network name is invalid"), True)
            return
        if len(ssid.encode("utf-8")) > 32:
            self.store.show_toast(_("Network name must be 32 bytes or less"), True)
            return

        sec_idx = sec_row.get_selected()
        security = (
            _HIDDEN_SECURITY_VALUES[sec_idx]
            if 0 <= sec_idx < len(_HIDDEN_SECURITY_VALUES)
            else "wpa-psk"
        )
        pw = None
        if security != "open":
            pw = pw_row.get_text()
            if not pw:
                self.store.show_toast(_("Password cannot be empty"), True)
                return
            if len(pw) < 8:
                self.store.show_toast(
                    _("Password must be at least 8 characters"), True)
                return
        self.store.show_toast(
            _("Connecting to {ssid}...").format(ssid=ssid)
        )
        if self._nm:
            self._connect_in_flight = True
            self._nm.connect_wifi(ssid, pw, hidden=True, security=security)
        self._nav.pop()

    # -- Connect-result feedback ---------------------------------------

    def _on_connect_success(self, _data):
        self._connect_in_flight = False
        # Toast auto-dismisses; no manual 3-second timer needed.
        self.store.show_toast(_("Connected successfully"))

    def _on_connect_error(self, message):
        self._connect_in_flight = False
        self.store.show_toast(str(message), True)

    # -- Active connection info ----------------------------------------

    def _refresh_active(self):
        if self._active_group is None or self._nm is None:
            return

        # Clear existing info rows.
        rows: list[Adw.PreferencesRow] = []
        child = self._active_group.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            if isinstance(child, Adw.PreferencesRow):
                rows.append(child)
            child = nxt
        for row in rows:
            self._active_group.remove(row)

        info = self._nm.get_active_connection_info()
        if info is None:
            self._active_group.set_description(_("Not connected"))
            return

        self._active_group.set_description("")
        for label, value in (
            (_("Network"), info.name),
            (_("Type"), info.type),
            (_("IP Address"), info.ip_address),
            (_("Gateway"), info.gateway),
            (_("DNS"), info.dns),
        ):
            self._active_group.add(self._make_property_row(label, value))

    @staticmethod
    def _make_property_row(label: str, value: str) -> Adw.ActionRow:
        row = Adw.ActionRow()
        row.set_title(label)
        row.set_subtitle(value)
        row.set_subtitle_selectable(True)
        row.add_css_class("property")
        return row

    # -- Wired status --------------------------------------------------

    def _refresh_wired(self):
        if self._wired_row is None or self._nm is None:
            return
        if not self._nm.has_wired():
            self._wired_row.set_subtitle(_("No wired adapter detected"))
        elif self._nm.is_wired_connected():
            self._wired_row.set_subtitle(_("Connected"))
        else:
            self._wired_row.set_subtitle(_("Disconnected"))
