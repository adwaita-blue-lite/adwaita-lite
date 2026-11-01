#!/usr/bin/bash

echo "::group:: ===$(basename "$0")==="

set -ouex pipefail

FEDORA_PACKAGES=(
    android-tools
    bcc
    bpftop
    bpftrace
    cascadia-code-fonts
    cockpit-bridge
    cockpit-machines
    cockpit-networkmanager
    cockpit-ostree
    cockpit-podman
    cockpit-selinux
    cockpit-storaged
    cockpit-system
    dbus-x11
    edk2-ovmf
    flatpak-builder
    genisoimage
    git-subtree
    git-svn
    iotop
    libvirt
    libvirt-nss
    nicstat
    numactl
    osbuild-selinux
    p7zip
    p7zip-plugins
    podman-compose
    podman-machine
    podman-tui
    qemu
    qemu-char-spice
    qemu-device-display-virtio-gpu
    qemu-device-display-virtio-vga
    qemu-device-usb-redirect
    qemu-img
    qemu-system-x86-core
    qemu-user-binfmt
    qemu-user-static
    sysprof
    incus
    incus-agent
    lxc
    tiptop
    trace-cmd
    udica
    util-linux-script
    virt-manager
    virt-v2v
    virt-viewer
    ydotool
)

dnf5 -y install --setopt=install_weak_deps=False "${FEDORA_PACKAGES[@]}"

if [[ ! "${IMAGE_NAME:-}" =~ nvidia ]]; then
    dnf5 -y install --setopt=install_weak_deps=False \
        rocm-hip \
        rocm-opencl \
        rocm-smi
fi

if [[ ! -f /etc/yum.repos.d/docker-ce.repo ]]; then
    dnf5 config-manager addrepo --from-repofile=https://download.docker.com/linux/fedora/docker-ce.repo
fi
sed -i "s/enabled=.*/enabled=0/g" /etc/yum.repos.d/docker-ce.repo
dnf5 -y install --setopt=install_weak_deps=False --enablerepo=docker-ce-stable \
    containerd.io \
    docker-buildx-plugin \
    docker-ce \
    docker-ce-cli \
    docker-compose-plugin \
    docker-model-plugin

cat > /etc/yum.repos.d/vscode.repo <<'EOF'
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
gpgcheck=1
gpgkey=https://packages.microsoft.com/keys/microsoft.asc
EOF
sed -i "s/enabled=.*/enabled=0/g" /etc/yum.repos.d/vscode.repo
dnf5 -y install --setopt=install_weak_deps=False --enablerepo=code code

systemctl enable docker.socket
systemctl enable podman.socket
systemctl enable swtpm-workaround.service
systemctl enable libvirt-workaround.service
systemctl enable incus-workaround.service
systemctl enable adwaita-lite-dx-groups.service

sed -i 's@enabled=1@enabled=0@g' /etc/yum.repos.d/fedora-cisco-openh264.repo

if [[ -f /etc/yum.repos.d/_copr_ublue-os-akmods.repo ]]; then
    sed -i 's@enabled=1@enabled=0@g' /etc/yum.repos.d/_copr_ublue-os-akmods.repo
fi

for repo in /etc/yum.repos.d/rpmfusion-*.repo; do
    if [[ -f "$repo" ]]; then
        sed -i 's@enabled=1@enabled=0@g' "$repo"
    fi
done

echo "::endgroup::"
