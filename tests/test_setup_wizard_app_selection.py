import ast
import re
import runpy
import sys
import types
from pathlib import Path


WIZARD = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-setup-wizard"


class _FakeGiNamespace(types.ModuleType):
    def __getattr__(self, name):
        value = type(name, (), {})
        setattr(self, name, value)
        return value


def _load_wizard_helpers(monkeypatch):
    gi = types.ModuleType("gi")
    gi.require_version = lambda *_args, **_kwargs: None
    repository = types.ModuleType("gi.repository")
    for name in ("Gtk", "Gdk", "GLib", "Gio", "NM", "Pango"):
        setattr(repository, name, _FakeGiNamespace(name))
    monkeypatch.setitem(sys.modules, "gi", gi)
    monkeypatch.setitem(sys.modules, "gi.repository", repository)
    return runpy.run_path(str(WIZARD), run_name="wizard_for_test")


def _css_blocks(css: str) -> list[tuple[list[str], str]]:
    blocks = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", css, flags=re.DOTALL):
        selectors = [s.strip() for s in match.group(1).split(",")]
        body = match.group(2)
        blocks.append((selectors, body))
    return blocks


def _css_body_for_selector(css: str, selector: str) -> str:
    bodies = [body for selectors, body in _css_blocks(css) if selector in selectors]
    assert bodies, f"Missing CSS selector: {selector}"
    return "\n".join(bodies)


def _css_properties(body: str) -> set[str]:
    properties = set()
    for declaration in body.split(";"):
        if ":" not in declaration:
            continue
        name, _value = declaration.split(":", 1)
        properties.add(name.strip())
    return properties


def _assert_selector_has_properties(css: str, selector: str, properties: set[str]) -> None:
    declared = _css_properties(_css_body_for_selector(css, selector))
    missing = sorted(properties - declared)
    assert not missing, f"{selector} missing CSS properties: {missing}"


def test_empty_app_selection_writes_zero_byte_flatpak_list(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)

    assert module["_flatpak_app_list_contents"](set()) == ""


def test_app_selection_writes_deterministic_flatpak_list(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)

    content = module["_flatpak_app_list_contents"]({
        "io.github.kolunmi.Bazaar",
        "com.google.Chrome",
    })

    assert content == "com.google.Chrome\nio.github.kolunmi.Bazaar\n"


def test_app_selection_file_is_readable_by_post_login_prompt():
    source = WIZARD.read_text()
    write_start = source.index('state_dir / "flatpak-apps"')
    write_call = source[write_start: write_start + 160]

    assert "_flatpak_app_list_contents(selected_ids)" in write_call
    assert "mode=0o644" in write_call


def test_pinned_defaults_follow_selected_apps(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)

    pinned = module["_pinned_apps_for_selected_flatpaks"]({
        "io.github.kolunmi.Bazaar",
        "org.gtk.Gtk3theme.adw-gtk3",
    })

    assert pinned == [{
        "name": "Bazaar",
        "command": "flatpak run io.github.kolunmi.Bazaar",
        "icon": "io.github.kolunmi.Bazaar",
        "desktop_id": "io.github.kolunmi.Bazaar.desktop",
        "app_id": "io.github.kolunmi.Bazaar",
        "startup_wm_class": "io.github.kolunmi.Bazaar",
    }]


def test_no_selected_apps_means_no_pinned_defaults(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)

    assert module["_pinned_apps_for_selected_flatpaks"](set()) == []


def test_password_entries_avoid_missing_activates_default_api():
    tree = ast.parse(WIZARD.read_text())
    password_entries = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "PasswordEntry"
            and isinstance(func.value, ast.Name)
            and func.value.id == "Gtk"
        ):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                password_entries.add(target.attr)
            elif isinstance(target, ast.Name):
                password_entries.add(target.id)

    bad_lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "set_activates_default":
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Attribute) and receiver.attr in password_entries:
            bad_lines.append(node.lineno)
        elif isinstance(receiver, ast.Name) and receiver.id in password_entries:
            bad_lines.append(node.lineno)

    assert not bad_lines, (
        "Gtk.PasswordEntry in the installer image lacks set_activates_default; "
        f"use the activate signal instead. Lines: {bad_lines}"
    )


def test_wizard_avoids_removed_accessibility_live_region_api():
    source = WIZARD.read_text()

    assert "Gtk.AccessibleProperty.LIVE" not in source
    assert "Gtk.AccessibleLive" not in source
    assert ".announce(" in source


def test_wizard_uses_current_alert_dialog_api():
    source = WIZARD.read_text()
    tree = ast.parse(source)

    assert "Gtk.MessageDialog" not in source

    helper = next(
        (
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_show_install_in_progress_alert"
        ),
        None,
    )
    assert helper is not None

    has_alert_dialog_guard = False
    for node in ast.walk(helper):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "hasattr"):
            continue
        if len(node.args) != 2:
            continue
        namespace, attribute = node.args
        if (
            isinstance(namespace, ast.Name)
            and namespace.id == "Gtk"
            and isinstance(attribute, ast.Constant)
            and attribute.value == "AlertDialog"
        ):
            has_alert_dialog_guard = True

    assert has_alert_dialog_guard


def test_wizard_forces_dark_theme_without_libadwaita(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)
    source = WIZARD.read_text()
    tree = ast.parse(source)

    def is_gtk_call(node, name):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == name
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "Gtk"
        )

    app_class = next(
        (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "SetupWizardApp"),
        None,
    )
    assert app_class is not None

    do_activate = next(
        (
            node for node in app_class.body
            if isinstance(node, ast.FunctionDef) and node.name == "do_activate"
        ),
        None,
    )
    assert do_activate is not None

    dark_call_index = None
    provider_index = None
    for index, statement in enumerate(do_activate.body):
        if (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and isinstance(statement.value.func, ast.Name)
            and statement.value.func.id == "_force_dark_theme"
        ):
            dark_call_index = index

        nodes = ast.walk(statement)
        if provider_index is not None:
            continue

        if any(is_gtk_call(node, "CssProvider") for node in nodes):
            provider_index = index
            continue

        nodes = ast.walk(statement)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_provider_for_display"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "StyleContext"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "Gtk"
            for node in nodes
        ):
            provider_index = index

    assert "gi.require_version(\"Adw\"" not in source
    assert "from gi.repository import Adw" not in source
    assert "_force_dark_theme" in module
    assert "Gtk.Settings.get_default" in source
    assert "gtk-application-prefer-dark-theme" in source
    assert dark_call_index is not None
    assert provider_index is not None
    assert dark_call_index < provider_index


def test_wizard_css_declares_adwaita_dark_palette(monkeypatch):
    module = _load_wizard_helpers(monkeypatch)
    colors = module["DARK_THEME_COLORS"]

    required = {
        "window_bg",
        "card_bg",
        "control_bg",
        "control_hover_bg",
        "subtle_bg",
        "border",
        "border_subtle",
        "primary_fg",
        "secondary_fg",
        "disabled_fg",
        "accent_bg",
        "accent_hover_bg",
        "accent_active_bg",
        "focus_border",
        "error_fg",
        "success_fg",
        "selection_bg",
        "selection_fg",
    }
    assert required <= set(colors)

    for name in required:
        value = colors[name]
        assert value.startswith(("#", "rgba(")), f"{name} has non-color token value {value!r}"


def test_wizard_css_covers_dark_gtk_control_nodes(monkeypatch):
    css = _load_wizard_helpers(monkeypatch)["CSS"]

    required_selectors = {
        "window": {"background-color", "color"},
        "*": {"color", "-gtk-icon-palette"},
        ".card": {"background-color", "color", "border"},
        "entry": {"background-color", "color", "border", "caret-color"},
        "entry text": {"background-color", "color"},
        "entry image": {"color"},
        "entry.search": {"background-color", "color", "border"},
        "selection": {"background-color", "color"},
        "dropdown": {"color"},
        "dropdown button": {"background-color", "color", "border"},
        "dropdown button label": {"color"},
        "dropdown button arrow": {"color"},
        "dropdown popover": {"background-color", "color"},
        "dropdown popover contents": {"background-color", "color"},
        "dropdown popover entry.search": {"background-color", "color", "border"},
        "dropdown popover listview": {"background-color", "color"},
        "dropdown popover row": {"background-color", "color"},
        "dropdown popover row:selected": {"background-color", "color"},
        "dropdown popover label": {"color"},
        "popover.background": {"background-color", "color"},
        "popover contents": {"background-color", "color", "border"},
        "popover arrow": {"background-color", "border"},
        "list": {"background-color", "color"},
        "listbox": {"background-color", "color"},
        "row": {"background-color", "color"},
        "row:selected": {"background-color", "color"},
        "checkbutton": {"color"},
        "checkbutton label": {"color"},
        "checkbutton check": {"background-color", "border"},
        "scrolledwindow": {"background-color"},
        "viewport": {"background-color"},
        "scrollbar slider": {"background-color"},
        "textview": {"background-color", "color"},
        "textview text": {"background-color", "color"},
        ".log-view": {"background-color", "color"},
    }

    for selector, properties in required_selectors.items():
        _assert_selector_has_properties(css, selector, properties)


def test_wizard_css_does_not_define_light_control_surfaces(monkeypatch):
    css = _load_wizard_helpers(monkeypatch)["CSS"]
    light_surface = re.compile(
        r"background(?:-color)?\s*:\s*(?:white|#fff(?:fff)?|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))",
        flags=re.IGNORECASE,
    )

    assert not light_surface.search(css)
