#!/usr/bin/env bash
#
# setup-branch-protection.sh — apply branch protection to main (AUDIT.md C2).
#
# Reproducible alternative to clicking through GitHub Settings → Branches, so the
# "main is protected; PR + green CI + review to merge" rule from git-workflow.md is
# actually enforced (not honor-system). Idempotent: re-run any time to re-assert.
#
# PREREQUISITES
#   * gh must be authenticated:  gh auth login   (or export GH_TOKEN=...)
#     The token's account needs admin on the repo.
#   * The CI workflow (.github/workflows/ci.yml) should be on the default branch so
#     its check names exist. REQUIRED_CHECKS below MUST match the job `name:` fields
#     in that workflow exactly ("Backend", "Frontend").
#
set -euo pipefail

# --- tunables ---------------------------------------------------------------
REPO="Danube-Labs/javv"
BRANCH="main"
REVIEWS=0                       # required approving reviews. 0 while solo/2-dev (CI + PR only;
                                # you can't approve your own PR) — raise to 1 with a second reviewer.
ENFORCE_ADMINS=false            # true = even admins must go through PRs (no break-glass).
# Must match the job `name:` fields in ci.yml exactly. All seven always run (detect-step
# pattern), so all seven can be required. "Frontend smoke" joined on issue 552 (2026-09-27): it
# had passed on every PR without blocking a merge.
REQUIRED_CHECKS=(
  "Backend" "Backend static" "Frontend" "Frontend smoke" "Scanner" "javv-common (shared lib)"
  "Commitlint"
)
# ----------------------------------------------------------------------------

if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh is not authenticated. Run 'gh auth login' (or set GH_TOKEN) first." >&2
  exit 1
fi

# Build the contexts JSON array from REQUIRED_CHECKS.
contexts_json=$(printf '%s\n' "${REQUIRED_CHECKS[@]}" | jq -R . | jq -s .)

echo "Applying branch protection to ${REPO}@${BRANCH} ..."
jq -n \
  --argjson contexts "$contexts_json" \
  --argjson reviews "$REVIEWS" \
  --argjson enforce_admins "$ENFORCE_ADMINS" \
  '{
    required_status_checks: { strict: true, contexts: $contexts },
    enforce_admins: $enforce_admins,
    required_pull_request_reviews: {
      dismiss_stale_reviews: true,
      required_approving_review_count: $reviews
    },
    restrictions: null,
    required_linear_history: false,
    allow_force_pushes: false,
    allow_deletions: false,
    required_conversation_resolution: true
  }' \
| gh api --method PUT "repos/${REPO}/branches/${BRANCH}/protection" --input -

echo
echo "Done. Current protection summary:"
gh api "repos/${REPO}/branches/${BRANCH}/protection" \
  --jq '{
    required_checks: .required_status_checks.contexts,
    strict_up_to_date: .required_status_checks.strict,
    reviews_required: .required_pull_request_reviews.required_approving_review_count,
    dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
    enforce_admins: .enforce_admins.enabled,
    force_pushes: .allow_force_pushes.enabled,
    deletions: .allow_deletions.enabled
  }'
