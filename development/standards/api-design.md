# API design

JAVV's HTTP conventions, so every router looks the same and the FE↔BE contract is predictable.
This is the **success/shape** side; errors live in [`observability.md`](observability.md) (one envelope,
one status taxonomy). Don't restate index mappings or requirements - link to them.

> Owned by **M1** (skeleton + ingest sets the conventions) and **M6** (read/reporting applies them at scale).
> The generated TS client (`@hey-api/openapi-ts`, M9a) is downstream of these - keep OpenAPI accurate.

## Versioning & shape
- All app routes are under **`/api/v1/`** (e.g. `POST /api/v1/ingest/scan`). Bump the prefix only on a
  breaking change; additive fields are not breaking. **Review is the only guard today:** CI's
  contract gate (I4/I7) checks that `frontend/openapi.json` matches the code, not whether a change
  breaks clients. An automatic breaking-change check is I8, still open in
  `docs/audits/remaining_audit_items.md`.
- **JSON only.** Request **and** response bodies are `snake_case` (matches Pydantic v2 / OpenSearch fields).
- **Paths:** lowercase, **kebab-case**, **plural** resource nouns (`/findings`, `/scan-events`,
  `/audit-log`); item by id `/findings/{finding_id}`; sub-resources nest one level max.

## The tenant rule (hard constraint)
Every read/export endpoint carries an explicit **`cluster_id`** and filters on it **in the query layer**,
never UI-only - routed through `tenant_search`, the single tenant read path (SEC-4), entitlement re-checked on every
fetch **and export** (IDOR). See [`../../CLAUDE.md`](../../CLAUDE.md) hard constraints + INDEX-MAP routing.
`cluster_id` **shape is validated at the edge**; an absent/!malformed one is `400`, not a silent all-tenant read.

## Requests
- Request models are **Pydantic v2 `extra="forbid"`**, with per-field `max_length` + bounded collections
  (NFR-7). Unknown field → `400` (validation envelope).
- **Reads use `GET`** with query params; **writes use `POST`/`PATCH`** with a JSON body. No state-changing `GET`.
- **Filtering** is driven by the shared `fields` config (the same one that powers the FE FilterBar, M9a) -
  `terms` / `range` / `date` / `bool` per field. Don't invent ad-hoc query params per endpoint.

## Pagination (no offset past 10k)
- `from`/`size` **only under 10 000**; beyond that, **PIT + `search_after`** (open a PIT, page by the last
  sort key, **delete the PIT in `finally`** - D38). Aggregations paginate via **composite `after_key`**.
- The cursor is **opaque** to the client: respond with `{ "data": [...], "next_cursor": "<opaque>|null" }`;
  the client passes `cursor` back verbatim. Never leak raw `search_after` arrays as a contract.
- Every list response is explicitly **sorted** (stable tiebreak on a unique key) so paging is deterministic.

### List response envelopes (three shapes — pagination style picks the shape)

The rule, and it is descriptive of what ships today rather than aspirational:

| Paging | Envelope | Examples |
|---|---|---|
| **cursor** (PIT + `search_after`, composite `after_key`, or `search_after` alone on an append-only newest-first read) | `{ "data": [...], "next_cursor": "<opaque>\|null", "total": {"value": N, "relation": "eq"} }` | `/findings`, `/audit`, and both at a past `as_of`; `/scanners/ingest-failures` (no PIT, issue 357) |
| **offset** (`size`/`offset`) | `{ "<named>": [...], "total": N }` — named key, `total` already unwrapped to a plain number | `/decisions/approvals` → `approvals`, `/decisions` → `decisions`, `/admin/users` → `users`, `/admin/tokens` → `tokens` |
| **unpaged** | `{ "<named>": [...] }` — named key, **no `total`** | `/contributors` → `leaderboard`, `/images` → `images`, `/images/timeline` → `events`, `/findings/top-components` → `components`, `/clusters` → `clusters`, `/views` → `views`, `/dashboards` → `dashboards`, `/notifications` → `items`, `/admin/jobs` → `jobs`, `/admin/roles` → `roles`, `/admin/snapshots` → `snapshots`, `/scanners/provenance` → `scanners`, `/scanners/freshness` → `scanners` |

**The routes are pinned by a test; this table mirrors that test's registry by hand.**
`backend/tests/test_list_envelope_contract.py` is the registry of record: it asserts every
registered route's list key and `total` form against the live app, and fails the build when a `GET`
route is neither registered there nor exempted with a reason — so a new list route cannot ship
undocumented, and a renamed key breaks a test rather than a reader. What nothing checks is that
this table still agrees with that registry, so edit the two together.

**Two exceptions, stated because a reader who assumes the pattern gets them wrong:**
- **`/notifications` names its array `items`**, not the resource noun — "named key" does not mean "resource name".
- **`/findings/groups` is cursor-paged but carries no `total`** (composite-agg paging can't cheaply produce one), so "cursor ⇒ three keys" does not hold either.

A route may also carry siblings alongside its array — `/contributors` returns a **second** array (`handled_over_time`), `/decisions/approvals` echoes `size`/`offset`/`facets`, `/images` carries `inventory`.

#### Reading one of these safely

**The generated TS client does not protect you.** No route declares a `response_model`, so OpenAPI
records `{type: object, additionalProperties: true}` and the client's type is `{[key: string]: unknown}`;
frontend consumers re-declare the shape with a hand-written cast. A wrong key is therefore **not** a
compile error on any consumer — it is `undefined` at runtime, and in `jq` it is worse: a missing key
yields `null`, and `null | length` is **0**. That reads as a legitimately empty list, is
self-consistent, and *passes* any assertion whenever the real answer is also 0.

So never reach for a key positionally. Assert it exists, and compare counts against the server:

```bash
jq -e 'has("approvals")' <<<"$body" >/dev/null || fail "wrong envelope for this route"
TOTAL=$(jq -r '.total' <<<"$body")        # offset-paged: already a plain number
TOTAL=$(jq -r '.total.value' <<<"$body")  # cursor-paged: unwrap .value
```

Compare an export or a sweep against that server-side `total`, **never against a page's length** — a
page-length comparison agrees with itself whenever the lens exceeds `size`.

## Responses & status
- Success: `200` read · `201` create (+ `Location`) · `202` accepted (async/queued ingest) · `204` no content.
- **Counts/pages come from OpenSearch aggregations/queries — never from shipping raw findings to the client**
  to count (server-side-everything hard constraint).
- Errors: **always** the [`observability.md`](observability.md) envelope (`type/title/status/detail/request_id`);
  status taxonomy (400/401/403/404/413/429/503) lives there - don't duplicate it here.

## Time-travel & idempotency
- The global **`as_of` (T)** param rewinds read endpoints (D28/FR-23): absent/`now` → materialized
  current-state; `T<now` → reconstruction (M8b). Every read endpoint accepts it the same way.
- **Ingest is idempotent** (deterministic `_id`, D18) - a retried push double-counts nothing.
