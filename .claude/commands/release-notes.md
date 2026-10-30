---
description: Write the What's new section of the open release PR, from the work the release holds, in STE
argument-hint: [release PR number]
---

# Release notes

Release PR: **$ARGUMENTS** (none given: the open PR from `release-please--branches--main`).

release-please makes the release page from the body of the release PR. Its list of PR titles
stays. This command writes a "What's new" section above that list. The section tells a user what
is new for them and what to do before an upgrade. The method comes from issue 1061.

## When to run it

Run it after the last merge before the release, just before the release merge. release-please
writes the body again each time a PR merges to `main`, and the section is then lost. The release
merge stays on the operator's word.

## 1. Make a list of all the work

1. Find the previous tag (`git describe --tags --abbrev=0 origin/main`) and run
   `git log --reverse --format='%h %s' <tag>..origin/main`.
2. Read the body of each PR (`gh pr view N`) and of the issue that it closes or names.
   A PR title is not proof of a claim.

## 2. Group the work by what a user gets

- Write one line for each user benefit, not one line for each PR. Several PRs can make one change.
- Compare each line with the previous release (its release page and the code at its tag), so that
  the section does not call old behavior new.
- Changes for contributors only (tests, lint rules, CI, dependency updates of the tools) go in a
  short part of their own, or out.

## 3. Check each claim where a user sees it

Open the screen, call the route or read the chart value. Read the code at the release head when
a screen is not at hand. Narrow a claim that you cannot show. Do not write a claim from the PR text alone.

## 4. Before you upgrade

Write this part from the changes of the release:
- a `MAPPING_VERSION` change (`git diff <tag>..origin/main -- backend/src`).
- a new permission that roles need, or a new setting in `docs/CONFIGURATION.md`.
- the rows of `docs/UPGRADING.md` § Version notes.
- a change to an API rule, and what going back to the previous release does to data that the new
  release wrote.

If there is nothing, the part says so.

## 5. Write the section

Use this shape, between the two markers, right under the `## [x.y.z]` heading of the body:

```markdown
<!-- whats-new -->
### What's new

- **One line for each user benefit.** Then what it does for the user.

### Before you upgrade

- What the operator does before the upgrade, or that nothing is needed.

### For contributors

- Changes that only contributors see.

The list below shows each change of this release.
<!-- /whats-new -->
```

The text is in STE, with no internal codes (milestones, decisions, issue numbers in prose), and
it names no person, tool or model. Lint it before you post it:

```bash
python3 development/scripts/check-release-notes.py <body file>
```

The command must exit 0. The `Release notes` workflow runs the same check when someone opens,
edits or reopens the release PR.

## 6. Post it and ask for approval

1. Read the body (`gh pr view N --json body`), add the section, and write the new body to a new
   file. Check that the diff only adds lines.
2. Post it with `gh pr edit N --body-file <file>`, then read the body back.
3. Give the operator the link and the section. The operator approves the text and says when to
   merge.
