# Status matrix

**Snapshot:** 2026-11-02T01:57Z
**Regenerate:** `build_files/ci/status-matrix.sh > docs/operations/status-matrix.md`

This matrix records what is actually evidenced. `unknown` and `no evidence` are
deliberate values, not placeholders to be filled with assumptions.

| Branch | Tip | Latest build | Stream digest | Signature | Boot |
|---|---|---|---|---|---|
| `main` | `e81620b` | [41375033850](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41375033850) (in progress) | `sha256:862dcc50ae19` | unknown | no evidence |
| `dx` | `5daeaf2` | [41370811264](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41370811264) (success) | `sha256:93c9561760ba` | verified | no evidence |
| `testing` | `598eb13` | [41371819302](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41371819302) (success) | `sha256:9156b23515ec` | verified | no evidence |
| `beta` | `78b41df` | [41370810484](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41370810484) (success) | `sha256:24e6ce1bc0a8` | verified | no evidence |

## Other state

| Check | State | Evidence |
|---|---|---|
| GHCR package visibility | **public** | registry API; anonymous pull test |
| Upstream sync | success [https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41311782551] | latest `upstream-sync` run |
| CI test/lint workflow | present | `.github/workflows/ci.yml` |
| Branch protection | ruleset (1) | `repos/adwaita-blue-lite/adwaita-lite/branches/main/protection` |
| `bootc container lint` | 3 warnings (last observed 2026-11-01) | nonempty-boot, sysusers, var-tmpfiles |
| Installer filesystem intent | contradictory (last observed 2026-11-01) | ext4 toml vs btrfs Justfile vs wizard options |
| 2 GB memory budget | unknown | no measurement |
| Boot / update / rollback | no evidence | requires VM/hardware run |

## Rules for this document

- A green build is not a boot.
- `verified` signature means `cosign verify` succeeded against the repository key.
- An in-progress build must stay in progress; do not backfill a conclusion.
- Boot remains `no evidence` until a VM/hardware boot is recorded with the tested
  environment, image digest, `bootc status`, and one update cycle.
