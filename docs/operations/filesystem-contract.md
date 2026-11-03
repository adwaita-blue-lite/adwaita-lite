# Filesystem contract

**Decision:** ext4 is the only supported root filesystem for the current
pre-release image.

## Why ext4

- CI/BIB already builds the raw image from
  `files/usr/lib/bootc/install/00-adwaita-lite.toml`, which declares ext4.
- The target is a 2 GB / 32 GB eMMC Chromebook; ext4 avoids btrfs COW and
  metadata overhead and removes an untested `mkfs.btrfs` path.
- The swap stack uses a loop device + dm-crypt and calls `swapon` on the
  mapper, so it does not require btrfs nocow rules.
- One supported path is easier to test than three partially implemented ones.

## Surface status

| Surface | State |
|---|---|
| `files/usr/lib/bootc/install/00-adwaita-lite.toml` | ext4 (authoritative default) |
| `Justfile` BIB builds | no `--rootfs` override; BIB reads the image TOML |
| Setup wizard | ext4 only; selector disabled |
| Swap init | filesystem-agnostic (loop + dm-crypt) |
| ISO / Anaconda | **pending**: the kickstart has no explicit storage directive; ISO install is a VM-gated follow-up |

## Migration policy

This is a pre-release convergence, not an in-place migration. Existing btrfs or
xfs installations are not converted. Advanced filesystems are deferred until
there is explicit installer, boot, update, and rollback evidence for each one.

## Verification

```bash
python3 -m pytest -q tests/test_fs_declarations.py tests/test_installer_mount_handling.py
just --unstable --fmt --check -f Justfile
```

A release claim additionally requires a real ISO/Anaconda install on the
supported filesystem, followed by boot, update, and rollback. CI build success
alone does not prove installer parity.
