# Stream Sync Build Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make successful `main` container builds from pushes and schedules automatically sync downstream streams and trigger their container builds, while keeping manual container builds targeted.

**Architecture:** Keep the existing chained promotion model. `build.yml` still builds containers, `build-disk.yml` still builds only `main` disks, `sync-streams.yml` starts automatic `main -> dx` and `main -> beta` syncs, and `sync-one-stream.yml` dispatches each aligned target build. The fix is limited to the automatic sync gate plus tests that encode the intended push/schedule behavior.

**Tech Stack:** GitHub Actions YAML, `gh` workflow dispatch, Python static workflow tests with `pytest`.

---

## File Structure

- Modify: `.github/workflows/sync-streams.yml`
  - Responsibility: Decide when automatic stream sync jobs run after `Build container image` completes, and preserve manual `source -> target` sync dispatch.
- Modify: `tests/test_branch_channels.py`
  - Responsibility: Static tests for branch stream workflow contracts.
- Existing, no change expected: `.github/workflows/build.yml`
  - Responsibility: Build and publish stream containers, including the existing sync-triggered `dx -> testing` continuation.
- Existing, no change expected: `.github/workflows/sync-one-stream.yml`
  - Responsibility: Merge one source branch into one target branch and dispatch the target container build after clean/no-op alignment.
- Existing, no change expected: `.github/workflows/build-disk.yml`
  - Responsibility: Build `main` disk images after successful `main` push/schedule container builds.

### Task 1: Encode Push/Schedule Sync Contract In Tests

**Files:**
- Modify: `tests/test_branch_channels.py`

- [ ] **Step 1: Replace the automatic sync workflow test with the new contract**

Replace the existing `test_sync_workflow_starts_from_scheduled_main_and_explicit_dispatch` function in `tests/test_branch_channels.py` with this function:

```python
def test_sync_workflow_starts_from_main_push_or_schedule_and_explicit_dispatch():
    workflow = _read(".github/workflows/sync-streams.yml")
    dispatch_inputs = workflow.split("workflow_dispatch:", maxsplit=1)[1].split(
        "\npermissions:", maxsplit=1
    )[0]
    source_input = dispatch_inputs.split("source:", maxsplit=1)[1].split(
        "target:", maxsplit=1
    )[0]
    target_input = dispatch_inputs.split("target:", maxsplit=1)[1]
    automatic_conditions = [
        line.strip()
        for line in workflow.splitlines()
        if line.strip().startswith("if: ${{ github.event_name == 'workflow_run'")
    ]

    assert 'workflows: ["Build container image"]' in workflow
    assert "branches: [main]" in workflow
    assert len(automatic_conditions) == 2
    for condition in automatic_conditions:
        assert "github.event.workflow_run.conclusion == 'success'" in condition
        assert "github.event.workflow_run.head_branch == 'main'" in condition
        assert "github.event.workflow_run.event == 'push'" in condition
        assert "github.event.workflow_run.event == 'schedule'" in condition
        assert "github.event.workflow_run.event == 'workflow_dispatch'" not in condition
    permissions = workflow.split("permissions:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert "actions: write" in permissions
    assert 'source: "main"' in workflow
    assert 'target: "dx"' in workflow
    assert 'target: "beta"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "- dx" in {line.strip() for line in source_input.splitlines()}
    assert "- testing" in {line.strip() for line in target_input.splitlines()}
    assert "source: ${{ inputs.source }}" in workflow
    assert "target: ${{ inputs.target }}" in workflow
```

- [ ] **Step 2: Run the focused test and verify it fails for the right reason**

Run:

```bash
python3 -m pytest tests/test_branch_channels.py::test_sync_workflow_starts_from_main_push_or_schedule_and_explicit_dispatch -q
```

Expected: FAIL because the current `sync-streams.yml` automatic conditions do not include `github.event.workflow_run.event == 'push'`.

- [ ] **Step 3: Do not edit production workflow yet if the test failure is a syntax/import error**

If the test fails because the function name is wrong, the file does not parse, or `automatic_conditions` is empty due to a test parsing bug, fix only the test and rerun Step 2 until the failure specifically points at the missing `push` event condition.

### Task 2: Allow Automatic Syncs After Main Push Builds

**Files:**
- Modify: `.github/workflows/sync-streams.yml`
- Test: `tests/test_branch_channels.py`

- [ ] **Step 1: Update `sync-main-to-dx` condition**

In `.github/workflows/sync-streams.yml`, change the `if:` for `sync-main-to-dx` from schedule-only:

```yaml
    if: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main' && github.event.workflow_run.event == 'schedule' }}
```

to push-or-schedule:

```yaml
    if: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main' && (github.event.workflow_run.event == 'push' || github.event.workflow_run.event == 'schedule') }}
```

- [ ] **Step 2: Update `sync-main-to-beta` condition**

In `.github/workflows/sync-streams.yml`, change the `if:` for `sync-main-to-beta` from schedule-only:

```yaml
    if: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main' && github.event.workflow_run.event == 'schedule' }}
```

to push-or-schedule:

```yaml
    if: ${{ github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.head_branch == 'main' && (github.event.workflow_run.event == 'push' || github.event.workflow_run.event == 'schedule') }}
```

- [ ] **Step 3: Run the focused test and verify it passes**

Run:

```bash
python3 -m pytest tests/test_branch_channels.py::test_sync_workflow_starts_from_main_push_or_schedule_and_explicit_dispatch -q
```

Expected: PASS.

### Task 3: Guard Existing Stream/Disk Contracts

**Files:**
- Test: `tests/test_branch_channels.py`
- Test indirectly: `.github/workflows/build.yml`, `.github/workflows/sync-one-stream.yml`, `.github/workflows/build-disk.yml`

- [ ] **Step 1: Run all branch-channel workflow tests**

Run:

```bash
python3 -m pytest tests/test_branch_channels.py -q
```

Expected: PASS. This confirms the changed sync gate did not break:

- `build.yml` stream tags and base images.
- sync-triggered `dx -> testing` continuation.
- `sync-one-stream.yml` target build dispatch after pushed/no-op alignment.
- conflict PR behavior without target build dispatch.
- `build-disk.yml` remaining limited to successful `main` push/schedule container builds.

- [ ] **Step 2: Run YAML-adjacent whitespace validation**

Run:

```bash
git diff --check
```

Expected: no output.

### Task 4: Full Verification And Commit

**Files:**
- Modified: `.github/workflows/sync-streams.yml`
- Modified: `tests/test_branch_channels.py`
- Existing unpushed commit: `docs/superpowers/specs/2026-05-25-stream-sync-build-automation-design.md`

- [ ] **Step 1: Run the full Python test suite**

Run:

```bash
python3 -m pytest tests -q
```

Expected: all tests pass. At the time this plan was written, the suite had one known `PyGIDeprecationWarning` from GI overrides; that warning is unrelated to this workflow change.

- [ ] **Step 2: Inspect the final diff**

Run:

```bash
git diff -- .github/workflows/sync-streams.yml tests/test_branch_channels.py
```

Expected: only the two automatic sync job conditions and the updated static test changed.

- [ ] **Step 3: Check repository status**

Run:

```bash
git status --short --branch
```

Expected: `main` is ahead of `origin/main` by at least the approved spec commit, with only `.github/workflows/sync-streams.yml` and `tests/test_branch_channels.py` modified in the working tree.

- [ ] **Step 4: Commit the workflow/test fix**

Run:

```bash
git add .github/workflows/sync-streams.yml tests/test_branch_channels.py
git commit -m "fix(ci): sync streams after main push builds"
```

Expected: a new commit containing only the workflow/test fix.

- [ ] **Step 5: Push both the spec and implementation commits**

Run:

```bash
git push origin main
```

Expected: `origin/main` advances to include the approved spec commit and the workflow/test fix commit. The push should trigger `Build container image` on `main`; after that succeeds, `Build disk images` and `Sync image streams` should both be triggered by `workflow_run`.

### Task 5: Post-Push Actions Verification

**Files:**
- No local file changes expected.

- [ ] **Step 1: Watch the `main` container build from the push**

Run:

```bash
gh run list --workflow build.yml --branch main --limit 3 --json databaseId,status,conclusion,event,headBranch,url
```

Expected: the newest `main` run has `event` set to `push`. If it is still running, watch it:

```bash
gh run watch <run-id> --exit-status
```

Expected: successful completion.

- [ ] **Step 2: Verify disk and sync workflow-run triggers appear after the main build**

Run:

```bash
gh run list --limit 10 --json databaseId,workflowName,status,conclusion,event,headBranch,url
```

Expected: after the successful `main` container build, there is a `Build disk images` run with `event=workflow_run` and a `Sync image streams` run with `event=workflow_run`.

- [ ] **Step 3: Verify downstream stream builds are dispatched**

Run:

```bash
gh run list --workflow build.yml --limit 10 --json databaseId,status,conclusion,event,headBranch,url
```

Expected: `dx` and `beta` container builds appear as `workflow_dispatch` runs. After the sync-triggered `dx` build succeeds, a `testing` container build appears as a `workflow_dispatch` run.

- [ ] **Step 4: Watch all new downstream container builds to completion**

For each new downstream run id, run:

```bash
gh run watch <run-id> --exit-status
```

Expected: `dx`, `beta`, and `testing` builds complete successfully. If one fails, use systematic debugging: inspect the failed job logs before retrying or changing code.

- [ ] **Step 5: Verify stream branches are aligned**

Run:

```bash
git fetch origin main dx testing beta
git merge-base --is-ancestor origin/main origin/dx
git merge-base --is-ancestor origin/main origin/beta
git merge-base --is-ancestor origin/dx origin/testing
```

Expected: all three `git merge-base --is-ancestor` commands exit `0`. If any command exits nonzero, inspect whether a sync conflict PR was opened for that stream.
