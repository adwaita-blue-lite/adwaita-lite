# Chrome Early-OOM Safety Valve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Adwaita-Lite early-OOM monitor that proactively closes Chrome Flatpak scopes before low-memory pressure leaves the desktop wedged.

**Architecture:** Implement a small Python system daemon with testable pure functions for meminfo parsing, threshold state, user discovery, and Chrome scope cleanup. The daemon reads `/proc/meminfo` every 2 seconds, requires two consecutive critical samples, kills active Chrome Flatpak scopes through each user's systemd user manager, then enters a 60 second cooldown. Existing `systemd-oomd` and Chrome `OnFailure=` cleanup remain as fallback, with OOMD relaxed to `80%` swap and `55%/25s` memory pressure because Chrome now has a targeted earlier safety valve.

**Tech Stack:** Python 3 standard library, systemd system service, pytest, existing file overlay under `files/`, image build enablement in `build_files/build.sh`.

---

## File Structure

- Create: `files/usr/libexec/adwaita-lite-chrome-early-oom`
  - Python daemon and reusable functions.
  - Owns `/proc/meminfo` parsing, threshold decision, logged-in user enumeration, user-manager command construction, Chrome scope listing, scope killing, loop/cooldown behavior, and logging.
- Create: `files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service`
  - System service that starts the daemon at boot.
- Modify: `build_files/build.sh`
  - Enable `adwaita-lite-chrome-early-oom.service` near existing `systemd-oomd.service` enablement.
- Modify: `files/usr/lib/systemd/oomd.conf.d/10-adwaita-lite.conf`
  - Keep `SwapUsedLimit=80%` and relax fallback pressure from `50%/20s` to `55%/25s`.
- Modify: `files/usr/lib/systemd/system/user@.service.d/10-adwaita-lite-oomd.conf`
  - Keep the user-session `ManagedOOMMemoryPressure=kill` opt-in and align its explicit pressure limit to `55%`.
- Modify: `tests/test_oomd_config.py`
  - Add config tests for service installation, build enablement, and relaxed OOMD fallback thresholds, including the explicit user-session limit.
- Create: `tests/test_chrome_early_oom.py`
  - Unit tests for parsing, trigger/cooldown behavior, command generation, and Chrome scope cleanup behavior.
- Keep: `files/usr/lib/systemd/user/app-flatpak-com.google.Chrome-.scope.d/10-adwaita-lite-oomd.conf`
  - No removal. Its `OOMPolicy=kill` and `OnFailure=` fallback remain defense-in-depth.

---

### Task 1: Meminfo Parsing And Trigger State

**Files:**
- Create: `tests/test_chrome_early_oom.py`
- Create: `files/usr/libexec/adwaita-lite-chrome-early-oom`

- [ ] **Step 1: Write failing tests for meminfo parsing and trigger state**

Add `tests/test_chrome_early_oom.py`:

```python
import importlib.machinery
import importlib.util
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_early_oom.py -v`

Expected: FAIL because `files/usr/libexec/adwaita-lite-chrome-early-oom` does not exist.

- [ ] **Step 3: Implement minimal parser and state logic**

Create `files/usr/libexec/adwaita-lite-chrome-early-oom`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


MEM_AVAILABLE_THRESHOLD_MIB = 200
SWAP_FREE_THRESHOLD_MIB = 300
SAMPLE_INTERVAL_SECONDS = 2
REQUIRED_CRITICAL_SAMPLES = 2
COOLDOWN_SECONDS = 60
CHROME_SCOPE_PATTERN = "app-flatpak-com.google.Chrome-*.scope"


def parse_meminfo(text: str) -> dict[str, int | None]:
    values: dict[str, int | None] = {
        "mem_available_mib": None,
        "swap_free_mib": None,
    }
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        if fields[0] == "MemAvailable:":
            values["mem_available_mib"] = int(fields[1]) // 1024
        elif fields[0] == "SwapFree:":
            values["swap_free_mib"] = int(fields[1]) // 1024
    return values


def read_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int | None]:
    return parse_meminfo(path.read_text(encoding="utf-8"))


@dataclass
class PressureState:
    required_samples: int = REQUIRED_CRITICAL_SAMPLES
    cooldown_seconds: int = COOLDOWN_SECONDS
    critical_samples: int = 0
    last_triggered_at: float | None = None

    def record_sample(
        self,
        mem_available_mib: int | None,
        swap_free_mib: int | None,
        now: float,
    ) -> bool:
        if self.last_triggered_at is not None:
            if now - self.last_triggered_at < self.cooldown_seconds:
                return False

        critical = (
            mem_available_mib is not None
            and swap_free_mib is not None
            and mem_available_mib < MEM_AVAILABLE_THRESHOLD_MIB
            and swap_free_mib < SWAP_FREE_THRESHOLD_MIB
        )
        if not critical:
            self.critical_samples = 0
            return False

        self.critical_samples += 1
        return self.critical_samples >= self.required_samples

    def mark_triggered(self, now: float) -> None:
        self.last_triggered_at = now
        self.critical_samples = 0
```

- [ ] **Step 4: Make script executable**

Run: `chmod +x files/usr/libexec/adwaita-lite-chrome-early-oom`

Expected: no output.

- [ ] **Step 5: Run tests to verify parser/state pass**

Run: `pytest tests/test_chrome_early_oom.py -v`

Expected: PASS for the four tests in this file.

- [ ] **Step 6: Commit Task 1**

Run:

```bash
git add tests/test_chrome_early_oom.py files/usr/libexec/adwaita-lite-chrome-early-oom
git commit -m "feat(oom): add Chrome early pressure state"
```

Expected: commit succeeds.

---

### Task 2: User Scope Enumeration And Chrome Kill Commands

**Files:**
- Modify: `tests/test_chrome_early_oom.py`
- Modify: `files/usr/libexec/adwaita-lite-chrome-early-oom`

- [ ] **Step 1: Write failing tests for systemd user-manager interactions**

Append to `tests/test_chrome_early_oom.py`:

```python
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
```

Also add this import near the top of the test file:

```python
import subprocess
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_early_oom.py -v`

Expected: FAIL with missing `list_logged_in_uids`, `list_active_chrome_scopes`, or `kill_chrome_scopes` attributes.

- [ ] **Step 3: Add user and Chrome scope functions**

Append to `files/usr/libexec/adwaita-lite-chrome-early-oom`:

```python
def run_command(command: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, **kwargs)


def list_logged_in_uids(runner=run_command) -> list[str]:
    result = runner(["loginctl", "list-users", "--no-legend"])
    if result.returncode != 0:
        logging.warning("failed to list logged-in users: %s", result.stderr.strip())
        return []

    uids: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if fields and fields[0].isdigit():
            uids.append(fields[0])
    return uids


def user_systemctl(uid: str, *args: str) -> list[str]:
    return ["systemctl", "--user", f"--machine={uid}@", *args]


def list_active_chrome_scopes(uid: str, runner=run_command) -> list[str]:
    result = runner(
        user_systemctl(
            uid,
            "list-units",
            CHROME_SCOPE_PATTERN,
            "--all",
            "--no-pager",
            "--plain",
            "--full",
            "--no-legend",
        )
    )
    if result.returncode != 0:
        logging.warning(
            "failed to list Chrome scopes for uid %s: %s",
            uid,
            result.stderr.strip(),
        )
        return []

    scopes: list[str] = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        unit = fields[0]
        active = fields[2]
        if not unit.startswith("app-flatpak-com.google.Chrome-"):
            continue
        if not unit.endswith(".scope"):
            continue
        if active in {"active", "activating"}:
            scopes.append(unit)
    return scopes


def kill_chrome_scopes(runner=run_command) -> list[str]:
    killed: list[str] = []
    for uid in list_logged_in_uids(runner=runner):
        for scope in list_active_chrome_scopes(uid, runner=runner):
            result = runner(
                user_systemctl(uid, "kill", "--kill-who=all", scope)
            )
            if result.returncode == 0:
                logging.warning("killed Chrome scope uid=%s unit=%s", uid, scope)
                killed.append(f"{uid}:{scope}")
            else:
                logging.warning(
                    "failed to kill Chrome scope uid=%s unit=%s: %s",
                    uid,
                    scope,
                    result.stderr.strip(),
                )
    return killed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_chrome_early_oom.py -v`

Expected: PASS for all tests in this file.

- [ ] **Step 5: Commit Task 2**

Run:

```bash
git add tests/test_chrome_early_oom.py files/usr/libexec/adwaita-lite-chrome-early-oom
git commit -m "feat(oom): kill Chrome Flatpak scopes early"
```

Expected: commit succeeds.

---

### Task 3: Daemon Loop And Systemd Service

**Files:**
- Modify: `tests/test_chrome_early_oom.py`
- Modify: `files/usr/libexec/adwaita-lite-chrome-early-oom`
- Create: `files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service`
- Modify: `tests/test_oomd_config.py`

- [ ] **Step 1: Write failing tests for service file and daemon wiring**

Append to `tests/test_chrome_early_oom.py`:

```python
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
```

Append to `tests/test_oomd_config.py`:

```python
CHROME_EARLY_OOM_SERVICE = (
    REPO / "files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service"
)
BUILD_SCRIPT = REPO / "build_files/build.sh"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_chrome_early_oom.py tests/test_oomd_config.py -v`

Expected: FAIL because `run_once` and the service/build enablement do not exist.

- [ ] **Step 3: Add daemon loop functions**

Append to `files/usr/libexec/adwaita-lite-chrome-early-oom`:

```python
def run_once(
    state: PressureState,
    read_meminfo_func=read_meminfo,
    kill_chrome_scopes_func=kill_chrome_scopes,
    now: float | None = None,
) -> bool:
    now = time.monotonic() if now is None else now
    meminfo = read_meminfo_func()
    mem_available_mib = meminfo.get("mem_available_mib")
    swap_free_mib = meminfo.get("swap_free_mib")

    if state.record_sample(mem_available_mib, swap_free_mib, now=now):
        logging.warning(
            "critical memory pressure: MemAvailable=%s MiB SwapFree=%s MiB; closing Chrome",
            mem_available_mib,
            swap_free_mib,
        )
        killed = kill_chrome_scopes_func()
        if killed:
            state.mark_triggered(now=now)
            return True
        logging.warning("critical memory pressure but no active Chrome Flatpak scopes were found")
    return False


def run_loop() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    state = PressureState()
    while True:
        try:
            run_once(state)
        except Exception:
            logging.exception("Chrome early-OOM monitor iteration failed")
        time.sleep(SAMPLE_INTERVAL_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Close Chrome Flatpak scopes before extreme memory pressure wedges the desktop."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one sample and exit; intended for diagnostics.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if args.once:
        run_once(PressureState(required_samples=1))
        return 0
    run_loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Add systemd service**

Create `files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service`:

```ini
[Unit]
Description=Adwaita-Lite Chrome early-OOM safety valve
Documentation=file:/usr/share/doc/adwaita-lite/chrome-early-oom.md
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/libexec/adwaita-lite-chrome-early-oom
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Enable service in image build**

Modify `build_files/build.sh` near the existing OOMD enablement block to become:

```sh
# OOM protection on 2 GB hardware — oomd kills the heaviest cgroup under
# memory/swap pressure before the kernel OOM killer engages and freezes
# the whole machine. Chrome gets an earlier safety valve because Flatpak
# Chrome can keep a sibling app scope alive after oomd kills one scope.
systemctl enable systemd-oomd.service
systemctl enable adwaita-lite-chrome-early-oom.service
```

- [ ] **Step 6: Run tests and shell syntax check**

Run: `pytest tests/test_chrome_early_oom.py tests/test_oomd_config.py -v`

Expected: PASS.

Run: `python -m py_compile files/usr/libexec/adwaita-lite-chrome-early-oom`

Expected: no output.

- [ ] **Step 7: Commit Task 3**

Run:

```bash
git add files/usr/libexec/adwaita-lite-chrome-early-oom files/usr/lib/systemd/system/adwaita-lite-chrome-early-oom.service build_files/build.sh tests/test_chrome_early_oom.py tests/test_oomd_config.py
git commit -m "feat(oom): enable Chrome early-OOM monitor"
```

Expected: commit succeeds.

---

### Task 4: Relax OOMD Fallback Thresholds

**Files:**
- Modify: `tests/test_oomd_config.py`
- Modify: `files/usr/lib/systemd/oomd.conf.d/10-adwaita-lite.conf`

- [ ] **Step 1: Write failing test for relaxed OOMD fallback thresholds**

Modify `tests/test_oomd_config.py::test_oomd_global_thresholds_fire_before_zram_is_exhausted` to assert the new fallback thresholds:

```python
def test_oomd_global_thresholds_fire_before_zram_is_exhausted():
    conf = OOMD_CONF.read_text(encoding="utf-8")

    assert "SwapUsedLimit=80%" in conf
    assert "DefaultMemoryPressureLimit=55%" in conf
    assert "DefaultMemoryPressureDurationSec=25s" in conf
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_oomd_config.py::test_oomd_global_thresholds_fire_before_zram_is_exhausted -v`

Expected: FAIL because the config still contains `DefaultMemoryPressureLimit=50%` and `DefaultMemoryPressureDurationSec=20s`.

- [ ] **Step 3: Update OOMD config comments and thresholds**

Modify `files/usr/lib/systemd/oomd.conf.d/10-adwaita-lite.conf` to:

```ini
# systemd-oomd tuning for 2 GB hardware.
#
# Keep swap protection earlier than Fedora's upstream 90% default because
# zram-only systems can become unresponsive near exhaustion. Memory pressure
# is slightly less aggressive than Adwaita-Lite's original 50%/20s policy
# because Chrome now has a targeted early-OOM safety valve before this broad
# fallback needs to kill non-Chrome workloads.
[OOM]
SwapUsedLimit=80%
DefaultMemoryPressureLimit=55%
DefaultMemoryPressureDurationSec=25s
```

- [ ] **Step 4: Run OOMD config tests**

Run: `pytest tests/test_oomd_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```bash
git add files/usr/lib/systemd/oomd.conf.d/10-adwaita-lite.conf tests/test_oomd_config.py
git commit -m "fix(oomd): relax fallback memory pressure"
```

Expected: commit succeeds.

---

### Task 5: Full Regression Verification And VM Smoke Instructions

**Files:**
- Modify: `docs/superpowers/specs/2026-05-16-chrome-early-oom-design.md` only if implementation discovers a necessary spec correction.
- No production code changes unless verification exposes a real defect.

- [ ] **Step 1: Run low-memory regression suite**

Run:

```bash
pytest tests/test_chrome_early_oom.py tests/test_oomd_config.py tests/test_swap_helpers.py tests/test_iso_install_contract.py tests/test_installer_mount_handling.py
```

Expected: all tests pass.

- [ ] **Step 2: Verify executable and service file are present in diff**

Run: `git status --short`

Expected: clean if prior tasks committed; otherwise only intended plan/spec changes remain.

Run: `git log -3 --oneline`

Expected: the four task commits are visible.

- [ ] **Step 3: Document VM smoke test commands in final handoff**

Use these commands on a built VM after installing the image:

```bash
systemctl status adwaita-lite-chrome-early-oom.service --no-pager
journalctl -b -u adwaita-lite-chrome-early-oom.service --no-pager
/usr/libexec/adwaita-lite-chrome-early-oom --once
```

Expected service status: active/running.

Expected journal before pressure: no repeated tracebacks.

Expected under reproduced Chrome pressure: journal contains a line like `critical memory pressure` followed by killed `app-flatpak-com.google.Chrome-*.scope` units, and the desktop remains responsive.

Use these commands to confirm the relaxed OOMD fallback thresholds on the VM:

```bash
grep -R 'SwapUsedLimit\|DefaultMemoryPressure' /usr/lib/systemd/oomd.conf.d /etc/systemd/oomd.conf.d 2>/dev/null
grep -R 'ManagedOOMMemoryPressureLimit' /usr/lib/systemd/system/user@.service.d /etc/systemd/system/user@.service.d 2>/dev/null
```

Expected: `SwapUsedLimit=80%`, `DefaultMemoryPressureLimit=55%`, `ManagedOOMMemoryPressureLimit=55%`, and `DefaultMemoryPressureDurationSec=25s` are present from Adwaita-Lite's config.

- [ ] **Step 4: Commit any verification-only documentation correction if needed**

If the VM smoke test requires a spec correction, run:

```bash
git add docs/superpowers/specs/2026-05-16-chrome-early-oom-design.md
git commit -m "docs(oom): update Chrome early-OOM design notes"
```

Expected: commit succeeds only if the spec changed.
