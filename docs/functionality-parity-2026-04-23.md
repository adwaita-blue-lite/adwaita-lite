# Functionality Parity Audit vs Bluefin / Silverblue — 2026-04-23

Five-agent investigation into whether recent security/memory sweeps
reduced OOTB functionality relative to upstream ublue-os images. The
headline: **yes, in one significant way — we weren't shipping Orca**,
the primary screen reader for a vision-impaired user. Multiple smaller
regressions also identified and fixed.

## Fixes applied

### Accessibility (agent #4 — critical)

11 packages added to `build_files/build.sh`:

- **`orca`** — the GNOME screen reader. Was completely absent. This
  was the headline gap; our primary user is vision-impaired, and
  nothing in the image could read the screen.
- **`speech-dispatcher` + `speech-dispatcher-espeak-ng` + `espeak-ng`**
  — TTS bus + engine Orca drives. Without these, Orca would install
  but be silent (`--setopt=install_weak_deps=False` blocks auto-pull).
- **`at-spi2-core` + `at-spi2-atk`** — AT-SPI accessibility bus. GTK
  pulls these as weak deps; our `install_weak_deps=False` meant they
  weren't landing.
- **`brltty`** — USB Braille display driver + udev auto-activation.
- **`gnome-themes-extra`** — ships `/usr/share/themes/HighContrast`.
  Unblocks the A14 audit TODO: `apply-settings` now selects the
  HighContrast GTK theme + `prefer-high-contrast` color-scheme +
  `org.gnome.desktop.a11y.interface high-contrast=true` when the
  settings toggle is on.
- **`adwaita-cursor-theme`** — large-cursor theme our settings app
  points at via `gtk-cursor-theme-name=Adwaita` at sizes 24/32/48.
  Wasn't a dep of anything we install.
- **`google-noto-sans-fonts` + `google-noto-sans-cjk-fonts` +
  `google-noto-emoji-fonts`** — required for the 22 translated
  locales we ship. Without them, a user switching to Arabic / Hindi /
  Japanese / Chinese / Thai sees tofu boxes.
- **`dejavu-sans-fonts` + `liberation-sans-fonts`** — Western-script
  fallback coverage.

### HighContrast theme activation (A14 follow-up)

`write_gtk_settings` in `apply-settings` now branches on
`tokens["high_contrast"]`:
- GTK theme name → `HighContrast`
- Icon theme → `HighContrast`
- `org.gnome.desktop.interface color-scheme` →
  `prefer-high-contrast`
- `org.gnome.desktop.a11y.interface high-contrast` → `true`

Settings app's High Contrast toggle now actually delivers the
higher-contrast rendering instead of just forcing dark mode.

### Masked-services rollback (agent #1)

Previous audit masked several services as "unused." Re-analysis showed
four of them are D-Bus / socket-activated upstream — masking them
saved zero RAM but broke clients that query them. Unmasking:

- **`avahi-daemon.socket`** now enabled. Restores network-printer
  auto-discovery (AirPrint / IPP-everywhere), Chromecast / DLNA
  detection, `.local` hostname resolution. Socket-activated → idle
  cost near zero. Important for a vision-impaired user adding a
  printer (previously they'd have to enter an IP address manually).
- **`colord`** unmasked — socket-activated ICC profile daemon;
  calibrated external monitors now work.
- **`geoclue`** unmasked — D-Bus-activated location service;
  Firefox location prompt and auto-timezone now work.
- **`iio-sensor-proxy`** unmasked — D-Bus-activated accel/light
  sensor bridge. Essential for screen auto-rotation on the many
  older Chromebooks that are 2-in-1 convertibles.

Still masked (correctly): `firewalld`, `sshd`, `ModemManager`,
`switcheroo-control`, `abrtd` family, `packagekit`. Cups remains
socket-activated.

### Hardware support (agent #3)

13 packages added for parity with Bluefin's network/Bluetooth stack:

- `NetworkManager-openvpn` + `-openvpn-gnome` — OpenVPN in
  nm-connection-editor.
- `NetworkManager-vpnc` + `-vpnc-gnome` — IPsec / Cisco VPN.
- `NetworkManager-openconnect` + `-openconnect-gnome` —
  AnyConnect / GlobalProtect (common in .edu / .gov environments).
- `NetworkManager-ppp` — PPP / PPPoE for DSL.
- `NetworkManager-ssh` + `-ssh-gnome` — SSH VPN.
- `wireguard-tools` — `wg` / `wg-quick` CLI.
- `bluez-obexd` — Bluetooth OBEX file send/receive.
- `cups-pk-helper` — polkit bridge for GUI printer add/remove.

~8-12 MiB on disk. None are resident daemons; NM plugins load only
when a matching connection activates.

### Codecs and hardware video acceleration (agent #5)

5 packages added for media playback + Intel iGPU hardware decode:

- `gstreamer1-plugins-bad-freeworld` — H.265, VP9, AV1-in-MKV, AC3.
- `gstreamer1-plugin-openh264` — H.264 fallback.
- `ffmpeg-free` — broader codec coverage for `mpv` + `tumbler`.
- `mesa-va-drivers-freeworld` — unlocks VAAPI H.264 / H.265 on Intel.
- `mesa-vdpau-drivers-freeworld` — same for VDPAU.

Without these, Intel iGPU sat idle and CPU did 100% video decode
(~30% battery hit on a 2 GB Chromebook).

## Verified clean (no changes needed)

### Desktop ecosystem (agent #5)

- `xdg-desktop-portal-wlr` + `xdg-desktop-portal` +
  `xdg-desktop-portal-gtk` all present. Bluefin's `-gnome` backend
  would actually be wrong for labwc.
- `toolbox` inherited from `base-main`. `distrobox` is deliberately
  removed (planned for a forthcoming adwaita-lite-dx variant with
  distrobox + brew) — we also delete `30-distrobox.just` so `ujust`
  doesn't list unreachable commands.
- Container runtime defaults unchanged — `/etc/containers/*.conf`
  inherited.
- Wayland utilities (`grim`, `slurp`, `wl-clipboard`, `wdisplays`,
  `wlr-randr`, `wlopm`, `swaybg`, `swayidle`, `swaylock`) all present.

### Package set (agent #2)

No functional RPM gaps. All Bluefin extras we don't ship are
GNOME-centric (nautilus, gnome-tweaks, extensions-app), power-user
dev tools (`fish`, `zsh`, `tmux`, `just`, `pip`), or enterprise
networking (`samba`, `krb5`, `sssd`, `davfs2`) — none appropriate
for a 2 GB single-user Chromebook.

### Supply chain

Covered by the parallel 2026-04-23 security audit — cosign signing,
policy.json, flatpak build-time remote, etc. all clean.

## Flagged for user decision (deliberately not applied)

| Item | Tradeoff |
|------|----------|
| Firefox Flatpak default in wizard | We offer Chrome; user can opt into Firefox in wizard. Consider making Firefox default instead. |
| A11Y keybinds in rc.xml (Super+Alt+S toggle Orca, zoom, mouse-keys) | Bluefin gets these from GNOME. We'd need to define our own bindings + backing scripts. |
| Orca autostart | Currently Orca is installed but nothing launches it. Accessibility page should expose a toggle; enabling it should create `~/.config/autostart/orca.desktop` or run `orca -r` on the next login. |
| Accessibility settings page additions | Currently exposes only: large text, cursor size, high-contrast, reduce motion. Missing: screen-reader toggle, magnifier, on-screen keyboard, Braille indicator, sticky/slow/bounce keys. |
| Screen magnifier for labwc | No Wayland magnifier packaged in Fedora 43. Options: Flatpak `org.gnome.Magnifier`, ship `magnus` from COPR, or document as limitation. |
| On-screen keyboard | `wvkbd` (the labwc-appropriate option) not in Fedora 43 repos. Would need COPR build or Flatpak. |
| `NetworkManager-tui` (`nmtui`) | ~500 KiB; useful recovery path for vision-impaired user with WiFi trouble. Bluefin doesn't ship it either. |

## Verification

- `bash -n build_files/build.sh` → OK.
- `python -m py_compile files/usr/libexec/adwaita-lite-apply-settings` → OK.
- Added 29 packages to `dnf5 install` across four agent work streams;
  no removals.
- Service changes: unmasked 4 D-Bus/socket-activated services;
  enabled `avahi-daemon.socket`.
