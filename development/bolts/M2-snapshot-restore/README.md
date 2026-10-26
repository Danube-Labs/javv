# M2 - Snapshot/restore (durability early)

**Status:** tracked in [#24](https://github.com/Danube-Labs/javv-poc/issues/24) — live status on the GitHub issue/board

## Goal
Register a snapshot repository (FS/MinIO `repository-s3`) and automate ISM snapshots of
`findings`/`images`/`system-*`; prove a tested, automated restore drill brings a seeded
current-state doc back on a fresh node via `_restore`. Durability is pulled forward so every
later bolt builds on a recoverable store. (NFR-6.)

**Canonical refs:** [`PLAN §8 M2`](../../../docs/engineering/PLAN.md) (step 3 — "Gate: tested restore drill") ·
`SPEC` NFR-6, FR-19 (ISM-automated schedule surfaced in the Data & OpenSearch panel) ·
[`INDEX-MAP`](../../../docs/engineering/INDEX-MAP.md) (`javv-findings`, `javv-images`, `system-config`,
`system-*`) · `D26` (rollover/retention/snapshot knobs).

## Depends on
- M1 (index bootstrap + ingest skeleton — the index templates and a real `findings`/`images`/`system-config`
  doc to snapshot and restore must already exist).

## Deliverables
The actual files/modules this bolt creates — **in the layered tree, not here** (paths proposed):
- `deploy/opensearch/snapshot-repo.yaml` — register the snapshot repository (FS for local/CI, `repository-s3`/MinIO for k3s);
  repo credentials live in the OpenSearch keystore, **never** in `system-config` (only the repo *ref* is stored there).
- `backend/src/backend/admin/snapshot.py` — thin helpers to register the repo, read/write the snapshot-repo ref in `system-config`,
  and trigger an on-demand snapshot (used by the restore-drill harness and, later, FR-19 admin panel).
- `deploy/opensearch/ism-snapshot-policy.json` — ISM policy: automated periodic snapshot of `javv-findings`/`javv-images`/`system-*`
  (schedule + retention per D26); attaches via index template.
- `deploy/cronjobs/snapshot-verify.yaml` — k8s CronJob that runs the automated restore drill against a throwaway namespace/index prefix.
- `backend/tests/integration/test_restore_drill.py` — the automated drill itself (seed → snapshot → fresh-node `_restore` → assert round-trip).

## Definition of Done
Everything in [`standards/definition-of-done.md`](../../standards/definition-of-done.md), **plus** (each an automated test, not a promise):
- **Restore drill (automated, the PLAN gate):** seed a known `javv-findings` current-state doc + `system-config` snapshot-repo ref →
  take a snapshot → restore into a **fresh** node/index-prefix → the restored doc is byte-equal to the seed (incl. `_source` and triage fields).
- Snapshot repository registers cleanly and the repo *ref* (not credentials) is persisted in `system-config`.
- ISM snapshot policy attaches to `javv-findings`/`javv-images`/`system-*` and a snapshot fires on schedule in the integration harness.
- Restore is idempotent/repeatable: re-running the drill on an already-restored prefix is a clean no-op or clean overwrite (no partial state).

> **Scope note (AUDIT N9):** at M2's position in the build order, neither `system-users` nor `system-audit-log`/triage exist
> (those land in M5a/M5b). M2's gate is therefore scoped to **indices + a seeded current-state doc round-trip via `_restore`**.
> The full "triage state **and users** return after a fresh node" re-verification (PLAN step 3's broader wording) is re-run as a
> follow-up drill **after M5a (users/sessions) and M5b (audit-log)** land — it is *not* a blocker for closing M2.

## Tests to write
See [`standards/testing.md`](../../standards/testing.md) for the *how*. This bolt needs:
- **Unit:** snapshot-repo ref read/write against `system-config` (assert creds are never serialized into the doc); ISM policy body shape.
- **Integration (real OpenSearch):** register FS repo → snapshot seeded `findings`/`images`/`system-config` → `_restore` into a fresh
  index prefix → assert round-trip equality; isolate by unique index prefix and clean up.
- **Golden fixtures:** a checked-in seed `findings` doc (with triage-ish fields) whose post-restore `_source` must match exactly — the
  anti-regression anchor for the durability contract.

## Out of scope (defer)
- Full users/triage restore re-verification → re-run as a drill **after M5a/M5b** (those indices don't exist at M2's position).
- Surfacing snapshot schedule/retention in the admin UI → `Settings → Data & OpenSearch` panel (FR-19, M9e).
- Cross-cluster / DR replication → out of MVP.

## Updates

### 2026-07-02 — Config-source decision (where snapshot config lives)
"Snapshot config" is **three separate things with three homes** — deliberately not one place, and
**not env vars for app config**:

1. **Credentials** (s3 `access_key`/`secret_key`) → **OpenSearch keystore** (`s3.client.default.*`),
   set by the operator via a Helm secret at cluster provisioning. Never in `system-config`, never in
   env visible to the app, never in a doc. `SnapshotRepoRef`'s allowlist structurally refuses them.
2. **Repo registration + `path.repo`** (the fs allow-path / s3 repo definition) → **deploy manifests
   on disk** (`deploy/opensearch/snapshot-repo.yaml`, GitOps-applied), because it's cluster-level infra
   that needs the keystore/`path.repo` to exist first and must be reproducible/auditable. For local/CI
   the drill registers an **fs** repo programmatically via `register_repository`.
3. **Which repo to use + schedule/retention** → the **`system-config` ref** (the app's pointer to a
   registered repo, non-secret) + the **ISM policy JSON** (indices/schedule/retention). The ref is
   edited via the **JAVV UI** later (FR-19/D26, M9e); until then a one-time write/CLI. The deploy
   manifest *creates* the repo in OpenSearch; the `system-config` ref *names* it for the app — complementary.

**Testing needs no S3.** The restore drill uses an **fs** repository = a local directory the OpenSearch
container can write to (`path.repo`). s3/MinIO is k3s-prod only. Slice 2 sets `path.repo` on the dev
compose + the CI service container; no external infra. No `settings.py` snapshot fields — the repo ref
lives in `system-config` (data), not process config.

### 2026-07-02 — Slice 3 scoping (SM policy now, deploy manifests → M10)
Scheduled snapshots use OpenSearch's native **Snapshot Management (SM)** policy
(`_plugins/_sm/policies`), not ISM (ISM = index rollover/delete; SM = scheduled snapshots) and
not a CronJob — OpenSearch takes + prunes the snapshot itself, so coordination stays in OpenSearch
(no-broker constraint). Policy body lives in code (`admin/snapshot.py`, source of truth like the
bootstrap mappings), D26-configurable; `create_snapshot_policy` registers it. The k8s deploy
manifests originally listed here — `snapshot-repo.yaml` (repo registration) and the
`snapshot-verify` CronJob (scheduled restore-drill) — are **deferred to M10**, where the Helm chart
lives; building them now (no chart yet, untestable) would be speculative. The PLAN gate (the
automated restore drill) is met in Slice 2 and doesn't depend on them.

### 2026-10-06: what M10 did not build (issue 754)

The deploy manifests deferred to M10 above were not built there. No chart registers a snapshot
repository: `docs/DEPLOYING.md` leaves that to the deployment (`PUT _snapshot/<name>`, with its
credentials in OpenSearch's keystore), and JAVV's least-privilege role cannot do it (issue 729).
There is no `snapshot-verify` CronJob or scheduled snapshot; issue 664 carries scheduled snapshots.

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
