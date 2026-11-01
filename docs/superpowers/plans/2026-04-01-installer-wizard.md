# Installer Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the first-boot setup wizard into a USB installer that deploys via `bootc install to-disk`, configures the sysroot directly, and delegates swap/service setup to a first-boot service on the installed system.

**Architecture:** The wizard boots from USB via greetd + labwc (existing architecture). A new Disk page (Page 1) collects target drive, filesystem, and memory management choices. The progress page executes `bootc install to-disk`, mounts the installed sysroot, and writes user/system/network/Flatpak configuration directly to it (Anaconda pattern). A headless first-boot service on the installed system handles operations requiring the running target system: swap file creation, service enablement, grubby kernel args. The encrypted swap architecture (dm-crypt with random per-boot key) is preserved unchanged.

**Tech Stack:** GTK4/Python3, bootc, greetd/labwc, rsync, useradd/chpasswd (`--root`), systemd, grubby, bash

**Spec:** `docs/superpowers/specs/2026-04-01-installer-wizard-design.md`

**Out of scope:** USB image build changes (pre-downloading Flatpaks into the live image, removing the raw DD image build) are a separate task that involves Containerfile/build pipeline changes, not covered by this plan.

---

### File Structure

**New files:**
- `files/usr/libexec/adwaita-lite-first-boot` — Headless first-boot config script (reads `install-config.json`, creates swap, enables services, applies kernel args)
- `files/etc/systemd/system/adwaita-lite-first-boot.service` — Systemd unit: runs once on first boot, guarded by `ConditionPathExists`

**Modified files:**
- `files/usr/bin/adwaita-lite-setup-wizard` — Major rewrite:
  - New Disk page (Page 1): drive selector, filesystem, memory management, swap size
  - Simplified System page: timezone, admin toggle, root password only
  - Rewritten progress page: bootc install pipeline with sysroot configuration
  - Updated confirm page: target drive/filesystem in summary
  - 7 pages (was 6), new `PAGE_DISK = 1`
  - Step error handling: fatal / retry / skippable behaviors
  - Imports: add `json`, remove `pwd`
- `files/etc/systemd/zram-generator.conf` — zram size: 150% → 125% of RAM
- `build_files/build.sh` — Add `rsync` package, chmod first-boot script, enable first-boot and flatpak-setup services

---

### Task 1: Update zram-generator config (125% of RAM)

**Files:**
- Modify: `files/etc/systemd/zram-generator.conf`

- [ ] **Step 1: Change zram size from 150% to 125%**

In `files/etc/systemd/zram-generator.conf`, replace the entire file with:

```ini
[zram0]
zram-size = min(ram * 5 / 4, 3072)
compression-algorithm = zstd(level=3)
swap-priority = 100
```

The formula `ram * 5/4` = 125% of RAM. On a 2 GB device this gives 2.5 GB of compressed swap — enough capacity while leaving more uncompressed RAM headroom than the previous 150% (3 GB).

- [ ] **Step 2: Commit**

```bash
git add files/etc/systemd/zram-generator.conf
git commit -m "feat: reduce default zram size from 150% to 125% of RAM"
```

---

### Task 2: Create first-boot service

**Files:**
- Create: `files/usr/libexec/adwaita-lite-first-boot`
- Create: `files/etc/systemd/system/adwaita-lite-first-boot.service`

- [ ] **Step 1: Create the first-boot script**

Create `files/usr/libexec/adwaita-lite-first-boot`:

```bash
#!/bin/bash
# First-boot configuration for installer-deployed Adwaita-Lite systems.
# Reads /var/lib/adwaita-lite/install-config.json and performs operations
# that require the running target system: swap file creation, service
# enablement, grubby kernel args.
#
# Called by adwaita-lite-first-boot.service.
# Guards: runs only when install-config.json exists and setup-done does not.

set -euo pipefail

CONFIG=/var/lib/adwaita-lite/install-config.json
STATE_DIR=/var/lib/adwaita-lite

# --- Read config via Python (already available in the image) ---
read_config() {
    python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2], ''))" \
        "$CONFIG" "$1"
}

strategy=$(read_config memory_strategy)
swap_gb=$(read_config swap_size_gb)
username=$(read_config username)

# --- Memory management ---
if [ "$strategy" = "zswap" ] && [ -n "$swap_gb" ] && [ "$swap_gb" != "None" ]; then
    # Write swap size for the swap-init script
    echo "$swap_gb" > "$STATE_DIR/swap-size"

    # Create the swap file
    /usr/libexec/adwaita-lite-swap-init

    # Enable swap services for future boots
    systemctl enable \
        adwaita-lite-swap-init.service \
        adwaita-lite-encrypted-swap.service \
        adwaita-lite-zswap.service

    # Activate encrypted swap for this boot
    /usr/libexec/adwaita-lite-encrypted-swap start

    # Mask zram-generator so it doesn't compete with disk swap
    systemctl mask systemd-zram-setup@.service

    # Apply zswap kernel args so they take effect from the next boot onward
    grubby --update-kernel=ALL \
        --args="zswap.enabled=1 zswap.compressor=zstd zswap.max_pool_percent=25"

    # Persist swappiness for disk-backed swap
    echo "vm.swappiness = 100" > /etc/sysctl.d/91-adwaita-lite-zswap.conf
    sysctl -w vm.swappiness=100 || true
fi
# zram: no action needed — zram-generator.conf (125%) is already in the image

# --- Greeter prefill ---
if [ -n "$username" ]; then
    echo "$username" > "$STATE_DIR/last-user"
fi

# --- Mark setup complete ---
touch "$STATE_DIR/setup-done"
```

- [ ] **Step 2: Create the systemd service unit**

Create `files/etc/systemd/system/adwaita-lite-first-boot.service`:

```ini
[Unit]
Description=First-boot configuration for installer-deployed Adwaita-Lite
After=local-fs.target
Before=greetd.service swap.target

[Service]
Type=oneshot
ExecStart=/usr/libexec/adwaita-lite-first-boot
ConditionPathExists=/var/lib/adwaita-lite/install-config.json
ConditionPathExists=!/var/lib/adwaita-lite/setup-done

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 3: Commit**

```bash
git add files/usr/libexec/adwaita-lite-first-boot \
        files/etc/systemd/system/adwaita-lite-first-boot.service
git commit -m "feat: add first-boot service for installer-deployed systems"
```

---

### Task 3: Add Disk page and update page constants

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

This task adds the new Disk page (Page 1) and updates all page constants and navigation to support 7 pages.

- [ ] **Step 1: Update imports and constants**

At the top of the file, add `json` to imports. Change line 18 from:

```python
import os
```

to:

```python
import json
import os
```

Remove `import pwd` (line 19) — it is no longer used (AccountsService D-Bus user creation is replaced by `useradd --root`).

Add `FILESYSTEMS` constant and update `SWAP_SIZES`. Change lines 250–262 from:

```python
SWAP_STRATEGIES = [
    "Compressed RAM only (zram) — fast, but apps may close if memory fills",
    "Compressed RAM + disk backup (zswap) — slower overflow to disk, apps stay open",
]

SWAP_SIZES = ["2 GB", "4 GB", "Custom"]

PAGE_NETWORK = 0
PAGE_ACCOUNT = 1
PAGE_SYSTEM = 2
PAGE_APPS = 3
PAGE_CONFIRM = 4
PAGE_PROGRESS = 5
```

to:

```python
SWAP_STRATEGIES = [
    "Compressed RAM only (zram) — fast, but apps may close if memory fills",
    "Compressed RAM + disk backup (zswap) — slower overflow to disk, apps stay open",
]

SWAP_SIZES = ["2 GB", "4 GB", "8 GB", "Custom"]

FILESYSTEMS = ["ext4", "xfs", "btrfs"]

PAGE_NETWORK = 0
PAGE_DISK = 1
PAGE_ACCOUNT = 2
PAGE_SYSTEM = 3
PAGE_APPS = 4
PAGE_CONFIRM = 5
PAGE_PROGRESS = 6
```

- [ ] **Step 2: Add warning-label CSS class**

In the `CSS` string, add after the `.progress-skipped` block (before the closing `"""`):

```css

.warning-label {
    font-family: "Roboto", sans-serif;
    font-size: 14px;
    color: #ff6b6b;
    font-weight: bold;
    margin-top: 16px;
}
```

- [ ] **Step 3: Add `_load_drives()` module-level helper**

Add after the `_load_timezones()` function (after line 307):

```python

def _load_drives() -> list[dict]:
    """Return list of eligible target drives from lsblk, excluding the boot device."""
    try:
        result = subprocess.run(
            ["lsblk", "--json", "--output", "NAME,SIZE,MODEL,TRAN,RM,TYPE"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired):
        return []

    # Identify the disk backing / so we can exclude the boot USB
    boot_disk = ""
    try:
        root_result = subprocess.run(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            capture_output=True, text=True, timeout=5,
        )
        boot_disk = re.sub(r"p?\d+$", "", os.path.basename(root_result.stdout.strip()))
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    drives = []
    for dev in data.get("blockdevices", []):
        if dev.get("type") != "disk":
            continue
        if dev.get("name") == boot_disk:
            continue
        drives.append(dev)
    return drives
```

- [ ] **Step 4: Add `_build_disk_page()` method**

Add the new method to `SetupWizardWindow`, after `_build_network_page()` (after line 534):

```python
    def _build_disk_page(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_halign(Gtk.Align.CENTER)
        wrapper.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(480, -1)

        title = Gtk.Label(label="Choose Installation Disk")
        title.add_css_class("welcome-title")
        title.set_halign(Gtk.Align.CENTER)
        card.append(title)

        subtitle = Gtk.Label(label="Select the target drive and installation options.")
        subtitle.add_css_class("welcome-subtitle")
        subtitle.set_halign(Gtk.Align.CENTER)
        card.append(subtitle)

        # --- Target drive ---
        card.append(self._make_label("Target drive"))
        self._drives = _load_drives()
        drive_labels = []
        for d in self._drives:
            model = d.get("model") or "Unknown"
            label = f"{d['name']} \u2014 {d['size']} {model}"
            tran = d.get("tran")
            if tran:
                label += f" ({tran})"
            drive_labels.append(label)
        if not drive_labels:
            drive_labels = ["No eligible drives found"]
        drive_model = Gtk.StringList.new(drive_labels)
        self._drive_dropdown = Gtk.DropDown(model=drive_model)
        self._drive_dropdown.set_hexpand(True)
        card.append(self._drive_dropdown)

        # --- Filesystem ---
        card.append(self._make_label("Filesystem"))
        fs_model = Gtk.StringList.new(FILESYSTEMS)
        self._fs_dropdown = Gtk.DropDown(model=fs_model)
        self._fs_dropdown.set_hexpand(True)
        self._fs_dropdown.set_selected(0)  # ext4 default
        card.append(self._fs_dropdown)

        # --- Memory management (moved from System page) ---
        card.append(self._make_label("Memory management"))
        swap_model = Gtk.StringList.new(SWAP_STRATEGIES)
        self._swap_strategy_dropdown = Gtk.DropDown(model=swap_model)
        self._swap_strategy_dropdown.set_hexpand(True)
        self._swap_strategy_dropdown.set_selected(0)
        card.append(self._swap_strategy_dropdown)

        # Swap size controls (visible only when zswap selected)
        self._swap_size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self._swap_size_box.append(self._make_label("Disk swap size"))
        swap_size_model = Gtk.StringList.new(SWAP_SIZES)
        self._swap_size_dropdown = Gtk.DropDown(model=swap_size_model)
        self._swap_size_dropdown.set_hexpand(True)
        self._swap_size_dropdown.set_selected(0)
        self._swap_size_box.append(self._swap_size_dropdown)

        self._custom_size_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._custom_size_box.append(self._make_label("Custom size (GB)"))
        self._custom_size_entry = Gtk.Entry()
        self._custom_size_entry.set_placeholder_text("8")
        self._custom_size_entry.add_css_class("form-entry")
        self._custom_size_entry.set_hexpand(True)
        self._custom_size_box.append(self._custom_size_entry)
        self._custom_size_box.set_visible(False)
        self._swap_size_box.append(self._custom_size_box)

        desc = Gtk.Label(
            label="zswap uses compressed RAM as a cache and spills to a disk swap file when full."
        )
        desc.add_css_class("form-description")
        desc.set_halign(Gtk.Align.START)
        desc.set_wrap(True)
        desc.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        desc.set_max_width_chars(50)
        self._swap_size_box.append(desc)

        self._swap_size_box.set_visible(False)
        card.append(self._swap_size_box)

        self._swap_strategy_dropdown.connect("notify::selected", self._on_swap_strategy_changed)
        self._swap_size_dropdown.connect("notify::selected", self._on_swap_size_changed)

        # --- Warning ---
        warning = Gtk.Label(label="All data on the selected drive will be erased.")
        warning.add_css_class("warning-label")
        warning.set_halign(Gtk.Align.CENTER)
        card.append(warning)

        wrapper.append(card)
        scrolled.set_child(wrapper)
        return scrolled
```

- [ ] **Step 5: Update `__init__` — add disk page to stack and fix defaults**

In `SetupWizardWindow.__init__`, update the stack construction. Change lines 339–344 from:

```python
        self._stack.add_named(self._build_network_page(), "network")
        self._stack.add_named(self._build_account_page(), "account")
        self._stack.add_named(self._build_system_page(), "system")
        self._stack.add_named(self._build_apps_page(), "apps")
        self._stack.add_named(self._build_confirm_page(), "confirm")
        self._stack.add_named(self._build_progress_page(), "progress")
```

to:

```python
        self._stack.add_named(self._build_network_page(), "network")
        self._stack.add_named(self._build_disk_page(), "disk")
        self._stack.add_named(self._build_account_page(), "account")
        self._stack.add_named(self._build_system_page(), "system")
        self._stack.add_named(self._build_apps_page(), "apps")
        self._stack.add_named(self._build_confirm_page(), "confirm")
        self._stack.add_named(self._build_progress_page(), "progress")
```

Update the default page (line 319). Change:

```python
        self._current_page = PAGE_ACCOUNT  # Start at Account (network skipped by default)
```

to:

```python
        self._current_page = PAGE_DISK  # Start at Disk (network skipped by default)
```

Update the step label initial text (line 329). Change:

```python
        self._step_label = Gtk.Label(label="Step 1 of 4")
```

to:

```python
        self._step_label = Gtk.Label(label="Step 1 of 6")
```

- [ ] **Step 6: Update navigation methods**

Update `_get_pages()` (line 1121). Change:

```python
    def _get_pages(self) -> list[str]:
        """Return ordered page names, excluding auto-skipped network."""
        pages = ["network", "account", "system", "apps", "confirm", "progress"]
        if self._network_skipped:
            pages.remove("network")
        return pages
```

to:

```python
    def _get_pages(self) -> list[str]:
        """Return ordered page names, excluding auto-skipped network."""
        pages = ["network", "disk", "account", "system", "apps", "confirm", "progress"]
        if self._network_skipped:
            pages.remove("network")
        return pages
```

Update `_get_first_page()` (line 1128). Change:

```python
    def _get_first_page(self) -> int:
        return PAGE_ACCOUNT if self._network_skipped else PAGE_NETWORK
```

to:

```python
    def _get_first_page(self) -> int:
        return PAGE_DISK if self._network_skipped else PAGE_NETWORK
```

Update `_update_navigation()` page_names dict (line 1154). Change:

```python
        page_names = {
            PAGE_NETWORK: "network", PAGE_ACCOUNT: "account",
            PAGE_SYSTEM: "system", PAGE_APPS: "apps",
            PAGE_CONFIRM: "confirm", PAGE_PROGRESS: "progress",
        }
```

to:

```python
        page_names = {
            PAGE_NETWORK: "network", PAGE_DISK: "disk",
            PAGE_ACCOUNT: "account", PAGE_SYSTEM: "system",
            PAGE_APPS: "apps", PAGE_CONFIRM: "confirm",
            PAGE_PROGRESS: "progress",
        }
```

Update the focus handling at the end of `_update_navigation()` (line 1180). Change:

```python
        if self._current_page == PAGE_ACCOUNT:
            self._fullname_entry.grab_focus()
        elif self._current_page == PAGE_SYSTEM:
            self._tz_dropdown.grab_focus()
```

to:

```python
        if self._current_page == PAGE_DISK:
            self._drive_dropdown.grab_focus()
        elif self._current_page == PAGE_ACCOUNT:
            self._fullname_entry.grab_focus()
        elif self._current_page == PAGE_SYSTEM:
            self._tz_dropdown.grab_focus()
```

Update `_on_connectivity_checked()` (line 840). Change:

```python
        if self._current_page == PAGE_ACCOUNT:
            self._current_page = PAGE_NETWORK
```

to:

```python
        if self._current_page == PAGE_DISK:
            self._current_page = PAGE_NETWORK
```

- [ ] **Step 7: Add `_validate_disk()` and update `_validate_page()`**

Add new validation method after `_validate_account()`:

```python
    def _validate_disk(self) -> bool:
        if not self._drives:
            self._set_status("No target drives found. Connect a drive and restart the installer.")
            return False

        use_zswap, swap_gb = self._get_swap_config()
        if use_zswap and swap_gb == -1:
            self._set_status("Custom swap size must be a positive whole number (in GB).")
            return False
        return True
```

Update `_validate_page()` (line 1190). Change:

```python
    def _validate_page(self, page: int) -> bool:
        if page == PAGE_ACCOUNT:
            return self._validate_account()
        elif page == PAGE_SYSTEM:
            return self._validate_system()
        return True  # Network, Apps, Confirm have no blocking validation
```

to:

```python
    def _validate_page(self, page: int) -> bool:
        if page == PAGE_DISK:
            return self._validate_disk()
        elif page == PAGE_ACCOUNT:
            return self._validate_account()
        elif page == PAGE_SYSTEM:
            return self._validate_system()
        return True  # Network, Apps, Confirm have no blocking validation
```

- [ ] **Step 8: Update `_get_swap_config()` and `_on_swap_size_changed()` for 8 GB option**

Update `_get_swap_config()` (line 1311). Change:

```python
    def _get_swap_config(self) -> tuple[bool, int]:
        use_zswap = self._swap_strategy_dropdown.get_selected() == 1
        swap_gb = 2

        if use_zswap:
            size_idx = self._swap_size_dropdown.get_selected()
            if size_idx == 0:
                swap_gb = 2
            elif size_idx == 1:
                swap_gb = 4
            else:
                custom_text = self._custom_size_entry.get_text().strip()
                try:
                    swap_gb = int(custom_text)
                    if swap_gb <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError):
                    swap_gb = -1

        return use_zswap, swap_gb
```

to:

```python
    def _get_swap_config(self) -> tuple[bool, int]:
        use_zswap = self._swap_strategy_dropdown.get_selected() == 1
        swap_gb = 2

        if use_zswap:
            size_idx = self._swap_size_dropdown.get_selected()
            if size_idx == 0:
                swap_gb = 2
            elif size_idx == 1:
                swap_gb = 4
            elif size_idx == 2:
                swap_gb = 8
            else:
                custom_text = self._custom_size_entry.get_text().strip()
                try:
                    swap_gb = int(custom_text)
                    if swap_gb <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError):
                    swap_gb = -1

        return use_zswap, swap_gb
```

Update `_on_swap_size_changed()` (line 1287). Change:

```python
    def _on_swap_size_changed(self, dropdown: Gtk.DropDown, _pspec: object) -> None:
        self._custom_size_box.set_visible(dropdown.get_selected() == 2)
```

to:

```python
    def _on_swap_size_changed(self, dropdown: Gtk.DropDown, _pspec: object) -> None:
        self._custom_size_box.set_visible(dropdown.get_selected() == 3)
```

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: add Disk page (drive, filesystem, memory management) and 7-page layout"
```

---

### Task 4: Simplify System page

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

Remove memory management and partition expansion from the System page (they moved to the Disk page in Task 3).

- [ ] **Step 1: Strip System page builder**

In `_build_system_page()`, remove everything between the timezone dropdown and the administrator checkbox. The method should become:

```python
    def _build_system_page(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_halign(Gtk.Align.CENTER)
        wrapper.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(480, -1)

        title = Gtk.Label(label="System Setup")
        title.add_css_class("welcome-title")
        title.set_halign(Gtk.Align.CENTER)
        card.append(title)

        # Timezone
        card.append(self._make_label("Timezone"))
        tz_model = Gtk.StringList.new(self._timezones)
        self._tz_dropdown = Gtk.DropDown(model=tz_model)
        self._tz_dropdown.set_hexpand(True)
        default_tz_idx = 0
        for i, tz in enumerate(self._timezones):
            if tz == "America/New_York":
                default_tz_idx = i
                break
        self._tz_dropdown.set_selected(default_tz_idx)
        card.append(self._tz_dropdown)

        # Administrator checkbox
        self._admin_check = Gtk.CheckButton(label="Administrator account (sudo)")
        self._admin_check.set_active(True)
        self._admin_check.add_css_class("form-label")
        card.append(self._admin_check)

        # Root password
        card.append(self._make_label("Root Password (optional)"))
        self._root_password_entry = Gtk.PasswordEntry()
        self._root_password_entry.set_show_peek_icon(True)
        self._root_password_entry.add_css_class("form-entry")
        self._root_password_entry.set_hexpand(True)
        self._root_password_entry.connect("activate", lambda _: self._go_next())
        card.append(self._root_password_entry)

        wrapper.append(card)
        scrolled.set_child(wrapper)
        return scrolled
```

Removed: memory management dropdown, swap size box, custom size entry, swap description, partition expansion checkbox, partition expansion description, and the two signal connections (`_swap_strategy_dropdown` and `_swap_size_dropdown` `notify::selected`) — those are now in `_build_disk_page()`.

- [ ] **Step 2: Simplify `_validate_system()`**

Replace the entire method:

```python
    def _validate_system(self) -> bool:
        is_admin = self._admin_check.get_active()
        root_password = self._root_password_entry.get_text()
        if not is_admin and not root_password:
            self._set_status(
                "Either enable administrator access or set a root password. "
                "Without one of these you will be locked out of system management."
            )
            return False
        return True
```

(Removed the `_get_swap_config()` validation — that's now in `_validate_disk()`.)

- [ ] **Step 3: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "refactor: simplify System page — memory management moved to Disk page"
```

---

### Task 5: Implement install pipeline step functions

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

Replace the old step functions (AccountsService user creation, direct swap/zswap setup) with the new `bootc install to-disk` pipeline that writes configuration directly to the mounted sysroot.

- [ ] **Step 1: Add sysroot mount/unmount helpers**

Add these methods to `SetupWizardWindow`, in the step functions section (before the existing `_step_create_user`):

```python
    # ------------------------------------------------------------------
    # Sysroot management (installer mode)
    # ------------------------------------------------------------------

    def _mount_sysroot(self) -> str | None:
        """Mount the installed system's root partition and locate the ostree deployment.

        Sets self._sysroot_mount, self._sysroot_deploy, and self._sysroot_var.
        Returns an error string or None on success.
        """
        target = self._setup_target_drive
        mount_point = "/mnt/sysroot"

        # Find root partition (last partition on the target disk)
        try:
            result = subprocess.run(
                ["lsblk", "-lnpo", "NAME,TYPE", f"/dev/{target}"],
                capture_output=True, text=True, check=True, timeout=10,
            )
            parts = [
                line.split()[0]
                for line in result.stdout.strip().splitlines()
                if len(line.split()) >= 2 and line.split()[1] == "part"
            ]
            if not parts:
                return "No partitions found on target disk after install"
            root_part = parts[-1]
        except subprocess.CalledProcessError as exc:
            return f"Failed to list partitions: {exc.stderr.strip() or exc}"

        Path(mount_point).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["mount", root_part, mount_point],
                check=True, capture_output=True, text=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            return f"Failed to mount sysroot: {exc.stderr.strip() or exc}"

        # Locate ostree deployment
        deploy_dirs = sorted(Path(mount_point).glob("ostree/deploy/*/deploy/*/"))
        if not deploy_dirs:
            return "No ostree deployment found on installed system"
        self._sysroot_deploy = str(deploy_dirs[-1])

        var_dirs = list(Path(mount_point).glob("ostree/deploy/*/var"))
        if not var_dirs:
            return "No var directory found on installed system"
        self._sysroot_var = str(var_dirs[0])

        self._sysroot_mount = mount_point
        return None

    def _unmount_sysroot(self) -> str | None:
        """Unmount the sysroot. Returns error string or None."""
        try:
            subprocess.run(
                ["umount", "-R", self._sysroot_mount],
                check=True, capture_output=True, text=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            return f"Failed to unmount sysroot: {exc.stderr.strip() or exc}"
        return None
```

- [ ] **Step 2: Add `_step_bootc_install()`**

```python
    # ------------------------------------------------------------------
    # Install pipeline steps
    # ------------------------------------------------------------------

    def _step_bootc_install(self) -> str | None:
        """Partition disk and install OS image via bootc, then mount sysroot."""
        target = self._setup_target_drive
        fs = self._setup_filesystem

        try:
            subprocess.run(
                ["bootc", "install", "to-disk", "--filesystem", fs,
                 f"/dev/{target}"],
                check=True, capture_output=True, text=True, timeout=900,
            )
        except subprocess.CalledProcessError as exc:
            return f"Installation failed: {exc.stderr.strip() or exc}"
        except subprocess.TimeoutExpired:
            return "Installation timed out after 15 minutes"

        # Mount sysroot for post-install configuration
        err = self._mount_sysroot()
        if err:
            return err

        return None
```

- [ ] **Step 3: Add `_step_configure_user()`**

```python
    def _step_configure_user(self) -> str | None:
        """Create user account, set root password, timezone, and locale on sysroot."""
        deploy = self._sysroot_deploy
        var_dir = self._sysroot_var
        username = self._setup_username
        fullname = self._setup_fullname

        try:
            hashed_pw = _hash_password(self._setup_password)
        except subprocess.CalledProcessError as exc:
            return f"Failed to hash password: {exc.stderr.strip() or exc}"

        # Create user in sysroot's /etc/passwd
        groups = "video"
        if self._setup_is_admin:
            groups = "wheel,video"

        try:
            subprocess.run(
                ["useradd", "--root", deploy,
                 "--home-dir", f"/var/home/{username}",
                 "--shell", "/bin/bash",
                 "--groups", groups,
                 "--password", hashed_pw,
                 "--comment", fullname,
                 username],
                check=True, capture_output=True, text=True, timeout=15,
            )
        except subprocess.CalledProcessError as exc:
            return f"Failed to create user: {exc.stderr.strip() or exc}"

        # Create home directory in the var partition (ostree keeps /home in /var/home)
        home = Path(var_dir) / "home" / username
        home.mkdir(parents=True, exist_ok=True)

        # Copy skeleton files
        skel = Path(deploy) / "etc" / "skel"
        if skel.is_dir():
            subprocess.run(
                ["cp", "-a", f"{skel}/.", str(home)],
                check=False, capture_output=True, timeout=10,
            )

        # Read the UID/GID assigned by useradd for correct ownership
        uid = gid = "1000"
        try:
            with open(Path(deploy) / "etc" / "passwd") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if parts[0] == username:
                        uid, gid = parts[2], parts[3]
                        break
        except (OSError, IndexError):
            pass

        subprocess.run(
            ["chown", "-R", f"{uid}:{gid}", str(home)],
            check=False, capture_output=True, timeout=10,
        )

        # Set root password if provided
        if self._setup_root_password:
            try:
                root_hash = _hash_password(self._setup_root_password)
                subprocess.run(
                    ["chpasswd", "--root", deploy, "-e"],
                    input=f"root:{root_hash}\n",
                    check=True, capture_output=True, text=True, timeout=10,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                return f"Failed to set root password: {exc}"

        # Set timezone
        tz = self._setup_timezone
        localtime = Path(deploy) / "etc" / "localtime"
        localtime.unlink(missing_ok=True)
        localtime.symlink_to(f"/usr/share/zoneinfo/{tz}")

        # Set locale
        (Path(deploy) / "etc" / "locale.conf").write_text(f"LANG=en_US.UTF-8\n")

        return None
```

- [ ] **Step 4: Add `_step_copy_network()`**

```python
    def _step_copy_network(self) -> str | None:
        """Copy NetworkManager connection profiles from live environment to sysroot."""
        src = "/etc/NetworkManager/system-connections/"
        dst = f"{self._sysroot_deploy}/etc/NetworkManager/system-connections/"

        if not os.path.isdir(src) or not os.listdir(src):
            return None  # No connections to copy (ethernet auto-connects without profiles)

        os.makedirs(dst, exist_ok=True)

        try:
            subprocess.run(
                ["rsync", "-a", src, dst],
                check=True, capture_output=True, text=True, timeout=30,
            )
        except subprocess.CalledProcessError as exc:
            return f"Failed to copy network configuration: {exc.stderr.strip() or exc}"

        return None
```

- [ ] **Step 5: Add `_step_copy_flatpaks()`**

```python
    def _step_copy_flatpaks(self) -> str | None:
        """rsync selected Flatpak apps from live USB to installed sysroot."""
        var_dir = self._sysroot_var
        selected_ids = {app_id for app_id, _ in self._setup_selected_apps}
        src = "/var/lib/flatpak"
        dst = f"{var_dir}/lib/flatpak"

        if not os.path.isdir(src):
            return "Flatpak store not found on live environment"

        Path(dst).mkdir(parents=True, exist_ok=True)

        # Copy shared infrastructure: repo (ostree object store), exports, runtimes
        for subdir in ["repo", "exports", "runtime", ".changed"]:
            src_path = f"{src}/{subdir}"
            if not os.path.exists(src_path):
                continue
            try:
                subprocess.run(
                    ["rsync", "-a", f"{src_path}/", f"{dst}/{subdir}/"],
                    check=True, capture_output=True, text=True, timeout=600,
                )
            except subprocess.CalledProcessError as exc:
                return f"Failed to copy Flatpak data ({subdir}): {exc.stderr.strip() or exc}"

        # Copy only selected app directories
        app_src = f"{src}/app"
        app_dst = f"{dst}/app"
        os.makedirs(app_dst, exist_ok=True)

        failed = []
        for app_id in selected_ids:
            src_app = f"{app_src}/{app_id}"
            if not os.path.isdir(src_app):
                continue
            try:
                subprocess.run(
                    ["rsync", "-a", f"{src_app}/", f"{app_dst}/{app_id}/"],
                    check=True, capture_output=True, text=True, timeout=300,
                )
            except subprocess.CalledProcessError:
                failed.append(app_id)

        if failed:
            return f"Failed to copy: {', '.join(failed)}"

        # Write app list for boot-time fallback service
        state_dir = Path(var_dir) / "lib" / "adwaita-lite"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "flatpak-apps").write_text("\n".join(selected_ids) + "\n")

        # Mark as complete so boot service doesn't re-run
        (state_dir / "flatpak-setup.done").write_text("")

        return None
```

- [ ] **Step 6: Add `_step_configure_memory()`**

```python
    def _step_configure_memory(self) -> str | None:
        """Write memory management configuration to the sysroot."""
        deploy = self._sysroot_deploy
        var_dir = self._sysroot_var

        state_dir = Path(var_dir) / "lib" / "adwaita-lite"
        state_dir.mkdir(parents=True, exist_ok=True)

        if self._setup_use_zswap:
            # Write swap size for the first-boot service
            (state_dir / "swap-size").write_text(str(self._setup_swap_gb))

            # Persist swappiness for disk-backed swap
            sysctl_dir = Path(deploy) / "etc" / "sysctl.d"
            sysctl_dir.mkdir(parents=True, exist_ok=True)
            (sysctl_dir / "91-adwaita-lite-zswap.conf").write_text(
                "vm.swappiness = 100\n"
            )
        else:
            # Explicitly write the zram-generator config to the sysroot
            # (ensures 125% even if the image default changes later)
            zram_dir = Path(deploy) / "etc" / "systemd"
            zram_dir.mkdir(parents=True, exist_ok=True)
            (zram_dir / "zram-generator.conf").write_text(
                "[zram0]\n"
                "zram-size = min(ram * 5 / 4, 3072)\n"
                "compression-algorithm = zstd(level=3)\n"
                "swap-priority = 100\n"
            )

        return None
```

- [ ] **Step 7: Add `_step_finalize()`**

```python
    def _step_finalize(self) -> str | None:
        """Write first-boot config JSON and unmount the sysroot."""
        var_dir = self._sysroot_var

        # Write install config for first-boot service
        state_dir = Path(var_dir) / "lib" / "adwaita-lite"
        state_dir.mkdir(parents=True, exist_ok=True)

        config = {
            "memory_strategy": "zswap" if self._setup_use_zswap else "zram",
            "swap_size_gb": self._setup_swap_gb if self._setup_use_zswap else None,
            "username": self._setup_username,
        }
        (state_dir / "install-config.json").write_text(
            json.dumps(config, indent=2) + "\n"
        )

        # Unmount sysroot
        err = self._unmount_sysroot()
        if err:
            return err

        return None
```

- [ ] **Step 8: Remove old step functions**

Delete these methods entirely:
- `_step_create_user()` (AccountsService D-Bus user creation — replaced by `_step_configure_user`)
- `_step_configure_system()` (timedatectl, systemctl enable — replaced by direct sysroot writes)
- `_step_configure_zswap()` (runtime zswap config — replaced by first-boot service)
- `_step_create_swap_file()` (direct swap creation — replaced by first-boot service)
- `_step_install_flatpaks()` (Flatpak download from Flathub — replaced by `_step_copy_flatpaks` rsync)

Also remove the `FLATHUB_URL` constant (line 271) — it was only used by `_step_install_flatpaks` which is now deleted. The boot-time flatpak-setup script has its own URL.

- [ ] **Step 9: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 10: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: replace wizard step functions with bootc install-to-disk pipeline"
```

---

### Task 6: Wire up step runner and form capture

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

Connect the new step functions to the step runner, update form value capture, and update error handling for the three-behavior model (fatal / retry / skippable).

- [ ] **Step 1: Rewrite `_on_setup_clicked()`**

Replace the entire method:

```python
    def _on_setup_clicked(self) -> None:
        # Capture all form values for thread-safe access
        # Disk page
        drive_idx = self._drive_dropdown.get_selected()
        self._setup_target_drive = self._drives[drive_idx]["name"]
        self._setup_filesystem = FILESYSTEMS[self._fs_dropdown.get_selected()]
        self._setup_use_zswap, self._setup_swap_gb = self._get_swap_config()

        # Account page
        self._setup_fullname = self._fullname_entry.get_text().strip()
        self._setup_username = self._username_entry.get_text().strip()
        self._setup_password = self._password_entry.get_text()

        # System page
        self._setup_is_admin = self._admin_check.get_active()
        self._setup_root_password = self._root_password_entry.get_text()
        self._setup_timezone = self._get_selected_timezone()

        # Apps
        self._setup_selected_apps = self._get_selected_apps()

        # Build step list: (label, callable, error_behavior)
        # error_behavior: "fatal" = Back button, "retry" = Retry button,
        #                 "skippable" = Skip + Retry buttons
        self._steps: list[tuple[str, callable, str]] = [
            ("Partitioning and installing", self._step_bootc_install, "fatal"),
            ("Configuring user account", self._step_configure_user, "retry"),
            ("Copying network configuration", self._step_copy_network, "retry"),
        ]
        if self._setup_selected_apps:
            self._steps.append((
                "Installing selected apps",
                self._step_copy_flatpaks,
                "skippable",
            ))
        self._steps.append(("Configuring memory management", self._step_configure_memory, "retry"))
        self._steps.append(("Finalizing", self._step_finalize, "retry"))

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
```

- [ ] **Step 2: Update `_start_step_runner()` for string behavior**

The thread loop unpacks the third element as `behavior` (string) instead of `is_flatpak` (bool). Replace the entire method:

```python
    def _start_step_runner(self) -> None:
        """Launch the step-runner thread starting from self._run_from_step."""
        self._progress_back_btn.set_visible(False)
        self._progress_skip_btn.set_visible(False)
        self._progress_retry_btn.set_visible(False)
        self._progress_reboot_btn.set_visible(False)

        start = self._run_from_step

        def _thread() -> None:
            for i in range(start, len(self._steps)):
                label_text, func, behavior = self._steps[i]
                GLib.idle_add(self._update_step_status, i, "active")
                err = func()
                if err:
                    GLib.idle_add(self._on_step_failed, i, err, behavior)
                    return
                GLib.idle_add(self._update_step_status, i, "done")

            GLib.idle_add(self._on_all_steps_done)

        threading.Thread(target=_thread, daemon=True).start()
```

- [ ] **Step 3: Update `_on_step_failed()` for three-behavior error handling**

Replace the entire method:

```python
    def _on_step_failed(self, index: int, error: str, behavior: str) -> None:
        lbl = self._step_labels[index]
        label_text = self._steps[index][0]
        lbl.set_text(f"  {label_text} \u2014 {error}")

        for cls in ("progress-pending", "progress-active", "progress-done"):
            lbl.remove_css_class(cls)
        lbl.add_css_class("progress-failed")

        if behavior == "fatal":
            # bootc install failed — user can go back and change settings
            self._progress_back_btn.set_visible(True)
        elif behavior == "skippable":
            # Flatpak copy failed — user can skip or retry
            self._progress_retry_btn.set_visible(True)
            self._progress_skip_btn.set_visible(True)
            self._run_from_step = index
        else:  # "retry"
            # Post-install config failed — retry from this step
            self._progress_retry_btn.set_visible(True)
            self._run_from_step = index
```

- [ ] **Step 4: Update `_progress_skip()` to continue with remaining steps**

Replace the entire method:

```python
    def _progress_skip(self) -> None:
        """Skip the current (skippable) step and continue with the rest."""
        self._update_step_status(self._run_from_step, "skipped")
        self._run_from_step += 1
        if self._run_from_step >= len(self._steps):
            self._on_all_steps_done()
        else:
            self._start_step_runner()
```

- [ ] **Step 5: Simplify `_on_all_steps_done()`**

The installer writes `setup-done` and `last-user` via the first-boot service on the installed system. The live USB no longer needs these. Replace:

```python
    def _on_all_steps_done(self) -> None:
        self._progress_title.set_text("Installation Complete!")
        self._progress_reboot_btn.set_visible(True)
```

- [ ] **Step 6: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: wire up bootc install pipeline with three-behavior error handling"
```

---

### Task 7: Update Confirm page, Apps page, and docstring

**Files:**
- Modify: `files/usr/bin/adwaita-lite-setup-wizard`

- [ ] **Step 1: Update `_build_confirm_page()`**

Replace the summary row definitions. The new page includes target drive and filesystem, and removes partition expansion:

```python
    def _build_confirm_page(self) -> Gtk.ScrolledWindow:
        scrolled = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_propagate_natural_height(True)

        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        wrapper.set_halign(Gtk.Align.CENTER)
        wrapper.set_valign(Gtk.Align.CENTER)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(480, -1)

        title = Gtk.Label(label="Ready to Install")
        title.add_css_class("welcome-title")
        title.set_halign(Gtk.Align.CENTER)
        card.append(title)

        subtitle = Gtk.Label(label="Review your settings and click Install to begin.")
        subtitle.add_css_class("welcome-subtitle")
        subtitle.set_halign(Gtk.Align.CENTER)
        card.append(subtitle)

        self._summary_network = self._make_summary_row(card, "Network")
        self._summary_drive = self._make_summary_row(card, "Target drive")
        self._summary_filesystem = self._make_summary_row(card, "Filesystem")
        self._summary_memory = self._make_summary_row(card, "Memory")
        self._summary_name = self._make_summary_row(card, "Name")
        self._summary_username = self._make_summary_row(card, "Username")
        self._summary_timezone = self._make_summary_row(card, "Timezone")
        self._summary_admin = self._make_summary_row(card, "Administrator")
        self._summary_root = self._make_summary_row(card, "Root password")
        self._summary_apps = self._make_summary_row(card, "Apps")

        wrapper.append(card)
        scrolled.set_child(wrapper)
        return scrolled
```

- [ ] **Step 2: Add drive/filesystem display helpers**

Add these methods in the field readers section:

```python
    def _get_selected_drive_display(self) -> str:
        """Return human-readable description of the selected target drive."""
        if not self._drives:
            return "None"
        idx = self._drive_dropdown.get_selected()
        if idx < 0 or idx >= len(self._drives):
            return "None"
        d = self._drives[idx]
        model = d.get("model") or "Unknown"
        return f"{d['name']} \u2014 {d['size']} {model}"

    def _get_selected_filesystem(self) -> str:
        """Return the selected filesystem name."""
        idx = self._fs_dropdown.get_selected()
        if 0 <= idx < len(FILESYSTEMS):
            return FILESYSTEMS[idx]
        return "ext4"
```

- [ ] **Step 3: Rewrite `_populate_summary()`**

Replace the entire method:

```python
    def _populate_summary(self) -> None:
        # Network
        if self._connected_ssid == "(Wired)":
            self._summary_network.set_text("Wired connection")
        elif self._connected_ssid:
            self._summary_network.set_text(f"Connected to {self._connected_ssid}")
        else:
            self._summary_network.set_text("No network (offline install)")

        # Disk
        self._summary_drive.set_text(self._get_selected_drive_display())
        self._summary_filesystem.set_text(self._get_selected_filesystem())

        # Memory
        use_zswap, swap_gb = self._get_swap_config()
        if use_zswap:
            self._summary_memory.set_text(f"zswap with {swap_gb} GB disk swap")
        else:
            self._summary_memory.set_text("zram only (compressed RAM)")

        # Account
        self._summary_name.set_text(self._fullname_entry.get_text().strip())
        self._summary_username.set_text(self._username_entry.get_text().strip())
        self._summary_timezone.set_text(self._get_selected_timezone())
        self._summary_admin.set_text("Yes" if self._admin_check.get_active() else "No")
        self._summary_root.set_text(
            "Set" if self._root_password_entry.get_text() else "Not set"
        )

        # Apps
        selected = self._get_selected_apps()
        if selected:
            self._summary_apps.set_text(", ".join(name for _, name in selected))
        else:
            self._summary_apps.set_text("No apps selected")
```

- [ ] **Step 4: Update Apps page subtitle**

In `_build_apps_page()`, change the subtitle text from:

```python
        subtitle = Gtk.Label(
            label="These apps will be installed during setup. Uncheck any you don't want."
        )
```

to:

```python
        subtitle = Gtk.Label(
            label="These apps are pre-downloaded and will be copied during install. Uncheck any you don't want."
        )
```

- [ ] **Step 5: Update button label and progress title**

In `_update_navigation()`, change `"Set Up"` to `"Install"`:

```python
        self._next_button.set_label(
            "Install" if self._current_page == PAGE_CONFIRM else "Next"
        )
```

In `_build_progress_page()`, change the title from `"Setting Up..."` to `"Installing..."`:

```python
        title = Gtk.Label(label="Installing...")
```

- [ ] **Step 6: Update module docstring**

Replace lines 1–16 (the module docstring) with:

```python
#!/usr/bin/env python3
"""Adwaita-Lite USB installer wizard.

Launched by greetd's initial_session inside a labwc desktop session on
the USB live environment when no user accounts exist.  Installs the OS
to a target disk via bootc, configures the sysroot directly (Anaconda
pattern), and rsyncs pre-downloaded Flatpak apps from the live
environment.

Seven-page flow:
  Page 0 — Network (WiFi scan-and-connect, auto-skipped if online)
  Page 1 — Disk (target drive, filesystem, memory management)
  Page 2 — Account (name, username, password)
  Page 3 — System setup (timezone, admin/root)
  Page 4 — Apps (Flatpak app selection — rsync from USB)
  Page 5 — Summary and confirmation
  Page 6 — Progress (real-time install execution)
"""
```

- [ ] **Step 7: Update `_hash_password` docstring**

Change the docstring from:

```python
    """Return a SHA-512 crypt(3) hash suitable for AccountsService.SetPassword."""
```

to:

```python
    """Return a SHA-512 crypt(3) hash suitable for useradd --password."""
```

- [ ] **Step 8: Verify syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "feat: update confirm/apps/progress pages for installer mode"
```

---

### Task 8: Update build.sh

**Files:**
- Modify: `build_files/build.sh`

- [ ] **Step 1: Add `rsync` to packages**

In the main `dnf5 install` block (line 15), add `rsync` to the package list. Insert it alphabetically after `python3-gobject`:

```
    python3-gobject \
    rsync \
    ristretto \
```

- [ ] **Step 2: Add first-boot script to chmod block**

In the chmod block (line 136), add `adwaita-lite-first-boot`. Insert after `adwaita-lite-encrypted-swap`:

```
    /usr/libexec/adwaita-lite-encrypted-swap \
    /usr/libexec/adwaita-lite-first-boot \
    /usr/libexec/adwaita-lite-flatpak-setup \
```

- [ ] **Step 3: Enable first-boot and flatpak-setup services**

After the existing `systemctl enable` block (after line 159), add:

```bash
systemctl enable adwaita-lite-first-boot.service
systemctl enable adwaita-lite-flatpak-setup.service
```

The first-boot service uses `ConditionPathExists` guards so it only runs when `install-config.json` exists and `setup-done` does not. The flatpak-setup service similarly checks for `flatpak-apps` and `flatpak-setup.done`.

- [ ] **Step 4: Commit**

```bash
git add build_files/build.sh
git commit -m "build: add rsync, first-boot service, flatpak-setup enablement"
```

---

### Task 9: Verify and clean up

- [ ] **Step 1: Python syntax check**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-setup-wizard').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 2: Verify no dangling references to removed features**

```bash
grep -rn "AccountsService\|_expand_root\|systemd-repart\|_step_create_user\|_step_configure_system\|_step_configure_zswap\|_step_create_swap_file\|_step_install_flatpaks\|import pwd\|FLATHUB_URL" files/usr/bin/adwaita-lite-setup-wizard
```

Expected: no output. If any matches found, remove them.

- [ ] **Step 3: Verify new references are consistent**

```bash
grep -rn "PAGE_DISK\|_build_disk_page\|_step_bootc_install\|_step_configure_user\|_step_copy_network\|_step_copy_flatpaks\|_step_configure_memory\|_step_finalize\|_mount_sysroot\|_unmount_sysroot\|install-config.json" files/usr/bin/adwaita-lite-setup-wizard
```

Expected: matches for all new functions and references.

- [ ] **Step 4: Verify first-boot service references**

```bash
grep -rn "adwaita-lite-first-boot" files/ build_files/
```

Expected: matches in:
- `files/usr/libexec/adwaita-lite-first-boot` (the script itself)
- `files/etc/systemd/system/adwaita-lite-first-boot.service` (the unit)
- `build_files/build.sh` (chmod + systemctl enable)

- [ ] **Step 5: Verify bash scripts are syntactically valid**

```bash
bash -n files/usr/libexec/adwaita-lite-first-boot && echo "OK"
```

Expected: `OK`

- [ ] **Step 6: Final commit if any cleanup was needed**

```bash
git diff --stat
```

If there are unstaged changes from cleanup:

```bash
git add files/usr/bin/adwaita-lite-setup-wizard
git commit -m "cleanup: remove dead code from pre-installer wizard"
```
