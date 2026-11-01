# Upstream Refresh Build Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route routine builds through already-published Adwaita-Lite Quay images while limiting upstream Universal Blue GHCR pulls to daily `main` and `beta` refresh builds.

**Architecture:** Keep routing logic in `.github/workflows/build.yml`. Scheduled builds use a matrix to build `main` and `beta` refresh targets from upstream GHCR; all push, PR, manual, and sync-triggered builds resolve their base image from Quay.

**Tech Stack:** GitHub Actions YAML, bash in workflow steps, Python pytest contract tests.

---

## File Structure

- Modify `.github/workflows/build.yml`: add a scheduled stream matrix and make `Resolve stream configuration` event-aware.
- Modify `tests/test_branch_channels.py`: update workflow contract tests so base-image routing is verified by concrete workflow strings.
- Existing `Containerfile` remains unchanged because it already accepts `BASE_IMAGE` as a build arg.

---

### Task 1: Add Failing Contract Tests For Quay-First Routing

**Files:**
- Modify: `tests/test_branch_channels.py`

- [ ] Replace `test_container_workflow_resolves_branch_tags_and_base_images` with assertions for Quay routine bases and upstream scheduled bases.
- [ ] Add `test_container_workflow_schedules_main_and_beta_upstream_refreshes` checking the schedule matrix uses `main` and `beta`.
- [ ] Add `test_container_workflow_uses_upstream_only_for_scheduled_refreshes` checking `upstream_refresh` gates upstream GHCR use.
- [ ] Run `pytest tests/test_branch_channels.py -q` and verify the new tests fail before implementation.

---

### Task 2: Implement Event-Aware Base Image Routing

**Files:**
- Modify: `.github/workflows/build.yml`
- Test: `tests/test_branch_channels.py`

- [ ] Add this event-dependent matrix after `runs-on: ubuntu-24.04`:

```yaml
    strategy:
      fail-fast: false
      matrix:
        stream: ${{ github.event_name == 'schedule' && fromJSON('["main","beta"]') || fromJSON('["main"]') }}
      max-parallel: 1
```

- [ ] Do not add a job-level `if:` referencing `matrix.stream`.
- [ ] Replace the `Resolve stream configuration` script so scheduled runs set `ref_name="${{ matrix.stream }}"` and `upstream_refresh="true"`.
- [ ] Gate the regular checkout to non-scheduled runs and add a scheduled checkout with `ref: ${{ matrix.stream }}`.
- [ ] Route routine bases as follows: `main` and `dx` to `${IMAGE_REGISTRY}/${IMAGE_NAME}:latest`, `testing` to `${IMAGE_REGISTRY}/${IMAGE_NAME}:dx`, `beta` to `${IMAGE_REGISTRY}/${IMAGE_NAME}:beta`.
- [ ] Route upstream refresh bases as follows: `latest` to `ghcr.io/ublue-os/base-main:latest`, `beta` to `ghcr.io/ublue-os/base-main:beta`.
- [ ] Run `pytest tests/test_branch_channels.py -q` and verify all focused tests pass.

---

### Task 3: Verify Full Suite And Commit

**Files:**
- Verify: `.github/workflows/build.yml`
- Verify: `tests/test_branch_channels.py`

- [ ] Run `pytest -q`; expected all tests pass with only the known `PyGIDeprecationWarning` if present.
- [ ] Run `git diff --check`; expected no output.
- [ ] Inspect `git status --short`, the intended diff, and `git log --oneline -10`.
- [ ] Commit with `git commit -m "fix(ci): route routine builds through quay"` including workflow, tests, spec, and plan.

---

### Task 4: Post-Push Verification

**Files:**
- Verify: GitHub Actions `Build container image`
- Verify: `.github/workflows/sync-streams.yml` behavior remains compatible

- [ ] Push only if requested or already authorized.
- [ ] Find the new main push build with `gh run list --workflow build.yml --branch main --limit 5 --json databaseId,status,conclusion,event,headBranch,headSha,createdAt,url`.
- [ ] Watch it with `gh run watch <run-id> --exit-status`.
- [ ] Expected for a push build: `Resolve stream configuration` uses `BASE_IMAGE=ghcr.io/adwaita-blue-lite/adwaita-lite:latest`, not `ghcr.io/ublue-os/base-main:latest`.
