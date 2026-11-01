from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/components"

PAGES = {
    "index": DOCS / "index.html",
    "setup-wizard": DOCS / "setup-wizard.html",
    "app-menu": DOCS / "app-menu.html",
    "greeter": DOCS / "greeter.html",
    "settings": DOCS / "settings.html",
    "theme-system": DOCS / "theme-system.html",
}

SOURCE_PATHS = [
    "files/usr/bin/adwaita-lite-setup-wizard",
    "files/usr/bin/adwaita-lite-app-menu",
    "files/usr/bin/adwaita-lite-greeter",
    "files/usr/lib/adwaita-lite/settings/",
    "files/usr/lib/adwaita-lite/settings/css/style.css",
    "files/usr/lib/adwaita-lite/theme.py",
    "files/usr/share/adwaita-lite/palette.json",
]

PAGE_SOURCE_PATHS = {
    "setup-wizard": ["files/usr/bin/adwaita-lite-setup-wizard"],
    "app-menu": ["files/usr/bin/adwaita-lite-app-menu"],
    "greeter": ["files/usr/bin/adwaita-lite-greeter"],
    "settings": [
        "files/usr/lib/adwaita-lite/settings/",
        "files/usr/lib/adwaita-lite/settings/css/style.css",
    ],
    "theme-system": [
        "files/usr/share/adwaita-lite/palette.json",
        "files/usr/lib/adwaita-lite/theme.py",
    ],
}

VISUAL_MARKERS = [
    "flow-strip",
    "component-grid",
    "source-map",
    "state-map",
    "safe-edit",
    "density-note",
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attrs = dict(attrs)
        href = attrs.get("href")
        if href:
            self.links.append(href)


def _text(path: Path) -> str:
    assert path.is_file(), f"missing docs page: {path}"
    return path.read_text(encoding="utf-8")


def _links(path: Path) -> list[str]:
    parser = LinkParser()
    parser.feed(_text(path))
    return parser.links


def test_component_docs_pages_exist():
    for name, path in PAGES.items():
        assert path.is_file(), f"missing docs page for {name}: {path}"


def test_component_docs_index_links_to_every_page():
    links = set(_links(PAGES["index"]))

    for name in ("setup-wizard", "app-menu", "greeter", "settings", "theme-system"):
        assert f"{name}.html" in links, f"index missing link to {name}.html"


def test_component_docs_pages_link_back_to_index():
    for name, path in PAGES.items():
        if name == "index":
            continue
        assert "index.html" in set(_links(path)), f"{name} does not link back to index"


def test_component_docs_reference_existing_source_paths():
    combined = "\n".join(_text(path) for path in PAGES.values())

    for source_path in SOURCE_PATHS:
        assert (ROOT / source_path).exists(), f"source path no longer exists: {source_path}"
        assert source_path in combined, f"docs do not reference {source_path}"


def test_component_pages_reference_their_own_source_paths():
    for page_name, source_paths in PAGE_SOURCE_PATHS.items():
        html = _text(PAGES[page_name])
        for source_path in source_paths:
            assert source_path in html, f"{page_name} doc does not reference {source_path}"


def test_component_docs_use_dense_visual_structures():
    for name, path in PAGES.items():
        html = _text(path)
        present = {marker for marker in VISUAL_MARKERS if marker in html}
        assert len(present) >= 2, (
            f"{name} should use at least two component-specific visual structures, "
            f"not plain Markdown-like prose; found: {sorted(present)}"
        )


def test_setup_wizard_doc_covers_major_ui_anchors():
    html = _text(PAGES["setup-wizard"])
    required = [
        "SetupWizardWindow",
        "_build_language_page",
        "_build_network_page",
        "_build_disk_page",
        "_build_account_page",
        "_build_system_page",
        "_build_apps_page",
        "_build_confirm_page",
        "_build_progress_page",
        "card",
        "welcome-title",
        "form-entry",
        "dark-list",
        "wifi-row",
        "keyboard-panel",
        "app-row",
        "log-view",
        "tests/test_setup_wizard_gtk_smoke.py",
        "tests/test_setup_wizard_app_selection.py",
    ]

    for term in required:
        assert term in html, f"setup wizard doc missing required anchor: {term}"


def test_app_menu_doc_covers_major_ui_anchors():
    html = _text(PAGES["app-menu"])
    required = [
        "AppMenu",
        "AppItem",
        "_build_css",
        "_menu_metrics",
        "_make_flowbox",
        "_make_gridview",
        "_build_power_bar",
        "Gtk4LayerShell",
        "app-menu-surface",
        "app-menu-grid",
        "app-menu-tile",
        "app-menu-power-bar",
        "tests/test_app_menu_css.py",
    ]

    for term in required:
        assert term in html, f"app menu doc missing required anchor: {term}"


def test_greeter_doc_covers_major_ui_anchors():
    html = _text(PAGES["greeter"])
    required = [
        "GreeterWindow",
        "GreetdClient",
        "_build_css",
        "_load_palettes",
        "_load_theme",
        "clock",
        "date",
        "card",
        "session-dropdown",
        "login-button",
        "switch-user",
    ]

    for term in required:
        assert term in html, f"greeter doc missing required anchor: {term}"


def test_settings_doc_covers_major_custom_surfaces():
    html = _text(PAGES["settings"])
    required = [
        "SettingsWindow",
        "BasePage",
        "AppearancePage",
        "PanelPage",
        "KeyboardPage",
        "NetworkPage",
        "DisplayPage",
        "wallpaper-tile",
        "accent-swatch",
        "Adw.NavigationView",
        "Adw.AlertDialog",
        "files/usr/lib/adwaita-lite/settings/css/style.css",
        "tests/test_settings_css.py",
        "docs/superpowers/specs/2026-04-20-settings-adwaita-reference.md",
    ]

    for term in required:
        assert term in html, f"settings doc missing required anchor: {term}"


def test_theme_system_doc_covers_major_theme_anchors():
    html = _text(PAGES["theme-system"])
    required = [
        "files/usr/share/adwaita-lite/palette.json",
        "files/usr/lib/adwaita-lite/theme.py",
        "gtk_color_defines",
        "_build_accent_css",
        "_build_twilight_css",
        "DARK_THEME_COLORS",
        "@accent_color",
        "@window_bg_color",
        "panel_twilight",
        "high_contrast",
    ]

    for term in required:
        assert term in html, f"theme system doc missing required anchor: {term}"
