#!/usr/bin/env bash
# Seed the CI route smoke's backend (#383, testing.md §4): bootstrap-admin login + must_change
# rotation, an ingest token per cluster, the GOLDEN trivy envelope (backend/tests/fixtures — the
# single source of truth for the ingest contract; when the contract changes, the fixture PR
# updates this seed for free), and the inventory-run commit so /images reads a committed run.
# Two clusters carry it: the fixture's own and a second one (step 4).
#
#   BACKEND=http://localhost:8000 ADMIN_PW_INIT=… ADMIN_PW=… ./development/scripts/seed-smoke.sh
#
# Mirrors development/e2e/smoke.sh §1/§3 (login/rotate/mint idiom) without k3d — the envelope
# replaces real scanners. Idempotent: re-runs re-push the same deterministic scan_run_id.
set -euo pipefail

BACKEND="${BACKEND:-http://localhost:8000}"
ADMIN_PW_INIT="${ADMIN_PW_INIT:?set ADMIN_PW_INIT}"
ADMIN_PW="${ADMIN_PW:?set ADMIN_PW}"
FIXTURE="$(dirname "$0")/../../backend/tests/fixtures/envelope-trivy-golden.json"
COOKIES="$(mktemp)"
trap 'rm -f "$COOKIES"' EXIT

fail() { echo "SEED FAILED: $1" >&2; exit 1; }

# 1. admin session (login + rotate must_change; idempotent across re-runs)
if curl -sf -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
     -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" | grep -q '"username":"admin"'; then
  echo "seed: logged in with rotated password"
else
  curl -sf -c "$COOKIES" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW_INIT\"}" >/dev/null || fail "initial login"
  curl -sf -b "$COOKIES" -c "$COOKIES" -X POST "$BACKEND/auth/password" -H 'content-type: application/json' \
    -d "{\"current_password\":\"$ADMIN_PW_INIT\",\"new_password\":\"$ADMIN_PW\"}" >/dev/null || fail "rotate"
  echo "seed: logged in + rotated must_change password"
fi

# 1b. a capability-LESS viewer (issue 460): the e2e suite needs a session that must NOT reach
# a gated route, and proving a gate with the admin session is impossible. Born must_change like
# any created user, so the password is rotated here — a must_change session can reach only
# /auth/* and would 403 everywhere, which is the wrong negative to be testing.
VIEWER_USER="${VIEWER_USER:-smoke-viewer}"
VIEWER_PW_INIT="${VIEWER_PW_INIT:-ci-smoke-viewer-init}"
VIEWER_PW="${VIEWER_PW:-ci-smoke-viewer-pw}"
if curl -sf -o /dev/null -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
     -d "{\"username\":\"$VIEWER_USER\",\"password\":\"$VIEWER_PW\"}"; then
  echo "seed: viewer $VIEWER_USER already usable"
else
  # role `viewer` is the EMPTY capability bundle (auth/capabilities.py) — exactly the negative
  # the gate test needs. The caller supplies the temp password; both it and the rotated one must
  # satisfy the password policy or the create/rotate 422s.
  curl -sf -b "$COOKIES" -o /dev/null -X POST "$BACKEND/api/v1/admin/users" \
    -H 'content-type: application/json' \
    -d "{\"username\":\"$VIEWER_USER\",\"temp_password\":\"$VIEWER_PW_INIT\",\"role\":\"viewer\"}" \
    || fail "viewer create"
  VJAR="$(mktemp)"
  curl -sf -c "$VJAR" -o /dev/null -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"$VIEWER_USER\",\"password\":\"$VIEWER_PW_INIT\"}" || fail "viewer initial login"
  curl -sf -b "$VJAR" -o /dev/null -X POST "$BACKEND/auth/password" -H 'content-type: application/json' \
    -d "{\"current_password\":\"$VIEWER_PW_INIT\",\"new_password\":\"$VIEWER_PW\"}" \
    || fail "viewer rotate"
  rm -f "$VJAR"
  echo "seed: viewer $VIEWER_USER created + rotated (role viewer — no capabilities)"
fi

# 2+3. per cluster: an ingest token, the envelope, and the inventory-run commit (status must come
# back committed)
seed_cluster() {
  local envelope="$1" cluster_id scanner token status order now pushed
  cluster_id="$(jq -r .cluster_id "$envelope")"
  scanner="$(jq -r .scanner "$envelope")"
  token="$(curl -sf -b "$COOKIES" -X POST "$BACKEND/api/v1/admin/tokens" -H 'content-type: application/json' \
    -d "{\"cluster_id\":\"$cluster_id\",\"scanner\":\"$scanner\"}" | jq -r .token)"
  [ -n "$token" ] && [ "$token" != null ] || fail "token mint ($cluster_id)"
  # the contract's cycle: the order comes from scan-runs, and the scan time is now (the backend
  # refuses an order it never handed out, and a time older than the staleness period)
  order="$(curl -sf -X POST "$BACKEND/api/v1/scan-runs" -H "Authorization: Bearer $token" | jq -r .scan_order)"
  [ -n "$order" ] && [ "$order" != null ] || fail "scan-runs ($cluster_id)"
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  pushed="$(mktemp)"
  jq --argjson order "$order" --arg now "$now" '.scan_order = $order | .last_seen_at = $now' \
    "$envelope" > "$pushed"
  curl -sf -X POST "$BACKEND/api/v1/ingest/scan" -H "Authorization: Bearer $token" \
    -H 'content-type: application/json' --data-binary "@$pushed" >/dev/null || fail "envelope ingest ($cluster_id)"
  rm -f "$pushed"
  status="$(curl -sf -X POST "$BACKEND/api/v1/inventory-runs" -H "Authorization: Bearer $token" \
    -H 'content-type: application/json' \
    -d "{\"scan_run_id\":\"$(jq -r .scan_run_id "$envelope")\",\"expected_count\":1,\"started_at\":\"$now\"}" \
    | jq -r .status)"
  [ "$status" = committed ] || fail "inventory run not committed for $cluster_id (status=$status)"
  echo "seed: cluster $cluster_id seeded — $(jq -r '.findings | length' "$envelope") findings, inventory committed"
}

seed_cluster "$FIXTURE"

# 4. a SECOND cluster (issue 666): the same golden envelope under another cluster_id, so the smoke
# can click from one cluster to the other. It is rewritten here, never a second fixture file, so
# a contract change still reaches both. The id sorts after the golden one: the registry lists
# clusters by id and a fresh browser selects the first, so every other check stays on the golden
# cluster.
SECOND="$(mktemp)"
trap 'rm -f "$COOKIES" "$SECOND"' EXIT
jq '.cluster_id = "7e57c1a5-0000-4000-8000-000000000002" | .scan_run_id = "goldenrun0002"' "$FIXTURE" > "$SECOND"
seed_cluster "$SECOND"
