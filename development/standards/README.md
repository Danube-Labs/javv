# JAVV - engineering standards

**How we build** (the cross-cutting rules). For **what** we build, see the canonical design in
[`docs/engineering/`](../../docs/engineering/). For the **dev environment**, see
[`development/README.md`](../README.md).

These files hold the rules that each issue shares, so the plan of an issue names only its own goal,
slices and spec files, and links here for the rest. The bolts in [`bolts/`](../bolts/) are history
(issue 1012).

| File | What it covers |
|------|----------------|
| [definition-of-done.md](definition-of-done.md) | The uniform gate **every** PR must pass before it's "done" |
| [testing.md](testing.md) | Test taxonomy (unit / integration / golden fixtures) + conventions |
| [observability.md](observability.md) | Logging, `/healthz` vs `/readyz`, boot-vs-runtime degrade, the error envelope, metrics |
| [api-design.md](api-design.md) | HTTP conventions: versioning, naming, the tenant filter, pagination, response/status shape |
| [ui-foundations.md](ui-foundations.md) | One visual system: design tokens as source of truth, typography, semantic color buckets, stylelint enforcement |
| [git-workflow.md](git-workflow.md) | Branch naming, commits, PR checklist, merge rules |
| [releases.md](releases.md) | Versioning + release automation (release-please) + dependency updates (Renovate) |
| [dependency-policy.md](dependency-policy.md) | Where each version is pinned, update cadence, the fix deadlines for vulnerable dependencies, adding a dependency |
| [security.md](security.md) | The engineering threat model (ingest, tenants, secrets) and the security checks that run; reporting lives in the root `SECURITY.md` |
| [bolt-readme-template.md](bolt-readme-template.md) | History: the template of the bolt READMEs. There are no new bolts. |

## Don't duplicate - point
These are the existing sources of truth; **link to them, don't re-host them** (re-hosting drifts):

- **Hard constraints + day-one engineering rules** → [`../../CLAUDE.md`](../../CLAUDE.md)
- **Stack best-practices** (async client, mappings, `_bulk`, Vue patterns) →
  [`../../docs/research/STACK-BEST-PRACTICES.md`](../../docs/research/STACK-BEST-PRACTICES.md)
- **Tooling & MCP servers** → [`../../docs/research/TOOLING-AND-MCP.md`](../../docs/research/TOOLING-AND-MCP.md)
- **Every index + mapping** → [`../../docs/engineering/INDEX-MAP.md`](../../docs/engineering/INDEX-MAP.md)
