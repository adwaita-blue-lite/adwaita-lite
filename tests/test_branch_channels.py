import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _resolve_stream_script(workflow: str) -> str:
    assert "- name: Resolve stream configuration" in workflow
    return workflow.split("- name: Resolve stream configuration", maxsplit=1)[1].split(
        "\n      - name:", maxsplit=1
    )[0]


def _shell_case_block(script: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}\)\n(?P<block>.*?)^\s*;;", script, re.M | re.S)
    assert match is not None, f"missing {label}) case block"
    return match.group("block")


def _schedule_event_block(script: str) -> str:
    marker = 'if [[ "${GITHUB_EVENT_NAME}" == "schedule" ]]; then'
    assert marker in script
    return script.split(marker, maxsplit=1)[1].split("\n          fi", maxsplit=1)[0]


def _workflow_step_block(workflow: str, name: str) -> str:
    marker = f"- name: {name}"
    assert marker in workflow
    return workflow.split(marker, maxsplit=1)[1].split("\n      - name:", maxsplit=1)[0]


def test_containerfile_base_image_is_build_arg_with_latest_default():
    containerfile = _read("Containerfile")

    assert 'ARG BASE_IMAGE="ghcr.io/ublue-os/base-main:latest"' in containerfile
    assert "FROM ${BASE_IMAGE}" in containerfile
    assert "FROM ghcr.io/ublue-os/base-main:latest" not in containerfile


def test_containerfile_base_image_arg_is_global_for_buildah():
    lines = _read("Containerfile").splitlines()
    base_arg_index = lines.index('ARG BASE_IMAGE="ghcr.io/ublue-os/base-main:latest"')
    first_from_index = next(
        index for index, line in enumerate(lines) if line.startswith("FROM ")
    )

    assert base_arg_index < first_from_index


def test_containerfile_normalizes_opt_for_symlink_or_directory_bases():
    containerfile = _read("Containerfile")

    assert "RUN rm -rf /opt && mkdir /opt" in containerfile
    assert "RUN rm /opt && mkdir /opt" not in containerfile


def test_container_workflow_builds_all_stream_branches_and_pr_targets():
    workflow = _read(".github/workflows/build.yml")

    for branch in ("main", "dx", "testing", "beta"):
        assert f"      - {branch}" in workflow

    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "workflow_dispatch:" in workflow


def test_container_workflow_schedules_main_and_beta_upstream_refreshes():
    workflow = _read(".github/workflows/build.yml")

    assert "name: Build and push image (${{ matrix.stream }})" in workflow
    assert "strategy:" in workflow
    strategy = workflow.split("strategy:", maxsplit=1)[1].split("\n    steps:", maxsplit=1)[0]

    assert "max-parallel: 1" in strategy
    assert "matrix:" in strategy
    assert "stream: ${{ github.event_name == 'schedule' && fromJSON('[\"main\",\"beta\"]') || fromJSON('[\"main\"]') }}" in strategy


def test_container_workflow_scheduled_builds_checkout_matrix_stream():
    workflow = _read(".github/workflows/build.yml")

    regular_checkout = _workflow_step_block(workflow, "Checkout")
    scheduled_checkout = _workflow_step_block(workflow, "Checkout scheduled stream")

    assert "if: github.event_name != 'schedule'" in regular_checkout
    assert "if: github.event_name == 'schedule'" in scheduled_checkout
    assert "ref: ${{ matrix.stream }}" in scheduled_checkout


def test_container_workflow_metadata_uses_checked_out_source_revision():
    workflow = _read(".github/workflows/build.yml")

    checkout_index = workflow.index("- name: Checkout")
    source_index = workflow.index("- name: Resolve source revision")
    metadata_index = workflow.index("- name: Image Metadata")
    source_step = _workflow_step_block(workflow, "Resolve source revision")
    metadata_step = _workflow_step_block(workflow, "Image Metadata")

    assert checkout_index < source_index < metadata_index
    assert "id: source" in source_step
    assert "git rev-parse HEAD" in source_step
    assert 'echo "revision=$(git rev-parse HEAD)" >> "${GITHUB_OUTPUT}"' in source_step
    assert "steps.source.outputs.revision" in metadata_step
    for label in (
        "io.artifacthub.package.readme-url",
        "org.opencontainers.image.documentation",
        "org.opencontainers.image.source",
        "org.opencontainers.image.url",
    ):
        line = next(
            line for line in metadata_step.splitlines() if line.strip().startswith(f"{label}=")
        )
        assert "${{ steps.source.outputs.revision }}" in line
        assert "${{ github.sha }}" not in line


def test_container_workflow_resolves_branch_tags_and_base_images():
    workflow = _read(".github/workflows/build.yml")
    stream_script = _resolve_stream_script(workflow)

    main_block = _shell_case_block(stream_script, "main")
    dx_block = _shell_case_block(stream_script, "dx")
    testing_block = _shell_case_block(stream_script, "testing")
    beta_block = _shell_case_block(stream_script, "beta")

    assert "id: stream" in stream_script
    assert 'ref_name="${GITHUB_BASE_REF}"' in stream_script
    assert "BASE_IMAGE=${{ steps.stream.outputs.base_image }}" in workflow
    assert 'tag="latest"' in main_block
    assert 'base_image="${IMAGE_REGISTRY}/${IMAGE_NAME}:latest"' in main_block
    assert 'tag="dx"' in dx_block
    assert 'base_image="${IMAGE_REGISTRY}/${IMAGE_NAME}:latest"' in dx_block
    assert 'tag="testing"' in testing_block
    assert 'base_image="${IMAGE_REGISTRY}/${IMAGE_NAME}:dx"' in testing_block
    assert 'tag="beta"' in beta_block
    assert 'base_image="${IMAGE_REGISTRY}/${IMAGE_NAME}:beta"' in beta_block


def test_container_workflow_uses_upstream_only_for_scheduled_refreshes():
    workflow = _read(".github/workflows/build.yml")
    stream_script = _resolve_stream_script(workflow)
    upstream_marker = 'if [[ "${upstream_refresh}" == "true" ]]; then'
    schedule_block = _schedule_event_block(stream_script)

    assert 'upstream_refresh="false"' in stream_script
    assert 'if [[ "${GITHUB_EVENT_NAME}" == "schedule" ]]; then' in stream_script
    assert 'upstream_refresh="true"' in stream_script
    assert 'ref_name="${{ matrix.stream }}"' in schedule_block
    assert upstream_marker in stream_script

    upstream_block = stream_script.split(upstream_marker, maxsplit=1)[1].split(
        "\n          fi", maxsplit=1
    )[0]
    bootstrap_marker = "# Bootstrap guard:"
    assert bootstrap_marker in stream_script
    bootstrap_block = stream_script.split(bootstrap_marker, maxsplit=1)[1]
    case_routing = stream_script.replace(upstream_block, "").replace(bootstrap_block, "")

    assert 'case "${tag}" in' in upstream_block
    assert 'latest) base_image="ghcr.io/ublue-os/base-main:latest" ;;' in upstream_block
    assert 'beta) base_image="ghcr.io/ublue-os/base-main:beta" ;;' in upstream_block
    assert "ghcr.io/ublue-os/base-main" not in case_routing


def test_container_workflow_bootstraps_missing_stream_bases():
    workflow = _read(".github/workflows/build.yml")
    stream_script = _resolve_stream_script(workflow)
    bootstrap_block = stream_script.split("# Bootstrap guard:", maxsplit=1)[1]

    assert 'skopeo inspect "docker://${base_image}"' in bootstrap_block
    assert 'beta) base_image="ghcr.io/ublue-os/base-main:beta" ;;' in bootstrap_block
    assert '*) base_image="ghcr.io/ublue-os/base-main:latest" ;;' in bootstrap_block


def test_container_workflow_tags_are_branch_aware():
    workflow = _read(".github/workflows/build.yml")

    assert "type=raw,value=${{ steps.stream.outputs.tag }},enable=${{ steps.stream.outputs.publish == 'true' }}" in workflow
    assert "type=raw,value=${{ steps.stream.outputs.tag }}.{{date 'YYYYMMDD'}},enable=${{ steps.stream.outputs.publish == 'true' }}" in workflow
    assert "type=raw,value={{date 'YYYYMMDD'}},enable=${{ steps.stream.outputs.include_date_alias == 'true' }}" in workflow
    assert "org.opencontainers.image.version=${{ steps.stream.outputs.tag }}.{{date 'YYYYMMDD'}}" in workflow


def test_container_workflow_publishes_only_stream_branches():
    workflow = _read(".github/workflows/build.yml")

    assert "if: steps.stream.outputs.publish == 'true'" in workflow
    assert "github.event.repository.default_branch" not in workflow


def test_container_workflow_uses_inline_space_cleanup_to_avoid_action_downloads():
    workflow = _read(".github/workflows/build.yml")

    assert "ublue-os/remove-unwanted-software" not in workflow
    assert "Removing unwanted software" in workflow
    assert "sudo rm -rf ${verbose} /usr/share/dotnet" in workflow
    assert "sudo docker image prune --all --force" in workflow
    assert "sudo apt-get autoremove -y" in workflow


def test_container_workflow_uses_github_hosted_runner_for_action_downloads():
    workflow = _read(".github/workflows/build.yml")

    assert "runs-on: ubuntu-24.04" in workflow
    assert "runs-on: ubicloud-premium-8-ubuntu-2404" not in workflow


def test_disk_workflow_manual_runs_can_choose_stream_tag():
    workflow = _read(".github/workflows/build-disk.yml")

    assert "image-tag:" in workflow
    assert "type: choice" in workflow
    for tag in ("latest", "dx", "testing", "beta"):
        assert f"          - {tag}" in workflow
    assert 'echo "IMAGE_TAG=${IMAGE_TAG}" >> ${GITHUB_ENV}' in workflow
    assert "${{ env.IMAGE_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ env.IMAGE_TAG }}" in workflow


def test_disk_workflow_runs_after_successful_main_push_or_schedule_container_build():
    workflow = _read(".github/workflows/build-disk.yml")

    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.event == 'push'" in workflow
    assert "github.event.workflow_run.event == 'schedule'" in workflow


def test_build_workflow_accepts_sync_promotion_dispatch_input():
    workflow = _read(".github/workflows/build.yml")
    dispatch_inputs = workflow.split("workflow_dispatch:", maxsplit=1)[1].split(
        "\nenv:", maxsplit=1
    )[0]

    assert "workflow_dispatch:" in workflow
    dispatch_lines = dispatch_inputs.splitlines()
    inputs_start = [
        index for index, line in enumerate(dispatch_lines) if line.strip() == "inputs:"
    ]
    assert inputs_start
    sync_promotion_start = [
        index
        for index, line in enumerate(dispatch_lines)
        if line.strip() == "sync_promotion:"
    ]
    assert sync_promotion_start
    assert inputs_start[0] < sync_promotion_start[0]
    start = sync_promotion_start[0]
    inputs_indent = len(dispatch_lines[inputs_start[0]]) - len(
        dispatch_lines[inputs_start[0]].lstrip()
    )
    input_indent = len(dispatch_lines[start]) - len(dispatch_lines[start].lstrip())
    assert input_indent > inputs_indent
    block_lines = [dispatch_lines[start]]
    for line in dispatch_lines[start + 1 :]:
        indent = len(line) - len(line.lstrip())
        if line.strip() and indent <= input_indent:
            break
        block_lines.append(line)
    sync_promotion = "\n".join(block_lines)

    assert 'description: "Internal stream sync promotion"' in sync_promotion
    assert "required: false" in sync_promotion
    assert "type: boolean" in sync_promotion
    assert "default: false" in sync_promotion


def test_build_workflow_continues_only_sync_triggered_dx_promotion():
    workflow = _read(".github/workflows/build.yml")

    permissions = workflow.split("permissions:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert "actions: write" in permissions
    assert "Continue sync promotion" in workflow
    step = workflow.split("- name: Continue sync promotion", maxsplit=1)[1].split(
        "\n      - name:", maxsplit=1
    )[0]
    condition = step.split("if:", maxsplit=1)[1].split("\n", maxsplit=1)[0].strip()
    if condition.startswith("${{") and condition.endswith("}}"):
        condition = condition.removeprefix("${{").removesuffix("}}").strip()
    condition = " ".join(condition.split())
    expected_condition = (
        "github.event_name == 'workflow_dispatch' && "
        "inputs.sync_promotion == true && "
        "steps.stream.outputs.tag == 'dx' && "
        "steps.stream.outputs.publish == 'true'"
    )

    assert condition == expected_condition
    assert "gh workflow run sync-streams.yml" in step
    assert "--ref main" in step
    assert "-f source=dx" in step
    assert "-f target=testing" in step


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
    scheduled_check = workflow.split("check-scheduled-main-build:", maxsplit=1)[1].split(
        "\n  sync-main-to-dx:", maxsplit=1
    )[0]

    assert 'workflows: ["Build container image"]' in workflow
    assert "branches: [main]" in workflow
    assert "name: Check scheduled main build" in scheduled_check
    assert "github.event.workflow_run.event == 'schedule'" in scheduled_check
    assert "main_success:" in scheduled_check
    assert "gh api" in scheduled_check
    assert 'repos/${{ github.repository }}/actions/runs/${{ github.event.workflow_run.id }}/jobs' in scheduled_check
    assert 'Build and push image (main)' in scheduled_check
    assert len(automatic_conditions) == 2
    for condition in automatic_conditions:
        assert "always()" in condition
        assert "github.event.workflow_run.head_branch == 'main'" in condition
        assert "github.event.workflow_run.event == 'push' && github.event.workflow_run.conclusion == 'success'" in condition
        assert "github.event.workflow_run.event == 'schedule' && needs.check-scheduled-main-build.outputs.main_success == 'true'" in condition
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


def test_sync_one_stream_dispatches_target_build_after_alignment():
    reusable = _read(".github/workflows/sync-one-stream.yml")

    permissions = reusable.split("permissions:", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]
    assert "actions: write" in permissions
    assert "git merge --no-edit" in reusable
    assert "dispatch_target_build()" in reusable
    dispatch_helper = reusable.split("dispatch_target_build()", maxsplit=1)[1].split(
        "Already aligned ${TARGET_BRANCH}", maxsplit=1
    )[0]
    assert "gh workflow run build.yml" in dispatch_helper
    assert '--ref "${TARGET_BRANCH}"' in dispatch_helper
    assert "-f sync_promotion=true" in dispatch_helper

    assert "Already aligned ${TARGET_BRANCH}" in reusable
    no_op_path = reusable.split("Already aligned ${TARGET_BRANCH}", maxsplit=1)[1].split(
        "exit 0", maxsplit=1
    )[0]
    no_op_commands = {
        line.strip()
        for line in no_op_path.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "dispatch_target_build" in no_op_commands
    assert "Pushed ${TARGET_BRANCH}" in reusable
    pushed_path = reusable.split("Pushed ${TARGET_BRANCH}", maxsplit=1)[1].split(
        "exit 0", maxsplit=1
    )[0]
    pushed_commands = {
        line.strip()
        for line in pushed_path.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert "dispatch_target_build" in pushed_commands

    assert "git merge --abort" in reusable
    conflict_path = reusable.split("git merge --abort", maxsplit=1)[1]
    assert "existing_pr_url=$(gh pr list" in conflict_path
    assert "Sync PR already exists" in conflict_path
    assert "dispatch skipped" in conflict_path
    assert 'PR_BRANCH="sync/${SOURCE_BRANCH}-to-${TARGET_BRANCH}"' in conflict_path
    assert 'git checkout -B "${PR_BRANCH}" "origin/${SOURCE_BRANCH}"' in conflict_path
    assert "gh pr create" in conflict_path
    pr_create = conflict_path.split("gh pr create", maxsplit=1)[1]
    assert "target build dispatch skipped" in pr_create
    assert "Opened sync PR for ${SOURCE_BRANCH} -> ${TARGET_BRANCH}; dispatch skipped." in pr_create


def test_latest_stream_exposes_devmode_rebase_recipe():
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert "devmode:" in justfile
    assert "toggle-devmode:" in justfile
    assert "@ujust toggle-devmode" in justfile
    assert "gum confirm \"Would you like to enable developer mode?\"" in justfile
    assert "gum confirm \"Would you like to disable developer mode?\"" in justfile
    assert "pkexec bootc switch --enforce-container-sigpolicy" in justfile
    assert "ghcr.io/adwaita-blue-lite/adwaita-lite:dx" in justfile
    assert "ghcr.io/adwaita-blue-lite/adwaita-lite:latest" in justfile
    assert "ostree-image-signed:docker://ghcr.io/adwaita-blue-lite/adwaita-lite:dx" not in justfile
    assert "ostree-image-signed:docker://ghcr.io/adwaita-blue-lite/adwaita-lite:latest" not in justfile
    assert "rpm-ostree rebase" not in justfile
    assert "quay.io/" not in justfile


def test_devmode_installs_upstream_dialog_dependency():
    build_script = _read("build_files/build.sh")
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")

    assert "gum confirm" in justfile
    assert "    gum \\" in build_script


def test_dx_group_uses_image_managed_group_entries():
    build_script = _read("build_files/build.sh")
    justfile = _read("files/usr/share/ublue-os/just/90-adwaita-lite.just")
    sysusers = _read("files/usr/lib/sysusers.d/adwaita-lite-dx.conf")

    assert "dx-group:" in justfile
    assert "groupadd --system" not in justfile
    assert "grep \"^${group_name}:\" /usr/lib/group >> /etc/group" in justfile
    assert "dx_groups=(docker incus-admin libvirt dialout)" not in build_script
    assert "groupadd --system \"$group_name\"" not in build_script
    assert "grep \"^${group_name}:\" /etc/group >> /usr/lib/group" not in build_script
    for group in ("docker", "incus-admin", "libvirt", "dialout"):
        assert f"g {group} -" in sysusers


def test_readme_stream_switches_use_bootc_registry_refs():
    readme = _read("README.md")
    stream_switch_docs = readme.split("### Switch streams", maxsplit=1)[1].split(
        "## Installer wizard", maxsplit=1
    )[0]

    assert "pkexec bootc switch --enforce-container-sigpolicy ghcr.io/adwaita-blue-lite/adwaita-lite:dx" in stream_switch_docs
    assert "bootc switch --enforce-container-sigpolicy ostree-image-signed" not in stream_switch_docs


def test_build_regenerates_current_ublue_ujust_entrypoint():
    build_script = _read("build_files/build.sh")

    assert "/usr/share/ublue-os/just/00-entry.just" in build_script
    assert "find /usr/share/ublue-os/just" in build_script
    assert "! -name '60-custom.just'" in build_script
    assert "import \"/usr/share/ublue-os/just/%s\"" in build_script
