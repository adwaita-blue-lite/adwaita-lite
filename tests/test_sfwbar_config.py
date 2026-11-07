"""Tests for the sfwbar preview generator."""

import importlib.machinery
import importlib.util
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "files/usr/bin/adwaita-lite-panel"
_APPLY = _ROOT / "files/usr/libexec/adwaita-lite-apply-settings"


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader, origin=str(path))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(path)
    spec.loader.exec_module(module)
    return module


panel = _load("adwaita_panel", _SCRIPT)


def _settings(**overrides):
    settings = {
        "edge": "bottom",
        "density": "normal",
        "theme": "light",
        "accent": "blue",
        "font_size": 11,
        "high_contrast": False,
        "panel_twilight": False,
        "clock_24h": False,
        "reduce_motion": False,
        "layout": {
            "start": ["custom/launcher"],
            "center": ["wlr/taskbar"],
            "end": ["pulseaudio", "backlight", "battery", "clock", "tray"],
        },
        "pinned": [],
    }
    settings.update(overrides)
    return settings


def _render(settings):
    tokens = panel.build_tokens(settings)
    return panel.render_config(settings, tokens), panel.render_css(settings, tokens)


def _rgba_parts(value):
    match = re.match(r"rgba\((\d+), (\d+), (\d+), ([0-9.]+)\)", value)
    assert match, value
    return tuple(float(part) for part in match.groups())


def test_config_has_named_bar_and_layout_sections():
    config, _ = _render(_settings())

    assert config.startswith("#Api2\n")
    assert 'layout "sfwbar" {' in config
    assert 'layout "sfwbar:center"' in config
    assert 'layout "sfwbar:end"' in config
    assert 'size = "100%"' in config
    assert "margin = 8" in config
    assert 'layer = "top"' in config
    assert 'exclusive_zone = "auto"' in config
    assert 'mirror = "*"' in config


def test_config_taskbar_launcher_tray_and_status():
    config, _ = _render(_settings())

    assert "view-app-grid-symbolic" in config
    assert panel.LAUNCHER_COMMAND in config
    assert "filter = output" in config
    assert "rows = 1" in config
    assert "action[LeftClick] = TaskbarItemDefault()" in config
    assert "action[MiddleClick] = Close()" in config
    assert 'style = "status"' in config
    assert 'module("pulsectl")' in config
    assert "audio-volume-high-symbolic" in config
    assert "display-brightness-symbolic" in config
    assert "BatteryLevel" in config
    assert 'Time("%I:%M %p")' in config
    assert 'style = "tray"' in config


def test_status_modules_in_one_run_share_a_single_capsule():
    config, _ = _render(_settings())

    assert config.count('style = "status"') == 1
    status_block = config.split('style = "status"', 1)[1]
    for module in ("Volume(", "BacklightActual", "BatteryLevel", 'Time("'):
        assert module in status_block
    assert status_block.index("Volume(") < status_block.index("BacklightActual")
    assert status_block.index("BacklightActual") < status_block.index("BatteryLevel")


def test_separated_status_modules_get_separate_capsules():
    layout = {
        "start": ["custom/launcher"],
        "center": ["wlr/taskbar"],
        "end": ["pulseaudio", "tray", "clock"],
    }
    config, _ = _render(_settings(layout=layout))

    assert config.count('style = "status"') == 2


def test_unsupported_layout_modules_are_dropped():
    layout = {
        "start": ["custom/launcher", "network"],
        "center": ["wlr/taskbar"],
        "end": ["clock"],
    }
    config, _ = _render(_settings(layout=layout))

    assert "network" not in config
    assert "pulseaudio" not in config


def test_pinned_buttons_follow_launcher_and_preserve_command():
    settings = _settings(
        pinned=[
            {
                "name": "Quoted",
                "command": 'flatpak run com.example.App --flag "x"',
                "icon": "com.example.App",
            }
        ]
    )
    config, _ = _render(settings)

    assert 'tooltip = "Quoted"' in config
    assert 'action[LeftClick] = Exec("flatpak run com.example.App --flag \\"x\\"")' in config
    assert config.index('style = "launcher"') < config.index('style = "pinned"')
    assert config.index('style = "pinned"') < config.index('layout "sfwbar:center"')


def test_pins_are_prepended_when_layout_has_no_launcher():
    settings = _settings(
        layout={"start": [], "center": ["wlr/taskbar"], "end": ["clock"]},
        pinned=[{"name": "Files", "command": "nautilus", "icon": "system-file-manager"}],
    )
    config, _ = _render(settings)

    assert 'style = "pinned"' in config
    assert config.index('style = "pinned"') < config.index('style = "taskbar"')


def test_vertical_and_compact_metrics():
    settings = _settings(edge="left", density="compact", font_size=15)
    config, css = _render(settings)
    tokens = panel.build_tokens(settings)

    assert "-GtkWidget-direction: left" in css
    assert 'size = "100%"' in config
    assert "cols = 1" in config
    assert "rows = 1" not in config
    assert f"font-size: {tokens['font_size']}px" in css
    assert "border-left: 3px solid" in css
    assert "min-width:" in css


def test_vertical_layout_flows_center_after_start():
    config, _ = _render(_settings(edge="left"))

    assert 'layout "sfwbar:center"' not in config
    assert config.index('style = "taskbar"') < config.index('style = "status"')


def test_clock_24h_and_vertical_formats():
    config, css = _render(_settings(clock_24h=True))
    assert 'Time("%H:%M")' in config

    config, css = _render(_settings(edge="right"))
    assert 'Time("%I:%M")' in config
    assert 'Time("%p")' in config
    assert 'Time("%I:%M %p")' not in config
    assert "-GtkWidget-wrap: true" in css
    assert "-GtkWidget-max-width:" in css


def test_high_contrast_wins_and_disables_motion():
    _, css = _render(_settings(high_contrast=True, panel_twilight=True))

    assert "rgba(0, 0, 0, 0.98)" in css
    assert "transition: none" in css
    assert "rgba(0, 0, 0, 0.90)" not in css


def test_twilight_uses_opposite_palette():
    _, css = _render(_settings(panel_twilight=True, theme="light"))

    assert "rgba(34, 34, 38, 0.90)" in css


def test_missing_battery_and_backlight_are_hidden():
    config, css = _render(_settings())

    assert 'style = If(!BatteryLevel.count, "hidden"' in config
    assert 'style = If(BacklightMax.count, "backlight", "hidden")' in config
    assert "-GtkWidget-visible: false" in css


def test_battery_icon_thresholds_map_to_ten_percent_steps():
    config, _ = _render(_settings())

    assert '90, "battery-level-100-charging-symbolic"' in config
    assert '80, "battery-level-90-charging-symbolic"' in config
    assert '0, "battery-level-10-charging-symbolic"' in config
    assert '90, "battery-level-100-symbolic"' in config
    assert "battery-missing-symbolic" in config


def test_css_targets_sfwbar_widget_names():
    _, css = _render(_settings())

    assert "window#sfwbar" in css
    assert "button#launcher" in css
    assert "button#pinned" in css
    assert "grid#taskbar button" in css
    assert "grid#taskbar button.focused" in css
    assert "grid#status" in css
    assert "label#clock" in css
    assert "grid#tray" in css
    assert "tooltip label" in css


@pytest.mark.parametrize("edge,indicator", [
    ("bottom", "border-bottom"),
    ("top", "border-top"),
    ("left", "border-left"),
    ("right", "border-right"),
])
def test_active_indicator_follows_panel_edge(edge, indicator):
    _, css = _render(_settings(edge=edge))

    assert f"grid#taskbar button.focused {{\n  {indicator}: 3px solid" in css


def test_write_assets_creates_drop_in_files(tmp_path):
    config, css = panel.write_assets(tmp_path, _settings())

    assert config.name == "sfwbar.config"
    assert css.name == "sfwbar.css"
    assert config.exists()
    assert css.exists()
    assert config.read_text(encoding="utf-8").startswith("#Api2\n")
    assert "window#sfwbar" in css.read_text(encoding="utf-8")


def test_preview_config_home_isolates_sfwbar_but_links_gtk(tmp_path, monkeypatch):
    real = tmp_path / "real"
    (real / "gtk-3.0").mkdir(parents=True)
    (real / "sfwbar").mkdir()
    runtime = tmp_path / "runtime"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(real))
    monkeypatch.setattr(panel, "_preview_dir", lambda: runtime / "preview")

    home = panel._preview_config_home()

    assert (home / "sfwbar").is_dir()
    assert (home / "gtk-3.0").is_symlink()
    assert not (home / "sfwbar").is_symlink()


def test_image_installs_sfwbar_and_panel_wrapper():
    build_script = (_ROOT / "build_files/build.sh").read_text(encoding="utf-8")

    assert "    sfwbar \\" in build_script
    assert "    adwaita-icon-theme \\" in build_script
    assert "/usr/bin/adwaita-lite-panel" in build_script


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["normal", "compact"])
@pytest.mark.parametrize("edge", ["bottom", "top", "left", "right"])
@pytest.mark.parametrize("font_size", [10, 11, 13, 15])
@pytest.mark.parametrize("high_contrast", [False, True])
@pytest.mark.parametrize("twilight", [False, True])
def test_tokens_match_waybar_generator(theme, density, edge, font_size, high_contrast, twilight):
    """Keep the sfwbar preview in visual lockstep with the Waybar contract."""
    apply_settings = _load("adwaita_apply_settings", _APPLY)
    settings = _settings(
        theme=theme,
        density=density,
        edge=edge,
        font_size=font_size,
        high_contrast=high_contrast,
        panel_twilight=twilight,
        accent="teal",
    )
    expected = apply_settings._build_tokens(settings)
    actual = panel.build_tokens(settings)

    vertical = edge in ("left", "right")
    assert actual["vertical"] == vertical
    assert actual["icon"] == expected["panel_icon_size"]
    assert actual["margin"] == expected["panel_margin"]
    assert actual["inset"] == expected["panel_bar_inset"]
    assert actual["spacing"] == expected["panel_spacing"]
    assert actual["pad_module"] == expected["panel_pad_module"]
    assert actual["pad_launcher"] == expected["panel_pad_launcher"]
    assert actual["pad_pin"] == expected["panel_pad_pin"]
    assert actual["size"] == (
        expected["panel_width"] if vertical else expected["panel_height"]
    )
    assert actual["font_size"] == expected["font_size_ui"]
    assert actual["accent"] == expected["accent_hex"]
    assert actual["clock_24h"] == expected["clock_24h"]

    assert _rgba_parts(actual["surface"]) == _rgba_parts(
        apply_settings._rgba_css(expected["panel_surface"], float(expected["panel_alpha"]))
    )
    assert _rgba_parts(actual["border"]) == _rgba_parts(expected["panel_border"])
    assert _rgba_parts(actual["control"]) == _rgba_parts(expected["panel_control_bg"])
    assert _rgba_parts(actual["control_hover"]) == _rgba_parts(expected["panel_control_hover"])
    assert _rgba_parts(actual["control_border"]) == _rgba_parts(expected["panel_control_border"])
    assert _rgba_parts(actual["status_bg"]) == _rgba_parts(expected["panel_status_bg"])
    assert _rgba_parts(actual["status_border"]) == _rgba_parts(expected["panel_status_border"])
