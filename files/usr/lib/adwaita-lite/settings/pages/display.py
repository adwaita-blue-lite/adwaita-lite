import re
import subprocess
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, Gtk

from ..base import BasePage

SCALE_OPTIONS = ["75%", "100%", "125%", "150%", "175%", "200%", "225%", "250%"]
SCALE_VALUES = [0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5]

SCHEDULE_LABELS = [_("Sunset to Sunrise"), _("Custom")]
SCHEDULE_VALUES = ["sunset-sunrise", "custom"]


class DisplayPage(BasePage, Adw.PreferencesPage):
    """Display settings: scale, resolution + refresh rate, night light, and
    an Advanced launcher for wdisplays.

    Scale and resolution changes go through a 15-second AdwAlertDialog
    revert flow: the new value is applied immediately (wlr-randr), then
    the dialog shows a live-updating countdown in its body; if the user
    doesn't click Keep before it hits 0s, we programmatically fire the
    Revert response and restore the prior value.
    """

    def __init__(self, store, event_bus):
        BasePage.__init__(self, store, event_bus)
        Adw.PreferencesPage.__init__(self)
        # Widgets and state we reach from outside build() (timers, dialog
        # responses, unmap cleanup). Initialised to None; populated in
        # build() / the revert-dialog flows.
        self._scale_row: Adw.ComboRow | None = None
        self._revert_timer_id: int | None = None
        self._revert_seconds: int = 15
        self._revert_dialog: Adw.AlertDialog | None = None
        self._revert_pending_scale: float | None = None
        self._revert_pending_old_scale: float | None = None
        self._res_revert_timer_id: int | None = None
        self._res_revert_seconds: int = 15
        self._res_revert_dialog: Adw.AlertDialog | None = None
        self._res_revert_pending: tuple[str, str] | None = None
        # Track last-confirmed resolution per output for proper revert
        # baseline (see _on_resolution_changed).
        self._current_res: dict[str, str] = {}

    @property
    def search_keywords(self):
        return [
            (_("Display Scale"), _("Scale")),
            (_("Display Scale"), _("Resolution")),
            (_("Resolution & Refresh Rate"), _("Resolution")),
            (_("Resolution & Refresh Rate"), _("Refresh")),
            (_("Night Light"), _("Night Light")),
            (_("Night Light"), _("Temperature")),
            (_("Night Light"), _("Blue light")),
        ]

    # -- build ----------------------------------------------------------

    def build(self):
        displays = self._get_displays()
        if not displays:
            status = Adw.StatusPage()
            status.set_icon_name("video-display-symbolic")
            status.set_title(_("No displays detected"))
            status.set_description(_("Connect a display and reopen Settings."))
            return status

        self.add(self._build_scale_group())
        self.add(self._build_resolution_group(displays))
        self.add(self._build_night_light_group())
        self.add(self._build_advanced_group())

        # Cancel any in-flight revert countdown if the page is unmapped
        # mid-dialog (user navigates away, window closes). Adw.AlertDialog
        # has force_close() for exactly this scenario.
        self.connect("unmap", lambda _w: self._cleanup_dialogs())

        # Tear down event-bus subscriptions on unmap.
        self.setup_cleanup(self)
        return self

    # -- group builders -------------------------------------------------

    def _build_scale_group(self) -> Adw.PreferencesGroup:
        row = Adw.ComboRow()
        row.set_title(_("Display scale"))
        row.set_model(Gtk.StringList.new(list(SCALE_OPTIONS)))

        current = self.store.get("scale", 1.0)
        try:
            current_f = float(current)
        except (TypeError, ValueError):
            current_f = 1.0
        row.set_selected(
            SCALE_VALUES.index(current_f) if current_f in SCALE_VALUES else 1
        )

        row.connect("notify::selected", self._on_scale_row_selected)
        self._scale_row = row

        group = Adw.PreferencesGroup()
        group.set_title(_("Display Scale"))
        group.add(row)
        return group

    def _build_resolution_group(self, displays) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Resolution & Refresh Rate"))

        # Expand-by-default only when a single display is present; with
        # multiple displays the user can pick the one they care about.
        single_display = len(displays) == 1

        for name, current, modes in displays:
            if not modes:
                continue

            expander = Adw.ExpanderRow()
            expander.set_use_markup(False)
            expander.set_title(name)
            expander.set_subtitle(_("Resolution and refresh rate"))
            expander.set_expanded(single_display)

            mode_row = Adw.ComboRow()
            mode_row.set_title(_("Mode"))
            mode_row.set_model(Gtk.StringList.new(list(modes)))
            if current and current in modes:
                mode_row.set_selected(modes.index(current))

            mode_row.connect(
                "notify::selected",
                self._on_resolution_changed, name, list(modes), current,
            )
            expander.add_row(mode_row)
            group.add(expander)

        return group

    def _build_night_light_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Night Light"))

        # Enable switch row.
        enable_row = Adw.SwitchRow()
        enable_row.set_title(_("Night Light"))
        enable_row.set_subtitle(_("Reduce blue light to help with sleep"))
        enable_row.set_active(self.store.get("night_light_enabled", False))
        enable_row.connect(
            "notify::active",
            lambda r, _p: self.store.save_and_apply(
                "night_light_enabled", r.get_active()),
        )
        group.add(enable_row)

        # Temperature slider as a suffix on an action row.
        temp_row = Adw.ActionRow()
        temp_row.set_title(_("Temperature"))
        temp_row.set_subtitle(_("3500K (warm) to 6500K (cool)"))

        temp_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 3500, 6500, 100,
        )
        temp_scale.set_value(self.store.get("night_light_temp", 4500))
        temp_scale.set_size_request(150, -1)
        temp_scale.set_hexpand(True)
        temp_scale.set_draw_value(True)
        temp_scale.set_valign(Gtk.Align.CENTER)
        temp_scale.set_format_value_func(lambda _s, v: f"{v:.0f}K")
        try:
            temp_scale.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Night Light temperature")]
            )
        except Exception:
            pass
        temp_scale.connect(
            "value-changed",
            lambda s: self.store.save_debounced(
                "night_light_temp", int(s.get_value())),
        )
        temp_row.add_suffix(temp_scale)
        group.add(temp_row)

        # Schedule combo.
        schedule_row = Adw.ComboRow()
        schedule_row.set_title(_("Schedule"))
        schedule_row.set_model(Gtk.StringList.new(list(SCHEDULE_LABELS)))

        current_schedule = self.store.get("night_light_schedule", "sunset-sunrise")
        try:
            schedule_row.set_selected(SCHEDULE_VALUES.index(current_schedule))
        except ValueError:
            schedule_row.set_selected(0)
        group.add(schedule_row)

        # Custom schedule expander — wraps the two HH:MM entry rows.
        custom_expander = Adw.ExpanderRow()
        custom_expander.set_title(_("Custom schedule"))
        custom_expander.set_subtitle(_("Times snap to 15-minute increments"))
        custom_expander.set_expanded(current_schedule == "custom")

        start_row = Adw.EntryRow()
        start_row.set_title(_("Start time"))
        start_row.set_text(self.store.get("night_light_start", "20:00"))
        start_row.set_show_apply_button(True)
        start_row.connect(
            "apply",
            lambda r: self._validate_and_save_time(r, "night_light_start"),
        )
        custom_expander.add_row(start_row)

        end_row = Adw.EntryRow()
        end_row.set_title(_("End time"))
        end_row.set_text(self.store.get("night_light_end", "06:00"))
        end_row.set_show_apply_button(True)
        end_row.connect(
            "apply",
            lambda r: self._validate_and_save_time(r, "night_light_end"),
        )
        custom_expander.add_row(end_row)

        group.add(custom_expander)

        # Schedule change toggles the custom expander's expanded state
        # AND saves. Split into one handler so both side-effects stay
        # in lockstep.
        def _on_schedule_selected(row: Adw.ComboRow, _pspec) -> None:
            idx = row.get_selected()
            if 0 <= idx < len(SCHEDULE_VALUES):
                value = SCHEDULE_VALUES[idx]
                self.store.save_and_apply("night_light_schedule", value)
                custom_expander.set_expanded(value == "custom")

        schedule_row.connect("notify::selected", _on_schedule_selected)

        return group

    def _build_advanced_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        group.set_title(_("Advanced"))

        row = Adw.ActionRow()
        row.set_title(_("Advanced display settings"))
        row.set_subtitle(_("Arrange and configure displays visually"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda _r: self._launch_wdisplays())
        group.add(row)
        return group

    # -- helpers --------------------------------------------------------

    def _launch_wdisplays(self) -> None:
        try:
            subprocess.Popen(
                ["wdisplays"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, OSError):
            # Sibling network.py page toasts "Connection editor not
            # found" for the same class of failure — matching here
            # gives the user a reason Advanced Display does nothing
            # instead of silently swallowing the click.
            self.store.show_toast(
                _("Advanced display tool not available"), True)

    def _validate_and_save_time(self, row: Adw.EntryRow, key: str) -> None:
        text = row.get_text().strip()
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if 0 <= h < 24 and 0 <= mm < 60:
                # Snap to the nearest quarter-hour so the schedule
                # boundaries line up with the 15-minute reconcile timer.
                rounded = round(mm / 15) * 15
                if rounded == 60:
                    h = (h + 1) % 24
                    rounded = 0
                canonical = f"{h:02d}:{rounded:02d}"
                if canonical != text:
                    row.set_text(canonical)
                row.remove_css_class("error")
                self.store.save_and_apply(key, canonical)
                return
        row.add_css_class("error")

    def _cleanup_dialogs(self) -> None:
        """Cancel any running countdown timers and dismiss live revert
        dialogs when the page is unmapped.

        Treats unmap as implicit *Keep*, not Revert. When the user
        navigates away mid-countdown, the scale/resolution is live in
        the compositor but not yet persisted to settings.json (that
        happens on explicit Keep). Previously we disconnected the
        response handler before force_close, so neither Keep nor
        Revert ran — next login's autostart reverted the choice.
        Now we call save_and_apply on the pending new value before
        dismissing, mirroring what the explicit Keep branch would do.
        """
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        if self._revert_dialog is not None:
            pending = getattr(self, "_revert_pending_scale", None)
            try:
                self._revert_dialog.disconnect_by_func(self._on_revert_response)
            except TypeError:
                pass
            self._revert_dialog.force_close()
            self._revert_dialog = None
            if pending is not None:
                self.store.save_and_apply("scale", pending)
                self._sync_scale_row_to(pending)
            self._revert_pending_scale = None
            self._revert_pending_old_scale = None
        if self._res_revert_timer_id is not None:
            GLib.source_remove(self._res_revert_timer_id)
            self._res_revert_timer_id = None
        if self._res_revert_dialog is not None:
            pending_res = getattr(self, "_res_revert_pending", None)
            try:
                self._res_revert_dialog.disconnect_by_func(self._on_res_revert_response)
            except TypeError:
                pass
            self._res_revert_dialog.force_close()
            self._res_revert_dialog = None
            if pending_res is not None:
                output_name, new_mode = pending_res
                self.store.save_and_apply(f"resolution_{output_name}", new_mode)
            self._res_revert_pending = None

    # ── Display Scale ──────────────────────────────────────────────────

    def _on_scale_row_selected(self, row: Adw.ComboRow, _pspec) -> None:
        idx = row.get_selected()
        if not (0 <= idx < len(SCALE_VALUES)):
            return
        new_scale = SCALE_VALUES[idx]
        old_scale_raw = self.store.get("scale", 1.0)
        try:
            old_scale = float(old_scale_raw)
        except (TypeError, ValueError):
            old_scale = 1.0
        if new_scale == old_scale:
            return
        self._apply_scale(new_scale)

    def _apply_scale(self, new_scale: float) -> None:
        # Cancel any in-flight revert before starting a new one: the user
        # just picked a third option mid-countdown.
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        if self._revert_dialog is not None:
            # Before force_close: the close-response ("revert") fires
            # synchronously against the original handler, which captures
            # the *first* pick's old/new scales and rolls the scale all
            # the way back before we apply the third pick. Net effect:
            # the display flickers through the pre-first-pick scale,
            # and the ComboRow briefly shows the pre-first-pick value.
            # Disconnect the response handler first; we're reopening a
            # fresh dialog with the correct captured values below.
            try:
                self._revert_dialog.disconnect_by_func(self._on_revert_response)
            except TypeError:
                pass
            self._revert_dialog.force_close()
            self._revert_dialog = None

        old_scale_raw = self.store.get("scale", 1.0)
        try:
            old_scale = float(old_scale_raw)
        except (TypeError, ValueError):
            old_scale = 1.0

        self._set_scale(new_scale)
        self._show_revert_dialog(old_scale, new_scale)

    def _set_scale(self, scale: float) -> None:
        # Use the shared output-enumeration helper instead of re-
        # parsing wlr-randr here. The previous inline parser trusted
        # line.split()[0] as an output name for any column-0 line,
        # which picked up noise like an "Outputs:" banner on some
        # wlr-randr versions and silently ran `--output Outputs
        # --scale <x>` (exit code ignored). scale changes then
        # appeared to succeed in settings.json while never actually
        # applying to the display.
        for name, _current, _modes in self._get_displays():
            if not name:
                continue
            try:
                result = subprocess.run(
                    ["wlr-randr", "--output", name, "--scale", str(scale)],
                    check=False, timeout=5, capture_output=True, text=True,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
            if result.returncode != 0:
                # Surface the failure so the user isn't left staring at
                # an unchanged display while the revert dialog counts
                # down against an apply that never happened.
                self.store.show_toast(
                    _("Failed to set display scale on {output}").format(output=name),
                    True,
                )

    def _show_revert_dialog(self, old_scale: float, new_scale: float) -> None:
        dialog = Adw.AlertDialog.new(
            _("Confirm display scale"),
            None,
        )
        dialog.add_response("revert", _("Revert"))
        dialog.add_response("keep", _("Keep"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("keep")
        dialog.set_close_response("revert")

        self._revert_dialog = dialog
        # Stash the pending values so _cleanup_dialogs can implicit-Keep
        # (persist to settings.json) when the user navigates away mid-
        # countdown. Without persistence, the compositor holds the new
        # scale for the session but the autostart at next login reads
        # the old value from settings.json and reverts.
        self._revert_pending_scale = new_scale
        self._revert_pending_old_scale = old_scale
        self._revert_seconds = 15
        dialog.set_body(
            _("Keep this display scale? Reverting in {seconds}s…").format(
                seconds=self._revert_seconds),
        )

        dialog.connect("response", self._on_revert_response,
                       old_scale, new_scale)

        parent = self._scale_row.get_root() if self._scale_row else self.get_root()
        dialog.present(parent)

        self._revert_timer_id = GLib.timeout_add_seconds(
            1, self._tick_revert, dialog,
        )

    def _tick_revert(self, dialog: Adw.AlertDialog) -> bool:
        self._revert_seconds -= 1
        if self._revert_seconds <= 0:
            # Clear the timer handle first — dialog.response() triggers
            # the response handler synchronously, which also attempts to
            # remove the timer. Returning SOURCE_REMOVE below is enough
            # for GLib but the handler's defensive source_remove would
            # be on a stale id.
            self._revert_timer_id = None
            dialog.response("revert")
            return GLib.SOURCE_REMOVE
        dialog.set_body(
            _("Keep this display scale? Reverting in {seconds}s…").format(
                seconds=self._revert_seconds),
        )
        return GLib.SOURCE_CONTINUE

    def _on_revert_response(
        self,
        _dialog: Adw.AlertDialog,
        response_id: str,
        old_scale: float,
        new_scale: float,
    ) -> None:
        if self._revert_timer_id is not None:
            GLib.source_remove(self._revert_timer_id)
            self._revert_timer_id = None
        self._revert_dialog = None
        self._revert_pending_scale = None
        self._revert_pending_old_scale = None

        if response_id == "keep":
            self.store.save_and_apply("scale", new_scale)
            self._sync_scale_row_to(new_scale)
        else:
            self._set_scale(old_scale)
            self._sync_scale_row_to(old_scale)

    def _sync_scale_row_to(self, scale: float) -> None:
        if self._scale_row is None:
            return
        try:
            target_idx = SCALE_VALUES.index(float(scale))
        except (ValueError, TypeError):
            return
        if self._scale_row.get_selected() != target_idx:
            # Block our own handler: changing the selected index here is
            # a sync operation, not a user choice, so it must not kick
            # off another revert countdown.
            self._scale_row.handler_block_by_func(self._on_scale_row_selected)
            try:
                self._scale_row.set_selected(target_idx)
            finally:
                self._scale_row.handler_unblock_by_func(self._on_scale_row_selected)

    # ── Resolution & Refresh Rate ──────────────────────────────────────

    @staticmethod
    def _get_displays():
        try:
            result = subprocess.run(
                ["wlr-randr"], capture_output=True, text=True, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return []
        displays = []
        name = None
        current = None
        modes = []
        for line in result.stdout.splitlines():
            if line and not line[0].isspace():
                if name:
                    displays.append((name, current, modes))
                name = line.split()[0]
                current = None
                modes = []
            else:
                m = re.search(r"(\d+x\d+)\s+px,\s+([\d.]+)\s+Hz", line)
                if m:
                    mode = f"{m.group(1)}@{m.group(2)}Hz"
                    if mode not in modes:
                        modes.append(mode)
                    if "current" in line.lower():
                        current = mode
        if name:
            displays.append((name, current, modes))
        return displays

    def _on_resolution_changed(
        self,
        row: Adw.ComboRow,
        _pspec,
        output_name: str,
        modes: list[str],
        old_mode: str | None,
    ) -> None:
        idx = row.get_selected()
        if idx < 0 or idx >= len(modes):
            return
        new_mode = modes[idx]
        # Track the user's last-confirmed mode per output so Revert
        # rolls back to THAT, not to the captured build-time mode.
        # Without this, after: pick 1920x1080, Keep, then pick 1280x720,
        # Revert — the revert baseline was still the original
        # build-time mode, not the 1920x1080 the user just confirmed.
        current_mode = self._current_res.get(output_name, old_mode)
        if new_mode == current_mode:
            return
        old_mode = current_mode
        # Cancel any in-flight resolution revert; starting a fresh one.
        if self._res_revert_timer_id is not None:
            GLib.source_remove(self._res_revert_timer_id)
            self._res_revert_timer_id = None
        if self._res_revert_dialog is not None:
            # Disconnect before force_close so the close-response's
            # "revert" branch doesn't roll back against captured old
            # values from the first pick — same pattern as _apply_scale.
            try:
                self._res_revert_dialog.disconnect_by_func(self._on_res_revert_response)
            except TypeError:
                pass
            self._res_revert_dialog.force_close()
            self._res_revert_dialog = None
        self._apply_resolution(output_name, new_mode)
        self._show_res_revert_dialog(row, output_name, modes, old_mode, new_mode)

    @staticmethod
    def _apply_resolution(output_name: str, mode_str: str) -> None:
        # mode_str: "1920x1080@60.0Hz" — strip "Hz" for wlr-randr's --mode flag
        mode_arg = mode_str.replace("Hz", "")
        try:
            subprocess.run(
                ["wlr-randr", "--output", output_name, "--mode", mode_arg],
                check=False, timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

    def _show_res_revert_dialog(
        self,
        mode_row: Adw.ComboRow,
        output_name: str,
        modes: list[str],
        old_mode: str | None,
        new_mode: str,
    ) -> None:
        dialog = Adw.AlertDialog.new(
            _("Confirm resolution"),
            None,
        )
        dialog.add_response("revert", _("Revert"))
        dialog.add_response("keep", _("Keep"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("keep")
        dialog.set_close_response("revert")

        self._res_revert_dialog = dialog
        # Stash so _cleanup_dialogs can implicit-Keep on unmap, same
        # reason as the scale case above.
        self._res_revert_pending = (output_name, new_mode)
        self._res_revert_seconds = 15
        dialog.set_body(
            _("Keep this resolution? Reverting in {seconds}s…").format(
                seconds=self._res_revert_seconds),
        )

        dialog.connect(
            "response", self._on_res_revert_response,
            mode_row, output_name, modes, old_mode, new_mode,
        )

        dialog.present(mode_row.get_root() or self.get_root())

        self._res_revert_timer_id = GLib.timeout_add_seconds(
            1, self._tick_res_revert, dialog,
        )

    def _tick_res_revert(self, dialog: Adw.AlertDialog) -> bool:
        self._res_revert_seconds -= 1
        if self._res_revert_seconds <= 0:
            self._res_revert_timer_id = None
            dialog.response("revert")
            return GLib.SOURCE_REMOVE
        dialog.set_body(
            _("Keep this resolution? Reverting in {seconds}s…").format(
                seconds=self._res_revert_seconds),
        )
        return GLib.SOURCE_CONTINUE

    def _on_res_revert_response(
        self,
        _dialog: Adw.AlertDialog,
        response_id: str,
        mode_row: Adw.ComboRow,
        output_name: str,
        modes: list[str],
        old_mode: str | None,
        new_mode: str,
    ) -> None:
        if self._res_revert_timer_id is not None:
            GLib.source_remove(self._res_revert_timer_id)
            self._res_revert_timer_id = None
        self._res_revert_dialog = None
        self._res_revert_pending = None

        if response_id == "keep":
            self.store.save_and_apply(f"resolution_{output_name}", new_mode)
            # Update the per-output baseline so the next revert rolls
            # back to THIS mode, not the build-time captured one.
            self._current_res[output_name] = new_mode
        else:
            self._apply_resolution(output_name, old_mode or new_mode)
            if old_mode and old_mode in modes:
                # Block to avoid re-triggering _on_resolution_changed.
                mode_row.handler_block_by_func(self._on_resolution_changed)
                try:
                    mode_row.set_selected(modes.index(old_mode))
                finally:
                    mode_row.handler_unblock_by_func(self._on_resolution_changed)
