#!/usr/bin/env bash
#
# Ingest round trip (issue 631): compare what `python -m scanner.compat --push --summary` sent with
# what the store now holds for that run. The push path is binary → adapters → envelope → ingest →
# store; the compat gate alone stops at the envelope. Checks, for the summary's scan_run_id:
#   - the run's occurrences per canonical severity equal the counts of its scan event, and their
#     total. Both count findings: a report lists a finding once per file that holds the package,
#     and ingest keeps one finding per key (issue 1076)
#   - the scan event's report_entries equals the entries the envelope sent (counts.total)
#   - the run's scan event carries the scanner version the binary reported
#   - the run's history rows hold the file paths that the envelope sent, each one once
#     (issue 1077); the fixtures stay under the cap of 64 paths on one finding
#   - the run's inventory is committed
# Reads OpenSearch directly: the backend offers no machine-token read of a run.
#
#   development/scripts/check-ingest-roundtrip.sh <summary.json> [opensearch-url]
#
# Requires: curl, jq.
set -euo pipefail

summary=${1:?usage: check-ingest-roundtrip.sh <summary.json> [opensearch-url]}
OS=${2:-http://localhost:9200}

run=$(jq -r .scan_run_id "$summary")
cluster=$(jq -r .cluster_id "$summary")
scanner=$(jq -r .scanner "$summary")
version=$(jq -r .scanner_version "$summary")
fail=0
bad() { echo "::error::$scanner round trip: $*"; fail=1; }

curl -sf -X POST "$OS/_refresh" >/dev/null

run_filter="{\"bool\":{\"filter\":[{\"term\":{\"scan_run_id\":\"$run\"}},{\"term\":{\"cluster_id\":\"$cluster\"}},{\"term\":{\"scanner\":\"$scanner\"}}]}}"
stored=$(curl -sf "$OS/javv-finding-occurrences*/_search" -H 'content-type: application/json' -d "{
  \"size\": 0, \"track_total_hits\": true, \"query\": $run_filter,
  \"aggs\": {\"sev\": {\"terms\": {\"field\": \"severity_canonical\", \"size\": 10}}}}")

event=$(curl -sf "$OS/javv-scan-events-$cluster-*/_search" -H 'content-type: application/json' \
  -d "{\"size\": 1, \"query\": $run_filter}" | jq '.hits.hits[0]._source // {}')

# the scan event's count columns keep the short names (D46 COUNT_COLUMN); the store keys on full words
for pair in crit:critical high:high med:medium low:low negligible:negligible unknown:unknown; do
  column=${pair%%:*}; severity=${pair#*:}
  counted=$(jq -r ".$column // \"none\"" <<<"$event")
  got=$(jq -r --arg s "$severity" '[.aggregations.sev.buckets[] | select(.key == $s) | .doc_count] | add // 0' <<<"$stored")
  [ "$counted" = "$got" ] || bad "$severity: scan event counts $counted, stored $got"
done
findings=$(jq -r '.total // "none"' <<<"$event")
got_total=$(jq -r .hits.total.value <<<"$stored")
[ "$findings" = "$got_total" ] || bad "total: scan event counts $findings, stored $got_total"

sent_entries=$(jq -r .counts.total "$summary")
entries=$(jq -r '.report_entries // "none"' <<<"$event")
[ "$sent_entries" = "$entries" ] || bad "entries: sent $sent_entries, stored $entries"

got_version=$(jq -r '.scanner_version // "none"' <<<"$event")
[ "$got_version" = "$version" ] || bad "scan event scanner_version: sent $version, stored $got_version"

# the paths are stored, not indexed (INDEX-MAP), so read them back from _source
sent_paths=$(jq -c '.paths // "none"' "$summary")
[ "$sent_paths" != '"none"' ] || bad "the summary lists no paths: the scanner predates issue 1077"
rows=$(curl -sf "$OS/javv-finding-occurrences*/_search" -H 'content-type: application/json' -d "{
  \"size\": 10000, \"track_total_hits\": true, \"_source\": [\"locations\"], \"query\": $run_filter}")
[ "$(jq -r .hits.total.value <<<"$rows")" -le 10000 ] || bad "more than 10,000 rows: read them in pages"
stored_paths=$(jq -c '[.hits.hits[]._source.locations // [] | .[]] | unique' <<<"$rows")
if [ "$sent_paths" != '"none"' ] && [ "$stored_paths" != "$sent_paths" ]; then
  only_sent=$(jq -nc --argjson a "$sent_paths" --argjson b "$stored_paths" '$a - $b | .[0:3]')
  only_stored=$(jq -nc --argjson a "$stored_paths" --argjson b "$sent_paths" '$a - $b | .[0:3]')
  bad "paths: sent $(jq length <<<"$sent_paths"), stored $(jq length <<<"$stored_paths"); only sent $only_sent, only stored $only_stored"
fi
paths=$(jq length <<<"$stored_paths")

status=$(curl -sf "$OS/javv-inventory-runs*/_search" -H 'content-type: application/json' \
  -d "{\"size\": 1, \"query\": {\"term\": {\"inventory_run_id\": \"$run\"}}}" \
  | jq -r '.hits.hits[0]._source.status // "missing"')
[ "$status" = "committed" ] || bad "inventory run $run is $status, not committed"

if [ "$fail" -ne 0 ]; then exit 1; fi
echo "OK $scanner $version: run $run stored what was sent ($sent_entries entries, $findings findings, $paths paths), inventory committed"
