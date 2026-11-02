import json
import os
import subprocess
import xml.etree.ElementTree as ET
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, Gdk, Gtk

from ..base import BasePage

LAYOUT_NAMES = {
    "us": _("English (US)"), "gb": _("English (UK)"), "de": _("German"),
    "fr": _("French"), "es": _("Spanish"), "it": _("Italian"),
    "pt": _("Portuguese"),
    "ru": _("Russian"), "jp": _("Japanese"), "kr": _("Korean"),
    "cn": _("Chinese"),
    "ar": _("Arabic"), "br": _("Portuguese (Brazil)"), "ca": _("Canadian"),
    "dk": _("Danish"), "fi": _("Finnish"), "nl": _("Dutch"),
    "no": _("Norwegian"),
    "pl": _("Polish"), "se": _("Swedish"), "ch": _("Swiss"),
    "tr": _("Turkish"),
    "ua": _("Ukrainian"), "in": _("Indian"), "il": _("Hebrew"),
    "th": _("Thai"),
    "cz": _("Czech"), "hu": _("Hungarian"), "ro": _("Romanian"),
    "sk": _("Slovak"),
    "hr": _("Croatian"), "si": _("Slovenian"), "bg": _("Bulgarian"),
    "gr": _("Greek"),
    "ir": _("Persian"), "et": _("Amharic"), "vn": _("Vietnamese"),
    "ke": _("Swahili (Kenya)"), "tz": _("Swahili (Tanzania)"),
    "ng": _("Nigerian"),
}

SYSTEM_RC_XML = Path("/etc/xdg/labwc/rc.xml")
USER_KEYBINDINGS = Path.home() / ".config/adwaita-lite/keybindings.json"

# Lazily populated caches for `localectl list-x11-keymap-*` output.
# Each subprocess call blocks the GTK main thread for up to 10s on cold
# xkeyboard-config reads. Caching at module scope means subsequent page
# opens within the same settings-app process reuse the first result.
_layouts_cache: list | None = None
_variants_cache: dict[str, list] = {}

# Human-readable names for action+command combos. Values wrapped so
# xgettext extracts them and the Keyboard shortcut rows render in the
# user's language instead of English-only.
SHORTCUT_NAMES = {
    ("Execute", "foot"): _("Open Terminal"),
    ("Execute", "Thunar"): _("Open File Manager"),
    ("Execute", "adwaita-lite-app-menu"): _("App Launcher"),
    ("Execute", "adwaita-lite-settings"): _("Open Settings"),
    ("Execute", "swaylock -f"): _("Lock Screen"),
    ("Execute", "xfce4-taskmanager"): _("System Monitor"),
    ("NextWindow", ""): _("Switch Windows"),
    ("PreviousWindow", ""): _("Switch Windows (Reverse)"),
    ("Close", ""): _("Close Window"),
    ("ToggleMaximize", ""): _("Maximize / Restore"),
    ("Iconify", ""): _("Minimize"),
    ("ToggleFullscreen", ""): _("Toggle Fullscreen"),
    ("SnapToEdge", "left"): _("Snap Left"),
    ("SnapToEdge", "right"): _("Snap Right"),
}

# Keys to skip in the shortcuts editor (internal bindings)
_SKIP_KEYS = {"C-F12"}

# Modifier key names that should be ignored during capture
_MODIFIER_KEYVALS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R",
    "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Meta_L", "Meta_R", "ISO_Level3_Shift", "Hyper_L", "Hyper_R",
    "Caps_Lock", "Num_Lock",
}


def _human_key_label(key_str: str) -> str:
    """Convert labwc key string like 'C-A-T' to 'Ctrl+Alt+T' for display."""
    parts = key_str.split("-")
    display = []
    for p in parts:
        if p == "C":
            display.append("Ctrl")
        elif p == "A":
            display.append("Alt")
        elif p == "S":
            display.append("Shift")
        elif p == "W":
            display.append("Super")
        elif p.startswith("XF86"):
            # Make XF86 keys readable
            name = p[4:]
            # Insert spaces before capitals
            readable = ""
            for i, ch in enumerate(name):
                if ch.isupper() and i > 0 and not name[i - 1].isupper():
                    readable += " "
                readable += ch
            display.append(readable)
        else:
            display.append(p.capitalize() if len(p) == 1 else p)
    return " + ".join(display)


def _get_action_name(action_name, command, direction):
    """Resolve a human-readable name for an action."""
    # Check SnapToEdge with direction
    if action_name == "SnapToEdge" and direction:
        key = ("SnapToEdge", direction)
        if key in SHORTCUT_NAMES:
            return SHORTCUT_NAMES[key]
        return _("Snap {direction}").format(direction=direction.capitalize())

    # Check exact match first
    key = (action_name, command)
    if key in SHORTCUT_NAMES:
        return SHORTCUT_NAMES[key]

    # Check without command for non-Execute actions
    if action_name != "Execute":
        key = (action_name, "")
        if key in SHORTCUT_NAMES:
            return SHORTCUT_NAMES[key]
        return action_name

    # For Execute actions, match by substring
    if command:
        cmd_lower = command.lower()
        if "volume up" in cmd_lower:
            return _("Volume Up")
        if "volume down" in cmd_lower:
            return _("Volume Down")
        if "volume mute" in cmd_lower:
            return _("Mute")
        if "brightness up" in cmd_lower:
            return _("Brightness Up")
        if "brightness down" in cmd_lower:
            return _("Brightness Down")
        if "grim -g" in cmd_lower:
            return _("Screenshot (Region)")
        if "grim" in cmd_lower:
            return _("Screenshot")

    return _("Run: {command}").format(command=command) if command else action_name


def _parse_system_keybindings() -> list[dict]:
    """Parse keybindings from the system rc.xml."""
    bindings = []
    try:
        tree = ET.parse(SYSTEM_RC_XML)
        root = tree.getroot()
    except (ET.ParseError, FileNotFoundError, OSError):
        return bindings

    keyboard = root.find("keyboard")
    if keyboard is None:
        return bindings

    for keybind in keyboard.findall("keybind"):
        key = keybind.get("key", "")
        if not key or key in _SKIP_KEYS:
            continue

        action_el = keybind.find("action")
        if action_el is None:
            continue

        action_name = action_el.get("name", "")
        command = action_el.get("command", "")
        menu = action_el.get("menu", "")
        direction = ""

        # Skip ShowMenu internal bindings
        if action_name == "ShowMenu":
            continue

        dir_el = action_el.find("direction")
        if dir_el is not None and dir_el.text:
            direction = dir_el.text.strip()

        display_name = _get_action_name(action_name, command, direction)

        bindings.append({
            "key": key,
            "action": action_name,
            "command": command,
            "direction": direction,
            "menu": menu,
            "display_name": display_name,
        })

    return bindings


def _load_user_keybindings() -> list[dict] | None:
    """Load user keybinding overrides. Returns None if no overrides exist.

    Validates each entry before returning. A partially-written or
    hand-edited JSON with missing "key" / "action" fields previously
    crashed the Keyboard page build via KeyError, leaving the user
    with no UI to repair it. Malformed rows are dropped with a stderr
    warning; the valid remainder is used.
    """
    if not USER_KEYBINDINGS.exists():
        return None
    try:
        data = json.loads(USER_KEYBINDINGS.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return None
        cleaned: list[dict] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            action = entry.get("action")
            if not isinstance(key, str) or not key:
                continue
            if not isinstance(action, str) or not action:
                continue
            command = entry.get("command", "")
            direction = entry.get("direction", "")
            menu = entry.get("menu", "")
            display_name = entry.get("display_name", "")
            if not isinstance(command, str):
                command = ""
            if not isinstance(direction, str):
                direction = ""
            if not isinstance(menu, str):
                menu = ""
            if not isinstance(display_name, str) or not display_name:
                display_name = _get_action_name(action, command, direction)
            cleaned.append({
                "key": key,
                "action": action,
                "command": command,
                "direction": direction,
                "menu": menu,
                "display_name": display_name,
            })
        return cleaned if cleaned else None
    except (json.JSONDecodeError, OSError):
        return None


def _save_user_keybindings(bindings: list[dict]) -> None:
    """Save keybinding overrides to JSON atomically.

    Writes to a `.tmp` sibling, fsyncs the file data, then os.replace()s
    it onto USER_KEYBINDINGS. fsync guards against a crash between write
    and rename leaving a zero-byte or truncated JSON that the next
    _load_user_keybindings treats as "no overrides".
    """
    USER_KEYBINDINGS.parent.mkdir(parents=True, exist_ok=True)
    tmp = USER_KEYBINDINGS.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(bindings, indent=2) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, USER_KEYBINDINGS)


def _clone_bindings(bindings: list[dict]) -> list[dict]:
    return [dict(binding) for binding in bindings]


class KeyboardPage(BasePage, Adw.PreferencesPage):
    """Keyboard settings: layout/variant, repeat timing, caps-lock remap,
    and per-shortcut rebinding.

    Returns an AdwNavigationView from build() because tapping a shortcut
    row pushes an AdwNavigationPage hosting an AdwStatusPage with its
    own Gtk.EventControllerKey — the capture flow lives in a sub-page
    instead of attaching to the root window.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        self._default_bindings = _parse_system_keybindings()
        user = _load_user_keybindings()
        self._bindings = (
            _clone_bindings(user)
            if user is not None else _clone_bindings(self._default_bindings)
        )
        # References populated in build(). None-safe because event
        # handlers may fire before first navigation on some paths.
        self._nav: Adw.NavigationView | None = None
        self._variant_row: Adw.ComboRow | None = None
        self._variant_codes: list[str] = []
        self._current_layout_code: str = self.store.get("keyboard_layout", "us")
        # AdwActionRow per binding. _apply_new_key / _reset_shortcut
        # update the rows' subtitles with the new human-readable label.
        self._shortcut_rows: list[Adw.ActionRow] = []
        self._shortcut_group: Adw.PreferencesGroup | None = None
        # Cached reference to each row's reset-to-default suffix button
        # (or None when absent), so we can add/remove the button as the
        # binding drifts from / returns to its default without walking
        # AdwActionRow's private child list.
        self._shortcut_reset_buttons: list[Gtk.Button | None] = []
        # Capture-state refs so we don't double-attach controllers on
        # rapid taps and can identify the right binding on key-press.
        self._capture_page: Adw.NavigationPage | None = None
        self._capture_index: int = -1
        self._capture_done: bool = False
        # Guard flag for programmatic ComboRow updates — see
        # _build_variant_dropdown. set_model/set_selected both emit
        # notify::selected while the handler is still connected, which
        # would otherwise save a spurious empty variant every time the
        # layout changes.
        self._updating_variant: bool = False

    @property
    def search_keywords(self):
        return [
            (_("Layout"), _("Keyboard layout")), (_("Layout"), _("Variant")),
            (_("Repeat"), _("Repeat delay")), (_("Repeat"), _("Repeat rate")),
            (_("Caps Lock"), _("Caps Lock behavior")), (_("Caps Lock"), _("Remap")),
            (_("Shortcuts"), _("Keyboard shortcuts")), (_("Shortcuts"), _("Keybinding")),
            (_("Shortcuts"), _("Hotkey")), (_("Shortcuts"), _("Key combo")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        self.add(self._build_layout_group())
        self.add(self._build_repeat_group())
        self.add(self._build_capslock_group())
        self.add(self._build_shortcuts_group())

        # Wrap self in a NavigationView so _push_capture_page can push
        # sub-pages. Back button, back gesture, and Escape are handled
        # natively by AdwNavigationView.
        self._nav = Adw.NavigationView()
        root_page = Adw.NavigationPage()
        root_page.set_title(_("Keyboard"))
        root_page.set_child(self)
        self._nav.add(root_page)

        # Tear down event-bus subscriptions when the nav (our outermost
        # widget) is destroyed. Attaching to self would fire on every
        # capture sub-page push (the PreferencesPage unmaps during
        # nav-view navigation) and permanently silence the page.
        self.setup_cleanup(self._nav)
        return self._nav

    # -- group builders -------------------------------------------------

    def _build_layout_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Layout"))

        layout_codes = self._get_layouts()
        display_names = [LAYOUT_NAMES.get(c, c) for c in layout_codes]
        current_layout = self.store.get("keyboard_layout", "us")
        try:
            layout_idx = layout_codes.index(current_layout)
        except ValueError:
            layout_idx = 0

        layout_row = Adw.ComboRow()
        layout_row.set_title(_("Keyboard layout"))
        layout_row.set_model(Gtk.StringList.new(display_names))
        layout_row.set_selected(layout_idx)

        # Variant row — populated by _build_variant_dropdown; shown only
        # when the current layout exposes variants.
        variant_row = Adw.ComboRow()
        variant_row.set_title(_("Variant"))
        variant_row.set_model(Gtk.StringList.new([_("(Default)")]))
        self._variant_row = variant_row

        def _on_variant_changed(row: Adw.ComboRow, _pspec) -> None:
            if self._updating_variant:
                return
            idx = row.get_selected()
            if idx == Gtk.INVALID_LIST_POSITION or not self._variant_codes:
                return
            code = self._variant_codes[idx] if idx < len(self._variant_codes) else ""
            self.store.save_and_apply("keyboard_variant", code)

        variant_row.connect("notify::selected", _on_variant_changed)

        def _on_layout_changed(row: Adw.ComboRow, _pspec) -> None:
            idx = row.get_selected()
            if idx == Gtk.INVALID_LIST_POSITION or idx >= len(layout_codes):
                return
            code = layout_codes[idx]
            # Atomic dict save — layout and variant must flip together
            # so apply-settings doesn't see a stale variant that no
            # longer belongs to the new layout.
            self.store.save_dict_and_apply(
                {"keyboard_layout": code, "keyboard_variant": ""}
            )
            self._current_layout_code = code
            self._build_variant_dropdown(code)

        layout_row.connect("notify::selected", _on_layout_changed)

        group.add(layout_row)
        group.add(variant_row)

        # Initial variant population — seeded from the stored variant
        # for the current layout.
        self._build_variant_dropdown(current_layout)
        return group

    def _build_variant_dropdown(self, layout_code: str) -> None:
        """Rebuild the variant ComboRow for the given layout.

        Hides the row entirely when the layout has no variants. The
        parallel `self._variant_codes` list maps the row's visible
        index to the persisted code; index 0 is always "" (Default).
        """
        if self._variant_row is None:
            return

        variants = self._get_variants(layout_code)
        self._variant_codes = [""] + list(variants)

        # Guard _on_variant_changed against the notify::selected signals
        # emitted by set_model/set_selected during this rebuild; otherwise
        # each layout change would spuriously save_and_apply an empty
        # variant before the real selection lands.
        current_variant = self.store.get("keyboard_variant", "")
        labels = [_("(Default)")] + list(variants)
        try:
            sel = self._variant_codes.index(
                current_variant if layout_code == self._current_layout_code else ""
            )
        except ValueError:
            sel = 0

        self._updating_variant = True
        try:
            self._variant_row.set_model(Gtk.StringList.new(labels))
            self._variant_row.set_visible(bool(variants))
            self._variant_row.set_selected(sel)
        finally:
            self._updating_variant = False

    def _build_repeat_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Repeat"))

        delay_row = Adw.SpinRow.new_with_range(150.0, 1000.0, 50.0)
        delay_row.set_title(_("Repeat delay"))
        delay_row.set_subtitle(_("Milliseconds before keys begin repeating"))
        delay_row.set_value(float(self.store.get("keyboard_repeat_delay", 300)))
        delay_row.connect(
            "notify::value",
            lambda r, _p: self.store.save_debounced(
                "keyboard_repeat_delay", int(r.get_value())
            ),
        )
        group.add(delay_row)

        rate_row = Adw.SpinRow.new_with_range(10.0, 100.0, 5.0)
        rate_row.set_title(_("Repeat rate"))
        rate_row.set_subtitle(_("Keys per second when held"))
        rate_row.set_value(float(self.store.get("keyboard_repeat_rate", 40)))
        rate_row.connect(
            "notify::value",
            lambda r, _p: self.store.save_debounced(
                "keyboard_repeat_rate", int(r.get_value())
            ),
        )
        group.add(rate_row)
        return group

    def _build_capslock_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Caps Lock Behavior"))

        caps_labels = [_("Default"), _("Ctrl"), _("Escape"), _("Disabled")]
        caps_values = ["default", "ctrl", "escape", "disabled"]

        row = Adw.ComboRow()
        row.set_title(_("Caps Lock key"))
        row.set_subtitle(_("Remap Caps Lock to another function"))
        row.set_model(Gtk.StringList.new(caps_labels))

        current_caps = self.store.get("capslock_behavior", "default")
        try:
            row.set_selected(caps_values.index(current_caps))
        except ValueError:
            row.set_selected(0)

        def _on_caps_changed(r: Adw.ComboRow, _pspec) -> None:
            idx = r.get_selected()
            if 0 <= idx < len(caps_values):
                self.store.save_and_apply("capslock_behavior", caps_values[idx])

        row.connect("notify::selected", _on_caps_changed)
        group.add(row)
        return group

    def _build_shortcuts_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Keyboard Shortcuts"))
        self._shortcut_group = group
        self._shortcut_rows = []
        self._shortcut_reset_buttons = []

        for i, binding in enumerate(self._bindings):
            row = self._build_shortcut_row(i, binding)
            self._shortcut_rows.append(row)
            group.add(row)

        # Reset All — trailing row in the same group with a
        # destructive-styled suffix button. Reads cleanly alongside the
        # per-binding reset suffixes.
        reset_all_row = Adw.ActionRow()
        reset_all_row.set_title(_("Reset all shortcuts"))
        reset_all_row.set_subtitle(_("Restore every shortcut to its default"))

        reset_all_btn = Gtk.Button(label=_("Reset All"))
        reset_all_btn.add_css_class("destructive-action")
        reset_all_btn.set_valign(Gtk.Align.CENTER)
        reset_all_btn.connect("clicked", lambda _b: self._reset_all_shortcuts())
        reset_all_row.add_suffix(reset_all_btn)
        group.add(reset_all_row)
        return group

    def _build_shortcut_row(self, index: int, binding: dict) -> Adw.ActionRow:
        """Build a single AdwActionRow for a shortcut binding.

        - Title: human-readable action name.
        - Subtitle: the current key combination (e.g. "Ctrl + Alt + T").
        - Suffix: a flat reset-to-default icon button if the binding has
          been modified from its system default.
        - Activating the row pushes the capture sub-page.
        """
        row = Adw.ActionRow()
        row.set_title(binding["display_name"])
        row.set_subtitle(_human_key_label(binding["key"]))
        row.set_activatable(True)

        reset_btn: Gtk.Button | None = None
        default_key = self._get_default_key(index)
        if default_key and default_key != binding["key"]:
            reset_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
            reset_btn.add_css_class("flat")
            reset_btn.set_tooltip_text(_("Reset to default"))
            # Icon-only buttons have no inherent accessible name, so
            # orca/AT-SPI would announce them as "push button". Attach an
            # explicit label for screen readers.
            try:
                reset_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [_("Reset to default")]
                )
            except Exception:
                pass
            reset_btn.set_valign(Gtk.Align.CENTER)
            reset_btn.connect(
                "clicked", lambda _b, idx=index: self._reset_shortcut(idx)
            )
            row.add_suffix(reset_btn)

        # Track the reset button slot so _update_shortcut_row can
        # add / remove it as the binding drifts from its default.
        while len(self._shortcut_reset_buttons) <= index:
            self._shortcut_reset_buttons.append(None)
        self._shortcut_reset_buttons[index] = reset_btn

        row.connect("activated", lambda _r, idx=index: self._push_capture_page(idx))
        return row

    def _update_shortcut_row(self, index: int) -> None:
        """Mutate a shortcut row in-place to reflect the current binding.

        Updates the subtitle and adds/removes the reset-to-default
        suffix button as needed. The row widget itself stays in the
        group at its original position.
        """
        if index >= len(self._shortcut_rows):
            return
        row = self._shortcut_rows[index]
        binding = self._bindings[index]
        row.set_subtitle(_human_key_label(binding["key"]))

        # Grow the reset-button slot list if this index somehow wasn't
        # registered at build time (defensive; normally set up already).
        while len(self._shortcut_reset_buttons) <= index:
            self._shortcut_reset_buttons.append(None)

        existing = self._shortcut_reset_buttons[index]
        default_key = self._get_default_key(index)
        needs_reset = bool(default_key and default_key != binding["key"])

        if needs_reset and existing is None:
            reset_btn = Gtk.Button.new_from_icon_name("edit-undo-symbolic")
            reset_btn.add_css_class("flat")
            reset_btn.set_tooltip_text(_("Reset to default"))
            try:
                reset_btn.update_property(
                    [Gtk.AccessibleProperty.LABEL], [_("Reset to default")]
                )
            except Exception:
                pass
            reset_btn.set_valign(Gtk.Align.CENTER)
            reset_btn.connect(
                "clicked", lambda _b, idx=index: self._reset_shortcut(idx)
            )
            row.add_suffix(reset_btn)
            self._shortcut_reset_buttons[index] = reset_btn
        elif not needs_reset and existing is not None:
            row.remove(existing)
            self._shortcut_reset_buttons[index] = None

    def _get_default_key(self, index: int) -> str | None:
        """Get the default key for a binding by matching its action signature."""
        if index >= len(self._bindings):
            return None
        binding = self._bindings[index]
        for default in self._default_bindings:
            if (default["action"] == binding["action"]
                    and default["command"] == binding["command"]
                    and default["direction"] == binding["direction"]):
                return default["key"]
        return None

    # -- capture sub-page -----------------------------------------------

    def _push_capture_page(self, index: int) -> None:
        """Push a navigation sub-page dedicated to capturing a new shortcut.

        The Gtk.EventControllerKey attaches to the NavigationPage itself
        (not the root window), so capture scope is limited to this
        sub-page. On success: apply + pop. On conflict: the existing
        AdwAlertDialog flow is preserved.
        """
        if index < 0 or index >= len(self._bindings) or self._nav is None:
            return

        sub = Adw.NavigationPage()
        sub.set_title(_("Press new shortcut"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()  # automatic back button in collapsed mode
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

        status = Adw.StatusPage()
        status.set_icon_name("input-keyboard-symbolic")
        status.set_title(_("Press the new shortcut"))
        status.set_description(
            _("Press the desired key combination. Press Escape to cancel.")
        )
        toolbar.set_content(status)
        sub.set_child(toolbar)

        self._capture_page = sub
        self._capture_index = index
        self._capture_done = False

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self._on_capture_keypress, index, sub)
        sub.add_controller(controller)

        # Clear capture state on any dismissal — Escape, back-gesture,
        # header back button, Alt-Left. Without this, the state fields
        # remain pointing at a popped-and-destroyed sub-page, so any
        # future code path that gates on "are we in capture?" gets
        # confused. The "hidden" signal fires on every dismissal path.
        def _on_hidden(_page):
            if self._capture_page is _page:
                self._capture_page = None
                self._capture_index = -1
                self._capture_done = False
        sub.connect("hidden", _on_hidden)

        self._nav.push(sub)

    def _on_capture_keypress(self, _ctrl, keyval, _keycode, state, index, sub):
        """Handle a key press on the capture sub-page."""
        if self._capture_done:
            # Second key-press while we're already processing the first
            # (e.g. after showing the conflict dialog). Ignore.
            return True

        key_name = Gdk.keyval_name(keyval)

        # Ignore lone modifier presses — wait for the actual key.
        if key_name in _MODIFIER_KEYVALS:
            return True

        # Escape cancels capture (unless combined with a modifier).
        if key_name == "Escape" and not (state & (
                Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK
                | Gdk.ModifierType.SUPER_MASK)):
            self._capture_done = True
            if self._nav is not None:
                self._nav.pop()
            self._capture_page = None
            self._capture_index = -1
            return True

        new_key = self._build_key_string(keyval, state)
        if not new_key:
            return True

        # Reject system-reserved keys outright. _SKIP_KEYS are bindings
        # we deliberately hide from the editor (internal/debug). If the
        # user captures one, the conflict check wouldn't catch it
        # because those bindings aren't in self._bindings, and at
        # runtime both the user binding and the system binding would
        # compete with only one silently winning.
        if new_key in _SKIP_KEYS:
            self._capture_done = True
            dialog = Adw.AlertDialog.new(
                _("Reserved key combination"),
                _("{key} is reserved by the system and can't be reassigned.").format(key=new_key),
            )
            dialog.add_response("ok", _("OK"))
            dialog.set_default_response("ok")
            dialog.set_close_response("ok")
            dialog.connect("response", lambda _d, _r: self._nav.pop())
            dialog.present(self.get_root())
            return True

        # Conflict check uses the same logic as before.
        conflict_idx = self._find_conflict(new_key, index)
        if conflict_idx is not None:
            conflict_name = self._bindings[conflict_idx]["display_name"]
            # The conflict dialog may resolve asynchronously; guard
            # against a double-fire if the user somehow taps another
            # key before it responds.
            self._capture_done = True
            self._show_conflict_dialog(new_key, index, conflict_idx, conflict_name, sub)
            return True

        # Success path: apply and pop.
        self._capture_done = True
        self._apply_new_key(index, new_key)
        if self._nav is not None:
            self._nav.pop()
        self._capture_page = None
        self._capture_index = -1
        return True

    def _build_key_string(self, keyval, state):
        """Build a labwc key string from GDK keyval and modifier state."""
        parts = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            parts.append("C")
        if state & Gdk.ModifierType.ALT_MASK:
            parts.append("A")
        if state & Gdk.ModifierType.SHIFT_MASK:
            parts.append("S")
        if state & Gdk.ModifierType.SUPER_MASK:
            parts.append("W")
        key_name = Gdk.keyval_name(keyval)
        if key_name is None:
            return ""
        # labwc expects the unshifted keysym; GDK reports the shifted
        # character. For single-letter keys with Shift held, downshift
        # so "S-t" matches instead of "S-T". Multi-char keysym names
        # like "Tab", "Return", "Print" are left untouched.
        if (state & Gdk.ModifierType.SHIFT_MASK) and len(key_name) == 1:
            key_name = key_name.lower()
        parts.append(key_name)
        return "-".join(parts) if parts else ""

    def _find_conflict(self, new_key: str, exclude_index: int) -> int | None:
        """Find index of binding that already uses this key, or None."""
        for i, binding in enumerate(self._bindings):
            if i == exclude_index:
                continue
            if binding["key"] == new_key:
                return i
        return None

    def _show_conflict_dialog(self, new_key: str, target_idx: int,
                              conflict_idx: int, conflict_name: str,
                              capture_page: Adw.NavigationPage) -> None:
        """Show a dialog asking the user to confirm reassigning a conflicting key.

        Preserved from the pre-migration code: AdwAlertDialog is already
        Adw-native, so the only change is that the dismissal path pops
        the capture sub-page instead of swapping a button label.
        """
        parent = capture_page.get_root() if capture_page else self.get_root()

        dialog = Adw.AlertDialog.new(
            _("Shortcut Conflict"),
            _('"{key}" is already assigned to "{conflict}".\n\n'
              'Reassign it to "{target}"?').format(
                key=_human_key_label(new_key),
                conflict=conflict_name,
                target=self._bindings[target_idx]["display_name"],
            ),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("reassign", _("Reassign"))
        dialog.set_response_appearance(
            "reassign", Adw.ResponseAppearance.SUGGESTED
        )
        dialog.set_default_response("reassign")
        dialog.set_close_response("cancel")

        def _on_response(_dialog, response_id: str) -> None:
            if response_id == "reassign":
                # Fall back the conflicting binding to its default if it
                # had one; otherwise leave it keyless and explicitly tell
                # the user so they can rebind it rather than silently
                # producing a blank row.
                old_default = self._get_default_key(conflict_idx)
                if old_default:
                    self._bindings[conflict_idx]["key"] = old_default
                else:
                    self._bindings[conflict_idx]["key"] = ""
                    displaced_name = self._bindings[conflict_idx].get(
                        "display_name", self._bindings[conflict_idx].get(
                            "action", "")
                    )
                    self.store.show_toast(
                        _("No default key for {action}; please rebind it.").format(
                            action=displaced_name
                        ),
                        True,
                    )
                self._update_shortcut_row(conflict_idx)
                self._apply_new_key(target_idx, new_key)
            # Whether reassigned or cancelled, pop back to the list.
            if self._nav is not None:
                self._nav.pop()
            self._capture_page = None
            self._capture_index = -1

        dialog.connect("response", _on_response)
        dialog.present(parent)

    # -- binding mutation ------------------------------------------------

    def _apply_new_key(self, index: int, new_key: str) -> None:
        """Set a new key for the binding at index, save, and reconfigure."""
        if index >= len(self._bindings):
            return
        self._bindings[index]["key"] = new_key
        self._update_shortcut_row(index)
        self._save_and_reconfigure()

    def _reset_shortcut(self, index: int) -> None:
        """Reset a single shortcut to its system default.

        If the default key is currently assigned to a *different*
        shortcut, the user's other customization would silently get
        stomped. Warn via an AlertDialog and let the user confirm or
        cancel, rather than cascade-resetting without permission.
        """
        default_key = self._get_default_key(index)
        if default_key is None:
            return
        conflict_idx = self._find_conflict(default_key, index)
        if conflict_idx is not None:
            conflict_name = self._bindings[conflict_idx]["display_name"]
            dialog = Adw.AlertDialog.new(
                _("Reset would affect another shortcut"),
                _("{key} is currently assigned to {name}. Reset this "
                  "shortcut and also reset {name} to its default?").format(
                      key=default_key, name=conflict_name),
            )
            dialog.add_response("cancel", _("Cancel"))
            dialog.add_response("reset", _("Reset Both"))
            dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_close_response("cancel")
            dialog.set_default_response("cancel")

            def _on_response(_d, response_id):
                if response_id != "reset":
                    return
                other_default = self._get_default_key(conflict_idx)
                if other_default:
                    self._bindings[conflict_idx]["key"] = other_default
                    self._update_shortcut_row(conflict_idx)
                self._bindings[index]["key"] = default_key
                self._update_shortcut_row(index)
                self._save_and_reconfigure()

            dialog.connect("response", _on_response)
            dialog.present(self.get_root())
            return

        self._bindings[index]["key"] = default_key
        self._update_shortcut_row(index)
        self._save_and_reconfigure()

    def _reset_all_shortcuts(self) -> None:
        """Prompt the user before resetting all shortcuts.

        Reset All is destructive and unrecoverable once apply-settings
        regenerates rc.xml, so the actual reset is gated behind an
        AdwAlertDialog. The real work happens in
        _on_reset_all_response.
        """
        dialog = Adw.AlertDialog.new(
            _("Reset all shortcuts?"),
            _("This will restore every shortcut to its system default. "
              "This cannot be undone."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("reset", _("Reset All"))
        dialog.set_response_appearance(
            "reset", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.set_close_response("cancel")
        dialog.set_default_response("cancel")
        dialog.connect("response", self._on_reset_all_response)
        dialog.present(self.get_root())

    def _on_reset_all_response(self, _dialog, response):
        if response != "reset":
            return
        self._bindings = _clone_bindings(self._default_bindings)
        # Update every row in place.
        for i in range(len(self._bindings)):
            self._update_shortcut_row(i)
        # Delete user overrides and reconfigure.
        try:
            if USER_KEYBINDINGS.exists():
                USER_KEYBINDINGS.unlink()
        except OSError:
            pass
        # Out-of-band: the keybindings JSON lives outside settings.json,
        # so there's no key to save. Just kick apply-settings so it
        # re-reads the JSON and regenerates rc.xml.
        self.store.apply()

    def _save_and_reconfigure(self) -> None:
        """Save keybindings to JSON and trigger apply-settings + labwc reconfigure."""
        # Save the full bindings list (for apply-settings to read)
        save_data = []
        for b in self._bindings:
            save_data.append({
                "key": b["key"],
                "action": b["action"],
                "command": b.get("command", ""),
                "direction": b.get("direction", ""),
                "menu": b.get("menu", ""),
            })
        try:
            _save_user_keybindings(save_data)
        except OSError as exc:
            self.store.show_toast(
                _("Failed to save shortcuts: {msg}").format(msg=str(exc)), True)
            return

        # Out-of-band: see note in _reset_all_shortcuts.
        self.store.apply()

    # -- subprocess helpers ---------------------------------------------

    @staticmethod
    def _get_layouts():
        global _layouts_cache
        if _layouts_cache is not None:
            return _layouts_cache
        try:
            r = subprocess.run(
                ["localectl", "list-x11-keymap-layouts"],
                capture_output=True, text=True, timeout=10,
            )
            result = [line.strip() for line in r.stdout.splitlines() if line.strip()]
            if r.returncode != 0 or not result:
                result = ["us"]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            result = ["us"]
        _layouts_cache = result
        return result

    @staticmethod
    def _get_variants(layout):
        cached = _variants_cache.get(layout)
        if cached is not None:
            return cached
        try:
            r = subprocess.run(
                ["localectl", "list-x11-keymap-variants", layout],
                capture_output=True, text=True, timeout=10,
            )
            result = [v.strip() for v in r.stdout.splitlines() if v.strip()]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            result = []
        _variants_cache[layout] = result
        return result
