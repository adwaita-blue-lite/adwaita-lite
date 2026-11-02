import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings.events import EventBus


def test_subscribe_and_publish():
    bus = EventBus()
    received = []
    bus.subscribe("test-event", lambda data: received.append(data))
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("test-event", "payload")
    assert received == ["payload"]


def test_unsubscribe():
    bus = EventBus()
    received = []
    def cb(data):
        return received.append(data)
    bus.subscribe("test-event", cb)
    bus.unsubscribe("test-event", cb)
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("test-event", "payload")
    assert received == []


def test_publish_no_subscribers():
    bus = EventBus()
    bus.publish("nonexistent-event", "data")


def test_multiple_subscribers():
    bus = EventBus()
    r1, r2 = [], []
    bus.subscribe("evt", lambda d: r1.append(d))
    bus.subscribe("evt", lambda d: r2.append(d))
    with patch("settings.events.GLib") as mock_glib:
        mock_glib.idle_add.side_effect = lambda fn, *args: fn(*args)
        bus.publish("evt", 42)
    assert r1 == [42]
    assert r2 == [42]
