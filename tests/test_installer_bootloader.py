"""Tests for the installer's target-bootloader fallback."""

import importlib.machinery
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "files/usr/bin/adwaita-lite-setup-wizard"
_loader = importlib.machinery.SourceFileLoader("setup_wizard", str(_SCRIPT))
_spec = importlib.util.spec_from_loader("setup_wizard", _loader, origin=str(_SCRIPT))
setup_wizard = importlib.util.module_from_spec(_spec)
setup_wizard.__file__ = str(_SCRIPT)
_spec.loader.exec_module(setup_wizard)


def _make_target(root: Path) -> tuple[Path, Path]:
    boot = root / "boot"
    esp = boot / "efi"
    (boot / "grub2").mkdir(parents=True)
    (boot / "grub2" / "grub.cfg").write_text("blscfg\n", encoding="utf-8")
    (esp / "EFI" / "fedora").mkdir(parents=True)
    (esp / "EFI" / "fedora" / "grubx64.efi").write_bytes(b"grub")
    (esp / "EFI" / "BOOT").mkdir(parents=True)
    (esp / "EFI" / "BOOT" / "BOOTX64.EFI").write_bytes(b"fallback")
    return boot, esp


def test_bootuuid_config_uses_the_target_boot_uuid():
    assert (
        setup_wizard._bootuuid_config("eb060a87-4a4a-4a92-b212-88aab8e10ed1")
        == 'set BOOT_UUID="eb060a87-4a4a-4a92-b212-88aab8e10ed1"\n'
    )


def test_bootloader_missing_accepts_a_complete_target(tmp_path):
    boot, esp = _make_target(tmp_path)
    assert setup_wizard._bootloader_missing(boot, esp) == []


def test_bootloader_missing_reports_the_uefi_fallback(tmp_path):
    boot, esp = _make_target(tmp_path)
    (esp / "EFI" / "BOOT" / "BOOTX64.EFI").unlink()

    assert setup_wizard._bootloader_missing(boot, esp) == [
        str(esp / "EFI" / "BOOT" / "BOOTX64.EFI")
    ]


def test_installer_runs_the_bootloader_fallback_and_fails_closed():
    script = _SCRIPT.read_text(encoding="utf-8")

    assert "bootloader_error = self._ensure_target_bootloader()" in script
    assert "Target bootloader is incomplete" in script
    assert "WARNING: expected {grub_efi}" not in script
