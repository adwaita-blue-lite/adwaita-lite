import json
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk

from .events import EventBus
from .settings_store import SettingsStore
from .window import SettingsWindow

APP_ID = "org.adwaitabluelite.Settings"
CSS_PATH = Path(__file__).parent / "css" / "style.css"
PALETTE_PATH = Path("/usr/share/adwaita-lite/palette.json")
_CHECK_FG_LIGHT = "#ffffff"
_CHECK_FG_DARK = "#2e3436"
_MIN_ICON_CONTRAST = 3.5


def _srgb_to_linear(channel: int) -> float:
    value = channel / 255
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    value = hex_color.removeprefix("#")
    if len(value) != 6:
        raise ValueError(hex_color)
    red, green, blue = (
        int(value[index:index + 2], 16)
        for index in (0, 2, 4)
    )
    return (
        0.2126 * _srgb_to_linear(red)
        + 0.7152 * _srgb_to_linear(green)
        + 0.0722 * _srgb_to_linear(blue)
    )


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    lum_a = _relative_luminance(hex_a)
    lum_b = _relative_luminance(hex_b)
    lighter = max(lum_a, lum_b)
    darker = min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def _accent_check_fg(hex_value: str) -> str:
    """Return a readable symbolic check color for an accent swatch."""
    try:
        light_contrast = _contrast_ratio(hex_value, _CHECK_FG_LIGHT)
    except ValueError:
        return _CHECK_FG_LIGHT
    if light_contrast >= _MIN_ICON_CONTRAST:
        return _CHECK_FG_LIGHT
    return _CHECK_FG_DARK


def _build_accent_css(current_accent: str = "blue") -> str:
    """Generate the .accent-<name> swatch rules from palette.json.

    Runs at app startup so the accent picker always reflects the
    current palette without a second file to keep in lockstep with
    palette.json. Returns an empty string if palette.json is
    unreadable; the app's @accent_color-driven rules still function
    and only the swatch fills go blank.
    """
    try:
        palette = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    accents = palette.get("accents", {})
    rules = []
    accent = accents.get(current_accent, accents.get("blue"))
    if accent:
        rules.append(f"@define-color accent_color {accent};")
        rules.append(f"@define-color accent_fg_color {_accent_check_fg(accent)};")
    for name, hex_value in accents.items():
        check_fg = _accent_check_fg(hex_value)
        rules.append(f".accent-{name} {{ background-color: {hex_value}; }}")
        rules.append(f".accent-{name}:checked image {{ color: {check_fg}; }}")
    return "\n".join(rules)


class SettingsApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        self._store = SettingsStore()
        self._event_bus = EventBus()
        self._accent_provider: Gtk.CssProvider | None = None
        self._event_bus.subscribe("accent-changed", self._reload_accent_css)

    def _reload_accent_css(self, accent: str | None = None) -> None:
        if self._accent_provider is None:
            return
        self._accent_provider.load_from_string(
            _build_accent_css(accent or self._store.get("accent", "blue"))
        )

    def do_activate(self) -> None:
        win = self.get_active_window()
        if win is not None:
            win.present()
            return
        if not getattr(self, "_css_providers_loaded", False):
            self._css_providers_loaded = True
            display = Gdk.Display.get_default()
            base_provider = Gtk.CssProvider()
            base_provider.load_from_path(str(CSS_PATH))
            Gtk.StyleContext.add_provider_for_display(
                display,
                base_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
            accent_css = _build_accent_css(self._store.get("accent", "blue"))
            if accent_css:
                self._accent_provider = Gtk.CssProvider()
                self._accent_provider.load_from_string(accent_css)
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    self._accent_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
                )
        win = SettingsWindow(self, self._store, self._event_bus)
        win.present()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self.set_accels_for_action("win.search", ["<Control>f"])


def main() -> None:
    app = SettingsApp()
    app.run([])
