# Security policy

## Supported streams

| Stream | Tag | Support |
|---|---|---|
| Stable | `latest` | Supported |
| Developer | `dx` | Supported for development use |
| Testing | `testing` | Experimental; may be rebuilt or retagged |
| Beta canary | `beta` | Experimental; Fedora-next compatibility testing |

Security fixes land on `main` first and are promoted through the stream
pipeline. Only the current stream images are supported; older date tags are
kept for pinning but do not receive backports.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

**https://github.com/adwaita-blue-lite/adwaita-lite/security/advisories/new**

Do not open a public issue for a suspected vulnerability.

Include, where possible:

- The image tag or digest (`ghcr.io/adwaita-blue-lite/adwaita-lite@sha256:...`)
- `bootc status` output
- Steps to reproduce and expected/actual behavior
- Whether the issue is in the image, a shipped script, the installer, or an
  upstream package
- Any logs or crash output, with secrets and personal data removed

## Image signing

Images are signed with the Adwaita-Lite cosign key during publishing. The
public key ships in the image at `/etc/pki/containers/adwaita-lite.pub` and in
this repository at `files/etc/pki/containers/adwaita-lite.pub`.

Public key SHA-256 fingerprint:

```
SHA256:ajMFHEU9usgFI2mxl/DEnNkvspaS3LQHLfNhPlSPwvw=
```

Verify a published image:

```bash
cosign verify \
  --key files/etc/pki/containers/adwaita-lite.pub \
  ghcr.io/adwaita-blue-lite/adwaita-lite:latest
```

The build workflow verifies the signature it just produced; a signing
regression fails the publish run instead of silently shipping an unsigned
image.

## Scope

In scope:

- The image build, shipped packages, systemd units, sysctl/sysusers/tmpfiles
  configuration, and the nftables ruleset
- The settings app, setup wizard, greeter, app menu, installer, and update
  helpers in `files/`
- The published GHCR image and disk artifacts

Out of scope:

- Vulnerabilities in upstream Universal Blue base images or Fedora packages
  (report those upstream, but tell us if the image configuration makes them
  worse)
- Flatpak applications installed by users
- Hardware firmware and Chromebook firmware modifications

## Response

We aim to acknowledge reports within 7 days, triage severity, fix in `main`,
and publish a GitHub Security Advisory when appropriate. Please allow time for
a fix before public disclosure.
