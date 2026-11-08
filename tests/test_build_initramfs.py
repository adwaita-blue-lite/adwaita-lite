"""Contract tests for the image initramfs build.

A bootc image without the ``ostree`` and ``bootc`` dracut modules cannot
assemble its deployment and fails at ``initrd-switch-root``. The build script
must install the bootc drop-in, fail on a dracut error, and verify the
resulting initramfs before the image is published.
"""

from pathlib import Path

BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "build_files/build.sh"


def _script() -> str:
    return BUILD_SCRIPT.read_text(encoding="utf-8")


def test_bootc_dracut_dropin_is_installed_from_the_package():
    script = _script()

    assert "10-bootc-base.conf" in script
    assert "/usr/share/doc/bootc/baseimage/dracut" in script
    assert 'add_dracutmodules+=" ostree bootc "' in script


def test_dracut_failure_is_not_masked():
    script = _script()

    assert 'initramfs.img" || true' not in script
    assert 'if ! dracut --force --no-hostonly --add "ostree bootc"' in script
    assert "refusing to publish an unbootable image" in script


def test_initramfs_is_checked_for_bootc_and_ostree_helpers():
    script = _script()

    assert "for helper in ostree-prepare-root bootc-root-setup" in script
    assert 'lsinitrd "$initramfs"' in script
