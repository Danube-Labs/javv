#!/usr/bin/env bash
# Stops the video stack: the app, the backend and the store (its data goes with it).
set -euo pipefail
# shellcheck source=SCRIPTDIR/env.sh
source "$(dirname "$0")/env.sh"
for port in "$APP_PORT" "$BACKEND_PORT"; do
  pid=$(port_pid "$port")
  if [ -n "$pid" ]; then kill "$pid" && echo "stopped the process on port $port"; fi
done
docker rm -f "$STORE_NAME" >/dev/null 2>&1 && echo "removed the store $STORE_NAME" || true
