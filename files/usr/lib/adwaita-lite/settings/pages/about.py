import os
import socket
import subprocess
import sys
import threading
from gettext import gettext as _
from pathlib import Path

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage

CATEGORY_KEYS = {
    "Appearance": [
        "theme", "accent", "wallpaper",
    ],
    "Accessibility": [
        "font_size", "cursor_size", "high_contrast", "reduce_motion",
    ],
    "Display": [
        "scale", "night_light_enabled", "night_light_temp",
        "night_light_schedule", "night_light_start", "night_light_end",
    ],
    "Panel": [
        "edge", "layout", "pinned", "density",
        "panel_twilight",
    ],
    "Mouse & Touchpad": [
        "touchpad_tap_to_click", "touchpad_natural_scroll",
        "touchpad_pointer_speed", "touchpad_scroll_speed",
        "mouse_pointer_speed", "mouse_natural_scroll", "mouse_accel_profile",
    ],
    "Keyboard": [
        "keyboard_layout", "keyboard_variant",
        "keyboard_repeat_delay", "keyboard_repeat_rate",
        "capslock_behavior",
    ],
    "Power & Lock": [
        "lock_timeout", "display_off_timeout",
        "suspend_timeout", "lid_close_action",
        "power_profile",
    ],
    # Date & Time and Language categories live mostly in OS state
    # (timedatectl / localectl) rather than settings.json, so the actual
    # reset work is done via the out-of-band cleanup block in
    # _run_restore below. clock_24h is the one Date & Time key that does
    # live in settings.json, so it's listed here.
    "Date & Time": ["clock_24h"],
    "Language & Region": [],
}


def _row_title_text(text: str) -> str:
    """Escape row titles that libadwaita renders as Pango markup."""
    return GLib.markup_escape_text(text)


class AboutPage(BasePage, Adw.PreferencesPage):
    """About / Updates / Troubleshooting.

    Returns an AdwNavigationView from build() so the Restore Defaults
    flow can push a sub-page over the top-level preferences content.
    The page class itself is still Adw.PreferencesPage so all the
    usual `self.add(group)` calls work on the root page.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        # References populated in build() and touched from async
        # handlers. Start None so _set_update_button_visible and the
        # check-update callbacks are safe before build() has run.
        self._update_label: Adw.ActionRow | None = None
        self._update_btn: Gtk.Button | None = None
        self._nav: Adw.NavigationView | None = None

    @property
    def search_keywords(self):
        return [
            (_("About"), _("Operating System")), (_("About"), _("Hostname")),
            (_("About"), _("Processor")), (_("About"), _("Memory")), (_("About"), _("Disk")),
            (_("About"), _("Desktop")), (_("About"), _("Graphics")), (_("About"), _("GPU")),
            (_("About"), _("Updates")),
            (_("About"), _("Restore Defaults")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        self.add(self._build_about_group())
        self.add(self._build_updates_group())
        self.add(self._build_troubleshooting_group())

        # Tear down event-bus subscriptions on unmap. Call on self
        # (the PreferencesPage), not on the nav wrapper, so this fires
        # the same way it does on wave-1 pages.
        self.setup_cleanup(self)

        # Wrap the preferences page in a NavigationView so Restore
        # Defaults can push a sub-page. The back button + Escape are
        # handled natively by AdwNavigationView.
        self._nav = Adw.NavigationView()
        root_page = Adw.NavigationPage()
        root_page.set_title(_("About"))
        root_page.set_child(self)
        self._nav.add(root_page)
        return self._nav

    # -- About group ----------------------------------------------------

    def _build_about_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("About"))

        os_name = "Adwaita-Lite"
        os_version = ""
        try:
            for line in Path("/etc/os-release").read_text().splitlines():
                if line.startswith("VERSION_ID="):
                    os_version = line.split("=", 1)[1].strip('"')
        except OSError:
            pass

        # CPU model: x86 exposes "model name" in /proc/cpuinfo; ARM
        # uses "Model" / "Hardware" / "CPU implementer" instead. A
        # meaningful subset of our 2 GB Chromebook targets are ARM
        # (Mediatek MT8173/MT8183, Rockchip RK3399), so fall back to
        # the ARM fields when "model name" is absent.
        cpu = _("Unknown")
        try:
            cpuinfo = Path("/proc/cpuinfo").read_text().splitlines()
            for line in cpuinfo:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
            if cpu == _("Unknown"):
                for key in ("Model", "Hardware", "CPU part"):
                    for line in cpuinfo:
                        if line.startswith(key):
                            cpu = line.split(":", 1)[1].strip()
                            break
                    if cpu != _("Unknown"):
                        break
        except OSError:
            pass

        ram = _("Unknown")
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    ram = f"{int(line.split()[1]) / 1048576:.1f} GB"
                    break
        except (OSError, ValueError):
            pass

        disk_value: str | None = None
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            used = (st.f_blocks - st.f_bfree) * st.f_frsize
            disk_value = _("{used:.1f} GB used of {total:.1f} GB").format(
                used=used / 1073741824, total=total / 1073741824,
            )
        except OSError:
            pass

        gpu = _("Unknown")
        try:
            r = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5)
            for line in r.stdout.splitlines():
                if "VGA" in line or "3D" in line or "Display" in line:
                    gpu = line.split(": ", 1)[-1] if ": " in line else line
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        labwc_ver = "unknown"
        try:
            r = subprocess.run(["labwc", "--version"], capture_output=True, text=True, timeout=5)
            labwc_ver = (r.stderr.strip() or r.stdout.strip()) or "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        # Order matches the pre-migration layout: OS, hostname, CPU,
        # RAM, Disk (if available), GPU, labwc.
        group.add(self._make_property_row(
            _("Operating System"), f"{os_name} {os_version}".strip()))
        group.add(self._make_property_row(_("Hostname"), socket.gethostname()))
        group.add(self._make_property_row(_("Processor"), cpu))
        group.add(self._make_property_row(_("Memory"), ram))
        if disk_value is not None:
            group.add(self._make_property_row(_("Disk"), disk_value))
        group.add(self._make_property_row(_("Graphics"), gpu))
        group.add(self._make_property_row(_("Desktop"), f"labwc {labwc_ver}"))
        return group

    @staticmethod
    def _make_property_row(title: str, value: str) -> Adw.ActionRow:
        """Build an AdwActionRow styled as a property row.

        The `.property` style class emphasises the subtitle (value)
        over the title (label), which is the libadwaita idiom for
        system-info rows. The subtitle is marked selectable so users
        can copy version strings, hostnames, etc. out of the UI.
        """
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(value)
        row.set_subtitle_selectable(True)
        row.add_css_class("property")
        return row

    # -- Updates group --------------------------------------------------

    def _build_updates_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Updates"))

        row = Adw.ActionRow()
        row.set_title(_("Status"))
        row.set_subtitle(_("Click to check for updates"))
        # Subtitle is updated from _check_updates on the main loop.
        self._update_label = row

        check_btn = Gtk.Button(label=_("Check for Updates"))
        check_btn.set_valign(Gtk.Align.CENTER)
        check_btn.connect("clicked", lambda _b: self._check_updates())
        row.add_suffix(check_btn)

        update_btn = Gtk.Button(label=_("Update now..."))
        update_btn.add_css_class("suggested-action")
        update_btn.set_valign(Gtk.Align.CENTER)
        update_btn.set_visible(False)
        update_btn.connect("clicked", lambda _b: self._run_update())
        row.add_suffix(update_btn)
        self._update_btn = update_btn

        group.add(row)
        return group

    # -- Troubleshooting group -----------------------------------------

    def _build_troubleshooting_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Troubleshooting"))

        row = Adw.ActionRow()
        row.set_title(_("Restore Defaults"))
        row.set_subtitle(_("Reset settings to factory defaults"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", self._push_restore_defaults)
        group.add(row)
        return group

    # -- Updates flow ---------------------------------------------------

    def _check_updates(self):
        """Run ``uupd update-check`` on a worker thread.

        Exit codes: 77 = update available, 0 = up to date. Any other
        exit code is surfaced as a generic "could not check" status.
        The subtitle of the Updates row is driven from the main loop
        via GLib.idle_add so we never touch widgets from the thread.
        """
        if self._update_label is not None:
            self._update_label.set_subtitle(_("Checking..."))

        def _check():
            try:
                r = subprocess.run(
                    ["uupd", "update-check"],
                    capture_output=True, text=True, timeout=60,
                )
            except subprocess.TimeoutExpired:
                GLib.idle_add(self._set_update_subtitle, _("Update check timed out"))
                return
            except FileNotFoundError:
                GLib.idle_add(self._set_update_subtitle, _("Update system not available"))
                return
            except OSError:
                GLib.idle_add(self._set_update_subtitle, _("Update check failed"))
                return
            if r.returncode == 77:
                GLib.idle_add(self._set_update_subtitle, _("Update available"))
                GLib.idle_add(self._set_update_button_visible, True)
            elif r.returncode == 0:
                GLib.idle_add(self._set_update_subtitle, _("System is up to date"))
                GLib.idle_add(self._set_update_button_visible, False)
            else:
                GLib.idle_add(self._set_update_subtitle, _("Could not check for updates"))

        threading.Thread(target=_check, daemon=True).start()

    def _set_update_subtitle(self, text: str) -> bool:
        if self._update_label is not None:
            self._update_label.set_subtitle(text)
        return False

    def _set_update_button_visible(self, visible: bool) -> bool:
        if self._update_btn is not None:
            self._update_btn.set_visible(visible)
        return False

    def _run_update(self) -> None:
        # Spawn a foot terminal so the user sees the ujust update
        # progress and can respond to the sudo prompt. start_new_session
        # detaches from the settings app's process group so the terminal
        # (and its ujust child) survives if the user closes Settings
        # mid-update -- critical because ujust is rewriting the bootc
        # image and interrupting it can leave the system in a partial
        # state.
        try:
            subprocess.Popen(
                ["foot", "-e", "ujust", "update"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            self.store.show_toast(_("Terminal not available"), True)

    # -- Restore Defaults sub-page -------------------------------------

    def _push_restore_defaults(self, *_args) -> None:
        """Push an AdwNavigationPage containing the category picker.

        Replaces the former restore-defaults Gtk.Window. The
        category checkboxes become AdwSwitchRows and the Select All
        toggle becomes a SwitchRow in a header-suffix position so the
        `notify::active` guard still matches the old handler_block
        pattern. Reset button is a destructive-action suffix on a
        trailing row.
        """
        if self._nav is None:
            return

        sub = Adw.NavigationPage()
        sub.set_title(_("Restore Defaults"))

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()  # automatic back button in collapsed mode
        header.set_decoration_layout(":minimize,maximize,close")
        toolbar.add_top_bar(header)

        inner = Adw.PreferencesPage()

        # Description group: no rows, just the intro copy.
        intro_group = Adw.PreferencesGroup()
        intro_group.set_description(
            _("Select which settings to reset to factory defaults.")
        )
        inner.add(intro_group)

        # Categories group with a Select All toggle in the header
        # suffix and one AdwSwitchRow per CATEGORY_KEYS entry.
        cat_group = Adw.PreferencesGroup()
        cat_group.set_title(_("Categories"))

        select_all = Adw.SwitchRow()
        select_all.set_title(_("Select All"))
        select_all.set_active(False)

        checks: list[tuple[str, Adw.SwitchRow]] = []

        def _on_category_toggled(_row: Adw.SwitchRow, _pspec) -> None:
            any_checked = any(c.get_active() for _, c in checks)
            all_checked = all(c.get_active() for _, c in checks)
            reset_btn.set_sensitive(any_checked)
            # Update Select All without re-triggering its handler.
            select_all.handler_block_by_func(_on_select_all_toggled)
            select_all.set_active(all_checked)
            select_all.handler_unblock_by_func(_on_select_all_toggled)

        def _on_select_all_toggled(row: Adw.SwitchRow, _pspec) -> None:
            active = row.get_active()
            for _name, check in checks:
                # Block the per-row handler while flipping en masse so
                # we don't fire _on_category_toggled once per child.
                check.handler_block_by_func(_on_category_toggled)
                check.set_active(active)
                check.handler_unblock_by_func(_on_category_toggled)
            reset_btn.set_sensitive(active)

        select_all.connect("notify::active", _on_select_all_toggled)
        cat_group.set_header_suffix(select_all)

        for category in CATEGORY_KEYS:
            check = Adw.SwitchRow()
            check.set_title(_row_title_text(_(category)))
            check.set_active(False)
            check.connect("notify::active", _on_category_toggled)
            cat_group.add(check)
            checks.append((category, check))

        inner.add(cat_group)

        # Action group with the Reset button as a destructive suffix.
        action_group = Adw.PreferencesGroup()
        reset_row = Adw.ActionRow()
        reset_btn = Gtk.Button(label=_("Reset"))
        reset_btn.add_css_class("destructive-action")
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.set_sensitive(False)
        reset_btn.connect(
            "clicked",
            lambda _b: self._on_reset_clicked(checks),
        )
        reset_row.add_suffix(reset_btn)
        action_group.add(reset_row)
        inner.add(action_group)

        toolbar.set_content(inner)
        sub.set_child(toolbar)
        self._nav.push(sub)

    def _on_reset_clicked(
        self, checks: list[tuple[str, Adw.SwitchRow]]
    ) -> None:
        """Apply the selected category resets and restart the app.

        JSON state is written first. Out-of-band files such as custom
        wallpaper manifests and keybinding overrides are deleted only
        after that write succeeds, then a single apply/restart refreshes
        pages from disk and OS state.
        """
        selected = [cat for cat, check in checks if check.get_active()]
        if not selected:
            return

        # Load defaults from the image (updated via bootc)
        defaults = self.store.get_defaults()
        if not defaults:
            self.store.show_toast(_("Could not read defaults file"), True)
            if self._nav is not None:
                self._nav.pop()
            return

        # Collect all keys from selected categories.
        keys = []
        for category in selected:
            keys.extend(CATEGORY_KEYS.get(category, []))

        remove_predicate = (
            (lambda k: k.startswith("resolution_"))
            if "Display" in selected else None
        )
        if not self.store.restore_keys(
            keys, defaults, remove_predicate=remove_predicate, apply_now=False,
        ):
            return

        # Out-of-band state that lives outside settings.json is cleared
        # only after the JSON reset has safely reached disk. That avoids
        # deleting user files while settings.json still points at them if
        # the atomic write fails.
        config_dir = Path.home() / ".config/adwaita-lite"
        if "Keyboard" in selected:
            try:
                (config_dir / "keybindings.json").unlink(missing_ok=True)
            except OSError:
                self.store.show_toast(_("Could not reset keyboard shortcuts"), True)
        if "Appearance" in selected:
            from ..wallpapers import list_wallpapers, remove_custom
            for wp in list_wallpapers():
                if wp.is_custom and not remove_custom(wp.id):
                    self.store.show_toast(_("Could not remove a custom wallpaper"), True)
        if "Date & Time" in selected:
            # Reset clock to 24-hour default (handled via restore_keys)
            # and attempt to re-enable NTP + reset timezone.
            self._restore_datetime_defaults()
        if "Language & Region" in selected:
            self._restore_language_defaults()

        # Apply after out-of-band cleanup so labwc reads the reset
        # keybindings/wallpaper state on the first reconciliation pass.
        self.store.apply()

        # Pop the sub-page before restarting so GTK finishes unmapping
        # it cleanly.
        if self._nav is not None:
            self._nav.pop()

        # Wait for apply-settings to finish (or 10s fallback) and then
        # re-exec so every page re-reads values from disk/OS state.
        # restarted[0] guard avoids a double-exec when both
        # wait_for_apply and the timeout fire.
        restarted = [False]

        def _do_restart():
            if restarted[0]:
                return GLib.SOURCE_REMOVE
            restarted[0] = True
            GLib.idle_add(lambda: os.execv(sys.executable, [sys.executable] + sys.argv))
            return GLib.SOURCE_REMOVE

        self.store.wait_for_apply(_do_restart)
        GLib.timeout_add_seconds(10, _do_restart)

    def _restore_datetime_defaults(self):
        """Reset timezone to UTC and re-enable NTP via timedatectl.

        Uses a background thread so polkit prompts don't block the
        restart flow. Best-effort: failures are logged via show_toast
        but don't abort the rest of the reset.
        """
        import threading

        def _worker():
            for argv in (
                ["timedatectl", "set-ntp", "true"],
                ["timedatectl", "set-timezone", "UTC"],
            ):
                try:
                    subprocess.run(argv, capture_output=True, timeout=60)
                except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def _restore_language_defaults(self):
        """Reset system locale to en_US.UTF-8 via localectl.

        Same best-effort pattern as _restore_datetime_defaults.
        """
        import threading

        def _worker():
            try:
                subprocess.run(
                    ["localectl", "set-locale",
                     "LANG=en_US.UTF-8",
                     "LC_TIME=en_US.UTF-8",
                     "LC_NUMERIC=en_US.UTF-8",
                     "LC_MONETARY=en_US.UTF-8"],
                    capture_output=True, timeout=60,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass

        threading.Thread(target=_worker, daemon=True).start()
