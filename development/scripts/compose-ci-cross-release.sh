#!/usr/bin/env bash
#
# Upgrade, roll back and upgrade again across two releases, on one store (issue 261, item 3). The
# Compose stack job runs it last, after `docker compose down -v`:
#   1. the last release (its compose file and its published images) on a new store, and data
#      written with it: the admin's sign-in, two clusters' scans and inventory runs
#      (seed-smoke.sh), and a saved SLA policy;
#   2. the build of this change on that store;
#   3. the last release again: a rollback;
#   4. the build of this change again.
# After each start: the expected images run, `GET /api/v1/meta` gives that code's
# mapping_version, and the findings of the golden cluster and the SLA policy read back the same.
#
#   development/scripts/compose-ci-cross-release.sh <last release tag, e.g. v0.8.1>
#
# Env: JAVV_BOOTSTRAP_ADMIN_PASSWORD, the bootstrap admin's password in deploy/compose/.env.
# Requires docker compose, jq, yq and the release tag in the checkout.
set -euo pipefail

tag=$1
: "${JAVV_BOOTSTRAP_ADMIN_PASSWORD:?set JAVV_BOOTSTRAP_ADMIN_PASSWORD}"
current=deploy/compose/compose.yaml
# next to compose.yaml, so it reads the same .env and keeps the project name (the store's volume)
previous=deploy/compose/compose.previous.yaml
override=$(mktemp --suffix=.yaml)
jar=$(mktemp)
trap 'rm -f "$previous" "$override" "$jar"' EXIT
git show "$tag:$current" > "$previous"

base=http://localhost:8080
admin_pw=ci-only-admin-rotated-261
golden=$(jq -r .cluster_id backend/tests/fixtures/envelope-trivy-golden.json)
sla='{"critical_days":5,"high_days":20,"medium_days":60,"low_days":120,"kev_days":3}'
mapping_version() { sed -n 's/^MAPPING_VERSION = //p'; }
change_mapping=$(mapping_version < backend/src/backend/core/bootstrap.py)
previous_mapping=$(git show "$tag:backend/src/backend/core/bootstrap.py" | mapping_version)

# This change's images carry the names in compose.yaml, and between two releases those are the
# last release's names too. Both get a name of their own before the pull replaces the tag.
for app in backend frontend; do
  docker tag "$(yq -r ".services.$app.image" "$current")" "javv-ci/$app:change"
  published=$(yq -r ".services.$app.image" "$previous")
  docker pull -q "$published"
  docker tag "$published" "javv-ci/$app:previous"
done

# $1 change | previous: start that release's apps, from its compose file, on the store as it is
start() {
  local file=$current
  [ "$1" = previous ] && file=$previous
  printf 'services:\n  backend:\n    image: javv-ci/backend:%s\n  frontend:\n    image: javv-ci/frontend:%s\n' \
    "$1" "$1" > "$override"
  echo "== $1 ($([ "$1" = previous ] && echo "$tag" || echo "this change"))"
  docker compose -f "$file" -f "$override" up -d --pull missing --wait --wait-timeout 300
  for app in backend frontend; do
    [ "$(docker inspect -f '{{.Image}}' "javv-$app-1")" = \
      "$(docker image inspect -f '{{.Id}}' "javv-ci/$app:$1")" ] || {
      echo "FAIL: javv-$app-1 does not run javv-ci/$app:$1"; exit 1; }
  done
}

# $1 the mapping_version that must run; reads the data back, and sets $findings the first time
findings=
check() {
  curl -sf -c "$jar" -o /dev/null -H 'content-type: application/json' \
    -d "{\"username\":\"admin\",\"password\":\"$admin_pw\"}" "$base/auth/login"
  curl -sf -b "$jar" "$base/api/v1/meta" | jq -e --argjson v "$1" '.mapping_version == $v' >/dev/null ||
    { echo "FAIL: mapping_version is not $1"; exit 1; }
  local count
  count=$(curl -sf -b "$jar" -G "$base/api/v1/findings" --data-urlencode "cluster_id=$golden" \
    --data-urlencode size=500 | jq '.data | length')
  [ "$count" -gt 0 ] && [ "${findings:=$count}" = "$count" ] ||
    { echo "FAIL: $count findings of $golden, $findings before"; exit 1; }
  curl -sf -b "$jar" "$base/api/v1/settings/sla" | jq -e --argjson want "$sla" \
    '.sla | with_entries(select(.key | IN($want | keys[]))) == $want' >/dev/null ||
    { echo "FAIL: the SLA policy did not read back"; exit 1; }
  echo "mapping_version $1, $count findings of $golden, the SLA policy: read back"
}

start previous
BACKEND=$base ADMIN_PW_INIT="$JAVV_BOOTSTRAP_ADMIN_PASSWORD" ADMIN_PW=$admin_pw \
  development/scripts/seed-smoke.sh
curl -sf -c "$jar" -o /dev/null -H 'content-type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$admin_pw\"}" "$base/auth/login"
curl -sf -b "$jar" -o /dev/null -X PUT -H 'content-type: application/json' -d "$sla" \
  "$base/api/v1/settings/sla"
check "$previous_mapping"

start change
check "$change_mapping"
start previous
check "$previous_mapping"
start change
check "$change_mapping"
echo "upgrade, rollback and a second upgrade from $tag: the data read back at each step"
