"""The release run's publish jobs, read from `.github/workflows/release-please.yml`: the app
images (issue 615) and the charts (issue 725, slice 4).

A release signs only on a real run (keyless cosign needs the job's OIDC token), so no CI job can
exercise it. These tests hold its shape instead:
- only the two publishing jobs can get a signing identity;
- each pushed image digest gets an SBOM, a signature and an attestation, before anyone pulls it;
- the charts publish only after the images, and each pushed chart digest is signed;
- the release verifies, signed out, with the identity `docs/DEPLOYING.md` gives operators;
- a re-run builds only what is not published (issue 833, B4), and its note says which case it is.
The chart packaging itself is `test_helm_publish.py`.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release-please.yml"
DEPLOYING = ROOT / "docs" / "DEPLOYING.md"
SIGN_ACTION = "./.github/actions/sign-image"


def _workflow() -> dict[Any, Any]:
    return yaml.safe_load(WORKFLOW.read_text())


def _steps(job: str) -> list[dict[str, Any]]:
    return _workflow()["jobs"][job]["steps"]


def _step(job: str, name: str) -> dict[str, Any]:
    return next(s for s in _steps(job) if s.get("name") == name)


def test_only_the_publish_jobs_can_get_a_signing_identity() -> None:
    workflow = _workflow()
    assert "id-token" not in workflow["permissions"]
    signers = {
        name
        for name, job in workflow["jobs"].items()
        if (job.get("permissions") or {}).get("id-token") == "write"
    }
    assert signers == {"publish-app-images", "publish-charts"}


def test_each_pushed_digest_is_signed_and_attested_before_anyone_pulls_it() -> None:
    names = [s.get("name") or s.get("uses") for s in _steps("publish-app-images")]
    sign = next(s for s in _steps("publish-app-images") if s.get("uses") == SIGN_ACTION)
    order = [
        "Push both images",
        "An SBOM of each pushed digest",
        sign["name"],
        "Anyone can pull them",
        "Anyone can verify them",
    ]
    where = [names.index(name) for name in order]
    assert where == sorted(where)

    # the push step records digests, the SBOM step reads those, and the action signs its list
    push = _step("publish-app-images", "Push both images")
    # the script prints app=<repo>@<digest> (pinned in test_release_app_images.py)
    assert (
        'release-app-images.sh push "$RUNNER_TEMP/app-images" > "$RUNNER_TEMP/pushed.txt"'
        in (push["run"])
    )
    assert 'cat "$RUNNER_TEMP/pushed.txt" >> "$GITHUB_OUTPUT"' in push["run"]
    sbom = _step("publish-app-images", "An SBOM of each pushed digest")
    assert sbom["env"] == {
        "BACKEND": "${{ steps.push.outputs.backend }}",
        "FRONTEND": "${{ steps.push.outputs.frontend }}",
    }
    assert sign["with"]["images"] == "${{ steps.sbom.outputs.images }}"


def test_a_rerun_signs_the_published_images_instead_of_building_new_ones() -> None:
    """Issue 833, B4: the build step builds only what is not published, so a re-run after a failed
    signature signs the digests the first run pushed. It reads the registry signed in: a private
    package must read as published, not as missing and be pushed over."""
    steps = _steps("publish-app-images")
    names = [s.get("name") or s.get("uses") for s in steps]
    login = next(i for i, s in enumerate(steps) if "docker/login-action" in (s.get("uses") or ""))
    build = names.index("Build the images not yet published")
    assert login < build < names.index("Smoke the release's compose file")
    assert sum("docker/login-action" in (s.get("uses") or "") for s in steps) == 1
    assert steps[build]["run"] == (
        'development/scripts/release-app-images.sh prepare "$RUNNER_TEMP/app-images"'
    )
    assert not any("build-app-images.sh" in s.get("run", "") for s in steps)


def test_the_release_note_says_whether_the_images_were_published() -> None:
    note = _step(
        "publish-app-images", "Say on the release that its images were not published, or not signed"
    )
    assert note["if"] == "failure()"
    assert note["env"]["PUSHED"] == "${{ steps.push.outcome == 'success' }}"
    published, not_published = note["run"].split("else", 1)
    assert 'if [ "$PUSHED" = true ]' in published
    assert "were published but are not signed and verified yet" in published
    assert "the re-run signs the images already" in published
    assert "were not published and signed" in not_published
    assert "were not published" not in published


def test_the_charts_publish_after_the_images_and_each_pushed_digest_is_signed() -> None:
    job = _workflow()["jobs"]["publish-charts"]
    assert "publish-app-images" in job["needs"]
    steps = job["steps"]
    names = [s.get("name") or s.get("uses", "").split("@")[0] for s in steps]
    order = [
        "Package the charts",
        "docker/login-action",
        "Push the charts",
        "Sign each pushed chart (cosign keyless)",
        "Anyone can pull and verify them",
    ]
    where = [names.index(name) for name in order]
    assert where == sorted(where)

    assert (
        'publish-charts.sh package "$VERSION"'
        in _step("publish-charts", "Package the charts")["run"]
    )
    assert "publish-charts.sh push" in _step("publish-charts", "Push the charts")["run"]
    pushed = "${{ steps.push.outputs.charts }}"
    sign = _step("publish-charts", "Sign each pushed chart (cosign keyless)")
    assert sign["env"] == {"CHARTS": pushed}
    assert "*@sha256:*) ;;" in sign["run"] and 'cosign sign --yes "$ref"' in sign["run"]
    assert _step("publish-charts", "Anyone can pull and verify them")["env"]["CHARTS"] == pushed


def test_the_release_verifies_with_the_identity_the_docs_give() -> None:
    workflow = _workflow()
    # PyYAML reads the key `on` as True
    assert workflow[True] == {"push": {"branches": ["main"]}}
    verify = _step("publish-app-images", "Anyone can verify them")["env"]
    charts = _step("publish-charts", "Anyone can pull and verify them")["env"]
    assert (charts["IDENTITY"], charts["ISSUER"]) == (verify["IDENTITY"], verify["ISSUER"])
    assert verify["IDENTITY"] == (
        r"^https://github\.com/Danube-Labs/javv-poc/\.github/workflows/release-please\.yml"
        r"@refs/heads/main$"
    )
    assert verify["ISSUER"] == "https://token.actions.githubusercontent.com"

    docs = DEPLOYING.read_text()
    section = docs.split("## Verify the images and charts\n", 1)[1].split("\n## ", 1)[0]
    assert 'cosign verify "ghcr.io/danube-labs/charts/javv:$VERSION"' in section
    identity = re.search(r"^\s*IDENTITY='(.+)'$", section, re.M)
    issuer = re.search(r"^\s*ISSUER=(\S+)$", section, re.M)
    assert identity and issuer
    assert (identity[1], issuer[1]) == (verify["IDENTITY"], verify["ISSUER"])


def test_the_release_pr_carries_chart_readmes_at_its_version() -> None:
    # release-please moves each Chart.yaml and the javv chart's tags, never the READMEs helm-docs
    # writes from them, so its PR failed CI's README check until this job (issue 752)
    workflow = _workflow()
    outputs = workflow["jobs"]["release-please"]["outputs"]
    assert outputs["prs_created"] == "${{ steps.release.outputs.prs_created }}"
    assert outputs["pr"] == "${{ steps.release.outputs.pr }}"

    job = workflow["jobs"]["chart-readmes"]
    assert job["needs"] == "release-please"
    assert job["if"] == (
        "needs.release-please.outputs.prs_created == 'true'"
        " && needs.release-please.outputs.release_created != 'true'"
    )
    assert job["permissions"] == {"contents": "write"}

    steps = job["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout@"))
    branch = "${{ fromJSON(needs.release-please.outputs.pr).headBranchName }}"
    assert checkout["with"]["ref"] == branch
    run = "\n".join(s.get("run", "") for s in steps)
    assert "development/scripts/helm-docs.sh" in run
    # a push only when a README changed, and only to the release PR's own branch
    assert "git diff --quiet -- 'deploy/helm/*/README.md' && exit 0" in run
    assert 'git push origin "HEAD:$BRANCH"' in run
    assert next(s for s in steps if "git push" in s.get("run", ""))["env"]["BRANCH"] == branch
