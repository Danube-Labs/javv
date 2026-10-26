# JAVV v4 - Design audit (consistency · overengineering · soundness · security)

> **Living doc** (formerly `AUDIT_v4.md` in the old `V4/` folder — suffixes dropped 2026-07-16, #410).
> The v1–v3 evolution trail is frozen in `.deprecated/`; version markers are reserved for frozen generations.

> Second-round audit of the v4 set, run as **4 independent agents** (consistency, overengineering,
> architecture-soundness, security/ops) framed on the `code-review-and-quality` five axes. Captured
> 2026-06-21. Synthesized + de-duped here with a recommendation per finding.
> **Resolved 2026-06-21:** the rulings were folded into PLAN (D28–D36 + CON fixes), SPEC (new FR-23 +
> FR-2/14/18 updates), ARCHITECTURE, and the new `INDEX-MAP.md`. This doc is the audit *record*; see
> those for the applied form. (Owner overrides: occurrences/scan-events/scheduled-export/two-timer kept;
> rebuild-state kept day-one; `apply_both` stays a release gate; whole-app time-travel added.)

## Verdict (one paragraph)
**v4 is sound, internally consistent, and buildable - no blocking contradictions.** The snapshot-model
migration is clean (zero stale close-event semantics survive), and the core bets (full snapshots + commit
marker, deterministic-`_id` idempotency, no-broker, per-`cluster_id` tenancy, decisions-as-source-of-truth)
hold up. The findings cluster in four buckets: (1) a handful of **reference/naming slips**; (2) three
**load-bearing-claim holes** in the point-in-time query bounds, the commit-marker write ordering, and the
"rebuildable cache" promise; (3) **security control-plane gaps** (audit-log tamper-resistance, maker/checker
on risk-accept, human-auth lifecycle, tenant chokepoint, token↔payload binding); and (4) **overengineering**
in second-order safety-nets/knobs. A pleasing through-line: **several of the overbuilt items, if deferred,
also delete security/soundness findings** - simplification and hardening point the same way.

---

## TIER 1 - Fix before building the affected area (Critical/High)

### Consistency slips (unambiguous - just fix)
- **CON-1 [High]** `PLAN` §8 M5d cites SLA/KEV as **(FR-13)**; it's **FR-10** (FR-13 is export). Wrong ref.
- **CON-2 [Med]** `D5a`/`D5b` referenced (§5.2, §5.3, M4, FLOW) but never defined - §3 only defines **D5**.
  → split D5 into D5a (severity disagree) / D5b (count disagree), or collapse all refs to `(D5)`.
- **CON-3 [Med]** Count-delta field is `delta` in PLAN §5.3 / SPEC FR-11 but **`count_delta`** in the FLOW
  sample. Pin one name (recommend `count_delta`).
- **CON-4 [Low]** `findings.installed_version` vs `occurrences.package_version` - same concept, two names;
  note the rename or unify. **CON-5 [Low]** `occurrences.vuln_id` ≡ `cve_id` elsewhere - note it.
- **CON-6 [Low]** `CLAUDE.md` label `D-FR18` doesn't exist → use `FR-18`. **CON-7 [Nit]** `PLAN` §10 lists
  the GitHub/CI + skills items twice.

### Genuine soundness holes
- **SND-1 [Critical] Symmetric point-in-time query has an unbounded `terms` fan-out.** F2 step 2
  (`scan_run_id IN {…} AND vuln_id=Y`) puts one `scan_run_id` per digest into a single `terms` clause; at the
  documented "thousands of digests" target this approaches/exceeds `index.max_terms_count` (default 65,536)
  and the bool clause cap. *Fix:* page the digest set (≤~1,000/chunk) or invert step 2 (`vuln_id=Y AND
  @ts≤T` → intersect against step-1's latest-per-digest map in app code). Pin in §5.5 + the M8b gate.
  (Verify the exact caps against the live cluster via the OpenSearch MCP - web tools were down for the agent.)
- **SND-2 [Critical] The "rebuildable cache" claim (D17) is overstated for `assignee`/`notes`/`acknowledge`/
  `stale`.** `system-decisions` only holds rule-derived state; those four are not reconstructable from it,
  and the FLOW `system-audit-log` doc is **prose `details` + `cve_id`/scope** (not `finding_key` + structured
  old/new) - so you can't deterministically replay them. *Fix:* pin a **structured `system-audit-log` field
  table** (the one missing `system-*` schema): `@timestamp, actor, action(enum), finding_key (or enumerable
  target), field, old_value, new_value`. State the rebuild rule ("latest entry per field wins"), and make
  `stale` a *recomputed-from-`last_seen`* value, not a "cache" rebuild reads (see SND-6/OE-2 interaction).
- **SND-3 [High] Commit-marker write ordering.** F1 says a half-written snapshot is never "latest," but §3
  step 4 writes scan-events **and** occurrences in **one `_bulk`** - which is non-atomic + cross-index
  refresh-skewed, so the marker can appear before/without its rows. *Fix:* make the commit (scan-events)
  doc a **second write, issued only after the occurrences `_bulk` returns zero per-item errors.** Wire the
  `response["errors"]`/per-item check (already mandated in best-practices) into the M8a gate.
- **SND-4 [High] "Committed-ness" isn't expressed in the queries.** Both forward + symmetric say "latest
  *committed* snapshot ≤ T" but select latest from occurrences alone; OpenSearch has no cross-index join.
  *Fix:* couple it to SND-1's bounded paging - fetch the committed `scan_run_id` set for the *current page's*
  digests from scan-events and filter by it; document the F1↔F2 coupling in §5.5.
- **SND-5 [High] Zombie images / "image fully gone."** Removing close events left **whole-digest
  disappearance** with no owner: the sweep is per-finding + per-scanner-down; nothing stales an `images`
  doc when a digest stops being scanned, and `images` has no time-retention. The "what's *actually running*"
  value prop accumulates stale inventory. *Fix:* extend the sweep to stale/tombstone `images` docs whose
  `last_seen < now−N` (it already walks current-state) **or** explicitly document zombie-inventory as a known
  limitation. Today it silently falls through - make it consistent and stated.

### Security control-plane gaps (add - these strengthen, don't cut)
- **SEC-1 [Critical] `system-audit-log`/`system-decisions` are "immutable" by convention only.** Same store,
  same app creds that update everything else → the source-of-truth for D17/Contributors/compliance is as
  mutable as the cache it's supposed to anchor. *Fix:* a **write-restricted (create-only, no update/delete)
  OpenSearch role** for the audit/decision/append indices; periodic snapshot to a **WORM/object-lock**
  bucket; optional hash-chained entries for tamper-evidence. Until then, stop calling it "immutable."
- **SEC-2 [Critical] No maker/checker on risk-accept.** `approver` is a free string on the decision doc;
  nothing enforces `approver != created_by`, that the approver holds Security-Lead/Admin at approval time, or
  that projection only fires after a genuine approval. A single Triager could self-approve a cluster-wide
  risk-accept and silently suppress criticals - the highest-value abuse path in the tool. *Fix:* server-side
  enforce approver≠author + role + approval-gated projection; journal create and approve separately. Add to
  the M5c gate.
- **SEC-3 [High] Token↔payload binding.** Tokens are per-`(cluster,scanner)` and authenticated, but nothing
  rejects a request whose envelope claims a *different* `cluster_id`/`scanner` than the token. A leaked
  cluster-A token could poison any tenant. *Fix:* assert `payload.cluster_id == token.cluster_id` &&
  `payload.scanner == token.scanner` → 403 + journal.
- **SEC-4 [High] Tenant `cluster_id` filter is a convention, not a chokepoint.** No single repository helper
  guarantees it; riskiest at the **two-step PIT query** (must be on *both* steps) and the **export drain**
  (CronJob identity vs requester scope). *Fix:* funnel every read through one tenant-scoping helper that
  *requires* `cluster_id`; add a negative test asserting no read DSL lacks the filter.
- **SEC-5 [High] Human-auth lifecycle underspecified.** No password policy, **no login lockout/throttle**
  (slowapi is described only for ingest), no session expiry/revocation model, no auth-event auditing. *Fix:*
  specify all four; journal login/password/role/token lifecycle into the audit log.
- **SEC-6 [High] Bootstrap-admin handling.** `JAVV_ADMIN_PASSWORD` should be a **mounted secret file** (not
  env, which leaks via `kubectl describe`/dumps), **seed-once** (no re-seed if an admin exists - else
  permanent backdoor), and **server-enforced** `must_change` (not a UI redirect).

---

## TIER 2 - Overengineering / simplification (mostly owner decisions)

> The cold auditor recommends cutting/deferring these. Some touch choices **you made deliberately** - flagged
> as **[your call]**. My recommendation in each, but these are yours to keep.

- **OE-1 [your call] `javv-scan-events-*` is redundant with full-snapshot occurrences** (counts are derivable
  from occurrences). The auditor says cut it to a tiny commit-marker. **My rec: KEEP it** - you wanted
  trends-from-summaries, you don't mind storage, and it's now **load-bearing as the commit marker** (SND-3).
  The redundancy is real but the commit-marker + cheap-trends roles justify it. (No change; note the dual
  role.)
- **OE-2 [recommend defer] Rebuild-state job → v1.1.** Snapshot/restore (M2) is the real DR; the rebuild job
  is a safety net for a single-pod MVP that nightly snapshots already cover. Deferring it also **dissolves
  much of SND-2** (you still keep the structured audit-log schema, which you need for Contributors anyway).
- **OE-3 [your call] Scheduled/throttled export (D24/M7/`system-reports`).** You proposed and liked this; the
  cold auditor calls it premature (a queue you built after swearing off brokers) and it adds export-security
  surface (object-store IDOR, tenant scoping - SEC-adjacent). **My rec: ship synchronous streaming CSV for
  MVP; keep the scheduled/off-peak version as the first v1.1 item.** If you keep it in MVP, it needs the
  export access-control hardening (signed short-lived URLs, per-tenant prefixes, download entitlement).
- **OE-4 [your call] Two-timer staleness (D20).** You explicitly designed this (3d finding / 7d scanner-down
  + banner). The auditor says one timer + banner suffices for MVP. **My rec: keep your model** (it's a
  deliberate, sound design) but **ship thresholds as defaults/constants first**, add the UI knobs when a user
  asks (config-before-need is the only ding).
- **OE-5 [recommend] `severity_rank` - keep on `findings`, drop from `occurrences`.** Grid sort needs it on
  current-state; point-in-time never range-sorts historical snapshots, so it's dead weight in the biggest
  index. (Or make it a code-side 6-entry sort constant and drop the stored field entirely - minor.)
- **OE-6 [recommend] Envelope N/N-1 acceptance → reject-old-only for MVP.** You ship both ends (Helm), so
  real skew is "operator ran an old image" - covered by `schema_version` + clear 4xx. Keep the *policy*; drop
  *implementing* dual-shape parsing in M1. (Also closes the SEC downgrade-strictness concern.)
- **OE-7 [recommend] Drop the "SQLite/Postgres swap" justification for the `system-*` repository interface.**
  OpenSearch-only is locked; a thin access module is fine, but don't build it as a portability layer for a
  datastore you've ruled out.
- **OE-8 [recommend] Demote the `apply_both` *gate* (M5c) to a normal test.** Keep the pinned D22 semantics;
  don't make a niche conflict rule a release blocker.

---

## TIER 3 - Medium / Low (pin or note; batch into the relevant milestone)

- **SND-6 [Med] rebuild-state vs sweep race** on `findings.state` (admin-rebuild can un-stale). Make rebuild
  recompute `stale` from `last_seen`, or serialize the two. (Moot if OE-2 defers rebuild.)
- **SND-7 [Med] Write-amplification regime.** A daily vuln-DB bump defeats `detect_noop` fleet-wide → the
  "≈0 writes on rescan" posture only holds between bumps. Document the two regimes; make the M3/M4 gates
  measure the **DB-bump-day** worst case, not the unchanged-rescan path.
- **SND-8 [Med] Optimistic concurrency vs scripted-upsert.** Pin `retry_on_conflict` on ingest + 409-retry
  on triage; add a concurrent ingest+triage golden test (no human-field loss either order).
- **SND-9 [Med] `apply_both` + expiry-refresh interaction** untested (specific decision expires → fall back
  to both-scanners, not `open`). Add to the M5c test.
- **SEC-7 [Med] Replay protection.** Idempotent `_id` stops double-count but not replay-to-revert (re-push an
  old snapshot → un-stale / reset `last_seen`). Reject envelopes older than the latest committed run for that
  `(cluster,scanner,digest)`.
- **SEC-8 [Med] TLS/mTLS** on scanner→ingest, app→OpenSearch, and snapshot-repo hops is assumed, not
  required. State it (mTLS for ingest recommended); require the OpenSearch security plugin in prod.
- **SEC-9 [Med] RBAC role list mismatch** - SPEC §Actors lists 5 (Viewer<Auditor<Operator<Security-Lead<
  Admin); FR-18/M5a name 4 (Admin/Security-Lead/Triager/Viewer). Reconcile to one list + publish an
  endpoint×role matrix; destructive ops (restore, drop-index, rebuild, retention) Admin-only + journaled.
- **SEC-10 [Med] Snapshot-repo + export-artifact credentials/access.** Repo creds via OpenSearch keystore
  (not a plaintext config doc). **Export-artifact access — REVISED by the M7 storage decision (2026-07-07,
  #32):** export results are stored **in OpenSearch** (chunked `system-report-chunks`), **not** an object
  store, so there is no per-tenant object prefix / presigned-URL model. Download is a backend endpoint
  (`GET /api/v1/reports/{id}/download`) enforcing the same intent — **per-tenant isolation** via the
  `cluster_id` chokepoint (SEC-4), **time-limited access** via a short-lived signed download token +
  `expires_at` (410 once past `JAVV_EXPORT_TTL_HOURS`), and **download entitlement** (IDOR) checked
  server-side. The keystore/snapshot-repo half of SEC-10 is unchanged (OpenSearch snapshot/restore, M2).
  *(Original model: per-tenant object prefixes + signed short-lived URLs on an S3/MinIO store.)*
- **SEC-11 [Med] Decompression-ratio kill-switch** - meter exists; add an inline abort at an anomalous ratio
  (e.g. >100:1) on top of the absolute 50 MB cap.
- **Low/Nit:** `total = Σ buckets` invariant unchecked at ingest (add golden assertion); CSV-injection rule
  not pinned (pin the prefix/escape rule + apply to notes/justification); `v-html`-free rule for user text in
  M9; scan-events `_id` excludes mutable dims intentionally (note it); bulk-action audit must record the
  target set/selector, not just a count; `system-tokens` sample lacks lifecycle fields (created_at/expiry/
  disabled); date drift in headers (2026-06-20 vs 21); DR RPO/RTO + more-frequent audit-log snapshot
  unspecified.

---

## Recommended action plan

1. **Apply now (no decision needed):** CON-1..7 (consistency slips). Pure correctness; ~10 min.
2. **Pin the three holes in the docs before M8/M3 (no re-architecture):** SND-1 (bounded symmetric query),
   SND-2 (structured audit-log schema + honest rebuild claim), SND-3/SND-4 (commit-marker as a gated second
   write), SND-5 (zombie-images decision).
3. **Add the security control-plane as an explicit hardening slice** (fold into M5a/M5c/M1): SEC-1..6 are the
   must-haves; SEC-7..11 in the same pass.
4. **Owner decisions (Tier 2):** OE-2 (defer rebuild-state?), OE-3 (defer scheduled export?), OE-4 (two-timer
   knobs as config now or later?), plus the recommends OE-5/6/7/8. My leans are marked; OE-1 I'd keep.

**Bottom line:** no re-architecting. Fix the slips, pin four load-bearing details, add the security
control-plane, and decide a few simplifications - then v4 is a solid foundation. The data-model *core*
(snapshots, idempotency, no-merge, no-broker, tenancy-by-digest) is lean and right; the weak spots are the
*human/control plane* and a few *second-order safety nets*, not the data plane.
