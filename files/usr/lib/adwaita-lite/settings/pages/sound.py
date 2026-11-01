import json
import re
import subprocess
import threading
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage
from ..dbus_helpers import PulseAudioSubscriber


class SoundPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._pa = None
        self._updating = False
        self._refresh_pending = False
        # Volume-slider drag coalesce (see _on_out_vol_changed).
        self._pending_out_volume: int | None = None
        self._pending_in_volume: int | None = None
        self._out_vol_source: int | None = None
        self._in_vol_source: int | None = None
        self._refresh_source: int | None = None
        # Widget refs for live updates — rewritten by _refresh()
        # After conversion: ComboRow / inner Gtk.Scale / SwitchRow
        self._sink_dd = None    # Adw.ComboRow
        self._out_vol = None    # Gtk.Scale (suffix inside ActionRow)
        self._out_mute = None   # Adw.SwitchRow
        self._source_dd = None  # Adw.ComboRow
        self._in_vol = None     # Gtk.Scale (suffix inside ActionRow)
        self._in_mute = None    # Adw.SwitchRow
        self._sink_names = []
        self._source_names = []

    @property
    def search_keywords(self):
        return [
            (_("Output"), _("Output device")), (_("Output"), _("Volume")), (_("Output"), _("Mute")),
            (_("Input"), _("Input device")), (_("Input"), _("Microphone")),
        ]

    def build(self):
        # -- Output group --
        output_group = Adw.PreferencesGroup()
        output_group.set_title(_("Output"))

        sinks = self._get_sinks()
        self._sink_names = [n for n, _ in sinks]
        sink_descs = [d for _, d in sinks]
        default_sink = self._get_default_sink()
        try:
            sink_idx = self._sink_names.index(default_sink)
        except ValueError:
            sink_idx = 0

        self._sink_dd = Adw.ComboRow()
        self._sink_dd.set_title(_("Output device"))
        self._sink_dd.set_model(
            Gtk.StringList.new(sink_descs if sink_descs else [_("(No output devices)")])
        )
        self._sink_dd.set_selected(sink_idx)
        self._sink_dd.connect("notify::selected", self._on_sink_selected)
        output_group.add(self._sink_dd)

        out_vol_row = Adw.ActionRow()
        out_vol_row.set_title(_("Volume"))
        self._out_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._out_vol.set_value(self._get_volume("@DEFAULT_SINK@"))
        self._out_vol.set_size_request(150, -1)
        self._out_vol.set_hexpand(True)
        self._out_vol.set_draw_value(True)
        self._out_vol.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        self._out_vol.set_valign(Gtk.Align.CENTER)
        try:
            self._out_vol.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Output volume")]
            )
        except Exception:
            pass
        self._out_vol.connect("value-changed", self._on_out_vol_changed)
        out_vol_row.add_suffix(self._out_vol)
        output_group.add(out_vol_row)

        self._out_mute = Adw.SwitchRow()
        self._out_mute.set_title(_("Mute"))
        self._out_mute.set_active(self._get_mute("@DEFAULT_SINK@"))
        self._out_mute.connect("notify::active", self._on_out_mute_changed)
        output_group.add(self._out_mute)

        self.add(output_group)

        # -- Input group --
        input_group = Adw.PreferencesGroup()
        input_group.set_title(_("Input"))

        sources = self._get_sources()
        self._source_names = [n for n, _ in sources]
        source_descs = [d for _, d in sources]
        default_source = self._get_default_source()
        try:
            source_idx = self._source_names.index(default_source)
        except ValueError:
            source_idx = 0

        self._source_dd = Adw.ComboRow()
        self._source_dd.set_title(_("Input device"))
        self._source_dd.set_model(
            Gtk.StringList.new(source_descs if source_descs else [_("(No input devices)")])
        )
        self._source_dd.set_selected(source_idx)
        self._source_dd.connect("notify::selected", self._on_source_selected)
        input_group.add(self._source_dd)

        in_vol_row = Adw.ActionRow()
        in_vol_row.set_title(_("Volume"))
        self._in_vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self._in_vol.set_value(self._get_volume("@DEFAULT_SOURCE@", is_source=True))
        self._in_vol.set_size_request(150, -1)
        self._in_vol.set_hexpand(True)
        self._in_vol.set_draw_value(True)
        self._in_vol.set_format_value_func(lambda _s, v: f"{v:.0f}%")
        self._in_vol.set_valign(Gtk.Align.CENTER)
        try:
            self._in_vol.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Input volume")]
            )
        except Exception:
            pass
        self._in_vol.connect("value-changed", self._on_in_vol_changed)
        in_vol_row.add_suffix(self._in_vol)
        input_group.add(in_vol_row)

        self._in_mute = Adw.SwitchRow()
        self._in_mute.set_title(_("Mute"))
        self._in_mute.set_active(self._get_mute("@DEFAULT_SOURCE@", is_source=True))
        self._in_mute.connect("notify::active", self._on_in_mute_changed)
        input_group.add(self._in_mute)

        self.add(input_group)

        self.subscribe("audio-changed", self._on_audio_changed)

        def _on_map(_widget):
            # Lazy start: only subscribe to pactl events while the page is
            # mapped. Avoids a persistent `pactl subscribe` thread on
            # 2 GB Chromebooks where the sound page is rarely visible.
            if self._pa is None:
                self._pa = PulseAudioSubscriber(self.event_bus)
                self._refresh()

        def _on_unmap(_widget):
            if self._out_vol_source is not None:
                GLib.source_remove(self._out_vol_source)
                self._out_vol_source = None
            if self._in_vol_source is not None:
                GLib.source_remove(self._in_vol_source)
                self._in_vol_source = None
            if self._refresh_source is not None:
                GLib.source_remove(self._refresh_source)
                self._refresh_source = None
                self._refresh_pending = False
            if self._pa is not None:
                self._pa.stop()
                self._pa = None

        self.connect("map", _on_map)
        self.connect("unmap", _on_unmap)

        self.setup_cleanup(self)
        return self

    # -- Signal handlers (user interaction) --

    def _on_sink_selected(self, dropdown, _pspec):
        if self._updating:
            return
        idx = dropdown.get_selected()
        if self._sink_names and idx < len(self._sink_names):
            sink = self._sink_names[idx]

            def _worker():
                try:
                    subprocess.run(
                        ["pactl", "set-default-sink", sink],
                        capture_output=True, timeout=5,
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass

            threading.Thread(target=_worker, daemon=True).start()

    def _on_out_vol_changed(self, scale):
        if self._updating:
            return
        # Slider drag fires value-changed at ~60 Hz. A synchronous
        # pactl subprocess per event blocks the main loop for up to
        # 5 s on every tick if pipewire-pulse is busy — UI feels
        # jerky even under normal load. Coalesce to the scale's
        # latest value every 80 ms, run pactl then.
        self._pending_out_volume = int(scale.get_value())
        if self._out_vol_source is None:
            self._out_vol_source = GLib.timeout_add(80, self._flush_out_volume)

    def _flush_out_volume(self) -> bool:
        self._out_vol_source = None
        value = self._pending_out_volume
        if value is None:
            return False
        self._pending_out_volume = None
        try:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
                capture_output=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        return False

    def _on_out_mute_changed(self, switch_row, _pspec):
        if self._updating:
            return
        state = switch_row.get_active()

        def _worker():
            try:
                subprocess.run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if state else "0"],
                    capture_output=True, timeout=5,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_source_selected(self, dropdown, _pspec):
        if self._updating:
            return
        idx = dropdown.get_selected()
        if self._source_names and idx < len(self._source_names):
            source = self._source_names[idx]

            def _worker():
                try:
                    subprocess.run(
                        ["pactl", "set-default-source", source],
                        capture_output=True, timeout=5,
                    )
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass

            threading.Thread(target=_worker, daemon=True).start()

    def _on_in_vol_changed(self, scale):
        if self._updating:
            return
        self._pending_in_volume = int(scale.get_value())
        if self._in_vol_source is None:
            self._in_vol_source = GLib.timeout_add(80, self._flush_in_volume)

    def _flush_in_volume(self) -> bool:
        self._in_vol_source = None
        value = self._pending_in_volume
        if value is None:
            return False
        self._pending_in_volume = None
        try:
            subprocess.run(
                ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{value}%"],
                capture_output=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
        return False

    def _on_in_mute_changed(self, switch_row, _pspec):
        if self._updating:
            return
        state = switch_row.get_active()

        def _worker():
            try:
                subprocess.run(
                    ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1" if state else "0"],
                    capture_output=True, timeout=5,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

        threading.Thread(target=_worker, daemon=True).start()

    # -- Live event handling --

    # Coalesce rapid-fire audio-changed events (pactl subscribe publishes
    # one per volume tick) into a single refresh per ~100 ms window.
    # Each _refresh runs 6-8 subprocess calls with 5 s timeouts on the
    # GTK main thread; a sustained volume-key press otherwise micro-
    # freezes the UI. _DEBOUNCE_MS is short enough that users don't
    # perceive lag, long enough to absorb the typical event burst.
    _REFRESH_DEBOUNCE_MS = 100

    def _on_audio_changed(self, _data):
        if self._refresh_pending:
            return
        self._refresh_pending = True
        self._refresh_source = GLib.timeout_add(
            self._REFRESH_DEBOUNCE_MS, self._run_pending_refresh,
        )

    def _run_pending_refresh(self) -> bool:
        self._refresh_pending = False
        self._refresh_source = None
        self._refresh()
        return False  # one-shot

    # _refresh kicks a worker thread that reads 8 pactl values then
    # hops back to idle_add for the UI update. The synchronous version
    # froze the main loop for up to 5 s per refresh on slow adapters
    # (see G8).
    def _refresh(self):
        def _worker():
            try:
                sinks = self._get_sinks()
                default_sink = self._get_default_sink()
                out_vol = self._get_volume("@DEFAULT_SINK@")
                out_mute = self._get_mute("@DEFAULT_SINK@")
                sources = self._get_sources()
                default_source = self._get_default_source()
                in_vol = self._get_volume("@DEFAULT_SOURCE@", is_source=True)
                in_mute = self._get_mute("@DEFAULT_SOURCE@", is_source=True)
            except Exception:
                return
            GLib.idle_add(
                self._apply_refresh,
                sinks, default_sink, out_vol, out_mute,
                sources, default_source, in_vol, in_mute,
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_refresh(self, sinks, default_sink, out_vol, out_mute,
                       sources, default_source, in_vol, in_mute):
        # Page may have been unmapped between worker dispatch and idle
        # callback. Widget refs are torn to None on unmap; bail quietly.
        if self._sink_dd is None or self._out_vol is None:
            return False
        self._updating = True
        try:
            new_sink_names = [n for n, _ in sinks]
            sink_descs = [d for _, d in sinks]

            if new_sink_names != self._sink_names:
                self._sink_names = new_sink_names
                model = Gtk.StringList.new(sink_descs if sink_descs else [_("(No output devices)")])
                self._sink_dd.set_model(model)

            try:
                sink_idx = self._sink_names.index(default_sink)
            except ValueError:
                sink_idx = 0
            if self._sink_names:
                self._sink_dd.set_selected(sink_idx)

            self._out_vol.set_value(out_vol)
            self._out_mute.set_active(out_mute)

            new_source_names = [n for n, _ in sources]
            source_descs = [d for _, d in sources]

            if new_source_names != self._source_names:
                self._source_names = new_source_names
                model = Gtk.StringList.new(source_descs if source_descs else [_("(No input devices)")])
                self._source_dd.set_model(model)

            try:
                source_idx = self._source_names.index(default_source)
            except ValueError:
                source_idx = 0
            if self._source_names:
                self._source_dd.set_selected(source_idx)

            self._in_vol.set_value(in_vol)
            self._in_mute.set_active(in_mute)
        finally:
            self._updating = False
        return False

    # -- Static helpers: read current PulseAudio state --

    @staticmethod
    def _get_sinks():
        try:
            r = subprocess.run(["pactl", "-f", "json", "list", "sinks"],
                               capture_output=True, text=True, timeout=5)
            return [(s["name"], s.get("description", s["name"])) for s in json.loads(r.stdout)]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError,
                json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _get_default_sink():
        try:
            return subprocess.run(["pactl", "get-default-sink"],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return ""

    @staticmethod
    def _get_sources():
        try:
            r = subprocess.run(["pactl", "-f", "json", "list", "sources"],
                               capture_output=True, text=True, timeout=5)
            return [(s["name"], s.get("description", s["name"]))
                    for s in json.loads(r.stdout) if ".monitor" not in s["name"]]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError,
                json.JSONDecodeError, KeyError):
            return []

    @staticmethod
    def _get_default_source():
        try:
            return subprocess.run(["pactl", "get-default-source"],
                                  capture_output=True, text=True, timeout=5).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return ""

    @staticmethod
    def _get_volume(target, is_source=False):
        cmd = "get-source-volume" if is_source else "get-sink-volume"
        try:
            r = subprocess.run(["pactl", cmd, target], capture_output=True, text=True, timeout=5)
            m = re.search(r"(\d+)%", r.stdout)
            return int(m.group(1)) if m else 50
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return 50

    @staticmethod
    def _get_mute(target, is_source=False):
        cmd = "get-source-mute" if is_source else "get-sink-mute"
        try:
            return "yes" in subprocess.run(["pactl", cmd, target],
                                           capture_output=True, text=True, timeout=5).stdout.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False
