# Status matrix

**Snapshot:** 2026-11-01T13:39Z
**Regenerate:** `build_files/ci/status-matrix.sh > docs/operations/status-matrix.md`

This matrix records what is actually evidenced. `unknown` and `no evidence` are
deliberate values, not placeholders to be filled with assumptions.

| Branch | Tip | Latest build | Stream digest | Signature | Boot |
|---|---|---|---|---|---|
| `main` | `62ccf66` | [41311775605](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41311775605) (in progress) | `sha256:22de706f63ce` | verified | no evidence |
| `dx` | `277b6b0` | [41311402655](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41311402655) (success) | `sha256:26dc928e1ec1` | verified | no evidence |
| `testing` | `c66eb4e` | [41312243816](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41312243816) (in progress) | `sha256:c93a11c8a5c1` | verified | no evidence |
| `beta` | `2ffc676` | [41311397867](https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41311397867) (success) | `sha256:aa8539e84774` | verified | no evidence |

## Other state

| Check | State | Evidence |
|---|---|---|
| GHCR package visibility | **private** | registry API; anonymous pull test |
| Upstream sync | success [https://github.com/adwaita-blue-lite/adwaita-lite/actions/runs/41311782551] | latest `upstream-sync` run |
| CI test/lint workflow | absent | `.github/workflows/ci.yml` |
| Branch protection | absent | `repos/adwaita-blue-lite/adwaita-lite/branches/main/protection` |
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
