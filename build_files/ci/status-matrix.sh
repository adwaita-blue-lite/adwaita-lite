#!/usr/bin/env bash
# Regenerate docs/operations/status-matrix.md from live GitHub and registry state.
set -euo pipefail

REPO="${REPO:-adwaita-blue-lite/adwaita-lite}"
REGISTRY="${REGISTRY:-ghcr.io/adwaita-blue-lite/adwaita-lite}"
KEY="${KEY:-cosign.pub}"
BRANCHES=(main dx testing beta)
TAGS=(latest dx testing beta)

now="$(date -u +%Y-%m-%dT%H:%MZ)"

pkg_visibility="$(gh api "/orgs/${REPO%%/*}/packages/container/${REPO##*/}" \
    --jq '.visibility' 2>/dev/null || echo unknown)"
sync_run="$(gh run list -R "${REPO}" -w upstream-sync.yml -L1 \
    --json conclusion,url \
    --jq '.[0] | (if (.conclusion == null or .conclusion == "") then "in progress" else .conclusion end) + " [" + .url + "]"' 2>/dev/null || echo unknown)"
if gh api "repos/${REPO}/branches/main/protection" >/dev/null 2>&1; then
    protection="present"
else
    protection="absent"
fi
if [[ -f .github/workflows/ci.yml ]]; then
    ci_state="present"
else
    ci_state="absent"
fi

cat <<EOF
# Status matrix

**Snapshot:** ${now}
**Regenerate:** \`build_files/ci/status-matrix.sh > docs/operations/status-matrix.md\`

This matrix records what is actually evidenced. \`unknown\` and \`no evidence\` are
deliberate values, not placeholders to be filled with assumptions.

| Branch | Tip | Latest build | Stream digest | Signature | Boot |
|---|---|---|---|---|---|
EOF

for i in "${!BRANCHES[@]}"; do
    branch="${BRANCHES[$i]}"
    tag="${TAGS[$i]}"

    sha="$(git ls-remote "https://github.com/${REPO}.git" "refs/heads/${branch}" | awk '{print substr($1, 1, 7)}')"
    [[ -n "${sha}" ]] || sha="unknown"

    run="$(gh run list -R "${REPO}" -w build.yml -b "${branch}" -L1 \
        --json databaseId,conclusion,url \
        --jq '.[0] | "[" + (.databaseId|tostring) + "](" + .url + ") (" + (if (.conclusion == null or .conclusion == "") then "in progress" else .conclusion end) + ")"' 2>/dev/null || true)"
    [[ -n "${run}" ]] || run="unknown"

    digest="$(skopeo inspect --no-tags "docker://${REGISTRY}:${tag}" \
        --format '{{.Digest}}' 2>/dev/null | cut -c1-19 || true)"
    [[ -n "${digest}" ]] || digest="unknown"

    if cosign verify --key "${KEY}" "${REGISTRY}:${tag}" >/dev/null 2>&1; then
        signature="verified"
    else
        signature="unknown"
    fi

    printf '| `%s` | `%s` | %s | `%s` | %s | no evidence |\n' \
        "${branch}" "${sha}" "${run}" "${digest}" "${signature}"
done

cat <<EOF

## Other state

| Check | State | Evidence |
|---|---|---|
| GHCR package visibility | **${pkg_visibility}** | registry API; anonymous pull test |
| Upstream sync | ${sync_run} | latest \`upstream-sync\` run |
| CI test/lint workflow | ${ci_state} | \`.github/workflows/ci.yml\` |
| Branch protection | ${protection} | \`repos/${REPO}/branches/main/protection\` |
| \`bootc container lint\` | 3 warnings (last observed 2026-11-01) | nonempty-boot, sysusers, var-tmpfiles |
| Installer filesystem intent | contradictory (last observed 2026-11-01) | ext4 toml vs btrfs Justfile vs wizard options |
| 2 GB memory budget | unknown | no measurement |
| Boot / update / rollback | no evidence | requires VM/hardware run |

## Rules for this document

- A green build is not a boot.
- \`verified\` signature means \`cosign verify\` succeeded against the repository key.
- An in-progress build must stay in progress; do not backfill a conclusion.
- Boot remains \`no evidence\` until a VM/hardware boot is recorded with the tested
  environment, image digest, \`bootc status\`, and one update cycle.
EOF
