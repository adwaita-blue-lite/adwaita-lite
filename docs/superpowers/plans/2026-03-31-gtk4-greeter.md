# GTK4 Greeter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace gtkgreet (GTK3) with a custom GTK4 Python greeter that integrates with the Adwaita theme system and provides a ChromeOS-inspired single-user login experience.

**Architecture:** Single Python/GTK4 script communicating with greetd via its IPC protocol (length-prefixed JSON over `$GREETD_SOCK`). Inline CSS generated from Adwaita palette. Runs inside cage (Wayland kiosk) launched by greetd. Stores last username for single-user fast login.

**Tech Stack:** Python 3, GTK4 (via PyGObject), greetd IPC, cage (Wayland compositor)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `files/usr/bin/adwaita-lite-greeter` | Create | The GTK4 greeter (~500 lines) |
| `files/usr/libexec/adwaita-lite-greeter-setup` | Modify | Point at new greeter instead of gtkgreet |
| `build_files/build.sh` | Modify | Remove gtkgreet package, add chmod for new greeter |
| `files/etc/greetd/gtkgreet.css` | Delete | No longer needed — CSS is inline |

---

### Task 1: Create the greeter — IPC + theme + CSS foundation

**Files:**
- Create: `files/usr/bin/adwaita-lite-greeter`

This task creates the complete greeter file. It's one file, and splitting it across tasks would create non-functional intermediate states.

- [ ] **Step 1: Create the greeter script**

Write the full file to `files/usr/bin/adwaita-lite-greeter`:

```python
#!/usr/bin/env python3
"""Adwaita-Lite login greeter for greetd.

GTK4 greeter communicating with greetd via its IPC protocol.
Runs inside cage (Wayland kiosk compositor) launched by greetd.

Visual design: Adwaita palette, ChromeOS-inspired layout —
prominent clock, centered login card, single-user optimised.
"""

import configparser
import json
import os
import socket
import struct
import sys
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402

APP_ID = "org.adwaitabluelite.Greeter"

LAST_USER_PATH = Path("/var/lib/adwaita-lite/last-user")
GREETER_CONFIG_PATH = Path("/etc/adwaita-lite/greeter.json")
SESSIONS_DIR = Path("/usr/share/wayland-sessions")

# ---------------------------------------------------------------------------
#  Adwaita palettes (identical to apply-settings)
# ---------------------------------------------------------------------------

PALETTES = {
    "light": {
        "window_bg": "#fafafa",
        "card_bg": "#ffffff",
        "fg": "#1e1e1e",
        "secondary_fg": "#5e5c64",
        "border": "#d1d1d1",
        "entry_bg": "#ffffff",
        "accent": "#3584e4",
        "accent_hover": "#62a0ea",
        "accent_active": "#1c71d8",
        "error": "#e62d42",
        "hover": "rgba(0, 0, 0, 0.04)",
    },
    "dark": {
        "window_bg": "#242424",
        "card_bg": "#383838",
        "fg": "#ffffff",
        "secondary_fg": "#c0bfbc",
        "border": "#4a4a4a",
        "entry_bg": "#2e2e2e",
        "accent": "#3584e4",
        "accent_hover": "#62a0ea",
        "accent_active": "#1c71d8",
        "error": "#ff6b6b",
        "hover": "rgba(255, 255, 255, 0.06)",
    },
}


def _load_theme() -> str:
    """Read theme from greeter config. Default to light."""
    try:
        data = json.loads(GREETER_CONFIG_PATH.read_text(encoding="utf-8"))
        theme = data.get("theme", "light")
        if theme in PALETTES:
            return theme
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return "light"


def _build_css(p: dict) -> str:
    """Generate GTK4 CSS from a palette dict."""
    return f"""\
window {{
    background-color: {p["window_bg"]};
}}

.clock {{
    font-family: "Roboto", sans-serif;
    font-size: 48px;
    font-weight: 300;
    color: {p["fg"]};
}}

.date {{
    font-family: "Roboto", sans-serif;
    font-size: 16px;
    color: {p["secondary_fg"]};
    margin-bottom: 32px;
}}

.card {{
    background-color: {p["card_bg"]};
    border-radius: 16px;
    padding: 40px 36px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08),
                0 0 0 1px rgba(0, 0, 0, 0.06);
}}

.greeting {{
    font-family: "Roboto", sans-serif;
    font-size: 20px;
    font-weight: 500;
    color: {p["fg"]};
    margin-bottom: 20px;
}}

.form-entry {{
    font-family: "Roboto", sans-serif;
    font-size: 15px;
    padding: 10px 14px;
    border-radius: 8px;
    background-color: {p["entry_bg"]};
    color: {p["fg"]};
    border: 1px solid {p["border"]};
    min-height: 22px;
}}

.form-entry:focus {{
    border-color: {p["accent"]};
    box-shadow: 0 0 0 2px rgba(53, 132, 228, 0.25);
}}

.error-label {{
    font-family: "Roboto", sans-serif;
    font-size: 13px;
    color: {p["error"]};
    margin-top: 8px;
    margin-bottom: 4px;
}}

.login-button {{
    font-family: "Roboto", sans-serif;
    font-size: 15px;
    font-weight: 700;
    padding: 10px 32px;
    border-radius: 999px;
    background: {p["accent"]};
    color: #ffffff;
    border: none;
    min-height: 22px;
}}

.login-button:hover {{ background: {p["accent_hover"]}; }}
.login-button:active {{ background: {p["accent_active"]}; }}

.switch-user {{
    font-family: "Roboto", sans-serif;
    font-size: 13px;
    color: {p["secondary_fg"]};
    background: none;
    border: none;
    margin-top: 12px;
    padding: 4px 8px;
}}

.switch-user:hover {{
    color: {p["accent"]};
}}

.gear-button {{
    background: none;
    border: none;
    color: {p["secondary_fg"]};
    padding: 4px;
    border-radius: 999px;
    min-width: 24px;
    min-height: 24px;
}}

.gear-button:hover {{
    background: {p["hover"]};
}}

.session-dropdown {{
    font-family: "Roboto", sans-serif;
    font-size: 13px;
    color: {p["secondary_fg"]};
}}

.session-dropdown button {{
    background: none;
    border: 1px solid {p["border"]};
    border-radius: 8px;
    padding: 6px 12px;
    color: {p["secondary_fg"]};
    font-size: 13px;
    min-height: 16px;
}}

.session-dropdown button:hover {{
    background: {p["hover"]};
}}
"""


# ---------------------------------------------------------------------------
#  greetd IPC
# ---------------------------------------------------------------------------

class GreetdClient:
    """Synchronous greetd IPC client."""

    def __init__(self) -> None:
        sock_path = os.environ.get("GREETD_SOCK")
        if not sock_path:
            raise RuntimeError("GREETD_SOCK not set")
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(sock_path)

    def _send(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        self._sock.sendall(struct.pack("<I", len(data)) + data)
        raw_len = self._sock.recv(4)
        if len(raw_len) < 4:
            raise RuntimeError("greetd IPC: unexpected EOF")
        length = struct.unpack("<I", raw_len)[0]
        buf = b""
        while len(buf) < length:
            chunk = self._sock.recv(length - len(buf))
            if not chunk:
                raise RuntimeError("greetd IPC: unexpected EOF")
            buf += chunk
        return json.loads(buf.decode())

    def create_session(self, username: str) -> dict:
        return self._send({"type": "create_session", "username": username})

    def post_auth_response(self, response: str | None) -> dict:
        return self._send({
            "type": "post_auth_message_response",
            "response": response,
        })

    def start_session(self, cmd: list[str]) -> dict:
        return self._send({"type": "start_session", "cmd": cmd, "env": []})

    def cancel_session(self) -> dict:
        return self._send({"type": "cancel_session"})


# ---------------------------------------------------------------------------
#  Session discovery
# ---------------------------------------------------------------------------

def _discover_sessions() -> list[tuple[str, list[str]]]:
    """Return list of (name, exec_args) from wayland-sessions/*.desktop."""
    sessions: list[tuple[str, list[str]]] = []
    if not SESSIONS_DIR.is_dir():
        return [("labwc", ["labwc"])]
    for desktop in sorted(SESSIONS_DIR.glob("*.desktop")):
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(str(desktop))
        if not cp.has_section("Desktop Entry"):
            continue
        name = cp.get("Desktop Entry", "Name", fallback=desktop.stem)
        exec_cmd = cp.get("Desktop Entry", "Exec", fallback="")
        if exec_cmd:
            sessions.append((name, exec_cmd.split()))
    return sessions or [("labwc", ["labwc"])]


def _read_last_user() -> str | None:
    try:
        user = LAST_USER_PATH.read_text(encoding="utf-8").strip()
        return user if user else None
    except OSError:
        return None


def _write_last_user(username: str) -> None:
    try:
        LAST_USER_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_USER_PATH.write_text(username + "\n", encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
#  Greeter window
# ---------------------------------------------------------------------------

class GreeterWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Login")
        self.set_default_size(800, 600)

        try:
            self._greetd = GreetdClient()
        except RuntimeError as exc:
            print(f"greeter: {exc}", file=sys.stderr)
            sys.exit(1)

        self._sessions = _discover_sessions()
        self._selected_session = 0
        # Pick Adwaita-Lite as default
        for i, (name, _) in enumerate(self._sessions):
            if "Adwaita-Lite" in name:
                self._selected_session = i
                break

        self._last_user = _read_last_user()
        self._current_username: str | None = None
        self._session_active = False

        # --- Outer layout: vertically centered ---
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_spacing(0)

        # --- Clock ---
        self._clock_label = Gtk.Label()
        self._clock_label.add_css_class("clock")
        self._clock_label.set_halign(Gtk.Align.CENTER)
        outer.append(self._clock_label)

        self._date_label = Gtk.Label()
        self._date_label.add_css_class("date")
        self._date_label.set_halign(Gtk.Align.CENTER)
        outer.append(self._date_label)

        self._update_clock()
        GLib.timeout_add_seconds(30, self._update_clock)

        # --- Login card ---
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_size_request(400, -1)

        # Card header with gear icon
        card_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        # Spacer pushes gear to the right
        header_spacer = Gtk.Box()
        header_spacer.set_hexpand(True)
        card_header.append(header_spacer)

        gear_btn = Gtk.Button()
        gear_btn.set_icon_name("emblem-system-symbolic")
        gear_btn.add_css_class("gear-button")
        gear_btn.set_tooltip_text("Session")
        gear_btn.connect("clicked", self._on_gear_clicked)
        card_header.append(gear_btn)
        card.append(card_header)

        # Session dropdown (hidden by default)
        self._session_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._session_box.set_visible(False)
        self._session_box.set_margin_bottom(12)

        session_names = [name for name, _ in self._sessions]
        self._session_dd = Gtk.DropDown.new_from_strings(session_names)
        self._session_dd.set_selected(self._selected_session)
        self._session_dd.add_css_class("session-dropdown")
        self._session_dd.connect("notify::selected", self._on_session_changed)
        self._session_box.append(self._session_dd)
        card.append(self._session_box)

        # Greeting label
        self._greeting = Gtk.Label()
        self._greeting.add_css_class("greeting")
        self._greeting.set_halign(Gtk.Align.CENTER)
        card.append(self._greeting)

        # Username entry (shown in username state)
        self._username_entry = Gtk.Entry()
        self._username_entry.set_placeholder_text("Username")
        self._username_entry.add_css_class("form-entry")
        self._username_entry.set_hexpand(True)
        self._username_entry.connect("activate", lambda _: self._on_submit())
        card.append(self._username_entry)

        # Password entry (shown in password state)
        self._password_entry = Gtk.PasswordEntry()
        self._password_entry.set_show_peek_icon(True)
        self._password_entry.set_placeholder_text("Password")
        self._password_entry.add_css_class("form-entry")
        self._password_entry.set_hexpand(True)
        self._password_entry.connect("activate", lambda _: self._on_submit())
        card.append(self._password_entry)

        # Error label
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error-label")
        self._error_label.set_halign(Gtk.Align.START)
        self._error_label.set_visible(False)
        self._error_label.set_wrap(True)
        self._error_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._error_label.set_max_width_chars(40)
        card.append(self._error_label)

        # Submit button
        self._submit_btn = Gtk.Button()
        self._submit_btn.add_css_class("login-button")
        self._submit_btn.set_halign(Gtk.Align.END)
        self._submit_btn.set_margin_top(16)
        self._submit_btn.connect("clicked", lambda _: self._on_submit())
        card.append(self._submit_btn)

        # "Not {user}?" link
        self._switch_btn = Gtk.Button()
        self._switch_btn.add_css_class("switch-user")
        self._switch_btn.set_halign(Gtk.Align.CENTER)
        self._switch_btn.connect("clicked", lambda _: self._show_username_state())
        card.append(self._switch_btn)

        outer.append(card)
        self.set_child(outer)

        # Clear error on keypress
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

        # Start in the right state
        if self._last_user:
            self._show_password_state(self._last_user)
        else:
            self._show_username_state()

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _update_clock(self) -> bool:
        now = datetime.now()
        self._clock_label.set_text(now.strftime("%-I:%M %p"))
        self._date_label.set_text(now.strftime("%A, %B %-d, %Y"))
        return GLib.SOURCE_CONTINUE

    # ------------------------------------------------------------------
    # Card states
    # ------------------------------------------------------------------

    def _show_password_state(self, username: str) -> None:
        """Show password field for a known user."""
        self._current_username = username
        self._greeting.set_text(f"Welcome back, {username}")
        self._greeting.set_visible(True)
        self._username_entry.set_visible(False)
        self._password_entry.set_visible(True)
        self._password_entry.set_text("")
        self._password_entry.grab_focus()
        self._submit_btn.set_label("Log In")
        self._switch_btn.set_label(f"Not {username}?")
        self._switch_btn.set_visible(True)
        self._error_label.set_visible(False)

        # Pre-create greetd session
        self._create_greetd_session(username)

    def _show_username_state(self) -> None:
        """Show username entry (no last user or 'Not you?' clicked)."""
        if self._session_active:
            try:
                self._greetd.cancel_session()
            except Exception:
                pass
            self._session_active = False
        self._current_username = None
        self._greeting.set_text("Log in")
        self._greeting.set_visible(True)
        self._username_entry.set_visible(True)
        self._username_entry.set_text("")
        self._username_entry.grab_focus()
        self._password_entry.set_visible(False)
        self._submit_btn.set_label("Next")
        self._switch_btn.set_visible(False)
        self._error_label.set_visible(False)

    # ------------------------------------------------------------------
    # greetd interaction
    # ------------------------------------------------------------------

    def _create_greetd_session(self, username: str) -> None:
        """Send create_session and handle the response."""
        try:
            resp = self._greetd.create_session(username)
        except Exception as exc:
            self._show_error(f"Connection error: {exc}")
            return

        self._session_active = True

        if resp.get("type") == "auth_message":
            msg_type = resp.get("auth_message_type", "")
            if msg_type == "secret":
                # Password prompt — already showing password entry
                return
            elif msg_type == "info":
                # Info message from PAM — acknowledge and wait
                try:
                    self._greetd.post_auth_response(None)
                except Exception:
                    pass
                return
            elif msg_type == "error":
                self._show_error(resp.get("auth_message", "Authentication error"))
                return
        elif resp.get("type") == "success":
            # No auth needed (unlikely but handle it)
            self._start_session()
            return
        elif resp.get("type") == "error":
            self._show_error(resp.get("description", "Unknown error"))
            self._session_active = False
            return

    def _on_submit(self) -> None:
        """Handle submit button or Enter key."""
        if self._current_username is None:
            # Username state: advance to password
            username = self._username_entry.get_text().strip()
            if not username:
                self._show_error("Enter a username.")
                return
            self._show_password_state(username)
            return

        # Password state: authenticate
        password = self._password_entry.get_text()
        if not password:
            self._show_error("Enter your password.")
            return

        self._submit_btn.set_sensitive(False)

        try:
            resp = self._greetd.post_auth_response(password)
        except Exception as exc:
            self._show_error(f"Connection error: {exc}")
            self._submit_btn.set_sensitive(True)
            return

        if resp.get("type") == "success":
            _write_last_user(self._current_username)
            self._start_session()
        elif resp.get("type") == "auth_message":
            # Additional PAM prompt (e.g., info message after password)
            msg_type = resp.get("auth_message_type", "")
            if msg_type == "error":
                self._show_error(resp.get("auth_message", "Authentication failed"))
                self._reset_auth()
            elif msg_type == "info":
                try:
                    resp2 = self._greetd.post_auth_response(None)
                    if resp2.get("type") == "success":
                        _write_last_user(self._current_username)
                        self._start_session()
                        return
                except Exception:
                    pass
                self._show_error("Unexpected authentication response.")
                self._reset_auth()
            else:
                # Another secret prompt — unusual, show error
                self._show_error("Multi-step auth not supported.")
                self._reset_auth()
        elif resp.get("type") == "error":
            desc = resp.get("description", "")
            if resp.get("error_type") == "auth_error":
                self._show_error("Incorrect password.")
            else:
                self._show_error(desc or "Login failed.")
            self._reset_auth()
        else:
            self._show_error("Unexpected response from login service.")
            self._reset_auth()

    def _start_session(self) -> None:
        """Send start_session to greetd and exit."""
        _, cmd = self._sessions[self._selected_session]
        try:
            resp = self._greetd.start_session(cmd)
        except Exception as exc:
            self._show_error(f"Failed to start session: {exc}")
            self._submit_btn.set_sensitive(True)
            return

        if resp.get("type") == "success":
            # greetd will launch the session; we exit cleanly
            self.get_application().quit()
        else:
            self._show_error(resp.get("description", "Failed to start session."))
            self._submit_btn.set_sensitive(True)

    def _reset_auth(self) -> None:
        """Reset after auth failure: cancel session, re-create, clear password."""
        self._session_active = False
        self._submit_btn.set_sensitive(True)
        self._password_entry.set_text("")
        self._password_entry.grab_focus()
        # Re-create session for retry
        if self._current_username:
            self._create_greetd_session(self._current_username)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _show_error(self, message: str) -> None:
        self._error_label.set_text(message)
        self._error_label.set_visible(True)

    def _on_key_pressed(self, _ctrl, _keyval, _keycode, _state) -> bool:
        if self._error_label.get_visible():
            self._error_label.set_visible(False)
        return False  # Don't consume the event

    def _on_gear_clicked(self, _btn) -> None:
        self._session_box.set_visible(not self._session_box.get_visible())

    def _on_session_changed(self, dd, _pspec) -> None:
        self._selected_session = dd.get_selected()


# ---------------------------------------------------------------------------
#  Application
# ---------------------------------------------------------------------------

class GreeterApp(Gtk.Application):
    def __init__(self, css: str) -> None:
        super().__init__(application_id=APP_ID)
        self._css = css

    def do_activate(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_string(self._css)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        win = GreeterWindow(self)
        win.present()


def main() -> None:
    if "GREETD_SOCK" not in os.environ:
        sys.exit("adwaita-lite-greeter: GREETD_SOCK not set. Must be launched by greetd.")
    theme = _load_theme()
    css = _build_css(PALETTES[theme])
    app = GreeterApp(css)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-greeter').read()); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add files/usr/bin/adwaita-lite-greeter
git commit -m "feat: custom GTK4 greeter for greetd

Adwaita-themed, ChromeOS-inspired login screen:
- Prominent clock/date above centered card
- Single-user optimised: last username pre-filled
- Password-only view with 'Not user?' to switch
- Gear icon reveals session selector
- Light/dark theme via /etc/adwaita-lite/greeter.json
- greetd IPC over Unix socket with proper error handling"
```

---

### Task 2: Update greeter-setup to launch the new greeter

**Files:**
- Modify: `files/usr/libexec/adwaita-lite-greeter-setup`

- [ ] **Step 1: Replace gtkgreet command with adwaita-lite-greeter**

Change the `cat > "$CONFIG"` block. Full new file contents:

```bash
#!/bin/bash
# Ensure greetd config always points to the normal login greeter.
# First-boot wizard is handled by adwaita-lite-first-boot.service.

set -euo pipefail

CONFIG="/etc/greetd/config.toml"

cat > "$CONFIG" <<EOF
[terminal]
vt = 7

[default_session]
command = "env WLR_NO_HARDWARE_CURSORS=1 cage -s -- /usr/bin/adwaita-lite-greeter"
user = "greetd"
EOF
```

- [ ] **Step 2: Commit**

```bash
git add files/usr/libexec/adwaita-lite-greeter-setup
git commit -m "refactor: greeter-setup launches GTK4 greeter instead of gtkgreet"
```

---

### Task 3: Update build.sh — remove gtkgreet, add chmod

**Files:**
- Modify: `build_files/build.sh`

- [ ] **Step 1: Remove gtkgreet from package list**

Delete the line `    gtkgreet \` from the `dnf5 install` block (currently line 67).

- [ ] **Step 2: Add new greeter to chmod block**

Add `    /usr/bin/adwaita-lite-greeter \` to the `chmod 0755` block, after the existing `adwaita-lite-setup-wizard` line.

The chmod block should look like:

```bash
chmod 0755 \
    /etc/xdg/labwc/autostart \
    /usr/bin/adwaita-lite-settings \
    /usr/bin/adwaita-lite-setup-wizard \
    /usr/bin/adwaita-lite-greeter \
    /usr/libexec/adwaita-lite-apply-settings \
    /usr/libexec/adwaita-lite-encrypted-swap \
    /usr/libexec/adwaita-lite-flatpak-setup \
    /usr/libexec/adwaita-lite-swap-init \
    /usr/libexec/adwaita-lite-greeter-setup \
    /usr/libexec/adwaita-lite-session \
    /usr/libexec/adwaita-lite-volume \
    /usr/libexec/adwaita-lite-brightness \
    /usr/bin/adwaita-lite-power-menu
```

- [ ] **Step 3: Commit**

```bash
git add build_files/build.sh
git commit -m "build: remove gtkgreet package, add chmod for GTK4 greeter"
```

---

### Task 4: Delete gtkgreet.css

**Files:**
- Delete: `files/etc/greetd/gtkgreet.css`

- [ ] **Step 1: Remove the file**

```bash
rm files/etc/greetd/gtkgreet.css
```

- [ ] **Step 2: Verify no remaining references**

```bash
grep -rn "gtkgreet" files/ build_files/ --include="*.sh" --include="*.py" --include="*.css" --include="*.toml" --include="*.service" --include="*.conf"
```

Expected: only `files/etc/greetd/config.toml` (the static fallback, which is overwritten by greeter-setup on every boot — update it too).

- [ ] **Step 3: Update the static config.toml fallback**

Write to `files/etc/greetd/config.toml`:

```toml
[terminal]
vt = 7

[default_session]
command = "env WLR_NO_HARDWARE_CURSORS=1 cage -s -- /usr/bin/adwaita-lite-greeter"
user = "greetd"
```

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove gtkgreet.css, update static config.toml fallback"
```

---

### Task 5: Final verification and push

- [ ] **Step 1: Verify Python syntax**

```bash
python3 -c "import ast; ast.parse(open('files/usr/bin/adwaita-lite-greeter').read()); print('OK')"
```

- [ ] **Step 2: Verify no orphaned gtkgreet references**

```bash
grep -rn "gtkgreet" files/ build_files/ docs/
```

Expected: only the design spec (docs/) and the audit doc — no functional references.

- [ ] **Step 3: Review git log**

```bash
git log --oneline -5
```

Expected: 4 new commits (greeter script, greeter-setup, build.sh, cleanup).

- [ ] **Step 4: Push**

```bash
git push
```
