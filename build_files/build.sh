#!/bin/bash

set -ouex pipefail

FEDORA_MAJOR="$(rpm -E %fedora)"

install -d /usr/share/wayland-sessions
install -Dm644 /ctx/files/usr/share/wayland-sessions/adwaita-lite.desktop /usr/share/wayland-sessions/adwaita-lite.desktop
install -Dm644 /ctx/files/usr/share/wayland-sessions/vanilla-labwc.desktop /usr/share/wayland-sessions/vanilla-labwc.desktop

dnf5 install -y \
    "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-${FEDORA_MAJOR}.noarch.rpm" \
    "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FEDORA_MAJOR}.noarch.rpm"

dnf5 install -y --setopt=install_weak_deps=False \
    --disablerepo=fedora-multimedia \
    NetworkManager-libnm \
    NetworkManager-openvpn \
    NetworkManager-openvpn-gnome \
    NetworkManager-vpnc \
    NetworkManager-vpnc-gnome \
    NetworkManager-openconnect \
    NetworkManager-openconnect-gnome \
    NetworkManager-ppp \
    NetworkManager-ssh \
    NetworkManager-ssh-gnome \
    wireguard-tools \
    bluez-obexd \
    cups-pk-helper \
    accountsservice \
    adw-gtk3-theme \
    adwaita-cursor-theme \
    adwaita-icon-theme \
    alsa-utils \
    at-spi2-atk \
    at-spi2-core \
    brltty \
    bash-completion \
    blueman \
    bluez \
    bluez-tools \
    brightnessctl \
    cage \
    cups \
    cryptsetup \
    dosfstools \
    evince \
    fastfetch \
    fedora-logos \
    material-icons-fonts \
    ffmpegthumbnailer \
    file-roller \
    flatpak \
    foot \
    labwc-menu-generator \
    "f${FEDORA_MAJOR}-backgrounds-base" \
    "f${FEDORA_MAJOR}-backgrounds-gnome" \
    dejavu-sans-fonts \
    espeak-ng \
    gammastep \
    glibc-langpack-am \
    glibc-langpack-ar \
    glibc-langpack-de \
    glibc-langpack-es \
    glibc-langpack-fa \
    glibc-langpack-fr \
    glibc-langpack-ha \
    glibc-langpack-hi \
    glibc-langpack-it \
    glibc-langpack-ja \
    glibc-langpack-ko \
    glibc-langpack-nl \
    glibc-langpack-pl \
    glibc-langpack-pt \
    glibc-langpack-ru \
    glibc-langpack-sv \
    glibc-langpack-sw \
    glibc-langpack-th \
    glibc-langpack-tr \
    glibc-langpack-vi \
    glibc-langpack-yo \
    glibc-langpack-zh \
    gnome-backgrounds \
    gnome-text-editor \
    fedora-workstation-backgrounds \
    libjxl \
    google-noto-emoji-fonts \
    google-noto-sans-cjk-fonts \
    google-noto-sans-fonts \
    google-roboto-fonts \
    google-roboto-mono-fonts \
    liberation-sans-fonts \
    greetd \
    grubby \
    gum \
    grim \
    gtk4-layer-shell \
    libadwaita \
    gvfs \
    gvfs-gphoto2 \
    gvfs-mtp \
    labwc \
    libnotify \
    mako \
    mpv \
    network-manager-applet \
    nftables \
    nm-connection-editor \
    orca \
    parted \
    pavucontrol \
    pipewire \
    power-profiles-daemon \
    pipewire-alsa \
    pipewire-pulseaudio \
    playerctl \
    python3-gobject \
    rsync \
    ristretto \
    slurp \
    sfwbar \
    speech-dispatcher \
    speech-dispatcher-espeak-ng \
    swaybg \
    swayidle \
    swaylock \
    systemd-oomd-defaults \
    wlopm \
    Thunar \
    tumbler \
    udisks2 \
    unzip \
    vulkan-tools \
    waybar \
    wdisplays \
    wlrctl \
    wlr-randr \
    wireplumber \
    xfce4-taskmanager \
    wl-clipboard \
    xfce-polkit \
    xorg-x11-server-Xwayland \
    xdg-desktop-portal \
    xdg-desktop-portal-gtk \
    xdg-desktop-portal-wlr \
    xdg-user-dirs \
    xdg-user-dirs-gtk \
    xfsprogs \
    btrfs-progs

# Multimedia codecs + hardware video acceleration (needs rpmfusion, enabled
# above). Native mpv + any GTK4 media widgets otherwise fall back to the
# Fedora-default openh264-only stack, which can't play H.265/HEVC, VP9,
# AV1-in-MKV, AC3/DTS audio, etc., and leaves GPU decode off on the
# Chromebook's Intel iGPU (CPU-only decode at ~30% battery hit on a 2 GB
# box). mesa-*-freeworld unlocks VA-API / VDPAU closed-codec paths in mesa.
# Prefer RPM Fusion for the multimedia stack and explicitly avoid the base
# image's negativo17 fedora-multimedia repo here, because its GStreamer
# packages overlap with RPM Fusion freeworld packages and cause RPM file
# conflicts. gstreamer1-plugins-bad-freeworld + gstreamer1-plugins-ugly +
# gstreamer1-plugin-openh264 cover the broad gst-based playback surface
# (tumbler thumbnailer, anything portal-based). ffmpeg-free is the full ffmpeg
# stack (not the stripped libavcodec-free shipped by default). Bluefin gets this
# story "for free" via GNOME's Videos/Celluloid Flatpaks which bundle their own
# codecs; we play through the host stack so the host stack has to be complete.
MULTIMEDIA_PACKAGES=(
    gstreamer1-plugins-ugly
    gstreamer1-plugins-bad-freeworld
    gstreamer1-plugin-openh264
    ffmpeg-free
    mesa-va-drivers-freeworld
    mesa-vdpau-drivers-freeworld
)

if [[ "$FEDORA_MAJOR" -ge 44 ]]; then
    dnf5 install -y --setopt=install_weak_deps=False \
        --skip-unavailable \
        --disablerepo=fedora-multimedia \
        "${MULTIMEDIA_PACKAGES[@]}" \
        || echo "rpmfusion multimedia packages are unavailable on Fedora ${FEDORA_MAJOR}; continuing build"
else
    dnf5 install -y --setopt=install_weak_deps=False \
        --disablerepo=fedora-multimedia \
        "${MULTIMEDIA_PACKAGES[@]}"
fi

# Build a GdkPixbuf loader for JPEG-XL so swaybg and the settings
# picker can display vendor .jxl wallpapers directly. Fedora 43
# doesn't package the loader, but libjxl upstream ships the plugin
# source alongside the library. Compile it against the already-
# installed libjxl, drop the .so into the system loader dir, and
# refresh the cache so every gdk-pixbuf consumer picks it up.
# Pinned to v0.11.1 to match libjxl-0.11.1-*.fc43 and avoid ABI drift.
dnf5 install -y --setopt=install_weak_deps=False \
    gcc libjxl-devel gdk-pixbuf2-devel git-core
_jxl_src=/tmp/libjxl-src
git clone --depth 1 --branch v0.11.1 \
    https://github.com/libjxl/libjxl.git "$_jxl_src"
# Upstream plugins/gdk-pixbuf/CMakeLists.txt assumes it's included from
# the full libjxl tree (references in-tree `jxl`/`jxl_threads` targets),
# so we compile the single source file directly against the system libs.
_gdk_moddir=$(pkg-config --variable=gdk_pixbuf_moduledir gdk-pixbuf-2.0)
install -d "$_gdk_moddir"
# Split pkg-config's flags intentionally; an array keeps shellcheck happy
# without changing the compiler argument list.
read -r -a _jxl_pkg_flags <<< "$(pkg-config --cflags --libs gdk-pixbuf-2.0 libjxl libjxl_threads)"
gcc -shared -fPIC -O2 -Wl,--as-needed \
    -o "$_gdk_moddir/libpixbufloader-jxl.so" \
    "$_jxl_src/plugins/gdk-pixbuf/pixbufloader-jxl.c" \
    "${_jxl_pkg_flags[@]}"
install -Dm644 "$_jxl_src/plugins/gdk-pixbuf/jxl.thumbnailer" \
    /usr/share/thumbnailers/jxl.thumbnailer
# Refresh the system loader cache so swaybg and gdk-pixbuf-based
# thumbnailers see the new .jxl loader immediately at first boot.
# Fedora ships the tool name-mangled by word size (-64 on x86_64).
gdk-pixbuf-query-loaders-64 --update-cache
rm -rf "$_jxl_src"
dnf5 remove -y gcc libjxl-devel gdk-pixbuf2-devel git-core

# DX user groups are image-managed through sysusers.d so systemd-sysusers
# creates them on every boot, including for existing installations.
cp -a /ctx/files/. /

# Language name matrix and all MO files (wizard + settings) are
# pre-compiled and shipped in files/, installed by the cp above.

# Recompile the GSettings schema cache so our zz-adwaita-lite
# override (button-layout: minimize/maximize/close) wins over
# Fedora's 'appmenu:close' default. Chrome/Chromium, Firefox,
# Electron apps, and Flatpak apps via xdg-desktop-portal's Settings
# namespace all read this.
glib-compile-schemas /usr/share/glib-2.0/schemas/

# Add signature verification for our container registry.
# Merge into existing policy.json rather than replacing it so
# the base image's ublue-os verification entries are preserved.
python3 -c "
import json
p = json.load(open('/etc/containers/policy.json'))
p.setdefault('transports', {}).setdefault('docker', {})['ghcr.io/adwaita-blue-lite'] = [{
    'type': 'sigstoreSigned',
    'keyPath': '/etc/pki/containers/adwaita-lite.pub',
    'signedIdentity': {'type': 'matchRepository'},
}]
json.dump(p, open('/etc/containers/policy.json', 'w'), indent=2)
"

# Ensure video group exists for brightnessctl backlight access
# `files/usr/lib/sysusers.d/adwaita-lite.conf` declares it; no manual
# groupadd is needed (and manual groups bypass sysusers/bootc lint).

install -d /etc/xdg/labwc

# Root menu: dynamic pipemenu (regenerated each time the menu opens).
# Desktop menu: static (right-click on desktop, no pipemenu support for named menus).
cat > /etc/xdg/labwc/menu.xml <<'MENU_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_menu>
  <menu id="root-menu" label="" execute="/usr/libexec/adwaita-lite-menu"/>
  <menu id="desktop-menu" label="Desktop">
    <item label="Settings"><action name="Execute" command="adwaita-lite-settings"/></item>
    <item label="File Manager"><action name="Execute" command="Thunar"/></item>
    <item label="Terminal"><action name="Execute" command="foot"/></item>
    <separator/>
    <item label="Lock Screen"><action name="Execute" command="swaylock -f"/></item>
    <item label="Log Out"><action name="Exit"/></item>
    <item label="Restart"><action name="Execute" command="systemctl reboot"/></item>
    <item label="Shut Down"><action name="Execute" command="systemctl poweroff"/></item>
  </menu>
</openbox_menu>
MENU_EOF

chmod 0755 \
    /etc/xdg/labwc/autostart \
    /usr/bin/ul-debug-nm \
    /usr/bin/adwaita-lite-settings \
    /usr/bin/adwaita-lite-setup-wizard \
    /usr/bin/adwaita-lite-greeter \
    /usr/libexec/adwaita-lite-apply-settings \
    /usr/libexec/adwaita-lite-encrypted-swap \
    /usr/libexec/adwaita-lite-first-boot \
    /usr/libexec/adwaita-lite-flatpak-setup \
    /usr/libexec/adwaita-lite-flatpak-skip \
    /usr/libexec/adwaita-lite-wallpaper-thumbnailer \
    /usr/libexec/adwaita-lite-nightlight \
    /usr/libexec/adwaita-lite-set-memory-strategy \
    /usr/libexec/adwaita-lite-swap-init \
    /usr/libexec/adwaita-lite-greeter-launch \
    /usr/libexec/adwaita-lite-greeter-setup \
    /usr/libexec/adwaita-lite-wizard-session \
    /usr/libexec/adwaita-lite-menu \
    /usr/bin/adwaita-lite-app-menu \
    /usr/bin/adwaita-lite-panel \
    /usr/libexec/adwaita-lite-session \
    /usr/libexec/adwaita-lite-volume \
    /usr/libexec/adwaita-lite-brightness
[ -e /usr/bin/adwaita-lite-app-setup ] && chmod 0755 /usr/bin/adwaita-lite-app-setup
[ -e /usr/libexec/adwaita-lite-app-setup-helper ] && chmod 0755 /usr/libexec/adwaita-lite-app-setup-helper

# Disable Plymouth entirely by masking the unit that starts it.
#
# An earlier version of this file masked plymouth-quit.service and
# plymouth-quit-wait.service instead, which is the WRONG end of the
# lifecycle to cut: plymouth-start would still run, Plymouth would
# grab DRM master on the primary display, and then there was no
# plymouth-quit-wait for downstream services to order against — so
# the DRM handoff to cage (the greeter's compositor) was a naked race.
# Sometimes cage won DRM master, sometimes Plymouth held it and cage
# hung silently on VT acquisition. That matched the intermittent
# "stuck at Started greetd.service" boot the user kept hitting.
#
# Masking plymouth-start.service prevents Plymouth from ever running,
# so the quit services have nothing to do and can stay at their
# defaults (greetd's stock After=plymouth-quit.service is satisfied
# instantly because plymouth-start never activated). Boot is pure text
# since we don't pass rhgb/splash kargs, which matches the current UX.
systemctl mask plymouth-start.service
systemctl enable greetd.service
systemctl enable power-profiles-daemon.service
systemctl enable accounts-daemon.service
# CUPS: socket-activated instead of always-on. cups.socket listens on
# the IPP socket; the first client connection brings cups.service up on
# demand. Saves ~10 MiB resident on boots where nothing prints, which
# is the common case on a home laptop. When a user prints, cups.service
# starts and stays up for the remainder of the session.
systemctl disable cups.service
systemctl enable cups.socket
systemctl enable bluetooth.service

# Mask daemons we never use but the base image ships enabled.
# Each is an idle process that would otherwise sit resident for the
# entire session on 2 GB hardware.
#
#   ModemManager         cellular modem daemon — Chromebooks have no modem
#   systemd-homed        encrypted/portable home-dir machinery — unused
#   systemd-userdbd      backing store for systemd-homed — unused
#   systemd-nsresourced  varlink NSS resource daemon — unused (basic NSS
#                        via /etc/nsswitch.conf covers our needs)
#   gssproxy             Kerberos/GSS proxy for NFS — no NFS on this image
#   sshd                 remote shell — no current use case; we can
#                        unmask it for development if needed
#
# Total savings on a typical boot: ~60 MiB resident.
systemctl mask \
    ModemManager.service \
    systemd-homed.service \
    systemd-userdbd.service \
    systemd-nsresourced.service \
    gssproxy.service \
    sshd.service

# Replace firewalld with nftables. firewalld is a Python daemon that
# loads XML zone configs and sits resident at ~50 MiB; for a single-
# user home Chromebook behind a router NAT we just need "drop new
# incoming connections, allow established + loopback + outgoing",
# which nftables.service can do with a ~20-line ruleset at ~10 MiB
# resident. Net savings: ~40 MiB.
systemctl disable firewalld.service 2>/dev/null || true
systemctl mask firewalld.service
mkdir -p /etc/sysconfig
cat > /etc/sysconfig/nftables.conf <<'NFT_EOF'
# Adwaita-Lite minimal nftables ruleset.
# Replaces firewalld on this image. Intended for a single-user
# laptop behind a home router NAT: drop unsolicited inbound, allow
# everything outbound plus return traffic for connections we
# initiated. No forwarding (we're not a router).
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        iif lo accept comment "loopback"
        ct state established,related accept comment "return traffic"
        ct state invalid drop comment "bogus packets"
        ip protocol icmp accept comment "IPv4 ICMP"
        ip6 nexthdr icmpv6 accept comment "IPv6 ICMP/ND"
        # DHCPv4 client: offers/acks come in as broadcast/unicast from
        # the server's port 67 to our port 68. Conntrack normally
        # marks these as RELATED but the broadcast-to-unicast
        # asymmetry can miss, so be explicit.
        udp sport 67 udp dport 68 accept comment "DHCPv4 client"
        # DHCPv6 client: server->client replies land on 546.
        udp sport 547 udp dport 546 accept comment "DHCPv6 client"
        # mDNS so zeroconf-aware apps keep working if they talk to
        # the kernel stack directly even with avahi masked.
        udp dport 5353 accept comment "mDNS"
        # IPP-over-USB / CUPS printer responses land here when a
        # print job is active. Socket activation keeps cupsd off
        # otherwise, so this rule only matters during actual prints.
        udp dport 631 accept comment "IPP browse"
    }
    chain forward {
        type filter hook forward priority 0; policy drop;
    }
    chain output {
        type filter hook output priority 0; policy accept;
    }
}
NFT_EOF
chmod 0644 /etc/sysconfig/nftables.conf
# Fail closed: make NetworkManager hard-require nftables.service so a
# ruleset load failure blocks interface bring-up rather than leaving
# the box on the network with no firewall. The stock nftables.service
# only uses Before=/Wants=network-pre.target, which fails open.
mkdir -p /etc/systemd/system/NetworkManager.service.d
cat > /etc/systemd/system/NetworkManager.service.d/10-require-nftables.conf <<'FAIL_EOF'
[Unit]
Requires=nftables.service
After=nftables.service
FAIL_EOF
chmod 0644 /etc/systemd/system/NetworkManager.service.d/10-require-nftables.conf
systemctl enable nftables.service

# Mask base-image daemons whose features we don't expose AND whose
# masking actually saves RAM (i.e. always-on services, not D-Bus-
# activated ones whose masking just breaks clients without any savings):
#
#   switcheroo-control     dual-GPU switching — Chromebooks have one
#                          GPU.
#   abrtd + abrt-*         crash reporter daemon and its satellite
#                          hook services. Useful for distro package
#                          maintainers, not home users.
#   packagekit             software-management daemon. We use bootc
#                          + flatpak; nothing talks PackageKit.
#
# Deliberately NOT masked (all D-Bus / socket-activated upstream, so
# masking saves zero RAM but breaks clients that query them):
#   avahi-daemon           mDNS — leave socket-activated so AirPrint
#                          / network-printer auto-discovery works.
#   colord                 ICC profile daemon — socket-activated.
#   geoclue                location service — D-Bus-activated; Firefox
#                          location prompt and auto-timezone need it.
#   iio-sensor-proxy       accel/light sensor — D-Bus-activated;
#                          essential for screen auto-rotation on
#                          convertible Chromebooks.
#
# Masks are idempotent — services that aren't actually enabled on
# the base image ignore this no-op.
systemctl mask \
    switcheroo-control.service \
    abrtd.service \
    abrt-journal-core.service \
    abrt-oops.service \
    abrt-vmcore.service \
    abrt-xorg.service \
    packagekit.service \
    packagekit-offline-update.service 2>/dev/null || true
# Restore socket-activation for avahi (network-printer auto-discovery)
# so AirPrint works when a printer appears on the LAN. The service
# stays inactive until a client queries the mDNS socket.
systemctl enable avahi-daemon.socket 2>/dev/null || true
# Explicit: NM is enabled by the base image, but re-enabling is a cheap
# safeguard against any preset drift. NetworkManager-wait-online stays
# at its preset default (enabled) to match bluefin exactly - nothing
# on this image actually orders against network-online.target on the
# critical boot path (greetd doesn't, our first-boot service doesn't,
# flatpak-setup polls DNS itself), so the unit being enabled costs
# nothing on the common case and keeps us aligned with the base image.
systemctl enable NetworkManager.service
systemctl enable adwaita-lite-first-boot.service
# App installation is a post-login user choice. Mask the old pre-login
# installer so presets, stale enablement, or manual dependencies cannot
# resurrect login-blocking Flatpak setup.
systemctl mask adwaita-lite-flatpak-install.service 2>/dev/null || true
systemctl enable adwaita-lite-flatpak-update.service
# OOM protection on 2 GB hardware — oomd kills the heaviest cgroup under
# memory/swap pressure before the kernel OOM killer engages and freezes
# the whole machine. Chrome gets an earlier safety valve because Flatpak
# Chrome can keep a sibling app scope alive after oomd kills one scope.
systemctl enable systemd-oomd.service
systemctl enable adwaita-lite-chrome-early-oom.service

# Add ublue-os COPR for uupd (unified updater with hardware safety checks).
dnf5 copr enable -y ublue-os/packages fedora-"${FEDORA_MAJOR}"-x86_64
dnf5 install -y --setopt=install_weak_deps=False uupd

# Unified updater: bootc image + Flatpak in one pass with hardware safety checks.
# Replaces the separate rpm-ostree + flatpak timers from the base image.
systemctl enable uupd.timer
systemctl disable rpm-ostreed-automatic.timer
systemctl disable flatpak-system-update.timer
systemctl --global disable flatpak-user-update.timer

# Hide launchers for packages that show up in the start menu but
# don't belong in this distro's UX.
#
# xfce4-panel can't be uninstalled: Fedora 43's Thunar package Requires
# xfce4-panel directly (verified: `dnf5 repoquery --whatrequires
# xfce4-panel` lists Thunar-4.20.*). An earlier version of this file
# did `dnf5 remove -y xfce4-panel`, which dnf5 honored by cascade-
# removing Thunar as well — so Super+E, File Manager menu entries,
# and inode/directory MIME defaults all dead-ended into "command
# not found". We now just remove the .desktop file so the launcher
# never surfaces; the ~5 MB of binaries stay on disk but never run
# under labwc + waybar.
#
# Mousepad used to be the default text editor; remove it defensively in case
# it is present in the base image. Its dependency stack is shared by Evince
# and Thunar, so dropping the package and our legacy desktop alias is the
# safe removal boundary.
#
# nvtop is a real leaf (no reverse deps), so we uninstall it outright.
dnf5 remove -y mousepad nvtop || true
rm -f /usr/share/applications/xfce4-panel.desktop \
      /usr/share/applications/nvtop.desktop

# distrobox ships on ublue-os/base-main and comes with a ujust recipe
# file. We keep it off main for memory reasons on 2 GB targets;
# container workflows belong on the forthcoming adwaita-lite-dx
# variant (distrobox + brew). Remove both the binary and the recipes
# so `ujust` doesn't list unreachable commands.
dnf5 remove -y distrobox || true
rm -f /usr/share/ublue-os/just/30-distrobox.just
_ujust_entrypoint=/usr/share/ublue-os/just/00-entry.just
if [ ! -f "$_ujust_entrypoint" ]; then
    _ujust_entrypoint=/usr/share/ublue-os/justfile
fi
_ujust_tmp=$(mktemp)
awk '
    /^# Imports$/ {
        print
        exit
    }
    { print }
' "$_ujust_entrypoint" > "$_ujust_tmp"
find /usr/share/ublue-os/just -maxdepth 1 -type f -name '*.just' ! -name '60-custom.just' -printf '%f\n' \
    | sort \
    | while read -r _just_file; do
        printf 'import "/usr/share/ublue-os/just/%s"\n' "$_just_file"
    done >> "$_ujust_tmp"
printf 'import? "/usr/share/ublue-os/just/60-custom.just"\n' >> "$_ujust_tmp"
install -m 0644 "$_ujust_tmp" "$_ujust_entrypoint"
rm -f "$_ujust_tmp"

# Flatpak apps are installed by the first-boot service from Flathub —
# not pre-installed in the image.  This keeps the raw image small for
# constrained target hardware (16 GB eMMC).

# fedora-logos already installs fedora-logo-icon.png into hicolor at
# all standard sizes.  Add the SVG as a scalable icon for HiDPI.
install -Dm644 /usr/share/fedora-logos/fedora_logo.svg \
    /usr/share/icons/hicolor/scalable/apps/fedora-logo-icon.svg

# Rebuild icon caches so waybar/GTK can find symbolic icons
gtk-update-icon-cache -f /usr/share/icons/Adwaita 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/hicolor 2>/dev/null || true

# Precompile our Python helpers so cold starts don't pay the
# .py -> .pyc compilation tax on first import. Without this step,
# launching the settings app on a freshly-booted 2 GB machine
# compiles ~25 modules totalling ~6 kLOC before the window even
# appears. `-q` silences per-file log output; `-j 0` parallelises
# across available cores. We only target /usr/lib/adwaita-lite —
# the top-level /usr/bin scripts are shebang files without a .py
# extension, so compileall skips them anyway, and their bytecode
# cache directory would be non-writable on a booted ostree system.
python3 -m compileall -q -j 0 /usr/lib/adwaita-lite 2>/dev/null || true

# Regenerate the initramfs into the bootc module path so
# /usr/lib/modprobe.d/adwaita-lite-i915.conf reaches the early-KMS load
# of i915. The image itself keeps /boot empty; bootc/installers generate
# the deployed initramfs from /usr/lib/modules.
if command -v dracut >/dev/null 2>&1; then
    KVER=$(rpm -q --qf '%{version}-%{release}.%{arch}' kernel-core | head -1)
    if [ -n "$KVER" ]; then
        dracut --force --no-hostonly --kver "$KVER" \
            "/usr/lib/modules/${KVER}/initramfs.img" || true
    fi
fi
install -d /boot
find /boot -mindepth 1 -delete 2>/dev/null || true

dnf5 clean all
rm -rf /var/lib/dnf /run/dnf /run/selinux-policy /var/lib/greetd/.config/systemd/user/xdg-desktop-portal.service
find /tmp /var/tmp -mindepth 1 -delete 2>/dev/null || true
find /run -mindepth 1 -not -path '/run/systemd*' -delete 2>/dev/null || true
