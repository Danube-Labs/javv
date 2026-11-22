#!/usr/bin/env bash
#
# preflight.sh — verify the JAVV dev environment is READY before running the app or a bolt.
#
# Complements setup-dev.sh: that script *installs* the toolchain; this one checks the tools
# are present (and Node is new enough) AND that the runtime dependencies are actually up —
# the Docker daemon, a k3d cluster, and OpenSearch. Closes AUDIT N6 (the missing self-test).
#
# Exit codes: non-zero on a HARD failure (missing tool / Docker down). Soft warnings (no
# cluster / OpenSearch not up yet) exit 0 — they're expected before you start the cluster.
#
# Override the OpenSearch endpoint with OPENSEARCH_URL (default http://localhost:9200).
#
set -uo pipefail

OPENSEARCH_URL="${OPENSEARCH_URL:-http://localhost:9200}"
NODE_MAJOR_MIN=26

HARD=0; SOFT=0
ok()   { printf '  \033[1;32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m!\033[0m %s\n' "$*"; SOFT=1; }
fail() { printf '  \033[1;31m✗\033[0m %s\n' "$*"; HARD=1; }
hdr()  { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

# kubectl and helm reject `--version`; everything else (incl. k3d/grype) prints a clean one-liner with it.
tool_version() {
  case "$1" in
    kubectl) kubectl version --client 2>/dev/null | head -1 ;;
    helm)    helm version --short 2>/dev/null ;;
    *)       "$1" --version 2>/dev/null | head -1 ;;
  esac
}

hdr "Required tools"
for t in docker uv ruff node npm pyright kubectl helm k3d trivy grype gh jq; do
  if command -v "$t" >/dev/null 2>&1; then
    ok "$t ($(tool_version "$t"))"
  else
    fail "$t missing — run development/setup/setup-dev.sh"
  fi
done

hdr "Node version"
if command -v node >/dev/null 2>&1; then
  maj=$(node -v | sed 's/^v//; s/\..*//')
  if [ "$maj" -ge "$NODE_MAJOR_MIN" ]; then ok "node $(node -v) (>= v$NODE_MAJOR_MIN)"
  else fail "node $(node -v) is below required v$NODE_MAJOR_MIN"; fi
fi

hdr "Playwright browser (e2e + visual rigs)"
# Not installed by setup-dev.sh: the browser is a per-checkout npm artifact, not host toolchain,
# so it lands with the frontend deps. Soft — you only need it to run the e2e suites.
PW_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
if compgen -G "$PW_CACHE/chromium-*" >/dev/null 2>&1; then
  ok "chromium present ($PW_CACHE)"
else
  warn "no Playwright chromium — run: cd frontend && npx playwright install chromium --with-deps"
fi

hdr "Docker daemon"
if docker info >/dev/null 2>&1; then
  ok "docker daemon reachable"
else
  fail "docker daemon not reachable — start Docker (if it needs sudo, add yourself to the docker group)"
fi

hdr "k3d cluster"
if command -v k3d >/dev/null 2>&1; then
  n=$(k3d cluster list -o json 2>/dev/null | jq 'length' 2>/dev/null || echo 0)
  if [ "${n:-0}" -gt 0 ]; then
    ok "k3d cluster(s): $(k3d cluster list --no-headers 2>/dev/null | awk '{print $1}' | paste -sd, -)"
  else
    warn "no k3d cluster yet — create one before deploying (see development/README.md)"
  fi
fi

hdr "OpenSearch ($OPENSEARCH_URL)"
health=$(curl -fsS --max-time 4 "$OPENSEARCH_URL/_cluster/health" 2>/dev/null || true)
if [ -n "$health" ]; then
  status=$(echo "$health" | jq -r '.status' 2>/dev/null)
  case "$status" in
    green|yellow) ok "OpenSearch up (status: $status)" ;;
    red)          warn "OpenSearch reachable but cluster status is RED" ;;
    *)            warn "OpenSearch reachable but health looked off: $health" ;;
  esac
else
  warn "OpenSearch not reachable at $OPENSEARCH_URL — start the dev cluster / OpenSearch container"
fi

hdr "Dev MCPs (soft — per-user config, not repo-enforced)"
if command -v claude >/dev/null 2>&1; then
  mcps=$(claude mcp list 2>/dev/null || true)
  for m in serena opensearch context7; do
    if printf '%s\n' "$mcps" | grep -qE "^${m}:.*Connected"; then
      ok "MCP $m connected"
    else
      warn "MCP $m not connected — see docs/research/TOOLING-AND-MCP.md (loads next session)"
    fi
  done
else
  warn "claude CLI not found — skipping MCP check"
fi

echo
if [ "$HARD" -ne 0 ]; then
  printf '\033[1;31mPREFLIGHT FAILED\033[0m — fix the ✗ items above.\n'; exit 1
elif [ "$SOFT" -ne 0 ]; then
  printf '\033[1;33mPREFLIGHT OK (with warnings)\033[0m — the ! items are fine if the cluster is not started yet.\n'; exit 0
else
  printf '\033[1;32mPREFLIGHT OK\033[0m — environment ready.\n'; exit 0
fi
