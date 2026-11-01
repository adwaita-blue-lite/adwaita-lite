"""Tests for installer disk/mount safety helpers."""

import importlib.machinery
import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import patch


_SCRIPT = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-setup-wizard"
_loader = importlib.machinery.SourceFileLoader("setup_wizard", str(_SCRIPT))
_spec = importlib.util.spec_from_loader("setup_wizard", _loader, origin=str(_SCRIPT))
setup_wizard = importlib.util.module_from_spec(_spec)
setup_wizard.__file__ = str(_SCRIPT)
_spec.loader.exec_module(setup_wizard)


class _DummyWindow:
    pass


_SWAP_UNITS = (
    "adwaita-lite-swap-init.service",
    "adwaita-lite-zswap.service",
    "adwaita-lite-encrypted-swap.service",
)


def _memory_window(tmp_path, use_zswap=True, swap_gb=4):
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._sysroot_deploy = str(tmp_path / "deploy")
    window._sysroot_var = str(tmp_path / "var")
    window._setup_use_zswap = use_zswap
    window._setup_swap_gb = swap_gb
    return window


class _FakeButton:
    def __init__(self, active=True, text=""):
        self.active = active
        self.text = text
        self.sensitive = None

    def get_active(self):
        return self.active

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text

    def set_sensitive(self, sensitive):
        self.sensitive = sensitive


class _FakeDropdown:
    def __init__(self, selected=0):
        self.selected = selected

    def get_selected(self):
        return self.selected


def test_device_tree_sources_include_child_partitions():
    def fake_run(cmd, **_kwargs):
        assert cmd == ["lsblk", "-lnpo", "NAME,TYPE", "/dev/nvme0n1"]
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout="/dev/nvme0n1 disk\n/dev/nvme0n1p1 part\n/dev/nvme0n1p2 part\n",
            stderr="",
        )

    with patch.object(setup_wizard.subprocess, "run", side_effect=fake_run):
        assert setup_wizard._device_tree_sources("/dev/nvme0n1") == [
            "/dev/nvme0n1",
            "/dev/nvme0n1p1",
            "/dev/nvme0n1p2",
        ]


def test_mounted_targets_for_sources_checks_children():
    def fake_run(cmd, **_kwargs):
        source = cmd[-1]
        stdout_by_source = {
            "/dev/sda": "",
            "/dev/sda1": "/run/media/live/EFI\n",
            "/dev/sda2": "/mnt/old-root\n/mnt/old-root/boot\n",
        }
        return subprocess.CompletedProcess(
            cmd,
            0 if stdout_by_source.get(source) else 1,
            stdout=stdout_by_source.get(source, ""),
            stderr="",
        )

    with patch.object(setup_wizard.subprocess, "run", side_effect=fake_run):
        assert setup_wizard._mounted_targets_for_sources(
            ["/dev/sda", "/dev/sda1", "/dev/sda2"]
        ) == [
            "/run/media/live/EFI",
            "/mnt/old-root",
            "/mnt/old-root/boot",
        ]


def test_mount_targets_sort_deepest_first():
    assert setup_wizard._sort_mount_targets_for_unmount([
        "/mnt/root",
        "/mnt/root/boot/efi",
        "/mnt/root/boot",
    ]) == [
        "/mnt/root/boot/efi",
        "/mnt/root/boot",
        "/mnt/root",
    ]


def test_retry_install_aborts_when_boot_remount_fails(tmp_path):
    window = _DummyWindow()
    window._mount_point = str(tmp_path)
    window._part_boot = "/dev/sda2"
    window._part_efi = "/dev/sda1"

    def fake_run_logged(cmd, **_kwargs):
        raise subprocess.CalledProcessError(32, cmd, output="mount failed")

    window._run_logged = fake_run_logged

    with patch.object(setup_wizard.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        err = setup_wizard.SetupWizardWindow._step_install_system(window)

    assert "Failed to remount" in err
    assert str(tmp_path / "boot") in err


def test_retry_install_unmounts_boot_when_efi_remount_fails(tmp_path):
    window = _DummyWindow()
    window._mount_point = str(tmp_path)
    window._part_boot = "/dev/sda2"
    window._part_efi = "/dev/sda1"

    def fake_run_logged(cmd, **_kwargs):
        if cmd[1] == "/dev/sda1":
            raise subprocess.CalledProcessError(32, cmd, output="efi mount failed")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    window._run_logged = fake_run_logged

    with patch.object(setup_wizard.subprocess, "run") as run:
        run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        err = setup_wizard.SetupWizardWindow._step_install_system(window)

    assert "Failed to remount" in err
    run.assert_any_call(
        ["umount", "-R", str(tmp_path / "boot")],
        capture_output=True,
        timeout=10,
    )


def test_configure_memory_enables_zswap_units_in_sysroot(tmp_path):
    window = _memory_window(tmp_path, use_zswap=True, swap_gb=8)

    err = setup_wizard.SetupWizardWindow._step_configure_memory(window)

    assert err is None
    deploy = Path(window._sysroot_deploy)
    var_dir = Path(window._sysroot_var)
    assert (var_dir / "lib/adwaita-lite/swap-size").read_text() == "8"
    assert (
        deploy / "etc/sysctl.d/91-adwaita-lite-zswap.conf"
    ).read_text() == "vm.swappiness = 100\n"
    assert (
        deploy / "etc/systemd/zram-generator.conf"
    ).read_text() == "[zram0]\nzram-size = 0\n"

    wants_dir = deploy / "etc/systemd/system/swap.target.wants"
    for unit in _SWAP_UNITS:
        link = wants_dir / unit
        assert link.is_symlink()
        assert os.readlink(link) == f"/usr/lib/systemd/system/{unit}"


def test_configure_memory_zram_removes_zswap_units_from_sysroot(tmp_path):
    window = _memory_window(tmp_path, use_zswap=False)
    deploy = Path(window._sysroot_deploy)
    var_dir = Path(window._sysroot_var)
    wants_dir = deploy / "etc/systemd/system/swap.target.wants"
    wants_dir.mkdir(parents=True)
    for unit in _SWAP_UNITS:
        (wants_dir / unit).symlink_to(f"/usr/lib/systemd/system/{unit}")
    (var_dir / "lib/adwaita-lite").mkdir(parents=True)
    (var_dir / "lib/adwaita-lite/swap-size").write_text("8")
    (deploy / "etc/sysctl.d").mkdir(parents=True)
    (deploy / "etc/sysctl.d/91-adwaita-lite-zswap.conf").write_text(
        "vm.swappiness = 100\n"
    )

    err = setup_wizard.SetupWizardWindow._step_configure_memory(window)

    assert err is None
    assert not (var_dir / "lib/adwaita-lite/swap-size").exists()
    assert not (deploy / "etc/sysctl.d/91-adwaita-lite-zswap.conf").exists()
    assert (
        deploy / "etc/systemd/zram-generator.conf"
    ).read_text() == (
        "[zram0]\n"
        "zram-size = min(ram * 5 / 4, 16384)\n"
        "compression-algorithm = zstd(level=3)\n"
        "swap-priority = 100\n"
    )
    for unit in _SWAP_UNITS:
        assert not (wants_dir / unit).exists()


def test_enable_rescan_clears_completed_source_id():
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._rescan_timer_id = 123
    window._rescan_button = _FakeButton()

    result = setup_wizard.SetupWizardWindow._enable_rescan(window)

    assert result == setup_wizard.GLib.SOURCE_REMOVE
    assert window._rescan_timer_id == 0
    assert window._rescan_button.sensitive is True


def test_setup_hash_failure_does_not_leave_installing_stuck(monkeypatch):
    window = setup_wizard.SetupWizardWindow.__new__(
        setup_wizard.SetupWizardWindow
    )
    window._installing = False
    window._drive_dropdown = _FakeDropdown(0)
    window._drives = [{"name": "/dev/vda"}]
    window._fs_dropdown = _FakeDropdown(0)
    window._swap_strategy_dropdown = _FakeDropdown(0)
    window._password_entry = _FakeButton(text="secret")
    window._root_password_entry = _FakeButton(text="")
    window._fullname_entry = _FakeButton(text="Jane Doe")
    window._username_entry = _FakeButton(text="jane")
    window._hostname_entry = _FakeButton(text="adwaita-lite")
    window._admin_check = _FakeButton(active=True)
    statuses = []
    window._set_status = lambda message, error=True: statuses.append((message, error))

    def fail_hash(_password):
        raise OSError("openssl missing")

    monkeypatch.setattr(setup_wizard, "_hash_password", fail_hash)

    setup_wizard.SetupWizardWindow._on_setup_clicked(window)

    assert getattr(window, "_installing", False) is False
    assert statuses
    assert "Failed to hash password" in statuses[-1][0]
