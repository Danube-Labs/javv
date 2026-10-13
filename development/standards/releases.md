# Releases & dependency automation

How JAVV versions, releases, and keeps dependencies current. Conventional-commit
discipline (see [git-workflow.md](git-workflow.md)) is the input that drives all of this.

> **Status: implemented** (2026-06-27). release-please and Renovate are set up:
> `.github/workflows/release-please.yml`, `release-please-config.json`,
> `.release-please-manifest.json`, `renovate.json`. Remaining gap below.

## Versioning
- **SemVer** (`MAJOR.MINOR.PATCH`), derived from conventional-commit types, never bumped by hand.
- **Pre-1.0:** while in MVP we stay in `0.x`. `release-please-config.json` sets
  `bump-minor-pre-major` and `bump-patch-for-minor-pre-major`, so a `feat` bumps the patch version
  and a breaking change the minor one; a minor bump beyond that is set with a `Release-As:` footer
  (0.5.0 and 0.6.0 were). The first tag, `v0.1.0`, was pinned with a one-time `release-as` that has
  since been removed. The **MVP release** closes the deploy bolt (M10) as **0.7.0** (operator,
  2026-10-09); the 0.6 line was the first deployable releases. **`1.0.0`** comes after a hardening
  phase, once JAVV installs plug-and-play and is as close to bug-free as we can make it.
- JAVV is a **deployed app** (FastAPI + Vue, shipped via Helm/k3s), **not a published library**.
  A "release" here is a tag + changelog + GitHub Release that a deploy can pin to, plus the
  backend and frontend images published under that version (issue 452), each signed with cosign
  keyless and carrying a signed SPDX SBOM attestation (issue 615). The `Publish app images` job in
  `release-please.yml` does that in the same run, and verifies the signatures signed out. The
  `Publish charts` job then publishes the three Helm charts at `oci://ghcr.io/danube-labs/charts`
  under the same version, each signed (issue 725), with the scanner images pinned by digest in
  `javv-scanner`. It runs only after the images are published. If either job fails, the release notes
  say so at the top. The `Publish docs` job runs last: it publishes the release's operator docs
  as its `major.minor` version and as `latest`, which the docs site opens on (issue 639). It adds
  no note when it fails; the site keeps opening the version before until the job is re-run. When the cause is outside the workflow (a registry or Sigstore outage), re-run
  the failed jobs once it clears, then delete the note. A re-run builds only the images not yet
  published: one the first run pushed is pulled, smoked and signed as it is, so its tag keeps the
  digest it had (issue 833). The note says which case it is: not published, or published but not
  yet signed. A re-run uses the workflow as it was at the
  release commit, so a cause in the workflow itself can only be fixed by a fix on `main` and the
  next release. 0.6.0's smoke step lacked a variable compose requires, so 0.6.0 published nothing
  and its fix went into the release after it.
- **Version notes for operators.** A change that does any of the following adds a row to
  [`docs/UPGRADING.md` § Version notes](../../docs/UPGRADING.md#version-notes) in the same PR,
  with `Unreleased` in the release column:
  - bumps `MAPPING_VERSION`;
  - changes the envelope versions the backend accepts;
  - needs the scanner images republished.

  Whoever merges the release PR renames `Unreleased` to the version. The changelog lists every
  change; this table lists only what an upgrade needs from the operator. The rollout mechanics
  are in [`docs/engineering/UPGRADES.md`](../../docs/engineering/UPGRADES.md).

## Release automation — `release-please` (not `semantic-release`)
We use **[release-please](https://github.com/googleapis/release-please)**, run as a GitHub Action.

**How it works:** instead of cutting a release on every merge, release-please maintains a
standing **"release PR"** that accumulates changelog entries and the next version bump. You
merge that PR when you decide to release — that merge creates the tag, GitHub Release, and
updated `CHANGELOG.md`.

**Cutting a release:**
1. **The version.** A `Release-As: <version>` footer in a commit's own message sets it; a
   one-commit squash keeps the commit message and drops the PR body.
2. **The chart READMEs.** The `chart-readmes` job regenerates them on the release PR (issue 752):
   release-please moves each `Chart.yaml` and the `javv` chart's tags, not the READMEs helm-docs
   writes from them.
3. **CI.** The release PR is pushed with `GITHUB_TOKEN`, so no CI runs on it (see Remaining gap).
   Close and reopen it to start CI.
4. **When to merge.** Only when no `scanner-images` run is in progress on `main`. That workflow
   republishes the scanner tags on a merge that touches `versions.yaml` or the scanner build, and
   signs them minutes later. The release refuses an unsigned scanner image.
5. **Merging.** Every release PR so far was merged with a merge commit. Then follow both publish
   jobs through their pull-and-verify steps.

**Why release-please over semantic-release:**
| | release-please | semantic-release |
|---|---|---|
| Release trigger | Merge a batched **release PR** (you choose when) | Auto-release on **every** qualifying merge to main |
| Best fit | Apps & services (and OSS) | Published npm/PyPI **libraries** |
| OSS contributor friction | Low — bad commit types just don't show in the changelog | High — a bad commit can misfire a publish |
| Languages | Multi-language, first-class Python + Node | Node tool |

For an open-source **app** like JAVV, batched + reviewable releases beat auto-publish-on-merge.
If JAVV later extracts a genuinely **published package**, semantic-release on *that package* is
reasonable — the two aren't mutually exclusive.

## Dependency automation — `Renovate` (not Dependabot)
We use **[Renovate](https://docs.renovatebot.com/)** (config: `renovate.json`) to open PRs that
bump dependencies. It's **orthogonal** to release automation — it feeds the dep-update PRs that
release-please later turns into releases.

**The policy it follows** (cadence, no automerge, fix deadlines for vulnerable dependencies) is
[dependency-policy.md](dependency-policy.md).

**Why Renovate over Dependabot:** Renovate covers JAVV's whole polyglot stack in one tool —
**uv/pip, npm, Docker base images, Helm charts, and GitHub Actions** — with grouping and
scheduling. Dependabot is simpler and GitHub-native but weaker on Helm/Docker and grouping.

## Remaining gap
- Release PRs are opened with `GITHUB_TOKEN`, which does **not** trigger the CI workflow, so the
  release PR is closed and reopened to run it (Cutting a release, step 3). A GitHub App token for
  release-please would remove that step.
