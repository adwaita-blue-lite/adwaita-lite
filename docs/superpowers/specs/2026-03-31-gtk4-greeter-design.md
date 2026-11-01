# Adwaita-Lite GTK4 Greeter — Design Spec

## Context

The current login screen uses gtkgreet (GTK3), which limits CSS capabilities and doesn't integrate with the settings app theme system. The session dropdown inherits the login button's blue pill styling, making it look like a second submit button. GTK3 CSS lacks proper box-shadow, focus ring, and other refinements available in GTK4.

Replace gtkgreet with a custom GTK4 Python greeter that shares the same Adwaita design language as the wizard and settings app. Feels like a libadwaita experience without the dependency. ChromeOS login screen is the UX reference — clean, single-user-focused, clock prominent, card centered.

## Architecture

Single Python/GTK4 script: `/usr/bin/adwaita-lite-greeter`

- Communicates with greetd via IPC protocol (length-prefixed JSON over `$GREETD_SOCK` Unix socket)
- Runs inside cage (kiosk Wayland compositor) launched by greetd
- Reads optional system config at `/etc/adwaita-lite/greeter.json` for theme preference
- Stores last-logged-in username at `/var/lib/adwaita-lite/last-user`
- ~400-600 lines Python, inline CSS generated from Adwaita palette

## greetd IPC Protocol

Wire format: 4-byte little-endian length prefix, then JSON payload.

### Message types (greeter → greetd)

```json
{"type": "create_session", "username": "alice"}
{"type": "post_auth_message_response", "response": "password123"}
{"type": "start_session", "cmd": ["labwc"], "env": []}
{"type": "cancel_session"}
```

### Response types (greetd → greeter)

```json
{"type": "success"}
{"type": "auth_message", "auth_message_type": "secret", "auth_message": "Password:"}
{"type": "auth_message", "auth_message_type": "info", "auth_message": "..."}
{"type": "auth_message", "auth_message_type": "error", "auth_message": "..."}
{"type": "error", "error_type": "auth_error", "description": "..."}
{"type": "error", "error_type": "error", "description": "..."}
```

### Auth flow

1. Greeter sends `create_session(username)`
2. greetd responds with `auth_message` type `secret` → greeter shows password field
3. User enters password → greeter sends `post_auth_message_response(password)`
4. greetd responds `success` → greeter sends `start_session(cmd, env)` → greetd launches session, greeter process exits
5. greetd responds `error` (auth_error) → greeter shows error, clears password, re-sends `create_session` to reset state

### IPC helper (Python)

```python
import json
import os
import socket
import struct

def _greetd_connect():
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(os.environ["GREETD_SOCK"])
    return sock

def _greetd_send(sock, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    sock.sendall(struct.pack("<I", len(data)) + data)
    length = struct.unpack("<I", sock.recv(4))[0]
    return json.loads(sock.recv(length).decode())
```

## Visual Layout

Vertically centered on screen, stacked top-to-bottom:

```
┌─────────────────────────────────────────────┐
│                                             │
│                                             │
│                 10:42 AM                    │  ← 48px Roboto, text_primary
│           Monday, March 31, 2026            │  ← 16px Roboto, text_secondary
│                                             │
│         ┌─────────────────────────┐         │
│         │                     ⚙  │         │  ← gear icon, top-right, muted
│         │                        │         │
│         │   Welcome back, Race   │         │  ← 20px Roboto, text_primary
│         │                        │         │
│         │   ┌──────────────────┐ │         │
│         │   │ Password         │ │         │  ← entry field, Adwaita styling
│         │   └──────────────────┘ │         │
│         │              [Log In]  │         │  ← accent-colored pill button
│         │                        │         │
│         │     Not race?          │         │  ← small link, text_secondary
│         │                        │         │
│         └─────────────────────────┘         │
│                                             │
│                                             │
└─────────────────────────────────────────────┘
```

### Card states

**State A — Password (default, last-user exists):**
- Greeting: "Welcome back, {display_name or username}"
- Password entry (focused on load)
- "Log In" button (accent color, pill shape)
- "Not {username}?" link below

**State B — Username (no last-user, or "Not you?" clicked):**
- Label: "Log in"
- Username entry (focused on load)
- "Next" button (accent color, pill shape)

**State C — Session selector revealed (gear clicked):**
- Dropdown appears below the gear icon
- Lists sessions from `/usr/share/wayland-sessions/*.desktop`
- Default: "Adwaita-Lite"

### Error display

- Red error label appears inside card between the entry and button
- Adwaita error color (#e62d42 light, #ff6b6b dark)
- Clears on next keystroke

## Theme System

### Palette

Hardcode both Adwaita palettes (identical to apply-settings):

| Token | Light | Dark |
|-------|-------|------|
| window_bg | #fafafa | #242424 |
| card_bg | #ffffff | #383838 |
| fg (text_primary) | #1e1e1e | #ffffff |
| secondary_fg | #5e5c64 | #c0bfbc |
| border | #d1d1d1 | #4a4a4a |
| accent | #3584e4 | #3584e4 |
| error | #e62d42 | #ff6b6b |

### Config file

`/etc/adwaita-lite/greeter.json` (optional, created by settings app later):
```json
{
  "theme": "light"
}
```

If missing, default to light. The settings app will write this file when the user changes the greeter theme preference (future feature).

### CSS generation

Same pattern as the wizard: build a CSS string from the palette at startup, load via `CssProvider.load_from_string()`. The CSS uses the Adwaita tokens directly — no magic values.

## Session Discovery

Read `/usr/share/wayland-sessions/*.desktop` files at startup. Parse `Name=` and `Exec=` from each. Default to the first entry whose `Name` contains "Adwaita-Lite", or the first entry if none match.

## Keyboard Navigation

- **Enter** on password/username entry → submit
- **Tab** between fields (standard GTK focus chain)
- **Escape** in password state with last-user → does nothing (no cancel needed)

## File Changes

### Create
- `/usr/bin/adwaita-lite-greeter` — the new GTK4 Python greeter (~400-600 lines)

### Modify
- `/usr/libexec/adwaita-lite-greeter-setup` — change gtkgreet command to `adwaita-lite-greeter`
- `/build_files/build.sh` — remove `gtkgreet` package, add `chmod` for new greeter

### Remove
- `/etc/greetd/gtkgreet.css` — no longer needed (CSS is inline in the greeter)

### Keep unchanged
- `/etc/greetd/config.toml` — still written dynamically by greeter-setup
- `greetd.service.d/10-greeter-setup.conf` — still runs greeter-setup as ExecStartPre
- All other services and scripts

## Last-User Persistence

- On successful login: write username to `/var/lib/adwaita-lite/last-user`
- On startup: read last-user file, if exists → pre-fill and send `create_session`
- File is plain text, single line, just the username
- Written by the greeter just before `start_session` succeeds
- Directory `/var/lib/adwaita-lite/` already exists (created by wizard)

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Wrong password | Show error "Incorrect password", clear password field, re-focus. Re-send `create_session` to reset greetd state. |
| Unknown username | Show error from greetd's response description |
| `$GREETD_SOCK` missing | Print to stderr, exit 1 (greetd will restart the greeter) |
| Session start failure | Show error, allow retry |
| IPC socket error | Print to stderr, exit 1 |
| No sessions found in wayland-sessions/ | Hardcode fallback: `["labwc"]` |

## Clock

- Updated every 30 seconds via `GLib.timeout_add_seconds(30, ...)`
- Format: 12-hour with AM/PM (`%-I:%M %p`) — matches default clock_24h=False
- Date: `%A, %B %-d, %Y` — matches waybar tooltip format
- No user-specific 24h preference available at login (no user logged in)
