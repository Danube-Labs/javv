<!--
History: the bolts M0 to M10 are frozen (issue 1012), and there are no new bolts. New work follows
one GitHub issue for each feature, with a spec file for each slice (git-workflow.md, "Tracking work").
The links below are relative to a bolt folder, development/bolts/M<n>-<slug>/.

Copy this file to development/bolts/M<n>-<slug>/README.md and fill it in.
Keep it THIN: link to the canonical design for the "what/why"; this file is the EXECUTION layer only.
Do NOT restate index mappings, requirements, or decisions - link to them. Restating = drift.
Code does NOT live in this folder - it lands in backend/ / frontend/ / scanner/ / deploy/.
-->

# M<n> - <Title>

**Status:** tracked in #<issue> — live status on the GitHub issue/board (label `bolt`)

## Goal
1-2 sentences. What this bolt delivers and why it exists.

**Canonical refs:** [`PLAN §8 M<n>`](../../../docs/engineering/PLAN.md) ·
`SPEC FR-<…>` · [`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (indices touched) · decisions `D<…>`

## Depends on
- M<…> (why). "None" if it's a leaf with no prerequisites.

## Deliverables
The actual files/modules this bolt creates - **in the layered tree, not here**:
- `backend/…` / `scanner/…` / `frontend/…` / `deploy/…`

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus**:
- <bolt-specific gate 1 - usually the PLAN "Gate" check, as an automated test>
- <bolt-specific gate 2>

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** …
- **Integration (real OpenSearch):** …
- **Golden fixtures:** …

## Out of scope (defer)
- <thing> → deferred to M<…>.

## Updates
<!-- Append-only log. Don't rewrite the brief above — record changes/progress here, newest last.
     Format: ### YYYY-MM-DD — <what changed / why>. Delete this comment in real bolts. -->
- _none yet_

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
