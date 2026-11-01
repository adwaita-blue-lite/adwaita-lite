# Upstream Refresh Build Routing Design

## Goal

Reduce pulls from Universal Blue GHCR base images so routine development and stream builds use already-published Adwaita-Lite images from Quay. Only daily upstream refresh builds should pull from `ghcr.io/ublue-os/base-main`.

## Current Problem

Every stream currently resolves its `BASE_IMAGE` directly to a Universal Blue image:

- `main`, `dx`, and `testing` use `ghcr.io/ublue-os/base-main:latest`.
- `beta` uses `ghcr.io/ublue-os/base-main:beta`.

This means pushes, manual runs, PR validation, and sync-triggered stream builds all pull large upstream layers. When GHCR or the upstream package hits egress limits, unrelated development builds fail before they can publish to Quay.

## Desired Behavior

Daily scheduled refresh builds are the only normal builds that pull from upstream Universal Blue images:

- Scheduled `main` refresh uses `ghcr.io/ublue-os/base-main:latest` and publishes `latest`, `latest.YYYYMMDD`, and `YYYYMMDD`.
- Scheduled `beta` refresh uses `ghcr.io/ublue-os/base-main:beta` and publishes `beta` and `beta.YYYYMMDD`.

All other builds use Adwaita-Lite images from Quay:

- Non-scheduled `main` builds use `ghcr.io/adwaita-blue-lite/adwaita-lite:latest`.
- `dx` builds use `ghcr.io/adwaita-blue-lite/adwaita-lite:latest`.
- `testing` builds use `ghcr.io/adwaita-blue-lite/adwaita-lite:dx`.
- Non-refresh `beta` builds use `ghcr.io/adwaita-blue-lite/adwaita-lite:beta`.

This keeps normal builds tied to the last successfully published Adwaita-Lite base while still refreshing from upstream once per day.

## Workflow Design

Keep the implementation in `.github/workflows/build.yml`.

The `Resolve stream configuration` step should become event-aware:

- Determine the effective stream from the PR target branch, branch ref, dispatch input, or scheduled matrix value.
- Determine whether the run is an upstream refresh.
- Use upstream GHCR only when the run is a scheduled refresh for `main` or `beta`.
- Use Quay for all other stream base images.

Scheduled builds need to cover both `main` and `beta`. The preferred design is a scheduled matrix in the existing build workflow rather than a separate dispatcher workflow. The matrix provides the stream value for scheduled runs, so one daily schedule can build both upstream refresh targets.

GitHub scheduled workflows start from the default branch, so scheduled matrix jobs must explicitly checkout the matrix stream branch before building. This keeps the scheduled `beta` refresh from publishing a `beta` image built from default-branch source.

## Stream Promotion

Existing stream promotion remains compatible:

- Successful scheduled `main` builds continue to trigger `main -> dx` and `main -> beta` syncs.
- Sync-triggered `dx` builds use the freshly published `latest` image from Quay.
- Sync-triggered `beta` builds use the beta image from Quay unless they are the daily scheduled beta refresh.
- Successful sync-triggered `dx` builds continue `dx -> testing`, and `testing` builds from the published `dx` image.

Push-triggered `main` builds still test and publish code changes, but they no longer refresh from Universal Blue. They build from the current published `latest` image.

The daily schedule may publish `beta` from the upstream beta refresh and then later publish `beta` again from the sync-triggered beta build. That follow-up build should use the newly refreshed Quay `beta` image as its base, so it preserves the upstream beta refresh while applying the current synced repository content.

## First-Build Assumption

The design assumes these Quay tags already exist:

- `latest`
- `dx`
- `testing`
- `beta`

They exist from previous successful builds. If a tag is deleted later, the relevant non-refresh build will fail until the tag is restored or a refresh run republishes it.

## Testing

Update workflow contract tests to verify base-image routing:

- Scheduled `main` refresh uses `ghcr.io/ublue-os/base-main:latest`.
- Scheduled `beta` refresh uses `ghcr.io/ublue-os/base-main:beta`.
- Non-scheduled `main` uses `ghcr.io/adwaita-blue-lite/adwaita-lite:latest`.
- `dx` uses `ghcr.io/adwaita-blue-lite/adwaita-lite:latest`.
- `testing` uses `ghcr.io/adwaita-blue-lite/adwaita-lite:dx`.
- Non-refresh `beta` uses `ghcr.io/adwaita-blue-lite/adwaita-lite:beta`.

Run the focused workflow tests and the full test suite before pushing.

## Non-Goals

- Do not add a new registry or mirror workflow.
- Do not change the final publish target from Quay.
- Do not change disk image build behavior.
- Do not remove the existing stream sync architecture.
