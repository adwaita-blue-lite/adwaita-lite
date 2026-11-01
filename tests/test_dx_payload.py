from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dx_containerfile_imports_homebrew_overlay():
    containerfile = _read("Containerfile")

    assert 'ARG BREW_IMAGE="ghcr.io/ublue-os/brew:latest"' in containerfile
    assert "FROM ${BREW_IMAGE} AS brew" in containerfile
    assert "COPY --from=brew /system_files /files" in containerfile


def test_dx_retains_distrobox_and_ujust_recipe():
    build_script = _read("build_files/build.sh")
    dx_script = _read("build_files/dx/00-dx.sh")

    assert "dnf5 remove -y distrobox" not in build_script
    assert "30-distrobox.just" not in build_script
    assert "distrobox" not in dx_script.lower()


def test_dx_installs_bluefin_dx_package_contract():
    dx_script = _read("build_files/dx/00-dx.sh")
    expected_packages = (
        "android-tools",
        "bcc",
        "bpftop",
        "bpftrace",
        "cascadia-code-fonts",
        "cockpit-bridge",
        "cockpit-machines",
        "cockpit-networkmanager",
        "cockpit-ostree",
        "cockpit-podman",
        "cockpit-selinux",
        "cockpit-storaged",
        "cockpit-system",
        "dbus-x11",
        "edk2-ovmf",
        "flatpak-builder",
        "genisoimage",
        "git-subtree",
        "git-svn",
        "iotop",
        "libvirt",
        "libvirt-nss",
        "nicstat",
        "numactl",
        "osbuild-selinux",
        "p7zip",
        "p7zip-plugins",
        "podman-compose",
        "podman-machine",
        "podman-tui",
        "qemu",
        "qemu-char-spice",
        "qemu-device-display-virtio-gpu",
        "qemu-device-display-virtio-vga",
        "qemu-device-usb-redirect",
        "qemu-img",
        "qemu-system-x86-core",
        "qemu-user-binfmt",
        "qemu-user-static",
        "sysprof",
        "incus",
        "incus-agent",
        "lxc",
        "tiptop",
        "trace-cmd",
        "udica",
        "util-linux-script",
        "virt-manager",
        "virt-v2v",
        "virt-viewer",
        "ydotool",
        "containerd.io",
        "docker-buildx-plugin",
        "docker-ce",
        "docker-ce-cli",
        "docker-compose-plugin",
        "docker-model-plugin",
        "code",
    )

    for package in expected_packages:
        assert package in dx_script


def test_dx_docker_repo_setup_is_idempotent_for_quay_rebuilds():
    dx_script = _read("build_files/dx/00-dx.sh")

    assert "if [[ ! -f /etc/yum.repos.d/docker-ce.repo ]]; then" in dx_script
    assert "dnf5 config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo" in dx_script
    assert "File \"/etc/yum.repos.d/docker-ce.repo\" already exists" not in dx_script


def test_dx_enables_bluefin_dx_services():
    dx_script = _read("build_files/dx/00-dx.sh")

    for unit in (
        "docker.socket",
        "podman.socket",
        "swtpm-workaround.service",
        "libvirt-workaround.service",
        "incus-workaround.service",
        "adwaita-lite-dx-groups.service",
    ):
        assert f"systemctl enable {unit}" in dx_script


def test_dx_image_build_validates_key_packages_and_services():
    dx_tests = _read("build_files/dx/01-tests-dx.sh")

    for package in (
        "code",
        "containerd.io",
        "docker-ce",
        "docker-buildx-plugin",
        "docker-compose-plugin",
        "flatpak-builder",
        "libvirt",
        "qemu",
    ):
        assert package in dx_tests

    assert "systemctl is-enabled" in dx_tests
    assert "docker.socket" in dx_tests
    assert "podman.socket" in dx_tests


def test_dx_files_include_user_setup_and_workarounds():
    expected_files = (
        "files/usr/bin/adwaita-lite-goblin",
        "files/usr/bin/adwaita-lite-dx-groups",
        "files/usr/lib/systemd/system/adwaita-lite-dx-groups.service",
        "files/usr/lib/systemd/system/libvirt-workaround.service",
        "files/usr/lib/systemd/system/swtpm-workaround.service",
        "files/usr/lib/systemd/system/incus-workaround.service",
        "files/usr/lib/sysctl.d/docker-ce.conf",
        "files/usr/lib/tmpfiles.d/libvirt-workaround.conf",
        "files/usr/lib/tmpfiles.d/swtpm-workaround.conf",
        "files/usr/lib/tmpfiles.d/incus-workaround.conf",
        "files/etc/skel/.config/Code/User/settings.json",
        "files/usr/share/ublue-os/user-setup.hooks.d/10-vscode.sh",
    )

    for path in expected_files:
        assert (ROOT / path).exists(), path


def test_dx_exposes_universal_blue_style_devmode_recipes():
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert "devmode:" in justfile
    assert "toggle-devmode:" in justfile
    assert "dx-group:" in justfile
    assert "@ujust toggle-devmode" in justfile
    assert "gum confirm \"Would you like to enable developer mode?\"" in justfile
    assert "gum confirm \"Would you like to disable developer mode?\"" in justfile
    assert "pkexec bootc switch --enforce-container-sigpolicy" in justfile
    assert "ujust dx-group" in justfile


def test_dx_regenerates_current_ublue_ujust_entrypoint():
    build_script = _read("build_files/build.sh")

    assert "/usr/share/ublue-os/just/00-entry.just" in build_script
    assert "find /usr/share/ublue-os/just" in build_script
    assert "! -name '60-custom.just'" in build_script
    assert "import \"/usr/share/ublue-os/just/%s\"" in build_script


def test_dx_includes_goblin_mode_easter_egg():
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert (ROOT / "files/usr/bin/adwaita-lite-goblin").exists()
    assert "goblin:" in justfile
    assert "/usr/bin/adwaita-lite-goblin" in justfile


def test_dx_devmode_uses_adwaita_lite_stream_tags_not_upstream_image_suffix():
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert "ghcr.io/adwaita-blue-lite/adwaita-lite:dx" in justfile
    assert "ghcr.io/adwaita-blue-lite/adwaita-lite:latest" in justfile
    assert "quay.io/" not in justfile
    assert "pkexec bootc switch --enforce-container-sigpolicy" in justfile
    assert "ostree-image-signed:docker://" not in justfile
    assert "rpm-ostree rebase" not in justfile
    assert 'sed "s/$IMAGE_BASE_NAME/$IMAGE_BASE_NAME-dx/"' not in justfile
    assert 'sed "s/\\-dx//"' not in justfile
