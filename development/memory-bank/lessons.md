# Lessons

Each lesson came from an incident. The rule that it made is in `CLAUDE.md`, a rule file or a
standard. This file keeps the incident, because the incident tells why the rule exists and what it
looks like when it happens again. A number is a GitHub issue or PR.

## Git, PRs and releases

| Incident | Lesson |
|---|---|
| 2026-07-07 to 2026-07-08 (215, 225, 248, 269): a report said "merged" for a PR that closed with no merge. A merged stacked base closed its child. One PR merged into a feature branch. | No stacked PRs. Each PR bases on `main`. A merge is real only when `gh pr view N --json mergedAt` is not empty. |
| A `gh pr merge` on a branch behind `main` exits 0 and merges nothing | Check `mergedAt` after each merge. Pin the merge to the head commit that CI checked. |
| The `ruff format` pre-commit hook changes a staged file and stops the commit, with no clear error | After each commit, check `git log --oneline -1`. |
| `git add -A` added files that git ignores to a commit | Add files by path. A hook in `.claude/hooks/` now refuses `git add -A`. |
| 2026-07-17 (447): a `Release-As:` footer in the PR body had no effect, because the squash of a one-commit PR uses the commit message | Put `Release-As:` in the commit message itself. |
| 2026-10-20 (935, 944): `docs:` merges did not reach the open release PR, so it shipped docs with the old version | Before a release PR merges, search its branch for the old version. |
| 2026-08-03 (537): a sentence in a PR body that said "fixes" and an issue number closed that issue | GitHub reads closing words anywhere in a PR body. Write them only on purpose. |
| 2026-10-04 (715): one line that the secret scan flags, in any pushed commit, fails CI for each branch, for good | Run the secret scan before a push. If a pushed commit has a flagged line, start a new branch. |
| 2026-10-09 (792): the scanner images published, then the signature step failed, so the tags pointed at unsigned images for about 40 minutes | After a scanner image merge, check that the workflow signed each digest. Run the failed jobs again if not. |
| A Renovate bump of a scanner version fails CI, because CI scans with the published image of that version | List the new version in `also_supported` first, merge and publish it, then bump `current`. |

## Tests and gates

| Incident | Lesson |
|---|---|
| vitest printed "N passed" while CI failed on an unhandled rejection | Judge a gate by its exit code. Run the exact CI commands. |
| The single-page app answers 200 with HTML for each GET | Check a response by its body, not by its status. |
| 2026-07-10 (310): a new filter field passed the parity tests, but the past-time reader had no parity test and ignored the field | A new field on a shared shape needs a check of each consumer, not only the ones with a mirror test. |
| 2026-07-08 (274): tests seeded with severities in the canonical form passed, but real scanner data did not match | Seed tests with the raw scanner words. |
| 2026-08-03 (541): the RBAC presence check could not fail after a FastAPI version stored routes in a new way | Prove a guard: switch the code off and see the test fail. FastAPI stays below the next minor version. |
| 2026-10-13 (832): three test instruments gave a pass with the guard off: leaked mock calls, unseen keepalive requests, a wrong counter | A guard proof counts only when it shows the failure. If it does not fail, check the instrument first. |
| 2026-09-26 (533): a test run with the clock 90 days ahead used the shared dev store, and the staleness sweep marked 60,355 real findings stale | Tests with a shifted clock use a throwaway store. |
| 2026-11-14 (1190): the e2e spec `inspect.spec.ts` ran on the dev store and clicked Staleness sweep. The sweep marked 82,820 findings of 3 clusters stale. The operator left the store as it is. | An e2e spec that starts a job or writes data runs on a throwaway store. Before a spec runs on the dev store, read it for job, sweep and delete buttons. |
| Backend tests against the dev store leave users, clusters and indices behind | Set `JAVV_OPENSEARCH_URL` on each pytest command, and clean with `development/scripts/clean-dev-store.sh`. |
| 2026-10-17 (905): the production build wrote `200ms` as `.2s`, so code that read the CSS token got 0.2 and the animation ended at once | Parse both time units. Check motion on a production build, not only in jsdom. |
| 2026-10-19 (924): a rare 502 did not show with one request at a time (0 of 123). It showed with the requests that a page sends at once. | Reproduce a race with the real number of requests before you say that it does not happen. |
| 2026-11-09 (1176): a new GET list route needed more than its own code. It also needed an entry in `test_list_envelope_contract.py` and in the list-key tables of `api-design.md` and `API.md`. It needed an MCP tool or a reason for no tool (`test_mcp_read_coverage.py`). | Before a new list route, read those three places. |
| 2026-11-07 (1108): the docs-site anchor test refused a link to `#steps_1`, which two headings with the same name made. `helm-docs.sh --check` compares with the git index. | Link the parent section. Stage the chart files before the check. |
| 2026-11-14 and 2026-11-15 (1190): two moves of a scoped style to `base.css` had a hidden effect. The Risk accept image chip lost its mono font, because the deleted copy had won over another scoped class by source order. The card of `ImageFindingsPanel` takes the `.first-run` padding of `ImageDetailView`, because Vue gives the scope of a parent to the root of its child. | Before a scoped rule moves to `base.css`, measure the computed style of each element that wears it, before and after. A read of the source misses both effects. |

## Product behaviour

| Incident | Lesson |
|---|---|
| 2026-10-10 (749): a sweep found reads that throw on an empty reply, but missed 3 reads that set no error and showed old data | Look for silent failures, not only for errors. Check that each read shows its failure text. |
| 2026-10-11 (817): a fresh install could not make its first scanner token in the UI. The test rigs made tokens through the API and seeded clusters, so no test saw it. | Test the first-run path on an empty store, with only the docs. |
| 2026-10-05 (715, 733): turning on OpenSearch security also turned on demo users that could sign in | When authentication changes, list each principal that can sign in, and try the default credentials. |
| A new permission on a default role did not reach existing users, because each user keeps a copy of its capabilities | A change to a default role updates the roles and the users of each role. |
| 2026-10-23 (977): a failure reason moved from the store into a component reset on each mount, while the store still said "failed" | Seed a view value from the store that it explains, and test unmount and mount again. |
| 2026-07-16 (384): a view grew to 721 lines over design passes before anyone measured it | After a design pass, count the lines of each view that the PR changed. Near 500, move parts into panels. |
| 2026-11-06 (1110, 1113): Claude Code sends 5 requests when it connects. A low MCP rate limit refused it, and the 429 reply had no detail. | The docs give 30 requests a minute as the lowest useful limit, and the 429 reply tells the reason. |
| 2026-11-14 (1205): a text rewrite renamed the legend item "Fixed" to "Resolved". Only a person sets Resolved. A finding that a scan no longer reports gets `present=false`. | Before a rename of a state or a term, read its meaning in the backend. |

## Docs

| Incident | Lesson |
|---|---|
| 2026-10-09 (794): an operator page said that more than one backend works. That came from design text, and nobody tested it. | Operator pages say only what somebody ran. Mark design intent as untested. |
| 2026-10-09 (796): a chart README had an install example with a missing Secret, while `docs/DEPLOYING.md` had the right steps | When a command is in two docs, compare each copy. |
| 2026-09-27 (588), 2026-10-06 (754), 2026-10-14 (857): each docs pass found claims that did not match the code | Check each claim against the code before you write it. Absolute words ("each", "never") are the most likely to be wrong. |
| 2026-11-09 (1161): an agent test said that a pull moved the tag of an image with no digest. The image had no tag before the run. `LastTagTime` shows only the last new tag. | Check a stated cause against the record before you act on it. |
