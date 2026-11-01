from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FLATPAK_SETUP = ROOT / "files/usr/libexec/adwaita-lite-flatpak-setup"
FLATPAK_SKIP_HELPER = ROOT / "files/usr/libexec/adwaita-lite-flatpak-skip"
FLATPAK_INSTALL_SERVICE = (
    ROOT / "files/usr/lib/systemd/system/adwaita-lite-flatpak-install.service"
)
FLATPAK_SKIP_SUDOERS = ROOT / "files/etc/sudoers.d/adwaita-lite-flatpak-skip"
BUILD_SCRIPT = ROOT / "build_files/build.sh"
SKIP_MARKER = "/var/lib/adwaita-lite/flatpak-setup.skip"
SKIP_HELPER = "/usr/libexec/adwaita-lite-flatpak-skip"


def test_initial_install_completion_checks_apps_and_runtimes():
    script = FLATPAK_SETUP.read_text()

    assert "flatpak list --system --columns=application" in script
    assert "flatpak list --system --app --columns=application" not in script


def test_flatpak_install_service_is_gated_by_skip_marker():
    service = FLATPAK_INSTALL_SERVICE.read_text()

    assert f"ConditionPathExists=!{SKIP_MARKER}" in service


def test_flatpak_setup_script_honors_skip_marker_before_network_work():
    script = FLATPAK_SETUP.read_text()
    skip_definition = f"SKIP_STAMP={SKIP_MARKER}"
    skip_check = 'if [ -f "$SKIP_STAMP" ]; then'

    assert skip_definition in script
    assert skip_check in script
    assert script.index(skip_check) < script.index("if [ -f \"$STAMP\" ]; then")


def test_flatpak_skip_helper_and_sudoers_contract():
    helper = FLATPAK_SKIP_HELPER.read_text()
    sudoers = FLATPAK_SKIP_SUDOERS.read_text()
    build = BUILD_SCRIPT.read_text()

    assert helper.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in helper
    assert "mkdir -p /var/lib/adwaita-lite" in helper
    assert f": > {SKIP_MARKER}" in helper
    assert f"chmod 0644 {SKIP_MARKER}" in helper
    assert "systemctl stop adwaita-lite-flatpak-install.service" in helper
    assert f"greetd ALL=(root) NOPASSWD: {SKIP_HELPER}" in sudoers
    assert SKIP_HELPER in build


def test_flatpak_setup_rechecks_skip_marker_after_startup():
    script = FLATPAK_SETUP.read_text()

    assert "skip_requested()" in script
    assert script.count("skip_requested") >= 5
    assert script.index("skip_requested") < script.index("wait_for_network")
    assert script.index("skip_requested \"before waiting for network\"") < script.index(
        "if ! wait_for_network; then"
    )
    assert script.index("skip_requested \"after waiting for network\"") < script.index(
        "echo \"Network connected.\""
    )
    assert script.index("skip_requested \"before configuring Flathub\"") < script.index(
        "flatpak remote-add"
    )
    assert script.index("skip_requested \"before installing $app_id\"") < script.index(
        "flatpak install --or-update"
    )
    assert script.index("skip_requested \"after installing $app_id\"") > script.index(
        "flatpak install --or-update"
    )


def test_flatpak_setup_rechecks_skip_marker_before_done_stamp():
    script = FLATPAK_SETUP.read_text()
    stamp_positions = [
        index for index in range(len(script)) if script.startswith('touch "$STAMP"', index)
    ]

    assert len(stamp_positions) == 2
    for stamp_position in stamp_positions:
        preceding_block = script[max(0, stamp_position - 200) : stamp_position]
        assert "skip_requested" in preceding_block


def test_flatpak_setup_recovery_copy_uses_flatpak_only():
    script = FLATPAK_SETUP.read_text()

    assert "Bazaar or flatpak CLI" not in script


APP_SETUP = ROOT / "files/usr/bin/adwaita-lite-app-setup"
APP_SETUP_HELPER = ROOT / "files/usr/libexec/adwaita-lite-app-setup-helper"
APP_SETUP_SUDOERS = ROOT / "files/etc/sudoers.d/adwaita-lite-app-setup"
LABWC_AUTOSTART = ROOT / "files/etc/xdg/labwc/autostart"
APP_SETUP_PATH = "/usr/bin/adwaita-lite-app-setup"
APP_SETUP_HELPER_PATH = "/usr/libexec/adwaita-lite-app-setup-helper"


def build_chmod_0755_block(build):
    lines = build.splitlines()
    start = lines.index("chmod 0755 \\")
    block = []
    for line in lines[start:]:
        block.append(line)
        if not line.rstrip().endswith("\\"):
            break
    return "\n".join(block)


def guarded_chmod_line(path):
    return f"[ -e {path} ] && chmod 0755 {path}"


def test_prelogin_flatpak_install_is_not_enabled_by_default():
    service = FLATPAK_INSTALL_SERVICE.read_text()
    build = BUILD_SCRIPT.read_text()

    assert "WantedBy=graphical.target" not in service
    assert "systemctl enable adwaita-lite-flatpak-install.service" not in build
    assert "systemctl mask adwaita-lite-flatpak-install.service" in build


def test_legacy_flatpak_installer_has_no_greeter_coordination():
    service = FLATPAK_INSTALL_SERVICE.read_text()
    script = FLATPAK_SETUP.read_text()
    combined = service + script

    assert "greeter" not in combined.lower()
    assert "flatpak-login-ready" not in combined
    assert "Finishing setup" not in combined
    assert "write_progress" not in combined


def test_post_login_app_setup_is_autostarted_and_executable():
    autostart = LABWC_AUTOSTART.read_text()
    build = BUILD_SCRIPT.read_text()

    assert APP_SETUP_PATH in autostart
    assert f"[ -x {APP_SETUP_PATH} ] && {APP_SETUP_PATH}" in autostart
    assert guarded_chmod_line(APP_SETUP_PATH) in build
    assert APP_SETUP.exists()
    if APP_SETUP.exists():
        assert APP_SETUP.stat().st_mode & 0o111


def test_post_login_app_setup_helper_and_sudoers_contract():
    build = BUILD_SCRIPT.read_text()

    assert guarded_chmod_line(APP_SETUP_HELPER_PATH) in build

    helper = APP_SETUP_HELPER.read_text()
    sudoers = APP_SETUP_SUDOERS.read_text()

    assert helper.startswith("#!/bin/bash\n")
    assert "set -euo pipefail" in helper
    assert "install)" in helper
    assert "skip)" in helper
    assert "status)" in helper
    assert "/var/lib/adwaita-lite/flatpak-apps" in helper
    assert "/var/lib/adwaita-lite/flatpak-setup.done" in helper
    assert "/var/lib/adwaita-lite/flatpak-setup.skip" in helper
    assert "if ! ensure_flathub" in helper
    assert 'echo "ERROR flathub"' in helper
    assert "flatpak install --or-update --system --noninteractive" in helper
    assert (
        "%wheel ALL=(root) NOPASSWD: "
        "/usr/libexec/adwaita-lite-app-setup-helper install, "
        "/usr/libexec/adwaita-lite-app-setup-helper skip, "
        "/usr/libexec/adwaita-lite-app-setup-helper status, "
        "/usr/libexec/adwaita-lite-app-setup-helper count"
    ) in sudoers
    assert "ALL ALL=(root) NOPASSWD: /usr/libexec/adwaita-lite-app-setup-helper" not in sudoers
    assert "/usr/libexec/adwaita-lite-app-setup-helper\n" not in sudoers
