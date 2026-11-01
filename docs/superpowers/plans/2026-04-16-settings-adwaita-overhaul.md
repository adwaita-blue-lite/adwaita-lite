# Settings App Adwaita Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the settings app visually match GNOME Settings (Adwaita) using pure GTK 4 — boxed-list groups, proper color hierarchy, CSD headerbar, content clamping — and add minimize/maximize/close buttons system-wide.

**Architecture:** CSS rewrite for Adwaita color hierarchy + boxed-list card pattern. New `make_group()` helper in BasePage wraps widgets in styled card containers. HeaderBar replaces server-side decoration. All 15 pages get mechanical migration from `make_group_label()` to `make_group()`. apply-settings writes `gtk-decoration-layout` for system-wide window buttons.

**Tech Stack:** GTK 4, CSS, Python. No libadwaita.

**Spec:** `docs/superpowers/specs/2026-04-16-settings-adwaita-overhaul-design.md`

---

### Task 1: Rewrite CSS for Adwaita color hierarchy and boxed-list cards

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/css/style.css`

This is the foundation — all other tasks depend on the classes defined here.

- [ ] **Step 1: Replace the entire `style.css` with the Adwaita-aligned version**

```css
/* === Sidebar === */
.sidebar {
    background-color: @headerbar_bg_color;
    border-right: 1px solid alpha(@borders, 0.3);
}
.sidebar row {
    padding: 12px 16px;
    margin: 2px 8px;
    border-radius: 8px;
}
.sidebar row:selected {
    background-color: alpha(@accent_color, 0.15);
}
.sidebar .category-icon {
    margin-end: 12px;
    opacity: 0.8;
}
.sidebar .category-label {
    font-size: 14px;
}

/* === Content area === */
.content-area {
    background-color: @window_bg_color;
}
.content-page {
    max-width: 640px;
    margin-left: auto;
    margin-right: auto;
    padding: 32px 16px;
}

/* === Boxed-list group cards === */
.group-title {
    font-size: 13px;
    font-weight: bold;
    opacity: 0.8;
    margin-bottom: 6px;
    margin-start: 4px;
}
.boxed-list {
    background-color: @card_bg_color;
    border-radius: 12px;
    border: 1px solid alpha(@borders, 0.3);
}
.boxed-list > row,
.boxed-list > box {
    padding: 12px 16px;
    min-height: 48px;
}
.boxed-list > row:first-child,
.boxed-list > box:first-child {
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}
.boxed-list > row:last-child,
.boxed-list > box:last-child {
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
.boxed-list > row:not(:first-child),
.boxed-list > box:not(:first-child) {
    border-top: 1px solid alpha(@borders, 0.15);
}

/* === Setting rows === */
.setting-row {
    min-height: 48px;
}
.setting-subtitle {
    font-size: 12px;
    opacity: 0.6;
}

/* === Toggle cards === */
.toggle-card {
    padding: 16px 24px;
    border-radius: 12px;
    border: 2px solid alpha(@borders, 0.5);
    background: none;
}
.toggle-card:checked {
    border-color: @accent_color;
    background: alpha(@accent_color, 0.08);
}

/* === Accent color circles === */
.accent-circle {
    min-width: 32px;
    min-height: 32px;
    border-radius: 16px;
    padding: 0;
}
.accent-circle:checked {
    box-shadow: 0 0 0 3px @accent_color;
}
.accent-blue { background-color: #3584e4; }
.accent-teal { background-color: #2190a4; }
.accent-green { background-color: #3a944a; }
.accent-yellow { background-color: #c88800; }
.accent-orange { background-color: #ed5b00; }
.accent-red { background-color: #e62d42; }
.accent-pink { background-color: #d56199; }
.accent-purple { background-color: #9141ac; }
.accent-slate { background-color: #6f8396; }

/* === Toast notifications === */
.toast {
    background-color: @headerbar_bg_color;
    color: @theme_fg_color;
    border-radius: 8px;
    padding: 8px 16px;
    box-shadow: 0 2px 8px alpha(black, 0.15);
    border: 1px solid alpha(@borders, 0.3);
}
.toast-error {
    background-color: #c01c28;
    color: white;
    border-color: #c01c28;
}

/* === Dialogs === */
.dialog-overlay {
    background-color: alpha(black, 0.5);
}
.dialog-card {
    background-color: @card_bg_color;
    border-radius: 12px;
    border: 1px solid alpha(@borders, 0.3);
    box-shadow: 0 4px 16px alpha(black, 0.2);
    padding: 24px;
    min-width: 360px;
}
.dialog-title {
    font-size: 18px;
    font-weight: bold;
}
.dialog-subtitle {
    font-size: 13px;
    opacity: 0.7;
    margin-bottom: 8px;
}

/* === Destructive actions === */
.destructive-button {
    color: #c01c28;
}
.destructive-button:hover {
    background-color: alpha(#c01c28, 0.1);
}
```

- [ ] **Step 2: Verify CSS syntax**

Run: `python3 -c "open('files/usr/lib/adwaita-lite/settings/css/style.css').read(); print('OK')"`

- [ ] **Step 3: Commit**

```
git add files/usr/lib/adwaita-lite/settings/css/style.css
git commit -m "style: rewrite settings CSS for Adwaita color hierarchy and boxed-list cards"
```

---

### Task 2: Update BasePage with `make_group()` and `make_page_box()` changes

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/base.py`

- [ ] **Step 1: Update `make_page_box()` to use content-page class instead of hardcoded margins**

In `base.py`, replace the existing `make_page_box()` static method:

```python
@staticmethod
def make_page_box() -> Gtk.Box:
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
    page.add_css_class("content-page")
    return page
```

This removes the hardcoded `margin_top/bottom/start/end` and uses the CSS class instead (which provides `max-width: 640px`, `margin: auto`, `padding: 32px 16px`).

- [ ] **Step 2: Add `make_group()` method**

Add this new static method to `BasePage`, after `make_page_box()`:

```python
@staticmethod
def make_group(title: str, children: list[Gtk.Widget]) -> Gtk.Box:
    """Build an Adwaita-style boxed-list group: title label + card container."""
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    if title:
        lbl = Gtk.Label(label=title, xalign=0)
        lbl.add_css_class("group-title")
        lbl.set_margin_bottom(6)
        outer.append(lbl)
    card = Gtk.ListBox()
    card.set_selection_mode(Gtk.SelectionMode.NONE)
    card.add_css_class("boxed-list")
    for child in children:
        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_child(child)
        card.append(row)
    outer.append(card)
    return outer
```

- [ ] **Step 3: Update `make_setting_row()` to remove standalone padding**

The setting-row padding is now handled by the boxed-list card. Update `make_setting_row()`:

```python
@staticmethod
def make_setting_row(label: str, subtitle: str, control: Gtk.Widget) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    row.add_css_class("setting-row")
    row.set_valign(Gtk.Align.CENTER)
    left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    left.set_hexpand(True)
    left.set_valign(Gtk.Align.CENTER)
    lbl = Gtk.Label(label=label, xalign=0)
    left.append(lbl)
    if subtitle:
        sub = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        sub.add_css_class("setting-subtitle")
        left.append(sub)
    row.append(left)
    control.set_valign(Gtk.Align.CENTER)
    row.append(control)
    return row
```

(This is the same as before but without standalone `padding: 8px 0` from CSS — the CSS class `.setting-row` now only sets `min-height: 48px`.)

- [ ] **Step 4: Commit**

```
git add files/usr/lib/adwaita-lite/settings/base.py
git commit -m "feat: add make_group() boxed-list helper and content-page clamping"
```

---

### Task 3: Add HeaderBar with search toggle to SettingsWindow

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/window.py`

- [ ] **Step 1: Add HeaderBar and move search bar**

Replace the `__init__` method of `SettingsWindow`. The key changes are:
1. Create a `Gtk.HeaderBar` and set it as the titlebar
2. Add a search toggle button to the headerbar
3. Move the `Gtk.SearchBar` from the sidebar to below the headerbar (inside the main content)
4. Add `content-area` CSS class to the content scroll area

```python
class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, store: SettingsStore, event_bus: EventBus) -> None:
        super().__init__(application=app)
        self.set_title(_("Settings"))
        self.set_default_size(900, 600)
        self.set_size_request(700, 500)

        self._store = store
        self._event_bus = event_bus
        self._page_names: list[str] = []
        self._pages: list = []

        # --- HeaderBar ---
        header = Gtk.HeaderBar()
        search_btn = Gtk.ToggleButton()
        search_btn.set_icon_name("system-search-symbolic")
        search_btn.set_tooltip_text(_("Search settings"))
        header.pack_end(search_btn)
        self.set_titlebar(header)

        # Toast overlay wraps everything
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        self._toast = ToastWidget()
        overlay.add_overlay(self._toast)
        store.set_toast_callback(self._toast.show_toast)

        # Main vertical layout: search bar + paned
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        overlay.set_child(main_box)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(_("Search settings\u2026"))
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._search_entry.connect("search-changed", self._on_search_changed)
        search_btn.bind_property("active", self._search_bar, "search-mode-enabled",
                                 GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE)
        main_box.append(self._search_bar)

        # Main paned layout
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(220)
        paned.set_shrink_start_child(False)
        paned.set_shrink_end_child(False)
        paned.set_vexpand(True)
        main_box.append(paned)

        # --- Sidebar ---
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_box.set_size_request(220, -1)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_vexpand(True)

        self._sidebar = Gtk.ListBox()
        self._sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._sidebar.add_css_class("sidebar")
        self._sidebar.set_margin_top(8)
        self._sidebar.set_margin_bottom(8)
        sidebar_scroll.set_child(self._sidebar)
        sidebar_box.append(sidebar_scroll)
        paned.set_start_child(sidebar_box)

        # --- Content stack ---
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        self._content_scroll = Gtk.ScrolledWindow()
        self._content_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._content_scroll.set_child(self._stack)
        self._content_scroll.set_hexpand(True)
        self._content_scroll.set_vexpand(True)
        self._content_scroll.add_css_class("content-area")
        paned.set_end_child(self._content_scroll)

        # Build pages from registry
        self._build_pages()

        self._sidebar.connect("row-selected", self._on_row_selected)
        first = self._sidebar.get_row_at_index(0)
        if first is not None:
            self._sidebar.select_row(first)

        search_action = Gio.SimpleAction.new("search", None)
        search_action.connect("activate", lambda *_: self.toggle_search())
        self.add_action(search_action)
```

- [ ] **Step 2: Add GObject import**

At the top of `window.py`, add the GObject import needed for `bind_property`:

```python
from gi.repository import GObject, Gio, Gtk
```

- [ ] **Step 3: Update toggle_search to use the search bar property**

```python
def toggle_search(self) -> None:
    active = self._search_bar.get_search_mode()
    self._search_bar.set_search_mode(not active)
    if not active:
        self._search_entry.grab_focus()
```

(This stays the same — the `bind_property` keeps the header button in sync.)

- [ ] **Step 4: Commit**

```
git add files/usr/lib/adwaita-lite/settings/window.py
git commit -m "feat: add CSD headerbar with search toggle to settings app"
```

---

### Task 4: Add `gtk-decoration-layout` to apply-settings

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-apply-settings` (in `write_gtk_settings()`)

- [ ] **Step 1: Add decoration-layout line to GTK settings output**

In the `write_gtk_settings()` function, after line 725 (`gtk-enable-animations`), add:

```python
            handle.write("gtk-decoration-layout=menu:minimize,maximize,close\n")
```

The full write block becomes:
```python
        with (directory / "settings.ini").open("w", encoding="utf-8") as handle:
            handle.write("[Settings]\n")
            handle.write(f"gtk-application-prefer-dark-theme={dark_pref}\n")
            handle.write(f"gtk-theme-name={theme_name}\n")
            handle.write(f"gtk-icon-theme-name={icon_theme}\n")
            handle.write(f"gtk-font-name=Roboto {tokens['font_size_mono']}\n")
            handle.write("gtk-cursor-theme-name=Adwaita\n")
            handle.write(f"gtk-cursor-theme-size={tokens['cursor_size']}\n")
            handle.write(f"gtk-enable-animations={'1' if not tokens['reduce_motion'] else '0'}\n")
            handle.write("gtk-decoration-layout=menu:minimize,maximize,close\n")
```

- [ ] **Step 2: Commit**

```
git add files/usr/libexec/adwaita-lite-apply-settings
git commit -m "feat: add minimize/maximize/close buttons to all GTK CSD apps"
```

---

### Task 5: Migrate Appearance, Display, and Network pages

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/appearance.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/display.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/network.py`

- [ ] **Step 1: Migrate AppearancePage**

Replace all `make_group_label()` + widget append patterns with `make_group()`. Read the current file, then transform:

**Theme group** — toggle cards are the sole child:
```python
page.append(self.make_group(_("Theme"), [self.make_toggle_cards(
    [("light", _("Light")), ("dark", _("Dark"))],
    self.store.get("theme", "light"),
    lambda v: self.store.save_and_apply("theme", v),
)]))
```

If high contrast note exists, append it as a second child of the group:
```python
children = [self.make_toggle_cards(...)]
if self.store.get("high_contrast", False):
    note = Gtk.Label(label=_("Theme is set to Dark by High Contrast mode"), xalign=0)
    note.add_css_class("setting-subtitle")
    children.append(note)
page.append(self.make_group(_("Theme"), children))
```

**Accent color group** — the accent_box is the sole child:
```python
page.append(self.make_group(_("Accent color"), [accent_box]))
```

**Font size group** — the setting row is the sole child:
```python
page.append(self.make_group(_("Font size"), [
    self.make_setting_row(_("Font size"), _("Affects all text throughout the interface"), font_dd),
]))
```

**Wallpaper group** — the FlowBox + custom button:
```python
page.append(self.make_group(_("Wallpaper"), [flow]))
```

Remove all `page.append(self.make_group_label(...))` calls — they are replaced by the title parameter in `make_group()`.

- [ ] **Step 2: Migrate DisplayPage**

Read `display.py` and transform. The page has 4 groups:

1. **Display Scale** — toggle cards:
```python
page.append(self.make_group(_("Display Scale"), [self.make_toggle_cards(...)]))
```

2. **Resolution & Refresh Rate** — dynamic display rows. Since displays are detected at build time and may have variable count, build the children list first:
```python
display_children = []
# ... existing display detection loop ...
for output_name, modes in displays:
    display_children.append(self.make_setting_row(output_name, "", dropdown))
if not display_children:
    display_children.append(Gtk.Label(label=_("No displays detected"), xalign=0))
page.append(self.make_group(_("Resolution & Refresh Rate"), display_children))
```

3. **Night Light** — multiple setting rows:
```python
page.append(self.make_group(_("Night Light"), [
    self.make_setting_row(_("Night Light"), _("..."), nl_switch),
    self.make_setting_row(_("Color Temperature"), "", temp_scale),
    self.make_setting_row(_("Schedule"), "", schedule_dd),
    time_box,  # custom start/end time box
]))
```

4. **Advanced** — single button:
```python
page.append(self.make_group(_("Advanced"), [wdisplays_btn]))
```

- [ ] **Step 3: Migrate NetworkPage**

Read `network.py` and transform. The network page has some special patterns (inline group-label+switch combos). Transform:

1. **WiFi** group with the switch, status label, network list, and buttons all as children
2. **Active Connection** group
3. **Wired** group
4. **Advanced** button

For groups where the title has an inline switch (WiFi, Bluetooth), create the group without a title and add a custom header row instead:
```python
wifi_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
wifi_label = Gtk.Label(label=_("WiFi"), xalign=0)
wifi_label.set_hexpand(True)
wifi_header.append(wifi_label)
wifi_header.append(wifi_switch)
page.append(self.make_group("", [wifi_header, status_label, network_list, button_box]))
```

Or use the title parameter and put the switch as the first row.

- [ ] **Step 4: Commit**

```
git add files/usr/lib/adwaita-lite/settings/pages/appearance.py \
        files/usr/lib/adwaita-lite/settings/pages/display.py \
        files/usr/lib/adwaita-lite/settings/pages/network.py
git commit -m "style: migrate Appearance, Display, Network pages to boxed-list groups"
```

---

### Task 6: Migrate Bluetooth, Panel, and Mouse/Touchpad pages

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/bluetooth.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/panel.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py`

- [ ] **Step 1: Migrate BluetoothPage**

Similar to NetworkPage — Bluetooth has an inline switch with the group title. Use the same pattern as WiFi (title-less group with a custom header row).

Paired Devices and Available Devices groups wrap their ListBoxes:
```python
page.append(self.make_group(_("Paired Devices"), [self._paired_list]))
page.append(self.make_group(_("Available Devices"), [self._available_list]))
```

The scan and advanced buttons go in a final group or standalone.

- [ ] **Step 2: Migrate PanelPage**

Panel has 5 groups. Read `panel.py` (already in context from earlier) and transform:

```python
# Position
page.append(self.make_group(_("Position"), [self.make_toggle_cards(...)]))

# Density
page.append(self.make_group(_("Density"), [self.make_toggle_cards(...)]))

# Twilight — single setting row
page.append(self.make_group("", [self.make_setting_row(
    _("Twilight"),
    _("Invert panel colors from the system theme"),
    twilight,
)]))

# Module Layout — the scrolled widget
page.append(self.make_group(_("Module Layout"), [self._build_module_layout()]))

# Pinned Apps
page.append(self.make_group(_("Pinned Apps"), [self._build_pinned_apps()]))

# Reset button
page.append(self.make_group("", [reset_btn]))
```

- [ ] **Step 3: Migrate MouseTouchpadPage**

```python
# Touchpad group — multiple setting rows
page.append(self.make_group(_("Touchpad"), [
    self.make_setting_row(_("Tap to click"), "", tap_switch),
    self.make_setting_row(_("Natural scrolling"), "", nat_switch),
    self.make_setting_row(_("Pointer speed"), "", speed_scale),
    self.make_setting_row(_("Scroll speed"), "", scroll_scale),
]))

# Mouse group — multiple setting rows + toggle cards
page.append(self.make_group(_("Mouse"), [
    self.make_setting_row(_("Natural scrolling"), "", m_nat_switch),
    self.make_setting_row(_("Pointer speed"), "", m_speed_scale),
    self.make_setting_row(_("Acceleration profile"), "", self.make_toggle_cards(...)),
]))
```

- [ ] **Step 4: Commit**

```
git add files/usr/lib/adwaita-lite/settings/pages/bluetooth.py \
        files/usr/lib/adwaita-lite/settings/pages/panel.py \
        files/usr/lib/adwaita-lite/settings/pages/mouse_touchpad.py
git commit -m "style: migrate Bluetooth, Panel, Mouse/Touchpad pages to boxed-list groups"
```

---

### Task 7: Migrate Keyboard, Sound, and Power/Lock pages

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/keyboard.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/sound.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/power_lock.py`

- [ ] **Step 1: Migrate KeyboardPage**

4 groups:
```python
# Layout
page.append(self.make_group(_("Layout"), [
    self.make_setting_row(_("Layout"), "", layout_dd),
    self.make_setting_row(_("Variant"), "", variant_dd),
]))

# Repeat
page.append(self.make_group(_("Repeat"), [
    self.make_setting_row(_("Repeat delay"), _("..."), delay_scale),
    self.make_setting_row(_("Repeat rate"), _("..."), rate_scale),
]))

# Caps Lock
page.append(self.make_group(_("Caps Lock Behavior"), [
    self.make_setting_row(_("Caps Lock"), "", caps_dd),
]))

# Shortcuts — dynamic rows in a group
shortcut_children = [self._build_shortcut_row(b) for b in bindings]
shortcut_children.append(reset_btn)
page.append(self.make_group(_("Keyboard Shortcuts"), shortcut_children))
```

- [ ] **Step 2: Migrate SoundPage**

2 groups:
```python
# Output
page.append(self.make_group(_("Output"), [
    self.make_setting_row(_("Device"), "", output_dd),
    self.make_setting_row(_("Volume"), "", vol_scale),
    self.make_setting_row(_("Mute"), "", mute_switch),
]))

# Input
page.append(self.make_group(_("Input"), [
    self.make_setting_row(_("Device"), "", input_dd),
    self.make_setting_row(_("Volume"), "", input_vol_scale),
    self.make_setting_row(_("Mute"), "", input_mute_switch),
]))
```

- [ ] **Step 3: Migrate PowerLockPage**

4 groups:
```python
page.append(self.make_group(_("Lock & Display"), [
    self.make_setting_row(_("Lock screen after"), "", lock_dd),
    self.make_setting_row(_("Turn off display after"), "", dpms_dd),
]))

page.append(self.make_group(_("Power Profile"), [self.make_toggle_cards(...)]))

page.append(self.make_group(_("Suspend on Idle"), [
    self.make_setting_row(_("Suspend after"), "", suspend_dd),
]))

page.append(self.make_group(_("Lid Close Behavior"), [
    self.make_setting_row(_("When lid is closed"), "", lid_dd),
]))
```

- [ ] **Step 4: Commit**

```
git add files/usr/lib/adwaita-lite/settings/pages/keyboard.py \
        files/usr/lib/adwaita-lite/settings/pages/sound.py \
        files/usr/lib/adwaita-lite/settings/pages/power_lock.py
git commit -m "style: migrate Keyboard, Sound, Power/Lock pages to boxed-list groups"
```

---

### Task 8: Migrate remaining pages (Accessibility, Date/Time, Users, Language, Default Apps, About)

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/pages/accessibility.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/datetime.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/users.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/language.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/default_apps.py`
- Modify: `files/usr/lib/adwaita-lite/settings/pages/about.py`

- [ ] **Step 1: Migrate AccessibilityPage**

Single group with multiple setting rows:
```python
page.append(self.make_group(_("Accessibility"), [
    self.make_setting_row(_("Large text"), "", large_text_switch),
    self.make_setting_row(_("Cursor size"), "", cursor_dd),
    self.make_setting_row(_("High contrast"), "", hc_switch),
    self.make_setting_row(_("Reduce motion"), "", motion_switch),
]))
```

- [ ] **Step 2: Migrate DateTimePage**

Single group:
```python
page.append(self.make_group(_("Date & Time"), [
    self.make_setting_row(_("Current time"), "", time_label),
    self.make_setting_row(_("Timezone"), "", tz_entry),
    self.make_setting_row(_("Automatic time"), _("..."), ntp_switch),
    self.make_setting_row(_("24-hour clock"), "", clock_switch),
]))
```

- [ ] **Step 3: Migrate UsersPage**

Single group:
```python
page.append(self.make_group(_("Users"), [
    self.make_setting_row(_("Display name"), "", name_entry),
    self.make_setting_row(_("Password"), "", pw_button),
    self.make_setting_row(_("Auto-login"), "", autologin_switch),
]))
```

- [ ] **Step 4: Migrate LanguagePage**

Single group with info banner:
```python
info = Gtk.Label(label=_("Changes take effect after logging out"), xalign=0)
info.add_css_class("setting-subtitle")
page.append(self.make_group(_("Language & Region"), [
    info,
    self.make_setting_row(_("Language"), "", lang_dd),
    self.make_setting_row(_("Formats"), "", fmt_dd),
]))
```

- [ ] **Step 5: Migrate DefaultAppsPage**

Single group with dynamic rows:
```python
app_rows = []
for label, mime_type, dropdown in self._build_app_rows():
    app_rows.append(self.make_setting_row(label, "", dropdown))
page.append(self.make_group(_("Default Applications"), app_rows))
```

- [ ] **Step 6: Migrate AboutPage**

3 groups:
```python
# About — info rows
info_rows = [self.make_info_row(k, v) for k, v in system_info]
page.append(self.make_group(_("About"), info_rows))

# Updates
page.append(self.make_group(_("Updates"), [status_label, check_btn]))

# Troubleshooting
page.append(self.make_group(_("Troubleshooting"), [desc_label, restore_btn]))
```

- [ ] **Step 7: Commit**

```
git add files/usr/lib/adwaita-lite/settings/pages/accessibility.py \
        files/usr/lib/adwaita-lite/settings/pages/datetime.py \
        files/usr/lib/adwaita-lite/settings/pages/users.py \
        files/usr/lib/adwaita-lite/settings/pages/language.py \
        files/usr/lib/adwaita-lite/settings/pages/default_apps.py \
        files/usr/lib/adwaita-lite/settings/pages/about.py
git commit -m "style: migrate remaining pages to boxed-list groups"
```

---

### Task 9: Remove dead code and final cleanup

**Files:**
- Modify: `files/usr/lib/adwaita-lite/settings/base.py`

- [ ] **Step 1: Remove `make_group_label()` if no longer used**

After all pages are migrated, check if `make_group_label()` is still referenced anywhere:

```bash
grep -r "make_group_label" files/usr/lib/adwaita-lite/settings/
```

If no results, remove the method from `BasePage`. If some pages still use it (e.g. for non-standard layouts), keep it.

- [ ] **Step 2: Verify Python syntax across all modified files**

```bash
python3 -m py_compile files/usr/lib/adwaita-lite/settings/base.py
python3 -m py_compile files/usr/lib/adwaita-lite/settings/window.py
for f in files/usr/lib/adwaita-lite/settings/pages/*.py; do python3 -m py_compile "$f"; done
```

All should compile with no errors.

- [ ] **Step 3: Commit and push**

```
git add -u files/usr/lib/adwaita-lite/settings/
git commit -m "refactor: remove unused make_group_label after boxed-list migration"
git push
```
