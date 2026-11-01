from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ..base import BasePage

ACCEL_OPTIONS: list[tuple[str, str]] = [
    ("adaptive", _("Adaptive")),
    ("flat", _("Flat")),
]


def _pointer_speed_label(_scale, value: float) -> str:
    """Map a libinput pointer-speed value ([-1.0, 1.0]) to a word.

    GTK's default value format for a Scale is "-0.3" / "0.7" — fine
    for keyboard shortcuts, meaningless for a non-technical user
    comparing "slow" to "fast". Five bands matching how libinput's
    acceleration curve feels in practice.
    """
    if value <= -0.6:
        return _("Slowest")
    if value < -0.2:
        return _("Slow")
    if value <= 0.2:
        return _("Default")
    if value < 0.6:
        return _("Fast")
    return _("Fastest")


class MouseTouchpadPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._accel_values: list[str] = []

    @property
    def search_keywords(self):
        return [
            (_("Touchpad"), _("Tap to click")), (_("Touchpad"), _("Natural scrolling")),
            (_("Touchpad"), _("Pointer speed")), (_("Touchpad"), _("Scroll speed")),
            (_("Mouse"), _("Natural scrolling")), (_("Mouse"), _("Pointer speed")),
            (_("Mouse"), _("Acceleration")),
        ]

    def build(self):
        self.add(self._build_touchpad_group())
        self.add(self._build_mouse_group())
        self.setup_cleanup(self)
        return self

    # -- group builders -------------------------------------------------

    def _build_touchpad_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Touchpad"))

        # Tap to click
        tap_row = Adw.SwitchRow()
        tap_row.set_title(_("Tap to click"))
        tap_row.set_active(self.store.get("touchpad_tap_to_click", True))
        tap_row.connect("notify::active", self._on_tap_to_click)
        group.add(tap_row)

        # Natural scrolling (with subtitle preserved from pre-migration)
        natural_row = Adw.SwitchRow()
        natural_row.set_title(_("Natural scrolling"))
        natural_row.set_subtitle(_("Content moves with your fingers"))
        natural_row.set_active(self.store.get("touchpad_natural_scroll", False))
        natural_row.connect("notify::active", self._on_touchpad_natural_scroll)
        group.add(natural_row)

        # Pointer speed
        tp_speed_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        tp_speed_scale.set_value(self.store.get("touchpad_pointer_speed", 0.0))
        tp_speed_scale.set_size_request(120, -1)
        tp_speed_scale.set_hexpand(True)
        # Show the current value as "Slow" / "Default" / "Fast" rather
        # than a bare scale thumb. Without this, the slider has no
        # visible readout for sighted users and announces as just
        # "slider" to Orca with no indication of the selected value.
        tp_speed_scale.set_draw_value(True)
        tp_speed_scale.set_value_pos(Gtk.PositionType.RIGHT)
        tp_speed_scale.set_format_value_func(_pointer_speed_label)
        tp_speed_scale.set_valign(Gtk.Align.CENTER)
        try:
            tp_speed_scale.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Touchpad pointer speed")]
            )
        except Exception:
            pass
        tp_speed_scale.connect("value-changed", self._on_touchpad_pointer_speed)

        tp_speed_row = Adw.ActionRow()
        tp_speed_row.set_title(_("Pointer speed"))
        tp_speed_row.add_suffix(tp_speed_scale)
        group.add(tp_speed_row)

        # Scroll speed (discrete 1..10 — SpinRow adapts to narrow widths)
        scroll_row = Adw.SpinRow.new_with_range(1.0, 10.0, 1.0)
        scroll_row.set_title(_("Scroll speed"))
        scroll_row.set_value(float(self.store.get("touchpad_scroll_speed", 5)))
        scroll_row.connect(
            "notify::value",
            lambda r, _p: self.store.save_debounced(
                "touchpad_scroll_speed", int(r.get_value())
            ),
        )
        group.add(scroll_row)

        return group

    def _build_mouse_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Mouse"))

        # Natural scrolling
        mouse_natural_row = Adw.SwitchRow()
        mouse_natural_row.set_title(_("Natural scrolling"))
        mouse_natural_row.set_active(self.store.get("mouse_natural_scroll", False))
        mouse_natural_row.connect("notify::active", self._on_mouse_natural_scroll)
        group.add(mouse_natural_row)

        # Pointer speed
        mouse_speed_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, -1.0, 1.0, 0.1)
        mouse_speed_scale.set_value(self.store.get("mouse_pointer_speed", 0.0))
        mouse_speed_scale.set_size_request(120, -1)
        mouse_speed_scale.set_hexpand(True)
        # Match the touchpad slider: show the "Slow"/"Default"/"Fast"
        # readout so the value is announced by Orca and visible to
        # sighted users.
        mouse_speed_scale.set_draw_value(True)
        mouse_speed_scale.set_value_pos(Gtk.PositionType.RIGHT)
        mouse_speed_scale.set_format_value_func(_pointer_speed_label)
        mouse_speed_scale.set_valign(Gtk.Align.CENTER)
        try:
            mouse_speed_scale.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Mouse pointer speed")]
            )
        except Exception:
            pass
        mouse_speed_scale.connect("value-changed", self._on_mouse_pointer_speed)

        mouse_speed_row = Adw.ActionRow()
        mouse_speed_row.set_title(_("Pointer speed"))
        mouse_speed_row.add_suffix(mouse_speed_scale)
        group.add(mouse_speed_row)

        # Acceleration profile (replaces toggle-cards)
        accel_row = Adw.ComboRow()
        accel_row.set_title(_("Acceleration"))

        labels = [label for _value, label in ACCEL_OPTIONS]
        values = [value for value, _label in ACCEL_OPTIONS]
        self._accel_values = values
        accel_row.set_model(Gtk.StringList.new(labels))

        current = self.store.get("mouse_accel_profile", "adaptive")
        accel_row.set_selected(values.index(current) if current in values else 0)
        accel_row.connect("notify::selected", self._on_accel_profile)
        group.add(accel_row)

        return group

    # -- event handlers -------------------------------------------------

    def _on_tap_to_click(self, row: Adw.SwitchRow, _pspec) -> None:
        self.store.save_and_apply("touchpad_tap_to_click", row.get_active())

    def _on_touchpad_natural_scroll(self, row: Adw.SwitchRow, _pspec) -> None:
        self.store.save_and_apply("touchpad_natural_scroll", row.get_active())

    def _on_touchpad_pointer_speed(self, scale: Gtk.Scale) -> None:
        self.store.save_debounced("touchpad_pointer_speed", round(scale.get_value(), 1))

    def _on_mouse_natural_scroll(self, row: Adw.SwitchRow, _pspec) -> None:
        self.store.save_and_apply("mouse_natural_scroll", row.get_active())

    def _on_mouse_pointer_speed(self, scale: Gtk.Scale) -> None:
        self.store.save_debounced("mouse_pointer_speed", round(scale.get_value(), 1))

    def _on_accel_profile(self, row: Adw.ComboRow, _pspec) -> None:
        idx = row.get_selected()
        if 0 <= idx < len(self._accel_values):
            self.store.save_and_apply("mouse_accel_profile", self._accel_values[idx])
