#!/usr/bin/env bash
# The backend of the video stack, in the foreground: start.sh runs it detached.
set -euo pipefail
# shellcheck source=SCRIPTDIR/env.sh
source "$(dirname "$0")/env.sh"
JAVV_SECRET_KEY="$(cat "$SECRETS/secret_key")"
JAVV_BOOTSTRAP_ADMIN_PASSWORD="$(cat "$SECRETS/admin_boot_pass")"
export JAVV_SECRET_KEY JAVV_BOOTSTRAP_ADMIN_PASSWORD
export JAVV_OPENSEARCH_URL="http://localhost:$STORE_PORT"
export JAVV_BOOTSTRAP_ADMIN_USERNAME=admin
# no sweeps on a schedule: video 5 runs the staleness sweep itself
export JAVV_SCHEDULER_ENABLED=false
export JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50
# plain http on loopback
export JAVV_SESSION_COOKIE_SECURE=false
cd "$REPO/backend"
uv run python -m backend.core.bootstrap
exec uv run uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
