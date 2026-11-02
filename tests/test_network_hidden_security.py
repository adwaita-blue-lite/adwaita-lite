import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings import dbus_helpers  # noqa: E402


class _FakeSetting:
    def __init__(self):
        self.properties = {}

    @classmethod
    def new(cls):
        return cls()

    def set_property(self, name, value):
        self.properties[name] = value


class _FakeConnection:
    def __init__(self):
        self.settings = []

    @classmethod
    def new(cls):
        return cls()

    def add_setting(self, setting):
        self.settings.append(setting)


class _FakeBytes:
    @staticmethod
    def new(value):
        return value


class _FakeNM:
    SimpleConnection = _FakeConnection
    SettingConnection = _FakeSetting
    SettingWireless = _FakeSetting
    SettingWirelessSecurity = _FakeSetting


class _FakeClient:
    def __init__(self):
        self.created_connection = None

    def add_and_activate_connection_async(self, conn, *_args):
        self.created_connection = conn


class _FakeBus:
    def __init__(self):
        self.events = []

    def publish(self, event, data=None):
        self.events.append((event, data))


def _make_helper(monkeypatch):
    monkeypatch.setattr(dbus_helpers, "NM", _FakeNM)
    monkeypatch.setattr(dbus_helpers.GLib, "Bytes", _FakeBytes)
    helper = dbus_helpers.NetworkManagerHelper.__new__(
        dbus_helpers.NetworkManagerHelper)
    helper._client = _FakeClient()
    helper._wifi_device = object()
    helper._event_bus = _FakeBus()
    return helper


def _security_settings(conn):
    return [
        setting for setting in conn.settings
        if "key-mgmt" in setting.properties
    ]


def test_hidden_open_network_has_no_security_setting(monkeypatch):
    helper = _make_helper(monkeypatch)

    helper.connect_wifi("Hidden", None, hidden=True, security="open")

    assert helper._client.created_connection is not None
    assert _security_settings(helper._client.created_connection) == []


def test_hidden_wpa_network_sets_wpa_psk(monkeypatch):
    helper = _make_helper(monkeypatch)

    helper.connect_wifi(
        "Hidden", "correct horse", hidden=True, security="wpa-psk")

    [security] = _security_settings(helper._client.created_connection)
    assert security.properties["key-mgmt"] == "wpa-psk"
    assert security.properties["psk"] == "correct horse"


def test_hidden_secured_network_requires_password(monkeypatch):
    helper = _make_helper(monkeypatch)

    helper.connect_wifi("Hidden", "", hidden=True, security="wpa-psk")

    assert helper._client.created_connection is None
    assert helper._event_bus.events == [
        ("network-connect-error", "Password cannot be empty")
    ]


def test_unknown_hidden_security_is_rejected(monkeypatch):
    helper = _make_helper(monkeypatch)

    helper.connect_wifi("Hidden", "correct horse", hidden=True, security="sae")

    assert helper._client.created_connection is None
    assert helper._event_bus.events == [
        ("network-connect-error", "Unsupported WiFi security")
    ]
