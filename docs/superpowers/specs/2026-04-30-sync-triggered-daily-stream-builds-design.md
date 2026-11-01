# Sync-Triggered Daily Stream Builds Design

## Goal

Ensure every published Adwaita-Lite stream image receives daily base-image and security refreshes while preserving the branch promotion model:

- `latest` is built from `main`.
- `dx` is built from `dx` after `main` successfully syncs into it.
- `testing` is built from `testing` after a sync-triggered `dx` build succeeds and `dx` syncs into it.
- `beta` is built from `beta` after `main` successfully syncs into it.

The important guarantee is that downstream streams rebuild even when branch sync is a no-op, because daily security updates can come from the upstream base image rather than repository commits.

## Current Problem

The current sync cascade depends on branch pushes made by the sync workflow triggering later workflows. Those pushes use the repository `GITHUB_TOKEN`, and GitHub does not trigger normal `push` workflows from most `GITHUB_TOKEN`-authored events. Even if push-triggered workflows were available, a no-op merge would not create a push, so downstream streams would miss daily rebuilds when only the base image changed.

## Architecture

Keep `build.yml` as the only workflow that builds and publishes container images. Keep `sync-streams.yml` and `sync-one-stream.yml` as the branch-alignment layer, but make successful sync jobs explicitly dispatch the target stream build.

The automated promotion chain is:

```text
main scheduled build succeeds
  -> sync main into dx
  -> dispatch dx build with sync-promotion marker
  -> sync-triggered dx build succeeds
  -> dispatch sync dx into testing
  -> dispatch testing build with sync-promotion marker

main scheduled build succeeds
  -> sync main into beta
  -> dispatch beta build with sync-promotion marker
```

This preserves the intended ordering and avoids adding PAT or GitHub App credentials.

## Workflow Contract

`build.yml` should accept a `workflow_dispatch` input such as `sync-promotion`, defaulting to `false`.

Manual builds keep the default value and do not trigger stream promotion. Sync-triggered dispatches run on the target branch ref and pass `sync-promotion=true`.

`sync-streams.yml` should keep reacting to successful scheduled `main` builds for `main -> dx` and `main -> beta`. It should also keep its manual `workflow_dispatch` path for a caller to request one explicit `source -> target` sync.

After `build.yml` successfully publishes and signs a sync-triggered `dx` build, it should explicitly dispatch `sync-streams.yml` with `source=dx` and `target=testing`. This avoids depending on `workflow_run` payload metadata to recover the original dispatch input.

Any workflow that dispatches another workflow should declare the token permissions it needs, including `actions: write`. Existing publish/sign permissions should remain scoped to the build job.

`sync-one-stream.yml` should merge the source branch into the target branch, then dispatch the target build when the target branch is either updated or already aligned. If the merge conflicts and a sync PR is opened or reused, it should skip the target build because the target branch is not aligned.

## Error Handling

Clean merge and push: push the target branch, then dispatch the target build. If dispatch fails, the sync job should fail because the target image rebuild is part of the update contract.

Already aligned: dispatch the target build anyway. This is required for daily base-image and security refreshes when repository content has not changed.

Merge conflict: abort the merge, open or reuse `sync/<source>-to-<target>`, and do not dispatch the target build. The open PR is the visible signal that the stream is stale or blocked.

Each outcome should log a concise status line: pushed and dispatched, already aligned and dispatched, or conflict PR opened and dispatch skipped.

## Testing

Static workflow tests should cover these contracts:

- `build.yml` exposes a `workflow_dispatch` input for sync-triggered promotion and keeps the default manual behavior non-promoting.
- `build.yml` dispatches `sync-streams.yml` for `dx -> testing` only after successful sync-triggered `dx` builds.
- Workflow permissions include `actions: write` where workflow dispatches are performed.
- `sync-one-stream.yml` dispatches `build.yml` on the target branch after clean or no-op syncs.
- `sync-one-stream.yml` passes the sync-promotion marker when dispatching builds.
- `sync-streams.yml` supports explicit `source=dx,target=testing` dispatches used by the successful sync-triggered `dx` build.
- Tests no longer encode the incorrect assumption that `GITHUB_TOKEN` branch pushes are enough to continue the cascade.

## Non-Goals

- Do not build every stream directly from a single scheduled matrix.
- Do not add PAT or GitHub App credentials for branch pushes.
- Do not promote manually dispatched `dx` builds into `testing`.
- Do not publish a target stream after a failed or conflicted branch sync.
