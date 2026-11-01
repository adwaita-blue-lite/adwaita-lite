# Publication contract

**Status:** pre-release (2026-11-01)
**Registry:** `ghcr.io/adwaita-blue-lite/adwaita-lite`
**Source:** `github.com/adwaita-blue-lite/adwaita-lite` — a standalone derivative of
[`ublue-os/image-template`](https://github.com/ublue-os/image-template)

This document is the one-page contract that must exist before the GHCR package is
made public. It records what users can rely on and what is explicitly not yet
guaranteed.

## Registry decision (Q2)

GHCR is the registry of record. The container package is public so that users,
`bootc`, and CI can pull it anonymously. GitHub's fork-network detach is
intentional; upstream changes arrive through the `upstream` git remote and the
daily `upstream-sync` workflow, not through GitHub's **Sync fork** button.

Adwaita-Lite is an **end-user image**, not a supported base image for downstream
derivatives. The Apache-2.0 license permits reuse, but no ABI, package-set, or
upgrade compatibility is guaranteed for images that build `FROM` this one.

## Supported streams

| Branch | Tags | Audience | Stability |
|---|---|---|---|
| `main` | `latest`, `latest.YYYYMMDD`, `YYYYMMDD` | end users | stable; the only supported install target |
| `dx` | `dx`, `dx.YYYYMMDD` | developers | best effort |
| `testing` | `testing`, `testing.YYYYMMDD` | testers | work in progress; may be rebuilt or retagged |
| `beta` | `beta`, `beta.YYYYMMDD` | Fedora-next canary | experimental |

Stream tags move as new builds publish. Date tags identify a build day and are the
right reference when pinning or reporting a problem. Rebuilds are not guaranteed
to be bit-for-bit reproducible.

Direct installs of `testing` or `beta` are opt-in and unsupported for normal
users.

## Install and verification

```bash
sudo bootc switch ghcr.io/adwaita-blue-lite/adwaita-lite:latest
```

Images are signed with the project cosign key. The public key ships at
`/etc/pki/containers/adwaita-lite.pub` inside the image and in this repository at
`files/etc/pki/containers/adwaita-lite.pub`.

```bash
cosign verify \
  --key files/etc/pki/containers/adwaita-lite.pub \
  ghcr.io/adwaita-blue-lite/adwaita-lite:latest
```

The image policy writes a `sigstoreSigned` + `matchRepository` entry for
`ghcr.io/adwaita-blue-lite` into `/etc/containers/policy.json` at build time.

## Rollback and recovery

- `sudo bootc rollback` returns to the previous deployment.
- Pin a known-good date tag:
  `sudo bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:latest.YYYYMMDD`
- The generated status matrix records branch tips, image digests, workflow runs,
  and signature state: [`status-matrix.md`](status-matrix.md).
- If a bad build is published, rebuild and republish the stream tag. Do not delete
  date tags that users may have pinned.

## Upstream

Upstream template changes are merged by
[`.github/workflows/upstream-sync.yml`](../../.github/workflows/upstream-sync.yml)
daily at 06:00 UTC. Each release branch gets its own pull request when the merge
is clean, or its own conflict issue when a human has to resolve it. The workflow
never pushes directly to a release branch.

Pull requests cannot be opened from this repository into
`ublue-os/image-template`. If a change belongs upstream, fork that repository
separately and open the pull request from the fork.

## Explicitly not guaranteed yet

- Boot, update, rollback, or installer behavior on the 2 GB target hardware.
- Secure Boot / UKI signing.
- Downstream derivative compatibility.
- Runtime memory or performance characteristics.

These are tracked as the Wave 2 verification gates. Until they are evidenced,
treat the image as pre-release.
