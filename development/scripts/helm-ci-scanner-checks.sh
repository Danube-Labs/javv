#!/usr/bin/env bash
#
# The javv-scanner chart against a running javv chart, across two clusters (issue 725, slice 3):
# the javv chart's cluster serves JAVV, a second cluster plays the monitored one.
#
#   registry <kind cluster> <monitored context> <scanner namespace>
#     A registry that requires a login, on the kind network, and an image in it that only that login
#     pulls (issue 739). Each node of the cluster pulls from it over http. The login is in the
#     Secret javv-ci-registry in the seeded namespace, for the kubelet, and in the scanner namespace,
#     for the scanners (the name ci/default-values.yaml uses). A deployment of the image runs in the
#     seeded namespace. Run it before prepare.
#
#   prepare <javv context> <javv namespace> <javv release> <monitored context> <scanner namespace>
#     Exposes the javv frontend Service as a NodePort, signs in (rotating the bootstrap password),
#     limits the monitored cluster's scan scope to one seeded namespace, mints a token per scanner
#     for that cluster and puts each in its own Secret: javv-ci-trivy-token, javv-ci-grype-token
#     (the names ci/default-values.yaml uses). Prints JAVV's address as the scanners reach it,
#     last, on its own line.
#
#   cycle <monitored context> <scanner namespace> <scanner release> <JAVV address>
#     Starts one cycle of each scanner from its CronJob, waits for both, and checks JAVV holds a
#     committed run from that cluster for each, by the version versions.yaml pins, and a scan by
#     each of the image that only the registry login pulls.
#
# Env: JAVV_CI_ADMIN_PASSWORD, the bootstrap admin's password in that JAVV install, and
# JAVV_CI_ADMIN_USERNAME when that admin is not called admin. Requires
# kubectl, helm, curl, jq and yq; registry also needs docker, kind, openssl and htpasswd. Nothing
# secret is printed.
set -euo pipefail
cd "$(dirname "$0")/../.."

: "${JAVV_CI_ADMIN_PASSWORD:?set JAVV_CI_ADMIN_PASSWORD}"
ADMIN=${JAVV_CI_ADMIN_USERNAME:-admin}
SEED_NS=javv-scan-seed
# a deliberately old image, so the scans find something
SEED_IMAGE=nginx:1.23.4
ROTATED="$JAVV_CI_ADMIN_PASSWORD-rotated"
# the registry by its container name on the kind network, which the nodes and the pods resolve
REGISTRY=javv-ci-registry:5000
# the scanner compatibility gate's fixture (issue 631): public, with known findings
PRIVATE_SOURCE=ghcr.io/danube-labs/javv-compat-fixture:python-3.9.16-slim
PRIVATE_IMAGE=$REGISTRY/private/python:3.9.16-slim

# The session cookie is Secure, which curl's own cookie jar never sends over http, so it travels
# as a header read from a file; a body with a password is a file too. Neither is ever in a
# process's arguments (jq reads the password from its environment).
jar=$(mktemp) headers=$(mktemp) body=$(mktemp)
# A cycle that fails while its CronJob is paused resumes it on the way out. The trap runs after
# cycle's locals are gone, so the whole command is kept here.
paused=()
on_exit() {
  rm -f "$jar" "$headers" "$body"
  if [ "${#paused[@]}" -gt 0 ]; then
    kubectl "${paused[@]}" -p '{"spec":{"suspend":false}}' >/dev/null || true
  fi
}
trap on_exit EXIT

json() {
  local status=0
  curl -sSf -H @"$jar" -D "$headers" -H 'content-type: application/json' "$@" || status=$?
  if grep -qi '^set-cookie:' "$headers"; then
    printf 'cookie: %s\n' "$(grep -i '^set-cookie:' "$headers" | sed -E 's/^[^:]*: *//; s/;.*//' |
      paste -sd ';')" >"$jar"
  fi
  return "$status"
}

sign_in() {  # url, then the password to try first and the one to try next
  local url=$1 password
  for password in "$2" "$3"; do
    P=$password jq -n --arg u "$ADMIN" '{username: $u, password: env.P}' >"$body"
    if json -o /dev/null -X POST "$url/auth/login" --data-binary @"$body" 2>/dev/null; then
      printf '%s' "$password"
      return 0
    fi
  done
  echo "FAIL: cannot sign in to $url as $ADMIN" >&2
  return 1
}

registry() {
  local cluster=$1 mon_ctx=$2 ns=$3 auth dir pw node target namespace
  # the registry reads the htpasswd file from this directory for as long as it runs
  auth=$(mktemp -d) dir=$(mktemp -d)
  pw=$(openssl rand -hex 24)
  htpasswd -Bbn ci "$pw" >"$auth/htpasswd" 2>/dev/null
  docker run -d --name "${REGISTRY%:*}" --network kind -p 127.0.0.1:5001:5000 \
    -v "$auth:/auth:ro" -e REGISTRY_AUTH=htpasswd -e REGISTRY_AUTH_HTPASSWD_REALM=ci \
    -e REGISTRY_AUTH_HTPASSWD_PATH=/auth/htpasswd registry:3.0.0 >/dev/null
  # containerd reads a registry's hosts.toml from certs.d at each pull: http, with no restart
  for node in $(kind get nodes --name "$cluster"); do
    docker exec "$node" sh -c "mkdir -p /etc/containerd/certs.d/$REGISTRY && printf \
      '[host.\"http://$REGISTRY\"]\n  capabilities = [\"pull\", \"resolve\"]\n' \
      >/etc/containerd/certs.d/$REGISTRY/hosts.toml"
  done

  # one Docker config with the login, for the push from this host and for both Secrets
  P=$pw jq -n --arg a "127.0.0.1:5001" --arg r "$REGISTRY" \
    '(("ci:" + env.P) | @base64) as $auth | {auths: {($a): {auth: $auth}, ($r): {auth: $auth}}}' \
    >"$dir/config.json"
  target=127.0.0.1:5001/${PRIVATE_IMAGE#*/}
  docker pull -q "$PRIVATE_SOURCE" >/dev/null
  docker tag "$PRIVATE_SOURCE" "$target"
  DOCKER_CONFIG=$dir docker push -q "$target" >/dev/null
  echo "pushed $PRIVATE_IMAGE, which pulls only with the login" >&2

  for namespace in "$SEED_NS" "$ns"; do
    kubectl --context "$mon_ctx" create namespace "$namespace" --dry-run=client -o yaml |
      kubectl --context "$mon_ctx" apply -f - >/dev/null
    kubectl --context "$mon_ctx" -n "$namespace" create secret generic javv-ci-registry \
      --type=kubernetes.io/dockerconfigjson --from-file=.dockerconfigjson="$dir/config.json" \
      --dry-run=client -o yaml | kubectl --context "$mon_ctx" apply -f - >/dev/null
  done
  rm -f "$dir/config.json" && rmdir "$dir"
  kubectl --context "$mon_ctx" -n "$SEED_NS" create deployment private --image="$PRIVATE_IMAGE" \
    --dry-run=client -o json -- sleep infinity |
    jq '.spec.template.spec.imagePullSecrets = [{name: "javv-ci-registry"}]' |
    kubectl --context "$mon_ctx" apply -f - >/dev/null
  kubectl --context "$mon_ctx" -n "$SEED_NS" rollout status deploy/private --timeout=5m >&2
}

prepare() {
  local javv_ctx=$1 javv_ns=$2 release=$3 mon_ctx=$4 ns=$5
  local svc node port url used cid scanner token

  # the frontend Service on every node's address, which the other cluster's pods can reach
  helm --kube-context "$javv_ctx" -n "$javv_ns" upgrade "$release" deploy/helm/javv \
    --reuse-values --set frontend.service.type=NodePort --wait --timeout 5m >/dev/null
  svc=$(kubectl --context "$javv_ctx" -n "$javv_ns" get svc \
    -l app.kubernetes.io/component=frontend -o jsonpath='{.items[0].metadata.name}')
  port=$(kubectl --context "$javv_ctx" -n "$javv_ns" get svc "$svc" \
    -o jsonpath='{.spec.ports[0].nodePort}')
  node=$(kubectl --context "$javv_ctx" get nodes \
    -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
  url="http://$node:$port"
  # a new NodePort, and a backend the javv checks just rolled back, can take a moment to route
  curl -sSf --retry 30 --retry-delay 2 --retry-all-errors "$url/readyz" >/dev/null
  echo "JAVV answers at $url" >&2

  used=$(sign_in "$url" "$JAVV_CI_ADMIN_PASSWORD" "$ROTATED")
  if [ "$used" != "$ROTATED" ]; then  # the bootstrap admin may do nothing else first
    C=$used N=$ROTATED jq -n '{current_password: env.C, new_password: env.N}' >"$body"
    json -o /dev/null -X POST "$url/auth/password" --data-binary @"$body"
  fi

  cid=$(kubectl --context "$mon_ctx" get namespace kube-system -o jsonpath='{.metadata.uid}')
  echo "the monitored cluster is $cid" >&2
  kubectl --context "$mon_ctx" create namespace "$SEED_NS" --dry-run=client -o yaml |
    kubectl --context "$mon_ctx" apply -f - >/dev/null
  kubectl --context "$mon_ctx" -n "$SEED_NS" create deployment seed --image="$SEED_IMAGE" \
    --dry-run=client -o yaml | kubectl --context "$mon_ctx" apply -f - >/dev/null
  kubectl --context "$mon_ctx" -n "$SEED_NS" rollout status deploy/seed --timeout=5m >&2
  json -o /dev/null -X PUT "$url/api/v1/scan-scope" \
    -d "$(jq -n --arg c "$cid" --arg s "$SEED_NS" '{cluster_id: $c, include_namespaces: [$s]}')"

  kubectl --context "$mon_ctx" create namespace "$ns" --dry-run=client -o yaml |
    kubectl --context "$mon_ctx" apply -f - >/dev/null
  for scanner in trivy grype; do
    token=$(json -X POST "$url/api/v1/admin/tokens" \
      -d "$(jq -n --arg c "$cid" --arg s "$scanner" '{cluster_id: $c, scanner: $s}')" | jq -r .token)
    [ -n "$token" ] && [ "$token" != null ] || { echo "FAIL: no $scanner token minted" >&2; exit 1; }
    # from stdin, so the token is in no process's arguments
    printf '%s' "$token" | kubectl --context "$mon_ctx" -n "$ns" create secret generic \
      "javv-ci-$scanner-token" --from-file=token=/dev/stdin --dry-run=client -o yaml |
      kubectl --context "$mon_ctx" apply -f - >/dev/null
    echo "minted the $scanner token into javv-ci-$scanner-token" >&2
  done
  echo "$url"
}

# Waits for a Job to finish and prints succeeded or failed, whichever it reaches first (a failed
# Job never meets condition=complete, which would hold the step for its whole timeout).
finished() {
  local job=$1 deadline=$((SECONDS + 1200)) state
  while [ "$SECONDS" -lt "$deadline" ]; do
    state=$(k get "$job" -o jsonpath='{.status.succeeded}/{.status.failed}')
    case "$state" in
      [1-9]*/*) echo succeeded; return ;;
      */[1-9]*) echo failed; return ;;
    esac
    sleep 5
  done
  echo "timed out"
}

# Waits until no Job of that scanner is running, or fails after 20 minutes.
until_none_running() {
  local selector=$1 scanner=$2 deadline=$((SECONDS + 1200)) active
  while [ "$SECONDS" -lt "$deadline" ]; do
    active=$(k get jobs -l "$selector" -o jsonpath='{range .items[*]}{.status.active}{end}')
    [ -z "$active" ] && return 0
    sleep 5
  done
  echo "FAIL: a $scanner job is still running after 20 minutes" >&2
  k get jobs -l "$selector" >&2 || true
  exit 1
}

cycle() {
  local mon_ctx=$1 ns=$2 release=$3 url=$4
  local k cid scanner cronjob want provenance version images
  k() { kubectl --context "$mon_ctx" -n "$ns" "$@"; }
  cid=$(kubectl --context "$mon_ctx" get namespace kube-system -o jsonpath='{.metadata.uid}')

  # One scanner at a time, and each cycle in the order the chart's NOTES give an operator: a Job
  # made by hand from a CronJob is outside Forbid, so the CronJob is paused, nothing of that
  # scanner may be running (its scheduled cycles, the install's refresh), and only then the Job
  # starts. A DB refresh also takes one to two GB of memory while it unpacks.
  for scanner in trivy grype; do
    local selector="app.kubernetes.io/instance=$release,app.kubernetes.io/component=$scanner"
    cronjob=$(k get cronjob -l "$selector" -o jsonpath='{.items[0].metadata.name}')
    k patch cronjob "$cronjob" -p '{"spec":{"suspend":true}}' >/dev/null
    paused=(--context "$mon_ctx" -n "$ns" patch cronjob "$cronjob")
    k delete job "ci-$scanner" --ignore-not-found >/dev/null
    until_none_running "$selector" "$scanner"
    k create job "ci-$scanner" --from="cronjob/$cronjob" >/dev/null
    if [ "$(finished "job/ci-$scanner")" != succeeded ]; then
      echo "FAIL: the $scanner cycle did not complete" >&2
      k logs "job/ci-$scanner" --all-containers --tail 60 >&2 || true
      exit 1
    fi
    k patch cronjob "$cronjob" -p '{"spec":{"suspend":false}}' >/dev/null
    paused=()
    k logs "job/ci-$scanner" -c refresh-vulndb --tail 5
  done

  sign_in "$url" "$ROTATED" "$JAVV_CI_ADMIN_PASSWORD" >/dev/null
  provenance=$(json "$url/api/v1/scanners/provenance?cluster_id=$cid")
  for scanner in trivy grype; do
    want=$(yq -r ".scanners.$scanner.current" versions.yaml)
    version=$(jq -r --arg s "$scanner" '.scanners[] | select(.scanner == $s) | .scanner_version' \
      <<<"$provenance")
    if [ "$version" != "$want" ]; then
      echo "FAIL: JAVV holds no $scanner run $want from $cid (got '${version}')" >&2
      jq -c '.scanners[] | {scanner, scanner_version, last_run}' <<<"$provenance" >&2 || true
      exit 1
    fi
    echo "ok: a committed $scanner $version run from $cid"
  done

  # the private image, which a scanner pulls only with its registry login (issue 739)
  images=$(json "$url/api/v1/images?cluster_id=$cid")
  if ! jq -e --arg ref "$PRIVATE_IMAGE" \
    'any(.images[]; .image_ref == $ref and (.severity_by_scanner | has("trivy") and has("grype")))' \
    <<<"$images" >/dev/null; then
    echo "FAIL: JAVV holds no scan of $PRIVATE_IMAGE by both scanners" >&2
    jq -c '.images[] | {image_ref, scanners: (.severity_by_scanner | keys)}' <<<"$images" >&2 || true
    exit 1
  fi
  echo "ok: both scanners scanned $PRIVATE_IMAGE with their registry login"
}

command=${1:-}
shift || true
case "$command" in
  registry) registry "$@" ;;
  prepare) prepare "$@" ;;
  cycle) cycle "$@" ;;
  *) echo "usage: $0 registry|prepare|cycle ..." >&2; exit 2 ;;
esac
