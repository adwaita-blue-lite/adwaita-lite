from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
MIMEAPPS = REPO / "files/etc/xdg/mimeapps.list"
APPLICATIONS = REPO / "files/usr/share/applications"
FOOT_INI = REPO / "files/etc/xdg/foot/foot.ini"
GTK_XDG_SETTINGS = (
    REPO / "files/etc/xdg/gtk-3.0/settings.ini",
    REPO / "files/etc/xdg/gtk-4.0/settings.ini",
)
GTK_DIRECT_SETTINGS = (
    REPO / "files/etc/gtk-3.0/settings.ini",
    REPO / "files/etc/gtk-4.0/settings.ini",
)


def _defaults() -> dict[str, str]:
    defaults = {}
    in_default_section = False
    for raw_line in MIMEAPPS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_default_section = line == "[Default Applications]"
            continue
        if in_default_section and "=" in line:
            mime_type, desktop_id = line.split("=", 1)
            defaults[mime_type] = desktop_id
    return defaults


def test_text_defaults_use_gnome_text_editor_desktop_id():
    defaults = _defaults()

    assert defaults["text/plain"] == "org.gnome.TextEditor.desktop"
    assert defaults["text/x-python"] == "org.gnome.TextEditor.desktop"


def test_legacy_mousepad_alias_is_not_shipped():
    assert not (APPLICATIONS / "mousepad.desktop").exists()


def test_system_foot_config_uses_current_color_theme_sections():
    ini = FOOT_INI.read_text(encoding="utf-8")

    assert "initial-color-theme=light" in ini
    assert "\n[colors]\n" not in ini
    assert "\n[colors-dark]\n" in ini
    assert "\n[colors-light]\n" in ini


def test_system_gtk_defaults_include_non_theme_runtime_keys():
    for path in GTK_XDG_SETTINGS:
        ini = path.read_text(encoding="utf-8")
        assert "gtk-font-name=Roboto 13" in ini
        assert "gtk-enable-animations=1" in ini
        assert "gtk-decoration-layout=:minimize,maximize,close" in ini


def test_direct_gtk_defaults_match_xdg_gtk_defaults():
    for direct, xdg in zip(GTK_DIRECT_SETTINGS, GTK_XDG_SETTINGS):
        assert direct.read_text(encoding="utf-8") == xdg.read_text(encoding="utf-8")
