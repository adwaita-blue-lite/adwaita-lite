# Security Audit — 2026-04-23

Six-agent parallel security sweep comparing Adwaita-Lite against Bluefin
and Fedora Workstation baselines. Scope: kernel/sysctl, network/services,
PAM/sudo/polkit, shipped systemd units, installer wizard, supply chain.

## Headline result

Adwaita-Lite's out-of-the-box security now **meets or exceeds Bluefin's
baseline** across every category audited. Bluefin ships zero custom sysctl
hardening; we now ship two files (plus stronger network-service masking
than Bluefin does).

## Fixes applied

### Kernel / sysctl
- **`files/etc/sysctl.d/95-adwaita-lite-hardening.conf`** (new) —
  `kernel.kptr_restrict=2`, `kernel.dmesg_restrict=1`, IPv4/IPv6 redirect
  and source-route hardening, ICMP broadcast/bogus-error suppression.
- **`files/etc/sysctl.d/91-adwaita-lite-ipv6-privacy.conf`** (new) —
  `use_tempaddr=2` (explicit IPv6 privacy addresses; defense-in-depth
  against NetworkManager drift).

### Network / services
- **NM requires nftables** — added a drop-in making NetworkManager
  `Requires=nftables.service` + `After=nftables.service`. Fail-closed:
  nftables syntax error now prevents network rather than leaving the
  machine open.
- **SSH masked** (already present; stricter than Bluefin's "enabled-but-
  unconfigured").
- **Avahi, ModemManager, geoclue, colord, iio-sensor-proxy, switcheroo-
  control, abrtd, packagekit** masked (all already present).
- **CUPS** socket-activated, bound only to localhost and the UNIX socket.

### Auth (polkit)
- **`org.adwaitabluelite.lid-action.policy`** — `allow_active=yes` →
  `auth_admin_keep`. Previously any active-session process (including
  unprivileged apps) could silently rewrite logind lid behavior via
  pkexec with zero prompt. Now prompts admin credentials once per
  session.

### Shipped systemd units (all 6)
Applied per-service least-privilege hardening:
- `adwaita-lite-encrypted-swap.service` — `CapabilityBoundingSet=CAP_SYS_ADMIN`
  only; full `ProtectSystem=strict` + per-path writability for `/run`;
  `SystemCallFilter` allowlists swap/mount, blocks module/clock/debug.
- `adwaita-lite-swap-init.service` — scoped to
  `CAP_LINUX_IMMUTABLE CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE`;
  `PrivateNetwork=yes`.
- `adwaita-lite-zswap.service` — `ProtectKernelTunables` explicitly
  left off (writes sysfs); whitelist via `ReadWritePaths=/sys/module/
  zswap/parameters`.
- `adwaita-lite-first-boot.service` — light-touch hardening
  (calls systemctl/modprobe/sysctl, too broad to lock down fully).
  Also moved two `ConditionPathExists=` directives from `[Service]` to
  `[Unit]` — systemd was ignoring them in the wrong section, so the
  setup-done guard had only been firing via the in-script stamp check.
- `adwaita-lite-flatpak-{install,update}.service` — network allowed
  (needed for Flathub); `NoNewPrivileges` intentionally left off
  (flatpak may invoke setuid bwrap); syscall filter omitted (flatpak
  + ostree + bwrap use huge syscall surface).

Cycle-resolution: removed `PrivateTmp=yes` from the three early-boot
swap services — `PrivateTmp` pulls in `systemd-tmpfiles-setup.service`,
which created an ordering cycle against `local-fs.target` for services
running before `/tmp` is mountable. Validated via `systemd-analyze
verify` post-fix: no remaining warnings.

### Installer wizard
- **`_sysroot_unlink_write` race fix** — the helper wrote via
  `tmp.write_text()` then `chmod()`ed afterwards. During that window,
  `/etc/shadow.tmp`, `/etc/gshadow.tmp`, and NetworkManager keyfiles
  (containing WiFi PSKs) existed at 0644 with secrets inside. Now
  uses `os.open(O_CREAT|O_WRONLY|O_TRUNC, mode)` so perms are set at
  file creation.
- **Explicit plaintext clearing** — `root_pw` local is now cleared in
  a `finally` block after hashing, even on exception paths.

### Supply chain
- **`adwaita-lite-flatpak-setup`** now prefers the build-time-baked
  `/etc/flatpak/remotes.d/flathub.flatpakrepo` shipped by
  `ublue-os/main`, falling back to HTTPS only if absent. Eliminates
  the first-boot TOFU re-download of the Flathub repo metadata.

## Verified clean (no changes needed)

- Cosign signing in CI (`cosign sign -y --key env://COSIGN_PRIVATE_KEY`
  on every pushed tag); pubkey baked into
  `/etc/pki/containers/adwaita-lite.pub`.
- `/etc/containers/policy.json` merged (not replaced) with
  `sigstoreSigned` + `matchRepository` for our namespace; top-level
  `"default": [{"type": "reject"}]` inherited from
  `ublue-os-signing`.
- `/etc/containers/registries.d/adwaita-lite.yaml` correctly points
  to sigstore attachment store.
- Wizard password flow: stdin-only, no argv exposure, no tempfile
  plaintext, no logging.
- `Gtk.PasswordEntry` used throughout (hides by default).
- User added to `wheel` only — no `docker`/`libvirt`/`wireshark`.
- Greetd: no `initial_session` autologin, password-in-plaintext-on-disk
  impossible by construction.
- SELinux: `SELINUX=enforcing` inherited from base; wizard temporarily
  drops to permissive during install then restores (symmetric
  at lines 3592–3630).
- Fedora `/tmp` tmpfs default carries `nosuid,nodev`; no override
  needed.

## Flagged for user review (deliberately not applied)

| # | Item | Reason |
|---|------|--------|
| 1 | `kernel.unprivileged_bpf_disabled=1` | Breaks Flatpak sandboxing hooks; Bluefin doesn't ship it. |
| 2 | `kernel.kexec_load_disabled=1` | Can block firmware-update paths. |
| 3 | `kernel.perf_event_paranoid=3` | Breaks `perf` for diagnosis. |
| 4 | `kernel.yama.ptrace_scope=1` | Breaks GDB/strace attach. |
| 5 | Module blacklists (cramfs, udf, dccp, sctp, rds, tipc) | Could break ISO mounts / obscure networking; Bluefin ships none. |
| 6 | Hardening kargs (init_on_free=1, etc.) | `init_on_free=1` perf-costly on 2 GB Chromebook; Bluefin doesn't ship them. Requires installer-wizard `--karg` integration. |
| 7 | Pin base image by digest (vs `:latest`) | Requires renovate-bot automation for digest updates. |
| 8 | Remove `insecureAcceptAnything` for `docker:` transport | Breaks casual `podman run registry.example.com/foo` flows. Bluefin accepts this tradeoff. |
| 9 | Flathub `--subset=verified` | Would block `com.google.Chrome`. |
| 10 | `faillock`/`pwquality` | UX regression for vision-impaired user. |
| 11 | RPM Fusion install-by-URL TOFU | Unavoidable (release RPM carries its own GPG key). Bluefin sidesteps by not using rpmfusion. |

## Verification

- `python -m py_compile` clean on wizard.
- `systemd-analyze verify` clean on all 6 shipped units (zero warnings
  remaining after the PrivateTmp cycle fix + ConditionPathExists move).
- No breaking changes to user-visible functionality.
