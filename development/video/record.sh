#!/usr/bin/env bash
# Records the screenshots of all six videos on a new video stack. The walks change triage data,
# so they run in this order, on one store: 2 sets a state, 3 accepts and revokes a risk, 4 makes a
# bulk change, and 6 shows the history of all three. Takes about 15 minutes.
set -euo pipefail
# shellcheck source=SCRIPTDIR/stack/env.sh
source "$(dirname "$0")/stack/env.sh"
"$VIDEO_DIR/stack/start.sh"
started=$(date +%s)
rm -f "$VIDEO_DIR/out/state/v2-cve.txt" "$VIDEO_DIR/out/state/v3-cve.txt"

walk() {
  echo "== walk $1"
  # each screenshot prints one line; show only the rest
  (cd "$REPO/frontend" && node "$VIDEO_DIR/record/walk-v$1.mjs") | { grep -v '^shot' || true; }
}
for v in 1 2 3 4; do walk "$v"; done

# Video 5: the scanners of staging-eu sent their last results at start. Short timers for that
# cluster (in days: 0.005 is 7.2 minutes), then a sweep, mark its findings Stale.
wait_s=$((9 * 60 - ($(date +%s) - started)))
if [ "$wait_s" -gt 0 ]; then
  echo "== waiting $wait_s seconds: staging-eu must be silent for 7.2 minutes"
  sleep "$wait_s"
fi
(
  cd "$REPO/backend"
  JAVV_OPENSEARCH_URL="http://localhost:$STORE_PORT"
  JAVV_SECRET_KEY="$(cat "$SECRETS/secret_key")"
  export JAVV_OPENSEARCH_URL JAVV_SECRET_KEY
  uv run python -m backend.jobs.staleness --set-freshness-days 0.003 \
    --set-scanner-down-days 0.005 --cluster staging-eu | tail -1
  uv run python -m backend.jobs.staleness | tail -1
)
for v in 5 6; do walk "$v"; done
echo "all walks done; the screenshots are in $VIDEO_DIR/public"
