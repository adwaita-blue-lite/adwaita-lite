import subprocess
import sys
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
gi.require_version("Gtk", "4.0")
from gi.repository import Adw, GLib, GObject, Gio, Gtk

from .events import EventBus
from .settings_store import SettingsStore


class SettingsWindow(Adw.ApplicationWindow):
    """Top-level settings window.

    Structure:
        AdwApplicationWindow
        └── AdwToastOverlay
            └── AdwNavigationSplitView
                ├── sidebar: AdwNavigationPage(title="Settings")
                │   └── AdwToolbarView
                │       ├── top: AdwHeaderBar
                │       └── content: ScrolledWindow > ListBox
                └── content: AdwNavigationPage(title=<current page>)
                    └── AdwToolbarView
                        ├── top: AdwHeaderBar (back-button appears
                        │         automatically in collapsed mode)
                        ├── top: GtkSearchBar
                        └── content: GtkStack

    An AdwBreakpoint watching the window's max-width flips the split
    view to collapsed mode. In that mode AdwNavigationSplitView uses
    push/pop navigation instead of an overlay drawer - picking a
    category slides in the content page on top of the sidebar, and a
    back button in the content's header pops back. Matches GNOME
    Settings' exact pattern.
    """

    # Below this window width the sidebar collapses into a drawer.
    # `sp` (scalable pixels) respects the Large Text accessibility
    # setting, so users with a bumped font size get the collapse
    # earlier, when they actually need the extra room.
    _COLLAPSE_WIDTH = "max-width: 700sp"

    def __init__(self, app: Adw.Application, store: SettingsStore,
                 event_bus: EventBus) -> None:
        super().__init__(application=app)
        self.set_title(_("Settings"))
        self.set_default_size(900, 600)
        # Minimum window size lets the breakpoint actually fire. Without
        # it the window refuses to shrink below the widest page's natural
        # width, defeating the collapse.
        self.set_size_request(360, 300)

        self._store = store
        self._event_bus = event_bus
        self._page_names: list[str] = []
        self._page_labels: list[str] = []
        self._pages: list = []
        self._built: set[str] = set()

        # -- Sidebar page (category list) -----------------------------
        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_vexpand(True)
        self._sidebar = Gtk.ListBox()
        self._sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        # Adwaita's standard class for a sidebar-style ListBox - gives
        # rows the right navigation look, hover, and selected colours.
        self._sidebar.add_css_class("navigation-sidebar")
        sidebar_scroll.set_child(self._sidebar)

        sidebar_toolbar = Adw.ToolbarView()
        sidebar_header = Adw.HeaderBar()
        sidebar_header.set_decoration_layout(":minimize,maximize,close")
        sidebar_toolbar.add_top_bar(sidebar_header)
        sidebar_toolbar.set_content(sidebar_scroll)

        sidebar_page = Adw.NavigationPage.new(sidebar_toolbar, _("Settings"))

        # -- Content page (stack of setting pages) -------------------
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._stack.set_transition_duration(150)

        content_header = Adw.HeaderBar()
        content_header.set_decoration_layout(":minimize,maximize,close")

        search_btn = Gtk.ToggleButton()
        search_btn.set_icon_name("system-search-symbolic")
        search_btn.set_tooltip_text(_("Search settings"))
        content_header.pack_end(search_btn)

        self._search_entry = Gtk.SearchEntry()
        self._search_entry.set_placeholder_text(_("Search settings\u2026"))
        self._search_entry.add_css_class("settings-search-entry")
        self._search_bar = Gtk.SearchBar()
        self._search_bar.set_child(self._search_entry)
        self._search_bar.connect_entry(self._search_entry)
        self._search_entry.connect("search-changed", self._on_search_changed)
        search_btn.bind_property(
            "active", self._search_bar, "search-mode-enabled",
            GObject.BindingFlags.BIDIRECTIONAL | GObject.BindingFlags.SYNC_CREATE,
        )

        content_toolbar = Adw.ToolbarView()
        content_toolbar.add_top_bar(content_header)
        content_toolbar.add_top_bar(self._search_bar)
        self._deferred_restart_banner = Adw.Banner()
        self._deferred_restart_banner.set_title(
            _("Restart your session to apply panel and start menu changes.")
        )
        self._deferred_restart_banner.set_button_label(_("Restart Session"))
        self._deferred_restart_banner.connect("button-clicked", self._on_restart_session_clicked)
        self._deferred_restart_banner.set_revealed(
            store.has_deferred_session_changes()
        )
        content_toolbar.add_top_bar(self._deferred_restart_banner)
        content_toolbar.set_content(self._stack)

        # Content page's title is updated in _on_row_selected so it
        # reflects the active category in the header (visible in
        # collapsed mode beside the back button).
        self._content_page = Adw.NavigationPage.new(content_toolbar,
                                                    _("Settings"))

        # -- NavigationSplitView -------------------------------------
        split = Adw.NavigationSplitView()
        split.set_sidebar(sidebar_page)
        split.set_content(self._content_page)
        split.set_sidebar_width_fraction(0.25)
        split.set_min_sidebar_width(200.0)
        split.set_max_sidebar_width(280.0)
        self._split_view = split

        # -- ToastOverlay wraps the split ----------------------------
        # Replaces our old custom Revealer-based ToastWidget. Handles
        # dismiss, stacking of concurrent toasts, and keyboard
        # accessibility correctly out of the box.
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(split)
        self.set_content(self._toast_overlay)
        store.set_toast_callback(self._show_toast)
        store.set_deferred_changes_callback(self._set_deferred_restart_banner_revealed)

        # -- Breakpoint: collapse below _COLLAPSE_WIDTH --------------
        # When collapsed, NavigationSplitView uses push/pop between
        # sidebar and content (with an automatic back button in the
        # content's header). Reverts when the window widens again.
        breakpoint_ = Adw.Breakpoint.new(
            Adw.BreakpointCondition.parse(self._COLLAPSE_WIDTH)
        )
        breakpoint_.add_setter(split, "collapsed", True)
        self.add_breakpoint(breakpoint_)

        # -- Pages + initial selection -------------------------------
        self._build_pages()
        self._sidebar.connect("row-selected", self._on_row_selected)
        first = self._sidebar.get_row_at_index(0)
        if first is not None:
            self._sidebar.select_row(first)

        # -- Actions -------------------------------------------------
        search_action = Gio.SimpleAction.new("search", None)
        search_action.connect("activate", lambda *_: self.toggle_search())
        self.add_action(search_action)

        # -- Teardown coordination -----------------------------------
        # Cancel any in-flight debounces and detach the toast callback
        # before the window's overlay is freed. Without this, a setting
        # changed within ~300 ms of hitting Close would fire its
        # debounced apply after close-request returns, and the apply's
        # completion handler would invoke our now-dead _show_toast on a
        # disposed Adw.ToastOverlay. Returning False lets the default
        # handler proceed with the close.
        self.connect("close-request", self._on_close_request)

    def _on_close_request(self, _window) -> bool:
        self._store.set_deferred_changes_callback(None)
        self._store.flush_and_detach()
        if self._store.has_apply_work():
            app = self.get_application()
            if app is not None:
                app.hold()

                def _release_app() -> None:
                    app.release()

                self._store.wait_for_apply(_release_app)
        return False

    # -- Toast -------------------------------------------------------

    def _show_toast(self, message: str, is_error: bool = False,
                    timeout: int = 3) -> None:
        """Display an Adw.Toast. Matches the old ToastWidget.show_toast API.

        Errors use red Pango markup in place of the old .toast-error
        CSS class - Adw.Toast doesn't expose a per-toast style class,
        but it does honour markup in its title, which is enough to
        distinguish a failure notice from a neutral one.
        """
        toast = Adw.Toast()
        if is_error:
            escaped = GLib.markup_escape_text(message)
            toast.set_use_markup(True)
            toast.set_title(f'<span foreground="#e01b24">{escaped}</span>')
            # Higher priority keeps error toasts visible when another
            # toast arrives before the user has read them.
            toast.set_priority(Adw.ToastPriority.HIGH)
        else:
            toast.set_title(message)
        toast.set_timeout(max(1, int(timeout)))
        self._toast_overlay.add_toast(toast)

    # -- Deferred Restart --------------------------------------------

    def _set_deferred_restart_banner_revealed(self, revealed: bool) -> None:
        self._deferred_restart_banner.set_revealed(revealed)

    def _on_restart_session_clicked(self, _banner: Adw.Banner) -> None:
        dialog = Adw.AlertDialog.new(
            _("Restart Session?"),
            _("This will close your apps and return you to the sign-in screen."),
        )
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("restart", _("Restart Session"))
        dialog.set_response_appearance("restart", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_restart_session_response)
        dialog.present(self)

    def _on_restart_session_response(
        self, _dialog: Adw.AlertDialog, response: str
    ) -> None:
        if response != "restart":
            return
        try:
            subprocess.Popen(
                ["labwc", "--exit"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            self._show_toast(
                _("Could not restart session: {detail}").format(detail=exc),
                is_error=True,
            )

    # -- Page building -----------------------------------------------

    def _build_pages(self) -> None:
        from .pages import ALL_PAGES

        for icon_name, label, page_cls in ALL_PAGES:
            try:
                page = page_cls(self._store, self._event_bus)
            except Exception as exc:
                print(f"Settings: failed to instantiate {label!r}: {exc!r}",
                      file=sys.stderr)
                page = None

            translated = _(label)
            row = self._build_sidebar_row(icon_name, translated)
            self._sidebar.append(row)
            self._page_names.append(label)
            self._page_labels.append(translated)
            self._pages.append(page)

    def _ensure_page_built(self, idx: int) -> None:
        """Build the page's widgets the first time it's shown."""
        label = self._page_names[idx]
        if label in self._built:
            return
        self._built.add(label)
        page = self._pages[idx]
        try:
            widget = page.build() if page is not None else None
        except Exception as exc:
            print(f"Settings: failed to build {label!r}: {exc!r}",
                  file=sys.stderr)
            if page is not None:
                try:
                    page.unsubscribe_all()
                except Exception as cleanup_exc:
                    print(
                        f"Settings: failed to clean up {label!r}: {cleanup_exc!r}",
                        file=sys.stderr,
                    )
            widget = None
        if widget is None:
            widget = Gtk.Label(
                label=_("Failed to load {label}").format(label=label),
                xalign=0,
            )
        self._stack.add_named(widget, label)

    @staticmethod
    def _build_sidebar_row(icon_name: str, label: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(16)
        box.append(icon)
        lbl = Gtk.Label(label=label, xalign=0)
        lbl.set_hexpand(True)
        box.append(lbl)
        row.set_child(box)
        return row

    # -- Navigation --------------------------------------------------

    def _on_row_selected(self, _listbox: Gtk.ListBox,
                         row: Gtk.ListBoxRow) -> None:
        if row is None:
            return
        idx = row.get_index()
        if not (0 <= idx < len(self._page_names)):
            return
        label = self._page_names[idx]
        # Build on demand. First selection at startup is deferred one
        # tick via GLib.idle_add so the window paints before we start
        # decoding wallpaper thumbnails or opening D-Bus connections.
        if label not in self._built:
            def _build_then_show() -> int:
                self._ensure_page_built(idx)
                self._show_page(idx, label)
                return GLib.SOURCE_REMOVE
            GLib.idle_add(_build_then_show)
            return
        self._show_page(idx, label)

    def _show_page(self, idx: int, label: str) -> None:
        self._stack.set_visible_child_name(label)
        self._content_page.set_title(self._page_labels[idx])
        # Push to the content page in collapsed mode. When not
        # collapsed this is a no-op (both panes are always visible).
        self._split_view.set_show_content(True)

    # -- Search ------------------------------------------------------

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text().lower().strip()
        if not text:
            self._sidebar.set_filter_func(None)
            return

        matching: set[int] = set()
        for i, page in enumerate(self._pages):
            if page is None:
                continue
            for group, setting in page.search_keywords:
                if text in group.lower() or text in setting.lower():
                    matching.add(i)
                    break

        self._sidebar.set_filter_func(lambda row: row.get_index() in matching)

    def toggle_search(self) -> None:
        active = self._search_bar.get_search_mode()
        self._search_bar.set_search_mode(not active)
        if not active:
            self._search_entry.grab_focus()
