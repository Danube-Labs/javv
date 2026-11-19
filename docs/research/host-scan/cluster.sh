#!/usr/bin/env bash
# Phase 0 of issue 1239: a scratch k3d cluster whose one node carries the package database and the
# release files of this machine, read-only and at their real paths. A k3d node image has no package
# database of its own, so the collector then reads the files of a real Ubuntu host as a node's.
# The default kubeconfig does not change: the cluster's kubeconfig goes to $KUBECONFIG_OUT.
set -euo pipefail
NAME=${NAME:-hostscan}
IMAGE=${K3S_IMAGE:-rancher/k3s:v1.35.5-k3s1}
KUBECONFIG_OUT=${KUBECONFIG_OUT:?set KUBECONFIG_OUT to a file for the cluster kubeconfig}
mounts=()
for f in /var/lib/dpkg/status /etc/os-release /usr/lib/os-release /etc/lsb-release; do
  [ -e "$f" ] && mounts+=(--volume "$(readlink -f "$f"):$f:ro@server:0")
done
k3d cluster create "$NAME" --image "$IMAGE" --servers 1 --agents 0 --no-lb \
  --kubeconfig-update-default=false --kubeconfig-switch-context=false \
  --k3s-arg "--disable=traefik@server:0" --k3s-arg "--disable=servicelb@server:0" \
  "${mounts[@]}"
k3d kubeconfig get "$NAME" > "$KUBECONFIG_OUT"
chmod 600 "$KUBECONFIG_OUT"
kubectl --kubeconfig "$KUBECONFIG_OUT" wait --for=condition=Ready node --all --timeout=120s
