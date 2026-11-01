"""Shared Adwaita-Lite theme helpers.

Adwaita-Lite owns its shell colors through settings.json plus
palette.json. GTK/GNOME settings are still written for third-party
apps, but our own shell surfaces should consume these tokens directly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path

DEFAULT_PALETTE_PATH = Path("/usr/share/adwaita-lite/palette.json")
DEFAULT_THEME = "light"
DEFAULT_ACCENT = "blue"

FALLBACK_PALETTE = {
    "light": {
        "window_bg": "#fafafa",
        "view_bg": "#ffffff",
        "headerbar_bg": "#ebebeb",
        "card_bg": "#ffffff",
        "fg": "#1e1e1e",
        "secondary_fg": "#5e5c64",
        "border": "#d9d9dc",
        "inactive_fg": "#c0bfbc",
    },
    "dark": {
        "window_bg": "#222226",
        "view_bg": "#1d1d20",
        "headerbar_bg": "#2e2e32",
        "card_bg": "#36363a",
        "fg": "#ffffff",
        "secondary_fg": "#c0bfbc",
        "border": "#434349",
        "inactive_fg": "#5e5c64",
    },
    "accents": {
        "blue": "#3584e4",
        "teal": "#2190a4",
        "green": "#3a944a",
        "yellow": "#c88800",
        "orange": "#ed5b00",
        "red": "#e62d42",
        "pink": "#d56199",
        "purple": "#9141ac",
        "slate": "#6f8396",
    },
}

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _valid_hex(value: object) -> bool:
    return isinstance(value, str) and _HEX_RE.fullmatch(value) is not None


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_palette(paths: Iterable[Path] | None = None) -> dict:
    """Load palette.json from the first readable path, with safe fallback."""
    search_paths = tuple(paths or (DEFAULT_PALETTE_PATH,))
    for path in search_paths:
        data = _load_json(path)
        if data is None:
            continue
        if _palette_is_usable(data):
            return data
    return FALLBACK_PALETTE


def _palette_is_usable(palette: dict) -> bool:
    try:
        accents = palette["accents"]
        light = palette["light"]
        dark = palette["dark"]
    except KeyError:
        return False
    if (
        not isinstance(accents, dict)
        or not isinstance(light, dict)
        or not isinstance(dark, dict)
    ):
        return False
    return (
        _valid_hex(accents.get(DEFAULT_ACCENT))
        and _valid_hex(accents.get("red"))
        and all(
            _valid_hex(theme.get(key))
            for theme in (light, dark)
            for key in ("window_bg", "fg", "border")
        )
    )


def normalize_theme(value: object, *, high_contrast: bool = False) -> str:
    if high_contrast:
        return "dark"
    if isinstance(value, str) and value in ("light", "dark"):
        return value
    return DEFAULT_THEME


def normalize_accent(value: object, palette: dict) -> str:
    accents = palette.get("accents", {})
    if isinstance(value, str) and _valid_hex(accents.get(value)):
        return value
    return DEFAULT_ACCENT


def hex_to_rgb_tuple(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def relative_luminance(color: str) -> float:
    red, green, blue = hex_to_rgb_tuple(color)

    def channel(value: int) -> float:
        adjusted = value / 255
        if adjusted <= 0.04045:
            return adjusted / 12.92
        return ((adjusted + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(red)
        + 0.7152 * channel(green)
        + 0.0722 * channel(blue)
    )


def contrast_ratio(foreground: str, background: str) -> float:
    fg_lum = relative_luminance(foreground)
    bg_lum = relative_luminance(background)
    lighter = max(fg_lum, bg_lum)
    darker = min(fg_lum, bg_lum)
    return (lighter + 0.05) / (darker + 0.05)


def accent_foreground(accent: str) -> str:
    dark = "#1e1e1e"
    light = "#ffffff"
    return dark if contrast_ratio(dark, accent) >= contrast_ratio(light, accent) else light


def coerce_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value in (0, 1):
            return bool(value)
    return default


def gtk_color_defines(settings: dict, paths: Iterable[Path] | None = None) -> str:
    """Return GTK CSS color definitions for Adwaita-Lite shell surfaces."""
    palette = load_palette(paths)
    high_contrast = coerce_bool(settings.get("high_contrast", False), False)
    theme_name = normalize_theme(settings.get("theme"), high_contrast=high_contrast)
    accent_name = normalize_accent(settings.get("accent"), palette)
    theme = palette[theme_name]
    accent = palette["accents"][accent_name]

    if high_contrast:
        window_bg = "#000000"
        window_fg = "#ffffff"
        borders = "#ffffff"
    else:
        window_bg = theme["window_bg"]
        window_fg = theme["fg"]
        borders = theme["border"]

    colors = {
        "window_bg_color": window_bg,
        "window_fg_color": window_fg,
        "borders": borders,
        "accent_color": accent,
        "accent_fg_color": accent_foreground(accent),
        "error_color": palette["accents"]["red"],
    }
    return "\n".join(
        f"@define-color {name} {value};"
        for name, value in colors.items()
    ) + "\n"
