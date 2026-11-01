from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from gettext import gettext as _

from gi.repository import Gio, GLib

from .events import EventBus

# NetworkManager's GI introspection data is ~several MB and loading it
# noticeably slows settings-app startup on 2 GB hardware. Nothing in
# this module except NetworkManagerHelper touches NM, but sound.py
# imports PulseAudioSubscriber at module level, which would otherwise
# drag NM in on every settings launch whether the user touches Network
# or not. We stage the import behind _ensure_nm() so it only happens
# when someone actually instantiates NetworkManagerHelper. Module-level
# type annotations referencing NM.Client are fine because
# `from __future__ import annotations` makes every annotation a string
# at class-definition time.
NM = None  # type: ignore[assignment]


# Bounded default timeout for synchronous D-Bus calls made on the GTK
# main thread. BlueZ's Adapter1 methods (StartDiscovery especially) are
# known to hang ~25 s after suspend/resume on some Chromebook
# hardware; power-profiles-daemon is much faster but can still stall
# briefly during pstate transitions. Using -1 (infinite) froze the
# whole settings UI during those stalls. 5 s is long enough for any
# normal call, short enough that the user sees a responsive UI.
_DBUS_CALL_TIMEOUT_MS = 5000


def _ensure_nm() -> None:
    global NM
    if NM is not None:
        return
    import gi
    gi.require_version("NM", "1.0")
    from gi.repository import NM as _NM
    NM = _NM


# ---------------------------------------------------------------------------
#  Data types
# ---------------------------------------------------------------------------

@dataclass
class AccessPointInfo:
    path: str
    ssid: str
    strength: int
    secured: bool
    active: bool


@dataclass
class ConnectionInfo:
    name: str
    type: str
    ip_address: str
    gateway: str
    dns: str


@dataclass
class BluetoothDevice:
    path: str
    name: str
    paired: bool
    connected: bool
    icon: str
    address: str


# ---------------------------------------------------------------------------
#  NetworkManager helper
# ---------------------------------------------------------------------------

class NetworkManagerHelper:
    """Wraps NM.Client. Publishes events: nm-ready, network-changed,
    network-connect-success, network-connect-error."""

    def __init__(self, event_bus: EventBus) -> None:
        _ensure_nm()
        self._event_bus = event_bus
        self._client: NM.Client | None = None
        self._wifi_device: NM.DeviceWifi | None = None
        NM.Client.new_async(None, self._on_client_ready)

    def _on_client_ready(self, _source: object, result: Gio.AsyncResult) -> None:
        try:
            self._client = NM.Client.new_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: NetworkManager client init failed: {exc.message}", file=sys.stderr)
            self._publish("nm-unavailable")
            return
        for dev in self._client.get_devices():
            if isinstance(dev, NM.DeviceWifi):
                self._wifi_device = dev
                break
        self._client.connect("notify::wireless-enabled", lambda *_: self._publish("network-changed"))
        if self._wifi_device is not None:
            self._wifi_device.connect("access-point-added", lambda *_: self._publish("network-changed"))
            self._wifi_device.connect("access-point-removed", lambda *_: self._publish("network-changed"))
        self._client.connect("active-connection-added", lambda *_: self._publish("network-changed"))
        self._client.connect("active-connection-removed", lambda *_: self._publish("network-changed"))
        self._publish("nm-ready")

    def _publish(self, event: str, data=None) -> None:
        self._event_bus.publish(event, data)

    # -- Queries --

    @property
    def ready(self) -> bool:
        return self._client is not None

    def is_wifi_enabled(self) -> bool:
        return self._client.wireless_get_enabled() if self._client else False

    def set_wifi_enabled(self, enabled: bool) -> None:
        if not self._client:
            return
        try:
            self._client.wireless_set_enabled(enabled)
        except GLib.Error as exc:
            print(f"dbus_helpers: NM: wireless_set_enabled failed: {exc.message}", file=sys.stderr)
            # Publish network-changed so the wifi SwitchRow re-reads
            # is_wifi_enabled() and reverts to match NM's real state.
            # Matches the reconciliation pattern used for BlueZ powered
            # and PowerProfiles active-profile failures.
            self._event_bus.publish("network-changed")

    def get_access_points(self) -> list[AccessPointInfo]:
        if self._wifi_device is None:
            return []
        aps = self._wifi_device.get_access_points()
        seen: dict[str, NM.AccessPoint] = {}
        for ap in aps:
            ssid_bytes = ap.get_ssid()
            if ssid_bytes is None:
                continue
            ssid = ssid_bytes.get_data().decode("utf-8", errors="replace")
            if not ssid:
                continue
            if ssid not in seen or ap.get_strength() > seen[ssid].get_strength():
                seen[ssid] = ap
        active_ssid = self._get_active_wifi_ssid()
        result: list[AccessPointInfo] = []
        for ssid, ap in sorted(seen.items(), key=lambda x: -x[1].get_strength()):
            flags = ap.get_wpa_flags() | ap.get_rsn_flags()
            result.append(AccessPointInfo(
                path=ap.get_path(),
                ssid=ssid,
                strength=ap.get_strength(),
                secured=flags != 0,
                active=ssid == active_ssid,
            ))
        return result

    def request_scan(self) -> None:
        if self._wifi_device is not None:
            self._wifi_device.request_scan_async(None, self._on_scan_done)

    def _on_scan_done(self, device: NM.DeviceWifi, result: Gio.AsyncResult) -> None:
        try:
            device.request_scan_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: WiFi scan failed: {exc.message}", file=sys.stderr)
        self._publish("network-changed")

    def get_active_connection_info(self) -> ConnectionInfo | None:
        if self._client is None:
            return None
        for ac in self._client.get_active_connections():
            ip4 = ac.get_ip4_config()
            if ip4 is None:
                continue
            addresses = ip4.get_addresses()
            nameservers = ip4.get_nameservers()
            return ConnectionInfo(
                name=ac.get_id(),
                type=ac.get_connection_type(),
                ip_address=addresses[0].get_address() if addresses else _("N/A"),
                gateway=ip4.get_gateway() or _("N/A"),
                dns=", ".join(str(ns) for ns in nameservers) if nameservers else _("N/A"),
            )
        return None

    def has_wired(self) -> bool:
        if self._client is None:
            return False
        return any(isinstance(d, NM.DeviceEthernet) for d in self._client.get_devices())

    def is_wired_connected(self) -> bool:
        if self._client is None:
            return False
        return any(
            ac.get_connection_type() == "802-3-ethernet"
            for ac in self._client.get_active_connections()
        )

    # -- Actions --

    def connect_wifi(
        self,
        ssid: str,
        password: str | None,
        hidden: bool = False,
        security: str | None = None,
    ) -> None:
        if self._client is None or self._wifi_device is None:
            return
        if security is None:
            security = "wpa-psk" if password else "open"
        if security not in {"open", "wpa-psk"}:
            self._publish("network-connect-error", _("Unsupported WiFi security"))
            return
        if security == "open":
            password = None
        elif not password:
            self._publish("network-connect-error", _("Password cannot be empty"))
            return

        # Reuse existing saved connection when no new password is being supplied.
        if not password and not hidden:
            existing = self._find_connection_by_ssid(ssid)
            if existing is not None:
                self._client.activate_connection_async(
                    existing, self._wifi_device, None, None, self._on_activate_done,
                )
                return
        conn = NM.SimpleConnection.new()
        s_con = NM.SettingConnection.new()
        s_con.set_property("type", "802-11-wireless")
        s_con.set_property("id", ssid)
        conn.add_setting(s_con)
        s_wifi = NM.SettingWireless.new()
        s_wifi.set_property("ssid", GLib.Bytes.new(ssid.encode("utf-8")))
        if hidden:
            s_wifi.set_property("hidden", True)
        conn.add_setting(s_wifi)
        if security != "open":
            s_sec = NM.SettingWirelessSecurity.new()
            s_sec.set_property("key-mgmt", security)
            s_sec.set_property("psk", password)
            conn.add_setting(s_sec)
        self._client.add_and_activate_connection_async(
            conn, self._wifi_device, None, None, self._on_connect_done,
        )

    def _on_connect_done(self, client: NM.Client, result: Gio.AsyncResult) -> None:
        try:
            client.add_and_activate_connection_finish(result)
            self._publish("network-connect-success")
        except GLib.Error as exc:
            err = exc.message
            print(f"dbus_helpers: WiFi connect failed: {err}", file=sys.stderr)
            if "802-11-wireless-security.psk" in err:
                self._publish("network-connect-error", _("Wrong password."))
            else:
                self._publish("network-connect-error", _("Could not connect to network"))

    def _on_activate_done(self, client: NM.Client, result: Gio.AsyncResult) -> None:
        try:
            client.activate_connection_finish(result)
            self._publish("network-connect-success")
        except GLib.Error as exc:
            err = exc.message
            print(f"dbus_helpers: WiFi activate failed: {err}", file=sys.stderr)
            if "802-11-wireless-security.psk" in err:
                self._publish("network-connect-error", _("Wrong password."))
            else:
                self._publish("network-connect-error", _("Could not connect to network"))

    def disconnect_wifi(self) -> None:
        if self._client is None:
            return
        for ac in self._client.get_active_connections():
            if ac.get_connection_type() == "802-11-wireless":
                self._client.deactivate_connection_async(ac, None, self._on_deactivate_done)
                break

    def _on_deactivate_done(self, client: NM.Client, result: Gio.AsyncResult) -> None:
        try:
            client.deactivate_connection_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: deactivate failed: {exc.message}", file=sys.stderr)
        self._publish("network-changed")

    def forget_connection(self, ssid: str) -> None:
        if self._client is None:
            return
        for conn in self._client.get_connections():
            s_con = conn.get_setting_connection()
            if s_con and s_con.get_id() == ssid:
                conn.delete_async(None, self._on_delete_done)
                break

    def _on_delete_done(self, conn, result: Gio.AsyncResult) -> None:
        try:
            conn.delete_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: delete failed: {exc.message}", file=sys.stderr)
        self._publish("network-changed")

    def _find_connection_by_ssid(self, ssid: str) -> "NM.RemoteConnection | None":
        if self._client is None:
            return None
        ssid_bytes = ssid.encode("utf-8")
        for conn in self._client.get_connections():
            s_wifi = conn.get_setting_wireless()
            if s_wifi is None:
                continue
            stored = s_wifi.get_ssid()
            if stored is not None and stored.get_data() == ssid_bytes:
                return conn
        return None

    def _get_active_wifi_ssid(self) -> str | None:
        if self._client is None:
            return None
        for ac in self._client.get_active_connections():
            if ac.get_connection_type() == "802-11-wireless":
                return ac.get_id()
        return None


# ---------------------------------------------------------------------------
#  BlueZ helper
# ---------------------------------------------------------------------------

class BlueZHelper:
    """Wraps BlueZ D-Bus API via Gio.DBusProxy. Publishes event: bluetooth-changed."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        self._adapter_path: str | None = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: failed to connect to system bus: {exc.message}", file=sys.stderr)
            return
        self._find_adapter()
        self._subscribe_signals()

    def _find_adapter(self) -> None:
        try:
            result = self._bus.call_sync(
                "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                None, GLib.VariantType("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            )
            objects = result.unpack()[0]
            for path, interfaces in objects.items():
                if "org.bluez.Adapter1" in interfaces:
                    self._adapter_path = path
                    break
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: GetManagedObjects failed (no adapter): {exc.message}", file=sys.stderr)

    @property
    def available(self) -> bool:
        return self._adapter_path is not None

    def is_powered(self) -> bool:
        if not self.available:
            return False
        if self._bus is None:
            return False
        try:
            result = self._bus.call_sync(
                "org.bluez", self._adapter_path,
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", ("org.bluez.Adapter1", "Powered")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            )
            return result.unpack()[0]
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: get Powered failed: {exc.message}", file=sys.stderr)
            return False

    def set_powered(self, enabled: bool) -> None:
        if not self.available or self._bus is None:
            return
        self._bus.call(
            "org.bluez", self._adapter_path,
            "org.freedesktop.DBus.Properties", "Set",
            GLib.Variant("(ssv)", ("org.bluez.Adapter1", "Powered", GLib.Variant("b", enabled))),
            None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            self._on_set_powered_done,
        )

    def _on_set_powered_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: set Powered failed: {exc.message}", file=sys.stderr)
        # Publish bluetooth-changed on BOTH success and failure so the
        # SwitchRow re-reads `is_powered()` and reconciles with the real
        # adapter state. Without this on failure, the switch stays
        # visually "on" while the adapter is still off, and the user has
        # to click twice to retry (GTK's toggle is sticky past the
        # second click because `_updating` guards block it).
        self._event_bus.publish("bluetooth-changed")

    def get_devices(self) -> list[BluetoothDevice]:
        if self._bus is None:
            return []
        try:
            result = self._bus.call_sync(
                "org.bluez", "/",
                "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                None, GLib.VariantType("(a{oa{sa{sv}}})"),
                Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            )
            objects = result.unpack()[0]
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: GetManagedObjects (devices) failed: {exc.message}", file=sys.stderr)
            return []
        devices: list[BluetoothDevice] = []
        for path, interfaces in objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            props = interfaces["org.bluez.Device1"]
            name = props.get("Name") or props.get("Alias") or props.get("Address") or ""
            devices.append(BluetoothDevice(
                path=path,
                name=name,
                paired=props.get("Paired", False),
                connected=props.get("Connected", False),
                icon=props.get("Icon", "bluetooth-symbolic"),
                address=props.get("Address", ""),
            ))
        return devices

    def start_discovery(self) -> None:
        if not self.available or self._bus is None:
            return
        self._bus.call(
            "org.bluez", self._adapter_path,
            "org.bluez.Adapter1", "StartDiscovery",
            None, None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            self._on_start_discovery_done,
        )

    def _on_start_discovery_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: StartDiscovery failed: {exc.message}", file=sys.stderr)
        self._event_bus.publish("bluetooth-changed")

    def stop_discovery(self) -> None:
        if not self.available or self._bus is None:
            return
        self._bus.call(
            "org.bluez", self._adapter_path,
            "org.bluez.Adapter1", "StopDiscovery",
            None, None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            self._on_stop_discovery_done,
        )

    def _on_stop_discovery_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: StopDiscovery failed: {exc.message}", file=sys.stderr)
        self._event_bus.publish("bluetooth-changed")

    def pair_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        self._bus.call(
            "org.bluez", device_path,
            "org.bluez.Device1", "Pair",
            None, None, Gio.DBusCallFlags.NONE, 60000, None,
            self._on_pair_done,
        )

    def _on_pair_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
            self._event_bus.publish("bluetooth-pair-success")
        except GLib.Error as e:
            self._event_bus.publish("bluetooth-pair-error", e.message)

    def connect_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        self._bus.call(
            "org.bluez", device_path,
            "org.bluez.Device1", "Connect",
            None, None, Gio.DBusCallFlags.NONE, 30000, None,
            self._on_generic_done,
        )

    def disconnect_device(self, device_path: str) -> None:
        if self._bus is None:
            return
        self._bus.call(
            "org.bluez", device_path,
            "org.bluez.Device1", "Disconnect",
            None, None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            self._on_disconnect_device_done,
        )

    def _on_disconnect_device_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: Disconnect failed: {exc.message}", file=sys.stderr)
        self._event_bus.publish("bluetooth-changed")

    def remove_device(self, device_path: str) -> None:
        if not self.available or self._bus is None:
            return
        self._bus.call(
            "org.bluez", self._adapter_path,
            "org.bluez.Adapter1", "RemoveDevice",
            GLib.Variant("(o)", (device_path,)),
            None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            self._on_remove_device_done,
        )

    def _on_remove_device_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: RemoveDevice failed: {exc.message}", file=sys.stderr)
        self._event_bus.publish("bluetooth-changed")

    def _on_generic_done(self, bus: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: BlueZ: async device call failed: {exc.message}", file=sys.stderr)
        self._event_bus.publish("bluetooth-changed")

    def _subscribe_signals(self) -> None:
        self._sub_ids: list[int] = []
        if self._bus is None:
            return
        sub_id = self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.ObjectManager",
            "InterfacesAdded", "/", None,
            Gio.DBusSignalFlags.NONE, self._on_changed, None,
        )
        self._sub_ids.append(sub_id)
        sub_id = self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.ObjectManager",
            "InterfacesRemoved", "/", None,
            Gio.DBusSignalFlags.NONE, self._on_changed, None,
        )
        self._sub_ids.append(sub_id)
        sub_id = self._bus.signal_subscribe(
            "org.bluez", "org.freedesktop.DBus.Properties",
            "PropertiesChanged", None, None,
            Gio.DBusSignalFlags.NONE, self._on_props_changed, None,
        )
        self._sub_ids.append(sub_id)

    def teardown(self) -> None:
        if self._bus is None:
            return
        for sub_id in getattr(self, "_sub_ids", []):
            try:
                self._bus.signal_unsubscribe(sub_id)
            except Exception:
                pass
        self._sub_ids = []

    def _on_changed(self, *_args) -> None:
        self._event_bus.publish("bluetooth-changed")

    def _on_props_changed(self, _conn, _sender, _path, _iface, _signal, params, _data) -> None:
        try:
            unpacked = params.unpack()
            if not unpacked or len(unpacked) < 2:
                return
            iface_name = unpacked[0]
        except Exception:
            return
        if iface_name in ("org.bluez.Adapter1", "org.bluez.Device1"):
            self._event_bus.publish("bluetooth-changed")


# ---------------------------------------------------------------------------
#  power-profiles-daemon helper
# ---------------------------------------------------------------------------

class PowerProfilesHelper:
    """Wraps net.hadess.PowerProfiles D-Bus. Publishes event: power-profile-changed."""

    BUS_NAME = "net.hadess.PowerProfiles"
    OBJECT_PATH = "/net/hadess/PowerProfiles"
    IFACE = "net.hadess.PowerProfiles"

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bus: Gio.DBusConnection | None = None
        self._sub_id: int | None = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error as exc:
            print(f"dbus_helpers: PowerProfiles: failed to connect to system bus: {exc.message}", file=sys.stderr)
            return
        self._sub_id = self._bus.signal_subscribe(
            self.BUS_NAME, "org.freedesktop.DBus.Properties",
            "PropertiesChanged", self.OBJECT_PATH, None,
            Gio.DBusSignalFlags.NONE, self._on_props_changed, None,
        )

    def teardown(self) -> None:
        if self._bus is None:
            return
        if self._sub_id is not None:
            try:
                self._bus.signal_unsubscribe(self._sub_id)
            except Exception:
                pass
        self._sub_id = None

    @property
    def available(self) -> bool:
        return self._bus is not None

    def get_active_profile(self) -> str:
        if self._bus is None:
            return "balanced"
        try:
            result = self._bus.call_sync(
                self.BUS_NAME, self.OBJECT_PATH,
                "org.freedesktop.DBus.Properties", "Get",
                GLib.Variant("(ss)", (self.IFACE, "ActiveProfile")),
                GLib.VariantType("(v)"),
                Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            )
            return result.unpack()[0]
        except GLib.Error as exc:
            print(f"dbus_helpers: PowerProfiles: get ActiveProfile failed: {exc.message}", file=sys.stderr)
            return "balanced"

    def set_active_profile(self, profile: str) -> bool:
        if self._bus is None:
            self._event_bus.publish("power-profile-changed", self.get_active_profile())
            return False
        self._bus.call(
            self.BUS_NAME, self.OBJECT_PATH,
            "org.freedesktop.DBus.Properties", "Set",
            GLib.Variant("(ssv)", (self.IFACE, "ActiveProfile", GLib.Variant("s", profile))),
            None, Gio.DBusCallFlags.NONE, _DBUS_CALL_TIMEOUT_MS, None,
            lambda bus, result: self._on_set_active_profile_done(bus, result, profile),
        )
        return True

    def _on_set_active_profile_done(
        self, bus: Gio.DBusConnection, result: Gio.AsyncResult, profile: str
    ) -> None:
        try:
            bus.call_finish(result)
        except GLib.Error as exc:
            print(f"dbus_helpers: PowerProfiles: set ActiveProfile failed: {exc.message}", file=sys.stderr)
            # On success, power-profiles-daemon emits PropertiesChanged
            # and _on_props_changed reconciles the UI. On failure no
            # signal fires, so the ComboRow would sit on the value the
            # user picked while the daemon is still on the old one.
            # Publish with the daemon's ACTUAL current profile so the
            # page's handler (_on_profile_changed) can look it up in
            # its ComboRow values list — publishing without a payload
            # landed a None that the handler silently ignored.
            self._event_bus.publish("power-profile-changed", self.get_active_profile())
            return
        self._event_bus.publish("power-profile-changed", profile)

    def _on_props_changed(self, _conn, _sender, _path, _iface, _signal, params, _data) -> None:
        changed = params.unpack()[1]
        if "ActiveProfile" in changed:
            self._event_bus.publish("power-profile-changed", changed["ActiveProfile"])


# ---------------------------------------------------------------------------
#  PulseAudio event subscriber
# ---------------------------------------------------------------------------

class PulseAudioSubscriber:
    """Runs `pactl subscribe` in background thread, publishes audio-changed events.
    Automatically reconnects if the audio server restarts."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._proc: subprocess.Popen | None = None
        self._stopped = False
        self._start()

    def _start(self) -> None:
        import shutil
        import threading
        import time

        if shutil.which("pactl") is None:
            return

        def _reader():
            while not self._stopped:
                try:
                    self._proc = subprocess.Popen(
                        ["pactl", "subscribe"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        start_new_session=True,
                    )
                    for line in self._proc.stdout:
                        if self._stopped:
                            break
                        line = line.strip()
                        if not line:
                            continue
                        if any(kw in line for kw in ("sink", "source", "server")):
                            self._event_bus.publish("audio-changed")
                except Exception as exc:
                    print(f"dbus_helpers: PulseAudio: pactl subscriber error: {exc}", file=sys.stderr)
                if not self._stopped:
                    time.sleep(2)

        threading.Thread(target=_reader, daemon=True).start()

    def stop(self) -> None:
        self._stopped = True
        if self._proc is None:
            return
        try:
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        self._proc.kill()
                    except OSError:
                        pass
                    try:
                        self._proc.wait(timeout=2)
                    except Exception:
                        pass
            except Exception:
                pass
        finally:
            try:
                if self._proc.stdout is not None:
                    self._proc.stdout.close()
            except Exception:
                pass
            self._proc = None
