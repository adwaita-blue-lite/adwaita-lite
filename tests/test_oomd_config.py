import os
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OOMD_CONF = REPO / "files/usr/lib/systemd/oomd.conf.d/10-adwaita-lite.conf"
ROOT_SLICE_OOMD = (
    REPO / "files/usr/lib/systemd/system/-.slice.d/10-adwaita-lite-oomd.conf"
)
USER_SERVICE_OOMD = (
    REPO
    / "files/usr/lib/systemd/system/user@.service.d/10-adwaita-lite-oomd.conf"
)
CHROME_FLATPAK_SCOPE_OOMD = (
    REPO
    / "files/usr/lib/systemd/user/app-flatpak-com.google.Chrome-.scope.d/10-adwaita-lite-oomd.conf"
)
CHROME_OOM_CLEANUP_SERVICE = (
    REPO / "files/usr/lib/systemd/user/adwaita-lite-chrome-oom-cleanup.service"
)
CHROME_OOM_CLEANUP = REPO / "files/usr/libexec/adwaita-lite-chrome-oom-cleanup"
CHROME_EARLY_OOM_SERVICE = (
    REPO / "files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service"
)
BUILD_SCRIPT = REPO / "build_files/build.sh"


def test_oomd_global_thresholds_fire_before_zram_is_exhausted():
    conf = OOMD_CONF.read_text(encoding="utf-8")

    assert "SwapUsedLimit=80%" in conf
    assert "DefaultMemoryPressureLimit=55%" in conf
    assert "DefaultMemoryPressureDurationSec=25s" in conf


def test_oomd_monitors_root_slice_for_swap_exhaustion():
    conf = ROOT_SLICE_OOMD.read_text(encoding="utf-8")

    assert "[Slice]" in conf
    assert "ManagedOOMSwap=kill" in conf


def test_oomd_monitors_user_sessions_for_memory_pressure():
    conf = USER_SERVICE_OOMD.read_text(encoding="utf-8")

    assert "[Service]" in conf
    assert "ManagedOOMMemoryPressure=kill" in conf
    assert "ManagedOOMMemoryPressureLimit=55%" in conf


def test_chrome_flatpak_scope_is_killed_as_one_oom_group():
    conf = CHROME_FLATPAK_SCOPE_OOMD.read_text(encoding="utf-8")

    assert "[Unit]" in conf
    assert "OnFailure=adwaita-lite-chrome-oom-cleanup.service" in conf
    assert "[Scope]" in conf
    assert "OOMPolicy=kill" in conf


def test_chrome_oom_cleanup_service_runs_helper():
    conf = CHROME_OOM_CLEANUP_SERVICE.read_text(encoding="utf-8")

    assert "[Service]" in conf
    assert "Type=oneshot" in conf
    assert "ExecStart=/usr/libexec/adwaita-lite-chrome-oom-cleanup" in conf


def test_chrome_oom_cleanup_helper_kills_remaining_active_chrome_scopes(tmp_path):
    fake_systemctl = tmp_path / "systemctl"
    log = tmp_path / "calls.log"
    fake_systemctl.write_text(
        f"""#!/bin/sh
if [ "$1 $2" = "--user list-units" ]; then
    cat <<'EOF'
app-flatpak-com.google.Chrome-111.scope loaded failed failed app-flatpak-com.google.Chrome-111.scope
app-flatpak-com.google.Chrome-222.scope loaded active running app-flatpak-com.google.Chrome-222.scope
app-flatpak-org.mozilla.firefox-333.scope loaded active running app-flatpak-org.mozilla.firefox-333.scope
EOF
    exit 0
fi
printf '%s\\n' "$*" >> {log}
""",
        encoding="utf-8",
    )
    fake_systemctl.chmod(fake_systemctl.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{tmp_path}:{env['PATH']}"

    subprocess.run([CHROME_OOM_CLEANUP], check=True, env=env)

    assert log.read_text(encoding="utf-8") == (
        "--user kill --kill-who=all app-flatpak-com.google.Chrome-222.scope\n"
    )


def test_chrome_early_oom_service_runs_monitor():
    conf = CHROME_EARLY_OOM_SERVICE.read_text(encoding="utf-8")

    assert "[Unit]" in conf
    assert "After=multi-user.target" in conf
    assert "[Service]" in conf
    assert "ExecStart=/usr/libexec/adwaita-lite-chrome-early-oom" in conf
    assert "Restart=always" in conf
    assert "[Install]" in conf
    assert "WantedBy=multi-user.target" in conf


def test_build_enables_chrome_early_oom_service():
    build = BUILD_SCRIPT.read_text(encoding="utf-8")

    assert "systemctl enable adwaita-lite-chrome-early-oom.service" in build
