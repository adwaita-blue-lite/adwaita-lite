import sys

from gi.repository import GLib


class EventBus:
    """Thread-safe publish/subscribe for system events. Callbacks run on the main GTK thread."""

    def __init__(self):
        self._subscribers: dict[str, list] = {}

    def subscribe(self, event: str, callback) -> None:
        self._subscribers.setdefault(event, []).append(callback)

    def unsubscribe(self, event: str, callback) -> None:
        if event in self._subscribers:
            self._subscribers[event] = [
                cb for cb in self._subscribers[event] if cb is not callback
            ]

    def publish(self, event: str, data=None) -> None:
        for cb in list(self._subscribers.get(event, [])):
            def _deliver(event=event, callback=cb, payload=data):
                # Re-check subscriber membership at delivery time. The
                # idle-add queue defers callbacks by at least one main-
                # loop iteration even when publish is called from the
                # main thread, so a page that unsubscribes (via
                # unsubscribe_all on widget unrealize) before the idle
                # dispatcher runs would previously still receive the
                # already-queued event and touch torn-down widgets.
                if callback not in self._subscribers.get(event, ()):
                    return GLib.SOURCE_REMOVE
                try:
                    callback(payload)
                except Exception as exc:
                    print(f"EventBus: callback error in {event!r}: {exc!r}", file=sys.stderr)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_deliver)
