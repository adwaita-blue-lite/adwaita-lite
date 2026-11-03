# Contributing to Adwaita-Lite

Adwaita-Lite is a Universal Blue-derived bootc image for old x86_64
Chromebooks and low-RAM laptops. Contributions are welcome, but the project is
maintained by a small team and prioritizes the 2 GB / 32 GB target.

## Before you start

- Read [`README.md`](README.md) and [`SECURITY.md`](SECURITY.md).
- For a bug, open an issue using the bug template with the image digest,
  `bootc status`, and logs.
- For a security issue, **do not open a public issue**. Use
  [private vulnerability reporting](https://github.com/adwaita-blue-lite/adwaita-lite/security/advisories/new).
- For a large change or a new component, open a discussion issue first so the
  design can be reviewed before implementation.

## Repository model

- `main` is protected: PRs require the `Pytest` and `Lint` checks; force-push
  and deletion are blocked.
- Release streams are `dx`, `testing`, and `beta`. They are promoted from
  `main` by the sync workflows. Do not force-push a stream branch.
- Upstream `ublue-os/image-template` changes arrive through the daily
  `upstream-sync` workflow as PRs. Resolve conflicts in favor of
  Adwaita-Lite-owned files; see
  [`docs/operations/upstream-sync.md`](docs/operations/upstream-sync.md).
- `Containerfile`, `build_files/build.sh`, and
  `.github/workflows/build.yml` are high-risk files. Do not mix changes to
  them with unrelated work.

## Local development

You need `podman`, `just`, `python3`, `pytest`, `ruff`, `shellcheck`, and
`actionlint` for the same checks CI runs.

```bash
# Fast checks
python3 -m pytest -q
just --unstable --fmt --check -f Justfile
ruff check .
shellcheck -S warning build_files/build.sh build_files/ci/*.sh
actionlint -shellcheck ""

# Build the image locally (large; needs podman and disk headroom)
just build

# Build a VM image
just build-qcow2
```

`just build-qcow2` uses the local filesystem override; CI and the installer
use the image's `bootc install` configuration. Keep them consistent when
changing installer behavior.

## Pull requests

- Use Conventional Commits: `fix(settings): ...`, `ci(disk): ...`,
  `docs: ...`, `feat(wizard): ...`.
- Keep one logical change per PR. If a change spans the image build, the
  installer, and CI, split it.
- Include in the PR body:
  - what changed and why
  - the files/areas touched
  - the commands you ran and their result
  - image/VM evidence when behavior changed
  - rollback steps for risky changes
- Do not commit secrets, `cosign.key`, generated `_build_*` output, or
  `~/.config` state.
- Update tests and documentation in the same PR when behavior changes.
- Translations live under `po/`. Run `make -C po mo` after editing catalogs;
  compiled `.mo` files are checked in.

## Licensing

Adwaita-Lite original code is GPL-3.0-or-later. Files derived from
`ublue-os/image-template` remain Apache-2.0; see [`NOTICE`](NOTICE) and
[`LICENSES/Apache-2.0.txt`](LICENSES/Apache-2.0.txt). By contributing, you
agree that your original contribution is provided under GPL-3.0-or-later.

## Review and response

This is a small project. Reviews and issue responses are best effort. A
maintainer may ask for a smaller PR, additional evidence, or a design issue
before merging. Security reports are prioritized over feature work.
