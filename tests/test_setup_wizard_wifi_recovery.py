"""Tests for installer Wi-Fi recovery behavior."""

import importlib.machinery
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-setup-wizard"
_loader = importlib.machinery.SourceFileLoader("setup_wizard_wifi", str(_SCRIPT))
_spec = importlib.util.spec_from_loader("setup_wizard_wifi", _loader, origin=str(_SCRIPT))
setup_wizard = importlib.util.module_from_spec(_spec)
setup_wizard.__file__ = str(_SCRIPT)
_spec.loader.exec_module(setup_wizard)


class _FakeConnectivityState:
    FULL = "full"
    UNKNOWN = "unknown"


class _FakeDeviceState:
    PREPARE = "prepare"
    CONFIG = "config"
    IP_CONFIG = "ip_config"
    IP_CHECK = "ip_check"
    NEED_AUTH = "need_auth"
    ACTIVATED = "activated"
    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"


class _FakeDeviceWifi:
    def __init__(self):
        self.scan_requests = 0

    def request_scan_async(self, _options, _callback):
        self.scan_requests += 1


class _FakeDeviceEthernet:
    def __init__(self, state=_FakeDeviceState.UNAVAILABLE):
        self._state = state

    def get_state(self):
        return self._state


class _FakeClientFactory:
    @staticmethod
    def new_finish(result):
        return result.client


class _FakeNM:
    Client = _FakeClientFactory
    ConnectivityState = _FakeConnectivityState
    DeviceState = _FakeDeviceState
    DeviceWifi = _FakeDeviceWifi
    DeviceEthernet = _FakeDeviceEthernet


class _FakeResult:
    def __init__(self, client):
        self.client = client


class _FakeClient:
    def __init__(self, devices=None, wireless_enabled=True):
        self.devices = list(devices or [])
        self.wireless_enabled = wireless_enabled
        self.wireless_set_calls = []
        self.callbacks = {}
        self.connectivity_callback = None

    def get_devices(self):
        return list(self.devices)

    def check_connectivity_async(self, _cancellable, callback):
        self.connectivity_callback = callback

    def check_connectivity_finish(self, _result):
        return _FakeConnectivityState.UNKNOWN

    def wireless_get_enabled(self):
        return self.wireless_enabled

    def wireless_set_enabled(self, enabled):
        self.wireless_set_calls.append(enabled)
        self.wireless_enabled = enabled

    def connect(self, signal_name, callback):
        self.callbacks[signal_name] = callback


class _FakeWidget:
    def __init__(self):
        self.visible = True
        self.sensitive = True
        self.text = ""
        self.css_added = []

    def set_visible(self, visible):
        self.visible = visible

    def set_sensitive(self, sensitive):
        self.sensitive = sensitive

    def set_text(self, text):
        self.text = text

    def set_label(self, text):
        self.text = text

    def add_css_class(self, css_class):
        self.css_added.append(css_class)

    def remove_css_class(self, css_class):
        if css_class in self.css_added:
            self.css_added.remove(css_class)


def _network_window():
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._nm_client = None
    window._wifi_device = None
    window._network_skipped = True
    window._connectivity_retries = 0
    window._current_page = setup_wizard.PAGE_LANGUAGE
    window._wired_poll_id = 1
    window._rescan_timer_id = 0
    window._update_navigation_calls = 0
    window._update_navigation = lambda: setattr(
        window, "_update_navigation_calls", window._update_navigation_calls + 1
    )

    window._net_status_label = _FakeWidget()
    window._wired_status_label = _FakeWidget()
    window._wired_connect_btn = _FakeWidget()
    window._wifi_header = _FakeWidget()
    window._wifi_list = _FakeWidget()
    window._wifi_empty_label = _FakeWidget()
    window._rescan_button = _FakeWidget()
    window._hidden_link = _FakeWidget()
    return window


def test_nm_client_ready_enables_wireless_radio(monkeypatch):
    monkeypatch.setattr(setup_wizard, "NM", _FakeNM)
    client = _FakeClient(wireless_enabled=False)
    window = _network_window()

    setup_wizard.SetupWizardWindow._on_nm_client_ready(
        window, None, _FakeResult(client)
    )

    assert client.wireless_set_calls == [True]
    assert client.connectivity_callback == window._on_connectivity_checked


def test_nm_client_ready_subscribes_to_late_wifi_devices(monkeypatch):
    monkeypatch.setattr(setup_wizard, "NM", _FakeNM)
    client = _FakeClient()
    window = _network_window()

    setup_wizard.SetupWizardWindow._on_nm_client_ready(
        window, None, _FakeResult(client)
    )
    wifi = _FakeDeviceWifi()
    client.devices.append(wifi)

    client.callbacks["device-added"](client, wifi)

    assert window._wifi_device is wifi
    assert wifi.scan_requests == 1
    assert window._wifi_header.visible is True
    assert window._hidden_link.visible is True


def test_connectivity_check_keeps_wifi_controls_visible_while_adapter_initializes(monkeypatch):
    monkeypatch.setattr(setup_wizard, "NM", _FakeNM)
    client = _FakeClient(devices=[])
    window = _network_window()
    window._nm_client = client

    setup_wizard.SetupWizardWindow._on_connectivity_checked(
        window, client, object()
    )

    assert window._network_skipped is False
    assert window._wifi_header.visible is True
    assert window._wifi_list.visible is True
    assert window._wifi_empty_label.visible is True
    assert window._rescan_button.visible is True
    assert window._hidden_link.visible is True
