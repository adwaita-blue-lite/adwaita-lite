"""Tests for the sfwbar preview generator."""

import importlib.machinery
import importlib.util
import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "files/usr/bin/adwaita-lite-panel"
_APPLY = _ROOT / "files/usr/libexec/adwaita-lite-apply-settings"
_DEFAULTS = _ROOT / "files/usr/share/adwaita-lite/defaults/settings.json"


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
            "start": ["custom/launcher", "wlr/taskbar"],
            "center": [],
            "end": ["tray", "network", "pulseaudio", "battery", "clock"],
        },
        "pinned": [],
    }
    settings.update(overrides)
    return settings


def _render(settings, *, floating=False):
    tokens = panel.build_tokens(settings, floating=floating)
    return panel.render_config(settings, tokens), panel.render_css(settings, tokens)


def _rgba_parts(value):
    match = re.match(r"rgba\((\d+), (\d+), (\d+), ([0-9.]+)\)", value)
    assert match, value
    return tuple(float(part) for part in match.groups())


def test_default_layout_is_edge_to_edge_with_apps_at_leading_edge():
    config, css = _render(_settings())

    assert config.startswith("#Api2\n")
    assert 'layout "sfwbar" {' in config
    assert 'layout "sfwbar:center"' not in config
    assert 'size = "100%"' in config
    assert "margin = 0" in config
    assert 'layer = "top"' in config
    assert 'exclusive_zone = "auto"' in config
    assert 'mirror = "*"' in config
    assert config.index('style = "launcher"') < config.index('style = "taskbar"')
    assert "border-radius: 0;" in css
    assert "rgba(250, 250, 250, 1.00)" in css
    assert "box-shadow: inset 0 1px 0 0" in css


def test_floating_variant_keeps_the_opt_in_pill():
    config, css = _render(_settings(), floating=True)
    tokens = panel.build_tokens(_settings(), floating=True)

    assert "margin = 8" in config
    assert tokens["bar_radius"] == 16
    assert "border-radius: 16px;" in css
    assert "rgba(250, 250, 250, 0.90)" in css
    assert "border: 1px solid" in css
    assert "inset 0 1px 0 0" not in css


def test_tiles_use_chromeos_sized_icons_and_adwaita_radii():
    config, css = _render(_settings())

    assert "min-width: 48px;" in css
    assert "min-height: 48px;" in css
    assert "border-radius: 12px;" in css
    assert "min-width: 32px;" in css
    assert "min-height: 32px;" in css
    assert "border-radius: 999px;" in css
    assert "min-width: 24px;" in css
    assert "min-width: 20px;" in css
    assert "-GtkWidget-max-width: 48px;" in css
    assert "-GtkWidget-max-height: 48px;" in css
    assert " class = " not in config


def test_compact_metrics_scale_down():
    settings = _settings(density="compact")
    _, css = _render(settings)
    tokens = panel.build_tokens(settings)

    assert tokens["tile"] == 40
    assert tokens["tile_radius"] == 10
    assert tokens["icon_app"] == 24
    assert tokens["icon_launcher"] == 20
    assert tokens["icon_status"] == 16
    assert tokens["clock_size"] == 12
    assert "min-width: 40px;" in css
    assert "border-radius: 10px;" in css


def test_state_ladder_uses_adwaita_alphas_and_static_urgent():
    _, css = _render(_settings())

    assert "background: rgba(30, 30, 30, 0.08);" in css
    assert "background: rgba(30, 30, 30, 0.16);" in css
    assert "box-shadow: inset 0 0 0 2px #3584e4;" in css
    assert "background: rgba(53, 132, 228, 0.12);" in css
    assert "box-shadow: inset 0 -3px 0 0 #3584e4;" in css
    assert "background: rgba(200, 136, 0, 0.16);" in css
    assert "animation" not in css


@pytest.mark.parametrize("edge,shadow", [
    ("bottom", "inset 0 -3px 0 0"),
    ("top", "inset 0 3px 0 0"),
    ("left", "inset 3px 0 0 0"),
    ("right", "inset -3px 0 0 0"),
])
def test_focused_indicator_follows_screen_edge(edge, shadow):
    _, css = _render(_settings(edge=edge))

    assert f"box-shadow: {shadow} #3584e4;" in css


def test_status_area_is_flat_and_ordered_like_a_shelf():
    config, css = _render(_settings())

    assert 'style = "status"' not in config
    assert 'style = "volume"' in config
    assert 'style = If(Ident(NetInfo), "network", "hidden")' in config
    assert "grid#status" not in css
    assert 'module("network")' in config
    assert "NetInfo" in config
    assert "network-offline-symbolic" in config
    assert "network-wired-symbolic" in config

    end = config.split('layout "sfwbar:end"', 1)[1]
    order = [
        end.index('style = "tray"'),
        end.index("NetInfo"),
        end.index("Volume("),
        end.index("BatteryLevel"),
        end.index('Time("'),
    ]
    assert order == sorted(order)


def test_backlight_is_opt_in_but_still_supported():
    default_config, _ = _render(_settings())
    assert "BacklightActual" not in default_config

    layout = {
        "start": ["custom/launcher", "wlr/taskbar"],
        "center": [],
        "end": ["tray", "network", "pulseaudio", "backlight", "battery", "clock"],
    }
    config, _ = _render(_settings(layout=layout))
    assert "BacklightActual" in config
    assert 'style = If(BacklightMax.count, "backlight", "hidden")' in config


def test_network_is_hidden_without_the_module():
    config, _ = _render(_settings())

    assert 'style = If(Ident(NetInfo), "network", "hidden")' in config
    assert "trigger = \"network\"" in config


def test_unsupported_layout_modules_are_dropped():
    layout = {
        "start": ["custom/launcher", "wlr/taskbar", "unknown-module"],
        "center": [],
        "end": ["clock"],
    }
    config, _ = _render(_settings(layout=layout))

    assert "unknown-module" not in config
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
    assert config.index('style = "pinned"') < config.index('style = "taskbar"')


def test_pins_are_prepended_when_layout_has_no_launcher():
    settings = _settings(
        layout={"start": ["wlr/taskbar"], "center": [], "end": ["clock"]},
        pinned=[{"name": "Files", "command": "nautilus", "icon": "system-file-manager"}],
    )
    config, _ = _render(settings)

    assert 'style = "pinned"' in config
    assert config.index('style = "pinned"') < config.index('style = "taskbar"')


def test_vertical_keeps_48px_tiles_inside_a_64px_bar():
    settings = _settings(edge="left")
    tokens = panel.build_tokens(settings)
    _, css = _render(settings)

    assert tokens["size"] == 64
    assert tokens["tile"] == 48
    assert tokens["side_pad"] == 8
    assert "padding: 16px 8px;" in css
    assert "-GtkWidget-valign: start;" in css
    assert "-GtkWidget-valign: end;" in css


def test_hover_and_pressed_feedback_are_present():
    _, css = _render(_settings())

    assert "button#launcher:hover, button#pinned:hover, grid#taskbar button:hover" in css
    assert "button#launcher:active, button#pinned:active, grid#taskbar button:active" in css


def test_vertical_layout_flows_center_after_start_and_uses_two_line_clock():
    config, css = _render(_settings(edge="left"))

    assert "-GtkWidget-direction: left" in css
    assert 'layout "sfwbar:center"' not in config
    assert "cols = 1" in config
    assert "rows = 1" not in config
    assert 'Time("%I:%M")' in config
    assert 'Time("%p")' in config
    assert 'Time("%I:%M %p")' not in config
    assert "-GtkWidget-wrap: true" in css


def test_config_avoids_unsupported_beta16_class_property():
    config, _ = _render(_settings())
    assert "class = " not in config


def test_clock_typography_and_24h_format():
    config, css = _render(_settings(clock_24h=True))

    assert 'Time("%H:%M")' in config
    assert "font-weight: 500;" in css
    assert "font-size: 13px;" in css
    assert "min-width: 58px;" in css
    assert "padding: 0 10px;" in css
    assert '"Adwaita Sans", "Inter", "Roboto", sans-serif' in css


def test_high_contrast_is_opaque_and_disables_motion():
    _, css = _render(_settings(high_contrast=True, panel_twilight=True))

    assert "rgba(0, 0, 0, 1.00)" in css
    assert "transition: none" in css
    assert "rgba(0, 0, 0, 0.90)" not in css
    assert "rgba(0, 0, 0, 0.98)" not in css


def test_twilight_uses_opposite_palette_opaque_shelf():
    _, css = _render(_settings(panel_twilight=True, theme="light"))

    assert "rgba(34, 34, 38, 1.00)" in css


def test_missing_battery_and_backlight_are_hidden():
    config, css = _render(_settings())

    assert 'style = If(!BatteryLevel.count, "hidden"' in config
    assert "-GtkWidget-visible: false" in css


def test_battery_icon_thresholds_map_to_ten_percent_steps():
    config, _ = _render(_settings())

    assert '90, "battery-level-100-charging-symbolic"' in config
    assert '80, "battery-level-90-charging-symbolic"' in config
    assert '0, "battery-level-10-charging-symbolic"' in config
    assert '90, "battery-level-100-symbolic"' in config
    assert "battery-missing-symbolic" in config


def test_css_targets_flat_status_and_tray_controls():
    _, css = _render(_settings())

    assert "button#volume" in css
    assert "button#network" in css
    assert "button#battery" in css
    assert "button#tray_item" in css
    assert "grid#tray" in css
    assert "background: transparent;" in css
    assert "border: none;" in css
    assert "tooltip label" in css
    assert "padding: 6px 8px;" in css


def test_write_assets_creates_drop_in_files(tmp_path):
    config, css = panel.write_assets(tmp_path, _settings())

    assert config.name == "sfwbar.config"
    assert css.name == "sfwbar.css"
    assert config.exists()
    assert css.exists()
    assert config.read_text(encoding="utf-8").startswith("#Api2\n")
    assert "window#sfwbar" in css.read_text(encoding="utf-8")


def test_write_assets_can_render_the_floating_variant(tmp_path):
    _, css = panel.write_assets(tmp_path, _settings(), floating=True)

    text = css.read_text(encoding="utf-8")
    assert "border-radius: 16px;" in text
    assert "rgba(250, 250, 250, 0.90)" in text


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


def test_image_installs_sfwbar_fonts_and_panel_wrapper():
    build_script = (_ROOT / "build_files/build.sh").read_text(encoding="utf-8")

    assert "    sfwbar \\" in build_script
    assert "    adwaita-icon-theme \\" in build_script
    assert "    adwaita-sans-fonts \\" in build_script
    assert "/usr/bin/adwaita-lite-panel" in build_script


def test_legacy_default_layout_migrates_to_the_shelf():
    defaults = json.loads(_DEFAULTS.read_text(encoding="utf-8"))
    assert defaults["layout"] == panel.LEGACY_DEFAULT_LAYOUT
    assert panel.DEFAULT_LAYOUT == panel.SHELF_LAYOUT

    config, _ = _render(_settings(layout=defaults["layout"]))
    assert config.index('style = "launcher"') < config.index('style = "taskbar"')
    assert "NetInfo" in config
    assert "BacklightActual" not in config


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("high_contrast", [False, True])
@pytest.mark.parametrize("twilight", [False, True])
@pytest.mark.parametrize("floating", [False, True])
def test_palette_stays_in_lockstep_with_the_waybar_generator(
    theme, high_contrast, twilight, floating
):
    """The shelf changes geometry/state, but palette semantics stay shared."""
    apply_settings = _load("adwaita_apply_settings", _APPLY)
    settings = _settings(
        theme=theme,
        high_contrast=high_contrast,
        panel_twilight=twilight,
        accent="teal",
    )
    expected = apply_settings._build_tokens(settings)
    actual = panel.build_tokens(settings, floating=floating)

    assert actual["accent"] == expected["accent_hex"]
    assert actual["fg"].lower() == expected["panel_fg"].lower()
    assert _rgba_parts(actual["border"]) == _rgba_parts(expected["panel_border"])
    assert _rgba_parts(actual["surface"])[:3] == _rgba_parts(
        apply_settings._rgba_css(expected["panel_surface"], 1.0)
    )[:3]
    expected_alpha = 0.90 if floating and not high_contrast else 1.0
    assert _rgba_parts(actual["surface"])[3] == pytest.approx(expected_alpha)
