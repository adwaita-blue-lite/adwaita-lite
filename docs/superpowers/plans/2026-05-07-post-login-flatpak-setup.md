# Post-Login Flatpak Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace pre-login Flatpak installation with a post-login Adwaita/ChromeOS-style app setup card that lets users install, defer, or opt out after the desktop is usable.

**Architecture:** Disable the pre-login Flatpak install gate and move user-visible installation into a new GTK4 session app launched from labwc autostart. The app reads `/var/lib/adwaita-lite/flatpak-apps`, respects existing done/skip stamps, uses a small root helper for system Flatpak operations, and owns all progress/error UI.

**Tech Stack:** Python 3, GTK4/PyGObject, Bash root helper, sudoers, labwc autostart, pytest static/method tests, Flatpak CLI.

---

## File Structure

- Create `files/usr/bin/adwaita-lite-app-setup`
  - GTK4 post-login app setup card.
  - Reads selected app IDs and state stamps.
  - Shows Ready, Installing, No Network, Partial Failure, and Complete states.
  - Runs a privileged helper for system Flatpak work.
- Create `files/usr/libexec/adwaita-lite-app-setup-helper`
  - Root-only Bash helper for `install`, `skip`, and `status` actions.
  - Installs selected refs idempotently and writes `/var/lib/adwaita-lite/flatpak-setup.done` only when all selected refs are present.
  - Writes `/var/lib/adwaita-lite/flatpak-setup.skip` for permanent opt-out.
- Create `files/etc/sudoers.d/adwaita-lite-app-setup`
  - Allows all normal users to run only `/usr/libexec/adwaita-lite-app-setup-helper` as root without a password.
- Modify `files/etc/xdg/labwc/autostart`
  - Launches `/usr/bin/adwaita-lite-app-setup` in normal Adwaita Lite sessions after desktop services start.
- Modify `build_files/build.sh`
  - Marks the new app and helper executable.
  - Disables `adwaita-lite-flatpak-install.service` so app setup no longer blocks pre-login first boot.
  - Keeps `adwaita-lite-flatpak-update.service` enabled for systems with the done stamp.
- Modify `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`
  - Leave the unit file available for recovery/manual use but remove its install target so new builds do not pull it into `graphical.target`.
- Modify `files/usr/libexec/adwaita-lite-flatpak-setup`
  - Keep the script for manual/recovery use, but remove greeter-oriented progress assumptions from comments if needed.
- Add `tests/test_post_login_flatpak_setup.py`
  - Static and method-level tests for prompt gating, copy, helper invocation, and CSS contract.
- Extend `tests/test_flatpak_setup_contract.py`
  - Assert pre-login install is not enabled and new helper/sudoers/autostart contracts exist.

---

### Task 1: Contract Tests For Moving Setup Post-Login

**Files:**
- Modify: `tests/test_flatpak_setup_contract.py`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Add failing contract tests**

Append these tests to `tests/test_flatpak_setup_contract.py`:

```python

APP_SETUP = ROOT / "files/usr/bin/adwaita-lite-app-setup"
APP_SETUP_HELPER = ROOT / "files/usr/libexec/adwaita-lite-app-setup-helper"
APP_SETUP_SUDOERS = ROOT / "files/etc/sudoers.d/adwaita-lite-app-setup"
LABWC_AUTOSTART = ROOT / "files/etc/xdg/labwc/autostart"
APP_SETUP_HELPER_PATH = "/usr/libexec/adwaita-lite-app-setup-helper"


def test_prelogin_flatpak_install_is_not_enabled_by_default():
    service = FLATPAK_INSTALL_SERVICE.read_text()
    build = BUILD_SCRIPT.read_text()

    assert "WantedBy=graphical.target" not in service
    assert "systemctl enable adwaita-lite-flatpak-install.service" not in build


def test_post_login_app_setup_is_autostarted_and_executable():
    autostart = LABWC_AUTOSTART.read_text()
    build = BUILD_SCRIPT.read_text()

    assert "/usr/bin/adwaita-lite-app-setup" in autostart
    assert "/usr/bin/adwaita-lite-app-setup" in build
    assert APP_SETUP.exists()


def test_post_login_app_setup_helper_and_sudoers_contract():
    helper = APP_SETUP_HELPER.read_text()
    sudoers = APP_SETUP_SUDOERS.read_text()
    build = BUILD_SCRIPT.read_text()

    assert helper.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in helper
    assert "install)" in helper
    assert "skip)" in helper
    assert "status)" in helper
    assert "/var/lib/adwaita-lite/flatpak-apps" in helper
    assert "/var/lib/adwaita-lite/flatpak-setup.done" in helper
    assert "/var/lib/adwaita-lite/flatpak-setup.skip" in helper
    assert "flatpak install --or-update --system --noninteractive" in helper
    assert "ALL ALL=(root) NOPASSWD: /usr/libexec/adwaita-lite-app-setup-helper" in sudoers
    assert APP_SETUP_HELPER_PATH in build
```

- [ ] **Step 2: Run contract tests and verify expected failure**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py
```

Expected: new tests fail because the app setup script, helper, sudoers file, autostart entry, build chmod entry, and service disablement do not exist yet.

- [ ] **Step 3: Commit failing contract tests**

Run:

```bash
git add tests/test_flatpak_setup_contract.py
git commit -m "test(flatpak): define post-login setup contract"
```

---

### Task 2: Disable Pre-Login Install And Wire Session Autostart

**Files:**
- Modify: `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`
- Modify: `build_files/build.sh`
- Modify: `files/etc/xdg/labwc/autostart`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Remove install target from pre-login Flatpak install service**

In `files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service`, delete the final install section:

```ini
[Install]
WantedBy=graphical.target
```

Leave the `[Unit]` and `[Service]` sections intact for manual recovery use.

- [ ] **Step 2: Stop enabling the pre-login install service**

In `build_files/build.sh`, replace:

```bash
systemctl enable adwaita-lite-flatpak-install.service
systemctl enable adwaita-lite-flatpak-update.service
```

with:

```bash
systemctl disable adwaita-lite-flatpak-install.service 2>/dev/null || true
systemctl enable adwaita-lite-flatpak-update.service
```

- [ ] **Step 3: Add future executable paths to build chmod block**

In the `chmod 0755 \` block in `build_files/build.sh`, add these entries after `/usr/bin/adwaita-lite-greeter \` and `/usr/libexec/adwaita-lite-flatpak-skip \` respectively:

```bash
    /usr/bin/adwaita-lite-app-setup \
```

```bash
    /usr/libexec/adwaita-lite-app-setup-helper \
```

- [ ] **Step 4: Launch app setup from labwc autostart**

In `files/etc/xdg/labwc/autostart`, after the `apply-settings --mode=live` block at the end, add:

```sh
# Offer post-login installation for apps selected during setup. This is
# intentionally after the desktop is usable; Flatpak setup must never block login.
/usr/bin/adwaita-lite-app-setup \
  >/dev/null 2>"$_logdir/app-setup.log" &
```

- [ ] **Step 5: Run contract tests and observe remaining expected failures**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py
```

Expected: `test_prelogin_flatpak_install_is_not_enabled_by_default` passes. Tests requiring the new app/helper files still fail until later tasks.

- [ ] **Step 6: Commit service/autostart wiring**

Run:

```bash
git add files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service \
        build_files/build.sh \
        files/etc/xdg/labwc/autostart
git commit -m "refactor(flatpak): move app setup out of pre-login boot"
```

---

### Task 3: Root Helper For Post-Login Setup

**Files:**
- Create: `files/usr/libexec/adwaita-lite-app-setup-helper`
- Create: `files/etc/sudoers.d/adwaita-lite-app-setup`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Create helper script**

Create `files/usr/libexec/adwaita-lite-app-setup-helper`:

```bash
#!/bin/bash
set -euo pipefail

APPS_FILE=/var/lib/adwaita-lite/flatpak-apps
STAMP=/var/lib/adwaita-lite/flatpak-setup.done
SKIP_STAMP=/var/lib/adwaita-lite/flatpak-setup.skip
FLATHUB_REPO_FILE=/etc/flatpak/remotes.d/flathub.flatpakrepo
FLATHUB_URL=https://dl.flathub.org/repo/flathub.flatpakrepo

ensure_flathub() {
    local source="$FLATHUB_URL"
    if [ -f "$FLATHUB_REPO_FILE" ]; then
        source="$FLATHUB_REPO_FILE"
    fi
    flatpak remote-add --system --if-not-exists flathub "$source" >/dev/null
}

installed_refs() {
    flatpak list --system --columns=application 2>/dev/null || true
}

app_count() {
    if [ ! -s "$APPS_FILE" ]; then
        echo 0
        return
    fi
    grep -c . "$APPS_FILE" 2>/dev/null || echo 0
}

status() {
    if [ -f "$STAMP" ]; then
        echo done
    elif [ -f "$SKIP_STAMP" ]; then
        echo skipped
    elif [ ! -s "$APPS_FILE" ]; then
        echo empty
    else
        echo pending
    fi
}

skip_setup() {
    mkdir -p "$(dirname "$SKIP_STAMP")"
    : > "$SKIP_STAMP"
    chmod 0644 "$SKIP_STAMP"
}

install_apps() {
    if [ -f "$SKIP_STAMP" ]; then
        echo "SKIPPED"
        return 0
    fi
    if [ ! -s "$APPS_FILE" ]; then
        touch "$STAMP"
        echo "DONE"
        return 0
    fi

    ensure_flathub
    local total current missing installed app_id
    total=$(app_count)
    current=0
    missing=0
    installed=$(installed_refs)

    while IFS= read -r app_id; do
        [ -n "$app_id" ] || continue
        current=$((current + 1))
        if printf '%s\n' "$installed" | grep -qx "$app_id"; then
            printf 'PROGRESS %s %s %s already-installed\n' "$current" "$total" "$app_id"
            continue
        fi
        printf 'PROGRESS %s %s %s installing\n' "$current" "$total" "$app_id"
        if flatpak install --or-update --system --noninteractive flathub "$app_id" >/dev/null; then
            printf 'PROGRESS %s %s %s installed\n' "$current" "$total" "$app_id"
        else
            printf 'FAILED %s\n' "$app_id"
            missing=$((missing + 1))
        fi
    done < "$APPS_FILE"

    if [ "$missing" -eq 0 ]; then
        touch "$STAMP"
        echo "DONE"
    else
        echo "PARTIAL $missing"
    fi
}

case "${1:-}" in
    install)
        install_apps
        ;;
    skip)
        skip_setup
        ;;
    status)
        status
        ;;
    count)
        app_count
        ;;
    *)
        echo "Usage: $0 {install|skip|status|count}" >&2
        exit 64
        ;;
esac
```

- [ ] **Step 2: Create sudoers drop-in**

Create `files/etc/sudoers.d/adwaita-lite-app-setup`:

```sudoers
ALL ALL=(root) NOPASSWD: /usr/libexec/adwaita-lite-app-setup-helper
```

- [ ] **Step 3: Run helper contract and syntax tests**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py
bash -n files/usr/libexec/adwaita-lite-app-setup-helper
visudo -c -f files/etc/sudoers.d/adwaita-lite-app-setup
```

Expected: helper/sudoers contract passes. The app setup file contract still fails until Task 4. Bash syntax passes. `visudo` reports the sudoers file parsed OK.

- [ ] **Step 4: Commit helper**

Run:

```bash
git add files/usr/libexec/adwaita-lite-app-setup-helper \
        files/etc/sudoers.d/adwaita-lite-app-setup
git commit -m "feat(flatpak): add post-login app setup helper"
```

---

### Task 4: App Setup Card Tests

**Files:**
- Create: `tests/test_post_login_flatpak_setup.py`
- Test: `tests/test_post_login_flatpak_setup.py`

- [ ] **Step 1: Add tests for script contract and pure helpers**

Create `tests/test_post_login_flatpak_setup.py`:

```python
import importlib.machinery
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "files/usr/bin/adwaita-lite-app-setup"
HELPER = "/usr/libexec/adwaita-lite-app-setup-helper"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("app_setup", str(SCRIPT))
    spec = importlib.util.spec_from_loader("app_setup", loader, origin=str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    module.__file__ = str(SCRIPT)
    spec.loader.exec_module(module)
    return module


def test_app_setup_copy_and_visual_contract():
    source = SCRIPT.read_text()

    assert "Set up your apps" in source
    assert "Install the apps you selected during setup" in source
    assert "Install apps" in source
    assert "Not now" in source
    assert "Don't ask again" in source
    assert "first boot" not in source.lower()
    assert "max-width: 480px" in source
    assert "border-radius: 16px" in source
    assert ".primary-button" in source
    assert ".secondary-button" in source
    assert ".low-emphasis-button" in source


def test_should_show_prompt_requires_apps_without_done_or_skip(tmp_path):
    module = _load_module()
    apps = tmp_path / "flatpak-apps"
    done = tmp_path / "done"
    skip = tmp_path / "skip"

    apps.write_text("com.google.Chrome\n")
    assert module._should_show_prompt(apps, done, skip) is True

    done.touch()
    assert module._should_show_prompt(apps, done, skip) is False
    done.unlink()
    skip.touch()
    assert module._should_show_prompt(apps, done, skip) is False
    skip.unlink()
    apps.write_text("")
    assert module._should_show_prompt(apps, done, skip) is False


def test_app_preview_limits_and_falls_back_to_ids(tmp_path):
    module = _load_module()
    apps = tmp_path / "flatpak-apps"
    apps.write_text("com.google.Chrome\nio.github.kolunmi.Bazaar\norg.example.Unknown\norg.more.App\n")

    preview = module._app_preview(apps, limit=3)

    assert preview == ["Google Chrome", "Bazaar", "org.example.Unknown", "+1 more"]


def test_helper_command_uses_noninteractive_sudo():
    module = _load_module()

    assert module._helper_command("install") == ["sudo", "-n", HELPER, "install"]
    assert module._helper_command("skip") == ["sudo", "-n", HELPER, "skip"]


def test_install_output_parser_reports_progress_and_failures():
    module = _load_module()
    events = module._parse_install_output(
        "PROGRESS 1 2 com.google.Chrome installing\n"
        "PROGRESS 1 2 com.google.Chrome installed\n"
        "FAILED io.github.kolunmi.Bazaar\n"
        "PARTIAL 1\n"
    )

    assert events.progress == (1, 2, "com.google.Chrome", "installed")
    assert events.failed == ["io.github.kolunmi.Bazaar"]
    assert events.complete is False


def test_success_output_parser_marks_complete():
    module = _load_module()
    events = module._parse_install_output("DONE\n")

    assert events.complete is True
    assert events.failed == []
```

- [ ] **Step 2: Run tests and verify expected failure**

Run:

```bash
pytest -q tests/test_post_login_flatpak_setup.py
```

Expected: tests fail because `files/usr/bin/adwaita-lite-app-setup` does not exist yet.

- [ ] **Step 3: Commit failing tests**

Run:

```bash
git add tests/test_post_login_flatpak_setup.py
git commit -m "test(flatpak): define post-login app setup UI contract"
```

---

### Task 5: Implement App Setup Card Shell And Helpers

**Files:**
- Create: `files/usr/bin/adwaita-lite-app-setup`
- Test: `tests/test_post_login_flatpak_setup.py`
- Test: `tests/test_flatpak_setup_contract.py`

- [ ] **Step 1: Create the app setup script**

Create `files/usr/bin/adwaita-lite-app-setup` with:

```python
#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402


APP_ID = "org.adwaitabluelite.AppSetup"
APPS_FILE = Path("/var/lib/adwaita-lite/flatpak-apps")
DONE_STAMP = Path("/var/lib/adwaita-lite/flatpak-setup.done")
SKIP_STAMP = Path("/var/lib/adwaita-lite/flatpak-setup.skip")
HELPER = "/usr/libexec/adwaita-lite-app-setup-helper"
PALETTE_PATH = Path("/usr/share/adwaita-lite/palette.json")

APP_NAMES = {
    "com.google.Chrome": "Google Chrome",
    "io.github.kolunmi.Bazaar": "Bazaar",
    "org.gtk.Gtk3theme.adw-gtk3": "GTK theme support",
    "org.gtk.Gtk3theme.adw-gtk3-dark": "Dark GTK theme support",
}


@dataclass
class InstallEvents:
    progress: tuple[int, int, str, str] | None = None
    failed: list[str] = field(default_factory=list)
    complete: bool = False


def _should_show_prompt(apps_file: Path = APPS_FILE,
                        done_stamp: Path = DONE_STAMP,
                        skip_stamp: Path = SKIP_STAMP) -> bool:
    return apps_file.exists() and apps_file.stat().st_size > 0 \
        and not done_stamp.exists() and not skip_stamp.exists()


def _selected_app_ids(apps_file: Path = APPS_FILE) -> list[str]:
    try:
        return [line.strip() for line in apps_file.read_text().splitlines() if line.strip()]
    except OSError:
        return []


def _friendly_name(app_id: str) -> str:
    return APP_NAMES.get(app_id, app_id)


def _app_preview(apps_file: Path = APPS_FILE, limit: int = 4) -> list[str]:
    app_ids = _selected_app_ids(apps_file)
    preview = [_friendly_name(app_id) for app_id in app_ids[:limit]]
    remaining = len(app_ids) - len(preview)
    if remaining > 0:
        preview.append(f"+{remaining} more")
    return preview


def _helper_command(action: str) -> list[str]:
    return ["sudo", "-n", HELPER, action]


def _parse_install_output(output: str) -> InstallEvents:
    events = InstallEvents()
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "PROGRESS" and len(parts) >= 5:
            try:
                events.progress = (int(parts[1]), int(parts[2]), parts[3], parts[4])
            except ValueError:
                continue
        elif parts[0] == "FAILED" and len(parts) >= 2:
            events.failed.append(parts[1])
        elif parts[0] == "DONE":
            events.complete = True
    return events


def _load_palette() -> dict:
    try:
        raw = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {
            "light": {"window_bg": "#fafafa", "card_bg": "#ffffff", "fg": "#1e1e1e", "secondary_fg": "#5e5c64", "border": "#d9d9dc"},
            "dark": {"window_bg": "#222226", "card_bg": "#36363a", "fg": "#ffffff", "secondary_fg": "#c0bfbc", "border": "#434349"},
            "accents": {"blue": "#3584e4", "red": "#e62d42"},
        }
    return raw


def _build_css() -> str:
    palette = _load_palette()
    p = palette["dark"]
    accent = palette.get("accents", {}).get("blue", "#3584e4")
    error = palette.get("accents", {}).get("red", "#e62d42")
    return f"""\
window {{
    background-color: transparent;
}}

.app-setup-card {{
    background-color: {p["card_bg"]};
    color: {p["fg"]};
    border: 1px solid {p["border"]};
    border-radius: 16px;
    padding: 32px;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.30), 0 8px 24px rgba(0,0,0,0.35);
    max-width: 480px;
}}

.title {{ font-size: 24px; font-weight: 700; color: {p["fg"]}; }}
.subtitle, .status, .app-preview {{ font-size: 14px; color: {p["secondary_fg"]}; }}
.error {{ color: {error}; }}

.primary-button {{
    background: {accent};
    color: white;
    border-radius: 999px;
    padding: 10px 24px;
    font-weight: 700;
}}

.secondary-button, .low-emphasis-button {{
    background: none;
    border: none;
    color: {p["secondary_fg"]};
    padding: 8px 12px;
}}
"""


class AppSetupWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application) -> None:
        super().__init__(application=app, title="Set up your apps")
        self.set_default_size(520, 360)
        self.set_resizable(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)
        outer.set_margin_top(32)
        outer.set_margin_bottom(32)
        outer.set_margin_start(32)
        outer.set_margin_end(32)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        card.add_css_class("app-setup-card")
        card.set_size_request(420, -1)
        outer.append(card)

        self._title = Gtk.Label(label="Set up your apps")
        self._title.add_css_class("title")
        self._title.set_halign(Gtk.Align.START)
        card.append(self._title)

        self._subtitle = Gtk.Label(label="Install the apps you selected during setup. You can keep using the desktop while this runs.")
        self._subtitle.add_css_class("subtitle")
        self._subtitle.set_wrap(True)
        self._subtitle.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._subtitle.set_halign(Gtk.Align.START)
        card.append(self._subtitle)

        preview = ", ".join(_app_preview())
        self._preview = Gtk.Label(label=preview)
        self._preview.add_css_class("app-preview")
        self._preview.set_wrap(True)
        self._preview.set_halign(Gtk.Align.START)
        card.append(self._preview)

        self._status = Gtk.Label(label="Ready")
        self._status.add_css_class("status")
        self._status.set_wrap(True)
        self._status.set_halign(Gtk.Align.START)
        card.append(self._status)

        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        card.append(self._spinner)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_halign(Gtk.Align.END)
        card.append(actions)

        self._dismiss_btn = Gtk.Button(label="Not now")
        self._dismiss_btn.add_css_class("secondary-button")
        self._dismiss_btn.connect("clicked", lambda _btn: self.close())
        actions.append(self._dismiss_btn)

        self._skip_btn = Gtk.Button(label="Don't ask again")
        self._skip_btn.add_css_class("low-emphasis-button")
        self._skip_btn.connect("clicked", lambda _btn: self._skip())
        actions.append(self._skip_btn)

        self._install_btn = Gtk.Button(label="Install apps")
        self._install_btn.add_css_class("primary-button")
        self._install_btn.connect("clicked", lambda _btn: self._install())
        actions.append(self._install_btn)

        self.set_child(outer)

    def _set_busy(self, busy: bool) -> None:
        self._install_btn.set_sensitive(not busy)
        self._skip_btn.set_sensitive(not busy)
        self._spinner.set_visible(busy)
        if busy:
            self._spinner.start()
        else:
            self._spinner.stop()

    def _skip(self) -> None:
        try:
            subprocess.run(_helper_command("skip"), check=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as exc:
            self._status.set_text(f"Could not disable app setup: {exc}")
            self._status.add_css_class("error")
            return
        self.close()

    def _install(self) -> None:
        self._set_busy(True)
        self._title.set_text("Installing apps")
        self._status.set_text("Starting app installation...")
        GLib.idle_add(self._run_install)

    def _run_install(self) -> bool:
        try:
            result = subprocess.run(
                _helper_command("install"),
                check=False,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._set_busy(False)
            self._title.set_text("No network connection")
            self._status.set_text(f"Connect to Wi-Fi or Ethernet, then try again. ({exc})")
            self._status.add_css_class("error")
            self._install_btn.set_label("Try again")
            return GLib.SOURCE_REMOVE

        events = _parse_install_output(result.stdout)
        self._set_busy(False)
        if result.returncode == 0 and events.complete:
            self._title.set_text("Apps installed")
            self._status.set_text("Your selected apps are ready to use.")
            self._install_btn.set_label("Done")
            self._install_btn.connect("clicked", lambda _btn: self.close())
        elif events.failed:
            self._title.set_text("Some apps couldn't be installed")
            failed = ", ".join(_friendly_name(app_id) for app_id in events.failed)
            self._status.set_text(f"Failed: {failed}")
            self._status.add_css_class("error")
            self._install_btn.set_label("Retry failed apps")
        else:
            self._title.set_text("No network connection")
            self._status.set_text("Connect to Wi-Fi or Ethernet, then try again.")
            self._status.add_css_class("error")
            self._install_btn.set_label("Try again")
        return GLib.SOURCE_REMOVE


class AppSetup(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)

    def do_activate(self) -> None:
        if not _should_show_prompt():
            self.quit()
            return
        provider = Gtk.CssProvider()
        provider.load_from_string(_build_css())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        window = AppSetupWindow(self)
        window.present()


def main() -> None:
    app = AppSetup()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
pytest -q tests/test_post_login_flatpak_setup.py tests/test_flatpak_setup_contract.py
python -m py_compile files/usr/bin/adwaita-lite-app-setup
```

Expected: all tests pass except any contract that still requires autostart/build files from Task 2 if Task 2 was not completed. `py_compile` exits with no output.

- [ ] **Step 3: Commit app shell**

Run:

```bash
git add files/usr/bin/adwaita-lite-app-setup tests/test_post_login_flatpak_setup.py
git commit -m "feat(flatpak): add post-login app setup card"
```

---

### Task 6: Polish Install Progress And Background Behavior

**Files:**
- Modify: `files/usr/bin/adwaita-lite-app-setup`
- Test: `tests/test_post_login_flatpak_setup.py`

- [ ] **Step 1: Add test for non-blocking install worker**

Append to `tests/test_post_login_flatpak_setup.py`:

```python

def test_app_setup_uses_background_thread_for_install():
    source = SCRIPT.read_text()

    assert "threading.Thread" in source
    assert "GLib.idle_add" in source
    assert "Run in background" in source
```

- [ ] **Step 2: Verify test fails before implementation**

Run:

```bash
pytest -q tests/test_post_login_flatpak_setup.py::test_app_setup_uses_background_thread_for_install
```

Expected: fails because install still runs from a GLib idle callback in the UI thread and no `Run in background` button exists.

- [ ] **Step 3: Implement background thread import and button copy**

In `files/usr/bin/adwaita-lite-app-setup`, add:

```python
import threading
```

Change `_install()` to start a worker thread:

```python
    def _install(self) -> None:
        self._set_busy(True)
        self._title.set_text("Installing apps")
        self._status.set_text("Starting app installation...")
        self._dismiss_btn.set_label("Run in background")
        threading.Thread(target=self._run_install_worker, daemon=True).start()
```

Rename `_run_install()` to `_run_install_worker()` and remove its `return GLib.SOURCE_REMOVE` lines. Wrap UI updates with `GLib.idle_add`:

```python
    def _run_install_worker(self) -> None:
        try:
            result = subprocess.run(
                _helper_command("install"),
                check=False,
                capture_output=True,
                text=True,
                timeout=1800,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            GLib.idle_add(self._show_install_exception, exc)
            return
        GLib.idle_add(self._show_install_result, result)
```

Add these UI methods after the worker:

```python
    def _show_install_exception(self, exc) -> bool:
        self._set_busy(False)
        self._title.set_text("No network connection")
        self._status.set_text(f"Connect to Wi-Fi or Ethernet, then try again. ({exc})")
        self._status.add_css_class("error")
        self._install_btn.set_label("Try again")
        return GLib.SOURCE_REMOVE

    def _show_install_result(self, result) -> bool:
        events = _parse_install_output(result.stdout)
        self._set_busy(False)
        if result.returncode == 0 and events.complete:
            self._title.set_text("Apps installed")
            self._status.set_text("Your selected apps are ready to use.")
            self._install_btn.set_label("Done")
            self._install_btn.connect("clicked", lambda _btn: self.close())
        elif events.failed:
            self._title.set_text("Some apps couldn't be installed")
            failed = ", ".join(_friendly_name(app_id) for app_id in events.failed)
            self._status.set_text(f"Failed: {failed}")
            self._status.add_css_class("error")
            self._install_btn.set_label("Retry failed apps")
        else:
            self._title.set_text("No network connection")
            self._status.set_text("Connect to Wi-Fi or Ethernet, then try again.")
            self._status.add_css_class("error")
            self._install_btn.set_label("Try again")
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest -q tests/test_post_login_flatpak_setup.py
python -m py_compile files/usr/bin/adwaita-lite-app-setup
```

Expected: all tests pass and syntax check exits with no output.

- [ ] **Step 5: Commit progress polish**

Run:

```bash
git add files/usr/bin/adwaita-lite-app-setup tests/test_post_login_flatpak_setup.py
git commit -m "fix(flatpak): run app setup install in background"
```

---

### Task 7: Final Verification

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run Flatpak setup tests**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py tests/test_flatpak_greeter_skip.py tests/test_post_login_flatpak_setup.py
```

Expected: all tests pass.

- [ ] **Step 2: Run related session and translation tests**

Run:

```bash
pytest -q tests/test_iso_install_contract.py tests/test_translation_catalogs.py
```

Expected: all tests pass.

- [ ] **Step 3: Run syntax checks**

Run:

```bash
python -m py_compile files/usr/bin/adwaita-lite-app-setup
bash -n files/usr/libexec/adwaita-lite-app-setup-helper
bash -n files/usr/libexec/adwaita-lite-flatpak-setup
visudo -c -f files/etc/sudoers.d/adwaita-lite-app-setup
```

Expected: Python and Bash checks exit with no output. `visudo` reports parsed OK.

- [ ] **Step 4: Verify pre-login install is not enabled**

Run:

```bash
pytest -q tests/test_flatpak_setup_contract.py::test_prelogin_flatpak_install_is_not_enabled_by_default
```

Expected: test passes.

- [ ] **Step 5: Inspect final diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected: only intended files are modified or untracked. Do not include unrelated work.

- [ ] **Step 6: Commit final verification fix if needed**

If verification required code changes, commit only the relevant files:

```bash
git add files/usr/bin/adwaita-lite-app-setup \
        files/usr/libexec/adwaita-lite-app-setup-helper \
        files/etc/sudoers.d/adwaita-lite-app-setup \
        files/etc/xdg/labwc/autostart \
        files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service \
        build_files/build.sh \
        tests/test_flatpak_setup_contract.py \
        tests/test_post_login_flatpak_setup.py
git commit -m "fix(flatpak): complete post-login app setup verification"
```

Do not create a commit if no files changed.

---

## Manual VM Acceptance After Rebuild

- Boot a rebuilt VM.
- Confirm login appears without waiting for Flatpak installation.
- Log in and confirm the centered `Set up your apps` card appears.
- Click `Not now`, log out/in, and confirm the card returns.
- Click `Don't ask again`, log out/in, and confirm it does not return.
- With networking disabled, click `Install apps` and confirm the no-network state appears.
- With networking enabled, click `Install apps` and confirm progress appears and completion writes `/var/lib/adwaita-lite/flatpak-setup.done`.

---

## Self-Review Notes

- Spec coverage: tasks cover no pre-login blocking, centered Adwaita/ChromeOS card, install/defer/skip states, state files, helper behavior, tests, and VM acceptance.
- Placeholder scan: no placeholder markers remain; code blocks and commands are concrete.
- Type consistency: app setup script path, helper path, state stamp names, and test constants match across tasks.
