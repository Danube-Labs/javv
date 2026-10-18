#!/usr/bin/env bash
# Starts the video stack from nothing: a new store, the backend, the users `admin` and `lead`
# (security lead), two made-up clusters, and the built app. Each start makes new passwords.
set -euo pipefail
# shellcheck source=SCRIPTDIR/env.sh
source "$(dirname "$0")/env.sh"
"$VIDEO_DIR/stack/stop.sh"

opensearch=$(yq -r '.datastore.opensearch' "$REPO/versions.yaml")
docker run -d --name "$STORE_NAME" -p "127.0.0.1:$STORE_PORT:9200" -e discovery.type=single-node \
  -e DISABLE_SECURITY_PLUGIN=true -e "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g" \
  "opensearchproject/opensearch:$opensearch" >/dev/null

mkdir -p "$SECRETS"
chmod 700 "$SECRETS"
umask 077
for f in secret_key admin_boot_pass admin_pass lead_pass; do
  python3 -c "import secrets; print(secrets.token_urlsafe(24), end='')" > "$SECRETS/$f"
done

until curl -s "localhost:$STORE_PORT/_cluster/health" | grep -q '"status":"\(green\|yellow\)"'; do
  sleep 2
done
echo "store ready"

mkdir -p "$VIDEO_DIR/out"
setsid -f bash -c "'$VIDEO_DIR/stack/backend.sh' > '$VIDEO_DIR/out/backend.log' 2>&1" \
  < /dev/null > /dev/null 2>&1
until curl -s -o /dev/null -w '%{http_code}' "localhost:$BACKEND_PORT/readyz" | grep -q 200; do
  sleep 2
done
echo "backend ready"

cd "$REPO/backend"
uv run python "$VIDEO_DIR/stack/setup.py"
# prod-eu-1 for videos 1 to 4 and 6; staging-eu goes silent for video 5
for c in "prod-eu-1 7 10 30" "staging-eu 3 6 20"; do
  read -r cluster seed images findings <<< "$c"
  JAVV_REPLAY_PASSWORD="$(cat "$SECRETS/admin_pass")" uv run python \
    ../development/scripts/replay_waves.py --backend "http://127.0.0.1:$BACKEND_PORT" \
    --cluster "$cluster" --seed "$seed" --images "$images" --findings "$findings" --waves 4 \
    2>&1 | tail -1
done

cd "$REPO/frontend"
npm run build > "$VIDEO_DIR/out/build.log" 2>&1
setsid -f node "$VIDEO_DIR/stack/serve.mjs" < /dev/null > "$VIDEO_DIR/out/app.log" 2>&1
until curl -s "localhost:$APP_PORT/login" | grep -q '<div id="app"'; do sleep 1; done
echo "app ready on http://127.0.0.1:$APP_PORT"
