# Upstream sync (ublue-os/image-template)

Adwaita-Lite is an **independent derivative** of
[`ublue-os/image-template`](https://github.com/ublue-os/image-template), not a
GitHub fork-network fork. The repository keeps upstream's git history as an
ancestor and pulls future template changes through a plain git remote.

## Why the repository is standalone

GitHub fork-network forks inherit visibility and restrict several repository
settings. A distribution needs full control over:

- package visibility and GHCR access
- rulesets and required checks
- secret scanning and dependency security settings
- repository visibility

Detaching (Settings → General → Danger Zone → **Leave fork network**) converts
the repository in place and preserves every commit. The only things lost are
fork-network conveniences: the **Sync fork** button and the ability to open pull
requests from this repository into `ublue-os/image-template`.

Git-level upstream access is unaffected. `ublue-os/image-template` is public, so
`git fetch` from its URL always works.

If a change should go upstream, fork `ublue-os/image-template` separately and
open the pull request from that small fork. The distribution repository does not
need to be the contribution vehicle.

## Automatic sync

[`.github/workflows/upstream-sync.yml`](../../.github/workflows/upstream-sync.yml)
runs every Monday at 06:00 UTC and on demand.

1. Fetches `upstream/main`.
2. Merges it into `upstream-sync/YYYYMMDD`.
3. Opens a pull request when the merge is clean and has changes.
4. Opens an issue with the upstream commit list when the merge conflicts.

The workflow never pushes directly to `main`. This is intentional: the image has
diverged substantially from the template, so conflicts need a human decision.

## Manual sync

```bash
git remote add upstream https://github.com/ublue-os/image-template.git
git fetch upstream main

git switch -C upstream-sync/manual
git merge upstream/main

# resolve conflicts, then verify
python3 -m pytest -q
just --unstable --fmt --check -f Justfile
git push -u origin upstream-sync/manual
```

Open a pull request from `upstream-sync/manual` into `main`.

## Conflict principles

- Keep Adwaita-Lite's `Containerfile`, `build_files/build.sh`, and product
  payload; upstream template files are starting points, not replacements.
- Take upstream action pins, workflow fixes, and documentation corrections when
  they do not change the image contract.
- Re-run the full test suite and a PR image build before merging a sync PR.
- Never resolve a conflict by deleting Adwaita-Lite-specific tests or branding.
