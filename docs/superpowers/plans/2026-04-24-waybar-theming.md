# Waybar ChromeOS Theming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor waybar CSS generation to produce consistent ChromeOS-inspired theming across horizontal and vertical orientations, with a unified common CSS layer and orientation-optimized overrides.

**Architecture:** Three-layer CSS builder — common layer handles shared design language (colors, transitions, pill radius, launcher circle, dot indicator, tooltips), horizontal layer handles bottom/top layout optimization, vertical layer handles left/right layout optimization. A new `group/status` waybar module wraps status modules for the grouped pill effect.

**Tech Stack:** Python (existing `adwaita-lite-apply-settings` script), waybar CSS, waybar `group` module type

**Spec:** `docs/superpowers/specs/2026-04-24-waybar-theming-design.md`

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `files/usr/libexec/adwaita-lite-apply-settings` | Modify | Refactor `_waybar_css_common`, `_waybar_css_horizontal`, `_waybar_css_vertical`; update `write_waybar_config` to add `group/status` module |
| `tests/test_apply_settings.py` | Modify | Update existing CSS assertion tests, add new tests for common CSS, grouped pill, dot indicator |

---

### Task 1: Update `_waybar_css_common` — Shared Design Language

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings:595-657` (`_waybar_css_common`)

This task refactors the common CSS to be the single source of truth for visual styling. It removes orientation-specific logic and adds ChromeOS design elements.

- [ ] **Step 1: Write the failing test for common CSS**

Add to `tests/test_apply_settings.py`:

```python
class TestCommonCssDesign:
    def test_common_has_launcher_circle(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_common(tokens)
        assert "border-radius: 50%" in css

    def test_common_has_dot_indicator(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_common(tokens)
        assert "::after" in css
        assert "width: 6px" in css
        assert "width: 16px" in css

    def test_common_has_transitions(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_common(tokens)
        assert "transition:" in css

    def test_common_pill_radius_on_window(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_common(tokens)
        assert "border-radius: 999px" in css

    def test_common_hover_on_modules(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_common(tokens)
        assert "#custom-launcher:hover" in css
        assert "#clock:hover" in css
        assert "#battery:hover" in css
        assert "#pulseaudio:hover" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestCommonCssDesign -v`
Expected: FAIL — `border-radius: 50%`, `::after`, `transition:` not found in current common CSS.

- [ ] **Step 3: Rewrite `_waybar_css_common`**

Replace the function at `files/usr/libexec/adwaita-lite-apply-settings:595-657` with:

```python
def _waybar_css_common(tokens: dict) -> str:
    pr, pg, pb = _hex_to_rgb_tuple(tokens["panel_surface"])
    fr, fg_, fb = _hex_to_rgb_tuple(tokens["panel_fg"])
    m = tokens["panel_margin"]
    icon_sz = tokens["panel_icon_size"]
    return f"""\
* {{
    font-family: "{tokens["font_ui"]}", "Material Icons Outlined", sans-serif;
    font-size: {tokens["font_size_ui"]}px;
    border: none;
    box-shadow: none;
}}

window#waybar {{
    background: rgba({pr}, {pg}, {pb}, 0.95);
    color: {tokens["panel_fg"]};
    border-radius: 999px;
    margin: {m}px;
}}

/* Material Icons glyphs sized to match theme icons (standard {icon_sz}px) */
#custom-launcher,
#pulseaudio, #backlight, #battery {{
    font-size: {icon_sz}px;
}}

#custom-launcher {{
    border-radius: 50%;
    background: rgba({fr}, {fg_}, {fb}, 0.08);
    transition: background-color 200ms ease;
}}
#custom-launcher:hover {{ background: rgba({fr}, {fg_}, {fb}, 0.15); }}

/* Taskbar dot/pill indicator (ChromeOS-style) */
#taskbar button {{
    position: relative;
    transition: background-color 200ms ease;
}}
#taskbar button::after {{
    content: "";
    position: absolute;
    bottom: 2px;
    left: 50%;
    transform: translateX(-50%);
    width: 6px;
    height: 3px;
    border-radius: 2px;
    background: rgba({fr}, {fg_}, {fb}, 0.25);
    transition: width 200ms ease, background-color 200ms ease;
}}
#taskbar button.active::after {{
    width: 16px;
    background: {tokens["accent_hex"]};
}}
#taskbar button:hover {{ background: {tokens["panel_hover"]}; }}

#battery.warning {{ color: {tokens["color_warning"]}; }}
#battery.critical {{ color: {tokens["color_error"]}; }}
#pulseaudio.muted {{ color: {tokens["panel_secondary_fg"]}; }}

#clock, #battery, #backlight, #pulseaudio, #tray {{
    transition: background-color 200ms ease;
}}
#clock:hover, #battery:hover, #backlight:hover,
#pulseaudio:hover, #tray:hover {{
    background: {tokens["panel_hover"]};
}}

tooltip {{
    background: {tokens["surface_card"]};
    border: 1px solid {tokens["border_default"]};
    border-radius: 8px;
    color: {tokens["text_primary"]};
}}
tooltip label {{
    color: {tokens["text_primary"]};
}}
"""
```

Key changes from current:
- Removed `bar_pad` (window padding) — moved to orientation layers
- Removed hover `border-radius: 999px` overrides from individual modules (common hover no longer sets radius)
- Added `#custom-launcher` circle (50%) with subtle background and hover
- Added `#taskbar button::after` dot indicator (inactive 6px, active 16px accent)
- Added `transition: 200ms ease` on all interactive elements
- Grouped `#taskbar button:hover` into common

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestCommonCssDesign -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "refactor(waybar): rewrite common CSS with ChromeOS design language"
```

---

### Task 2: Update `_waybar_css_horizontal` — Bottom/Top Optimization

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings:660-702` (`_waybar_css_horizontal`)

- [ ] **Step 1: Write failing tests for horizontal CSS**

Add to `tests/test_apply_settings.py`:

```python
class TestHorizontalCss:
    def test_horizontal_pill_radius_on_modules(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "border-radius: 999px" in css

    def test_horizontal_has_min_height_not_min_width(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "min-height" in css
        assert "min-width" not in css

    def test_horizontal_no_border_bottom_active(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "border-bottom:" not in css

    def test_horizontal_window_padding_horizontal_only(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "padding: 0 " in css

    def test_horizontal_pinned_pill_radius(self):
        tokens = _make_tokens(pinned=[
            {"name": "A", "command": "a", "icon": "a"},
            {"name": "B", "command": "b", "icon": "b"},
        ])
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "#image.pin-0" in css
        assert "#image.pin-1" in css
        assert "border-radius: 999px" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestHorizontalCss -v`
Expected: FAIL — `border-bottom:` currently exists, `min-width` assertion may fail, no `min-height` without `min-width` yet.

- [ ] **Step 3: Rewrite `_waybar_css_horizontal`**

Replace the function at `files/usr/libexec/adwaita-lite-apply-settings:660-702` with:

```python
def _waybar_css_horizontal(tokens: dict) -> str:
    h = tokens["panel_height"]
    pl = tokens["panel_pad_launcher"]
    pm = tokens["panel_pad_module"]
    pp = tokens["panel_pad_pin"]
    inset = tokens["panel_bar_inset"]
    pinned = tokens.get("pinned", [])
    fr, fg_, fb = _hex_to_rgb_tuple(tokens["panel_fg"])

    pin_css = ""
    if pinned:
        selectors = ", ".join(f"#image.pin-{i}" for i in range(len(pinned)))
        hover_selectors = ", ".join(f"#image.pin-{i}:hover" for i in range(len(pinned)))
        pin_css = f"""
{selectors} {{
    padding: 0 {pp}px;
    min-height: {h}px;
    border-radius: 999px;
}}
{hover_selectors} {{ background: {tokens["panel_hover"]}; }}
"""

    return f"""
window#waybar {{
    padding: 0 {inset}px;
}}

#custom-launcher {{
    padding: 0 {pl}px;
    min-height: {h}px;
}}

#taskbar {{ padding: 0; }}
#taskbar button {{
    padding: 0 {pp}px;
    border-radius: 999px;
    min-height: {h}px;
}}

{pin_css}
#clock, #battery, #backlight, #pulseaudio, #tray {{
    padding: 0 {pm}px;
    min-height: {h}px;
}}

#clock {{ font-weight: bold; }}

#status {{
    background: rgba({fr}, {fg_}, {fb}, 0.06);
    border-radius: 999px;
    padding: 0 4px;
}}
#status > * {{
    background: transparent;
    border-radius: 999px;
    transition: background-color 200ms ease;
}}
#status > *:hover {{
    background: rgba({fr}, {fg_}, {fb}, 0.08);
    border-radius: 999px;
}}
"""
```

Key changes:
- Added `window#waybar` padding override (horizontal-only)
- Removed `border-bottom: 3px solid` from `#taskbar button.active` — dot indicator from common handles this
- Removed `accent_rgba_15` background from `#taskbar button.active` — dot indicator replaces it
- Removed `#taskbar button.active` rule entirely (common handles it)
- All modules use `border-radius: 999px` consistently

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestHorizontalCss -v`
Expected: PASS

- [ ] **Step 5: Run all tests to check no regressions**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`
Expected: Some tests in `TestVerticalCssBorder` will fail (they assert `border-bottom:`/`border-right:`/`border-left:` which we removed). This is expected — Task 3 fixes those.

- [ ] **Step 6: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "refactor(waybar): rewrite horizontal CSS with pill consistency"
```

---

### Task 3: Update `_waybar_css_vertical` — Left/Right Optimization

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings:705-771` (`_waybar_css_vertical`)

- [ ] **Step 1: Rewrite tests for vertical CSS**

Replace the `TestVerticalCssBorder` class in `tests/test_apply_settings.py` with:

```python
class TestVerticalCss:
    def test_vertical_has_min_width_and_min_height(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        assert "min-width" in css
        assert "min-height" in css

    def test_vertical_pill_radius_on_modules(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        assert "border-radius: 999px" in css

    def test_vertical_no_border_direction(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        assert "border-right:" not in css
        assert "border-left:" not in css
        assert "border-bottom:" not in css

    def test_vertical_window_has_min_width(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        assert "min-width:" in css

    def test_vertical_window_padding_both_axes(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        inset = tokens["panel_bar_inset"]
        assert f"padding: {inset}px {inset // 2}px" in css

    def test_vertical_pinned_pill_radius(self):
        tokens = _make_tokens(edge="left", is_vertical=True, pinned=[
            {"name": "A", "command": "a", "icon": "a"},
        ])
        css = apply_settings._waybar_css_vertical(tokens)
        assert "#image.pin-0" in css
        assert "border-radius: 999px" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestVerticalCss -v`
Expected: FAIL — current vertical CSS uses `border-right:`/`border-left:`, `10px` radius, not `999px`.

- [ ] **Step 3: Rewrite `_waybar_css_vertical`**

Replace the function at `files/usr/libexec/adwaita-lite-apply-settings:705-771` with:

```python
def _waybar_css_vertical(tokens: dict) -> str:
    w = tokens["panel_width"]
    pm = tokens["panel_pad_module"]
    inset = tokens["panel_bar_inset"]
    pinned = tokens.get("pinned", [])
    btn_w = max(w - 2 * inset, 16)
    fr, fg_, fb = _hex_to_rgb_tuple(tokens["panel_fg"])

    pin_css = ""
    if pinned:
        selectors = ", ".join(f"#image.pin-{i}" for i in range(len(pinned)))
        hover_selectors = ", ".join(f"#image.pin-{i}:hover" for i in range(len(pinned)))
        pin_css = f"""
{selectors} {{
    padding: {pm}px {inset}px;
    min-width: {btn_w}px;
    min-height: {btn_w}px;
    border-radius: 999px;
}}
{hover_selectors} {{ background: {tokens["panel_hover"]}; }}
"""

    return f"""
window#waybar {{
    min-width: {w}px;
    padding: {inset}px {inset // 2}px;
}}

#custom-launcher {{
    padding: {pm}px {inset}px;
    min-width: {btn_w}px;
    min-height: {btn_w}px;
}}

#taskbar {{ padding: 0; }}
#taskbar button {{
    padding: {pm}px {inset}px;
    border-radius: 999px;
    min-width: {btn_w}px;
    min-height: {btn_w}px;
}}

{pin_css}
#clock, #battery, #backlight, #pulseaudio, #tray {{
    padding: {pm}px {inset}px;
    min-width: {btn_w}px;
    min-height: {btn_w}px;
}}

#clock {{ font-weight: bold; }}

#status {{
    background: rgba({fr}, {fg_}, {fb}, 0.06);
    border-radius: 999px;
    padding: 4px 0;
}}
#status > * {{
    background: transparent;
    border-radius: 999px;
    transition: background-color 200ms ease;
}}
#status > *:hover {{
    background: rgba({fr}, {fg_}, {fb}, 0.08);
    border-radius: 999px;
}}
"""
```

Key changes:
- Removed `active_border` direction logic (`border-right`/`border-left`) — dot indicator from common replaces it
- Changed all `border-radius: 10` to `border-radius: 999px` for pill consistency
- Removed hover radius override (common hover no longer sets radius, so no conflict)
- Window padding uses both axes for vertical
- All modules constrained to `btn_w` width

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "refactor(waybar): rewrite vertical CSS with pill consistency"
```

---

### Task 4: Add `group/status` Module to Waybar Config

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings:781-930` (`write_waybar_config`)

This task adds the waybar `group/status` module that wraps status modules (pulseaudio, backlight, battery, clock) for the grouped pill effect.

- [ ] **Step 1: Write failing test for group/status config**

Add to `tests/test_apply_settings.py`:

```python
class TestStatusGroup:
    def test_group_status_in_config(self, tmp_path):
        tokens = _make_tokens()
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        assert "group/status" in config

    def test_group_status_orientation_horizontal(self, tmp_path):
        tokens = _make_tokens()
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        assert config["group/status"]["orientation"] == "horizontal"

    def test_group_status_orientation_vertical(self, tmp_path):
        tokens = _make_tokens(edge="left", is_vertical=True)
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        assert config["group/status"]["orientation"] == "vertical"

    def test_status_modules_in_group(self, tmp_path):
        tokens = _make_tokens()
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        group_modules = config["group/status"]["modules"]
        for mod in ["pulseaudio", "backlight", "battery", "clock"]:
            assert mod in group_modules

    def test_tray_not_in_group(self, tmp_path):
        tokens = _make_tokens()
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        group_modules = config["group/status"]["modules"]
        assert "tray" not in group_modules

    def test_module_list_uses_group_not_individual(self, tmp_path):
        tokens = _make_tokens()
        with patch.object(apply_settings, "WAYBAR_DIR", tmp_path):
            apply_settings.write_waybar_config(tokens)
        config = json.loads((tmp_path / "config.jsonc").read_text())
        all_modules = config["modules-left"] + config["modules-center"] + config["modules-right"]
        for mod in ["pulseaudio", "backlight", "battery", "clock"]:
            assert mod not in all_modules
        assert "group/status" in all_modules
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestStatusGroup -v`
Expected: FAIL — `group/status` not in current config.

- [ ] **Step 3: Update `write_waybar_config` to add group/status**

In `files/usr/libexec/adwaita-lite-apply-settings`, in the `write_waybar_config` function (starting around line 781), add the following logic after the module lists are built (after line 808 where pin injection happens) but before the config dict is created:

After pin injection (line ~808) and before the config dict, insert status module grouping:

```python
    STATUS_MODULES = frozenset(["pulseaudio", "backlight", "battery", "clock"])
    all_modules_flat = modules_left + modules_center + modules_right
    status_in_layout = [m for m in all_modules_flat if m in STATUS_MODULES]

    if status_in_layout:
        def _inject_status_group(mlist):
            indices = [i for i, m in enumerate(mlist) if m in STATUS_MODULES]
            if not indices:
                return mlist
            first, last = indices[0], indices[-1]
            between = mlist[first:last + 1]
            if any(m not in STATUS_MODULES for m in between):
                return mlist
            return mlist[:first] + ["group/status"] + mlist[last + 1:]

        modules_left = _inject_status_group(modules_left)
        modules_center = _inject_status_group(modules_center)
        modules_right = _inject_status_group(modules_right)
```

Then in the config dict section, after `config["tray"]` (line ~920), add:

```python
    if status_in_layout:
        config["group/status"] = {
            "orientation": "vertical" if is_vertical else "horizontal",
            "modules": status_in_layout,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py::TestStatusGroup -v`
Expected: PASS

- [ ] **Step 5: Run all tests**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add files/usr/libexec/adwaita-lite-apply-settings tests/test_apply_settings.py
git commit -m "feat(waybar): add group/status module for grouped status pill"
```

---

### Task 5: Add Grouped Status Pill CSS Tests

**Files:**
- Modify: `tests/test_apply_settings.py`

The `#status` CSS is already included in the functions from Tasks 2 and 3. This task adds the corresponding tests.

- [ ] **Step 1: Add grouped pill tests**

Add to `tests/test_apply_settings.py`:

```python
class TestGroupedPillCss:
    def test_horizontal_group_pill_background(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "#status" in css
        assert "#status > *" in css

    def test_vertical_group_pill_background(self):
        tokens = _make_tokens(edge="left", is_vertical=True)
        css = apply_settings._waybar_css_vertical(tokens)
        assert "#status" in css
        assert "#status > *" in css

    def test_group_has_transparent_children(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "background: transparent" in css

    def test_group_children_hover(self):
        tokens = _make_tokens()
        css = apply_settings._waybar_css_horizontal(tokens)
        assert "#status > *:hover" in css
```

- [ ] **Step 2: Run full test suite**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_apply_settings.py
git commit -m "test(waybar): add grouped status pill CSS tests"
```

---

### Task 6: Fix Existing Tests and Verify Full Suite

**Files:**
- Modify: `tests/test_apply_settings.py`

- [ ] **Step 1: Run full test suite to identify any remaining failures**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`

- [ ] **Step 2: Fix any failing tests**

The tests from `TestPinInjection` reference `custom/pin-0` but the actual module names are `image#pin-0`. Verify these tests still pass. If any test references the old `border-bottom:`/`border-left:`/`border-right:` assertions in `TestVerticalCssBorder`, those have been replaced in Task 3.

If `TestConfigChangeDetection` tests fail because the CSS output changed format, update the assertions to check the new format. These tests compare full re-writes, so they should still pass as long as the same tokens produce the same output.

- [ ] **Step 3: Run full test suite**

Run: `cd /var/home/race/ublue-mike && python -m pytest tests/test_apply_settings.py -v`
Expected: ALL PASS, 0 failures

- [ ] **Step 4: Commit**

```bash
git add tests/test_apply_settings.py
git commit -m "test(waybar): update tests for ChromeOS theming consistency"
```
