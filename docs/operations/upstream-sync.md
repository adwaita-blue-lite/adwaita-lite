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

## Sync policy and ledger

The authoritative policy, owned-file list, baseline record, and per-run ledger
are in [upstream-template.md](upstream-template.md). In short:

- upstream-managed files merge automatically;
- conflicting owned files (`.github/workflows/build.yml`, `README.md`) resolve
  with `ours`, but the upstream delta is committed as a drift patch;
- any non-owned conflict aborts the sync and is reported;
- the workflow opens or updates a PR and uploads the drift patch as an
  artifact; it never creates an issue and never pushes to a stream branch.

## Automatic sync

[`.github/workflows/upstream-sync.yml`](../../.github/workflows/upstream-sync.yml)
runs daily at 06:00 UTC for `main`, `dx`, `testing`, and `beta`, and on demand.

1. Fetches `upstream/main`.
2. Merges it into `upstream-sync/<stream>/<YYYYMMDD>` via
   [`scripts/upstream-sync.sh`](../../scripts/upstream-sync.sh).
3. If only owned files conflict, keeps `ours` for those files and records the
   dropped upstream delta under `docs/operations/upstream-drift/`.
4. If any non-owned file conflicts, aborts, writes a conflict report, uploads
   it, and fails the job with a step summary.
5. Updates the ledger and opens/updates one pull request per stream. The drift
   patch is attached as an artifact and linked from the PR body.

The workflow never pushes directly to a stream branch. This is intentional: the
image has diverged substantially from the template, so conflicts need a human
decision. Reporting no longer relies on issue creation, which fails in this
repository with `Resource not accessible by integration`.

## Manual sync

Use the helper to apply the same classification as CI:

```bash
# Classify without changing the worktree.
scripts/upstream-sync.sh --base main --dry-run

# Create and commit a local sync branch (the helper never pushes).
scripts/upstream-sync.sh --base main
```

Then verify and push the branch the helper reports:

```bash
python3 -m pytest -q
just --unstable --fmt --check -f Justfile
git push -u origin upstream-sync/main/<YYYYMMDD>
```

Open a pull request from the sync branch into the stream. For a hand-resolved
sync, run the same commands after `git merge upstream/main` and make sure the
owned-file drift is captured in the patch.

> `just upstream-sync` is a legacy raw-merge recipe and still hits the daily
> owned-file conflict. Use `scripts/upstream-sync.sh`; replacing the recipe is
> tracked separately so it stays outside this policy change.

## Conflict principles

- Only `.github/workflows/build.yml` and `README.md` are downstream-owned.
  Resolve those with `ours` **only** through the workflow/helper, so the
  upstream delta is recorded.
- Any other conflict is a classification event: stop, inspect it, and decide
  whether it is upstream-managed or newly owned. Do not guess.
- Keep Adwaita-Lite's `Containerfile`, `build_files/build.sh`, and product
  payload; upstream template files are starting points, not replacements.
- Take upstream action pins, workflow fixes, and documentation corrections when
  they do not change the image contract.
- Re-run the full test suite and a PR image build before merging a sync PR.
- Never resolve a conflict by deleting Adwaita-Lite-specific tests or branding.
