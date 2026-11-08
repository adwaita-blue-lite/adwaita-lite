# Upstream template ledger (`ublue-os/image-template`)

This ledger records every automated or manual sync of
[`ublue-os/image-template`](https://github.com/ublue-os/image-template) into
Adwaita-Lite. The workflow policy lives in
[`.github/workflows/upstream-sync.yml`](../../.github/workflows/upstream-sync.yml)
and is reproduced locally by
[`scripts/upstream-sync.sh`](../../scripts/upstream-sync.sh). The repository
relationship is described in [upstream-sync.md](upstream-sync.md).

## Decision: reviewed sync, not blind auto-merge

Adwaita-Lite intentionally diverges from the template. A blind auto-merge (or a
`merge=ours` driver in `.gitattributes`) would either conflict every day or
silently drop upstream fixes. The policy is:

- **Upstream-managed:** everything that merges cleanly, especially generic
  workflows, action pins, Dependabot changes, and template scaffolding.
- **Downstream-owned (initial):**
  - `.github/workflows/build.yml` — stream matrix, signing/promotion, and disk
    build contract are product decisions, not template defaults.
  - `README.md` — product/install documentation.
- **Classification rule:** any conflict outside the owned list stops the sync.
  Add the path to the owned list only after an explicit review, never by
  resolving it automatically.

A conflicting owned file is resolved with `ours`, but the upstream delta is
captured as a patch before the merge commit. Dropping an upstream change is
therefore always visible and reviewable.

## Daily behavior

`upstream-sync.yml` runs at 06:00 UTC for `main`, `dx`, `testing`, and `beta`,
and can be dispatched manually (`dry_run` is available).

1. Fetch `upstream/main`.
2. Attempt `git merge --no-edit --no-ff upstream/main` on
   `upstream-sync/<stream>/<YYYYMMDD>`.
3. If every conflict is in the owned list:
   - `git checkout --ours -- <owned>` and `git add` each one;
   - write `docs/operations/upstream-drift/<YYYY-MM-DD>.patch` containing the
     upstream delta that was not applied;
   - commit the merge with the upstream SHA and drift summary.
4. If any non-owned path conflicts: abort, write
   `docs/operations/upstream-drift/<YYYY-MM-DD>-conflicts.md`, upload it as an
   artifact, fail the job with a step summary. No guess is made.
5. Upload the drift patch as a workflow artifact on every run that produces one.
6. Push the sync branch and open or update one pull request per stream. The PR
   body links the patch and embeds an excerpt.
7. Update the ledger table below.

The workflow never pushes directly to a stream branch and never merges a pull
request.

### Reporting and permissions

The workflow uses `contents: write` and `pull-requests: write`. It deliberately
does **not** create issues: `GITHUB_TOKEN` issue creation in this repository
returns `GraphQL: Resource not accessible by integration`, which was the source
of the previous silent failures. Reporting is instead:

- one open/updated pull request per stream when a merge or owned-file
  resolution is produced;
- a failed check with a step summary plus an artifact when the sync is blocked;
- the committed ledger row and drift patch.

If PR creation itself fails, the job fails after the artifact upload, so the
drift is still recoverable from the run.

## Cadence and fallback

- Daily: automatic detection/merge for upstream-managed files.
- Weekly: review owned-file drift (15–30 minutes, agent-assisted). Decide
  whether to port an upstream change into the owned file or keep `ours`.
- If the policy produces noise for two consecutive weeks, switch the workflow
  to **detector only**: stop committing, upload the drift patch, and open one
  tracking PR per week.

## Ledger

Newest entries are inserted first. A `-` drift cell means the merge was
clean. Patch links are relative to this directory.

| Date (UTC) | Stream | Upstream SHA | Result | Drift patch |
|---|---|---|---|---|
<!-- upstream-sync:rows -->
| 2026-11-08 | baseline | `e9c6420` | resolved-owned | [`2026-11-08.patch`](upstream-drift/2026-11-08.patch) |

## One-time baseline (2026-11-08)

The baseline merge was prepared on `upstream-sync/baseline-2026-11-08` and is
not pushed or merged without review.

- Repo base: `main` @ `f7857a8`; the prepared branch also contains the policy
  commits (`b5674a3` is the baseline's first parent).
- Upstream: `ublue-os/image-template` `main` @
  `e9c6420` (4 commits ahead of the merge base).
- Merge base: `72e9b7c`.
- Conflicts: exactly the two owned files,
  `.github/workflows/build.yml` and `README.md`.
- Resolution: `git checkout --ours --` both files; all other upstream changes
  merged normally.
- Local baseline commit: `4b16895`; its tree is identical to its parent policy
  commit (`b5674a3`) and the merge only records upstream ancestry.
- Upstream delta not applied (see the patch):
  - `docker/login-action` `v4.7.0` → `v4.8.0`
  - `sigstore/cosign-installer` `v4.1.2` → `v4.1.3`, cosign `v3.1.2` → `v3.1.4`
  - README: NVIDIA driver section for custom images
- Drift patch: [`upstream-drift/2026-11-08.patch`](upstream-drift/2026-11-08.patch).

Reproduce the baseline locally from a checkout that contains this policy:

```bash
# On the policy branch before merge, or on main after it merges.
git switch -C upstream-sync/baseline-2026-11-08 <policy-branch>
scripts/upstream-sync.sh \
  --base upstream-sync/baseline-2026-11-08 \
  --stream baseline \
  --sync-branch upstream-sync/baseline-2026-11-08 \
  --no-ledger
```

Review the drift patch, then open a PR. Do not push the baseline branch or
merge it without approval.

## Manual resolution

Use the helper so the owned/non-owned policy is applied consistently:

```bash
# Classify without committing or switching branches. A blocked run still
# writes the conflict report.
scripts/upstream-sync.sh --base main --dry-run

# Create and commit a local sync branch (never pushes).
scripts/upstream-sync.sh --base main
```

Exit codes: `0` merged/aligned/resolved, `2` blocked by a non-owned conflict,
`1` configuration or git error.

For a blocked sync:

1. Read `docs/operations/upstream-drift/<date>-conflicts.md` for the exact
   paths.
2. Classify each path. If it should be upstream-managed, resolve it manually in
   a sync branch and run the tests.
3. If it should be owned, update:
   - `OWNED_FILES` in `scripts/upstream-sync.sh` (the single list CI uses),
   - this document.
4. Re-run the workflow. Never use `ours` outside the owned list.

## Changing the owned list

Changing ownership is a policy change. Update the script, the workflow, this
ledger, and the drift rationale in the same PR. Removing a path from the owned
list means upstream becomes authoritative for it; expect the next sync to
overwrite downstream edits.
