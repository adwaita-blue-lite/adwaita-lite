import importlib.machinery
import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "files/usr/libexec/adwaita-lite-chrome-early-oom"


def load_module():
    loader = importlib.machinery.SourceFileLoader("chrome_early_oom", str(SCRIPT))
    spec = importlib.util.spec_from_loader("chrome_early_oom", loader)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["chrome_early_oom"] = module
    spec.loader.exec_module(module)
    return module


def test_parse_meminfo_returns_mib_values():
    early_oom = load_module()

    values = early_oom.parse_meminfo(
        "MemTotal:        2048000 kB\n"
        "MemAvailable:     199680 kB\n"
        "SwapTotal:       2500000 kB\n"
        "SwapFree:         307200 kB\n"
    )

    assert values == {"mem_available_mib": 195, "swap_free_mib": 300}


def test_parse_meminfo_missing_fields_is_non_triggering():
    early_oom = load_module()

    values = early_oom.parse_meminfo("MemAvailable:     102400 kB\n")

    assert values == {"mem_available_mib": 100, "swap_free_mib": None}


def test_pressure_state_requires_two_consecutive_critical_samples():
    early_oom = load_module()
    state = early_oom.PressureState(required_samples=2, cooldown_seconds=60)

    first = state.record_sample(
        mem_available_mib=150,
        swap_free_mib=250,
        now=100,
    )
    second = state.record_sample(
        mem_available_mib=140,
        swap_free_mib=240,
        now=102,
    )

    assert first is False
    assert second is True


def test_pressure_state_resets_after_recovery_and_honors_cooldown():
    early_oom = load_module()
    state = early_oom.PressureState(required_samples=2, cooldown_seconds=60)

    assert state.record_sample(150, 250, now=100) is False
    assert state.record_sample(300, 250, now=102) is False
    assert state.record_sample(150, 250, now=104) is False
    assert state.record_sample(140, 240, now=106) is True
    state.mark_triggered(now=106)

    assert state.record_sample(130, 230, now=120) is False
    assert state.record_sample(120, 220, now=168) is False
    assert state.record_sample(110, 210, now=170) is True


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:3] == ["loginctl", "list-users", "--no-legend"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="1000 hopeful\n1001 other\n",
                stderr="",
            )
        if command[:7] == [
            "systemctl",
            "--user",
            "--machine=1000@",
            "list-units",
            "app-flatpak-com.google.Chrome-*.scope",
            "--all",
            "--no-pager",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "app-flatpak-com.google.Chrome-111.scope loaded failed failed app-flatpak-com.google.Chrome-111.scope\n"
                    "app-flatpak-com.google.Chrome-222.scope loaded active running app-flatpak-com.google.Chrome-222.scope\n"
                    "app-flatpak-org.mozilla.firefox-333.scope loaded active running app-flatpak-org.mozilla.firefox-333.scope\n"
                ),
                stderr="",
            )
        if command[:7] == [
            "systemctl",
            "--user",
            "--machine=1001@",
            "list-units",
            "app-flatpak-com.google.Chrome-*.scope",
            "--all",
            "--no-pager",
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def test_list_logged_in_uids_uses_loginctl():
    early_oom = load_module()
    runner = FakeRunner()

    assert early_oom.list_logged_in_uids(runner=runner) == ["1000", "1001"]


def test_list_active_chrome_scopes_returns_only_active_chrome_units():
    early_oom = load_module()
    runner = FakeRunner()

    scopes = early_oom.list_active_chrome_scopes("1000", runner=runner)

    assert scopes == ["app-flatpak-com.google.Chrome-222.scope"]


def test_kill_chrome_scopes_targets_user_manager_units():
    early_oom = load_module()
    runner = FakeRunner()

    killed = early_oom.kill_chrome_scopes(runner=runner)

    assert killed == ["1000:app-flatpak-com.google.Chrome-222.scope"]
    assert [
        "systemctl",
        "--user",
        "--machine=1000@",
        "kill",
        "--kill-who=all",
        "app-flatpak-com.google.Chrome-222.scope",
    ] in runner.calls


def test_run_once_triggers_kill_when_pressure_state_trips():
    early_oom = load_module()
    state = early_oom.PressureState(required_samples=1, cooldown_seconds=60)
    killed_calls = []

    def fake_read_meminfo():
        return {"mem_available_mib": 150, "swap_free_mib": 250}

    def fake_kill_chrome_scopes():
        killed_calls.append(True)
        return ["1000:app-flatpak-com.google.Chrome-222.scope"]

    early_oom.run_once(
        state=state,
        read_meminfo_func=fake_read_meminfo,
        kill_chrome_scopes_func=fake_kill_chrome_scopes,
        now=100,
    )

    assert killed_calls == [True]


def test_run_once_does_not_trigger_without_swap_pressure():
    early_oom = load_module()
    state = early_oom.PressureState(required_samples=1, cooldown_seconds=60)
    killed_calls = []

    early_oom.run_once(
        state=state,
        read_meminfo_func=lambda: {"mem_available_mib": 150, "swap_free_mib": 500},
        kill_chrome_scopes_func=lambda: killed_calls.append(True),
        now=100,
    )

    assert killed_calls == []
