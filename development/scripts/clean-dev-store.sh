#!/usr/bin/env bash
#
# Dev-store test-residue sweep (#410 §5, second-bite rule). The backend pytest suite runs against
# the shared dev OpenSearch and leaves debris that poisons later suites and demos: `t-<hex>-*` and
# `pytest-<hex>-*` prefix-isolated indices and index templates (only on fixture crashes since
# issue 550; before it every run leaked ~1,236 templates, and 51k of them made the store ~5x
# slower per test), `javv-*-c-*` series for throwaway `c-*` test
# clusters, `nu-*`/`ext-*`/`0-list-*`/`u-*` users, `rt-*` saved-view docs, cluster-scoped config
# docs for test clusters, and `c-*`-tenant rows in the mutable caches.
#
# Default is a DRY RUN (prints what it would delete). Pass --apply to actually delete.
# Never touches: the {admin, rig} users, real-cluster (uuid) data, real-actor audit history.
# Audit rows journaled BY test actors (u-*/nu-*/ext-*/0-list-* logins, job triggers, store
# inspects) ARE purged — once fleet-scoped rows became visible in the audit screen, that
# residue flooded the actor facet on the dev store. Append-forever applies to real history,
# not test debris.
#
set -euo pipefail

OS_URL="${JAVV_OPENSEARCH_URL:-http://localhost:9200}"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

say() { printf '%s\n' "$*"; }

# --- 1. whole residue indices -------------------------------------------------------------
for pattern in "t-*" "pytest-*" "restored-pytest-*" "javv-*-c-*"; do
  hits=$(curl -s "$OS_URL/_cat/indices/$pattern?h=index" 2>/dev/null | grep -v '^\.' || true)
  if [ -n "$hits" ]; then
    say "indices matching $pattern:"
    say "$hits"
    if [ "$APPLY" = 1 ]; then
      while IFS= read -r idx; do
        curl -s -XDELETE "$OS_URL/$idx" >/dev/null && say "  deleted $idx"
      done <<<"$hits"
    fi
  else
    say "indices matching $pattern: none"
  fi
done

# --- 1b. prefix-isolated index templates (the real ones are javv-* and system-*) -----------
for pattern in "t-*" "pytest-*"; do
  n=$(curl -s "$OS_URL/_index_template" | jq --arg p "${pattern%\*}" \
    '[.index_templates[].name | select(startswith($p))] | length')
  say "index templates matching $pattern: $n"
  if [ "$APPLY" = 1 ] && [ "$n" -gt 0 ]; then
    curl -s -XDELETE "$OS_URL/_index_template/$pattern" >/dev/null && say "  deleted $n"
  fi
done

# --- 2. residue users (keep admin + rig) --------------------------------------------------
users=$(curl -s "$OS_URL/system-users/_search?size=500&_source=false" | jq -r '.hits.hits[]._id' \
  | grep -E '^(nu-|ext-|0-list-|u-)' || true)
say "residue users: ${users:-none}"
if [ "$APPLY" = 1 ] && [ -n "$users" ]; then
  while IFS= read -r u; do
    curl -s -XDELETE "$OS_URL/system-users/_doc/$u?refresh=true" >/dev/null && say "  deleted user $u"
  done <<<"$users"
fi

# --- 3. residue docs by query -------------------------------------------------------------
# rt-* saved views · cluster-scoped config for c-* test clusters · c-* tenant rows in the caches
delete_matching() { # index, query-json, label
  local index=$1 query=$2 label=$3
  local n
  n=$(curl -s "$OS_URL/$index/_count" -H 'content-type: application/json' -d "$query" 2>/dev/null \
    | jq -r '.count // 0')
  say "$label: $n docs"
  if [ "$APPLY" = 1 ] && [ "$n" != 0 ] && [ "$n" != null ]; then
    curl -s -XPOST "$OS_URL/$index/_delete_by_query?refresh=true&conflicts=proceed" \
      -H 'content-type: application/json' -d "$query" | jq -r '"  deleted \(.deleted)"'
  fi
}
delete_matching "system-views"        '{"query":{"prefix":{"view_id":"rt-"}}}'                "rt-* saved views"
delete_matching "system-views"        '{"query":{"prefix":{"owner":"u-"}}}'                   "u-*-owned saved views"
delete_matching "system-dashboards"   '{"query":{"prefix":{"owner":"u-"}}}'                   "u-*-owned dashboards"
delete_matching "system-notifications" '{"query":{"prefix":{"user_id":"u-"}}}'                "u-* notification docs"
delete_matching "system-config"       '{"query":{"wildcard":{"key":{"value":"*:c-*"}}}}'      "c-* cluster config docs"
delete_matching "findings"            '{"query":{"prefix":{"cluster_id":"c-"}}}'              "c-* findings rows"
delete_matching "javv-scan-watermarks" '{"query":{"prefix":{"cluster_id":"c-"}}}'             "c-* watermark rows"
delete_matching "javv-scan-orders"    '{"query":{"prefix":{"cluster_id":"c-"}}}'              "c-* scan-order counters"
delete_matching "system-audit-log-*"  '{"query":{"bool":{"should":[{"prefix":{"actor":"u-"}},{"prefix":{"actor":"nu-"}},{"prefix":{"actor":"ext-"}},{"prefix":{"actor":"0-list-"}}],"minimum_should_match":1}}}' "test-actor audit rows"

if [ "$APPLY" = 1 ]; then
  say "sweep applied. users kept: $(curl -s "$OS_URL/system-users/_search?size=10&_source=false" | jq -cr '[.hits.hits[]._id]')"
else
  say "dry run — re-run with --apply to delete."
fi
