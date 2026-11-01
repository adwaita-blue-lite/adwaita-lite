import copy
import json
import re
import shlex
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gio, GLib, Gtk

from ..base import BasePage

MODULE_NAMES = {
    "custom/launcher": _("Apps"), "wlr/taskbar": _("Window list"),
    "pulseaudio": _("Volume"), "backlight": _("Brightness"), "battery": _("Battery"),
    "clock": _("Clock"), "tray": _("System tray"),
}

_DEFAULTS_PATH = Path("/usr/share/adwaita-lite/defaults/settings.json")

def _load_default_layout():
    try:
        data = json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("defaults root is not an object")
        layout = data.get("layout")
        if isinstance(layout, dict) and all(
            k in layout and isinstance(layout[k], list) for k in ("start", "center", "end")
        ):
            return layout
    except (OSError, json.JSONDecodeError, KeyError, ValueError):
        pass
    return {
        "start": ["custom/launcher"],
        "center": ["wlr/taskbar"],
        "end": ["pulseaudio", "backlight", "battery", "clock", "tray"],
    }

DEFAULT_LAYOUT = _load_default_layout()
VALID_MODULES = set(MODULE_NAMES) | {
    module for modules in DEFAULT_LAYOUT.values() for module in modules
}
HORIZONTAL_LABELS = {"start": _("Left"), "center": _("Center"), "end": _("Right")}
VERTICAL_LABELS = {"start": _("Top"), "center": _("Center"), "end": _("Bottom")}
SECTION_ORDER = ["start", "center", "end"]

EDGE_OPTIONS: list[tuple[str, str]] = [
    ("bottom", _("Bottom")),
    ("top", _("Top")),
    ("left", _("Left")),
    ("right", _("Right")),
]

DENSITY_OPTIONS: list[tuple[str, str]] = [
    ("normal", _("Normal")),
    ("compact", _("Compact")),
]

PANEL_RESTART_NOTICE = _("Panel changes apply after you restart your session.")


class PanelPage(BasePage, Adw.PreferencesPage):
    """Panel position, density, twilight, module layout, and pinned apps.

    Returns an AdwNavigationView from build() so the Add Pinned App
    picker can push a sub-page over the top-level preferences content.
    The module-layout editor renders as three stacked AdwPreferencesGroups
    (one per section — Left/Center/Right horizontally, Top/Middle/Bottom
    vertically) with each module as an AdwActionRow carrying arrow
    suffix buttons for up/down and prev/next-section movement.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._layout_data: dict = {}
        self._section_groups: dict[str, Adw.PreferencesGroup] = {}
        self._section_rows: dict[str, list[Adw.ActionRow]] = {}
        self._pinned_data: list = []
        self._pinned_group: Adw.PreferencesGroup | None = None
        self._pinned_rows: list[Adw.ActionRow] = []
        self._nav: Adw.NavigationView | None = None
        self._module_refresh_source: int | None = None
        self._pinned_refresh_source: int | None = None
        self._updating: bool = False
        self._built: bool = False

    @property
    def search_keywords(self):
        return [
            (_("Position"), _("Panel")), (_("Density"), _("Compact")),
            (_("Twilight"), _("Invert")),
            (_("Module Layout"), _("Modules")), (_("Pinned Apps"), _("Pinned")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        self.add(self._build_position_group())
        self.add(self._build_density_group())
        self.add(self._build_twilight_group())
        for group in self._build_module_layout_groups():
            self.add(group)
        self.add(self._build_layout_reset_group())
        self.add(self._build_pinned_apps_group())

        # Wrap the preferences page in a NavigationView so the Add
        # Pinned App picker can push a sub-page. Back button + Escape
        # are handled natively by AdwNavigationView.
        self._nav = Adw.NavigationView()
        root_page = Adw.NavigationPage()
        root_page.set_title(_("Panel"))
        root_page.set_child(self)
        self._nav.add(root_page)

        # Tear down event-bus subscriptions when the nav (our outermost
        # widget) is destroyed. Attaching to self would fire on every
        # sub-page push (the PreferencesPage unmaps during nav-view
        # navigation) and permanently silence the page's subscriptions.
        self.setup_cleanup(self._nav)
        self._nav.connect("unrealize", lambda _widget: self._cancel_pending_refreshes())
        self._built = True
        return self._nav

    # -- Position / Density / Twilight ---------------------------------

    def _build_position_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Position"))
        group.set_description(PANEL_RESTART_NOTICE)

        row = Adw.ComboRow()
        row.set_title(_("Panel position"))

        labels = [label for _v, label in EDGE_OPTIONS]
        values = [v for v, _label in EDGE_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self.store.get("edge", "bottom")
        row.set_selected(values.index(current) if current in values else 0)

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self._on_edge_changed(values[idx])

        row.connect("notify::selected", _on_selected)
        group.add(row)
        return group

    def _build_density_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Density"))

        row = Adw.ComboRow()
        row.set_title(_("Panel density"))

        labels = [label for _v, label in DENSITY_OPTIONS]
        values = [v for v, _label in DENSITY_OPTIONS]
        row.set_model(Gtk.StringList.new(labels))

        current = self.store.get("density", "normal")
        row.set_selected(values.index(current) if current in values else 0)

        def _on_selected(r: Adw.ComboRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            idx = r.get_selected()
            if 0 <= idx < len(values):
                self._on_density_changed(values[idx])

        row.connect("notify::selected", _on_selected)
        group.add(row)
        return group

    def _build_twilight_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Twilight"))

        row = Adw.SwitchRow()
        row.set_title(_("Twilight"))
        row.set_subtitle(_("Invert panel colors from the system theme"))
        row.set_active(self.store.get("panel_twilight", False))

        def _on_active(r: Adw.SwitchRow, _pspec) -> None:
            if self._updating or not self._built:
                return
            self._on_twilight_changed(r.get_active())

        row.connect("notify::active", _on_active)
        group.add(row)
        return group

    # -- Module layout -------------------------------------------------

    def _build_module_layout_groups(self) -> list[Adw.PreferencesGroup]:
        """Build three stacked AdwPreferencesGroups, one per section.

        Each group's title is edge-aware (Left/Center/Right horizontally,
        Top/Middle/Bottom vertically). Module rows are populated by
        _refresh_module_lists so arrow enable/disable state tracks layout
        changes after every move.
        """
        self._layout_data = self._load_layout()
        edge = self.store.get("edge", "bottom")
        labels = HORIZONTAL_LABELS if edge in ("top", "bottom") else VERTICAL_LABELS
        self._section_groups = {}
        self._section_rows = {}
        for section in SECTION_ORDER:
            group = Adw.PreferencesGroup()
            group.set_title(labels[section])
            self._section_groups[section] = group
            self._section_rows[section] = []
        self._refresh_module_lists()
        return list(self._section_groups.values())

    def _build_layout_reset_group(self) -> Adw.PreferencesGroup:
        """Trailing group with a destructive-action reset button."""
        group = Adw.PreferencesGroup()
        reset_row = Adw.ActionRow()
        reset_row.set_title(_("Reset layout to defaults"))
        reset_row.set_activatable(False)
        reset_btn = Gtk.Button(label=_("Reset"))
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", lambda _b: self._reset_layout())
        reset_row.add_suffix(reset_btn)
        group.add(reset_row)
        return group

    def _on_edge_changed(self, edge):
        if self._updating:
            return
        self._updating = True
        try:
            self.store.save_and_apply("edge", edge, mode="waybar")
            self._update_section_labels()
            self._refresh_module_lists()
        finally:
            self._updating = False

    def _on_twilight_changed(self, active):
        if self._updating:
            return
        self._updating = True
        try:
            self.store.save_and_apply("panel_twilight", active, mode="waybar")
        finally:
            self._updating = False

    def _on_density_changed(self, density):
        if self._updating:
            return
        self._updating = True
        try:
            self.store.save_and_apply("density", density, mode="waybar")
        finally:
            self._updating = False

    def _update_section_labels(self):
        edge = self.store.get("edge", "bottom")
        labels = HORIZONTAL_LABELS if edge in ("top", "bottom") else VERTICAL_LABELS
        for section, group in self._section_groups.items():
            group.set_title(labels[section])

    def _load_layout(self):
        saved = self.store.get("layout")
        return self._sanitize_layout(saved)

    @staticmethod
    def _sanitize_layout(raw) -> dict[str, list[str]]:
        if not (
            isinstance(raw, dict)
            and all(k in raw and isinstance(raw[k], list) for k in SECTION_ORDER)
        ):
            return copy.deepcopy(DEFAULT_LAYOUT)

        layout = {section: [] for section in SECTION_ORDER}
        seen: set[str] = set()
        for section in SECTION_ORDER:
            for module in raw[section]:
                if (
                    isinstance(module, str)
                    and module in VALID_MODULES
                    and module not in seen
                ):
                    layout[section].append(module)
                    seen.add(module)

        for section in SECTION_ORDER:
            for module in DEFAULT_LAYOUT.get(section, []):
                if module in VALID_MODULES and module not in seen:
                    layout[section].append(module)
                    seen.add(module)
        return layout

    @staticmethod
    def _sanitize_pinned(raw) -> list[dict]:
        if not isinstance(raw, list):
            return []
        pinned: list[dict] = []
        for app in raw:
            if not isinstance(app, dict):
                continue
            command = str(app.get("command", "")).strip()
            if not command:
                continue
            name = str(app.get("name", "")).strip() or command
            icon = str(app.get("icon", "")).strip() or "application-x-executable-symbolic"
            pin = {"name": name, "command": command, "icon": icon}
            for key in ("desktop_id", "app_id", "startup_wm_class"):
                value = str(app.get(key, "")).strip()
                if value:
                    pin[key] = value
            pinned.append(pin)
        return pinned

    @staticmethod
    def _identity_fields_from_app_info(app_info, command: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        desktop_id = ""
        get_id = getattr(app_info, "get_id", None)
        if callable(get_id):
            desktop_id = str(get_id() or "").strip()
        if desktop_id:
            fields["desktop_id"] = desktop_id
            if desktop_id.endswith(".desktop"):
                fields["app_id"] = desktop_id[:-8]

        get_startup_wm_class = getattr(app_info, "get_startup_wm_class", None)
        if callable(get_startup_wm_class):
            startup_wm_class = str(get_startup_wm_class() or "").strip()
            if startup_wm_class:
                fields["startup_wm_class"] = startup_wm_class

        try:
            parts = shlex.split(command)
        except ValueError:
            parts = []
        if "run" in parts:
            run_idx = parts.index("run")
            for part in parts[run_idx + 1:]:
                if part == "--" or part.startswith("-"):
                    continue
                if "." in part:
                    fields.setdefault("app_id", part)
                    break
        return fields

    def _refresh_module_lists(self):
        for section, group in self._section_groups.items():
            # Remove all currently-tracked rows from the group.
            for row in self._section_rows.get(section, []):
                group.remove(row)
            self._section_rows[section] = []

            modules = self._layout_data.get(section, [])
            for idx, mod_key in enumerate(modules):
                row = self._build_module_row(mod_key, section, idx, len(modules))
                group.add(row)
                self._section_rows[section].append(row)

    def _cancel_module_refresh(self) -> None:
        if self._module_refresh_source is not None:
            GLib.source_remove(self._module_refresh_source)
            self._module_refresh_source = None

    def _cancel_pending_refreshes(self) -> None:
        self._cancel_module_refresh()
        self._cancel_pinned_refresh()

    def _queue_module_refresh(self) -> None:
        """Rebuild module rows after the current GTK signal unwinds."""
        if self._module_refresh_source is not None:
            return

        def _refresh() -> int:
            self._module_refresh_source = None
            self._refresh_module_lists()
            return GLib.SOURCE_REMOVE

        self._module_refresh_source = GLib.idle_add(_refresh)

    def _build_module_row(self, mod_key, section, idx, total):
        row = Adw.ActionRow()
        row.set_title(MODULE_NAMES.get(mod_key, mod_key))
        row.set_activatable(False)

        edge = self.store.get("edge", "bottom")
        is_horizontal = edge in ("top", "bottom")
        labels = HORIZONTAL_LABELS if is_horizontal else VERTICAL_LABELS
        # Cross-section icons follow panel orientation: horizontal
        # panel -> horizontal arrows between Left/Center/Right sections;
        # vertical panel -> vertical arrows between Top/Middle/Bottom.
        prev_icon = "go-previous-symbolic" if is_horizontal else "go-up-symbolic"
        next_icon = "go-next-symbolic" if is_horizontal else "go-down-symbolic"

        sec_idx = SECTION_ORDER.index(section)
        can_up = idx > 0
        can_down = idx < total - 1
        can_prev_section = sec_idx > 0
        can_next_section = sec_idx < len(SECTION_ORDER) - 1

        if can_up:
            up_btn = Gtk.Button.new_from_icon_name("go-up-symbolic")
            up_btn.add_css_class("flat")
            up_btn.set_valign(Gtk.Align.CENTER)
            up_tip = _("Move up in section")
            up_btn.set_tooltip_text(up_tip)
            # Accessible label so Orca announces the arrow-button purpose
            # — icon-only Gtk.Buttons have no intrinsic label.
            try:
                up_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [up_tip])
            except Exception:
                pass
            up_btn.connect(
                "clicked",
                lambda _b, k=mod_key, s=section: self._reorder_module(k, s, -1),
            )
            row.add_suffix(up_btn)
        if can_down:
            down_btn = Gtk.Button.new_from_icon_name("go-down-symbolic")
            down_btn.add_css_class("flat")
            down_btn.set_valign(Gtk.Align.CENTER)
            down_tip = _("Move down in section")
            down_btn.set_tooltip_text(down_tip)
            try:
                down_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [down_tip])
            except Exception:
                pass
            down_btn.connect(
                "clicked",
                lambda _b, k=mod_key, s=section: self._reorder_module(k, s, 1),
            )
            row.add_suffix(down_btn)
        if can_prev_section:
            prev_btn = Gtk.Button.new_from_icon_name(prev_icon)
            prev_btn.add_css_class("flat")
            prev_btn.set_valign(Gtk.Align.CENTER)
            prev_tip = _("Move to {section}").format(
                section=labels[SECTION_ORDER[sec_idx - 1]])
            prev_btn.set_tooltip_text(prev_tip)
            try:
                prev_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [prev_tip])
            except Exception:
                pass
            prev_btn.connect(
                "clicked",
                lambda _b, k=mod_key, s=section: self._move_module(
                    k, s, SECTION_ORDER[SECTION_ORDER.index(s) - 1]
                ),
            )
            row.add_suffix(prev_btn)
        if can_next_section:
            next_btn = Gtk.Button.new_from_icon_name(next_icon)
            next_btn.add_css_class("flat")
            next_btn.set_valign(Gtk.Align.CENTER)
            next_tip = _("Move to {section}").format(
                section=labels[SECTION_ORDER[sec_idx + 1]])
            next_btn.set_tooltip_text(next_tip)
            try:
                next_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [next_tip])
            except Exception:
                pass
            next_btn.connect(
                "clicked",
                lambda _b, k=mod_key, s=section: self._move_module(
                    k, s, SECTION_ORDER[SECTION_ORDER.index(s) + 1]
                ),
            )
            row.add_suffix(next_btn)

        return row

    def _reorder_module(self, mod_key, section, direction):
        if self._updating:
            return
        self._updating = True
        try:
            modules = self._layout_data.get(section, [])
            if mod_key not in modules:
                return
            idx = modules.index(mod_key)
            new_idx = idx + direction
            if 0 <= new_idx < len(modules):
                modules[idx], modules[new_idx] = modules[new_idx], modules[idx]
                self._queue_module_refresh()
                self.store.save_and_apply("layout", self._layout_data, mode="waybar")
        finally:
            self._updating = False

    def _move_module(self, mod_key, from_section, to_section):
        if self._updating:
            return
        self._updating = True
        try:
            modules = self._layout_data.get(from_section, [])
            if mod_key not in modules:
                return
            modules.remove(mod_key)
            self._layout_data.setdefault(to_section, []).append(mod_key)
            self._queue_module_refresh()
            self.store.save_and_apply("layout", self._layout_data, mode="waybar")
        finally:
            self._updating = False

    def _reset_layout(self):
        if self._updating:
            return
        self._updating = True
        try:
            self._layout_data = copy.deepcopy(DEFAULT_LAYOUT)
            self._queue_module_refresh()
            self.store.save_and_apply("layout", self._layout_data, mode="waybar")
        finally:
            self._updating = False
        # Pinned apps are not affected by layout reset

    # -- Pinned apps ---------------------------------------------------

    def _build_pinned_apps_group(self) -> Adw.PreferencesGroup:
        raw = self.store.get("pinned", [])
        self._pinned_data = self._sanitize_pinned(raw)

        group = Adw.PreferencesGroup()
        group.set_title(_("Pinned Apps"))

        add_btn = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_btn.add_css_class("flat")
        add_btn.set_tooltip_text(_("Add pinned app"))
        try:
            add_btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Add pinned app")]
            )
        except Exception:
            pass
        add_btn.connect("clicked", lambda _b: self._push_add_pinned_page())
        group.set_header_suffix(add_btn)

        self._pinned_group = group
        self._refresh_pinned_list()
        return group

    def _refresh_pinned_list(self):
        group = self._pinned_group
        if group is None:
            return

        # Remove existing pinned rows. Only our cached rows so future
        # siblings (group description etc.) aren't touched.
        for row in self._pinned_rows:
            group.remove(row)
        self._pinned_rows = []

        if not self._pinned_data:
            group.set_description(_("No pinned apps"))
            return
        group.set_description("")

        for idx, app in enumerate(self._pinned_data):
            row = self._build_pinned_row(app, idx)
            group.add(row)
            self._pinned_rows.append(row)

    def _cancel_pinned_refresh(self) -> None:
        if self._pinned_refresh_source is not None:
            GLib.source_remove(self._pinned_refresh_source)
            self._pinned_refresh_source = None

    def _queue_pinned_refresh(self) -> None:
        """Rebuild pinned rows after the current GTK signal unwinds."""
        if self._pinned_refresh_source is not None:
            return

        def _refresh() -> int:
            self._pinned_refresh_source = None
            self._refresh_pinned_list()
            return GLib.SOURCE_REMOVE

        self._pinned_refresh_source = GLib.idle_add(_refresh)

    def _build_pinned_row(self, app, idx):
        row = Adw.ActionRow()
        row.set_use_markup(False)
        row.set_title(app.get("name", app.get("command", _("Unknown"))))

        icon = Gtk.Image.new_from_icon_name(
            app.get("icon", "application-x-executable-symbolic"))
        icon.set_pixel_size(20)
        row.add_prefix(icon)

        remove_btn = Gtk.Button(label=_("Remove"))
        remove_btn.add_css_class("flat")
        remove_btn.set_valign(Gtk.Align.CENTER)
        remove_btn.connect("clicked", lambda _b, i=idx: self._remove_pinned(i))
        row.add_suffix(remove_btn)
        return row

    def _remove_pinned(self, idx):
        if 0 <= idx < len(self._pinned_data):
            self._pinned_data.pop(idx)
            self._queue_pinned_refresh()
            self.store.save_and_apply("pinned", self._pinned_data, mode="waybar")

    # -- Add-pinned sub-page -------------------------------------------

    def _push_add_pinned_page(self):
        if self._nav is None:
            return

        sub = Adw.NavigationPage()
        sub.set_title(_("Add Pinned App"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()  # automatic back button in collapsed mode
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

        inner = Adw.PreferencesPage()

        # Search group: single AdwEntryRow used as a filter driver. No
        # apply side-effects — we just watch `notify::text` to
        # invalidate the apps group filter.
        search_group = Adw.PreferencesGroup()
        search_row = Adw.EntryRow()
        search_row.set_title(_("Search apps"))
        search_group.add(search_row)
        inner.add(search_group)

        # Apps group populated from Gio.AppInfo.get_all(). Each row is
        # an AdwActionRow with an icon prefix and an Add button suffix
        # that calls _add_app_from_info + pops the nav page.
        apps_group = Adw.PreferencesGroup()
        apps_group.set_title(_("Applications"))
        inner.add(apps_group)

        apps = [a for a in Gio.AppInfo.get_all() if a.should_show()]
        apps.sort(key=lambda a: a.get_display_name().lower())

        app_rows: list[tuple[Adw.ActionRow, str]] = []

        for app in apps:
            row = Adw.ActionRow()
            row.set_use_markup(False)
            row.set_title(app.get_display_name())

            icon_info = app.get_icon()
            if icon_info is not None:
                icon_widget = Gtk.Image.new_from_gicon(icon_info)
            else:
                icon_widget = Gtk.Image.new_from_icon_name(
                    "application-x-executable-symbolic")
            icon_widget.set_pixel_size(24)
            row.add_prefix(icon_widget)

            add_btn = Gtk.Button(label=_("Add"))
            add_btn.add_css_class("suggested-action")
            add_btn.set_valign(Gtk.Align.CENTER)
            add_btn.connect(
                "clicked", lambda _b, a=app: self._on_add_app_clicked(a))
            row.add_suffix(add_btn)

            apps_group.add(row)
            app_rows.append((row, app.get_display_name().lower()))

        def _on_search_changed(entry: Adw.EntryRow, _pspec) -> None:
            query = entry.get_text().lower().strip()
            for row, name in app_rows:
                row.set_visible(not query or query in name)

        search_row.connect("notify::text", _on_search_changed)

        toolbar.set_content(inner)
        sub.set_child(toolbar)
        self._nav.push(sub)

    def _on_add_app_clicked(self, app_info):
        self._add_app_from_info(app_info)
        if self._nav is not None:
            self._nav.pop()

    def _add_app_from_info(self, app_info):
        name = app_info.get_display_name()
        cmd = re.sub(r'\s*%[uUfFdDnNickvm]', '', app_info.get_commandline() or "").strip()
        if not cmd:
            self.store.show_toast(
                _("{app} has no launch command").format(app=name), True)
            return

        # Normalize shell quoting so paths with spaces survive a round-trip
        # through waybar's shell-exec consumer. Unparseable quoting (e.g.
        # a stray single quote in a hand-edited .desktop Exec line) falls
        # back to the raw string rather than dropping the entry — worst
        # case it launches a little oddly, best case the user can still
        # fix it from the Pinned Apps UI.
        try:
            tokens = shlex.split(cmd)
            if tokens:
                cmd = shlex.join(tokens)
        except ValueError:
            pass

        icon_gicon = app_info.get_icon()
        icon = ""
        if icon_gicon is not None:
            # Prefer simple themed-icon names (first name in a GThemedIcon) over
            # the full GIcon serialization — downstream waybar and Gtk.Image
            # both accept icon *names*, not serialized GIcon strings.
            if isinstance(icon_gicon, Gio.ThemedIcon):
                names = icon_gicon.get_names() or []
                icon = names[0] if names else ""
            elif isinstance(icon_gicon, Gio.FileIcon):
                f = icon_gicon.get_file()
                icon = f.get_path() if f else ""
            else:
                icon = icon_gicon.to_string() or ""
        if not icon:
            icon = "application-x-executable-symbolic"

        pin = {"name": name, "command": cmd, "icon": icon}
        pin.update(self._identity_fields_from_app_info(app_info, cmd))
        self._pinned_data.append(pin)
        self._refresh_pinned_list()
        self.store.save_and_apply("pinned", self._pinned_data, mode="waybar")
