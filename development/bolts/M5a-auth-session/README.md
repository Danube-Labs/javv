# M5a - Auth & Session (prereq for all mutations)

**Status:** tracked in [#27](https://github.com/Danube-Labs/javv/issues/27) — live status on the GitHub issue/board

## Goal
Local human auth (argon2id) + server-side sessions and the **capability-based RBAC**
chokepoint that gates every mutation in the app. Ships the bootstrap admin, the single
`tenant_search` `cluster_id` chokepoint, peppered-SHA-256 ingest tokens, auth-event
auditing, and a **standing parametrized RBAC/IDOR negative-test suite** every future
mutating endpoint registers into. *Security-critical: this is the prerequisite for M5b–M5d
and every later mutation.*

**Canonical refs:** [`PLAN §8 M5a`](../../../docs/engineering/PLAN.md) (M5 split, SEC-4/SEC-6) ·
`SPEC` FR-18 (auth/RBAC, D33), MVP tenant model D38/H9 ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`system-users` **[OWNS]**, `system-roles` **[OWNS]**,
`system-sessions` **[OWNS]**, `system-tokens` **[OWNS]**, `system-audit-log` *append-only, schema owned by M5b*) ·
decisions D33 (capability RBAC + `can_accept_audit_final`), D38/M14 (peppered SHA-256 tokens), D17 (journaling).

## Depends on
- M1 (index bootstrap + `AsyncOpenSearch` `lifespan` client + ingest-token surface to harden).
  **`system-tokens` already exists in `backend/core/bootstrap.py`; add `system-users` /
  `system-roles` / `system-sessions` there (+ `MAPPING_VERSION` bump) — the versioned boot-time
  bootstrap, not a separate creation path.**

## Auth design (settled with the operator at kickoff, 2026-07-04 — mirrored on #27)
**Server-side sessions, not JWTs.** Login mints a 256-bit random `session_id`; only its peppered
SHA-256 is stored (`system-sessions`, doc `_id` = hash → one GET per request); the raw value lives
solely in an `HttpOnly; Secure; SameSite=Lax` cookie. TTL is the server-side `expires_at`
(`JAVV_SESSION_TTL_HOURS`); logout / logout-all / **role-change** flip `revoked:true` — instant
server-side kill. *Why no JWT:* D33 requires instant revocation, which a self-contained JWT cannot
do without a per-request server-side denylist — i.e. a session store with extra steps; JWT's
statelessness only pays when third parties verify tokens without calling us, which never happens
in a single-backend app whose store is already one `GET` away.

**Login** (`POST /auth/login`): lockout check → argon2id verify that ALWAYS runs (unknown user
verifies against `DUMMY_HASH` — no username timing oracle; generic 401 either way) → `must_change`
gate (bootstrap admin gets a restricted session that can only change its password, SEC-6) →
session mint → `{user, capabilities}` body (UI hints only — the server re-checks every call).
**Logout**: revoke + clear cookie. **CSRF**: SameSite=Lax + JSON-only mutation APIs, same-origin SPA.

**OIDC/LDAP seam (designed in now, built post-MVP):** an `IdentityProvider` protocol —
`authenticate(credentials) → AuthResult` — with `LocalPasswordProvider` as the only MVP
implementation. External IdPs replace **credential verification + user provisioning only, never
the session layer**: after any provider authenticates, JAVV mints its own first-party session, so
sessions/capabilities/audit/logout and the RBAC suite are identical across providers. Baked in
now: `system-users.auth_source` (`local|ldap|oidc`) + `external_id`, nullable `password_hash`
(INDEX-MAP updated); capabilities always resolve from `system-roles` regardless of provider
(LDAP groups / OIDC claims later map *into* roles).

## Already landed (M1–M3 + audit fixes) — M5a builds ON these, doesn't duplicate them
- **Ingest-token crypto** — `backend/src/backend/core/security.py`: 256-bit `mint_token`,
  peppered-SHA-256 `hash_token`, constant-time `tokens_match`, `token_expired` (audit m-3).
- **Token↔payload binding (SEC-3)** — enforced + tested on the ingest POST
  (`routers/ingest.py`: 403 `scope_mismatch`); `require_token` (`core/auth.py`) is the shared
  machine read-path dependency (generic 401, no existence oracle, expiry + `disabled` honored).
- **Mint (CLI)** — `core/tokens.py` (`python -m backend.core.tokens`); the raw token prints once,
  only the peppered hash is stored. The capability-gated mint/rotate/revoke **API** is this bolt.
- **`system-tokens` index** — mutable index + `dynamic:false` mapping in bootstrap
  (`MUTABLE_INDEXES`), incl. `expiry`/`disabled`/`last_ingest_at`.
- **Reusable patterns:** the ingest rate-limiter (`routers/ingest.py`, audit m-4) is the shape for
  the login lockout; the `system-config` read/write helpers (`jobs/staleness.py` /
  `jobs/lifecycle.py`) are the shape for any auth policy knobs.

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed,
matching the real `backend/src/backend/` layout; a new `auth/` package beside `core/`):
- `backend/src/backend/auth/passwords.py` — argon2id hash/verify; `password_hash` **never logged**; password policy (length/complexity); `compare_digest`-style constant-time verify.
- `backend/src/backend/auth/sessions.py` — server-side sessions: mint/lookup/revoke; **hashed** `session_id` in `system-sessions`; httpOnly+Secure+SameSite cookie; TTL `expires_at`; **revoke-on-role-change / logout-all**; one session per browser, shared across tabs.
- `backend/src/backend/auth/lockout.py` — login lockout/throttle (failed-attempt counter + backoff; the ingest rate-limiter is the pattern).
- `backend/src/backend/auth/capabilities.py` — capability bundles resolved from `system-roles`; `require_capability(cap)` FastAPI dependency; `can_accept_audit_final`, `can_triage`, `can_manage_*`, destructive caps Admin-only (D33/SEC-2/SEC-9).
- `backend/src/backend/auth/principal.py` — `get_current_principal()` resolving the session → user + effective capabilities (OIDC-swappable later).
- `backend/src/backend/auth/bootstrap_admin.py` — bootstrap admin: mounted-secret, **seed-once** (idempotent), server-enforced `must_change` on first login (SEC-6).
- **Token admin API** (`backend/src/backend/routers/tokens.py`) — capability-gated mint/rotate/revoke/list over the **existing** token machinery (`core/security.py` crypto, SEC-3 binding, `core/tokens.py` mint — see *Already landed*; do NOT create a second token path). Rotate = mint-new + disable-old (the staleness sweep already dedupes rotated tokens, audit M-2); revoke = `disabled:true`. Machine tokens stay **separate from human session auth**.
- `backend/src/backend/tenancy/chokepoint.py` — the single `tenant_search(...)` helper that injects the `cluster_id` filter into **every** read/export query (SEC-4); the only sanctioned path to OpenSearch reads for the user-facing API (M6 consumes it; internal jobs/services keep their explicit-filter queries). Per-request entitlement on fetch **and** export (IDOR).
- `backend/src/backend/routers/auth.py` — `POST /auth/login`, `POST /auth/logout`, `POST /auth/password` (first-login change), `GET /auth/me`; admin user/role management endpoints (capability-gated).
- `backend/src/backend/auth/audit.py` — emits auth-event audit entries (`login`/`logout`/`pwd_change`/`role_change`/`token_mint`/`token_revoke`) into `system-audit-log` (D17). *(Consumes the audit-log writer/schema **owned by M5b**; if M5b lands after, a thin local appender stands in and is replaced.)*
- `backend/tests/security/rbac_idor_contract.py` — **the standing parametrized RBAC/IDOR negative-test suite** (AUDIT N4 / SEC-4): a registry every mutating endpoint registers into, asserting each rejects (a) missing capability, (b) insufficient capability, and (c) cross-`cluster_id` access.
- `system-users` / `system-roles` / `system-sessions` mutable indices (`dynamic:false`) added to `bootstrap.MUTABLE_INDEXES` (+ `MAPPING_VERSION` bump); `system-tokens` already exists there.

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **Capability gate (D33):** risk-accept (and every `can_*`-gated action) is rejected for a principal lacking the capability; `can_accept_audit_final` specifically gates risk-accept; Admin holds all.
- **Bootstrap admin (FR-18/SEC-6):** seeds exactly once from the mounted secret (idempotent re-run is a no-op); first login is forced through `must_change` before any other action succeeds.
- **Token security (D38/M14):** *(crypto/binding/expiry already green — keep as regression)* ingest token is 256-bit, stored only as a **peppered SHA-256**; verification is constant-time; a token whose payload `cluster_id`/`scanner` ≠ its scope is rejected (SEC-3 binding). **New here:** mint/rotate/revoke API is capability-gated + audited; a revoked/rotated-out token 401s immediately.
- **Session security:** cookie is httpOnly+Secure+SameSite; `session_id` stored hashed; expired/revoked sessions rejected; role-change revokes live sessions.
- **Tenant chokepoint (SEC-4):** a read that bypasses `tenant_search` is caught by the negative test; every read carries a `cluster_id` filter; MVP = all-clusters-visible but the filter is *always applied* (D38/H9).
- **Standing RBAC/IDOR suite (AUDIT N4):** the parametrized suite passes for every registered mutating endpoint (missing-cap, insufficient-cap, cross-`cluster_id`); an endpoint that forgets to register fails a presence check.
- **Auth-event auditing:** login/logout/pwd_change/role_change/token_mint/token_revoke each append exactly one `system-audit-log` entry with the correct `actor`/`action`/`entity_type`.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** argon2id hash/verify + never-logged assertion; password-policy validator; lockout/throttle state machine; capability-bundle resolution; token hash + constant-time compare; `tenant_search` DSL-builder (asserts the emitted `cluster_id` filter clause).
- **Integration (real OpenSearch):** full login→session→protected-call→logout round-trip; bootstrap seed-once idempotency; `must_change` enforcement; revoke-on-role-change invalidates a live session; ingest-token mint/verify/revoke + payload-binding rejection.
- **Security negative (required — AUDIT N4/SEC-4):** the standing parametrized RBAC/IDOR suite (missing cap / insufficient cap / cross-`cluster_id`) over all M5a mutating endpoints; the registry-presence guard; a bypass-the-chokepoint read fails.
- **Golden fixtures:** auth-event → `system-audit-log` row shape for each `action` enum value.

## Out of scope (defer)
- OIDC/SSO → post-MVP (`get_current_principal()` is the swap seam).
- Per-user `allowed_cluster_ids` grants → post-MVP (D38/H9: MVP is all-clusters-visible with the filter always applied).
- Body-HMAC / replay-nonce ingest signing → post-MVP.
- The `system-audit-log` index template + structured writer **schema** → **M5b owns it** (M5a only appends auth events).

## Config tracking

> **When this bolt introduces config**, add each new knob (a `JAVV_*` / OpenSearch env var, a
> `system-config` key, or a scanner scan flag) to
> [`docs/CONFIGURATION.md`](../../../docs/CONFIGURATION.md) in the same PR — default · how it's set ·
> whether it's UI-controllable. That file is the single tracker for every configuration knob (DoD §6).

## Updates

- **2026-07-04 — pre-kickoff refresh against the M0–M4 reality (post-M4 close).** The ingest-token
  surface listed as a deliverable was largely built by M1/M3 + the M3 audit fixes: crypto
  (`core/security.py`), SEC-3 binding (ingest 403, tested), expiry/disabled enforcement,
  `require_token`, the mint CLI, and the `system-tokens` index — moved to a new *Already landed*
  section; the deliverable is rescoped to the **capability-gated token admin API** (mint/rotate/
  revoke/list) on top of the existing machinery, one token path only. Fixed stale `backend/app/`
  paths to the real `backend/src/backend/` layout (new `auth/` package); "index templates" for the
  system indices corrected to **mutable indices in `bootstrap.MUTABLE_INDEXES`** (they don't roll).
  Noted reusable patterns: ingest rate-limiter → login lockout; staleness/lifecycle config helpers
  → auth knobs. Everything human-auth (passwords/sessions/lockout/capabilities/principal/bootstrap
  admin/routes/chokepoint/RBAC-IDOR suite/auth auditing) is untouched net-new scope — the bolt is
  fully doable on the M0–M4 base.

- **2026-07-05 — Task D (#141) delivered the deferred FR-18 admin surface.** Both independent
  audits flagged that this bolt promised admin user/role endpoints + "role-change revokes
  sessions" but shipped only the self-service half. Operator ruled **build now**:
  `routers/admin_users.py` (`can_manage_users`-gated) — create (admin-set temp password →
  `must_change: true`, same SEC-6 discipline as the bootstrap admin), list, role change
  (role + denormalized capabilities updated together, then `revoke_all_for_user` — D33 finally
  has its caller), disable/enable (disable revokes), password-reset (temp + `must_change` +
  revoke-all, local users only). **Last-enabled-admin guard** (409 on demote/disable — no
  self-bricking). Rulings: bootstrap stays **secret-only** (a default `admin/admin` was
  considered and rejected — `must_change` can't close the pre-first-login hijack race);
  role-bundle editing stays out of scope. All four mutating routes registered in the RBAC/IDOR
  suite; every action journaled. Docs: `docs/CONFIGURATION.md` §6.

### 2026-10-26 — Frozen as history

The bolts M0 to M10 ended on 2026-10-09. This file is history now, not the spec of record. New work
follows one GitHub issue for each feature, with the plan and a spec file for each slice on the
issue. The timeline, the rulings that still apply and the open work are in the
[memory bank](../../memory-bank/README.md) (issue 1012).

## Logging (standing rule)
> All app-code logging goes through the shared library: `structlog.get_logger()` on the
> `libs/javv-common` pipeline — redaction, JSON, `timestamp→level→event` order and
> `JAVV_LOG_LEVEL` come free ([observability.md §1](../../standards/observability.md)).
> **Never `print()`, never `logging.getLogger()`, never a private logging setup.**
