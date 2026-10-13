#!/usr/bin/env bash
#
# The release's app images (issue 833, B4): build only what is not published yet, push only what
# was built, and print the digest of each, so a re-run after a failed signature signs the images
# already published instead of moving their tags to a new build. A build is not reproducible: two
# runs give two digests, and the first would stay public and unsigned.
#
#   development/scripts/release-app-images.sh prepare <state dir>
#       per app: published -> pulled (the release smoke runs on it); "not found" -> built.
#       Any other registry answer stops the run: an outage or a private package must never read
#       as "not published" and be pushed over.
#   development/scripts/release-app-images.sh push <state dir>
#       pushes what prepare built, then prints app=<repo>@<digest> for both, from the registry.
#
# Env: REGISTRY (default ghcr.io/danube-labs); the version is .release-please-manifest.json's.
# Requires: docker (buildx), jq, git.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
mode=${1:-}
state=${2:-}
[ -n "$mode" ] && [ -n "$state" ] || {
  echo "usage: release-app-images.sh prepare|push <state dir>" >&2
  exit 2
}
registry=${REGISTRY:-ghcr.io/danube-labs}
version=$(jq -r '."."' .release-please-manifest.json)
mkdir -p "$state"

digest_of() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest}}' | jq -r .digest
}

case $mode in
  prepare)
    build=()
    for app in backend frontend; do
      ref="$registry/javv-$app:$version"
      if out=$(docker buildx imagetools inspect "$ref" 2>&1); then
        echo "$ref is already published: pulled, not built" >&2
        docker pull -q "$ref" >&2
        echo published > "$state/$app"
      elif [[ $out == *": not found"* ]]; then
        build+=("$app")
        echo built > "$state/$app"
      else
        echo "release-app-images: cannot tell whether $ref is published: $out" >&2
        exit 1
      fi
    done
    if [ ${#build[@]} -gt 0 ]; then
      development/scripts/build-app-images.sh "${build[@]}" >&2
    fi
    ;;
  push)
    for app in backend frontend; do
      ref="$registry/javv-$app:$version"
      case $(cat "$state/$app") in
        built) docker push -q "$ref" >&2 ;;
        published) echo "$ref was already published: not pushed again" >&2 ;;
        *) echo "release-app-images: no prepare state for $app" >&2; exit 1 ;;
      esac
      digest=$(digest_of "$ref")
      [[ $digest == sha256:* ]] || {
        echo "release-app-images: no digest for $ref" >&2
        exit 1
      }
      echo "$app=$registry/javv-$app@$digest"
    done
    ;;
  *)
    echo "release-app-images: no mode '$mode'" >&2
    exit 2
    ;;
esac
