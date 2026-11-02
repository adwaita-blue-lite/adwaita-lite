import hashlib
import json
import os
import subprocess
import sys
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

from ..base import BasePage
from ..wallpapers import (
    ADD_CUSTOM_IO_ERROR,
    ADD_CUSTOM_MISSING,
    ADD_CUSTOM_OK,
    ADD_CUSTOM_TOO_LARGE,
    ADD_CUSTOM_UNSUPPORTED,
    Wallpaper,
    add_custom_detailed,
    list_wallpapers,
    remove_custom,
)

# Accent order displayed in the picker. Names must match palette.json
# keys; the visible fill color comes from the CSS rule .accent-<name>
# generated at app startup from palette.json (see app.py), so the hex
# is not referenced at runtime — only the name, and only as a CSS
# class suffix + the key passed to save_and_apply. A previous version
# hardcoded (name, hex) tuples here, giving us three separate places
# accent names had to stay in sync (this file, apply-settings'
# VALID_ACCENT, and palette.json). Now we read the palette once and
# let it drive the picker.
_PALETTE_PATH = Path("/usr/share/adwaita-lite/palette.json")
_ACCENT_FALLBACK = [
    "blue", "teal", "green", "yellow", "orange",
    "red", "pink", "purple", "slate",
]


def _accent_display_name(name: str) -> str:
    """Human-readable color name for screen readers and tooltips.

    Essential for the primary (vision-impaired) user: the circles
    have no visible label and, without this, Orca announces every
    one as identical "toggle button, pressed" with no way to tell
    them apart. Returns a translated string; falls back to the raw
    name (title-cased) for accent names we haven't pre-translated.
    """
    names = {
        "blue": _("Blue"),
        "teal": _("Teal"),
        "green": _("Green"),
        "yellow": _("Yellow"),
        "orange": _("Orange"),
        "red": _("Red"),
        "pink": _("Pink"),
        "purple": _("Purple"),
        "slate": _("Slate"),
    }
    return names.get(name, name.title())


def _load_accent_names() -> list[str]:
    try:
        palette = json.loads(_PALETTE_PATH.read_text(encoding="utf-8"))
        names = list(palette.get("accents", {}).keys())
        return names or _ACCENT_FALLBACK
    except (OSError, json.JSONDecodeError) as exc:
        print(f"appearance: palette.json unreadable ({exc}); "
              f"using fallback accent list", file=sys.stderr)
        return _ACCENT_FALLBACK

# Wallpaper thumbnail geometry.
TILE_W = 160
TILE_H = 100
# Cap decoded pixel size so 4K WebP thumbnails don't stall the UI thread
# on low-RAM hardware. Still 2× the display size for sharp rendering.
THUMB_MAX = max(TILE_W, TILE_H) * 2
# GdkPixbuf loaders for newer container formats are native code and have
# been crashy on the VM images used for testing. Never synchronously decode
# these in the Settings process; ask the thumbnail helper for a cached PNG
# and render a stable placeholder if the helper cannot produce one.
RISKY_THUMBNAIL_EXTS = {".jxl", ".avif", ".heif", ".heic"}
THUMBNAIL_HELPER = (
    Path(__file__).resolve().parents[4]
    / "libexec/adwaita-lite-wallpaper-thumbnailer"
)
THUMBNAIL_TIMEOUT_SECONDS = 8


def _thumbnail_placeholder() -> Gtk.Widget:
    box = Gtk.Box()
    box.add_css_class("wallpaper-placeholder")
    box.set_size_request(TILE_W, TILE_H)
    box.set_halign(Gtk.Align.FILL)
    box.set_valign(Gtk.Align.FILL)

    icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
    icon.set_pixel_size(32)
    icon.set_halign(Gtk.Align.CENTER)
    icon.set_valign(Gtk.Align.CENTER)
    box.append(icon)
    return box


def _thumbnail_cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    return (Path(base) if base else Path.home() / ".cache") / (
        "adwaita-lite/wallpaper-thumbnails"
    )


def _thumbnail_cache_path(path: str) -> Path | None:
    source = Path(path)
    try:
        stat = source.stat()
    except OSError:
        return None
    key = "\0".join((
        str(source.resolve(strict=False)),
        str(stat.st_mtime_ns),
        str(stat.st_size),
        str(THUMB_MAX),
    ))
    digest = hashlib.sha256(key.encode("utf-8", "surrogateescape")).hexdigest()
    return _thumbnail_cache_dir() / f"{digest}.png"


def _picture_from_texture_file(path: Path) -> Gtk.Widget | None:
    try:
        texture = Gdk.Texture.new_from_filename(str(path))
    except Exception as exc:
        print(f"appearance: cached thumbnail load failed for {path}: {exc}",
              file=sys.stderr)
        return None
    pic = Gtk.Picture.new_for_paintable(texture)
    pic.set_content_fit(Gtk.ContentFit.COVER)
    pic.set_size_request(TILE_W, TILE_H)
    pic.set_can_shrink(True)
    return pic


def _load_external_thumbnail(path: str) -> Gtk.Widget | None:
    """Render risky formats in a helper so loader crashes stay isolated."""
    cache_path = _thumbnail_cache_path(path)
    if cache_path is None:
        return None
    if cache_path.is_file():
        pic = _picture_from_texture_file(cache_path)
        if pic is not None:
            return pic
        try:
            cache_path.unlink()
        except OSError:
            return None
    if not THUMBNAIL_HELPER.is_file():
        print(f"appearance: thumbnail helper missing: {THUMBNAIL_HELPER}",
              file=sys.stderr)
        return None
    try:
        subprocess.run(
            [str(THUMBNAIL_HELPER), path, str(cache_path), str(THUMB_MAX)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=THUMBNAIL_TIMEOUT_SECONDS,
            check=True,
        )
    except subprocess.TimeoutExpired:
        print(f"appearance: thumbnail helper timed out for {path}",
              file=sys.stderr)
        return None
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        detail = f": {stderr.strip()}" if stderr.strip() else f": {exc}"
        print(f"appearance: thumbnail helper failed for {path}{detail}",
              file=sys.stderr)
        return None
    if not cache_path.is_file():
        return None
    return _picture_from_texture_file(cache_path)


def _load_thumbnail(path: str) -> Gtk.Widget | None:
    """Load an image as a scaled thumbnail.

    Uses GdkPixbuf's scale-during-decode so large wallpapers don't blow
    through memory. Risky formats are decoded in a helper process and
    cached as PNG so native loader failures cannot crash Settings.
    """
    if Path(path).suffix.lower() in RISKY_THUMBNAIL_EXTS:
        return _load_external_thumbnail(path) or _thumbnail_placeholder()
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, THUMB_MAX, THUMB_MAX)
    except Exception as exc:  # GLib.Error, etc.
        print(f"appearance: thumbnail load failed for {path}: {exc}", file=sys.stderr)
        return _thumbnail_placeholder()
    texture = Gdk.Texture.new_for_pixbuf(pixbuf)
    pic = Gtk.Picture.new_for_paintable(texture)
    pic.set_content_fit(Gtk.ContentFit.COVER)
    pic.set_size_request(TILE_W, TILE_H)
    pic.set_can_shrink(True)
    return pic


PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")


class AppearancePage(BasePage, Adw.PreferencesPage):
    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._wallpaper_flow: Gtk.FlowBox | None = None
        self._wallpaper_buttons: list[tuple[Gtk.ToggleButton, str, Gtk.Widget]] = []
        # Re-entry guard for accent & wallpaper pickers. Both handlers
        # emulate radio-button semantics by calling set_active(False)
        # on sibling buttons, but set_active re-fires `toggled`, which
        # re-enters the handler. Without this guard, a single user
        # click recurses forever: sibling goes off -> its handler
        # force-reactivates it -> that handler deactivates the newly-
        # clicked tile -> its handler force-reactivates, etc.
        self._group_updating: bool = False
        self._wallpaper_refresh_source: int | None = None

    @property
    def search_keywords(self):
        return [
            (_("Theme"), _("Light")), (_("Theme"), _("Dark")),
            (_("Accent color"), _("Color")),
            (_("Font size"), _("Font")),
            (_("Wallpaper"), _("Background")),
        ]

    def build(self):
        # -- Group 1: Theme --
        theme_group = Adw.PreferencesGroup()
        theme_group.set_title(_("Theme"))

        hc_active = self.store.get("high_contrast", False)
        dark_row = Adw.SwitchRow()
        dark_row.set_title(_("Dark mode"))
        # Reflect High Contrast's forced-dark state in the UI — otherwise
        # the switch would show "light" while the applied theme is dark.
        dark_row.set_active(
            self.store.get("theme", "light") == "dark" or hc_active)

        def _on_dark_mode(row, _pspec):
            self.store.save_and_apply("theme", "dark" if row.get_active() else "light")
            self._queue_wallpaper_refresh()

        if hc_active:
            # High Contrast forces dark — disable the switch and surface
            # the reason in the group description. Only connect the
            # notify::active handler when HC is off, so toggling can't
            # silently write theme="light" while HC keeps the effective
            # theme dark (which would then flip light unexpectedly when
            # the user disables HC later).
            dark_row.set_sensitive(False)
            theme_group.set_description(
                _("Theme is set to Dark by High Contrast mode"))
        else:
            dark_row.connect("notify::active", _on_dark_mode)
        theme_group.add(dark_row)

        self.add(theme_group)

        # -- Group 2: Accent color --
        accent_group = Adw.PreferencesGroup()
        accent_group.set_title(_("Accent color"))
        accent_group.set_description(PANEL_RESTART_NOTICE)

        accent_flow = Gtk.FlowBox()
        accent_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        accent_flow.set_max_children_per_line(9)
        accent_flow.set_min_children_per_line(3)
        accent_flow.set_homogeneous(True)
        accent_flow.set_column_spacing(8)
        accent_flow.set_row_spacing(8)
        accent_flow.set_valign(Gtk.Align.CENTER)
        accent_flow.set_halign(Gtk.Align.CENTER)
        accent_flow.add_css_class("accent-swatch-grid")
        accent_buttons: list[Gtk.ToggleButton] = []
        current_accent = self.store.get("accent", "blue")

        def _on_accent_toggled(btn, name):
            # Re-entry guard: sibling set_active(False) below re-fires
            # this handler on each deselected button. Without the guard,
            # each of those re-entries would force the sibling back on
            # and then recursively deselect the freshly-clicked tile,
            # creating an unbounded signal loop that crashes the page.
            if self._group_updating:
                return
            self._group_updating = True
            try:
                if not btn.get_active():
                    # Single-selection group — no accent is never valid.
                    # Force the button back on so the UI can't drift
                    # away from settings.json.
                    btn.set_active(True)
                    return
                for other in accent_buttons:
                    if other is not btn and other.get_active():
                        other.set_active(False)
                self.store.save_and_apply("accent", name, mode="waybar")
                self.event_bus.publish("accent-changed", name)
            finally:
                self._group_updating = False

        for name in _load_accent_names():
            display_name = _accent_display_name(name)
            btn = Gtk.ToggleButton()
            btn.add_css_class("accent-swatch")
            btn.add_css_class(f"accent-{name}")
            btn.set_size_request(44, 44)
            check_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check_icon.set_pixel_size(16)
            btn.set_child(check_icon)
            # Tooltip doubles as the accessible name for GTK4 widgets
            # that don't otherwise carry a label. Without it Orca reads
            # each circle as "toggle button" with no way for a vision-
            # impaired user to distinguish Blue from Red.
            btn.set_tooltip_text(display_name)
            try:
                btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [display_name])
            except Exception:
                # update_property is GTK 4.10+; on older GTK tooltip
                # fallback still provides the accessible name.
                pass
            btn.set_active(name == current_accent)
            btn.connect("toggled", _on_accent_toggled, name)
            accent_buttons.append(btn)
            accent_flow.append(btn)

        # Wrap in a bare PreferencesRow (parent of ActionRow) so the
        # group's boxed-list card styling still frames the picker, but
        # the FlowBox is the row's full-width child rather than an
        # ActionRow suffix — suffixes pin to the row's trailing edge
        # and would cluster the nine circles on the right.
        accent_row = Adw.PreferencesRow()
        accent_row.set_activatable(False)
        accent_row.set_child(accent_flow)
        accent_group.add(accent_row)

        self.add(accent_group)

        # -- Group 3: Font size --
        font_group = Adw.PreferencesGroup()
        font_group.set_title(_("Font size"))

        font_sizes = [("10", _("Small")), ("11", _("Default")), ("13", _("Large")), ("15", _("Larger"))]
        font_labels = [label for _, label in font_sizes]
        font_values = [val for val, _ in font_sizes]

        font_row = Adw.ComboRow()
        font_row.set_title(_("Font size"))
        font_row.set_subtitle(_("Affects all text throughout the interface"))
        font_row.set_model(Gtk.StringList.new(font_labels))

        current_font = str(self.store.get("font_size", 11))
        try:
            font_row.set_selected(font_values.index(current_font))
        except ValueError:
            font_row.set_selected(1)

        def _on_font_size(row, _pspec):
            idx = row.get_selected()
            if 0 <= idx < len(font_values):
                self.store.save_and_apply("font_size", int(font_values[idx]))

        font_row.connect("notify::selected", _on_font_size)
        font_group.add(font_row)

        self.add(font_group)

        # -- Group 4: Wallpaper --
        # Built inside a try/except so a broken manifest or thumbnail never
        # takes down the whole Appearance page.
        wallpaper_group = Adw.PreferencesGroup()
        wallpaper_group.set_title(_("Wallpaper"))

        try:
            flow = Gtk.FlowBox()
            flow.set_max_children_per_line(6)
            flow.set_min_children_per_line(1)
            flow.set_selection_mode(Gtk.SelectionMode.NONE)
            flow.set_homogeneous(True)
            flow.set_column_spacing(12)
            flow.set_row_spacing(12)
            flow.add_css_class("wallpaper-grid")
            self._wallpaper_flow = flow
            self._safe_populate_wallpapers(wallpaper_group)

            # Bare PreferencesRow (not ActionRow) keeps the group's
            # boxed-list card styling while letting the grid fill the
            # row's full width. ActionRow's add_suffix pins the grid
            # to the trailing edge, clustering wallpaper tiles on the
            # right with empty space on the left — same reasoning as
            # the accent picker above.
            wallpaper_row = Adw.PreferencesRow()
            wallpaper_row.set_activatable(False)
            wallpaper_row.set_child(flow)
            wallpaper_group.add(wallpaper_row)
        except Exception as exc:
            print(f"appearance: wallpaper grid failed: {exc!r}", file=sys.stderr)
            wallpaper_group.set_description(_("Wallpaper picker unavailable"))

        self.add(wallpaper_group)

        # Tear down event-bus subscriptions and pending idle refreshes
        # when the page is destroyed.
        self.setup_cleanup(self)
        self.connect("unrealize", lambda _widget: self._cancel_wallpaper_refresh())
        return self

    # ── Wallpaper grid ────────────────────────────────────────────────────

    def _cancel_wallpaper_refresh(self) -> None:
        if self._wallpaper_refresh_source is not None:
            GLib.source_remove(self._wallpaper_refresh_source)
            self._wallpaper_refresh_source = None

    def _queue_wallpaper_refresh(self) -> None:
        """Refresh theme-dependent wallpaper thumbnails outside signal delivery."""
        if (
            self._wallpaper_flow is None
            or self._wallpaper_refresh_source is not None
        ):
            return

        def _refresh() -> int:
            self._wallpaper_refresh_source = None
            self._safe_populate_wallpapers(self)
            return GLib.SOURCE_REMOVE

        self._wallpaper_refresh_source = GLib.idle_add(_refresh)

    def _safe_populate_wallpapers(self, page: Gtk.Widget) -> None:
        try:
            self._populate_wallpapers(page)
        except Exception as exc:
            print(f"appearance: wallpaper refresh failed: {exc!r}", file=sys.stderr)

    def _populate_wallpapers(self, page: Gtk.Widget) -> None:
        flow = self._wallpaper_flow
        if flow is None:
            return

        while (child := flow.get_first_child()) is not None:
            flow.remove(child)
        self._wallpaper_buttons = []

        theme = "dark" if self.store.get("theme", "light") == "dark" else "light"
        current_raw = self.store.get("wallpaper", "")
        current = current_raw if isinstance(current_raw, str) else ""

        try:
            wallpapers = list_wallpapers()
        except Exception as exc:
            print(f"appearance: wallpaper list failed: {exc!r}", file=sys.stderr)
            wallpapers = []
        if not current.startswith("/"):
            wp = next((candidate for candidate in wallpapers
                       if candidate.id == current), None)
            if wp is None and current == "fedora-default":
                fedora_defaults = [
                    candidate for candidate in wallpapers
                    if candidate.id.startswith("f")
                    and candidate.name.lower().startswith("fedora ")
                    and "default" in candidate.name.lower()
                ]
                if fedora_defaults:
                    wp = sorted(
                        fedora_defaults,
                        key=lambda candidate: candidate.id,
                        reverse=True,
                    )[0]
            if wp is not None:
                current = wp.id
        # Map a stored absolute path (legacy settings) onto the matching manifest ID
        # so its tile shows as selected after migration.
        if current.startswith("/"):
            for wp in wallpapers:
                if current in (wp.light_path, wp.dark_path):
                    current = wp.id
                    break

        for wp in wallpapers:
            tile = self._make_wallpaper_tile(wp, current, theme, page)
            if tile is not None:
                flow.append(tile)

        flow.append(self._make_add_tile(page))

    def _make_wallpaper_tile(
        self, wp: Wallpaper, current_id: str, theme: str, page: Gtk.Widget,
    ) -> Gtk.Widget | None:
        pic = _load_thumbnail(wp.path_for_theme(theme))
        if pic is None:
            return None

        btn = Gtk.ToggleButton()
        btn.add_css_class("wallpaper-tile")
        btn.set_child(pic)
        btn.set_active(wp.id == current_id)
        btn.set_tooltip_text(wp.name)
        # Accessible label so Orca announces the wallpaper name — without
        # it each tile reads as an anonymous "toggle button" since the
        # ToggleButton's only child is a Gtk.Picture with no label text.
        try:
            btn.update_property([Gtk.AccessibleProperty.LABEL], [wp.name])
        except Exception:
            # update_property requires GTK 4.10+; tooltip fallback still
            # provides the accessible name on older GTK builds.
            pass
        btn.connect("toggled", self._on_wallpaper_toggled, wp.id)

        overlay = Gtk.Overlay()
        overlay.set_child(btn)

        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.add_css_class("wallpaper-check")
        check.set_pixel_size(16)
        check.set_halign(Gtk.Align.END)
        check.set_valign(Gtk.Align.END)
        check.set_margin_end(8)
        check.set_margin_bottom(8)
        check.set_can_target(False)
        check.set_visible(btn.get_active())
        overlay.add_overlay(check)

        self._wallpaper_buttons.append((btn, wp.id, check))

        if not wp.is_custom:
            return overlay

        # Custom tiles show an always-visible × badge in the top-right corner.
        remove = Gtk.Button.new_from_icon_name("window-close-symbolic")
        remove.add_css_class("wallpaper-remove")
        remove.set_halign(Gtk.Align.END)
        remove.set_valign(Gtk.Align.START)
        remove.set_margin_top(6)
        remove.set_margin_end(6)
        remove.set_tooltip_text(_("Remove"))
        try:
            remove.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [_("Remove {name}").format(name=wp.name)],
            )
        except Exception:
            pass
        remove.connect("clicked", self._on_remove_custom, wp.id, page)
        overlay.add_overlay(remove)
        return overlay

    def _make_add_tile(self, page: Gtk.Widget) -> Gtk.Widget:
        btn = Gtk.Button()
        btn.add_css_class("wallpaper-add")
        btn.set_tooltip_text(_("Add picture…"))
        # Accessible label so Orca announces "Add picture" instead of an
        # anonymous "button" — the button's only child is a + icon with
        # no text label.
        try:
            btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Add picture…")])
        except Exception:
            pass
        btn.set_size_request(TILE_W, TILE_H)
        icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
        icon.set_pixel_size(24)
        btn.set_child(icon)
        btn.connect("clicked", self._on_custom_clicked, page)
        return btn

    def _on_wallpaper_toggled(self, btn: Gtk.ToggleButton, wp_id: str) -> None:
        # Same re-entry pattern as the accent handler — sibling
        # set_active(False) calls re-fire this handler, so gate the
        # entire body behind _group_updating to prevent recursion.
        if self._group_updating:
            return
        self._group_updating = True
        try:
            if not btn.get_active():
                # Single-selection group — force the active-tile click
                # back on.
                btn.set_active(True)
                return
            for other_btn, _id, _check in self._wallpaper_buttons:
                if other_btn is not btn and other_btn.get_active():
                    other_btn.set_active(False)
            self.store.save_and_apply("wallpaper", wp_id)
        finally:
            self._group_updating = False
            self._sync_wallpaper_selection()

    def _sync_wallpaper_selection(self) -> None:
        for btn, _id, check in self._wallpaper_buttons:
            check.set_visible(btn.get_active())

    def _on_custom_clicked(self, _btn: Gtk.Button, page: Gtk.Widget) -> None:
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Choose Wallpaper"))
        image_filter = Gtk.FileFilter()
        image_filter.set_name(_("Images"))
        # Keep the filter patterns in sync with what add_custom will
        # actually accept (wallpapers._CUSTOM_WALLPAPER_ALLOWED_TYPES
        # sniffs MIME via Gio, but file dialogs only filter by pattern).
        # Previously the dialog only offered jpg/jpeg/png/webp/svg, so
        # users couldn't even select a JXL, BMP, TIFF, AVIF, or HEIF
        # file that add_custom would otherwise happily accept.
        for ext in (
            "*.jpg", "*.jpeg", "*.png", "*.webp", "*.svg",
            "*.bmp", "*.tiff", "*.tif", "*.jxl",
            "*.avif", "*.heif", "*.heic",
        ):
            image_filter.add_pattern(ext)
        # Matching MIME types let Flatpak portals that don't honour
        # glob patterns (rare but possible) still include our formats.
        for mime in (
            "image/jpeg", "image/png", "image/webp", "image/svg+xml",
            "image/bmp", "image/tiff", "image/jxl",
            "image/avif", "image/heif", "image/heic",
        ):
            image_filter.add_mime_type(mime)
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(image_filter)
        dialog.set_filters(filters)

        def _on_open_finish(d, result):
            try:
                file = d.open_finish(result)
            except Exception:
                return
            if file is None:
                return
            source = file.get_path()
            if not source:
                return
            status, wp = add_custom_detailed(source)
            if status != ADD_CUSTOM_OK or wp is None:
                # Give the user a reason specific enough to act on.
                # A generic "could not add wallpaper" left them
                # guessing whether the file was too big, wrong
                # format, or an I/O glitch.
                messages = {
                    ADD_CUSTOM_MISSING:
                        _("Picture not found"),
                    ADD_CUSTOM_TOO_LARGE:
                        _("Picture is too large (50 MB limit)"),
                    ADD_CUSTOM_UNSUPPORTED:
                        _("Picture format not supported"),
                    ADD_CUSTOM_IO_ERROR:
                        _("Could not add wallpaper"),
                }
                self.store.show_toast(
                    messages.get(status, _("Could not add wallpaper")),
                    True,
                )
                return
            self.store.save_and_apply("wallpaper", wp.id)
            self._safe_populate_wallpapers(page)

        dialog.open(self._get_window(page), None, _on_open_finish)

    def _on_remove_custom(self, _btn: Gtk.Button, wp_id: str, page: Gtk.Widget) -> None:
        if not remove_custom(wp_id):
            return
        if self.store.get("wallpaper", "") == wp_id:
            defaults = self.store.get_defaults()
            self.store.save_and_apply("wallpaper", defaults.get("wallpaper", ""))
        self._safe_populate_wallpapers(page)

    @staticmethod
    def _get_window(widget):
        root = widget.get_root()
        return root if isinstance(root, Gtk.Window) else None
