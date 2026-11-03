# Status matrix

**Snapshot:** 2026-11-03T21:28Z
**Regenerate:** `build_files/ci/status-matrix.sh > docs/operations/status-matrix.md`

This matrix records what is actually evidenced. `unknown` and `no evidence` are
deliberate values, not placeholders to be filled with assumptions.

| Branch | Tip | Latest build | Stream digest | Signature | Boot |
|---|---|---|---|---|---|
| `main` | `a749f05` | [41721853584](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41721853584) (in progress) | `sha256:ef3b01bb614f` | unknown | no evidence |
| `dx` | `b021841` | [41625313684](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41625313684) (success) | `sha256:ea744b426d84` | verified | no evidence |
| `testing` | `0a93e0a` | [41626931843](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41626931843) (success) | `sha256:4e01b074c824` | verified | no evidence |
| `beta` | `e2c158a` | [41625313758](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41625313758) (success) | `sha256:6a4437767fb0` | verified | no evidence |

## Other state

| Check | State | Evidence |
|---|---|---|
| GHCR package visibility | **public** | registry API; anonymous pull test |
| Upstream sync | success [https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41592660975] | latest `upstream-sync` run |
| CI test/lint workflow | present | `.github/workflows/ci.yml` |
| Branch protection | ruleset (2) | rulesets API |
| `bootc container lint` | 0 warnings (verified 2026-11-02) | CI build log |
| Installer filesystem intent | ext4-only (ISO storage directive pending) | docs/operations/filesystem-contract.md |
| 2 GB memory budget | unknown | no measurement |
| Boot / update / rollback | no evidence | requires VM/hardware run |

## Rules for this document

- A green build is not a boot.
- `verified` signature means `cosign verify` succeeded against the repository key.
- An in-progress build must stay in progress; do not backfill a conclusion.
- Boot remains `no evidence` until a VM/hardware boot is recorded with the tested
  environment, image digest, `bootc status`, and one update cycle.
