#!/usr/bin/env bash
# Sync ublue-os/image-template into this branch using the reviewed policy.
#
# Policy:
#   * Everything upstream-managed merges normally.
#   * Conflicting files in the owned list are resolved with "ours" and the
#     upstream delta is captured under docs/operations/upstream-drift/.
#   * Any conflict outside the owned list aborts the merge and is reported.
#
# The script never pushes. CI runs it and opens the pull request; locally it
# leaves a committed sync branch for review.

set -euo pipefail

readonly DEFAULT_UPSTREAM_URL="https://github.com/ublue-os/image-template.git"
readonly DEFAULT_UPSTREAM_REF="main"
readonly DEFAULT_REPORT_DIR="docs/operations/upstream-drift"
readonly DEFAULT_LEDGER="docs/operations/upstream-template.md"

OWNED_FILES=(
  ".github/workflows/build.yml"
  "README.md"
)

UPSTREAM_URL="${DEFAULT_UPSTREAM_URL}"
UPSTREAM_REF="${DEFAULT_UPSTREAM_REF}"
BASE_BRANCH=""
SYNC_BRANCH=""
REPORT_DIR="${DEFAULT_REPORT_DIR}"
LEDGER="${DEFAULT_LEDGER}"
STREAM=""
DRY_RUN=false
UPDATE_LEDGER=true

RUN_DATE="$(date -u +%Y-%m-%d)"
RUN_STAMP="$(date -u +%Y%m%d)"

RESULT=""
UPSTREAM_SHA=""
MERGE_BASE=""
SYNC_BRANCH_CREATED=false
PATCH_FILE=""
PATCH_TMP_DIR=""
CONFLICT_REPORT=""
CONFLICTS=()
NON_OWNED=()

usage() {
  cat <<'EOF'
Usage: scripts/upstream-sync.sh [options]

Merge ublue-os/image-template into the current (or --base) branch using the
reviewed owned-file policy.

Options:
  --base <branch>        Branch to sync (default: current branch)
  --stream <name>        Ledger stream label (default: base branch)
  --sync-branch <name>   Sync branch name (default: upstream-sync/<base>/<date>)
  --upstream-url <url>   Upstream repository URL
  --upstream-ref <ref>   Upstream branch (default: main)
  --owned <path>         Add an owned path (repeatable)
  --report-dir <dir>     Drift patch directory
  --ledger <path>        Ledger file
  --no-ledger            Do not update the ledger
  --dry-run              Classify and report, then abort every change
  -h, --help             Show this help

Exit codes: 0 merged/aligned/resolved, 2 blocked by a non-owned conflict,
1 configuration or git error.
EOF
}

log() {
  printf '%s\n' "$*" >&2
}

fail() {
  log "error: $*"
  exit 1
}

emit() {
  local key="$1"
  local value="$2"
  printf '%s=%s\n' "${key}" "${value}"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s=%s\n' "${key}" "${value}" >>"${GITHUB_OUTPUT}"
  fi
}

write_summary() {
  if [[ -z "${GITHUB_STEP_SUMMARY:-}" ]]; then
    return 0
  fi
  {
    printf '## Upstream sync: `%s`\n\n' "${BASE_BRANCH}"
    printf -- '- Result: `%s`\n' "${RESULT}"
    printf -- '- Upstream: `%s` (`%s`)\n' "${UPSTREAM_SHA}" "${UPSTREAM_REF}"
    printf -- '- Merge base: `%s`\n' "${MERGE_BASE}"
    printf -- '- Sync branch: `%s`\n' "${SYNC_BRANCH}"
    printf -- '- Dry run: `%s`\n' "${DRY_RUN}"
    if ((${#CONFLICTS[@]})); then
      printf -- '- Conflicted paths:\n'
      printf -- '  - `%s`\n' "${CONFLICTS[@]}"
    fi
    if ((${#NON_OWNED[@]})); then
      printf -- '- Non-owned conflicts (policy abort):\n'
      printf -- '  - `%s`\n' "${NON_OWNED[@]}"
    fi
    if [[ -n "${PATCH_FILE}" ]]; then
      printf -- '- Drift patch: `%s`\n' "${PATCH_FILE}"
    fi
    if [[ -n "${CONFLICT_REPORT}" ]]; then
      printf -- '- Conflict report: `%s`\n' "${CONFLICT_REPORT}"
    fi
    printf '\n'
  } >>"${GITHUB_STEP_SUMMARY}"
}

abort_merge() {
  if [[ -f "$(git rev-parse --git-path MERGE_HEAD)" ]]; then
    git merge --abort
  fi
}

is_owned() {
  local path="$1"
  local owned
  for owned in "${OWNED_FILES[@]}"; do
    if [[ "${path}" == "${owned}" ]]; then
      return 0
    fi
  done
  return 1
}

configure_identity() {
  if ! git config user.name >/dev/null 2>&1; then
    git config user.name "github-actions[bot]"
  fi
  if ! git config user.email >/dev/null 2>&1; then
    git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  fi
}

update_ledger() {
  local row="$1"
  local marker="<!-- upstream-sync:rows:${STREAM:-${BASE_BRANCH}} -->"
  local tmp

  if [[ "${UPDATE_LEDGER}" != true ]]; then
    return 0
  fi
  if [[ ! -f "${LEDGER}" ]]; then
    log "warning: ledger ${LEDGER} not found; skipping ledger update"
    return 0
  fi

  tmp="$(mktemp)"
  awk -v row="${row}" -v marker="${marker}" '
    index($0, marker) == 1 {
      print
      print row
      found = 1
      next
    }
    { print }
    END {
      if (!found) {
        exit 3
      }
    }
  ' "${LEDGER}" >"${tmp}" || {
    rm -f "${tmp}"
    fail "ledger marker ${marker} is missing from ${LEDGER}"
  }
  cat "${tmp}" >"${LEDGER}"
  rm -f "${tmp}"
}

write_patch() {
  local patch_dir="$1"
  shift
  local owned_paths=("$@")
  local patch_path="${patch_dir}/${RUN_DATE}.patch"

  mkdir -p "${patch_dir}"
  {
    printf '# Upstream drift for downstream-owned files\n'
    printf '# stream: %s\n' "${STREAM:-${BASE_BRANCH}}"
    printf '# upstream: %s\n' "${UPSTREAM_SHA}"
    printf '# merge-base: %s\n' "${MERGE_BASE}"
    printf '# date: %s\n' "${RUN_DATE}"
    printf '#\n'
    printf '# Downstream-owned content is retained in the branch; this patch is\n'
    printf '# the upstream delta that was NOT applied and needs review.\n'
    git diff --binary "${MERGE_BASE}" "${UPSTREAM_SHA}" -- "${owned_paths[@]}"
  } >"${patch_path}"
  printf '%s\n' "${patch_path}"
}

write_conflict_report() {
  local report_dir="$1"
  shift
  local conflicted=("$@")
  local report_path="${report_dir}/${RUN_DATE}-conflicts.md"

  mkdir -p "${report_dir}"
  {
    printf '# Upstream sync blocked: `%s`\n\n' "${BASE_BRANCH}"
    printf 'The reviewed sync policy aborted because a path outside the owned\n'
    printf 'list conflicts. Do not resolve these automatically.\n\n'
    printf -- '- Date: `%s`\n' "${RUN_DATE}"
    printf -- '- Upstream: `%s` (`%s`)\n' "${UPSTREAM_SHA}" "${UPSTREAM_REF}"
    printf -- '- Merge base: `%s`\n' "${MERGE_BASE}"
    printf -- '- Owned files: %s\n\n' "$(printf '`%s` ' "${OWNED_FILES[@]}")"
    printf '## Conflicted paths\n\n'
    printf -- '- `%s`\n' "${conflicted[@]}"
    printf '\n## Next steps\n\n'
    printf '1. Classify each non-owned conflict as upstream-managed or owned.\n'
    printf '2. If upstream-managed, resolve it in a manual sync branch.\n'
    printf '3. If owned, add it to the owned list in the workflow, the helper\n'
    printf '   script, and `docs/operations/upstream-template.md` first.\n'
    printf '4. Re-run the workflow. Never force an automatic `ours` resolution\n'
    printf '   outside the owned list.\n'
  } >"${report_path}"
  printf '%s\n' "${report_path}"
}

while (($#)); do
  case "$1" in
    --base)
      BASE_BRANCH="${2:?--base requires a value}"
      shift 2
      ;;
    --stream)
      STREAM="${2:?--stream requires a value}"
      shift 2
      ;;
    --sync-branch)
      SYNC_BRANCH="${2:?--sync-branch requires a value}"
      shift 2
      ;;
    --upstream-url)
      UPSTREAM_URL="${2:?--upstream-url requires a value}"
      shift 2
      ;;
    --upstream-ref)
      UPSTREAM_REF="${2:?--upstream-ref requires a value}"
      shift 2
      ;;
    --owned)
      OWNED_FILES+=("${2:?--owned requires a value}")
      shift 2
      ;;
    --report-dir)
      REPORT_DIR="${2:?--report-dir requires a value}"
      shift 2
      ;;
    --ledger)
      LEDGER="${2:?--ledger requires a value}"
      shift 2
      ;;
    --no-ledger)
      UPDATE_LEDGER=false
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1 (use --help)"
      ;;
  esac
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 ||
  fail "not inside a git worktree"
if [[ -n "$(git status --porcelain)" ]]; then
  fail "working tree is not clean; commit or stash changes first"
fi

if [[ -z "${BASE_BRANCH}" ]]; then
  BASE_BRANCH="$(git branch --show-current)"
  [[ -n "${BASE_BRANCH}" ]] || fail "detached HEAD; pass --base <branch>"
fi
if ! git rev-parse --verify "${BASE_BRANCH}^{commit}" >/dev/null 2>&1; then
  fail "base branch ${BASE_BRANCH} does not exist"
fi
if [[ "$(git branch --show-current)" != "${BASE_BRANCH}" ]]; then
  git switch "${BASE_BRANCH}"
fi

if git remote get-url upstream >/dev/null 2>&1; then
  remote_url="$(git remote get-url upstream)"
  if [[ "${remote_url}" != "${UPSTREAM_URL}" && "${remote_url}" != "${UPSTREAM_URL%.git}" ]]; then
    fail "remote 'upstream' points to ${remote_url}, expected ${UPSTREAM_URL}"
  fi
else
  git remote add upstream "${UPSTREAM_URL}"
fi

log "fetching ${UPSTREAM_URL} ${UPSTREAM_REF}"
git fetch --no-tags upstream "${UPSTREAM_REF}"

UPSTREAM_TRACKING="upstream/${UPSTREAM_REF}"
UPSTREAM_SHA="$(git rev-parse "refs/remotes/${UPSTREAM_TRACKING}")"
MERGE_BASE="$(git merge-base HEAD "${UPSTREAM_TRACKING}")"
if [[ -z "${SYNC_BRANCH}" ]]; then
  SYNC_BRANCH="upstream-sync/${BASE_BRANCH}/${RUN_STAMP}"
fi

log "base: ${BASE_BRANCH} ($(git rev-parse --short HEAD))"
log "upstream: ${UPSTREAM_SHA:0:12}"
log "merge base: ${MERGE_BASE:0:12}"

if git merge-base --is-ancestor "${UPSTREAM_TRACKING}" HEAD; then
  RESULT="aligned"
  emit "result" "${RESULT}"
  emit "upstream_sha" "${UPSTREAM_SHA}"
  emit "merge_base" "${MERGE_BASE}"
  emit "sync_branch" "${SYNC_BRANCH}"
  emit "dry_run" "${DRY_RUN}"
  emit "patch" ""
  emit "conflict_report" ""
  write_summary
  log "${BASE_BRANCH} is already aligned with ${UPSTREAM_TRACKING}"
  exit 0
fi

configure_identity

if [[ "${DRY_RUN}" == true ]]; then
  log "dry run: not creating ${SYNC_BRANCH}"
else
  git switch -C "${SYNC_BRANCH}"
  SYNC_BRANCH_CREATED=true
fi

merge_status=0
git merge --no-edit --no-ff --no-commit "${UPSTREAM_TRACKING}" || merge_status=$?

if [[ "${merge_status}" -eq 0 ]]; then
  RESULT="merged"
else
  if [[ ! -f "$(git rev-parse --git-path MERGE_HEAD)" ]]; then
    fail "merge failed without a conflicted merge state"
  fi
  mapfile -t CONFLICTS < <(git diff --name-only --diff-filter=U)
  ((${#CONFLICTS[@]})) || fail "merge failed without conflicted paths"

  NON_OWNED=()
  for conflicted_path in "${CONFLICTS[@]}"; do
    if ! is_owned "${conflicted_path}"; then
      NON_OWNED+=("${conflicted_path}")
    fi
  done

  if ((${#NON_OWNED[@]})); then
    CONFLICT_REPORT="$(write_conflict_report "${REPORT_DIR}" "${CONFLICTS[@]}")"
    RESULT="blocked"
    emit "result" "${RESULT}"
    emit "upstream_sha" "${UPSTREAM_SHA}"
    emit "merge_base" "${MERGE_BASE}"
    emit "sync_branch" "${SYNC_BRANCH}"
    emit "dry_run" "${DRY_RUN}"
    emit "patch" ""
    emit "conflict_report" "${CONFLICT_REPORT}"
    emit "non_owned" "$(printf '%s,' "${NON_OWNED[@]}")"
    write_summary
    abort_merge
    if [[ "${SYNC_BRANCH_CREATED}" == true && "${DRY_RUN}" == false ]]; then
      git switch "${BASE_BRANCH}"
      git branch -D "${SYNC_BRANCH}"
    fi
    log "blocked: non-owned conflicts: ${NON_OWNED[*]}"
    log "report: ${CONFLICT_REPORT}"
    exit 2
  fi

  RESULT="resolved-owned"
  for conflicted_path in "${CONFLICTS[@]}"; do
    log "owned conflict, keeping ours: ${conflicted_path}"
    git checkout --ours -- "${conflicted_path}"
    git add -- "${conflicted_path}"
  done
fi

if [[ "${RESULT}" == "resolved-owned" ]]; then
  if [[ "${DRY_RUN}" == true ]]; then
    PATCH_TMP_DIR="$(mktemp -d)"
    patch_dir="${PATCH_TMP_DIR}"
  else
    patch_dir="${REPORT_DIR}"
  fi
  PATCH_FILE="$(write_patch "${patch_dir}" "${CONFLICTS[@]}")"
  log "drift patch: ${PATCH_FILE}"
  if [[ "${DRY_RUN}" == true ]]; then
    log "dry run: discarding merge and drift patch"
    rm -rf "${PATCH_TMP_DIR}"
    PATCH_TMP_DIR=""
    PATCH_FILE=""
    abort_merge
  else
    git add -- "${PATCH_FILE}"
  fi
else
  if [[ "${DRY_RUN}" == true ]]; then
    log "dry run: merge would apply cleanly"
    abort_merge
  fi
fi

emit "result" "${RESULT}"
emit "upstream_sha" "${UPSTREAM_SHA}"
emit "merge_base" "${MERGE_BASE}"
emit "sync_branch" "${SYNC_BRANCH}"
emit "dry_run" "${DRY_RUN}"
emit "patch" "${PATCH_FILE}"
emit "conflict_report" ""
write_summary

if [[ "${DRY_RUN}" == false ]]; then
  if [[ "${RESULT}" == "resolved-owned" ]]; then
    drift_cell="[\`${PATCH_FILE}\`](upstream-drift/$(basename "${PATCH_FILE}"))"
    drift_note="Owned conflicts resolved with ours: ${CONFLICTS[*]}. Drift: ${PATCH_FILE}"
  else
    drift_cell="-"
    drift_note="No owned-file conflicts."
  fi
  ledger_row="| ${RUN_DATE} | \`${UPSTREAM_SHA:0:12}\` | ${RESULT} | ${drift_cell} |"
  update_ledger "${ledger_row}"
  if [[ -f "${LEDGER}" ]]; then
    git add -- "${LEDGER}"
  fi

  git commit -m "chore(upstream): sync image-template ${UPSTREAM_SHA:0:12} into ${BASE_BRANCH}" \
    -m "Upstream: ${UPSTREAM_SHA}" \
    -m "Merge base: ${MERGE_BASE}" \
    -m "${drift_note}"
fi

if [[ "${SYNC_BRANCH_CREATED}" == true && "${DRY_RUN}" == false ]]; then
  log "sync branch ready: ${SYNC_BRANCH}"
fi
