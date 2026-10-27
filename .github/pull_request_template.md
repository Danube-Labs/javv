<!-- Keep it reviewable: past ~10 files, or across backend and frontend, split it. -->

## What and why

<!-- What changed, and why. Link the issue: `Closes #<n>` if this PR finishes it, `Refs #<n>` if
not. A closing word followed by an issue number closes that issue anywhere in this text. -->

## Checks run

<!-- The exact CI commands and their exit codes (CONTRIBUTING.md § The gates). -->

```
backend   ruff check . / ruff format --check . / pyright / pytest   →
frontend  npm run lint / npm run test:ci                              →
```

## Definition of Done

- [ ] Static floor and tests pass ([definition-of-done.md](https://github.com/Danube-Labs/javv/blob/main/development/standards/definition-of-done.md) §1–2)
- [ ] Hard constraints hold: per-scanner never merged, every read carries `cluster_id`, server-side counts, no broker
- [ ] Artifacts in this PR: route change → `docs/API.md` + regenerated `openapi.json` and client;
      new mutating route → RBAC/IDOR registry; mapping change → `MAPPING_VERSION` + INDEX-MAP;
      new setting → `docs/CONFIGURATION.md`
- [ ] UI change: screenshots below, hover/pressed/focus states, loading/empty/error states
- [ ] Commit messages pass the commit-msg hook (lowercase subject, lines ≤ 100 characters)

## Screenshots

<!-- UI changes only. Delete this section otherwise. -->
