"""Versioned index bootstrap (M1). Declarative index/template definitions pinned to
INDEX-MAP.md — the single source of truth for every mapping; read it before changing anything
here. All mappings are `dynamic:false` (unmapped fields survive in `_source` — raw fidelity — but
are never indexed) and carry `_meta.version`; `bootstrap()` is idempotent and only touches an
index/template whose recorded version is older.

Scope: the `findings` current-state cache + `system-tokens` (ingest auth) + `system-config`
(M2 — holds the snapshot-repo ref) + the M5a human-auth trio (`system-users` / `system-roles` /
`system-sessions`, FR-18/D33/SEC-5), plus index *templates* for the per-cluster
`javv-scan-events-*` / `javv-images-*` append series so any per-cluster index gets the pinned
mapping at auto-create. Rollover/retention is M4's lifecycle job; `javv-scan-orders` (D45) and
`javv-scan-watermarks` (D40) are owned by M3; occurrences (M8a) + audit-log (M5b) land with
their bolts.

Runnable standalone: `uv run python -m backend.core.bootstrap`.
"""

from typing import Any

from opensearchpy import AsyncOpenSearch, RequestError

# ── MAPPING_VERSION: the ONE place schema versions change ──────────────────────────────────────
# Single source by construction: every mapping's `_meta.version` and every compare in bootstrap()
# reference this constant — no other file carries a version literal (test_bootstrap asserts the
# marker via the same import). To evolve any index/template mapping:
#   1. Edit the `_*_PROPERTIES` dict here (ADDITIVE only — `dynamic:false` means new fields must
#      be mapped here first; never retype/remove a field, that's a reindex-migration).
#      tests/test_mapping_additive.py holds this against the newest release tag (issue 261).
#   2. Bump MAPPING_VERSION by 1 and extend the history comment below. The same test fails a
#      mapping change that main does not have yet under main's MAPPING_VERSION.
#   3. Keep INDEX-MAP.md in the same change (it's the spec of record for every mapping), and add
#      an `Unreleased` row to docs/UPGRADING.md § Version notes (operators read that, not this).
#   4. Done — on next startup bootstrap() sees version < MAPPING_VERSION and applies an additive
#      `put_mapping` (mutable indices) / template overwrite (append series); already-current
#      clusters are untouched. Existing DOCS are never rewritten — new fields are simply absent
#      until writes populate them.
# History: v2 schema-v2 fields · v3 + javv-scan-watermarks (M3/D40) ·
#          v4 + system-users/system-roles/system-sessions (M5a/FR-18) ·
#          v5 + system-audit-log template (M5a appender; writer/replay semantics owned by M5b) ·
#          v6 + system-decisions (M5b/FR-8 — immutable except revoked_at) ·
#          v7 + ingested_at on scan-events/images (task F m-4 — server-side retention clock)
#          v8 + scanner on system-decisions + state_decision_id on findings (M5c/D22 — the
#             scanner-specific subject + projection provenance for direct-action-wins/expiry)
#          v9 + system-reports/system-report-chunks/system-notifications (M7/#32 — the scheduled
#             export queue + chunked-in-OpenSearch result blobs + the bell)
#          v10 + worker/started_at/finished_at on system-reports (M7 slice 2/#32 — claim/lease
#             diagnostics: which drain holds the lease, attempt timing for reclaim debugging)
#          v11 + javv-finding-occurrences template (M8a/#33 — full per-scan snapshot rows; the
#             point-in-time history the D28 time-travel reconstructs from)
#          v12 + javv-inventory-runs template (M8a slice 2/#33 — the inventory commit manifest;
#             "running images now/at T" reads only status=committed runs by inventory_order)
#          v13 + ptype on findings + javv-finding-occurrences (M8d/B-1/#241 — package type,
#             "os" | verbatim-lowercase ecosystem; envelope v4, v3 still accepted → null)
#          v14 + system-views (M8e/C-6/#242 — server-side saved filter views; preset =
#             SearchFilters mirror, enabled:false; all-visible, owner-or-admin mutations)
#          v15 + severity_canonical on findings + javv-finding-occurrences (D46/#274 — the
#             full-word canonical query key; verbatim severity stays display-only)
#          v16 + sla_clock_at on findings (issue 363 — the materialized D21 group clock; the
#             overdue FILTER ranges on it, the verdict stays read-time against the live policy)
#          v17 + system-jobs (issue 406 repair actions — one lease/status doc per maintenance
#             job kind; bounded at #kinds docs, OCC claim + fencing attempt_id like reports)
#          v18 + javv-ingest-failures template (issue 357 — one doc per push rejected past the
#             token check; per-cluster series under the lifecycle's drop-whole-index retention)
#          v19 + system-dashboards (issue 440 — saved dashboards: a layout of catalog panels,
#             shared with the owner, everyone or roles; panels enabled:false like a view preset)
#          v20 + kev on javv-finding-occurrences (issue 1000 — the scan's own KEV value, so a
#             past-time read gives a KEV finding the KEV deadline, as the live read does)
MAPPING_VERSION = 20

_KW = {"type": "keyword"}
_DATE = {"type": "date"}
_INT = {"type": "integer"}
_BOOL = {"type": "boolean"}

# severity buckets (D16) + total/fixable — the envelope's counts, invariant-checked at ingest
_COUNT_BUCKETS = ("crit", "high", "med", "low", "negligible", "unknown", "total", "fixable")

# 1 primary shard per INDEX-MAP; replicas auto-expand 0→1 with node count (single-node dev = green)
_BASE_SETTINGS: dict[str, Any] = {"number_of_shards": 1, "auto_expand_replicas": "0-1"}

# the shared lowercase normalizer (INDEX-MAP header): verbatim in _source, normalized for aggs
_LC_ANALYSIS = {"normalizer": {"lc": {"type": "custom", "filter": ["lowercase"]}}}


def _mappings(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "dynamic": False,
        "_meta": {"version": MAPPING_VERSION},
        "properties": properties,
    }


# --- mutable shelf (single index, no rollover) -------------------------------

_FINDINGS_PROPERTIES: dict[str, Any] = {
    "finding_key": _KW,
    "cluster_id": _KW,
    "scanner": _KW,
    "image_digest": _KW,
    "image_repo": _KW,
    "tag": _KW,
    "namespaces": _KW,  # keyword[] — a digest can span namespaces (D30); filter = array-contains
    "app": _KW,
    "cve_id": _KW,
    "package_name": _KW,
    "installed_version": _KW,
    "severity": {"type": "keyword", "normalizer": "lc"},  # verbatim in _source (D16) — display
    "severity_canonical": _KW,  # D46/#274: the full-word QUERY key (filters + facets target this)
    "severity_rank": {"type": "byte"},  # 5..0 sort/range key — findings only (OE-5)
    "cvss": {"type": "float"},
    "fixable": _BOOL,
    "fixed_version": _KW,
    "epss": {"type": "float"},  # grype only (null for trivy)
    "kev": _BOOL,  # grype only
    "ptype": _KW,  # package type (M8d/B-1): "os" | ecosystem string; null = pre-v4 observation
    "disagree": _BOOL,  # precomputed severity disagreement (D5a)
    "first_seen_at": _DATE,  # full precision (D37/M13)
    # the materialized D21 group clock (issue 363): min first_seen_at across the finding's
    # (cve_id, image_digest) group, cross-scanner — derived, owned by services.sla_clock
    "sla_clock_at": _DATE,
    "last_seen_at": _DATE,
    "last_scan_run_id": _KW,
    "last_scan_order": {"type": "long"},  # newer-scan-wins guard key (D40/C-r3)
    "last_scan_at": _DATE,
    "present": _BOOL,  # presence ⟂ state (D39/M10-r2)
    "resolved_at": _DATE,
    "state": _KW,  # open|acknowledged|not_affected|risk_accepted|resolved|stale
    "vex_justification": _KW,
    "assignee": _KW,
    "notes": {"type": "text"},
    "pre_stale_status": _KW,
    "state_decision_id": _KW,  # projection provenance (M5c): set by project, cleared by triage
    "schema_version": {"type": "short"},
}

# system-config (M2): a small key/value config shelf — SLA policy, rollover/retention/staleness
# settings, and the snapshot-repo ref (creds live in the OS keystore, never here). `value` is an
# opaque object (`enabled:false`): stored in _source, never indexed, so heterogeneous config
# payloads can't explode the mapping. Fetch by `_id` (the config key), never aggregate.
_CONFIG_PROPERTIES: dict[str, Any] = {
    "key": _KW,  # the config key — also the doc _id (e.g. "snapshot_repo")
    "value": {"type": "object", "enabled": False},  # opaque blob, kept in _source, not indexed
    "updated_at": _DATE,
    "updated_by": _KW,
}

_TOKENS_PROPERTIES: dict[str, Any] = {
    "token_hash": _KW,  # peppered SHA-256 of a 256-bit random token — never the raw value (D38)
    "cluster_id": _KW,  # authz binding: payload must match token scope (SEC-3)
    "scanner": _KW,
    "scope": _KW,  # "push:findings"
    "created_by": _KW,
    "created_at": _DATE,
    "expiry": _DATE,
    "disabled": _BOOL,
    "last_ingest_at": _DATE,  # scanner-down guard
}

# javv-scan-orders (M3/D45): the AUTHORITATIVE per-(cluster,scanner) scan_order counter —
# #clusters × #scanners docs, CAS-updated in place; no rollover/ISM/retention EVER; rebuild-state
# never touches it (unlike the derived watermarks). See CORRECTNESS-CONTRACT §2.
_SCAN_ORDERS_PROPERTIES: dict[str, Any] = {
    "cluster_id": _KW,
    "scanner": _KW,
    "max_allocated_scan_order": {"type": "long"},  # strictly increasing per (cluster_id, scanner)
    "allocated_at": _DATE,  # last allocation time (display/ops)
    "schema_version": {"type": "short"},
}

# javv-scan-watermarks (M3/D40): per-(cluster,scanner,image_digest) committed-scan watermark — the
# serialization point that makes newer-scan-wins safe *including creates* (per-doc findings state
# can't guard a finding that doesn't exist yet). CAS-bumped at commit; a run below the watermark
# skips ALL cache writes. Mutable, no rollover; bounded by the live fleet (prune with findings).
# See CORRECTNESS-CONTRACT §3.
_SCAN_WATERMARKS_PROPERTIES: dict[str, Any] = {
    "cluster_id": _KW,
    "scanner": _KW,
    "image_digest": _KW,
    "max_committed_scan_order": {"type": "long"},  # guards create AND update of findings (D40/C-r3)
    "max_committed_scan_at": _DATE,  # committed run @timestamp (display)
    "schema_version": {"type": "short"},
}

# M5a (FR-18/D33) human-auth trio. system-users: password_hash is argon2id and NEVER logged;
# auth_source/external_id are the OIDC/LDAP seam (external users = normal rows, null password_hash
# — #27 kickoff design); capabilities are denormalized from the role bundle for fast checks.
_USERS_PROPERTIES: dict[str, Any] = {
    "username": _KW,
    "password_hash": _KW,  # argon2id; null for external (ldap|oidc) users
    "role": _KW,  # → capability bundle in system-roles
    "capabilities": _KW,  # keyword[] — effective caps, denormalized
    "must_change": _BOOL,  # SEC-6: server-enforced first-login password change
    "disabled": _BOOL,
    "auth_source": _KW,  # local|ldap|oidc — the IdP seam
    "external_id": _KW,  # IdP subject/DN; null for local users
    "created_at": _DATE,
}

_ROLES_PROPERTIES: dict[str, Any] = {  # capability bundles (SEC-9); Admin holds all (D33)
    "role": _KW,
    "capabilities": _KW,  # keyword[] — can_triage, can_accept_audit_final, can_manage_*, …
}

# system-sessions (SEC-5): session_id stores the HASH of the cookie value (a leaked index can't
# replay sessions); expires_at is the authoritative TTL; revoked = logout / role-change kill.
_SESSIONS_PROPERTIES: dict[str, Any] = {
    "session_id": _KW,
    "user_id": _KW,
    "created_at": _DATE,
    "expires_at": _DATE,
    "revoked": _BOOL,
}

# system-decisions (M5b/FR-8): 1 doc per decision, IMMUTABLE except revoked_at (D39/H5-r2);
# edit = revoke+create-new under one effective_at/operation_id (D40/G-r3 — the pair tie).
# "Active at T" = created_at <= T AND (revoked_at null OR > T) AND (expiry null OR > T).
_DECISIONS_PROPERTIES: dict[str, Any] = {
    "decision_id": _KW,
    "type": _KW,  # risk_accepted|ignore_rule|not_affected
    "cve_id": _KW,
    "scope": {"properties": {"namespaces": _KW, "images": _KW}},  # empty = cluster-wide
    "apply_both_scanners": _BOOL,  # semantics pinned (D22)
    "scanner": _KW,  # required iff NOT apply-both — the D22 scanner-specific subject (M5c)
    "vex_justification": _KW,
    "justification": {"type": "text"},
    "created_by": _KW,  # gated by can_accept_audit_final (SEC-2)
    "created_at": _DATE,  # = effective_at for a create
    "expiry": _DATE,  # IMMUTABLE — change = revoke+create-new
    "revoked_at": _DATE,  # the only post-hoc stamp
    "effective_at": _DATE,  # revoke+create pair shares ONE effective_at
    "operation_id": _KW,  # ties the pair; projection waits for both (D40/G-r3)
    "cluster_id": _KW,
    "schema_version": {"type": "short"},
}

# M7/#32 scheduled-export queue. system-reports = the job doc (OCC claim + fencing attempt_id);
# `params` is an opaque request blob (enabled:false — never indexed/aggregated). Result blobs do NOT
# ride this doc: they live in system-report-chunks so a large export stays queryable + small.
_REPORTS_PROPERTIES: dict[str, Any] = {
    "report_id": _KW,
    "kind": _KW,  # export|bulk_triage
    "status": _KW,  # pending|running|done|failed
    "cluster_id": _KW,
    "requested_by": _KW,
    "run_mode": _KW,  # now|offpeak
    "params": {"type": "object", "enabled": False},  # opaque request lens/format — not indexed
    "scheduled_for": _DATE,
    "as_of_t": _DATE,  # export at a past T (M8b); absent = current state
    "created_at": _DATE,
    "attempt_id": _KW,  # fencing token — heartbeat + done CAS on it (D38/D40)
    "worker": _KW,  # claim diagnostics: which drain holds the lease
    "started_at": _DATE,
    "finished_at": _DATE,
    "heartbeat_at": _DATE,
    "lease_expires_at": _DATE,
    "retry_count": _INT,
    "bytes": {"type": "long"},  # result size (done)
    "chunk_count": _INT,
    "expires_at": _DATE,  # TTL-sweep boundary (created_at + JAVV_EXPORT_TTL_HOURS at completion)
    "error": {"type": "text"},  # failure reason (failed)
    "schema_version": {"type": "short"},
}

# system-jobs = the repair-actions surface (issue 406): ONE doc per job kind (_id = kind), so the
# index is bounded by construction. Claim/heartbeat/finalize reuse the reports OCC grammar.
_JOBS_PROPERTIES: dict[str, Any] = {
    "kind": _KW,  # one of the seven kinds in jobs/registry.py
    "status": _KW,  # idle|running|done|failed
    "requested_by": _KW,
    "attempt_id": _KW,  # fencing token — heartbeat + finalize CAS on it (D39/D40)
    "started_at": _DATE,
    "finished_at": _DATE,
    "heartbeat_at": _DATE,
    "result": {"type": "object", "enabled": False},  # the job's own count summary — not indexed
    "error": {"type": "text"},
    "schema_version": {"type": "short"},
}

# system-report-chunks = the result BLOB, chunked (~5 MiB text slices). `data` is un-indexed text
# (index:false → no inverted index, no keyword 32 KB term cap) so a chunk holds MiBs; in _source
# and streamed back on download in `seq` order. Written under the attempt_id; only the `done`
# doc's attempt_id chunks are canonical (orphans swept).
_REPORT_CHUNKS_PROPERTIES: dict[str, Any] = {
    "report_id": _KW,
    "attempt_id": _KW,
    "seq": _INT,
    "data": {"type": "text", "index": False},  # un-indexed blob slice — stored in _source only
}

# system-notifications (FR-16): the bell feed — one doc per user event. report_ready points `ref` at
# a report_id; the M9f bell polls this (no broker). read=false until dismissed.
_NOTIFICATIONS_PROPERTIES: dict[str, Any] = {
    "notification_id": _KW,
    "user_id": _KW,
    "type": _KW,  # sla_breach|assignment|report_ready|cluster_retiring
    "ref": _KW,  # referenced entity id (e.g. report_id)
    "cluster_id": _KW,
    "created_at": _DATE,
    "read": _BOOL,
}

# system-views (M8e/C-6, #242): server-side saved filter views — visible to ALL authenticated
# users, mutations owner-or-admin. `preset` is the SearchFilters mirror, {enabled:false}: views
# are fetched by _id / listed, never queried by preset innards (card counts come from
# /findings/facets at render time — server-side-everything holds).
_VIEWS_PROPERTIES: dict[str, Any] = {
    "view_id": _KW,
    "name": _KW,
    "description": {"type": "text"},
    "preset": {"type": "object", "enabled": False},  # opaque filter blob, in _source only
    "owner": _KW,  # username; immutable after create
    "created_at": _DATE,
    "updated_at": _DATE,
    "schema_version": {"type": "short"},
}

# system-dashboards (issue 440): saved dashboards. `panels` is opaque like a view's preset: a
# dashboard is fetched by _id or listed by who may see it (owner, sharing, roles), never queried
# by its panels.
_DASHBOARDS_PROPERTIES: dict[str, Any] = {
    "dashboard_id": _KW,
    "name": _KW,
    "description": {"type": "text"},
    "scanner": _KW,  # all|trivy|grype: the switch the dashboard opens with
    "panels": {"type": "object", "enabled": False},
    "sharing": _KW,  # private|everyone|roles
    "roles": _KW,
    "owner": _KW,  # user id; immutable after create
    "created_by": _KW,
    "created_at": _DATE,
    "updated_by": _KW,
    "updated_at": _DATE,
    "revision": _INT,
    "schema_version": {"type": "short"},
}

MUTABLE_INDEXES: dict[str, dict[str, Any]] = {
    "findings": {
        "settings": {"index": {**_BASE_SETTINGS, "analysis": _LC_ANALYSIS}},
        "mappings": _mappings(_FINDINGS_PROPERTIES),
    },
    "system-tokens": {
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_TOKENS_PROPERTIES),
    },
    "system-config": {  # M2 — snapshot-repo ref + other config settings
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_CONFIG_PROPERTIES),
    },
    "javv-scan-orders": {  # M3/D45 — authoritative scan_order counter
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_SCAN_ORDERS_PROPERTIES),
    },
    "javv-scan-watermarks": {  # M3/D40 — per-digest committed-scan watermark
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_SCAN_WATERMARKS_PROPERTIES),
    },
    "system-users": {  # M5a/FR-18 — humans (local + future ldap/oidc)
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_USERS_PROPERTIES),
    },
    "system-roles": {  # M5a/D33 — capability bundles
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_ROLES_PROPERTIES),
    },
    "system-sessions": {  # M5a/SEC-5 — server-side sessions
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_SESSIONS_PROPERTIES),
    },
    "system-decisions": {  # M5b/FR-8 — immutable except revoked_at
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_DECISIONS_PROPERTIES),
    },
    "system-reports": {  # M7/#32 — scheduled-export job queue (OCC claim + fencing attempt_id)
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_REPORTS_PROPERTIES),
    },
    "system-report-chunks": {  # M7/#32 — chunked result blobs (un-indexed text)
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_REPORT_CHUNKS_PROPERTIES),
    },
    "system-notifications": {  # M7/#32 (FR-16) — the bell feed
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_NOTIFICATIONS_PROPERTIES),
    },
    "system-views": {  # M8e/C-6 (#242) — server-side saved filter views
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_VIEWS_PROPERTIES),
    },
    "system-jobs": {  # issue 406 repair actions — one lease/status doc per maintenance job kind
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_JOBS_PROPERTIES),
    },
    "system-dashboards": {  # issue 440 — saved dashboards
        "settings": {"index": _BASE_SETTINGS},
        "mappings": _mappings(_DASHBOARDS_PROPERTIES),
    },
}

# --- append shelf (per-cluster series → index templates) ----------------------

_SCAN_EVENTS_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,  # display only — NOT the ordering key (D40)
    "ingested_at": _DATE,  # SERVER-stamped append time — the retention age basis (task F m-4)
    "scan_run_id": _KW,
    "scan_order": {"type": "long"},  # the catalog ordering key (D40/C-r3)
    "commit_key": _KW,  # hash(cluster_id+scanner+image_digest+scan_run_id) (D37/H3)
    "cluster_id": _KW,
    "scanner": _KW,  # scanner is a FIELD, not part of the index name (D38/M15)
    "scanner_version": _KW,  # provenance (D41)
    "scanner_db_version": _KW,
    "scanner_db_built": _DATE,
    "namespaces": _KW,
    "image_repo": _KW,
    "image_digest": _KW,
    "tag": _KW,
    "app": _KW,
    # D44/FR-25: what the cycle ran with — stored for display/audit, deliberately NOT indexed
    # (enabled:false keeps it in _source without mapping churn as tuning settings evolve)
    "effective_config": {"type": "object", "enabled": False},
    **{bucket: _INT for bucket in _COUNT_BUCKETS},
    "schema_version": {"type": "short"},
}

_IMAGES_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,
    "ingested_at": _DATE,  # SERVER-stamped append time — the retention age basis (task F m-4)
    "scan_run_id": _KW,
    "inventory_run_id": _KW,  # "running now/at T" reads the latest committed run (D37/H5)
    "cluster_id": _KW,
    "image_digest": _KW,
    "image_repo": _KW,
    "tag": _KW,
    "namespaces": _KW,  # schema-v2 observed topology (audit finding #1)
    "app": _KW,
    "scanners": _KW,  # scanners that reported this image this run
    **{bucket: _INT for bucket in _COUNT_BUCKETS},
    "trivy_count": _INT,  # count-disagreement pair (D5b)
    "grype_count": _INT,
    "count_delta": _INT,
    "replicas": _INT,  # observed at scan time — scanner-only observation
    "schema_version": {"type": "short"},
}

# javv-finding-occurrences-* (M8a/FR-5b): 1 immutable row per finding per scan — the full
# per-scan snapshot history point-in-time reads reconstruct from. `_id = hash(scan_run_id +
# finding_key)` (D18). Ordered by `scan_order`, read ONLY via the scan-events catalog (R-CATALOG,
# D37/D40). No `severity_rank` (OE-5) and no state field — absence in a later snapshot = resolved.
_OCCURRENCES_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,  # scan time — display only, NOT the ordering key (D40)
    "ingested_at": _DATE,  # SERVER-stamped append time — the retention age basis (task F m-4)
    "scan_run_id": _KW,  # valid only if a scan-events commit doc exists for the run
    "scan_order": {"type": "long"},  # the ordering key (D40/C-r3)
    "commit_key": _KW,  # = scan-events commit_key; symmetric-query membership (D39)
    "cluster_id": _KW,
    "scanner": _KW,
    "image_digest": _KW,  # reconstruction identity (content-addressed)
    "namespaces": _KW,
    "vuln_id": _KW,  # CVE pivot (= cve_id elsewhere)
    "package_name": _KW,
    "package_version": _KW,  # = findings.installed_version
    "finding_key": _KW,  # per-row identity
    "severity": {"type": "keyword", "normalizer": "lc"},  # as-of-then, verbatim in _source (D16)
    "severity_canonical": _KW,  # D46/#274: the full-word query key, as-of-then
    "cvss": {"type": "float"},
    "fixable": _BOOL,
    "fixed_version": _KW,
    "ptype": _KW,  # package type (M8d/B-1): "os" | ecosystem string; null on v3-era rows
    # as-of-then (issue 1000): the past-time SLA deadline; absent on rows written before v20
    "kev": _BOOL,
    "schema_version": {"type": "short"},
}

# javv-inventory-runs-* (M8a slice 2, D39/H4-r2): 1 immutable manifest per inventory cycle — the
# catalog for inventory COMPLETENESS (the images analog of scan-events). Written last; "running
# images now/at T" reads only `status=committed` runs ordered by `inventory_order` (D40/F-r3).
# `_id = inventory_run_id` (= the cycle's scan_run_id, #33).
_INVENTORY_RUNS_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,  # run completion time (display)
    "inventory_run_id": _KW,
    "inventory_order": {"type": "long"},  # backend-allocated (D45 basis), per cluster
    "cluster_id": _KW,
    "started_at": _DATE,
    "completed_at": _DATE,
    "expected_count": _INT,  # images discovered this run
    "written_count": _INT,  # image docs that landed (== expected when committed)
    "status": _KW,  # committed | partial | failed — only committed is read
    "schema_version": {"type": "short"},
}

# system-audit-log-* (SND-2/D38-H8): 1 immutable structured row per field change / auth event.
# Template landed with M5a's thin appender so auth events never write into a dynamic-mapped index;
# **M5b owns the writer + replay semantics** (latest-entry-per-field, revision ordering). Append
# only; time-rollover; kept long — deliberately NOT in the M4 lifecycle SERIES (retention is an
# M5b/M9e decision). Order by (@timestamp, event_id); same-(entity,field) by `revision` (D40/H-r3).
_AUDIT_LOG_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,
    "event_id": _KW,  # unique per event; tiebreak for UNRELATED events
    "actor": _KW,  # user_id (or "system")
    "action": _KW,  # assign|…|login|logout|pwd_change|role_change|token_mint|token_revoke
    "entity_type": _KW,  # finding|decision|user|token|session|…
    "entity_id": _KW,
    "finding_key": _KW,  # convenience target for finding actions
    "target_ids": _KW,  # bulk actions: the FROZEN affected set (H8)
    "target_selector": {"type": "object", "enabled": False},  # provenance only; replay uses ids
    "result_hash": _KW,
    "result_count": _INT,
    "cluster_id": _KW,
    "field": _KW,  # e.g. state|assignee|notes
    "field_type": _KW,  # scalar|text|json
    "revision": {"type": "long"},  # same-(entity,field) causal order (D40/H-r3)
    "old_value": _KW,
    "new_value": _KW,
    "old_value_json": {"type": "object", "enabled": False},
    "new_value_json": {"type": "object", "enabled": False},
    "decision_id": _KW,
    "schema_version": {"type": "short"},
}

# javv-ingest-failures-* (issue 357): 1 immutable doc per push rejected PAST the token check
# (401/429 write nothing), routed on the token's cluster, never the payload's. The table behind
# scanner status's failed-ingests panel. `error` is display-only, so it is neither indexed nor
# aggregatable; `failure_id` is the unique tiebreak for the newest-first paged read.
_INGEST_FAILURES_PROPERTIES: dict[str, Any] = {
    "@timestamp": _DATE,  # server time of the rejection
    "ingested_at": _DATE,  # same server stamp — the lifecycle retention basis (task F m-4)
    "failure_id": _KW,
    "cluster_id": _KW,  # the TOKEN's cluster
    "scanner": _KW,  # the TOKEN's scanner — a field, never in the index name (D38)
    "stage": _KW,  # receive | decode | validate | authorize | store
    "reason": _KW,  # the javv_ingest_rejected_total label
    "status": {"type": "short"},  # the HTTP status the scanner got
    "error": {"type": "keyword", "index": False, "doc_values": False},
    "image_ref": {"type": "keyword", "ignore_above": 512},  # null before the body parsed
    "schema_version": {"type": "short"},
}

INDEX_TEMPLATES: dict[str, dict[str, Any]] = {
    "system-audit-log": {
        "index_patterns": ["system-audit-log-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_AUDIT_LOG_PROPERTIES),
        },
    },
    "javv-scan-events": {
        "index_patterns": ["javv-scan-events-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_SCAN_EVENTS_PROPERTIES),
        },
    },
    "javv-images": {
        "index_patterns": ["javv-images-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_IMAGES_PROPERTIES),
        },
    },
    "javv-finding-occurrences": {  # M8a/#33 — per-scan snapshot rows
        "index_patterns": ["javv-finding-occurrences-*"],
        "priority": 10,
        "template": {
            # the lc normalizer must ship with the template — `severity` aggs fold on it (D16)
            "settings": {"index": {**_BASE_SETTINGS, "analysis": _LC_ANALYSIS}},
            "mappings": _mappings(_OCCURRENCES_PROPERTIES),
        },
    },
    "javv-inventory-runs": {  # M8a slice 2/#33 — inventory commit manifests
        "index_patterns": ["javv-inventory-runs-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_INVENTORY_RUNS_PROPERTIES),
        },
    },
    "javv-ingest-failures": {  # issue 357 — failed-ingest records
        "index_patterns": ["javv-ingest-failures-*"],
        "priority": 10,
        "template": {
            "settings": {"index": _BASE_SETTINGS},
            "mappings": _mappings(_INGEST_FAILURES_PROPERTIES),
        },
    },
}

# --- bootstrap ---------------------------------------------------------------


def _template_version(existing: dict[str, Any]) -> int:
    tmpl = existing["index_templates"][0]["index_template"]
    meta = tmpl.get("template", {}).get("mappings", {}).get("_meta", {})
    return int(meta.get("version", 0))


def _prefixed_template(body: dict[str, Any], prefix: str) -> dict[str, Any]:
    if not prefix:
        return body
    return {**body, "index_patterns": [prefix + p for p in body["index_patterns"]]}


async def bootstrap(client: AsyncOpenSearch, *, prefix: str = "") -> dict[str, str]:
    """Create/upgrade every M1 index + template. Returns {name: created|updated|unchanged}.

    Idempotent and versioned: an index/template already at MAPPING_VERSION is untouched; an older
    one gets an additive `put_mapping`/template overwrite. `prefix` isolates names (tests only).
    """
    results: dict[str, str] = {}

    for name, body in MUTABLE_INDEXES.items():
        full = prefix + name
        if await client.indices.exists(index=full):
            # keyed by the real index name: after a breaking migration `full` is an alias of the
            # copy (docs/engineering/UPGRADES.md, "A breaking change", issue 261)
            (current,) = (await client.indices.get_mapping(index=full)).values()
            version = int(current["mappings"].get("_meta", {}).get("version", 0))
            if version >= MAPPING_VERSION:
                results[full] = "unchanged"
            else:
                await client.indices.put_mapping(index=full, body=body["mappings"])
                results[full] = "updated"
        else:
            try:
                await client.indices.create(index=full, body=body)
                results[full] = "created"
            except RequestError as exc:  # two pods bootstrapping at once — the other one won
                if exc.error != "resource_already_exists_exception":
                    raise
                results[full] = "unchanged"

    for name, body in INDEX_TEMPLATES.items():
        full = prefix + name
        if await client.indices.exists_index_template(name=full):
            existing = await client.indices.get_index_template(name=full)
            if _template_version(existing) >= MAPPING_VERSION:
                results[full] = "unchanged"
                continue
            action = "updated"
        else:
            action = "created"
        await client.indices.put_index_template(name=full, body=_prefixed_template(body, prefix))
        results[full] = action

    return results


if __name__ == "__main__":  # pragma: no cover — thin runner; logic is bootstrap() above
    import asyncio

    from backend.core.opensearch_client import build_client
    from backend.core.settings import get_settings

    async def _main() -> None:
        settings = get_settings()
        client = build_client(settings)
        try:
            for index_name, outcome in (await bootstrap(client)).items():
                print(f"{outcome:9s} {index_name}")
        finally:
            await client.close()

    asyncio.run(_main())


def summarize_actions(results: dict[str, str]) -> dict[str, list[str]]:
    """Invert {index: action} → {action: [indexes]} for the startup log line (#156): index names
    must be list VALUES, never dict keys — the (deliberately broad) redaction processor masks any
    key containing `token`, so `system-tokens` as a key came out `[REDACTED]`."""
    summary: dict[str, list[str]] = {}
    for name, action in results.items():
        summary.setdefault(action, []).append(name)
    return {action: sorted(names) for action, names in summary.items()}
