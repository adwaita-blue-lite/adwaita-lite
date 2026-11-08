# GTK4 panel — 2 GB VM gate checkpoint

**Date:** 2026-11-08
**Branch:** `main` @ `fc1f562`
**Image under test:** `ghcr.io/adwaita-blue-lite/adwaita-lite:latest`
(`sha256:da1cb1a292a35666caaa97d10376046c5cc0938a41731a55aff3a2505d1220e4`)

## Where we are

- PRs #13–#20 are merged on `main`: sfwbar shelf, design spec, Wave 0,
  scaffold, taskbar, popups/focus, status services, and image integration.
- The native panel is built and installed by `build_files/build.sh`; Waybar
  remains the default `panel_backend`.
- The 2 GB VM/hardware gate has not passed. It is blocked by an image boot
  failure found while creating the Gate VM.

## Gate VM

Created in the GNOME Boxes Flatpak libvirt session:

- Domain: `universal-lite-install`
- 2048 MiB RAM, 4 vCPU, UEFI (non-secure)
- `vda`: `disk-boot.qcow2` — writable qcow2 overlay backed by `disk.qcow2`
- `vdb`: `target.qcow2` — install destination
- Files: `/var/home/race/Downloads/universal-lite-raw/image/`
- XML: `universal-lite-raw/image/universal-lite-install.xml`

The source image has no UID ≥ 1000 account, so greetd's `initial_session`
starts the setup wizard as root. The wizard should install to `/dev/vdb`.

## Symptom

The VM boots the kernel from `vda`, then drops to a dracut emergency shell:

```
[FAILED] Failed to start initrd-switch-root.service - Switch Root.
See 'systemctl status initrd-switch-root.service' for details.
```

## Root cause — image build blocker

The image build's `dracut` run fails, and the failure is masked by `|| true`:

```text
+ dracut --force --no-hostonly --kver 7.2.15-200.fc44.x86_64 \
    /usr/lib/modules/7.2.15-200.fc44.x86_64/initramfs.img
dracut-install: ERROR: installing '/root'
dracut[E]: FAILED: /usr/lib/dracut/dracut-install ... -f /root
```

Consequences:

- `/usr/lib/modules/7.2.15-200.fc44.x86_64/initramfs.img` is never
  generated correctly.
- The deployed initramfs lacks the `ostree` and `bootc` dracut modules.
  `lsinitrd` shows no `ostree-prepare-root` / `bootc-root-setup`, and the
  dracut module list has neither `ostree` nor `bootc`.
- Without `ostree-prepare-root`, the initramfs cannot assemble the bootc
  deployment, so `initrd-switch-root` fails.
- The image was still published because `build.sh` ends the dracut call
  with `|| true`.

Two contributing defects:

1. The bootc base dracut config is missing from the image. The `bootc`
   package ships it at
   `/usr/share/doc/bootc/baseimage/dracut/usr/lib/dracut.conf.d/10-bootc-base.conf`
   with:
   ```
   hostonly=no
   add_dracutmodules+=" ostree bootc "
   ```
   The image's `/usr/lib/dracut/dracut.conf.d/` has `01-dist.conf`,
   `10-compression.conf`, `20-atomic-*`, `50-nss-softokn.conf`,
   `90-ublue-luks.conf`, but **not** `10-bootc-base.conf`.
2. `/root` is absent from the new deployment (the older image and the host
   have `/root` as a directory or a `var/roothome` symlink). `dracut`
   aborts while installing it, before it can add the ostree/bootc modules.

## Fix plan

1. In `build_files/build.sh`, before regenerating the initramfs:
   - install `10-bootc-base.conf` from the bootc package docs into
     `/usr/lib/dracut/dracut.conf.d/`;
   - ensure `/root` exists with the correct layout for the image.
2. Remove `|| true` from the dracut call, or verify the output explicitly.
   The build must fail if the initramfs cannot be generated.
3. Add a check that the generated initramfs contains `ostree-prepare-root`
   and `bootc-root-setup` (and/or that `lsinitrd` lists `ostree`/`bootc`).
4. Rebuild and republish the image, then recreate/reboot the Gate VM and
   continue with the 2 GB gate.

## Current gate status

| Gate item | Status |
|---|---|
| Image installs to target disk | blocked by unbootable source image |
| Panel appears after install | not reached |
| Focus theft / taskbar / popups | not reached |
| Status services | not reached |
| RSS / idle CPU on 2 GB | not reached |
| Suspend / resume | not reached |

Waybar remains the safe default. Do not flip `panel_backend` until this is
fixed and the gate passes.

## Notes

- `target.qcow2` contains an older universal-lite install (user `hopeful`);
  the installer will overwrite it.
- `disk.qcow2` is read-only and untouched; `disk-boot.qcow2` is the
  disposable overlay.
- The local host has only ~11 GB free, so do not duplicate `target.qcow2`.
