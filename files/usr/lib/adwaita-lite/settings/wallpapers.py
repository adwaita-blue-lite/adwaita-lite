"""Wallpaper manifest system.

Parses ``gnome-background-properties`` XML manifests for system- and
user-installed wallpapers. Supports paired light/dark variants and GNOME
timed-slideshow XML files.

``settings.json`` stores either a manifest ID (basename of the XML file,
no extension) or an absolute path for ad-hoc selections — the leading
slash is how we tell them apart.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from gi.repository import GLib

SYSTEM_MANIFEST_DIRS = (
    Path("/usr/share/gnome-background-properties"),
)
USER_MANIFEST_DIR = Path.home() / ".local/share/gnome-background-properties"
CUSTOM_WALLPAPER_DIR = Path.home() / ".local/share/adwaita-lite/custom-wallpapers"
FEDORA_DEFAULT_ID = "fedora-default"

# Declared as wallpapers upstream but not real desktop backgrounds
# (tiny logo-on-solid-color placeholders used by gdm / VNC fallback).
EXCLUDED_NAMES = frozenset({"Symbolics", "VNC"})

# Formats GdkPixbuf can render on the Adwaita-Lite image.
# JXL support is provided by the in-image libpixbufloader-jxl.so we build
# from libjxl upstream (see build_files/build.sh).
THUMBNAIL_EXTS = frozenset({
    ".svg", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff",
    ".jxl", ".avif", ".heif", ".heic",
})


@dataclass(frozen=True)
class Wallpaper:
    id: str
    name: str
    light_path: str
    dark_path: str
    manifest_path: str
    is_custom: bool = False

    def path_for_theme(self, theme: str) -> str:
        return self.dark_path if theme == "dark" else self.light_path


# Cache for list_wallpapers(). Keyed on (path, mtime_ns) for every
# manifest directory so it invalidates when the user adds/removes a
# custom wallpaper or the image is updated via bootc (which touches
# the parent dir's mtime when entries are added or removed).
_LIST_CACHE: list[Wallpaper] | None = None
_LIST_CACHE_KEY: tuple | None = None


def _cache_key() -> tuple:
    entries = []
    for d in (*SYSTEM_MANIFEST_DIRS, USER_MANIFEST_DIR):
        try:
            entries.append((str(d), d.stat().st_mtime_ns))
        except OSError:
            entries.append((str(d), None))
    return tuple(entries)


def _resolve_slideshow(xml_path: Path) -> tuple[str, str] | None:
    """Return ``(first_static_file, last_static_file)`` from a GNOME slideshow.

    Vendor timed-slideshow XMLs (e.g. Bluefin's ``NN-bluefin.xml``) alternate
    between day and night static frames; we treat first/last as light/dark.
    """
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return None
    files = [(e.findtext("file") or "").strip() for e in root.findall("static")]
    files = [f for f in files if f]
    if not files:
        return None
    return files[0], files[-1]


def _parse_manifest(xml_path: Path, *, is_custom: bool) -> list[Wallpaper]:
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return []

    out: list[Wallpaper] = []
    base_id = xml_path.stem

    for idx, wp in enumerate(root.findall("wallpaper")):
        if (wp.get("deleted") or "").lower() == "true":
            continue

        name = (wp.findtext("name") or "").strip()
        if not name or name in EXCLUDED_NAMES:
            continue

        light = (wp.findtext("filename") or "").strip()
        if not light:
            continue
        dark = (wp.findtext("filename-dark") or "").strip() or light

        if light.endswith(".xml"):
            slideshow = _resolve_slideshow(Path(light))
            if slideshow is None:
                continue
            first, last = slideshow
            if dark == light:
                light, dark = first, last
            else:
                light = first
        if dark.endswith(".xml"):
            slideshow = _resolve_slideshow(Path(dark))
            dark = slideshow[1] if slideshow else light

        if not Path(light).is_file():
            continue
        if Path(light).suffix.lower() not in THUMBNAIL_EXTS:
            continue
        if not Path(dark).is_file() or Path(dark).suffix.lower() not in THUMBNAIL_EXTS:
            dark = light

        wp_id = base_id if idx == 0 else f"{base_id}:{idx}"
        out.append(Wallpaper(
            id=wp_id, name=name,
            light_path=light, dark_path=dark,
            manifest_path=str(xml_path), is_custom=is_custom,
        ))
    return out


def list_wallpapers() -> list[Wallpaper]:
    """Enumerate known wallpapers, sorted: system first (alphabetical), then custom."""
    global _LIST_CACHE, _LIST_CACHE_KEY

    key = _cache_key()
    if _LIST_CACHE is not None and _LIST_CACHE_KEY == key:
        return _LIST_CACHE

    seen: set[str] = set()
    system: list[Wallpaper] = []
    custom: list[Wallpaper] = []

    for d in SYSTEM_MANIFEST_DIRS:
        if not d.is_dir():
            continue
        for xml in sorted(d.glob("*.xml")):
            for wp in _parse_manifest(xml, is_custom=False):
                if wp.id in seen:
                    continue
                seen.add(wp.id)
                system.append(wp)

    if USER_MANIFEST_DIR.is_dir():
        for xml in sorted(USER_MANIFEST_DIR.glob("*.xml")):
            for wp in _parse_manifest(xml, is_custom=True):
                if wp.id in seen:
                    continue
                seen.add(wp.id)
                custom.append(wp)

    system.sort(key=lambda w: w.name.casefold())
    custom.sort(key=lambda w: w.name.casefold())
    _LIST_CACHE = system + custom
    _LIST_CACHE_KEY = key
    return _LIST_CACHE


def get_wallpaper(wp_id: str) -> Wallpaper | None:
    if not wp_id or wp_id.startswith("/"):
        return None
    wallpapers = list_wallpapers()
    if wp_id == FEDORA_DEFAULT_ID:
        fedora_defaults = [
            wp for wp in wallpapers
            if re.fullmatch(r"f\d+", wp.id)
            and wp.name.lower().startswith("fedora ")
            and "default" in wp.name.lower()
        ]
        if fedora_defaults:
            return sorted(fedora_defaults, key=lambda wp: wp.id, reverse=True)[0]
    for wp in wallpapers:
        if wp.id == wp_id:
            return wp
    return None


def resolve_for_theme(value: str, theme: str) -> str | None:
    """Resolve a stored wallpaper value (ID or absolute path) to a concrete file."""
    if not value:
        return None
    if value.startswith("/"):
        return value if Path(value).is_file() else None
    wp = get_wallpaper(value)
    return wp.path_for_theme(theme) if wp is not None else None


#: Maximum size of a file the user can pick as a custom wallpaper.
#: A 50 MB cap comfortably accommodates every reasonable photo size
#: while preventing a user (or a renamed non-image file) from driving
#: shutil.copy2 into a multi-gigabyte synchronous copy on the main
#: thread. Enforced before the copy starts so the UI doesn't freeze.
_CUSTOM_WALLPAPER_MAX_BYTES = 50 * 1024 * 1024

#: Content types we're willing to treat as wallpapers. Sniffed via
#: Gio.File.query_info against the actual file header, not the
#: extension — a .mp4 renamed to .jpg would previously land in the
#: manifest and break thumbnail decode on every re-render.
_CUSTOM_WALLPAPER_ALLOWED_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/bmp",
    "image/tiff", "image/svg+xml", "image/x-portable-pixmap",
    "image/jxl", "image/avif", "image/heif", "image/heic",
}


#: Reasons add_custom can fail, surfaced via the tuple return so the
#: caller can show a meaningful toast instead of a generic error.
ADD_CUSTOM_OK = "ok"
ADD_CUSTOM_MISSING = "missing"
ADD_CUSTOM_TOO_LARGE = "too_large"
ADD_CUSTOM_UNSUPPORTED = "unsupported"
ADD_CUSTOM_IO_ERROR = "io_error"


def add_custom(source_path: str) -> Wallpaper | None:
    """Copy *source_path* into the user wallpaper dir and register a manifest.

    Thin wrapper around :func:`add_custom_detailed` for callers that
    only need the success case. Returns the new Wallpaper on success,
    ``None`` on any failure.
    """
    _status, wallpaper = add_custom_detailed(source_path)
    return wallpaper


def add_custom_detailed(source_path: str) -> tuple[str, Wallpaper | None]:
    """Same as :func:`add_custom` but returns a (status, wallpaper) tuple.

    Status is one of the ADD_CUSTOM_* constants so the picker can
    show a specific error: "file too large", "file type not supported",
    etc., instead of a generic "could not add wallpaper". The wallpaper
    is only non-None when status == ADD_CUSTOM_OK.
    """
    src = Path(source_path).resolve()
    if not src.is_file():
        return ADD_CUSTOM_MISSING, None

    try:
        if src.stat().st_size > _CUSTOM_WALLPAPER_MAX_BYTES:
            return ADD_CUSTOM_TOO_LARGE, None
    except OSError:
        return ADD_CUSTOM_IO_ERROR, None

    # Sniff the MIME from file content via Gio (not just the extension).
    try:
        from gi.repository import Gio
        info = Gio.File.new_for_path(str(src)).query_info(
            "standard::content-type", Gio.FileQueryInfoFlags.NONE, None,
        )
        content_type = info.get_content_type() or ""
    except GLib.Error:
        content_type = ""
    # Reject if content_type is empty OR not in allowed list
    if content_type not in _CUSTOM_WALLPAPER_ALLOWED_TYPES:
        return ADD_CUSTOM_UNSUPPORTED, None

    CUSTOM_WALLPAPER_DIR.mkdir(parents=True, exist_ok=True)
    USER_MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    try:
        digest = hashlib.sha1(src.read_bytes()).hexdigest()[:10]
    except OSError:
        return ADD_CUSTOM_IO_ERROR, None
    wp_id = f"custom-{digest}"
    dest = CUSTOM_WALLPAPER_DIR / f"{wp_id}{src.suffix.lower()}"

    try:
        if not dest.exists():
            shutil.copy2(src, dest)
    except OSError:
        return ADD_CUSTOM_IO_ERROR, None

    display_name = src.stem.replace("_", " ").replace("-", " ").strip()
    display_name = display_name.title() if display_name else "Custom"

    manifest_path = USER_MANIFEST_DIR / f"{wp_id}.xml"
    xml_content = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE wallpapers SYSTEM "gnome-wp-list.dtd">\n'
        '<wallpapers>\n'
        '  <wallpaper deleted="false">\n'
        f'    <name>{_escape_xml(display_name)}</name>\n'
        f'    <filename>{_escape_xml(str(dest))}</filename>\n'
        '    <options>zoom</options>\n'
        '    <shade_type>solid</shade_type>\n'
        '    <pcolor>#000000</pcolor>\n'
        '    <scolor>#000000</scolor>\n'
        '  </wallpaper>\n'
        '</wallpapers>\n'
    )
    manifest_tmp = manifest_path.with_suffix(".xml.tmp")
    try:
        manifest_tmp.write_text(xml_content, encoding="utf-8")
        os.replace(manifest_tmp, manifest_path)
    except OSError:
        # Clean up orphan image copy
        try:
            dest.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            manifest_tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return ADD_CUSTOM_IO_ERROR, None

    return ADD_CUSTOM_OK, Wallpaper(
        id=wp_id, name=display_name,
        light_path=str(dest), dark_path=str(dest),
        manifest_path=str(manifest_path), is_custom=True,
    )


def remove_custom(wp_id: str) -> bool:
    """Remove a custom wallpaper's manifest and its copied image."""
    if not wp_id.startswith("custom-"):
        return False
    manifest_path = USER_MANIFEST_DIR / f"{wp_id}.xml"
    if not manifest_path.is_file():
        return False

    filename = ""
    try:
        root = ET.parse(manifest_path).getroot()
        filename = (root.findtext("wallpaper/filename") or "").strip()
    except (ET.ParseError, OSError):
        pass

    try:
        manifest_path.unlink()
    except OSError:
        return False

    if filename:
        f = Path(filename)
        try:
            if f.is_file() and CUSTOM_WALLPAPER_DIR.resolve() in f.resolve().parents:
                f.unlink()
        except OSError:
            pass
    return True


def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
