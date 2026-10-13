#!/usr/bin/env bash
# The proof of JAVV's OpenSearch role (issue 729): with the backend signed in as a user holding
# only that role, call every surface that reaches OpenSearch and require each to succeed, then
# require OpenSearch to refuse that user what the role leaves out. Run it on a seeded backend
# (development/scripts/seed-smoke.sh first); CI's Compose stack job runs both.
#
#   BACKEND=http://localhost:8080 ADMIN_PW=… OS_ADMIN_LOGIN=admin:… OS_JAVV_LOGIN=javv:… \
#     RUN_JOB='docker compose -f deploy/compose/compose.yaml exec -T backend python -m' \
#     OS_EXEC='docker compose -f deploy/compose/compose.yaml exec -T opensearch' \
#     development/scripts/opensearch-role-walk.sh
#
# OS_EXEC runs curl where OpenSearch answers (inside its container for compose; empty to run it
# here), at OS_URL. Logins reach curl as config on stdin, never as arguments. The lifecycle part
# sets one cluster's retention to RETENTION_SECONDS and waits past it, so an index really drops.
set -euo pipefail

BACKEND="${BACKEND:?set BACKEND}"
ADMIN_PW="${ADMIN_PW:?set ADMIN_PW}"
OS_ADMIN_LOGIN="${OS_ADMIN_LOGIN:?set OS_ADMIN_LOGIN}"
OS_JAVV_LOGIN="${OS_JAVV_LOGIN:?set OS_JAVV_LOGIN}"
RUN_JOB="${RUN_JOB:?set RUN_JOB}"
OS_EXEC="${OS_EXEC:-}"
OS_URL="${OS_URL:-https://localhost:9200}"
RETENTION_SECONDS="${RETENTION_SECONDS:-60}"
FIXTURE="$(dirname "$0")/../../backend/tests/fixtures/envelope-trivy-golden.json"
C1="$(jq -r .cluster_id "$FIXTURE")"
C2=7e57c1a5-0000-4000-8000-000000000002  # seed-smoke.sh's second cluster
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

fail() { echo "WALK FAILED: $*" >&2; exit 1; }
step() { echo "walk: $*"; }

# one JAVV API call as the app's admin; prints the body, fails on any non-2xx
api() {
  local method=$1 path=$2 body=${3:-}
  local args=(-sS -b "$JAR" -X "$method" -w '\n%{http_code}' "$BACKEND$path")
  [ -n "$body" ] && args+=(-H 'content-type: application/json' -d "$body")
  local out code
  out=$(curl "${args[@]}") || fail "$method $path: no answer"
  code=${out##*$'\n'}
  out=${out%$'\n'*}
  [[ $code == 2* ]] || fail "$method $path: $code $(head -c 300 <<<"$out")"
  printf '%s' "$out"
}

# curl against OpenSearch as one login ($1), the rest are curl's arguments
os_as() {
  local login=$1; shift
  printf 'user = "%s"\n' "$(printf %s "$login" | sed 's/[\\"]/\\&/g')" |
    $OS_EXEC curl -sk -K - "$@"
}
os_status() {  # login method path [body]: prints the status code
  local login=$1 method=$2 path=$3 body=${4:-}
  local args=(-o /dev/null -w '%{http_code}' -X "$method" "$OS_URL$path")
  [ -n "$body" ] && args+=(-H 'content-type: application/json' -d "$body")
  os_as "$login" "${args[@]}"
}

job() {  # a job through the API (the three the Data inspector runs), this run waited to done
  local kind=$1 attempt run
  attempt=$(api POST "/api/v1/admin/jobs/$kind/run" | jq -r .attempt_id)
  for _ in $(seq 1 60); do
    run=$(api GET /api/v1/admin/jobs |
      jq -c --arg k "$kind" --arg a "$attempt" '.. | objects | select(.kind? == $k and .attempt_id? == $a)')
    case "$(jq -r .status <<<"$run")" in
      done) return 0 ;;
      failed) fail "job $kind failed: $run" ;;
    esac
    sleep 2
  done
  fail "job $kind (attempt $attempt) did not finish"
}

run_module() {  # a job or bootstrap in the backend's own process; its log lines are its output
  local out
  out=$($RUN_JOB "$@" 2>&1) || fail "$* failed: $(tail -n 5 <<<"$out")"
  if grep -E 'status:403|security_exception' <<<"$out"; then fail "OpenSearch refused $*"; fi
  printf '%s' "$out"
}

inspector_reads() {  # with no index the _cat reads take in every index (issue 729)
  for path in _cluster/health _cat/indices _cat/shards _nodes/stats; do
    api POST /api/v1/admin/opensearch/inspect "{\"method\":\"GET\",\"path\":\"$path\"}" >/dev/null
  done
}

backing() {  # the backing indices of a series for a cluster, as admin sees them
  os_as "$OS_ADMIN_LOGIN" -s "$OS_URL/_cat/indices/$1-$2-*?h=index&format=json" | jq -r '.[].index' | sort
}

step "the backend signs in to OpenSearch as a user holding only the javv role"
os_as "$OS_JAVV_LOGIN" -sf "$OS_URL/_plugins/_security/authinfo" |
  jq -e '.user_name == "javv" and .roles == ["javv"]' >/dev/null || fail "authinfo"

step "sign in to JAVV"
curl -sf -c "$JAR" -X POST "$BACKEND/auth/login" -H 'content-type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PW\"}" >/dev/null || fail "login"
api GET /auth/me | jq -e '.user.must_change == false' >/dev/null || fail "me"

step "readiness, version, clusters"
curl -sf "$BACKEND/readyz" >/dev/null || fail "readyz"
# /readyz answers ready even when its store checks are refused, so ask for them as javv directly
os_as "$OS_JAVV_LOGIN" -sf "$OS_URL/_cluster/health" >/dev/null || fail "cluster health as javv"
os_as "$OS_JAVV_LOGIN" -sf \
  "$OS_URL/_cluster/state/blocks/findings,javv-*,system-*?ignore_unavailable=true&allow_no_indices=true" \
  >/dev/null || fail "index blocks as javv"
api GET /api/v1/meta >/dev/null
api GET /api/v1/clusters >/dev/null

step "a second scan run over seed-smoke.sh's findings, and a push the backend refuses"
token=$(api POST /api/v1/admin/tokens "{\"cluster_id\":\"$C1\",\"scanner\":\"trivy\"}" | jq -r .token)
push() {  # an envelope on stdin; prints the status code
  curl -s -o /dev/null -w '%{http_code}' -X POST "$BACKEND/api/v1/ingest/scan" \
    -H "Authorization: Bearer $token" -H 'content-type: application/json' --data-binary @-
}
# the order comes from scan-runs and the scan time is now, as in seed-smoke.sh
order=$(curl -sf -X POST "$BACKEND/api/v1/scan-runs" -H "Authorization: Bearer $token" |
  jq -r .scan_order)
[ -n "$order" ] && [ "$order" != null ] || fail "scan-runs"
code=$(jq --argjson order "$order" --arg now "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '.scan_run_id = "walkrun0002" | .scan_order = $order | .last_seen_at = $now' "$FIXTURE" | push)
[[ $code == 2* ]] || fail "second scan run: $code"
# recorded in javv-ingest-failures-*, which the scanners screen reads back
code=$(jq '.findings = "not a list"' "$FIXTURE" | push)
[ "$code" = 422 ] || fail "a malformed push got $code, not 422"
curl -sf "$BACKEND/api/v1/scan-scope" -H "Authorization: Bearer $token" >/dev/null ||
  fail "scan-scope"

step "findings: a paged search (point in time), facets, groups, components"
page=$(api GET "/api/v1/findings?cluster_id=$C1&size=5")
cursor=$(jq -r '.next_cursor // empty' <<<"$page")
[ -n "$cursor" ] || fail "the first page carried no cursor"
api GET "/api/v1/findings?cluster_id=$C1&size=5&cursor=$cursor" >/dev/null
key=$(jq -r '.data[0].finding_key // empty' <<<"$page")
[ -n "$key" ] || fail "no finding_key on the first page: $(jq -c 'keys' <<<"$page")"
api GET "/api/v1/findings/facets?cluster_id=$C1" >/dev/null
api GET "/api/v1/findings/groups?cluster_id=$C1&by=cve_id" >/dev/null
api GET "/api/v1/findings/top-components?cluster_id=$C1" >/dev/null

step "triage: one finding, a bulk, the approvals queue"
api PATCH "/api/v1/findings/$key/triage" '{"state":"acknowledged","notes":"role walk"}' >/dev/null
cve=$(jq -r '.data[0].cve_id' <<<"$page")
api POST /api/v1/findings/bulk-triage \
  "{\"cluster_id\":\"$C1\",\"selector\":{\"cve_id\":\"$cve\"},\"patch\":{\"assignee\":\"admin\"}}" >/dev/null
api GET "/api/v1/decisions?cluster_id=$C1" >/dev/null
api GET "/api/v1/decisions/approvals?cluster_id=$C1" >/dev/null
api GET "/api/v1/decisions/approvals/export.csv?cluster_id=$C1" >/dev/null

step "trends, scanners, contributors, audit, images"
api GET "/api/v1/trends/scans?cluster_id=$C1" >/dev/null
api GET "/api/v1/trends/findings?cluster_id=$C1" >/dev/null
api GET "/api/v1/trends/ingest-failures?cluster_id=$C1" >/dev/null
api GET "/api/v1/scanners/freshness?cluster_id=$C1" >/dev/null
api GET "/api/v1/scanners/provenance?cluster_id=$C1" >/dev/null
api GET "/api/v1/scanners/ingest-failures?cluster_id=$C1&scanner=trivy" |
  jq -e '[.. | numbers] | length > 0' >/dev/null || fail "ingest failures"
api GET "/api/v1/contributors?cluster_id=$C1" >/dev/null
api GET "/api/v1/contributors/export.csv?cluster_id=$C1" >/dev/null
api GET "/api/v1/audit?cluster_id=$C1" >/dev/null
api GET "/api/v1/audit/facets?cluster_id=$C1" >/dev/null
api GET "/api/v1/audit/export.csv?cluster_id=$C1" >/dev/null
api GET "/api/v1/images?cluster_id=$C1" >/dev/null
api GET "/api/v1/images/timeline?cluster_id=$C1&image_repo=$(jq -r '.data[0].image_repo | @uri' <<<"$page")&tag=$(jq -r '.data[0].tag | @uri' <<<"$page")" >/dev/null
api GET "/api/v1/settings/scan-scope?cluster_id=$C1" >/dev/null

step "settings, views, notifications"
api PUT /api/v1/settings/sla \
  '{"critical_days":7,"high_days":30,"medium_days":90,"low_days":180,"kev_days":7}' >/dev/null
api PUT "/api/v1/clusters/$C1/name" '{"cluster_name":"walk"}' >/dev/null
view=$(api POST /api/v1/views '{"name":"role walk"}' | jq -r '.view_id // .view.view_id')
api PATCH "/api/v1/views/$view" '{"description":"walked"}' >/dev/null
api DELETE "/api/v1/views/$view" >/dev/null
api GET /api/v1/notifications >/dev/null

step "exports: inline, VEX, and a queued one built by the report drain"
api GET "/api/v1/findings/export.csv?cluster_id=$C1" >/dev/null
api GET "/api/v1/findings/export.vex?cluster_id=$C1&scanner=trivy" >/dev/null
report=$(api POST /api/v1/reports "{\"cluster_id\":\"$C1\",\"run_mode\":\"now\"}" | jq -r .report_id)
run_module backend.jobs.report_drain >/dev/null
api GET "/api/v1/reports/$report" | jq -e '.status == "done"' >/dev/null || fail "report not done"

step "the jobs the Data inspector runs, and the scheduled-only ones"
job rebuild_state
job staleness_sweep
for kind in report_sweep findings_cleanup session_sweep; do
  run_module "backend.jobs.$kind" >/dev/null
done

step "bootstrap upgrades an index on an older mapping version, as after an upgrade"
os_as "$OS_ADMIN_LOGIN" -sf -X PUT "$OS_URL/system-config/_mapping" -H 'content-type: application/json' \
  -d '{"_meta":{"version":0}}' >/dev/null || fail "lowering the mapping version"
out=$(run_module backend.core.bootstrap)
grep -q 'updated *system-config' <<<"$out" || fail "bootstrap did not update system-config: $out"
os_as "$OS_ADMIN_LOGIN" -sf "$OS_URL/system-config/_mapping" |
  jq -e '."system-config".mappings._meta.version > 0' >/dev/null || fail "mapping version"

step "the Data inspector and the runtime card"
api GET /api/v1/admin/opensearch-runtime >/dev/null
api GET "/api/v1/settings/data?cluster_id=$C1" >/dev/null
inspector_reads
api POST /api/v1/admin/opensearch/inspect \
  '{"method":"POST","path":"findings/_search","body":{"size":1}}' >/dev/null
api POST /api/v1/admin/opensearch/inspect '{"method":"GET","path":"findings/_count"}' >/dev/null
api POST /api/v1/admin/opensearch/inspect '{"method":"GET","path":"findings/_mapping"}' >/dev/null

step "snapshots: admin registers the repository, as a deployment does; JAVV takes and restores"
repo=javv-walk
os_as "$OS_ADMIN_LOGIN" -sf -X PUT "$OS_URL/_snapshot/$repo" -H 'content-type: application/json' \
  -d "{\"type\":\"fs\",\"settings\":{\"location\":\"$repo\"}}" >/dev/null || fail "repository"
os_as "$OS_ADMIN_LOGIN" -sf -X PUT "$OS_URL/system-config/_doc/snapshot_repo?refresh=true" \
  -H 'content-type: application/json' \
  -d "{\"key\":\"snapshot_repo\",\"value\":{\"repository\":\"$repo\",\"type\":\"fs\",\"settings\":{\"location\":\"$repo\"}},\"updated_at\":\"$(date -u +%FT%TZ)\",\"updated_by\":\"walk\"}" \
  >/dev/null || fail "repository ref"
snap=$(api POST /api/v1/admin/snapshots | jq -r .snapshot)
for _ in $(seq 1 60); do
  state=$(api GET /api/v1/admin/snapshots | jq -r --arg s "$snap" '.snapshots[] | select(.snapshot == $s) | .state')
  [ "$state" = SUCCESS ] && break
  [ "$state" = FAILED ] && fail "snapshot $snap failed"
  sleep 2
done
[ "$state" = SUCCESS ] || fail "snapshot $snap did not finish ($state)"
api POST "/api/v1/admin/snapshots/$snap/restore" >/dev/null
for _ in $(seq 1 60); do
  [ "$(os_status "$OS_ADMIN_LOGIN" HEAD /restored-findings)" = 200 ] && break
  sleep 2
done
[ "$(os_status "$OS_ADMIN_LOGIN" HEAD /restored-findings)" = 200 ] || fail "restore"
# the inspector lists restored-* too, so its reads must hold once a copy exists
inspector_reads
# a copy is listed, never read: it holds system-users and system-tokens too. CI's compose job
# also finds this refusal in the backend's log, which shows its log check can see one.
code=$(curl -s -b "$JAR" -o /dev/null -w '%{http_code}' -X POST "$BACKEND/api/v1/admin/opensearch/inspect" \
  -H 'content-type: application/json' -d '{"method":"POST","path":"restored-findings/_search","body":{"size":1}}')
[ "$code" = 403 ] || fail "a search of a restored copy got $code, not 403"

step "lifecycle: a series and the audit log roll over, then an old backing index drops"
api PUT /api/v1/settings/rollover \
  "{\"max_age_days\":30,\"max_docs\":1,\"max_size_gb\":50,\"cluster_id\":\"$C1\"}" >/dev/null
api PUT /api/v1/settings/rollover '{"max_age_days":30,"max_docs":1,"max_size_gb":50}' >/dev/null
retention=$(awk -v s="$RETENTION_SECONDS" 'BEGIN { printf "%.6f", s / 86400 }')
api PUT /api/v1/settings/retention "{\"retention_days\":$retention,\"cluster_id\":\"$C1\"}" >/dev/null
before=$(backing javv-scan-events "$C1")
audit_before=$(os_as "$OS_ADMIN_LOGIN" -s "$OS_URL/_cat/indices/system-audit-log-*?h=index" | wc -l)
job lifecycle_sweep
after=$(backing javv-scan-events "$C1")
[ "$(wc -l <<<"$after")" -gt "$(wc -l <<<"$before")" ] || fail "javv-scan-events did not roll over"
audit_after=$(os_as "$OS_ADMIN_LOGIN" -s "$OS_URL/_cat/indices/system-audit-log-*?h=index" | wc -l)
[ "$audit_after" -gt "$audit_before" ] || fail "system-audit-log did not roll over"
oldest=$(head -1 <<<"$before")
sleep $((RETENTION_SECONDS + 5))
job lifecycle_sweep
[ "$(os_status "$OS_ADMIN_LOGIN" HEAD "/$oldest")" = 404 ] || fail "$oldest was not dropped"
api GET "/api/v1/settings/data?cluster_id=$C2" >/dev/null

step "OpenSearch refuses the javv user what the role leaves out"
os_as "$OS_ADMIN_LOGIN" -sf -X PUT "$OS_URL/walk-other" >/dev/null || fail "admin index"
for check in \
  "GET /_plugins/_security/api/internalusers" \
  "POST /walk-other/_search" \
  "PUT /_cluster/settings {\"persistent\":{\"cluster.routing.allocation.enable\":\"all\"}}" \
  "PUT /_snapshot/walk-other {\"type\":\"fs\",\"settings\":{\"location\":\"walk-other\"}}" \
  "DELETE /findings"; do
  read -r method path body <<<"$check"
  code=$(os_status "$OS_JAVV_LOGIN" "$method" "$path" "$body")
  [ "$code" = 403 ] || fail "javv got $code, not 403, for $method $path"
done
os_as "$OS_ADMIN_LOGIN" -sf -X DELETE "$OS_URL/walk-other" >/dev/null

# left in the store: the javv-walk repository and its snapshot, the restored-* copies, and the
# cluster with a one-doc rollover and a minute's retention
echo "walk: every surface passed as javv, and each refusal held"
