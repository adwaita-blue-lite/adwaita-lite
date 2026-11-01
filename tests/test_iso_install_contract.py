import tomllib
from pathlib import Path


ISO_CONFIG = Path(__file__).resolve().parents[1] / "disk_config/iso.toml"


def _kickstart_contents() -> str:
    data = tomllib.loads(ISO_CONFIG.read_text())
    return data["customizations"]["installer"]["kickstart"]["contents"]


def test_iso_seeds_same_zram_install_contract_as_wizard():
    kickstart = _kickstart_contents()

    assert '"memory_strategy": "zram"' in kickstart
    assert '"swap_size_gb": null' in kickstart
    assert 'chmod 0600 /var/lib/adwaita-lite/install-config.json' in kickstart


def test_iso_writes_default_flatpak_selection_explicitly():
    kickstart = _kickstart_contents()

    assert "cat > /var/lib/adwaita-lite/flatpak-apps <<'EOF'" in kickstart
    assert "com.google.Chrome" in kickstart
    assert "io.github.kolunmi.Bazaar" in kickstart
    assert "org.gtk.Gtk3theme.adw-gtk3" in kickstart
    assert "org.gtk.Gtk3theme.adw-gtk3-dark" in kickstart
