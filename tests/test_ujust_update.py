from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
UPDATE_JUST = REPO / "files/usr/share/ublue-os/just/10-update.just"


def test_ujust_update_runs_uupd_interactively_for_visible_progress():
    source = UPDATE_JUST.read_text(encoding="utf-8")

    assert "alias upgrade := update" in source
    assert "sudo uupd" in source
    assert "systemctl start" not in source
    assert "--json" not in source


def test_ujust_update_does_not_fall_back_to_legacy_split_commands():
    source = UPDATE_JUST.read_text(encoding="utf-8")

    assert "rpm-ostree update" not in source
    assert "flatpak update" not in source
    assert "distrobox upgrade" not in source
