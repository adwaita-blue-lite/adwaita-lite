# Wizard Network + Flatpak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a WiFi network configuration page and first-boot Flatpak installation to the Adwaita-Lite setup wizard, replacing the standalone Flatpak systemd service.

**Architecture:** The existing 3-page GTK4 wizard (`files/usr/bin/adwaita-lite-setup-wizard`) expands to 6 pages: Network -> Account -> System -> Apps -> Confirm -> Progress. Network uses libnm (`gi.repository.NM`) for WiFi scan/connect with auto-skip on existing connectivity. Progress page replaces the inline status pattern with a step-runner that provides per-step feedback, retry/skip for Flatpak failures, and a manual Reboot button on success.

**Tech Stack:** Python 3 / GTK4 / libnm (gi.repository.NM) / Flatpak CLI / AccountsService D-Bus

**Spec:** `docs/superpowers/specs/2026-03-25-wizard-network-and-flatpak-design.md`

**Note:** This project has no test framework. The wizard runs as root inside a cage (kiosk Wayland compositor) at first boot. Verification is syntax-checking (`python3 -c "import ast; ast.parse(open(...).read())"`) and manual testing in the real environment or GNOME Boxes.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `files/usr/bin/adwaita-lite-setup-wizard` | Modify | All wizard logic: new pages, navigation, NM integration, step runner |
| `build_files/build.sh` | Modify | Add `NetworkManager-libnm` + `flatpak` packages; remove flatpak-setup refs |
| `files/usr/libexec/adwaita-lite-session-init` | Modify | Remove stamp file notification block (lines 53-60) |
| `files/etc/systemd/system/adwaita-lite-flatpak-setup.service` | Delete | Replaced by wizard |
| `files/usr/libexec/adwaita-lite-flatpak-setup` | Delete | Replaced by wizard |

---

### Task 1: Infrastructure cleanup — remove Flatpak service, update build

Delete the standalone Flatpak provisioning path and add new package dependencies. This is a standalone change with no code dependencies on the wizard.

**Files:**
- Delete: `files/etc/systemd/system/adwaita-lite-flatpak-setup.service`
- Delete: `files/usr/libexec/adwaita-lite-flatpak-setup`
- Modify: `build_files/build.sh:17-78` (dnf5 install list), `build_files/build.sh:98-105` (chmod block), `build_files/build.sh:111` (systemctl enable block)
- Modify: `files/usr/libexec/adwaita-lite-session-init:53-60`

- [ ] **Step 1: Delete the Flatpak service file and script**

```bash
rm files/etc/systemd/system/adwaita-lite-flatpak-setup.service
rm files/usr/libexec/adwaita-lite-flatpak-setup
```

- [ ] **Step 2: Update build.sh — add packages**

Add `flatpak` and `NetworkManager-libnm` to the `dnf5 install` list in alphabetical order. `NetworkManager-libnm` goes at the top (capital N sorts before lowercase). `flatpak` goes after `ffmpegthumbnailer` ('l' > 'f' at index 1).

```
    NetworkManager-libnm \
    accountsservice \
    ...
    file-roller \
    flatpak \
    foot \
    ...
```

- [ ] **Step 3: Update build.sh — remove Flatpak service references**

Remove `chmod 0755 /usr/libexec/adwaita-lite-flatpak-setup` from the chmod block (line ~103).

Remove `systemctl enable adwaita-lite-flatpak-setup.service` from the systemctl block (line ~112).

- [ ] **Step 4: Update session-init — remove stamp file notification**

Remove lines 53-60 from `files/usr/libexec/adwaita-lite-session-init` (the background subshell that checks for `/var/lib/adwaita-lite/flatpak-setup.done` and sends a `notify-send` notification).

- [ ] **Step 5: Verify and commit**

```bash
bash -n build_files/build.sh
bash -n files/usr/libexec/adwaita-lite-session-init
test ! -f files/etc/systemd/system/adwaita-lite-flatpak-setup.service
test ! -f files/usr/libexec/adwaita-lite-flatpak-setup

git add -A && git commit -m "refactor: remove standalone Flatpak service, add NM/flatpak packages

Wizard will take over Flatpak provisioning. Remove the systemd oneshot
service, its script, the session-init notification, and the build.sh
references. Add NetworkManager-libnm (GIR typelib for gi.repository.NM)
and flatpak to the package list."
```

---

### Task 2: 6-page scaffold — constants, imports, CSS, navigation, stub pages

Update the wizard's top-level declarations AND navigation for the new 6-page flow simultaneously, with stub pages for Network, Apps, and Progress so the wizard is functional at every commit boundary.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` (entire file — imports, constants, CSS, navigation, page builders, stack registration)

- [ ] **Step 1: Update module docstring**

Change the docstring (lines 2-12) to reflect the new 6-page flow:

```python
"""Adwaita-Lite first-boot user creation wizard.

Runs inside cage (kiosk Wayland compositor) on the login screen when no user
accounts exist.  Creates a local user with sudo (wheel) access, configures
timezone, swap, and optional Flatpak apps, then reboots into the normal
login screen.

Six-page flow:
  Page 0 — Network (WiFi scan-and-connect, auto-skipped if online)
  Page 1 — Account (name, username, password)
  Page 2 — System setup (timezone, memory management, admin/root)
  Page 3 — Apps (Flatpak app selection)
  Page 4 — Summary and confirmation
  Page 5 — Progress (real-time setup execution)
"""
```

- [ ] **Step 2: Add NM import**

After `gi.require_version("Gtk", "4.0")`, add:

```python
gi.require_version("NM", "1.0")
```

Update the gi.repository import line:

```python
from gi.repository import Gtk, Gdk, GLib, Gio, NM, Pango  # noqa: E402
```

- [ ] **Step 3: Update page constants and add data structures**

Replace:

```python
PAGE_ACCOUNT = 0
PAGE_SYSTEM = 1
PAGE_CONFIRM = 2
```

With:

```python
PAGE_NETWORK = 0
PAGE_ACCOUNT = 1
PAGE_SYSTEM = 2
PAGE_APPS = 3
PAGE_CONFIRM = 4
PAGE_PROGRESS = 5

DEFAULT_FLATPAKS = [
    ("dev.bazaar.app", "Bazaar", "Browse and install apps"),
]

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
```

- [ ] **Step 4: Add new CSS classes**

Append inside the `CSS` string, before the closing `"""`:

```css
.wifi-row {
    padding: 12px 16px;
    border-radius: 8px;
    background-color: #363636;
    margin-bottom: 4px;
}

.wifi-row:hover {
    background-color: #404040;
}

.wifi-ssid {
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    color: #ffffff;
}

.wifi-detail {
    font-family: "Roboto", sans-serif;
    font-size: 13px;
    color: #aaaaaa;
}

.wifi-connected {
    background-color: #1a3a1a;
    border: 1px solid #57e389;
}

.app-row {
    padding: 12px 16px;
    border-radius: 8px;
    background-color: #363636;
    margin-bottom: 4px;
}

.app-name {
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    color: #ffffff;
}

.app-description {
    font-family: "Roboto", sans-serif;
    font-size: 13px;
    color: #aaaaaa;
}

.progress-step {
    font-family: "Roboto", sans-serif;
    font-size: 15px;
    padding: 8px 0;
}

.progress-pending {
    color: #888888;
}

.progress-active {
    color: #62a0ea;
}

.progress-done {
    color: #57e389;
}

.progress-failed {
    color: #ff6b6b;
}

.progress-skipped {
    color: #888888;
    font-style: italic;
}
```

- [ ] **Step 5: Add stub page builders**

Add three placeholder page builders that will be fleshed out in later tasks. Each returns a simple ScrolledWindow with a title label, so the stack has all 6 pages and navigation works:

```python
def _build_network_page(self) -> Gtk.ScrolledWindow:
    """Stub — replaced in Task 3."""
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)
    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)
    title = Gtk.Label(label="Connect to Wi-Fi")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)
    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled

def _build_apps_page(self) -> Gtk.ScrolledWindow:
    """Stub — replaced in Task 5."""
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)
    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)
    title = Gtk.Label(label="Install Apps")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)
    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled

def _build_progress_page(self) -> Gtk.ScrolledWindow:
    """Stub — replaced in Task 7."""
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)
    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)
    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)
    title = Gtk.Label(label="Setting Up...")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)
    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled
```

- [ ] **Step 6: Update stack registration in `__init__`**

Replace the old 3-page stack registration with all 6 pages:

```python
self._stack.add_named(self._build_network_page(), "network")
self._stack.add_named(self._build_account_page(), "account")
self._stack.add_named(self._build_system_page(), "system")
self._stack.add_named(self._build_apps_page(), "apps")
self._stack.add_named(self._build_confirm_page(), "confirm")
self._stack.add_named(self._build_progress_page(), "progress")
```

- [ ] **Step 7: Add state variables to `__init__`**

Add before the stack creation:

```python
self._network_skipped = True   # Default to skipped; Task 4 will set False when NM is ready
self._connected_ssid: str | None = None
self._current_page = PAGE_ACCOUNT  # Start at Account (network skipped by default until NM wires up)
```

Update the step label initial text:

```python
self._step_label = Gtk.Label(label="Step 1 of 4")
```

Add `_update_navigation()` at the very end of `__init__`, after `self.set_child(outer)`, to synchronize the visible stack child with `_current_page` from the start (prevents briefly showing the network stub when network is skipped):

```python
self.set_child(outer)
self._update_navigation()
```

- [ ] **Step 8: Rewrite navigation methods**

Replace `_go_next`, `_go_back`, `_update_navigation`, and `_validate_page`:

```python
def _get_pages(self) -> list[str]:
    """Return ordered page names, excluding auto-skipped network."""
    pages = ["network", "account", "system", "apps", "confirm", "progress"]
    if self._network_skipped:
        pages.remove("network")
    return pages

def _get_first_page(self) -> int:
    return PAGE_ACCOUNT if self._network_skipped else PAGE_NETWORK

def _go_next(self) -> None:
    if not self._validate_page(self._current_page):
        return

    if self._current_page == PAGE_CONFIRM:
        self._on_setup_clicked()
        return

    self._current_page += 1
    self._set_status("")
    self._update_navigation()

    if self._current_page == PAGE_CONFIRM:
        self._populate_summary()

def _go_back(self) -> None:
    if self._current_page <= self._get_first_page():
        return
    self._current_page -= 1
    self._set_status("")
    self._update_navigation()

def _update_navigation(self) -> None:
    page_names = {
        PAGE_NETWORK: "network", PAGE_ACCOUNT: "account",
        PAGE_SYSTEM: "system", PAGE_APPS: "apps",
        PAGE_CONFIRM: "confirm", PAGE_PROGRESS: "progress",
    }
    self._stack.set_visible_child_name(page_names[self._current_page])

    pages = self._get_pages()
    current_name = page_names[self._current_page]
    visible_idx = pages.index(current_name) if current_name in pages else 0
    total = len(pages) - 1  # Exclude progress from step count

    is_progress = self._current_page == PAGE_PROGRESS
    self._step_label.set_visible(not is_progress)
    if not is_progress:
        self._step_label.set_text(f"Step {visible_idx + 1} of {total}")

    first = self._get_first_page()
    self._back_button.set_visible(
        self._current_page > first and not is_progress
    )
    self._next_button.set_visible(not is_progress)
    self._next_button.set_label(
        "Set Up" if self._current_page == PAGE_CONFIRM else "Next"
    )

    # Focus first input on new page
    if self._current_page == PAGE_ACCOUNT:
        self._fullname_entry.grab_focus()
    elif self._current_page == PAGE_SYSTEM:
        self._tz_dropdown.grab_focus()

def _validate_page(self, page: int) -> bool:
    if page == PAGE_ACCOUNT:
        return self._validate_account()
    elif page == PAGE_SYSTEM:
        return self._validate_system()
    return True  # Network, Apps, Confirm have no blocking validation
```

- [ ] **Step 9: Add stub `_get_selected_apps` helper**

Needed by `_populate_summary` until the real Apps page is built:

```python
def _get_selected_apps(self) -> list[tuple[str, str]]:
    """Return list of (app_id, app_name) for checked apps. Stub until Task 5."""
    return []
```

- [ ] **Step 10: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "refactor: 6-page wizard scaffold with constants, CSS, navigation, stubs

Updates page constants (PAGE_NETWORK through PAGE_PROGRESS), adds NM
import, new CSS classes, stub pages for Network/Apps/Progress, and
rewrites navigation for dynamic page counting with auto-skip support.
Wizard is fully functional at this commit with stubs in place."
```

---

### Task 3: Network page — full UI

Replace the network page stub with the complete layout: WiFi list, hidden network entry, rescan button, status area.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — replace `_build_network_page` stub

- [ ] **Step 1: Replace `_build_network_page`**

Replace the stub with the full implementation:

```python
def _build_network_page(self) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)

    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)

    title = Gtk.Label(label="Connect to Wi-Fi")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)

    subtitle = Gtk.Label(label="Select a network to get online.")
    subtitle.add_css_class("welcome-subtitle")
    subtitle.set_halign(Gtk.Align.CENTER)
    card.append(subtitle)

    # WiFi network list
    self._wifi_list = Gtk.ListBox()
    self._wifi_list.set_selection_mode(Gtk.SelectionMode.NONE)
    self._wifi_list.set_vexpand(False)
    card.append(self._wifi_list)

    # "No networks" placeholder
    self._wifi_empty_label = Gtk.Label(label="Scanning for networks...")
    self._wifi_empty_label.add_css_class("wifi-detail")
    self._wifi_empty_label.set_margin_top(16)
    self._wifi_empty_label.set_margin_bottom(8)
    card.append(self._wifi_empty_label)

    # Rescan button
    self._rescan_button = Gtk.Button(label="Rescan")
    self._rescan_button.add_css_class("back-button")
    self._rescan_button.set_halign(Gtk.Align.CENTER)
    self._rescan_button.set_visible(False)
    self._rescan_button.connect("clicked", lambda _: self._request_wifi_scan())
    card.append(self._rescan_button)

    # Hidden network section
    self._hidden_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    self._hidden_box.set_visible(False)
    self._hidden_box.set_margin_top(8)

    self._hidden_box.append(self._make_label("Network Name (SSID)"))
    self._hidden_ssid_entry = Gtk.Entry()
    self._hidden_ssid_entry.add_css_class("form-entry")
    self._hidden_ssid_entry.set_hexpand(True)
    self._hidden_box.append(self._hidden_ssid_entry)

    self._hidden_box.append(self._make_label("Password"))
    self._hidden_pw_entry = Gtk.PasswordEntry()
    self._hidden_pw_entry.set_show_peek_icon(True)
    self._hidden_pw_entry.add_css_class("form-entry")
    self._hidden_pw_entry.set_hexpand(True)
    self._hidden_box.append(self._hidden_pw_entry)

    hidden_connect_btn = Gtk.Button(label="Connect")
    hidden_connect_btn.add_css_class("create-button")
    hidden_connect_btn.set_halign(Gtk.Align.END)
    hidden_connect_btn.set_margin_top(8)
    hidden_connect_btn.connect("clicked", lambda _: self._connect_hidden_network())
    self._hidden_box.append(hidden_connect_btn)

    card.append(self._hidden_box)

    # "Join hidden network" toggle
    hidden_link = Gtk.Button(label="Join hidden network...")
    hidden_link.add_css_class("back-button")
    hidden_link.set_halign(Gtk.Align.START)
    hidden_link.set_margin_top(8)
    hidden_link.connect("clicked", lambda _: self._hidden_box.set_visible(
        not self._hidden_box.get_visible()))
    card.append(hidden_link)

    # Network status
    self._net_status_label = Gtk.Label(label="")
    self._net_status_label.add_css_class("status-label")
    self._net_status_label.set_halign(Gtk.Align.CENTER)
    self._net_status_label.set_wrap(True)
    self._net_status_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    self._net_status_label.set_max_width_chars(50)
    self._net_status_label.set_margin_top(8)
    card.append(self._net_status_label)

    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled
```

- [ ] **Step 2: Add stub NM methods**

These stubs will be replaced in Task 4:

```python
def _request_wifi_scan(self) -> None:
    """Trigger a WiFi scan via NM. Implemented in Task 4."""
    pass

def _connect_hidden_network(self) -> None:
    """Connect to a hidden network. Implemented in Task 4."""
    pass
```

- [ ] **Step 3: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add network page UI to wizard

WiFi list, hidden network entry, rescan button, and status area.
NM integration in next commit."
```

---

### Task 4: Network page — libnm integration

Wire up NM.Client for async WiFi scanning, populating the list, and connecting to networks.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — NM.Client init, scan, connect, auto-skip

**Reference:** libnm GObject API — `NM.Client`, `NM.DeviceWifi`, `NM.AccessPoint`, `NM.SimpleConnection`, `NM.SettingWireless`, `NM.SettingWirelessSecurity`

- [ ] **Step 1: Add NM.Client async initialization at END of `__init__`**

**IMPORTANT:** Place this AFTER all UI construction (after `self.set_child(outer)`) to avoid race conditions where the async callback fires before the stack is built:

```python
# Start NM client init AFTER UI is fully constructed
self._nm_client: NM.Client | None = None
self._wifi_device: NM.DeviceWifi | None = None
NM.Client.new_async(None, self._on_nm_client_ready)
```

- [ ] **Step 2: Implement `_on_nm_client_ready` callback**

```python
def _on_nm_client_ready(self, _source: object, result: Gio.AsyncResult) -> None:
    try:
        self._nm_client = NM.Client.new_finish(result)
    except Exception:
        # NM unavailable — stay on Account page (network already skipped by default)
        return

    # Check existing connectivity (force fresh check)
    self._nm_client.check_connectivity_async(None, self._on_connectivity_checked)

def _on_connectivity_checked(self, client: NM.Client, result: Gio.AsyncResult) -> None:
    try:
        connectivity = client.check_connectivity_finish(result)
    except Exception:
        connectivity = NM.ConnectivityState.UNKNOWN

    if connectivity == NM.ConnectivityState.FULL:
        # Already online — keep network skipped
        self._connected_ssid = self._detect_current_ssid()
        return

    # Find WiFi device
    for dev in self._nm_client.get_devices():
        if isinstance(dev, NM.DeviceWifi):
            self._wifi_device = dev
            break

    if self._wifi_device is None:
        # No WiFi adapter — stay skipped
        return

    # WiFi available, no connectivity — show network page
    self._network_skipped = False
    self._current_page = PAGE_NETWORK
    self._update_navigation()
    self._request_wifi_scan()
```

- [ ] **Step 3: Implement `_detect_current_ssid`**

```python
def _detect_current_ssid(self) -> str | None:
    if self._nm_client is None:
        return None
    for conn in self._nm_client.get_active_connections():
        if conn.get_connection_type() == "802-11-wireless":
            return conn.get_id()
        if conn.get_connection_type() == "802-3-ethernet":
            return "(Wired)"
    return None
```

- [ ] **Step 4: Implement `_request_wifi_scan` and `_on_scan_done`**

Replace the stub:

```python
def _request_wifi_scan(self) -> None:
    if self._wifi_device is None:
        return
    self._rescan_button.set_sensitive(False)
    self._wifi_empty_label.set_text("Scanning for networks...")
    self._wifi_empty_label.set_visible(True)
    self._wifi_device.request_scan_async(None, self._on_scan_done)

def _on_scan_done(self, device: NM.DeviceWifi, result: Gio.AsyncResult) -> None:
    try:
        device.request_scan_finish(result)
    except Exception:
        pass  # Scan may fail if rate-limited; still show cached APs
    self._populate_wifi_list()
    self._rescan_button.set_visible(True)
    # Re-enable rescan after NM cooldown (~10s)
    GLib.timeout_add_seconds(10, self._enable_rescan)

def _enable_rescan(self) -> bool:
    self._rescan_button.set_sensitive(True)
    return GLib.SOURCE_REMOVE
```

Note: rescan button stays insensitive after scan completes. Only the 10-second timer re-enables it, respecting NM's rate limit.

- [ ] **Step 5: Implement `_populate_wifi_list`**

```python
def _populate_wifi_list(self) -> None:
    # Clear existing rows
    while row := self._wifi_list.get_row_at_index(0):
        self._wifi_list.remove(row)

    if self._wifi_device is None:
        return

    aps = self._wifi_device.get_access_points()
    # Deduplicate by SSID, keep strongest signal
    seen: dict[str, NM.AccessPoint] = {}
    for ap in aps:
        ssid_bytes = ap.get_ssid()
        if ssid_bytes is None:
            continue
        ssid = ssid_bytes.get_data().decode("utf-8", errors="replace")
        if not ssid:
            continue
        if ssid not in seen or ap.get_strength() > seen[ssid].get_strength():
            seen[ssid] = ap

    if not seen:
        self._wifi_empty_label.set_text("No networks found.")
        self._wifi_empty_label.set_visible(True)
        return

    self._wifi_empty_label.set_visible(False)

    # Sort by signal strength descending
    for ssid, ap in sorted(seen.items(), key=lambda x: x[1].get_strength(), reverse=True):
        row = self._build_wifi_row(ssid, ap)
        self._wifi_list.append(row)
```

- [ ] **Step 6: Implement `_build_wifi_row`**

```python
def _build_wifi_row(self, ssid: str, ap: NM.AccessPoint) -> Gtk.ListBoxRow:
    row = Gtk.ListBoxRow()
    row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    row_box.add_css_class("wifi-row")

    # Top line: SSID + signal + security
    top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

    ssid_label = Gtk.Label(label=ssid)
    ssid_label.add_css_class("wifi-ssid")
    ssid_label.set_halign(Gtk.Align.START)
    ssid_label.set_hexpand(True)
    top.append(ssid_label)

    strength = ap.get_strength()
    if strength > 70:
        signal_text = "Strong"
    elif strength >= 40:
        signal_text = "Medium"
    else:
        signal_text = "Weak"

    flags = ap.get_wpa_flags() | ap.get_rsn_flags()
    secured = flags != NM.AP80211ApSecurityFlags.NONE
    detail = f"{signal_text} {'Secured' if secured else 'Open'}"

    detail_label = Gtk.Label(label=detail)
    detail_label.add_css_class("wifi-detail")
    top.append(detail_label)

    row_box.append(top)

    # Password entry (hidden by default, shown on click)
    pw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    pw_box.set_visible(False)
    pw_box.set_margin_top(8)

    if secured:
        pw_entry = Gtk.PasswordEntry()
        pw_entry.set_show_peek_icon(True)
        pw_entry.add_css_class("form-entry")
        pw_entry.set_hexpand(True)
        pw_entry.set_placeholder_text("Password")
        pw_box.append(pw_entry)

        connect_btn = Gtk.Button(label="Connect")
        connect_btn.add_css_class("create-button")
        connect_btn.connect("clicked", lambda _, s=ssid, e=pw_entry: self._connect_to_ap(s, e.get_text(), False))
        pw_entry.connect("activate", lambda _, s=ssid, e=pw_entry: self._connect_to_ap(s, e.get_text(), False))
        pw_box.append(connect_btn)
    else:
        connect_btn = Gtk.Button(label="Connect")
        connect_btn.add_css_class("create-button")
        connect_btn.connect("clicked", lambda _, s=ssid: self._connect_to_ap(s, None, False))
        pw_box.append(connect_btn)

    row_box.append(pw_box)

    # Click to expand/collapse password entry
    click = Gtk.GestureClick()
    click.connect("released", lambda _g, _n, _x, _y, b=pw_box: b.set_visible(not b.get_visible()))
    row.add_controller(click)

    row.set_child(row_box)
    return row
```

- [ ] **Step 7: Implement `_connect_to_ap`, `_connect_hidden_network`, and callbacks**

Replace the `_connect_hidden_network` stub:

```python
def _connect_to_ap(self, ssid: str, password: str | None, hidden: bool) -> None:
    if self._nm_client is None or self._wifi_device is None:
        return

    self._net_status_label.set_text(f"Connecting to {ssid}...")
    self._net_status_label.remove_css_class("status-error")
    self._net_status_label.remove_css_class("status-success")

    conn = NM.SimpleConnection.new()

    s_con = NM.SettingConnection.new()
    s_con.set_property("type", "802-11-wireless")
    s_con.set_property("id", ssid)
    conn.add_setting(s_con)

    s_wifi = NM.SettingWireless.new()
    s_wifi.set_property("ssid", GLib.Bytes.new(ssid.encode("utf-8")))
    if hidden:
        s_wifi.set_property("hidden", True)
    conn.add_setting(s_wifi)

    if password:
        s_sec = NM.SettingWirelessSecurity.new()
        s_sec.set_property("key-mgmt", "wpa-psk")
        s_sec.set_property("psk", password)
        conn.add_setting(s_sec)

    self._nm_client.add_and_activate_connection_async(
        conn, self._wifi_device, None, None, self._on_connection_done
    )

def _connect_hidden_network(self) -> None:
    ssid = self._hidden_ssid_entry.get_text().strip()
    password = self._hidden_pw_entry.get_text()
    if not ssid:
        self._net_status_label.set_text("Enter a network name.")
        self._net_status_label.add_css_class("status-error")
        return
    self._connect_to_ap(ssid, password if password else None, hidden=True)

def _on_connection_done(self, client: NM.Client, result: Gio.AsyncResult) -> None:
    try:
        client.add_and_activate_connection_finish(result)
        # Force a fresh connectivity check
        self._nm_client.check_connectivity_async(None, self._on_post_connect_check)
    except Exception as exc:
        err = str(exc)
        if "802-11-wireless-security.psk" in err:
            msg = "Wrong password."
        else:
            msg = f"Connection failed: {err}"
        self._net_status_label.set_text(msg)
        self._net_status_label.add_css_class("status-error")

def _on_post_connect_check(self, client: NM.Client, result: Gio.AsyncResult) -> None:
    try:
        connectivity = client.check_connectivity_finish(result)
    except Exception:
        connectivity = NM.ConnectivityState.UNKNOWN

    if connectivity == NM.ConnectivityState.FULL:
        self._connected_ssid = self._detect_current_ssid()
        self._net_status_label.set_text(f"Connected to {self._connected_ssid or 'network'}!")
        self._net_status_label.remove_css_class("status-error")
        self._net_status_label.add_css_class("status-success")
    else:
        self._net_status_label.set_text("Connected, but no internet access detected.")
        self._net_status_label.remove_css_class("status-error")
```

- [ ] **Step 8: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add libnm WiFi integration to network page

Async NM.Client init (placed after UI construction to avoid races),
WiFi scanning with signal strength and security detection, connect
to visible and hidden networks (with hidden=True flag for hidden SSIDs),
auto-skip when connectivity exists or no WiFi adapter found.
Uses check_connectivity_async for fresh connectivity checks."
```

---

### Task 5: Apps page

Replace the apps page stub with the full Flatpak app selection UI.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — replace `_build_apps_page` stub, replace `_get_selected_apps` stub

- [ ] **Step 1: Replace `_build_apps_page`**

```python
def _build_apps_page(self) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)

    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)

    title = Gtk.Label(label="Install Apps")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)

    subtitle = Gtk.Label(
        label="These apps will be installed during setup. Uncheck any you don't want."
    )
    subtitle.add_css_class("welcome-subtitle")
    subtitle.set_halign(Gtk.Align.CENTER)
    subtitle.set_wrap(True)
    subtitle.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    subtitle.set_max_width_chars(50)
    card.append(subtitle)

    self._app_checks: list[tuple[str, str, Gtk.CheckButton]] = []

    for app_id, app_name, app_desc in DEFAULT_FLATPAKS:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("app-row")

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        text_box.set_hexpand(True)

        name_label = Gtk.Label(label=app_name)
        name_label.add_css_class("app-name")
        name_label.set_halign(Gtk.Align.START)
        text_box.append(name_label)

        desc_label = Gtk.Label(label=app_desc)
        desc_label.add_css_class("app-description")
        desc_label.set_halign(Gtk.Align.START)
        text_box.append(desc_label)

        row.append(text_box)

        check = Gtk.CheckButton()
        check.set_active(True)
        check.set_valign(Gtk.Align.CENTER)
        row.append(check)

        self._app_checks.append((app_id, app_name, check))
        card.append(row)

    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled
```

- [ ] **Step 2: Replace `_get_selected_apps` stub**

```python
def _get_selected_apps(self) -> list[tuple[str, str]]:
    """Return list of (app_id, app_name) for checked apps."""
    return [(aid, name) for aid, name, check in self._app_checks if check.get_active()]
```

- [ ] **Step 3: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add Flatpak app selection page to wizard

Shows DEFAULT_FLATPAKS with per-app checkbox toggles. Currently
just Bazaar. _get_selected_apps returns the checked app list."
```

---

### Task 6: Confirm page updates

Add network and apps summary rows to the confirm page.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — `_build_confirm_page`, `_populate_summary`

- [ ] **Step 1: Update `_build_confirm_page`**

Add `_summary_network` before the existing rows and `_summary_apps` after `_summary_root`:

```python
self._summary_network = self._make_summary_row(card, "Network")
self._summary_name = self._make_summary_row(card, "Name")
self._summary_username = self._make_summary_row(card, "Username")
self._summary_timezone = self._make_summary_row(card, "Timezone")
self._summary_memory = self._make_summary_row(card, "Memory")
self._summary_admin = self._make_summary_row(card, "Administrator")
self._summary_root = self._make_summary_row(card, "Root password")
self._summary_apps = self._make_summary_row(card, "Apps")
```

- [ ] **Step 2: Update `_populate_summary`**

Add network and apps population at the start and end:

```python
def _populate_summary(self) -> None:
    # Network
    if self._connected_ssid == "(Wired)":
        self._summary_network.set_text("Wired connection")
    elif self._connected_ssid:
        self._summary_network.set_text(f"Connected to {self._connected_ssid}")
    else:
        self._summary_network.set_text("No network (offline setup)")

    self._summary_name.set_text(self._fullname_entry.get_text().strip())
    self._summary_username.set_text(self._username_entry.get_text().strip())
    self._summary_timezone.set_text(self._get_selected_timezone())
    self._summary_admin.set_text("Yes" if self._admin_check.get_active() else "No")
    self._summary_root.set_text(
        "Set" if self._root_password_entry.get_text() else "Not set"
    )

    use_zswap, swap_gb = self._get_swap_config()
    if use_zswap:
        self._summary_memory.set_text(f"zswap with {swap_gb} GB disk swap")
    else:
        self._summary_memory.set_text("zram only (compressed RAM)")

    # Apps
    selected = self._get_selected_apps()
    if selected:
        self._summary_apps.set_text(", ".join(name for _, name in selected))
    else:
        self._summary_apps.set_text("No apps selected")
```

- [ ] **Step 3: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add network and apps summaries to confirm page"
```

---

### Task 7: Progress page + step runner

Replace the progress page stub and the monolithic `_create_account` with a dedicated progress page and step-runner loop.

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard` — replace `_build_progress_page` stub, add step functions, rewrite `_on_setup_clicked`

- [ ] **Step 1: Replace `_build_progress_page`**

```python
def _build_progress_page(self) -> Gtk.ScrolledWindow:
    scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_propagate_natural_height(True)

    wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    wrapper.set_halign(Gtk.Align.CENTER)
    wrapper.set_valign(Gtk.Align.CENTER)

    card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    card.add_css_class("card")
    card.set_size_request(480, -1)

    title = Gtk.Label(label="Setting Up...")
    title.add_css_class("welcome-title")
    title.set_halign(Gtk.Align.CENTER)
    card.append(title)
    self._progress_title = title

    # Step labels container
    self._progress_steps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    self._progress_steps_box.set_margin_top(24)
    card.append(self._progress_steps_box)

    # Action buttons (reboot, retry, skip, back) — hidden by default
    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    btn_box.set_halign(Gtk.Align.CENTER)
    btn_box.set_margin_top(24)

    self._progress_back_btn = Gtk.Button(label="Back")
    self._progress_back_btn.add_css_class("back-button")
    self._progress_back_btn.set_visible(False)
    self._progress_back_btn.connect("clicked", lambda _: self._progress_go_back())
    btn_box.append(self._progress_back_btn)

    self._progress_skip_btn = Gtk.Button(label="Skip")
    self._progress_skip_btn.add_css_class("back-button")
    self._progress_skip_btn.set_visible(False)
    self._progress_skip_btn.connect("clicked", lambda _: self._progress_skip())
    btn_box.append(self._progress_skip_btn)

    self._progress_retry_btn = Gtk.Button(label="Retry")
    self._progress_retry_btn.add_css_class("create-button")
    self._progress_retry_btn.set_visible(False)
    self._progress_retry_btn.connect("clicked", lambda _: self._progress_retry())
    btn_box.append(self._progress_retry_btn)

    self._progress_reboot_btn = Gtk.Button(label="Reboot")
    self._progress_reboot_btn.add_css_class("create-button")
    self._progress_reboot_btn.set_visible(False)
    self._progress_reboot_btn.connect("clicked",
        lambda _: subprocess.run(["systemctl", "reboot"]))
    btn_box.append(self._progress_reboot_btn)

    card.append(btn_box)

    wrapper.append(card)
    scrolled.set_child(wrapper)
    return scrolled
```

- [ ] **Step 2: Add step functions**

Each returns `None` on success or an error string. These are methods on `SetupWizardWindow`, reading from `self._setup_*` fields that are captured in `_on_setup_clicked`:

```python
def _step_create_user(self) -> str | None:
    """Create user account via AccountsService, set password, add to video group."""
    fullname = self._setup_fullname
    username = self._setup_username
    password = self._setup_password
    is_admin = self._setup_is_admin

    try:
        user_pw_hash = _hash_password(password)
    except subprocess.CalledProcessError as exc:
        return f"Failed to hash password: {exc.stderr.strip() or exc}"

    try:
        accounts = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            "org.freedesktop.Accounts", "/org/freedesktop/Accounts",
            "org.freedesktop.Accounts", None,
        )
    except Exception as exc:
        return f"Failed to connect to AccountsService: {exc}"

    account_type = 1 if is_admin else 0

    try:
        result = accounts.call_sync(
            "CreateUser",
            GLib.Variant("(ssi)", (username, fullname, account_type)),
            Gio.DBusCallFlags.NONE, -1, None,
        )
        user_object_path = result.get_child_value(0).get_string()
    except Exception as exc:
        return f"Failed to create user: {exc}"

    try:
        user_proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
            "org.freedesktop.Accounts", user_object_path,
            "org.freedesktop.Accounts.User", None,
        )
        user_proxy.call_sync(
            "SetPassword",
            GLib.Variant("(ss)", (user_pw_hash, "")),
            Gio.DBusCallFlags.NONE, -1, None,
        )
    except Exception as exc:
        return f"Failed to set user password: {exc}"

    try:
        group_path = Path("/etc/group")
        lines = group_path.read_text().splitlines()
        new_lines = []
        for line in lines:
            if line.startswith("video:"):
                parts = line.split(":")
                members = parts[3].split(",") if parts[3] else []
                if username not in members:
                    members.append(username)
                parts[3] = ",".join(members)
                line = ":".join(parts)
            new_lines.append(line)
        group_path.write_text("\n".join(new_lines) + "\n")
    except (OSError, IndexError) as exc:
        return f"Failed to add user to video group: {exc}"

    return None

def _step_configure_system(self) -> str | None:
    """Set timezone, root password, and swap configuration."""
    root_password = self._setup_root_password
    timezone = self._setup_timezone
    use_zswap = self._setup_use_zswap
    swap_gb = self._setup_swap_gb

    if root_password:
        try:
            root_hash = _hash_password(root_password)
            shadow_path = Path("/etc/shadow")
            lines = shadow_path.read_text().splitlines()
            new_lines = []
            for line in lines:
                if line.startswith("root:"):
                    parts = line.split(":")
                    parts[1] = root_hash
                    line = ":".join(parts)
                new_lines.append(line)
            shadow_path.write_text("\n".join(new_lines) + "\n")
        except (OSError, IndexError, subprocess.CalledProcessError) as exc:
            return f"Failed to set root password: {exc}"

    try:
        subprocess.run(
            ["timedatectl", "set-timezone", timezone],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to set timezone: {exc.stderr.strip() or exc}"

    if use_zswap:
        try:
            subprocess.run(
                ["bash", "-c", 'echo "" > /etc/systemd/zram-generator.conf'],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [
                    "grubby", "--update-kernel=ALL",
                    "--args=zswap.enabled=1 zswap.max_pool_percent=25 zswap.compressor=zstd",
                ],
                check=True, capture_output=True, text=True,
            )
            for param, value in [
                ("enabled", "1"), ("max_pool_percent", "25"), ("compressor", "zstd"),
            ]:
                try:
                    Path(f"/sys/module/zswap/parameters/{param}").write_text(value)
                except (OSError, FileNotFoundError):
                    pass

            size_mb = swap_gb * 1024
            subprocess.run(
                ["dd", "if=/dev/zero", "of=/var/swap", "bs=1M", f"count={size_mb}"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            subprocess.run(["chmod", "600", "/var/swap"],
                           check=True, capture_output=True, text=True)
            subprocess.run(["systemctl", "enable", "adwaita-lite-encrypted-swap.service"],
                           check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            return f"Failed to configure swap: {exc.stderr.strip() or exc}"
        except OSError as exc:
            return f"Failed to configure swap: {exc}"

    return None

def _step_add_flathub(self) -> str | None:
    """Add Flathub remote."""
    try:
        subprocess.run(
            ["flatpak", "remote-add", "--system", "--if-not-exists",
             "flathub", FLATHUB_URL],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to add Flathub: {exc.stderr.strip() or exc}"
    return None

def _step_install_flatpak(self, app_id: str) -> str | None:
    """Install a single Flatpak app."""
    try:
        subprocess.run(
            ["flatpak", "install", "--system", "--noninteractive",
             "flathub", app_id],
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        return f"Failed to install: {exc.stderr.strip() or exc}"
    return None
```

- [ ] **Step 3: Rewrite `_on_setup_clicked` with step runner**

Delete the old `_on_setup_clicked` and everything it contains (the nested `_create_account`, `_on_done`, `_reboot`, `_thread_target`). Replace with:

```python
def _on_setup_clicked(self) -> None:
    # Capture all form values for thread-safe access
    self._setup_fullname = self._fullname_entry.get_text().strip()
    self._setup_username = self._username_entry.get_text().strip()
    self._setup_password = self._password_entry.get_text()
    self._setup_is_admin = self._admin_check.get_active()
    self._setup_root_password = self._root_password_entry.get_text()
    self._setup_timezone = self._get_selected_timezone()
    self._setup_use_zswap, self._setup_swap_gb = self._get_swap_config()

    # Build step list: (label, callable, is_flatpak_step)
    self._steps: list[tuple[str, callable, bool]] = [
        ("Creating user account", self._step_create_user, False),
        ("Configuring system", self._step_configure_system, False),
    ]
    selected_apps = self._get_selected_apps()
    if selected_apps:
        self._steps.append(("Adding Flathub repository", self._step_add_flathub, True))
        for app_id, app_name in selected_apps:
            self._steps.append((
                f"Installing {app_name}",
                lambda aid=app_id: self._step_install_flatpak(aid),
                True,
            ))

    # Build progress UI
    while child := self._progress_steps_box.get_first_child():
        self._progress_steps_box.remove(child)

    self._step_labels: list[Gtk.Label] = []
    for label_text, _, _ in self._steps:
        lbl = Gtk.Label(label=f"  {label_text}")
        lbl.add_css_class("progress-step")
        lbl.add_css_class("progress-pending")
        lbl.set_halign(Gtk.Align.START)
        self._step_labels.append(lbl)
        self._progress_steps_box.append(lbl)

    # Navigate to progress page
    self._current_page = PAGE_PROGRESS
    self._update_navigation()

    # Launch step runner
    self._run_from_step = 0
    self._start_step_runner()

def _start_step_runner(self) -> None:
    """Launch the step-runner thread starting from self._run_from_step."""
    self._progress_back_btn.set_visible(False)
    self._progress_skip_btn.set_visible(False)
    self._progress_retry_btn.set_visible(False)
    self._progress_reboot_btn.set_visible(False)

    start = self._run_from_step

    def _thread() -> None:
        for i in range(start, len(self._steps)):
            label_text, func, is_flatpak = self._steps[i]
            GLib.idle_add(self._update_step_status, i, "active")
            err = func()
            if err:
                GLib.idle_add(self._on_step_failed, i, err, is_flatpak)
                return
            GLib.idle_add(self._update_step_status, i, "done")

        # All done — write stamp file and show reboot
        stamp = Path("/var/lib/adwaita-lite/flatpak-setup.done")
        stamp.parent.mkdir(parents=True, exist_ok=True)
        stamp.touch()
        GLib.idle_add(self._on_all_steps_done)

    threading.Thread(target=_thread, daemon=True).start()

def _update_step_status(self, index: int, status: str) -> None:
    lbl = self._step_labels[index]
    label_text = self._steps[index][0]

    for cls in ("progress-pending", "progress-active", "progress-done",
                "progress-failed", "progress-skipped"):
        lbl.remove_css_class(cls)

    if status == "active":
        lbl.set_text(f"  {label_text}...")
        lbl.add_css_class("progress-active")
    elif status == "done":
        lbl.set_text(f"  {label_text}")
        lbl.add_css_class("progress-done")
    elif status == "failed":
        lbl.add_css_class("progress-failed")
    elif status == "skipped":
        lbl.set_text(f"  {label_text} (skipped)")
        lbl.add_css_class("progress-skipped")

def _on_step_failed(self, index: int, error: str, is_flatpak: bool) -> None:
    lbl = self._step_labels[index]
    label_text = self._steps[index][0]
    lbl.set_text(f"  {label_text} — {error}")

    for cls in ("progress-pending", "progress-active", "progress-done"):
        lbl.remove_css_class(cls)
    lbl.add_css_class("progress-failed")

    if is_flatpak:
        self._progress_retry_btn.set_visible(True)
        self._progress_skip_btn.set_visible(True)
        self._run_from_step = index
    else:
        self._progress_back_btn.set_visible(True)

def _on_all_steps_done(self) -> None:
    self._progress_title.set_text("Setup Complete!")
    self._progress_reboot_btn.set_visible(True)

def _progress_retry(self) -> None:
    self._start_step_runner()

def _progress_skip(self) -> None:
    # Mark remaining Flatpak steps as skipped
    for i in range(self._run_from_step, len(self._steps)):
        _, _, is_flatpak = self._steps[i]
        if is_flatpak:
            self._update_step_status(i, "skipped")

    # Write stamp and show reboot
    stamp = Path("/var/lib/adwaita-lite/flatpak-setup.done")
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch()
    self._on_all_steps_done()

def _progress_go_back(self) -> None:
    """Return to confirm page on fatal error for correction."""
    self._current_page = PAGE_CONFIRM
    self._update_navigation()
```

- [ ] **Step 4: Verify syntax and commit**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"

git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add progress page with step-runner, retry/skip, and reboot

Replaces monolithic _create_account with individual step functions
and a step-runner loop. Progress page shows per-step status with
retry/skip for Flatpak failures and manual reboot on success.
Writes flatpak-setup.done stamp on any successful completion."
```

---

### Task 8: Final verification

One last pass to make sure everything is consistent.

**Files:**
- All modified files

- [ ] **Step 1: Syntax check wizard**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read())"
```

- [ ] **Step 2: Syntax check shell scripts**

```bash
bash -n build_files/build.sh
bash -n files/usr/libexec/adwaita-lite-session-init
```

- [ ] **Step 3: Verify deleted files are gone**

```bash
test ! -f files/etc/systemd/system/adwaita-lite-flatpak-setup.service
test ! -f files/usr/libexec/adwaita-lite-flatpak-setup
```

- [ ] **Step 4: Verify no stale references**

```bash
# Should return no matches
grep -r "adwaita-lite-flatpak-setup" build_files/ files/ || echo "Clean"
```

- [ ] **Step 5: Review diff for consistency**

```bash
git diff HEAD~7 --stat  # All commits from this plan
```
