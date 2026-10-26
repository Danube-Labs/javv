# Handoff docs — the current UI contract (refreshed against the shipped backend)

> **Living UI contract** (formerly the `v5/` folder — the version suffix dropped 2026-07-16, #410).
> Layered over the frozen `handoff/v4/` prototype; when sources disagree, `docs/engineering/` wins.

Produced 2026-07-07 via Claude design (claude.ai/design) from the major-audit inputs
(`.deprecated/docs/audits/major_audit/05-backend-ui-drift-m9.md` §F prompt: `docs/API.md` as the contract,
the drift-table rulings, the full v4 handoff docs + prototype + brand assets).

- `SCREENS.md` — screen-by-screen spec; every screen names its M9 bolt, its data as
  concrete endpoint calls, and its states. Carries the **DECIDE register** (open operator
  rulings, recommended option drawn) and the **BLOCKED register** (reads that need backend).
- `DATA_MODEL.md` — the UI-facing shapes on the real fields (drift table §B).

`handoff/v4/` stays frozen as the evolution trail (same convention as the engineering docs).
Endpoints were verified against `docs/API.md` at landing time — anything not shipped is marked
BLOCKED/planned, never assumed.
