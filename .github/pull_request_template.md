## Summary

<!-- What changed and why? Link the issue or design discussion if there is one. -->

## Package / area

<!-- e.g. disk artifact gate, ext4 convergence, governance docs, settings -->

- Files/areas touched:
- Does this change image contents? yes / no
- Does this change installer behavior? yes / no
- Does this change CI or release behavior? yes / no

## Verification

<!-- Paste the commands and results, not just "tests pass". -->

```bash
python3 -m pytest -q
ruff check .
shellcheck -S warning build_files/build.sh build_files/ci/*.sh
actionlint -shellcheck ""
```

- [ ] `Pytest` is green
- [ ] `Lint` is green
- [ ] Image build / VM evidence attached where behavior changed
- [ ] Documentation updated
- [ ] Translations updated and `make -C po mo` run (if strings changed)

## Risk and rollback

<!-- What could break, and the exact revert/rollback step. -->

## Checklist

- [ ] No secrets, `cosign.key`, or generated build output committed
- [ ] No force-push or direct push to `main`/streams
- [ ] No unrelated changes bundled
- [ ] High-risk files (`Containerfile`, `build_files/build.sh`, `.github/workflows/build.yml`) are not mixed with unrelated work
- [ ] Contribution is provided under GPL-3.0-or-later; upstream-derived files retain Apache-2.0
