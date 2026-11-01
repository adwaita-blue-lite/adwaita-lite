# Stream Sync Build Automation Design

## Goal

Ensure same-day automatic updates for every published Adwaita-Lite stream after real `main` updates, while keeping manual builds targeted.

The intended update graph is:

```text
main push/schedule -> main container -> main disk
main push/schedule -> main container -> sync main -> dx -> dx container -> sync dx -> testing -> testing container
main push/schedule -> main container -> sync main -> beta -> beta container
```

Manual `main` container builds should not automatically promote downstream streams. Manual sync workflows can still be used for explicit repairs or one-off promotions.

## Current Problem

`sync-streams.yml` currently listens for completed `main` container builds, but its automatic sync jobs require `github.event.workflow_run.event == 'schedule'`. A successful `main` build from a normal push therefore triggers the sync workflow, then skips every automatic sync job.

Recent evidence showed exactly that behavior: the `main` container and disk builds completed successfully after a push, but the stream-sync run concluded `skipped`, leaving `dx` and `beta` behind current `main`. Remote branch ancestry confirmed `origin/main` was not an ancestor of `origin/dx` or `origin/beta`.

## Architecture

Keep the existing chained promotion architecture and fix the automatic sync gate.

`build.yml` remains the single container-image builder for all stream refs. It should still accept `workflow_dispatch.sync_promotion`, defaulting to `false`, so sync-triggered builds can be distinguished from human-triggered builds.

`build-disk.yml` remains `main`-only. It should continue building disk images after successful `main` container builds caused by `push` or `schedule` events.

`sync-streams.yml` should automatically run `main -> dx` and `main -> beta` after successful `main` container builds caused by `push` or `schedule` events. It should keep the explicit `workflow_dispatch` path for manual `source -> target` syncs.

`sync-one-stream.yml` remains the reusable branch-alignment unit. After a clean merge or already-aligned no-op, it should dispatch the target branch's container build using `sync_promotion=true`. If the merge conflicts and a sync PR is opened or reused, it should skip the target build because the target branch is not aligned.

The existing `dx` continuation remains: a successful sync-triggered `dx` build dispatches `sync-streams.yml` with `source=dx,target=testing`; that sync then dispatches the `testing` container build.

## Event Rules

Automatic stream promotion should run for these completed `main` container builds:

- `workflow_run.conclusion == 'success'`
- `workflow_run.head_branch == 'main'`
- `workflow_run.event == 'push'` or `workflow_run.event == 'schedule'`

Automatic stream promotion should not run for:

- Pull requests.
- Manual `workflow_dispatch` container builds.
- Failed, cancelled, or skipped `main` container builds.
- Non-`main` container builds except the existing sync-triggered `dx -> testing` continuation.

## Error Handling

If a branch sync updates or confirms alignment of the target branch but cannot dispatch the target container build, the sync job should fail. Dispatching the target build is part of the same-day update contract.

If a merge conflicts, the sync workflow should open or reuse `sync/<source>-to-<target>` and skip the target build. The open PR is the visible stale-stream signal.

Concurrency should continue preventing duplicate same-ref container builds from racing, but the workflow design should avoid starting two `testing` builds for the same promotion chain.

## Testing

Static tests should verify:

- `sync-streams.yml` automatic jobs allow `push` and `schedule` workflow-run events.
- `sync-streams.yml` automatic jobs still require successful `main` container workflow runs.
- `sync-streams.yml` keeps manual `workflow_dispatch` sync support.
- `sync-one-stream.yml` dispatches target builds after pushed and no-op alignments.
- `sync-one-stream.yml` does not dispatch target builds when a conflict PR is opened or reused.
- `build.yml` continues only sync-triggered `dx` builds into `dx -> testing`.
- `build-disk.yml` remains limited to successful `main` push/schedule container builds.

## Non-Goals

- Do not promote downstream streams from manual `main` container builds.
- Do not replace the chained branch-promotion model with a central matrix orchestrator.
- Do not add PAT or GitHub App credentials.
- Do not build disk images for `dx`, `testing`, or `beta`.
