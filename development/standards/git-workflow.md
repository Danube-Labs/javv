# Git workflow

Lightweight rules for a small team. Full rationale in the `git-workflow-and-versioning` skill.

## Branches
- Cut from `main`. Naming: `feat/<issue>-<slug>`, `fix/<issue>-<slug>`, `chore/<slug>`, `docs/<slug>`.
  - e.g. `feat/440-dashboard-edit`, `feat/243-can-export`, `docs/1012-memory-bank`.
- One **issue** → one or more PRs, each with one or more slices of the issue's plan, in thin vertical
  slices (`incremental-implementation` skill). **No stacked PRs, ever** — every slice bases on `main`. Hold
  finished work rather than stacking (a merged stacked base has closed its child PR before).

## Commits
- **Conventional commits:** `type: subject` - `feat`, `fix`, `chore`, `docs`, `test`, `refactor`.
- Imperative, present tense, lower-case subject. Body explains *why* when non-obvious.
- Name the issue in the body (`issue 440`). Put `Refs #<n>` or `Closes #<n>` only in the PR body:
  release-please copies a `Refs #<n>` from a commit into the release notes as `closes`.
- No attribution footers (`Co-Authored-By` lines for tools) and no session links in commits or PRs.
- **Never** `--no-verify` / skip hooks. If a hook fails, fix the cause. Hooks are installed by
  [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) (ruff + the conventional-commit check,
  which mirrors CI commitlint: the 6 types, subject case, header and every body line ≤ 100 chars);
  `setup-dev.sh` installs them.
- **Pre-commit trap — the first commit of a new/reformatted file can silently NOT land:** when the
  `ruff format` hook reformats a staged file it exits non-zero and **aborts the commit with HEAD
  unmoved** (the reformatted file is left unstaged). Always `git log --oneline -1` after committing;
  if the commit is missing, re-`git add` and commit again. Running `uv run ruff format <file>` before
  staging avoids it entirely.
- Commit **subjects are all-lowercase even for identifiers** (`d21`, `m5c`, `opensearch`). CI
  commitlint and the local hook both reject an uppercase first letter.

## Pull requests
- Target `main`; keep them reviewable (small > big).
- **PR description = the Definition of Done checklist** ([definition-of-done.md](definition-of-done.md)) ticked off,
  plus the issue: **`Closes #<n>`** in the PR that finishes it, `Refs #<n>` in the PRs before it.
- CI must be green (ruff + pyright + pytest, ESLint + Vitest) before merge.
- `code-review-and-quality` pass on the diff.

## Handing a PR to review (implementer → reviewer)

Standing division of labour (operator ruling 2026-07-27): **one agent implements, an independent
reviewer checks.**
Scoped issues carry an implementation-prompt comment ending in a **Review gate** — that list is the
review contract for the PR.

**The implementation prompt names artifacts per slice, not principles per PR** (ruling 2026-07-28,
out of PR #491's review — all three findings were one shape: new logic or scope without its mirror
artifact). Each slice in the prompt states:
- **the spec file its tests land in** — "tests in the same slice" is the principle that got skipped;
  "pin the matcher in `image-filters.spec.ts`" is the checkbox that didn't. A slice that adds a pure
  function, matcher, or branch and names no spec file is mis-scoped, not test-exempt.
- work sliced so that **review can land per slice** when the PR will cross ~10 files — a finding
  after slice 1 costs minutes; the same finding on a 26-file PR costs a round-trip.

A PR is ready for review only when its description carries:

1. **Gates run, exit codes shown.** The exact CI commands for the touched stacks (`npm run lint` /
   `npm run test:ci` from `frontend/`; tree-wide `ruff` + `pyright` + full `pytest` from `backend/`),
   quoted with their exit codes — not grepped output, and not "CI will catch it".
2. **The issue's Review gate, ticked with evidence.** One line per item: what was done and where to
   look (a file:line, a test name, a screenshot). An unticked item needs a stated reason, not silence.
3. **UI deltas: proof by pixels.** Before/after screenshots per changed screen, a `/visual-test` run
   where routes changed, and a one-line stranger's-walk note (walked the screens as a user, with data
   verified against the corpus — not hand-crafted docs).
4. **Contract artifacts in the same diff.** Route/param change → API.md + regenerated
   `frontend/openapi.json` + client; new setting → CONFIGURATION.md; mapping → INDEX-MAP +
   `MAPPING_VERSION`; new mutating route → the RBAC/IDOR registry. Listing them beats the reviewer
   discovering them missing.
5. **Known gaps stated.** What was deliberately not done, and why. A gap the implementer names costs
   a sentence; the same gap found in review costs a round-trip.
6. **Scope deltas named.** Anything user-visible the issue did not ask for — a new panel, a new rail
   dim, a changed default — gets its own line, even when it fell out of the implementation as a
   side effect (PR #491: two facet groups appeared because the cell action needed the fields — real
   reason, still a delta the reviewer had to discover). Silence on a delta is treated as hiding it,
   not as it being minor; "none" is a valid entry and is written out.

Review findings land as PR comments; fixes go on the same branch (no fixup PRs). The reviewer
re-greps factual claims in docs/comments against the code — prose written *about* the system instead
of checked against it is this repo's most repeated defect (see PR #480's history).

## Tracking work (GitHub issues)
The bolts M0 to M10 are history (issue 1012): their READMEs do not change any more. Each feature
or fix has one GitHub issue, and that issue is the live status and the spec. While you work an
issue:
- **Plan first** — before any code, post the plan as a comment on the issue, with a spec file (the
  test file) for each slice. The operator rules on the open decisions there.
- **Kickoff** — "starting slice <n>". First **check the dev tooling**: the relevant MCPs
  (`claude mcp list` → serena / opensearch / context7 per
  [`docs/research/TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md)) and the static
  floor (ruff/pyright). If any are missing, wire them at kickoff (they load on the next session).
  Do not skip this step.
- **Blocker** — what blocks the work, and on what.
- **Scope or decision change** — the change and the operator's ruling, on the issue. A ruling that
  stays in force also goes in [`rulings.md`](../memory-bank/rulings.md) of the memory bank, and a
  changed design decision in [`system-patterns.md`](../memory-bank/system-patterns.md).
- **Done** — a short wrap-up. The PR that finishes the issue has `Closes #<n>` in its body. Note
  which **MCPs/skills you actually used** (one line).

Mechanical activity (commits and PRs that mention `#<n>`) shows in the issue timeline
automatically, with no comment. An AI agent that works an issue follows the same checkpoints. The
timeline of the project, the rulings that still apply and the open work are in
[`development/memory-bank/`](../memory-bank/README.md).

## Housekeeping (chores outside a feature issue)
Maintenance work — CI/tooling bumps, dependency hygiene, version pins, doc/branch cleanup — stays off the
feature issues. There is no shared tracker issue (we closed the old one, #66, on 2026-07-07). For every such PR:
- Add the **`housekeeping`** label; `is:pr label:housekeeping` lists them all.
- Put **`Refs #<n>`** in the body for the issue the work came from, so the PR shows up in that issue's
  timeline. Use `Closes #<n>` only when the PR finishes that issue. If no issue exists, say where the
  work came from in the body instead.

Renovate PRs get the label automatically (`labels: [dependencies, housekeeping]` in renovate.json).
Hand-authored chore PRs follow the convention; the agent included.

## main
- Protected. No direct pushes; PR + green CI + review to merge.
- First tag (`v0.1.0`) is cut at **M0/M1** (first runnable code). The MVP release (`0.6.1`) came from
  the deploy bolt (M10), which closed with `0.7.0`. `1.0.0` follows a hardening phase (see [releases.md](releases.md)).
- Versioning + release/dependency automation (release-please, Renovate): see [releases.md](releases.md).
