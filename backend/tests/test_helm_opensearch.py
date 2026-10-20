"""The javv-opensearch chart (issue 725, slice 1), rendered with `helm template` against the
official chart vendored in its `charts/` folder: no network, no cluster. `helm` must be on PATH
(it is on the CI runner; versions.yaml leaves Kubernetes tooling at its latest), and these tests
fail without it rather than skip.

What they hold:
- one node with the compose file's OpenSearch settings, on the image versions.yaml pins, and the
  chart's version is the release's, on a line release-please moves;
- admin and javv are the only password users in every mode: an init container writes a users file
  holding the two, each hashed from its Secret read through the environment (issues 736, 729), and
  the javv role and its mapping are mounted from files/ in place of the image's;
- demo certificates by default; your own, from a Secret or from cert-manager, switch the demo setup
  off through opensearch.yml and are mounted so a renewal reaches the node;
- every rule the chart enforces at install fails with its message.

`ct install` in CI installs the same chart for real and runs its `helm test`."""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy" / "helm" / "javv-opensearch"
COMPOSE = ROOT / "deploy" / "compose" / "compose.yaml"
VERSIONS = ROOT / "versions.yaml"
MANIFEST = ROOT / ".release-please-manifest.json"
RELEASE_PLEASE = ROOT / "release-please-config.json"

PASSWORD = "opensearch.javv.auth.password=Pw-725-render!"
BACKEND = "opensearch.javv.backend.password=Pj-729-render"
DEMO = (PASSWORD, BACKEND)
OWN_SECRET = (
    "opensearch.javv.auth.existingSecret=store-admin",
    "opensearch.javv.backend.existingSecret=store-backend",
    "opensearch.javv.tls.existingSecret=store-certs",
)
CERT_MANAGER = (
    PASSWORD,
    BACKEND,
    "opensearch.javv.tls.certManager.enabled=true",
    "opensearch.javv.tls.certManager.issuerRef.name=store-ca",
)
IMAGE_HOME = "/usr/share/opensearch"


def _helm(*sets: str) -> subprocess.CompletedProcess[str]:
    args = ["helm", "template", "t", str(CHART), "--namespace", "javv"]
    for value in sets:
        args += ["--set", value]
    return subprocess.run(args, capture_output=True, text=True)


def _render(*sets: str) -> list[dict[str, Any]]:
    out = _helm(*sets)
    assert out.returncode == 0, out.stderr
    return [doc for doc in yaml.safe_load_all(out.stdout) if doc]


def _kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [doc for doc in docs if doc["kind"] == kind]


def _pod(docs: list[dict[str, Any]]) -> dict[str, Any]:
    (statefulset,) = _kind(docs, "StatefulSet")
    return statefulset["spec"]["template"]["spec"]


def _store(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(c for c in _pod(docs)["containers"] if c["name"] == "opensearch")


def _users_init(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(c for c in _pod(docs)["initContainers"] if c["name"] == "javv-users")


def _opensearch_yml(docs: list[dict[str, Any]]) -> str:
    (config,) = [c for c in _kind(docs, "ConfigMap") if "opensearch.yml" in c["data"]]
    return config["data"]["opensearch.yml"]


def _test_pod_env(docs: list[dict[str, Any]]) -> dict[str, str]:
    (pod,) = _kind(docs, "Pod")
    return {e["name"]: e.get("value", "") for e in pod["spec"]["containers"][0]["env"]}


def _pinned_opensearch() -> str:
    return yaml.safe_load(VERSIONS.read_text())["datastore"]["opensearch"]


def test_one_node_with_the_compose_settings() -> None:
    docs = _render(*DEMO)
    (statefulset,) = _kind(docs, "StatefulSet")
    assert statefulset["spec"]["replicas"] == 1
    env = {e["name"]: e.get("value") for e in _store(docs)["env"]}
    assert env["discovery.type"] == "single-node"
    compose = yaml.safe_load(COMPOSE.read_text())["services"]["opensearch"]["environment"]
    for name in (
        "plugins.index_state_management.enabled",
        "plugins.index_state_management.history.enabled",
        "search.insights.top_queries.latency.enabled",
        "search.insights.top_queries.cpu.enabled",
        "search.insights.top_queries.memory.enabled",
        "path.repo",
        "plugins.security.audit.type",
    ):
        assert env[name] == str(compose[name]), name
    heap = compose["OPENSEARCH_JAVA_OPTS"]  # ${OPENSEARCH_JAVA_OPTS:-<default>}
    assert env["OPENSEARCH_JAVA_OPTS"] == heap.split(":-", 1)[1].rstrip("}")


def test_the_service_javv_signs_in_to_is_javv_opensearch() -> None:
    services = {s["metadata"]["name"]: s for s in _kind(_render(*DEMO), "Service")}
    ports = {p["name"]: p["port"] for p in services["javv-opensearch"]["spec"]["ports"]}
    assert ports["http"] == 9200


def test_every_container_is_the_pinned_opensearch_image_and_none_runs_as_root() -> None:
    # the default install, on a volume: the official chart's chown init container would run as
    # root on an unpinned busybox image; the pod's fsGroup does its job
    pod = _pod(_render(*DEMO))
    assert pod["securityContext"]["fsGroup"] == 1000
    image = f"opensearchproject/opensearch:{_pinned_opensearch()}"
    for container in (*pod.get("initContainers", []), *pod["containers"]):
        assert container["image"] == image, container["name"]
        assert (container.get("securityContext") or {}).get("runAsUser") != 0, container["name"]


def test_the_helm_test_pod_meets_the_restricted_pod_security_level() -> None:
    # the pod is this chart's own template: in a namespace that enforces restricted, Kubernetes
    # refuses a pod without these fields, and `helm test` fails
    (pod,) = _kind(_render(*DEMO), "Pod")
    spec = pod["spec"]
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    for container in spec["containers"]:
        context = container["securityContext"]
        assert context["allowPrivilegeEscalation"] is False, container["name"]
        assert context["capabilities"]["drop"] == ["ALL"], container["name"]


def test_the_image_is_the_opensearch_versions_yaml_pins() -> None:
    docs = _render(*DEMO)
    image = f"opensearchproject/opensearch:{_pinned_opensearch()}"
    assert _store(docs)["image"] == image
    assert _users_init(docs)["image"] == image
    chart = yaml.safe_load((CHART / "Chart.yaml").read_text())
    assert chart["appVersion"] == _pinned_opensearch()


def test_the_chart_carries_this_release() -> None:
    """Ruling 4 on issue 725: every chart carries the JAVV release. release-please rewrites only
    lines that carry its annotation, and only in files its config names."""
    version = json.loads(MANIFEST.read_text())["."]
    chart_yaml = (CHART / "Chart.yaml").read_text()
    assert yaml.safe_load(chart_yaml)["version"] == version
    assert f"version: {version}  # x-release-please-version" in chart_yaml
    extra = json.loads(RELEASE_PLEASE.read_text())["packages"]["."]["extra-files"]
    assert {"type": "generic", "path": "deploy/helm/javv-opensearch/Chart.yaml"} in extra


@pytest.mark.parametrize("mode", [DEMO, OWN_SECRET, CERT_MANAGER], ids=["demo", "own", "cm"])
def test_the_security_files_replace_the_images_in_every_mode(mode: tuple[str, ...]) -> None:
    docs = _render(*mode)
    env = {e["name"]: e["valueFrom"]["secretKeyRef"] for e in _users_init(docs)["env"]}
    own = mode is OWN_SECRET
    assert env == {
        "JAVV_ADMIN_PASSWORD": {
            "name": "store-admin" if own else "t-javv-opensearch-admin",
            "key": "password",
        },
        "JAVV_BACKEND_PASSWORD": {
            "name": "store-backend" if own else "t-javv-opensearch-backend",
            "key": "password",
        },
    }
    security = f"{IMAGE_HOME}/config/opensearch-security"
    mounts = {(m["name"], m.get("subPath")): m["mountPath"] for m in _store(docs)["volumeMounts"]}
    assert mounts[("javv-users", "internal_users.yml")] == f"{security}/internal_users.yml"
    assert mounts[("javv-security", "roles.yml")] == f"{security}/roles.yml"
    assert mounts[("javv-security", "roles_mapping.yml")] == f"{security}/roles_mapping.yml"
    volumes = {v["name"]: v for v in _pod(docs)["volumes"]}
    assert volumes["javv-security"]["configMap"]["name"] == "t-javv-opensearch-security"


def test_the_role_and_mapping_are_the_charts_files() -> None:
    """files/ is held equal to the compose file's configs by test_opensearch_role.py."""
    (config,) = [c for c in _kind(_render(*DEMO), "ConfigMap") if "roles.yml" in c["data"]]
    assert config["metadata"]["name"] == "t-javv-opensearch-security"
    for name in ("roles.yml", "roles_mapping.yml"):
        assert yaml.safe_load(config["data"][name]) == yaml.safe_load(
            (CHART / "files" / name).read_text()
        )


def test_each_password_is_only_in_its_secret() -> None:
    docs = _render(*DEMO)
    secrets = {s["metadata"]["name"]: s["stringData"] for s in _kind(docs, "Secret")}
    admin, backend = PASSWORD.split("=", 1)[1], BACKEND.split("=", 1)[1]
    assert secrets == {
        "t-javv-opensearch-admin": {"password": admin},
        "t-javv-opensearch-backend": {"password": backend},
    }
    others = yaml.safe_dump_all([doc for doc in docs if doc["kind"] != "Secret"])
    assert admin not in others and backend not in others


def test_an_existing_secret_renders_no_secret() -> None:
    assert _kind(_render(*OWN_SECRET), "Secret") == []


def _run_users_init(
    home: Path, hash_line: str, backend: str = "Pj-729-render"
) -> subprocess.CompletedProcess[str]:
    """Run the init container's script with a stand-in for OpenSearch's hash.sh that prints its
    usual noise, then a line built from the variable it was told to read."""
    script = _users_init(_render(*DEMO))["command"][2]
    tools = home / "plugins" / "opensearch-security" / "tools"
    tools.mkdir(parents=True)
    (home / "javv-users").mkdir()
    hash_sh = tools / "hash.sh"
    hash_sh.write_text(
        f'#!/bin/sh\necho "WARNING: noise"\n[ "$1" = -env ] || exit 2\n{hash_line}\n'
    )
    hash_sh.chmod(0o755)
    env = {
        "PATH": os.environ["PATH"],
        "JAVV_ADMIN_PASSWORD": "Pw-725-render!",
        "JAVV_BACKEND_PASSWORD": backend,
    }
    script = script.replace("/javv-users/", f"{home}/javv-users/")
    return subprocess.run(["bash", "-c", script], cwd=home, env=env, capture_output=True, text=True)


HASH_FROM_THE_VARIABLE = 'v=$(printenv "$2") && [ -n "$v" ] && printf \'$2y$12$%s\\n\' "$v"'


def test_the_users_file_holds_admin_and_javv_hashed_from_the_environment(tmp_path: Path) -> None:
    # the stand-in "hashes" the variable named after -env, so the hash proves where it read from
    started = _run_users_init(tmp_path, HASH_FROM_THE_VARIABLE)
    assert started.returncode == 0, started.stderr
    users = yaml.safe_load((tmp_path / "javv-users" / "internal_users.yml").read_text())
    assert users == {
        "_meta": {"type": "internalusers", "config_version": 2},
        "admin": {
            "hash": "$2y$12$Pw-725-render!",
            "reserved": True,
            "backend_roles": ["admin"],
            "description": "JAVV admin user",
        },
        "javv": {"hash": "$2y$12$Pj-729-render", "reserved": False, "description": "JAVV backend"},
    }


def test_no_users_file_without_a_hash(tmp_path: Path) -> None:
    started = _run_users_init(tmp_path, "echo 'no such variable'")
    assert started.returncode != 0
    assert "no bcrypt hash for JAVV_ADMIN_PASSWORD" in started.stderr
    assert not (tmp_path / "javv-users" / "internal_users.yml").exists()


def test_no_users_file_without_javvs_hash(tmp_path: Path) -> None:
    started = _run_users_init(tmp_path, HASH_FROM_THE_VARIABLE, backend="")
    assert started.returncode != 0
    assert "no bcrypt hash for JAVV_BACKEND_PASSWORD" in started.stderr
    assert not (tmp_path / "javv-users" / "internal_users.yml").exists()


def test_demo_mode_leaves_the_certificates_to_the_demo_setup() -> None:
    """The image's demo setup adds its certificates unless opensearch.yml already mentions
    plugins.security, so in demo mode the file must not."""
    docs = _render(*DEMO)
    assert "plugins.security" not in _opensearch_yml(docs)
    assert "javv-tls" not in {v["name"] for v in _pod(docs)["volumes"]}
    assert _kind(docs, "Certificate") == []
    assert _test_pod_env(docs)["TLS"] == "--insecure"


@pytest.mark.parametrize("mode", [OWN_SECRET, CERT_MANAGER], ids=["own", "cm"])
def test_your_own_certificates_switch_the_demo_setup_off(mode: tuple[str, ...]) -> None:
    docs = _render(*mode)
    config = yaml.safe_load(_opensearch_yml(docs))
    for layer in ("transport", "http"):
        assert config[f"plugins.security.ssl.{layer}.pemcert_filepath"] == "certs/tls.crt"
        assert config[f"plugins.security.ssl.{layer}.pemkey_filepath"] == "certs/tls.key"
        assert config[f"plugins.security.ssl.{layer}.pemtrustedcas_filepath"] == "certs/ca.crt"
    assert config["plugins.security.ssl.http.enabled"] is True
    assert config["plugins.security.ssl.certificates_hot_reload.enabled"] is True
    assert "plugins.security.authcz.admin_dn" not in config
    volumes = {v["name"]: v for v in _pod(docs)["volumes"]}
    secret = "store-certs" if mode is OWN_SECRET else "t-javv-opensearch-tls"
    assert volumes["javv-tls"]["secret"]["secretName"] == secret
    mount = next(m for m in _store(docs)["volumeMounts"] if m["name"] == "javv-tls")
    # a directory mount: Kubernetes updates it in place when the Secret changes, a subPath never
    assert mount["mountPath"] == f"{IMAGE_HOME}/config/certs"
    assert "subPath" not in mount
    assert _test_pod_env(docs)["TLS"] == "--cacert /javv-tls/ca.crt"


def test_cert_manager_asks_for_a_certificate_opensearch_can_read() -> None:
    (certificate,) = _kind(_render(*CERT_MANAGER), "Certificate")
    spec = certificate["spec"]
    assert spec["secretName"] == "t-javv-opensearch-tls"
    assert spec["issuerRef"] == {"name": "store-ca"}
    assert spec["privateKey"]["encoding"] == "PKCS8"
    assert {"server auth", "client auth"} <= set(spec["usages"])
    assert {"javv-opensearch", "javv-opensearch.javv.svc", "localhost"} <= set(spec["dnsNames"])
    assert _kind(_render(*OWN_SECRET), "Certificate") == []


def test_admin_dn_names_who_may_run_securityadmin() -> None:
    docs = _render(*OWN_SECRET, "opensearch.javv.tls.adminDn[0]=CN=javv-admin")
    config = yaml.safe_load(_opensearch_yml(docs))
    assert config["plugins.security.authcz.admin_dn"] == ["CN=javv-admin"]


@pytest.mark.parametrize(
    ("sets", "message"),
    [
        ((BACKEND,), "opensearch.javv.auth: set existingSecret"),
        ((PASSWORD, BACKEND, "opensearch.javv.auth.existingSecret=s"), "not both"),
        ((PASSWORD,), "opensearch.javv.backend: set existingSecret"),
        (
            (*DEMO, "opensearch.javv.backend.existingSecret=s"),
            "opensearch.javv.backend: set existingSecret or password, not both",
        ),
        (
            (*OWN_SECRET, "opensearch.javv.tls.certManager.enabled=true"),
            "opensearch.javv.tls: set existingSecret or certManager.enabled, not both",
        ),
        (
            (*DEMO, "opensearch.javv.tls.certManager.enabled=true"),
            "opensearch.javv.tls.certManager.issuerRef.name",
        ),
        ((*DEMO, "opensearch.singleNode=false"), "JAVV runs one OpenSearch node"),
        ((*DEMO, "opensearch.javv.tls.adminDN[0]=x"), "additional properties 'adminDN'"),
    ],
    ids=[
        "no-password",
        "two-passwords",
        "no-backend-password",
        "two-backend-passwords",
        "two-certificates",
        "no-issuer",
        "nodes",
        "typo",
    ],
)
def test_the_install_fails_with_its_reason(sets: tuple[str, ...], message: str) -> None:
    out = _helm(*sets)
    assert out.returncode != 0
    assert message in out.stderr
