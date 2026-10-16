"""The javv-scanner chart (issue 725, slice 3), rendered with `helm template`: no cluster. `helm`
must be on PATH (it is on the CI runner), and these tests fail without it rather than skip.

What they hold (the scanners' own settings are held to the code by
`scanner/tests/test_helm_config.py`):
- one CronJob per enabled scanner, one cycle at a time (`Forbid`, D40), bounded and not retried;
- the RBAC the scanner's two API calls need, and nothing more: no Secret access (ruled on #725);
- the security context and the three writable mounts (issue 632);
- each scanner's own cache volume, refreshed by the run's init container on the same image from
  the source in `vulnDb`, and the scan itself with updates off;
- each scanner's own token Secret, by reference, and no token value outside it;
- a registry login only when one is named: Kubernetes mounts it into the scan container, and the
  refresh and the RBAC stay as they are (issue 739);
- the image tags against versions.yaml, a digest winning over the tag;
- every rule the chart enforces at install fails with its message.

`ct install` in CI installs it in a second cluster pushing to the javv chart, and runs its
`helm test`."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "javv-scanner"
VERSIONS = ROOT / "versions.yaml"
MANIFEST = ROOT / ".release-please-manifest.json"
RELEASE_PLEASE = ROOT / "release-please-config.json"

SCANNERS = ("trivy", "grype")
TRIVY_TOKEN = "trivy-token-725-render"
GRYPE_TOKEN = "grype-token-725-render"
VALUES = (
    "backendUrl=http://javv.javv.svc:8080",
    f"trivy.token.value={TRIVY_TOKEN}",
    f"grype.token.value={GRYPE_TOKEN}",
)
EXISTING = (
    "backendUrl=http://javv.javv.svc:8080",
    "trivy.token.existingSecret=trivy-secret",
    "grype.token.existingSecret=grype-secret",
)
DIGEST = "sha256:" + "a" * 64
LOGINS = tuple(f"{s}.registryAuth.existingSecret=regcred" for s in ("trivy", "grype"))


def _helm(*sets: str) -> subprocess.CompletedProcess[str]:
    args = ["helm", "template", "s", str(CHART), "--namespace", "scan"]
    for value in sets:
        args += ["--set", value]
    return subprocess.run(args, capture_output=True, text=True)


def _render(*sets: str) -> list[dict[str, Any]]:
    out = _helm(*sets)
    assert out.returncode == 0, out.stderr
    return [doc for doc in yaml.safe_load_all(out.stdout) if doc]


def _of(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [d for d in docs if d["kind"] == kind]


def _cronjob(docs: list[dict[str, Any]], scanner: str) -> dict[str, Any]:
    return next(
        d for d in _of(docs, "CronJob") if d["metadata"]["name"] == f"s-javv-scanner-{scanner}"
    )


def _pod(docs: list[dict[str, Any]], scanner: str) -> dict[str, Any]:
    return _cronjob(docs, scanner)["spec"]["jobTemplate"]["spec"]["template"]["spec"]


def _env(container: dict[str, Any]) -> dict[str, Any]:
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in container.get("env") or []}


def test_one_cycle_at_a_time_bounded_and_not_retried() -> None:
    docs = _render(*VALUES)
    assert sorted(c["metadata"]["name"] for c in _of(docs, "CronJob")) == [
        "s-javv-scanner-grype",
        "s-javv-scanner-trivy",
    ]
    for scanner in SCANNERS:
        spec = _cronjob(docs, scanner)["spec"]
        assert spec["concurrencyPolicy"] == "Forbid"
        assert spec["jobTemplate"]["spec"]["backoffLimit"] == 0
        assert spec["jobTemplate"]["spec"]["activeDeadlineSeconds"] == 19800
    assert _cronjob(docs, "trivy")["spec"]["schedule"] == "0 */6 * * *"
    assert _cronjob(docs, "grype")["spec"]["schedule"] == "30 */6 * * *"


def test_a_cycle_started_by_hand_waits_for_the_running_one() -> None:
    # Forbid counts only the CronJob's own Jobs: a hand-made one carries the same labels, so
    # "is one running" can find both, and NOTES pause the CronJob before starting one
    docs = _render(*VALUES)
    for scanner in SCANNERS:
        labels = _cronjob(docs, scanner)["spec"]["jobTemplate"]["metadata"]["labels"]
        assert labels == {
            "app.kubernetes.io/name": "javv-scanner",
            "app.kubernetes.io/instance": "s",
            "app.kubernetes.io/component": scanner,
        }
    # NOTES read as the template's text: helm template does not print them, and helm install
    # --dry-run asks a cluster for its version even with =client
    notes = (CHART / "templates" / "NOTES.txt").read_text()
    steps = [
        """patch cronjob {{ $cj }} -p '{"spec":{"suspend":true}}'""",
        "get jobs -l app.kubernetes.io/instance={{ $.Release.Name }},"
        "app.kubernetes.io/component={{ $name }}",
        "create job {{ $name }}-now --from=cronjob/{{ $cj }}",
        """patch cronjob {{ $cj }} -p '{"spec":{"suspend":false}}'""",
        "If a step fails, still run the last patch",
    ]
    where = [notes.index(step) for step in steps]
    assert where == sorted(where)
    assert '{{- $cj := printf "%s-%s" (include "javv-scanner.fullname" $) $name }}' in notes


@pytest.mark.parametrize("off", SCANNERS)
def test_a_disabled_scanner_renders_nothing(off: str) -> None:
    on = next(s for s in SCANNERS if s != off)
    docs = _render("backendUrl=http://j:8080", f"{on}.token.value=t", f"{off}.enabled=false")
    names = [d["metadata"]["name"] for d in docs]
    assert not [n for n in names if off in n]
    assert f"s-javv-scanner-{on}" in names


@pytest.mark.parametrize("sets", [VALUES, (*VALUES, *LOGINS)], ids=["no-login", "login"])
def test_rbac_is_the_two_calls_and_no_secret(sets: tuple[str, ...]) -> None:
    docs = _render(*sets)
    assert not _of(docs, "Role") and not _of(docs, "RoleBinding")
    (role,) = _of(docs, "ClusterRole")
    assert role["rules"] == [
        {"apiGroups": [""], "resources": ["pods"], "verbs": ["list"]},
        {
            "apiGroups": [""],
            "resources": ["namespaces"],
            "resourceNames": ["kube-system"],
            "verbs": ["get"],
        },
    ]
    (binding,) = _of(docs, "ClusterRoleBinding")
    assert binding["roleRef"]["name"] == role["metadata"]["name"] == "scan-s-javv-scanner"
    (account,) = _of(docs, "ServiceAccount")
    assert account["automountServiceAccountToken"] is False
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": account["metadata"]["name"], "namespace": "scan"}
    ]
    for scanner in SCANNERS:
        pod = _pod(docs, scanner)
        assert pod["serviceAccountName"] == account["metadata"]["name"]
        assert pod["automountServiceAccountToken"] is True


@pytest.mark.parametrize("scanner", SCANNERS)
def test_the_images_user_a_read_only_root_and_three_writable_mounts(scanner: str) -> None:
    pod = _pod(_render(*VALUES), scanner)
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == pod["securityContext"]["runAsGroup"] == 65532
    assert pod["securityContext"]["fsGroup"] == 65532
    for container in (*pod["initContainers"], *pod["containers"]):
        context = container["securityContext"]
        assert context["readOnlyRootFilesystem"] is True
        assert context["allowPrivilegeEscalation"] is False
        assert context["capabilities"] == {"drop": ["ALL"]}
    (scan,) = pod["containers"]
    assert {m["mountPath"]: m["name"] for m in scan["volumeMounts"]} == {
        "/var/cache/javv": "vulndb",
        "/var/lib/javv": "dead-letter",
        "/tmp": "tmp",
    }
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert volumes["dead-letter"]["emptyDir"] == {} and volumes["tmp"]["emptyDir"] == {}
    claim = volumes["vulndb"]["persistentVolumeClaim"]["claimName"]
    assert claim == f"s-javv-scanner-{scanner}-vulndb"


def test_each_scanner_has_its_own_cache_volume() -> None:
    docs = _render(*VALUES)
    claims = {c["metadata"]["name"]: c["spec"] for c in _of(docs, "PersistentVolumeClaim")}
    assert set(claims) == {f"s-javv-scanner-{s}-vulndb" for s in SCANNERS}
    for spec in claims.values():
        assert spec["accessModes"] == ["ReadWriteOnce"]
        assert spec["resources"]["requests"]["storage"] == "10Gi"
    own = _render(*VALUES, "grype.vulnDb.existingClaim=mine", "trivy.vulnDb.storageClass=fast")
    claims = {c["metadata"]["name"]: c["spec"] for c in _of(own, "PersistentVolumeClaim")}
    assert set(claims) == {"s-javv-scanner-trivy-vulndb"}
    assert claims["s-javv-scanner-trivy-vulndb"]["storageClassName"] == "fast"
    grype = {v["name"]: v for v in _pod(own, "grype")["volumes"]}
    assert grype["vulndb"]["persistentVolumeClaim"]["claimName"] == "mine"


@pytest.mark.parametrize(
    ("scanner", "off"),
    [
        (
            "trivy",
            {
                "TRIVY_SKIP_DB_UPDATE": "true",
                "TRIVY_SKIP_JAVA_DB_UPDATE": "true",
                "TRIVY_SKIP_CHECK_UPDATE": "true",
            },
        ),
        ("grype", {"GRYPE_DB_AUTO_UPDATE": "false"}),
    ],
)
def test_the_run_refreshes_first_and_the_scan_never_updates(
    scanner: str, off: dict[str, str]
) -> None:
    pod = _pod(_render(*VALUES), scanner)
    (refresh,) = pod["initContainers"]
    (scan,) = pod["containers"]
    assert refresh["name"] == "refresh-vulndb"
    assert refresh["image"] == scan["image"]  # the same binary, so the DB schema it reads (D41)
    assert refresh["command"][:2] == ["sh", "-c"]
    assert refresh["command"][2] == (CHART / "files" / "refresh-vulndb.sh").read_text()
    assert {"name": "vulndb", "mountPath": "/var/cache/javv"} in refresh["volumeMounts"]
    env = _env(scan)
    assert {k: env.get(k) for k in off} == off
    assert not set(off) & set(_env(refresh))


def _refresh_job(docs: list[dict[str, Any]], scanner: str) -> dict[str, Any]:
    (job,) = [
        d
        for d in _of(docs, "Job")
        if d["metadata"]["name"].startswith(f"s-javv-scanner-{scanner}-vulndb-")
    ]
    return job


@pytest.mark.parametrize("scanner", SCANNERS)
def test_the_install_refreshes_each_cache_once_and_so_binds_it(scanner: str) -> None:
    docs = _render(*VALUES)
    job = _refresh_job(docs, scanner)
    pod = job["spec"]["template"]["spec"]
    assert job["spec"]["backoffLimit"] == 0
    assert pod["automountServiceAccountToken"] is False
    # the run's own refresh, container for container: one definition, two places
    assert pod["containers"] == _pod(docs, scanner)["initContainers"]
    claims = [
        v["persistentVolumeClaim"]["claimName"]
        for v in pod["volumes"]
        if "persistentVolumeClaim" in v
    ]
    assert claims == [f"s-javv-scanner-{scanner}-vulndb"]


def test_a_new_refresh_job_only_when_what_it_runs_changes() -> None:
    def names(*sets: str) -> dict[str, str]:
        docs = _render(*VALUES, *sets)
        return {s: _refresh_job(docs, s)["metadata"]["name"] for s in SCANNERS}

    base = names()
    assert names("trivy.schedule=0 1 * * *", "clusterId=abc") == base
    assert names(*LOGINS) == base  # the login is the scan's alone
    moved = names("grype.vulnDb.updateUrl=https://mirror.example/databases")
    assert moved["trivy"] == base["trivy"] and moved["grype"] != base["grype"]
    assert names(f"trivy.image.digest={DIGEST}")["trivy"] != base["trivy"]


@pytest.mark.parametrize(
    ("sets", "scanner", "want"),
    [
        (
            ("trivy.vulnDb.repository=reg.example/trivy-db:2",),
            "trivy",
            {"TRIVY_DB_REPOSITORY": "reg.example/trivy-db:2"},
        ),
        (
            ("trivy.vulnDb.javaRepository=reg.example/trivy-java-db:1",),
            "trivy",
            {"TRIVY_JAVA_DB_REPOSITORY": "reg.example/trivy-java-db:1"},
        ),
        (
            ("grype.vulnDb.updateUrl=https://mirror.example/databases",),
            "grype",
            {"GRYPE_DB_UPDATE_URL": "https://mirror.example/databases"},
        ),
        ((), "trivy", {}),
        ((), "grype", {}),
    ],
    ids=["trivy-db", "trivy-java-db", "grype-url", "trivy-default", "grype-default"],
)
def test_the_refresh_pulls_from_the_source_in_vulndb(
    sets: tuple[str, ...], scanner: str, want: dict[str, str]
) -> None:
    (refresh,) = _pod(_render(*VALUES, *sets), scanner)["initContainers"]
    assert _env(refresh) == want


@pytest.mark.parametrize("scanner", SCANNERS)
def test_each_scanner_has_its_own_token_by_reference(scanner: str) -> None:
    for sets, secret in (
        (VALUES, f"s-javv-scanner-{scanner}-token"),
        (EXISTING, f"{scanner}-secret"),
    ):
        env = _env(_pod(_render(*sets), scanner)["containers"][0])
        assert env["JAVV_TOKEN"] == {"secretKeyRef": {"name": secret, "key": "token"}}
        assert env["JAVV_BACKEND_URL"] == "http://javv.javv.svc:8080"
        assert "JAVV_CLUSTER_ID" not in env
    docs = _render(*VALUES)
    secrets = {s["metadata"]["name"]: s["stringData"] for s in _of(docs, "Secret")}
    assert secrets == {
        "s-javv-scanner-trivy-token": {"token": TRIVY_TOKEN},
        "s-javv-scanner-grype-token": {"token": GRYPE_TOKEN},
    }
    assert not _of(_render(*EXISTING), "Secret")
    env = _env(_pod(_render(*VALUES, "clusterId=abc"), scanner)["containers"][0])
    assert env["JAVV_CLUSTER_ID"] == "abc"


@pytest.mark.parametrize("scanner", SCANNERS)
def test_a_registry_login_is_mounted_for_the_scan_only(scanner: str) -> None:
    other = next(s for s in SCANNERS if s != scanner)
    base = _render(*VALUES)
    docs = _render(*VALUES, f"{scanner}.registryAuth.existingSecret=regcred")
    pod = _pod(docs, scanner)
    (scan,) = pod["containers"]
    volumes = {v["name"]: v for v in pod["volumes"]}
    # the Secret type's key is .dockerconfigjson; both binaries read DOCKER_CONFIG/config.json
    assert volumes["registry-auth"] == {
        "name": "registry-auth",
        "secret": {
            "secretName": "regcred",
            "items": [{"key": ".dockerconfigjson", "path": "config.json"}],
        },
    }
    mount = next(m for m in scan["volumeMounts"] if m["name"] == "registry-auth")
    assert mount == {"name": "registry-auth", "mountPath": "/etc/javv/registry", "readOnly": True}
    assert _env(scan)["DOCKER_CONFIG"] == mount["mountPath"]
    # the refresh pulls only the vulnerability database, and is the same as with no login
    assert pod["initContainers"] == _pod(base, scanner)["initContainers"]
    assert _pod(docs, other) == _pod(base, other)
    for unset in (_pod(base, scanner), _pod(base, other)):
        assert "registry-auth" not in {v["name"] for v in unset["volumes"]}
        for container in (*unset["initContainers"], *unset["containers"]):
            assert "DOCKER_CONFIG" not in _env(container)


def test_no_token_outside_its_secret() -> None:
    for doc in _render(*VALUES):
        if doc["kind"] == "Secret":
            continue
        text = yaml.safe_dump(doc)
        assert TRIVY_TOKEN not in text and GRYPE_TOKEN not in text, doc["metadata"]["name"]


def test_the_image_tags_are_versions_yaml_and_a_digest_wins() -> None:
    pins = yaml.safe_load(VERSIONS.read_text())["scanners"]
    docs = _render(*VALUES)
    for scanner in SCANNERS:
        image = _pod(docs, scanner)["containers"][0]["image"]
        assert image == f"ghcr.io/danube-labs/javv-scanner-{scanner}:{pins[scanner]['current']}"
        assert _pod(docs, scanner)["containers"][0]["imagePullPolicy"] == "Always"
    pinned = _pod(_render(*VALUES, f"grype.image.digest={DIGEST}"), "grype")
    assert pinned["containers"][0]["image"] == f"ghcr.io/danube-labs/javv-scanner-grype@{DIGEST}"
    assert pinned["initContainers"][0]["image"] == pinned["containers"][0]["image"]


def test_the_chart_carries_this_release() -> None:
    version = json.loads(MANIFEST.read_text())["."]
    chart_yaml = (CHART / "Chart.yaml").read_text()
    chart = yaml.safe_load(chart_yaml)
    assert chart["version"] == version and chart["appVersion"] == version
    assert f"version: {version}  # x-release-please-version" in chart_yaml
    assert f'appVersion: "{version}"  # x-release-please-version' in chart_yaml
    extra = json.loads(RELEASE_PLEASE.read_text())["packages"]["."]["extra-files"]
    assert {"type": "generic", "path": "deploy/helm/javv-scanner/Chart.yaml"} in extra


def test_helm_test_checks_each_token_against_javv() -> None:
    out = subprocess.run(
        ["helm", "template", "s", str(CHART), "--namespace", "scan"]
        + [arg for v in VALUES for arg in ("--set", v)]
        + ["--show-only", "templates/tests/token.yaml"],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0, out.stderr
    pods = [d for d in yaml.safe_load_all(out.stdout) if d]
    assert [p["metadata"]["name"] for p in pods] == [
        "s-javv-scanner-test-trivy",
        "s-javv-scanner-test-grype",
    ]
    for pod, scanner in zip(pods, SCANNERS, strict=True):
        assert pod["metadata"]["annotations"]["helm.sh/hook"] == "test"
        assert pod["spec"]["automountServiceAccountToken"] is False
        (container,) = pod["spec"]["containers"]
        token = _env(container)["JAVV_TOKEN"]["secretKeyRef"]
        assert token == {"name": f"s-javv-scanner-{scanner}-token", "key": "token"}
        assert "/api/v1/scan-scope" in container["command"][2]


@pytest.mark.parametrize(
    ("sets", "message"),
    [
        (
            (f"trivy.token.value={TRIVY_TOKEN}", f"grype.token.value={GRYPE_TOKEN}"),
            "backendUrl: set",
        ),
        (("backendUrl=http://j:8080", "grype.token.value=t"), "trivy.token: set existingSecret"),
        (
            (*VALUES, "trivy.token.existingSecret=x"),
            "trivy.token: set existingSecret or value, not both",
        ),
        (
            ("backendUrl=http://j:8080", "trivy.enabled=false", "grype.enabled=false"),
            "enable at least one scanner",
        ),
        ((*VALUES, "backendUrl=javv:8080"), "/backendUrl"),
        ((*VALUES, "grype.image.digest=latest"), "/grype/image/digest"),
        ((*VALUES, "trivy.vulnDb.updateUrl=x"), "/trivy/vulnDb"),
        ((*VALUES, "grype.registryAuth.key=x"), "/grype/registryAuth"),
    ],
    ids=[
        "no-url",
        "no-token",
        "two-sources",
        "none-enabled",
        "url",
        "digest",
        "wrong-db-key",
        "wrong-login-key",
    ],
)
def test_the_install_fails_with_its_reason(sets: tuple[str, ...], message: str) -> None:
    out = _helm(*sets)
    assert out.returncode != 0
    assert message in out.stderr


# A stand-in trivy for the refresh script: NET=1 lets downloads through; a DB marked `cut` is one
# whose metadata calls it current, so a download leaves it alone until it is dropped.
_FAKE_TRIVY = """#!/bin/sh
db="$TRIVY_CACHE_DIR/db" java="$TRIVY_CACHE_DIR/java-db"
case "$1 $2" in
  "image --download-db-only")
    [ "$NET" = 1 ] || exit 1
    [ -e "$db/cut" ] && exit 0
    mkdir -p "$db" && : >"$db/good" ;;
  "image --download-java-db-only")
    [ "$NET" = 1 ] || exit 1
    [ -e "$java/cut" ] && exit 0
    mkdir -p "$java" && : >"$java/good" ;;
  rootfs*)
    [ -e "$db/good" ] && [ ! -e "$db/cut" ] || exit 2
    case "$*" in
      *"--pkg-types os"*) ;;
      *) if [ -e "$java/good" ] && [ ! -e "$java/cut" ]; then echo CVE-2021-44228; fi ;;
    esac ;;
  *) exit 9 ;;
esac
"""
_REFETCH = ["vuln db unreadable, fetching it again", "vuln db up to date"]
_NO_SCAN = [
    "vuln db unreadable, fetching it again",
    "vuln db refresh failed and no readable one is cached, this cycle does not scan",
]


# The stand-in behaves as Trivy 0.74 did on a cut DB: "current" by its metadata, so a refresh
# skips it; a cut trivy.db fails the scan, a cut Java DB exits 0 and only the finding is missing.
@pytest.mark.parametrize(
    ("cached", "net", "code", "events"),
    [
        (None, "0", 1, _NO_SCAN),
        (None, "1", 0, ["vuln db up to date"]),
        ("good", "0", 0, ["vuln db refresh failed, scanning with the cached db"]),
        ("db", "1", 0, _REFETCH),
        ("db", "0", 1, _NO_SCAN),
        ("java-db", "1", 0, _REFETCH),
        ("java-db", "0", 1, _NO_SCAN),
    ],
    ids=[
        "empty-offline",
        "empty-online",
        "cached-offline",
        "cut-db-online",
        "cut-db-offline",
        "cut-java-db-online",
        "cut-java-db-offline",
    ],
)
def test_the_refresh_goes_on_only_with_a_db_it_can_read(
    tmp_path: Path, cached: str | None, net: str, code: int, events: list[str]
) -> None:
    bin_dir, cache = tmp_path / "bin", tmp_path / "cache"
    bin_dir.mkdir()
    (bin_dir / "trivy").write_text(_FAKE_TRIVY)
    (bin_dir / "trivy").chmod(0o755)
    if cached:
        for name in ("db", "java-db"):
            (cache / name).mkdir(parents=True)
            (cache / name / "good").touch()
        if cached != "good":
            (cache / cached / "cut").touch()
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "JAVV_SCANNER": "trivy",
        "TRIVY_CACHE_DIR": str(cache),
        "NET": net,
    }
    out = subprocess.run(
        ["sh", str(CHART / "files" / "refresh-vulndb.sh")], env=env, capture_output=True, text=True
    )
    assert out.returncode == code, out.stdout + out.stderr
    lines = [json.loads(line) for line in out.stdout.splitlines()]
    assert [line["event"] for line in lines] == events
    assert {line["scanner"] for line in lines} == {"trivy"}
