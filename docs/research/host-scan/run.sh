#!/usr/bin/env bash
# Phase 0 of issue 1239: the collector, then one scan Job for each scanner, on the cluster of
# cluster.sh. Prints the collector's meta line and each Job's measurement line.
#   KUBECONFIG_OUT=<file from cluster.sh> docs/research/host-scan/run.sh
set -euo pipefail
cd "$(dirname "$0")"
K=(kubectl --kubeconfig "${KUBECONFIG_OUT:?set KUBECONFIG_OUT}")
TRIVY_IMAGE=${TRIVY_IMAGE:-local1/javv-scanner-trivy:0.76.2-hostscan}
GRYPE_IMAGE=${GRYPE_IMAGE:-local1/javv-scanner-grype:0.121.3-hostscan}

"${K[@]}" create namespace javv-hostscan --dry-run=client -o yaml | "${K[@]}" apply -f -
"${K[@]}" label namespace javv-hostscan --overwrite pod-security.kubernetes.io/enforce=privileged
"${K[@]}" -n javv-hostscan create configmap host-collector-script --from-file=collector.py \
  --dry-run=client -o yaml | "${K[@]}" apply -f -
"${K[@]}" -n javv-hostscan create configmap host-scan-script --from-file=scan.py \
  --dry-run=client -o yaml | "${K[@]}" apply -f -
"${K[@]}" apply -f collector.yaml
"${K[@]}" -n javv-hostscan rollout status daemonset/host-collector --timeout=120s
"${K[@]}" -n javv-hostscan logs daemonset/host-collector | grep '"collector ready"'

for s in trivy grype; do
  image=$TRIVY_IMAGE db="trivy image --download-db-only --cache-dir /var/cache/javv/trivy"
  [ "$s" = grype ] && image=$GRYPE_IMAGE db="grype db update"
  "${K[@]}" -n javv-hostscan delete job "host-scan-$s" --ignore-not-found
  sed -e "s|SCANNER|$s|g" -e "s|IMAGE|$image|g" -e "s|DBCOMMAND|$db|" scan-job.yaml | "${K[@]}" apply -f -
  "${K[@]}" -n javv-hostscan wait --for=condition=complete "job/host-scan-$s" --timeout=1200s
  "${K[@]}" -n javv-hostscan logs "job/host-scan-$s" -c scan
done
