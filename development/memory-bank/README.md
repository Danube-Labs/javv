# Memory bank

The memory bank is one place to read what JAVV is, how it got to this point, which decisions and
rulings still apply, and what work is open. It is for a new contributor, a reviewer, and an agent
that starts a session with no context.

The bank is a summary. It is not a spec. When the bank and a canonical document do not agree, the
canonical document is correct, and the bank must change. The canonical documents are
[`CLAUDE.md`](../../CLAUDE.md), the files in [`.claude/rules/`](../../.claude/rules/),
[`docs/engineering/PLAN.md`](../../docs/engineering/PLAN.md),
[`docs/engineering/SPEC.md`](../../docs/engineering/SPEC.md),
[`docs/engineering/INDEX-MAP.md`](../../docs/engineering/INDEX-MAP.md),
[`docs/API.md`](../../docs/API.md), [`docs/CONFIGURATION.md`](../../docs/CONFIGURATION.md) and
[`frontend/DESIGN.md`](../../frontend/DESIGN.md).

## Read in this order

| File | What it holds |
|---|---|
| [`project-brief.md`](project-brief.md) | What JAVV is, who it is for, the hard constraints, and what it does not do |
| [`tech-context.md`](tech-context.md) | The stack, the repository, the dev stack, the gates, CI and the release |
| [`timeline.md`](timeline.md) | The bolts M0 to M10, then the work after them, by release and by theme |
| [`system-patterns.md`](system-patterns.md) | The architecture and the decisions that still apply |
| [`rulings.md`](rulings.md) | The operator rulings that still apply |
| [`lessons.md`](lessons.md) | The lessons from incidents, and the rule that each lesson made |
| [`active-context.md`](active-context.md) | Open, held and next work, on a given date |

## How the bank stays current

- After each release, one docs PR updates `timeline.md` and `active-context.md`.
- A PR that changes a decision or a ruling also changes `system-patterns.md` or `rulings.md`.
- A PR that adds a lesson to `CLAUDE.md` or to a rule file also adds the incident to `lessons.md`.
- `backend/tests/test_memory_bank.py` makes sure that each repository path in the bank exists, that
  each release in `CHANGELOG.md` has a line in the timeline, and that each decision number exists
  in `PLAN.md`.

## Sources

The first version of the bank (issue 1012, 2026-10-26) comes from the git history, the merged PRs,
the issues and their comments, the bolt READMEs, `CHANGELOG.md`, the documents in
`docs/engineering/`, and the session handoffs. The handoffs are local files that git does not
track (`.claude/sessions/`), so the bank keeps what they hold that has a value after the session.

## Rules for the text

- Simplified Technical English, as for all new text in the repository.
- A link or an issue number for each fact that has a source.
- No person's name, no local path, no model name and no session link.
