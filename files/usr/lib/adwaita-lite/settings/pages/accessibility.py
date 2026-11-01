from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gtk

from ..base import BasePage

CURSOR_SIZES = [
    ("24", _("Default (24px)")),
    ("32", _("Large (32px)")),
    ("48", _("Larger (48px)")),
]


class AccessibilityPage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._prev_font_size = 11

    @property
    def search_keywords(self):
        return [
            (_("Accessibility"), _("Large text")),
            (_("Accessibility"), _("Cursor size")),
            (_("Accessibility"), _("High contrast")),
            (_("Accessibility"), _("Reduce motion")),
        ]

    def build(self):
        group = Adw.PreferencesGroup()
        group.set_title(_("Accessibility"))

        # -- Large text -------------------------------------------------
        large_text_row = Adw.SwitchRow()
        large_text_row.set_title(_("Large text"))
        large_text_row.set_subtitle(_("Increases font size for better readability"))
        # Remember the font size at page-load time so toggling off
        # restores the user's previous choice without round-tripping
        # through settings.json.
        self._prev_font_size = self.store.get("font_size", 11)
        large_text_row.set_active(self._prev_font_size >= 15)

        def _on_large_text(row, _pspec):
            if row.get_active():
                current = self.store.get("font_size", 11)
                if current < 15:
                    self._prev_font_size = current
                self.store.save_and_apply("font_size", 15)
            else:
                prev = self._prev_font_size if self._prev_font_size < 15 else 11
                self.store.save_and_apply("font_size", prev)

        large_text_row.connect("notify::active", _on_large_text)
        group.add(large_text_row)

        # -- Cursor size ------------------------------------------------
        labels = [label for _, label in CURSOR_SIZES]
        values = [val for val, _ in CURSOR_SIZES]
        cursor_row = Adw.ComboRow()
        cursor_row.set_title(_("Cursor size"))
        cursor_row.set_model(Gtk.StringList.new(labels))
        current = str(self.store.get("cursor_size", 24))
        cursor_row.set_selected(
            values.index(current) if current in values else 0
        )

        def _on_cursor_size(row, _pspec):
            idx = row.get_selected()
            if 0 <= idx < len(values):
                self.store.save_and_apply("cursor_size", int(values[idx]))

        cursor_row.connect("notify::selected", _on_cursor_size)
        group.add(cursor_row)

        # -- High contrast ----------------------------------------------
        contrast_row = Adw.SwitchRow()
        contrast_row.set_title(_("High contrast"))
        contrast_row.set_subtitle(_("Forces dark theme with stronger borders"))
        contrast_row.set_active(self.store.get("high_contrast", False))

        def _on_contrast(row, _pspec):
            self.store.save_and_apply("high_contrast", row.get_active())

        contrast_row.connect("notify::active", _on_contrast)
        group.add(contrast_row)

        # -- Reduce motion ----------------------------------------------
        motion_row = Adw.SwitchRow()
        motion_row.set_title(_("Reduce motion"))
        motion_row.set_subtitle(_("Disables animations throughout the interface"))
        motion_row.set_active(self.store.get("reduce_motion", False))

        def _on_motion(row, _pspec):
            self.store.save_and_apply("reduce_motion", row.get_active())

        motion_row.connect("notify::active", _on_motion)
        group.add(motion_row)

        self.add(group)
        return self
