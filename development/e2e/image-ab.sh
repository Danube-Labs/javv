#!/usr/bin/env bash
#
# The old images and the new images of JAVV side by side (issue 1263). Run it after each image
# build, and put the report in the PR body.
#
#   NEW_REGISTRY=local2 development/e2e/image-ab.sh
#
# It runs the same steps for the old images (OLD_REGISTRY, by default the published ones) and then
# for the new images (NEW_REGISTRY), one after the other, each on a new store, so the two runs do
# not slow each other:
#   1. the facts of each image: size, layers, config, the tools on its PATH, the package count,
#      and the findings of each scanner in it (the old scanner images scan both, as one instrument)
#   2. the compose stack of deploy/compose on a new store, with the backend and frontend images of
#      that run, on 127.0.0.1:PORT; the time until /readyz answers
#   3. sign-in and ingest: development/scripts/seed-smoke.sh
#   4. every GET route without a path value, ROUNDS times each: status, body, time
#   5. one scan cycle of each scanner image of that run with deploy/docker/javv_docker_push.py,
#      on one fixed container, then the findings that JAVV holds for it
#   6. the memory of each container, then the logs of the backend, the frontend and the scans
# Then development/e2e/image_ab.py writes OUT/report.md, and the exit code is its exit code.
#
# The scanner databases update once at the start and stay the same for both runs, so the two scan
# cycles see the same data. Nothing touches the dev stack: the stacks have their own project names
# and volumes, and `down -v` removes them.
#
# Env: NEW_REGISTRY (required)   the registry name of the new build (build-app-images.sh REGISTRY)
#      OLD_REGISTRY              default ghcr.io/danube-labs
#      APP_TAG                   default the version in .release-please-manifest.json
#      PORT                      default 18080
#      ROUNDS                    default 5
#      TRIVY_CACHE, GRYPE_CACHE  the cache volumes, default javv-ab-cache-trivy and -grype
#      OUT                       default development/e2e/logs/image-ab/<UTC time> (git ignores it)
# Requires docker with compose, jq, curl and python3. Refuses to start at 85% disk or more: the
# low disk watermark of OpenSearch, where the dev store stops too.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
NEW_REGISTRY=${NEW_REGISTRY:?set NEW_REGISTRY to the registry name of the new build}
OLD_REGISTRY=${OLD_REGISTRY:-ghcr.io/danube-labs}
APP_TAG=${APP_TAG:-$(jq -r '."."' "$ROOT/.release-please-manifest.json")}
PORT=${PORT:-18080}
ROUNDS=${ROUNDS:-5}
TRIVY_CACHE=${TRIVY_CACHE:-javv-ab-cache-trivy}
GRYPE_CACHE=${GRYPE_CACHE:-javv-ab-cache-grype}
OUT=${OUT:-$HERE/logs/image-ab/$(date -u +%Y%m%dT%H%M%SZ)}
BASE="http://127.0.0.1:$PORT"
GOLDEN="$(jq -r .cluster_id "$ROOT/backend/tests/fixtures/envelope-trivy-golden.json")"
SCAN_CLUSTER=image-ab-docker
TARGET=javv-ab-target
PY="python3 $HERE/image_ab.py"

pin() { sed -n "/^  $1:/,/current/p" "$ROOT/versions.yaml" | grep -o 'current: "[0-9.]*"' | head -1 | grep -o '[0-9.]*'; }
TRIVY_TAG=$(pin trivy)
GRYPE_TAG=$(pin grype)

say() { printf '== %s\n' "$*"; }
fail() { printf 'image-ab FAILED: %s\n' "$*" >&2; exit 2; }
now() { date +%s.%N; }
since() { python3 -c "import sys; print(round(float(sys.argv[2]) - float(sys.argv[1]), 1))" "$1" "$(now)"; }

for tool in docker jq curl python3; do command -v "$tool" >/dev/null || fail "$tool is missing"; done
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
[ "$used" -lt 85 ] || fail "the disk is at $used%; free space first (OpenSearch stops at 85%)"
curl -s -o /dev/null "$BASE" && fail "port $PORT answers already; set PORT"

image() { # <registry> <role>
  case $2 in
    scanner-trivy) echo "$1/javv-$2:$TRIVY_TAG" ;;
    scanner-grype) echo "$1/javv-$2:$GRYPE_TAG" ;;
    *) echo "$1/javv-$2:$APP_TAG" ;;
  esac
}
ROLES="backend frontend scanner-trivy scanner-grype"
for role in $ROLES; do
  old=$(image "$OLD_REGISTRY" "$role") new=$(image "$NEW_REGISTRY" "$role")
  docker image inspect "$old" >/dev/null 2>&1 || docker pull -q "$old" >/dev/null || fail "no image $old"
  docker image inspect "$new" >/dev/null 2>&1 || fail "no image $new: build it first"
done
INSTRUMENT_TRIVY=$(image "$OLD_REGISTRY" scanner-trivy)
INSTRUMENT_GRYPE=$(image "$OLD_REGISTRY" scanner-grype)
SOCK_GID=$(stat -c %g /var/run/docker.sock)
mkdir -p "$OUT"
say "run folder $OUT"

cleanup() {
  docker rm -f "$TARGET" >/dev/null 2>&1 || true
  for side in old new; do
    [ -f "$OUT/$side/.work" ] || continue
    work=$(cat "$OUT/$side/.work")
    docker compose -p "javv-ab-$side" --project-directory "$work" -f "$work/compose.yaml" \
      -f "$work/override.yaml" down -v >/dev/null 2>&1 || true
    case "$work" in /tmp/javv-ab.*) rm -r -- "$work" ;; esac
    rm -f "$OUT/$side/.work"
  done
}
trap cleanup EXIT

# the scanners run as the image user (65532), as in a deployment: the caches must be theirs
# `|` splits the parts: an image reference holds `:`
for set in "$TRIVY_CACHE|$INSTRUMENT_TRIVY|/var/cache/javv/trivy" "$GRYPE_CACHE|$INSTRUMENT_GRYPE|/var/cache/javv/grype"; do
  IFS='|' read -r vol img dir <<<"$set"
  docker run --rm --user 0 -v "$vol:$dir" --entrypoint chown "$img" -R 65532:65532 "$dir"
done
say "update the scanner databases once, for both runs"
docker run --rm --group-add "$SOCK_GID" -v "$TRIVY_CACHE:/var/cache/javv/trivy" --entrypoint trivy \
  "$INSTRUMENT_TRIVY" image --download-db-only --quiet --cache-dir /var/cache/javv/trivy
docker run --rm -v "$GRYPE_CACHE:/var/cache/javv/grype" --entrypoint grype "$INSTRUMENT_GRYPE" db update -q
FROZEN=(-e TRIVY_SKIP_DB_UPDATE=true -e TRIVY_SKIP_JAVA_DB_UPDATE=true -e GRYPE_DB_AUTO_UPDATE=false)

# the one container that both scan cycles scan: the old backend image, asleep
docker rm -f "$TARGET" >/dev/null 2>&1 || true
docker run -d --name "$TARGET" --entrypoint sleep "$(image "$OLD_REGISTRY" backend)" infinity >/dev/null

facts() { # <registry> <role> -> one JSON object
  local img; img=$(image "$1" "$2")
  local tmp; tmp=$(mktemp -d)
  # the scanners write their reports here as the image user
  chmod 777 "$tmp"
  docker run --rm --group-add "$SOCK_GID" -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v "$TRIVY_CACHE:/var/cache/javv/trivy" -v "$tmp:/out" "${FROZEN[@]}" --entrypoint trivy \
    "$INSTRUMENT_TRIVY" image --quiet --scanners vuln --list-all-pkgs --cache-dir /var/cache/javv/trivy \
    --format json --output /out/trivy.json "$img"
  docker run --rm --group-add "$SOCK_GID" -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -v "$GRYPE_CACHE:/var/cache/javv/grype" -v "$tmp:/out" "${FROZEN[@]}" --entrypoint grype \
    "$INSTRUMENT_GRYPE" -q "docker:$img" -o json --file /out/grype.json
  local tools
  tools=$(docker run --rm --entrypoint sh "$img" -c \
    'for t in sh python python3 pip pip3 node npm npx yarn corepack uv trivy grype; do command -v "$t" >/dev/null && printf "%s " "$t"; done; true')
  local versions
  versions=$(docker run --rm --entrypoint sh "$img" -c \
    '{ command -v python >/dev/null && python --version; command -v node >/dev/null && echo "node $(node --version)"; } 2>&1 | tr "\n" " "; true')
  docker image inspect "$img" | jq --arg tools "$tools" --arg versions "$versions" \
    --argjson pkgs "$(jq '[.Results[]?.Packages[]?] | length' "$tmp/trivy.json")" \
    --argjson vulns "$($PY vulns "$tmp/trivy.json" "$tmp/grype.json")" '.[0] | {
      size_mb: ((.Size / 1000000) | floor), layers: (.RootFS.Layers | length),
      user: .Config.User, entrypoint: .Config.Entrypoint, cmd: .Config.Cmd,
      workdir: .Config.WorkingDir, ports: (.Config.ExposedPorts // {} | keys),
      healthcheck: .Config.Healthcheck.Test, env: .Config.Env,
      tools: $tools, versions: $versions, packages: $pkgs} + $vulns'
  case "$tmp" in /tmp/tmp.*) rm -r -- "$tmp" ;; esac
}

side() { # <old|new> <registry>
  local side=$1 reg=$2 dir="$OUT/$1"
  mkdir -p "$dir/logs" "$dir/scan"
  say "$side: image facts"
  local f="{}"
  for role in $ROLES; do f=$(jq --arg r "$role" --argjson v "$(facts "$reg" "$role")" '. + {($r): $v}' <<<"$f"); done
  echo "$f" > "$dir/facts.json"

  say "$side: start the stack"
  local work; work=$(mktemp -d /tmp/javv-ab.XXXXXX)
  echo "$work" > "$dir/.work"
  cp "$ROOT/deploy/compose/compose.yaml" "$ROOT/deploy/compose/setup.sh" "$ROOT/deploy/compose/.env.example" "$work/"
  # setup.sh shows the first admin password: it stays out of every log
  (cd "$work" && COMPOSE_PROJECT_NAME="javv-ab-$side" ./setup.sh >/dev/null 2>&1)
  cat > "$work/override.yaml" <<EOF
services:
  backend:
    image: $(image "$reg" backend)
  frontend:
    image: $(image "$reg" frontend)
    ports: !override
      - "127.0.0.1:$PORT:8080"
EOF
  local dc=(docker compose -p "javv-ab-$side" --project-directory "$work" -f "$work/compose.yaml" -f "$work/override.yaml")
  local t0; t0=$(now)
  "${dc[@]}" up -d --quiet-pull >/dev/null 2>&1 || fail "$side: compose up"
  local up=""
  for _ in $(seq 1 150); do
    if curl -sf "$BASE/readyz" 2>/dev/null | jq -e . >/dev/null 2>&1; then up=$(since "$t0"); break; fi
    sleep 2
  done
  [ -n "$up" ] || fail "$side: /readyz did not answer in 300 s"

  say "$side: sign-in and ingest"
  local init pw; init=$(sed -n 's/^JAVV_BOOTSTRAP_ADMIN_PASSWORD=//p' "$work/.env")
  pw="ab-$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
  t0=$(now)
  BACKEND=$BASE ADMIN_PW_INIT=$init ADMIN_PW=$pw "$ROOT/development/scripts/seed-smoke.sh" > "$dir/logs/seed.txt" 2>&1 \
    || fail "$side: seed-smoke.sh (see $dir/logs/seed.txt)"
  local seed; seed=$(since "$t0")

  say "$side: reads, $ROUNDS rounds"
  t0=$(now)
  JAVV_AB_PASSWORD=$pw $PY reads "$BASE" "$ROOT/frontend/openapi.json" "$GOLDEN" "$ROUNDS" > "$dir/reads.jsonl"
  local reads; reads=$(since "$t0")

  local jar; jar=$(mktemp)
  curl -sf -c "$jar" -X POST "$BASE/auth/login" -H 'content-type: application/json' \
    -d "$(jq -n --arg p "$pw" '{username: "admin", password: $p}')" >/dev/null
  # every place on this host but the one target container
  local skip
  skip=$(docker ps --format '{{.Label "com.docker.compose.project"}}|{{.Names}}' \
    | awk -F'|' -v t="$TARGET" '{p = ($1 != "") ? $1 : $2; if (p != t) print p}' | sort -u | paste -sd, -)
  local scans="{}"
  for s in trivy grype; do
    say "$side: scan cycle of the $s image"
    local token; token=$(curl -sf -b "$jar" -X POST "$BASE/api/v1/admin/tokens" -H 'content-type: application/json' \
      -d "{\"cluster_id\":\"$SCAN_CLUSTER\",\"scanner\":\"$s\"}" | jq -r .token)
    local vol=$TRIVY_CACHE; [ "$s" = grype ] && vol=$GRYPE_CACHE
    t0=$(now)
    local code=0
    docker run --rm --network host --group-add "$SOCK_GID" -v /var/run/docker.sock:/var/run/docker.sock \
      -v "$ROOT/deploy/docker/javv_docker_push.py:/javv/javv_docker_push.py:ro" -v "$vol:/var/cache/javv/$s" \
      "${FROZEN[@]}" -e JAVV_BACKEND_URL="$BASE" -e JAVV_CLUSTER_ID="$SCAN_CLUSTER" -e JAVV_SCANNER="$s" \
      -e JAVV_TOKEN="$token" -e JAVV_DOCKER_SKIP_PROJECTS="$skip" --entrypoint python3 \
      "$(image "$reg" "scanner-$s")" /javv/javv_docker_push.py > "$dir/logs/scan-$s.log" 2>&1 || code=$?
    scans=$(jq --arg s "$s" --argjson v "$(since "$t0")" '. + {("scan_" + $s + "_seconds"): $v}' <<<"$scans")
    JAVV_AB_PASSWORD=$pw $PY findings "$BASE" "$SCAN_CLUSTER" "$s" \
      | jq --argjson code "$code" '{exit: $code, findings: .}' > "$dir/scan/$s.json"
  done
  rm -f "$jar"

  local mem
  mem=$(docker stats --no-stream --format '{{.Name}}|{{.MemUsage}}' | awk -F'|' -v p="javv-ab-$side-" \
    'index($1, p) == 1 {split($2, m, " / "); sub(p, "", $1); sub(/-[0-9]+$/, "", $1); print $1 "\t" m[1]}' \
    | jq -R 'split("\t") | {("memory_" + .[0]): .[1]}' | jq -s 'add // {}')
  for c in backend frontend; do "${dc[@]}" logs --no-color --no-log-prefix "$c" > "$dir/logs/$c.log" 2>&1; done
  jq -n --argjson up "$up" --argjson seed "$seed" --argjson reads "$reads" --argjson scans "$scans" \
    --argjson mem "$mem" '{start_seconds: $up, seed_seconds: $seed, reads_seconds: $reads} + $scans + $mem' \
    > "$dir/times.json"

  say "$side: stop the stack"
  "${dc[@]}" down -v >/dev/null 2>&1
  case "$work" in /tmp/javv-ab.*) rm -r -- "$work" ;; esac
  rm -f "$dir/.work"
}

side old "$OLD_REGISTRY"
side new "$NEW_REGISTRY"
$PY report "$OUT"
