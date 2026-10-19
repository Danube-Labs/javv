#!/usr/bin/env bash
#
# Publishes the operator docs of one release to the docs site (issue 925). Each release gets its own
# folder on the gh-pages branch (`/0.8.4/`), so a patch release no longer writes over the docs of
# the one before it. Run it in a checkout of the release's tag, with every release tag fetched.
#
# The aliases come from the tags, so the order of the runs does not matter:
#   - the newest release of a minor also gets the minor (`/0.8/`, a redirect, for old links);
#   - the newest release of all also gets `latest`, which the site opens on.
# Before issue 925 each minor was a folder of its own. The run that gives a minor its alias first
# removes that folder, in the same push, so the site has no gap.
#
#   development/scripts/publish-docs-version.sh 0.8.4            # build, commit to gh-pages, push
#   development/scripts/publish-docs-version.sh 0.8.4 --dry-run  # print the plan, change nothing
#
set -euo pipefail

usage() { printf 'usage: %s VERSION [--dry-run]\n' "$0" >&2; }

[ $# -ge 1 ] && [ $# -le 2 ] || { usage; exit 2; }
VERSION=$1
DRY=0
case "${2:-}" in
  "") ;;
  --dry-run) DRY=1 ;;
  *) usage; exit 2 ;;
esac
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { usage; exit 2; }

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  printf 'publish-docs-version: run it inside the git repository\n' >&2
  exit 2
}
cd "$ROOT"
git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null || {
  printf 'publish-docs-version: no tag v%s\n' "$VERSION" >&2
  exit 2
}

minor=${VERSION%.*}
# release tags only, newest first by version (0.8.10 sorts above 0.8.9)
releases() { git tag -l "$1" --sort=-v:refname | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true; }
newest_of_minor=$(releases "v$minor.*" | head -1)
newest=$(releases 'v*' | head -1)

aliases=()
[ "v$VERSION" = "$newest_of_minor" ] && aliases+=("$minor")
[ "v$VERSION" = "$newest" ] && aliases+=(latest)

# the site as it is now; absent before the first publish
if git remote get-url origin >/dev/null 2>&1; then
  git fetch -q origin +gh-pages:gh-pages 2>/dev/null || true
fi
old_minor_folder=0
if [ "${#aliases[@]}" -gt 0 ] && [ "${aliases[0]}" = "$minor" ] &&
  git show gh-pages:versions.json 2>/dev/null | jq -e --arg v "$minor" 'any(.[]; .version == $v)' >/dev/null; then
  old_minor_folder=1
fi

printf 'release: %s (tag v%s)\n' "$VERSION" "$VERSION"
[ "$old_minor_folder" -eq 1 ] && printf 'remove old folder: %s\n' "$minor"
printf 'aliases: %s\n' "${aliases[*]:-none}"
if [[ " ${aliases[*]:-} " == *" latest "* ]]; then printf 'default: latest\n'; fi

if [ "$DRY" -eq 1 ]; then
  printf 'Dry run. Nothing changed.\n'
  exit 0
fi

mike() { uv run --project docs-site --frozen mike "$1" --config-file docs-site/mkdocs.yml "${@:2}"; }

# each mike command commits to the local gh-pages branch; the one push at the end publishes them
[ "$old_minor_folder" -eq 1 ] && mike delete "$minor"
mike deploy --update-aliases --alias-type=redirect --title "$VERSION" "$VERSION" "${aliases[@]}"
if [[ " ${aliases[*]:-} " == *" latest "* ]]; then mike set-default latest; fi
git push -q origin gh-pages
printf 'Published %s.\n' "$VERSION"
