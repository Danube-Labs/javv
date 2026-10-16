#!/usr/bin/env bash
#
# Local clutter sweep (issue 660): test and build output, end-to-end logs, scanner dead-letter
# files and tool caches. Everything it deletes is rebuilt by the next build, test run or tool run.
#
# Default is a DRY RUN (prints what it would delete). Pass --apply to actually delete.
# A path is deleted only when git ignores it AND it is in one of the categories below, so nothing
# git tracks and no file you have not added yet is ever touched. Never touches `tmp/` (screenshots,
# the trailer and demo work; operator rulings 2026-10-03 and 2026-10-16), the other ignored files
# a developer keeps (.claude/, .codex/, .serena/, .impeccable/, AGENTS.md, cookies), or
# node_modules/ and .venv/.
#
#   development/scripts/clean-local.sh            # list
#   development/scripts/clean-local.sh --apply    # delete
#
set -euo pipefail

usage() { printf 'usage: %s [--apply]\n' "$0" >&2; }

APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  *) usage; exit 2 ;;
esac
[ $# -le 1 ] || { usage; exit 2; }

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'clean-local: run it inside the git repository\n' >&2
  exit 2
}
cd "$ROOT"

# one category each; git lists an ignored folder once, with a trailing slash
in_category() {
  case "$1" in
    frontend/coverage/ | frontend/dist/ | frontend/test-results/ | docs-site/site/ | docs-site/.cache/) return 0 ;;
    .coverage | */.coverage) return 0 ;;
    development/e2e/logs/) return 0 ;;
    *.dead-letter.jsonl) return 0 ;;
    __pycache__/ | */__pycache__/ | .pytest_cache/ | */.pytest_cache/ | .ruff_cache/ | */.ruff_cache/) return 0 ;;
    frontend/.eslintcache) return 0 ;;
  esac
  return 1
}

# git already folds these into one ignored folder; the check keeps that true if a rule changes
never() {
  case "$1" in
    tmp/* | .claude/* | .codex/* | .serena/* | .impeccable/*) return 0 ;;
    node_modules/* | */node_modules/* | .venv/* | */.venv/*) return 0 ;;
  esac
  return 1
}

# --others never lists a tracked file, and git folds a folder into one ignored entry only when
# it holds no tracked file: so no path below is one git knows
paths=()
while IFS= read -r -d '' p; do
  in_category "$p" || continue
  never "$p" && continue
  paths+=("$p")
done < <(git ls-files --others --ignored --exclude-standard --directory -z)

if [ ${#paths[@]} -eq 0 ]; then
  printf 'Nothing to delete.\n'
  exit 0
fi

total=$(du -sck "${paths[@]}" | tail -1 | cut -f1)
human=$(numfmt --to=iec --from-unit=1024 "$total")

if [ "$APPLY" -eq 0 ]; then
  printf 'Dry run. These paths would be deleted:\n'
  for p in "${paths[@]}"; do
    printf '  %s\t%s\n' "$(du -sh -- "$p" | cut -f1)" "$p"
  done
  printf '%d paths, %s. Nothing deleted. Run with --apply to delete them.\n' "${#paths[@]}" "$human"
  exit 0
fi

for p in "${paths[@]}"; do
  find "$p" -delete
  printf 'deleted\t%s\n' "$p"
done
printf 'Deleted %d paths, %s.\n' "${#paths[@]}" "$human"
