import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files/usr/lib/adwaita-lite"))
from settings import wallpapers


def _reset_cache():
    wallpapers._LIST_CACHE = None
    wallpapers._LIST_CACHE_KEY = None


def test_cache_returns_same_object_on_second_call(monkeypatch, tmp_path):
    d = tmp_path / "gbp"
    d.mkdir()
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", tmp_path / "user")
    _reset_cache()

    first = wallpapers.list_wallpapers()
    second = wallpapers.list_wallpapers()
    assert first is second  # same object → cache hit


def test_cache_invalidates_when_system_dir_mtime_changes(monkeypatch, tmp_path):
    d = tmp_path / "gbp"
    d.mkdir()
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", tmp_path / "user")
    _reset_cache()

    first = wallpapers.list_wallpapers()
    # Touch the directory mtime forward by adding a file.
    # mtime_ns resolution is ns-level on ext4/btrfs so no sleep needed,
    # but give the filesystem one tick of slack on slower mounts.
    time.sleep(0.01)
    (d / "new.xml").write_text("<wallpapers/>")
    second = wallpapers.list_wallpapers()
    assert first is not second  # cache key changed → fresh compute


def test_cache_invalidates_when_user_dir_mtime_changes(monkeypatch, tmp_path):
    sys_d = tmp_path / "gbp"
    sys_d.mkdir()
    user_d = tmp_path / "user"
    user_d.mkdir()
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (sys_d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", user_d)
    _reset_cache()

    first = wallpapers.list_wallpapers()
    time.sleep(0.01)
    (user_d / "custom.xml").write_text("<wallpapers/>")
    second = wallpapers.list_wallpapers()
    assert first is not second


def test_cache_survives_missing_user_dir(monkeypatch, tmp_path):
    sys_d = tmp_path / "gbp"
    sys_d.mkdir()
    # USER_MANIFEST_DIR does NOT exist — _cache_key must still return
    # a key rather than raising; list_wallpapers must skip the user dir
    # per its existing is_dir() guard.
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (sys_d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", tmp_path / "nope")
    _reset_cache()

    first = wallpapers.list_wallpapers()
    second = wallpapers.list_wallpapers()
    assert first is second


def test_fedora_default_alias_tracks_newest_release_manifest(monkeypatch, tmp_path):
    d = tmp_path / "gbp"
    d.mkdir()
    for release in (42, 43):
        light = tmp_path / f"f{release}-day.svg"
        dark = tmp_path / f"f{release}-night.svg"
        light.write_text("<svg/>")
        dark.write_text("<svg/>")
        (d / f"f{release}.xml").write_text(
            f"""<?xml version="1.0"?>
<wallpapers>
  <wallpaper deleted="false">
    <name>Fedora {release} Default</name>
    <filename>{light}</filename>
    <filename-dark>{dark}</filename-dark>
  </wallpaper>
</wallpapers>
""",
            encoding="utf-8",
        )
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", tmp_path / "user")
    _reset_cache()

    wp = wallpapers.get_wallpaper("fedora-default")

    assert wp is not None
    assert wp.id == "f43"
    assert wallpapers.resolve_for_theme("fedora-default", "dark").endswith("f43-night.svg")


def test_wallpaper_manifest_keeps_modern_image_formats_for_external_previews(
    monkeypatch, tmp_path
):
    d = tmp_path / "gbp"
    d.mkdir()
    light = tmp_path / "photo.avif"
    dark = tmp_path / "photo-dark.heic"
    light.write_bytes(b"")
    dark.write_bytes(b"")
    (d / "modern.xml").write_text(
        f"""<?xml version="1.0"?>
<wallpapers>
  <wallpaper deleted="false">
    <name>Modern Photo</name>
    <filename>{light}</filename>
    <filename-dark>{dark}</filename-dark>
  </wallpaper>
</wallpapers>
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(wallpapers, "SYSTEM_MANIFEST_DIRS", (d,))
    monkeypatch.setattr(wallpapers, "USER_MANIFEST_DIR", tmp_path / "user")
    _reset_cache()

    listed = wallpapers.list_wallpapers()

    assert len(listed) == 1
    assert listed[0].light_path == str(light)
    assert listed[0].dark_path == str(dark)
