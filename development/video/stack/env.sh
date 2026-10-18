# shellcheck shell=bash
# Shared by the scripts of the video stack. The stack has its own store, backend and app, on
# loopback ports away from the dev stack (9200, 8000, 5173): the walks change triage data, and
# never in the dev store.
VIDEO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPO=$(cd "$VIDEO_DIR/../.." && pwd)
# passwords and the secret key, one 600 file each; never printed
SECRETS=${JAVV_VIDEO_SECRETS:-$VIDEO_DIR/sec}
STORE_NAME=javv-os-video
STORE_PORT=9203
BACKEND_PORT=8010
APP_PORT=8091
export SECRETS STORE_PORT BACKEND_PORT APP_PORT REPO VIDEO_DIR STORE_NAME

# the PID that listens on a loopback port, or nothing
port_pid() {
  ss -ltnp | grep "127.0.0.1:$1 " | grep -oP 'pid=\K[0-9]+' | head -1 || true
}
