#!/usr/bin/env bash
#
# Packages and pushes the three charts for a release (issue 725, slice 4).
#
#   development/scripts/publish-charts.sh package <version> <out dir>
#     Checks every chart's version is <version>, then packages javv-opensearch, javv and javv-scanner
#     into <out dir>. The packaged javv-scanner names each scanner image by the digest its tag
#     points at now (slice 3 ruling 3: the repository's chart keeps the moving tag), and only
#     after cosign verifies that digest was signed by scanner-images.yml on main or a scanner-v*
#     tag. An image that does not verify stops the release.
#
#   development/scripts/publish-charts.sh push <out dir> <oci registry> [helm push args...]
#     Pushes each package, then prints "<registry host and path>/<chart>@<digest>" per chart,
#     the form cosign signs.
#
# Requires helm, yq, jq, docker (buildx imagetools, for the digests) and cosign.
set -euo pipefail
cd "$(dirname "$0")/../.."

CHARTS=(javv-opensearch javv javv-scanner)
SCANNERS=(trivy grype)
SCANNER_IDENTITY='^https://github\.com/Danube-Labs/javv(-poc)?/\.github/workflows/scanner-images\.yml@refs/(heads/main|tags/scanner-v.+)$'
ISSUER=https://token.actions.githubusercontent.com

package() {
  local version=$1 out=$2 chart scanner repo tag digest
  mkdir -p "$out"
  # appVersion is what each chart runs (OpenSearch's version for javv-opensearch); the render
  # tests hold it
  for chart in "${CHARTS[@]}"; do
    [ "$(yq -r .version "deploy/helm/$chart/Chart.yaml")" = "$version" ] || {
      echo "FAIL: deploy/helm/$chart/Chart.yaml version is not $version" >&2
      exit 1
    }
  done

  work=$(mktemp -d)
  trap 'rm -r -f "$work"' EXIT
  cp -R deploy/helm/javv-scanner "$work/javv-scanner"
  for scanner in "${SCANNERS[@]}"; do
    repo=$(yq -r ".$scanner.image.repository" "$work/javv-scanner/values.yaml")
    tag=$(yq -r ".$scanner.image.tag" "$work/javv-scanner/values.yaml")
    # the digest first, then the check on that digest: a tag can move between two lookups
    digest=$(docker buildx imagetools inspect "$repo:$tag" --format '{{json .Manifest}}' | jq -r .digest)
    case "$digest" in
      sha256:*) ;;
      *) echo "FAIL: no digest for $repo:$tag" >&2; exit 1 ;;
    esac
    cosign verify "$repo@$digest" --certificate-identity-regexp "$SCANNER_IDENTITY" \
      --certificate-oidc-issuer "$ISSUER" >/dev/null || {
      echo "FAIL: $repo@$digest ($tag) is not signed by scanner-images.yml" >&2
      exit 1
    }
    D=$digest yq -i ".$scanner.image.digest = strenv(D)" "$work/javv-scanner/values.yaml"
    echo "pinned $repo:$tag to $digest" >&2
  done

  helm package deploy/helm/javv-opensearch -d "$out" >/dev/null
  helm package deploy/helm/javv -d "$out" >/dev/null
  helm package "$work/javv-scanner" -d "$out" >/dev/null
  for chart in "${CHARTS[@]}"; do
    [ -s "$out/$chart-$version.tgz" ] || { echo "FAIL: no $out/$chart-$version.tgz" >&2; exit 1; }
  done
}

push() {
  local out=$1 registry=$2 tgz chart pushed digest
  shift 2
  for tgz in "$out"/*.tgz; do
    pushed=$(helm push "$tgz" "$registry" "$@" 2>&1) || { echo "$pushed" >&2; exit 1; }
    digest=$(sed -n 's/^Digest: //p' <<<"$pushed")
    chart=$(helm show chart "$tgz" | yq -r .name)
    case "$digest" in
      sha256:*) echo "${registry#oci://}/$chart@$digest" ;;
      *) echo "FAIL: helm push printed no digest for $tgz:" >&2; echo "$pushed" >&2; exit 1 ;;
    esac
  done
}

case "${1:-}" in
  package) package "$2" "$3" ;;
  push) shift; push "$@" ;;
  *) echo "usage: $0 package <version> <out dir> | push <out dir> <oci registry> [helm push args...]" >&2; exit 2 ;;
esac
