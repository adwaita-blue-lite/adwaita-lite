"""Filesystem contract: ext4 is the only supported root filesystem."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_bootc_install_config_declares_ext4():
    install = _read("files/usr/lib/bootc/install/00-adwaita-lite.toml")

    assert 'type = "ext4"' in install


def test_justfile_does_not_override_the_image_filesystem():
    justfile = _read("Justfile")

    assert "--rootfs=btrfs" not in justfile
    assert "--rootfs=xfs" not in justfile


def test_wizard_offers_only_ext4():
    wizard = _read("files/usr/bin/adwaita-lite-setup-wizard")

    assert 'FILESYSTEMS = ["ext4"]' in wizard
    assert "mkfs.btrfs" not in wizard
    assert "mkfs.xfs" not in wizard
    assert "self._fs_dropdown.set_sensitive(False)" in wizard


def test_swap_init_is_filesystem_agnostic():
    swap_init = _read("files/usr/libexec/adwaita-lite-swap-init")

    assert "chattr +C" not in swap_init
    assert "btrfs" not in swap_init.lower()
