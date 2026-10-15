"""The compose file is the second copy of the settings (issue 452): `deploy/compose/compose.yaml`
lists every backend setting with its default and a comment, like a Helm values file. The code
(`core/settings.py`) is the source, and this test keeps the copy honest:

- every `Settings` field appears in the backend service;
- every `JAVV_` key in the file is a `Settings` field or a name the code reads (the rule of
  `development/scripts/check-docs-drift.sh`: `JAVV_LOG_LEVEL` is read by javv_common, and
  `JAVV_BACKEND_URL` by the frontend server);
- every value is the code default, except the named set the compose file sets on purpose;
- the backend and frontend run the images a release publishes, under the release-please manifest's
  version, on lines release-please rewrites (a release PR gets no CI run of its own);
- OpenSearch runs with its security plugin on, and one password from `.env` reaches both the
  store and the backend, without being written into a container's command (issue 715);
- OpenSearch starts with `admin` as its only user: the demo setup's other users are cut from its
  users file before the first start (issue 736).

The Helm chart is the third copy (issue 725): `deploy/helm/javv/values.yaml` lists the same settings
under `backend.config` as plain values, each the compose file's default, except the store's
address. Its secrets come from Kubernetes Secrets, so they are not settings there.

Each value is written `${JAVV_X:-default}`, so `.env` overrides any setting without an edit to the
compose file; the default after `:-` is what is compared. Keys without the prefix (`TZ`) are not
settings and are ignored. No store needed."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import TypeAdapter

from backend.core.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "deploy" / "compose" / "compose.yaml"
MANIFEST = ROOT / ".release-please-manifest.json"
CHART_VALUES = ROOT / "deploy" / "helm" / "javv" / "values.yaml"

# set on purpose to something other than the code default (issue 452, plan v7 ruling 3)
NOT_THE_CODE_DEFAULT = {
    "JAVV_OPENSEARCH_URL",  # the compose service, not localhost
    "JAVV_SECRET_KEY",  # required from .env
    "JAVV_BOOTSTRAP_ADMIN_PASSWORD",  # required from .env
    "JAVV_ENV",  # prod: the dev secret key refuses to start
    # issue 715: the compose store runs with its security plugin on, with demo certificates
    # issue 729: javv, which holds only the javv role, and its password, which the store sets
    "JAVV_OPENSEARCH_USERNAME",
    "JAVV_OPENSEARCH_PASSWORD",  # required from .env
    "JAVV_OPENSEARCH_VERIFY_CERTS",  # false: the demo certificate does not name the service
}

_VALUE = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+)(?P<op>:-|:\?)(?P<rest>.*)\}$")
_JAVV_NAME = re.compile(r"JAVV_[A-Z0-9_]+")


def _services() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def _environment(service: str) -> dict[str, str]:
    return {k: str(v) for k, v in (_services()[service].get("environment") or {}).items()}


def _all_javv_keys() -> set[str]:
    return {
        key for service in _services() for key in _environment(service) if key.startswith("JAVV_")
    }


def _code_literals() -> set[str]:
    """Every JAVV_ name the shipped code mentions: the backend, the shared lib, the frontend
    server. Settings fields are matched separately (pydantic adds the prefix)."""
    sources = [
        *(ROOT / "backend" / "src").rglob("*.py"),
        *(ROOT / "libs").rglob("*.py"),
        *(ROOT / "frontend" / "server").rglob("*.mjs"),
    ]
    return {name for path in sources for name in _JAVV_NAME.findall(path.read_text())}


def _env_name(field: str) -> str:
    return f"JAVV_{field.upper()}"


def _parsed(key: str, raw: str, name: str | None = None) -> re.Match[str]:
    """`name` is the variable the value must read, when it differs from the key (OpenSearch's own
    `OPENSEARCH_INITIAL_ADMIN_PASSWORD` reads `JAVV_OPENSEARCH_ADMIN_PASSWORD`)."""
    match = _VALUE.match(raw)
    assert match, f"{key}: write it as ${{{key}:-default}} so .env can override it, got {raw!r}"
    expected = name or key
    assert match["name"] == expected, f"{key} interpolates {match['name']}, not {expected}"
    return match


def test_every_setting_is_in_the_compose_file() -> None:
    backend = _environment("backend")
    missing = sorted(_env_name(f) for f in Settings.model_fields if _env_name(f) not in backend)
    assert not missing, f"settings missing from {COMPOSE.relative_to(ROOT)}: {missing}"


def test_every_javv_key_in_the_compose_file_is_read_by_the_code() -> None:
    known = {_env_name(f) for f in Settings.model_fields} | _code_literals()
    unknown = sorted(_all_javv_keys() - known)
    assert not unknown, f"no code reads these: {unknown}"


def test_every_javv_value_can_be_overridden_from_env() -> None:
    for service in _services():
        for key, raw in _environment(service).items():
            if key.startswith("JAVV_"):
                _parsed(key, raw)


@pytest.mark.parametrize(
    "field",
    [f for f in Settings.model_fields if _env_name(f) not in NOT_THE_CODE_DEFAULT],
)
def test_each_value_is_the_code_default(field: str) -> None:
    key = _env_name(field)
    match = _parsed(key, _environment("backend")[key])
    assert match["op"] == ":-", f"{key} is a setting with a default, not a required value"
    info = Settings.model_fields[field]
    # pydantic's own coercion, as for a real environment variable: "24" and "24.0" both read 24.0
    assert TypeAdapter(info.annotation).validate_python(match["rest"]) == info.default


def test_the_named_exceptions_are_what_a_deployment_needs() -> None:
    backend = _environment("backend")
    for secret in (
        "JAVV_SECRET_KEY",
        "JAVV_BOOTSTRAP_ADMIN_PASSWORD",
        "JAVV_OPENSEARCH_PASSWORD",
    ):
        assert _parsed(secret, backend[secret])["op"] == ":?", f"{secret} must be required"
    assert _parsed("JAVV_ENV", backend["JAVV_ENV"])["rest"] == "prod"
    assert _parsed("JAVV_OPENSEARCH_URL", backend["JAVV_OPENSEARCH_URL"])["rest"] == (
        "https://opensearch:9200"
    )
    assert _parsed("JAVV_OPENSEARCH_USERNAME", backend["JAVV_OPENSEARCH_USERNAME"])["rest"] == (
        "javv"
    )
    verify = _parsed("JAVV_OPENSEARCH_VERIFY_CERTS", backend["JAVV_OPENSEARCH_VERIFY_CERTS"])
    assert verify["rest"] == "false"


# required in compose (`:?`); in the chart they come from Secrets, never from backend.config
SECRETS = {"JAVV_SECRET_KEY", "JAVV_BOOTSTRAP_ADMIN_PASSWORD", "JAVV_OPENSEARCH_PASSWORD"}


def _chart(block: str) -> dict[str, str]:
    return {k: str(v) for k, v in yaml.safe_load(CHART_VALUES.read_text())[block]["config"].items()}


def test_every_setting_is_in_the_chart() -> None:
    chart = _chart("backend")
    expected = {_env_name(f) for f in Settings.model_fields} - SECRETS
    assert not sorted(expected - set(chart)), f"missing from {CHART_VALUES.relative_to(ROOT)}"
    assert not SECRETS & set(chart), "a secret is a Secret in the chart, not a setting"


def test_every_javv_key_in_the_chart_is_read_by_the_code() -> None:
    known = {_env_name(f) for f in Settings.model_fields} | _code_literals()
    keys = {k for block in ("backend", "frontend") for k in _chart(block) if k.startswith("JAVV_")}
    assert not sorted(keys - known), "no code reads these"


@pytest.mark.parametrize(
    "field",
    [f for f in Settings.model_fields if _env_name(f) not in NOT_THE_CODE_DEFAULT],
)
def test_each_chart_value_is_the_code_default(field: str) -> None:
    info = Settings.model_fields[field]
    value = _chart("backend")[_env_name(field)]
    assert TypeAdapter(info.annotation).validate_python(value) == info.default


def test_the_chart_and_compose_agree_on_every_value_but_the_store_address() -> None:
    """The named exceptions too: prod, javv as the store user, unchecked demo certificates. Only
    the address differs: the chart's store is the javv-opensearch chart's Service."""
    compose = {k: _VALUE.match(v) for k, v in _environment("backend").items()}
    for key, value in _chart("backend").items():
        match = compose[key]
        default = match["rest"] if match else None  # TZ is written the same way
        if key == "JAVV_OPENSEARCH_URL":
            assert value == "https://javv-opensearch:9200"
        else:
            assert value == default, f"{key}: chart {value!r}, compose {default!r}"
    frontend = _environment("frontend")
    for key, value in _chart("frontend").items():
        if key != "JAVV_BACKEND_URL":  # the chart's own backend Service, filled in by the template
            assert value == _parsed(key, frontend[key])["rest"], key


def test_opensearch_runs_with_its_security_plugin_on() -> None:
    store = _environment("opensearch")
    assert "DISABLE_SECURITY_PLUGIN" not in store, "compose runs OpenSearch with its login on"
    assert "DISABLE_INSTALL_DEMO_CONFIG" not in store, "the demo certificates are what it serves"
    admin = _parsed(
        "OPENSEARCH_INITIAL_ADMIN_PASSWORD",
        store["OPENSEARCH_INITIAL_ADMIN_PASSWORD"],
        name="JAVV_OPENSEARCH_ADMIN_PASSWORD",
    )
    assert admin["op"] == ":?", "the store's admin password is required from .env"
    javv = _parsed(
        "OPENSEARCH_JAVV_PASSWORD",
        store["OPENSEARCH_JAVV_PASSWORD"],
        name="JAVV_OPENSEARCH_PASSWORD",
    )
    assert javv["op"] == ":?", "javv's password is required from .env"
    # the demo setup's own audit log writes a daily index nothing deletes (ISM is off); JAVV
    # keeps its own audit trail
    assert store.get("plugins.security.audit.type") == "noop"


def test_the_backend_never_gets_the_stores_admin_password() -> None:
    """Issue 729: the backend signs in as javv; admin's password stays with the store."""
    for service in ("backend", "frontend"):
        values = _environment(service).values()
        assert not any("JAVV_OPENSEARCH_ADMIN_PASSWORD" in v for v in values), service


# the layout of the image's own users file (OpenSearch 3.9.0), with stand-in hashes: comments,
# _meta, then the demo users, each of whom signs in with its own name as password
DEMO_USERS = """---
# This is the internal user database
# The hash value is a bcrypt hash and can be generated with plugin/tools/hash.sh

_meta:
  type: "internalusers"
  config_version: 2

# Define your internal users here

## Demo users

admin:
  hash: "admin-hash"
  reserved: true
  backend_roles:
  - "admin"
  description: "Demo admin user"

anomalyadmin:
  hash: "anomalyadmin-hash"
  reserved: false
  opendistro_security_roles:
  - "anomaly_full_access"
  description: "Demo anomaly admin user, using internal role"

readall:
  hash: "readall-hash"
  reserved: false
  backend_roles:
  - "readall"
  description: "Demo readall user"

snapshotrestore:
  hash: "snapshotrestore-hash"
  reserved: false
  backend_roles:
  - "snapshotrestore"
  description: "Demo snapshotrestore user"
"""
USERS_FILE = Path("config/opensearch-security/internal_users.yml")
HASH_TOOL = Path("plugins/opensearch-security/tools/hash.sh")
# OpenSearch's hash.sh prints a warning, then the bcrypt hash of the variable `-env` names; the
# stand-in's "hash" is the password's sha256, in bcrypt's alphabet as a real hash is
STAND_IN_HASH = """#!/bin/sh
[ "$1" = -env ] || exit 2
eval "password=\\$$2"
[ -n "$password" ] || { echo "no password"; exit 0; }
echo "**************************************************************************"
printf '$2y$12$%s\\n' "$(printf %s "$password" | sha256sum | cut -c1-53)"
"""


def _stand_in_hash(password: str) -> str:
    return "$2y$12$" + hashlib.sha256(password.encode()).hexdigest()[:53]


def _run_opensearch_entrypoint(
    home: Path, users: str, command: list[str] | None = None, javv_password: str = "Javv-pass-729!"
) -> subprocess.CompletedProcess[str]:
    """Run the store's entrypoint as its container does: compose hands the shell one `$` and
    appends the service's command (or `compose run`'s) after the entrypoint. The layout is a copy
    of the image's, whose own entrypoint is a stand-in that reports how it was called, and the
    shell's temp directory is the test's own, so a file left behind shows."""
    service = _services()["opensearch"]
    entrypoint = service["entrypoint"]
    assert entrypoint[:2] == ["/bin/bash", "-c"]
    (home / USERS_FILE).parent.mkdir(parents=True)
    (home / USERS_FILE).write_text(users)
    (home / "tmp").mkdir()
    image_entrypoint = home / "opensearch-docker-entrypoint.sh"
    image_entrypoint.write_text('#!/bin/sh\necho "image entrypoint: $*"\n')
    image_entrypoint.chmod(0o755)
    (home / HASH_TOOL).parent.mkdir(parents=True)
    (home / HASH_TOOL).write_text(STAND_IN_HASH)
    (home / HASH_TOOL).chmod(0o755)
    argv = [entrypoint[2].replace("$$", "$"), *entrypoint[3:], *(command or service["command"])]
    env = {
        "PATH": os.environ["PATH"],
        "TMPDIR": str(home / "tmp"),
        "OPENSEARCH_JAVV_PASSWORD": javv_password,
    }
    return subprocess.run(["bash", "-c", *argv], cwd=home, env=env, capture_output=True, text=True)


def test_opensearch_starts_with_admin_and_javv_as_its_users(tmp_path: Path) -> None:
    """The demo security setup loads every user in the image's file, and no setting turns the
    others off (issue 736). The entrypoint keeps `_meta` and `admin`, unchanged, adds `javv` with
    its password hashed by OpenSearch's own tool (issue 729), then hands over to the image's own
    entrypoint with the image's own command."""
    started = _run_opensearch_entrypoint(tmp_path, DEMO_USERS, javv_password='Pa"ss$Word-729!')
    assert started.returncode == 0, started.stderr
    assert started.stdout == "image entrypoint: opensearch\n"
    kept = yaml.safe_load((tmp_path / USERS_FILE).read_text())
    demo = yaml.safe_load(DEMO_USERS)
    assert kept == {
        "_meta": demo["_meta"],
        "admin": demo["admin"],
        "javv": {
            "hash": _stand_in_hash('Pa"ss$Word-729!'),
            "reserved": False,
            "description": "JAVV backend",
        },
    }
    assert not any((tmp_path / "tmp").iterdir())


def test_opensearch_does_not_start_when_javvs_password_cannot_be_hashed(tmp_path: Path) -> None:
    started = _run_opensearch_entrypoint(tmp_path, DEMO_USERS, javv_password="")
    assert started.returncode != 0
    assert "could not hash OPENSEARCH_JAVV_PASSWORD" in started.stderr
    assert started.stdout == "", "the image's entrypoint must not run"
    assert (tmp_path / USERS_FILE).read_text() == DEMO_USERS
    assert not any((tmp_path / "tmp").iterdir())


def test_opensearch_does_not_start_without_an_admin_user(tmp_path: Path) -> None:
    without_admin = DEMO_USERS.replace("admin:\n", "someone:\n", 1)
    started = _run_opensearch_entrypoint(tmp_path, without_admin)
    assert started.returncode != 0
    assert "no admin user" in started.stderr
    assert started.stdout == "", "the image's entrypoint must not run"
    assert (tmp_path / USERS_FILE).read_text() == without_admin
    # restart: unless-stopped retries it, so a file left per try would pile up
    assert not any((tmp_path / "tmp").iterdir())


def test_compose_run_still_hands_its_command_to_the_image(tmp_path: Path) -> None:
    """`docker compose run opensearch bash` replaces the service's command, not the entrypoint;
    the image's own entrypoint runs any command other than `opensearch` as given."""
    started = _run_opensearch_entrypoint(tmp_path, DEMO_USERS, command=["bash", "-l"])
    assert started.returncode == 0, started.stderr
    assert started.stdout == "image entrypoint: bash -l\n"


def test_the_health_check_keeps_the_password_out_of_the_container_command() -> None:
    """One `$` is interpolated by compose, which writes the password into the container's
    command, visible in docker inspect; `$$` leaves it to the container's shell. The login then
    reaches curl on stdin (`-K -`), not as `-u`, where `ps` in the container would show it."""
    check = " ".join(_services()["opensearch"]["healthcheck"]["test"])
    assert "$$OPENSEARCH_INITIAL_ADMIN_PASSWORD" in check
    assert "${" not in check and "JAVV_" not in check
    assert "-K -" in check and " -u " not in check and "--user" not in check
    assert "https://localhost:9200" in check


@pytest.mark.parametrize(
    "password",
    ['Pa"ss\\Word1-715!', "Sp ace%$#'-Word1!", "Plain-Word1-715!"],
)
def test_the_health_check_hands_curl_any_password_intact(password: str) -> None:
    """OpenSearch's rules ask for a special character, and curl reads a double-quoted config
    value with escapes: unescaped, `pa"ss` reached the store as `pa` and the store never turned
    healthy (review of PR 733). Run the part of the check that builds curl's config, as the
    container's shell runs it, and require each `"` and `\\` escaped and nothing else touched."""
    check = _services()["opensearch"]["healthcheck"]["test"][1]
    feed = check.replace("$$", "$").split(" | curl ")[0]  # compose hands the shell one $
    env = {"PATH": os.environ["PATH"], "OPENSEARCH_INITIAL_ADMIN_PASSWORD": password}
    out = subprocess.run(["sh", "-c", feed], env=env, capture_output=True, text=True, check=True)
    escaped = password.replace("\\", "\\\\").replace('"', '\\"')
    assert out.stdout == f'user = "admin:{escaped}"\n'


def test_the_frontend_reaches_the_backend_by_its_service_name() -> None:
    frontend = _environment("frontend")
    assert _parsed("JAVV_BACKEND_URL", frontend["JAVV_BACKEND_URL"])["rest"] == (
        "http://backend:8000"
    )


@pytest.mark.parametrize("app", ["backend", "frontend"])
def test_the_app_runs_the_published_image_of_this_release(app: str) -> None:
    version = json.loads(MANIFEST.read_text())["."]
    service = _services()[app]
    assert "build" not in service, f"{app} builds from source, not the published image"
    image = f"ghcr.io/danube-labs/javv-{app}:{version}"
    assert service["image"] == image
    assert f"image: {image} # x-release-please-version" in COMPOSE.read_text(), (
        f"{app}: without the annotation, release-please leaves the tag behind on the next release"
    )


WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
COMPOSE_UP = "docker compose -f deploy/compose/compose.yaml up"
SETUP_SCRIPT = "deploy/compose/setup.sh"


def _filled_by_setup_script() -> set[str]:
    """The keys that setup.sh fills: the template's empty `KEY=` lines (issue 869)."""
    template = (COMPOSE.parent / ".env.example").read_text().splitlines()
    return {line[:-1] for line in template if re.fullmatch(r"[A-Z0-9_]+=", line)}


def _compose_up_steps() -> list[tuple[str, set[str]]]:
    """Every workflow step that starts the compose file, with the names it sets: its env, and the
    .env of setup.sh when an earlier step of its job ran the script."""
    found = []
    for workflow in WORKFLOWS:
        for name, job in (yaml.safe_load(workflow.read_text())["jobs"] or {}).items():
            made_env = False
            for step in job.get("steps", []):
                run = step.get("run", "")
                if COMPOSE_UP in run:
                    names = {*(job.get("env") or {}), *(step.get("env") or {})}
                    if made_env:
                        names |= _filled_by_setup_script()
                    found.append((f"{workflow.name} {name} / {step.get('name')}", names))
                made_env = made_env or SETUP_SCRIPT in run
    return found


def test_every_workflow_that_starts_the_stack_sets_what_compose_requires() -> None:
    # compose refuses to start on an unset `${NAME:?…}`: 0.6.0's release smoke missed one, issue 729
    required = set(re.findall(r"\$\{([A-Z0-9_]+):\?", COMPOSE.read_text()))
    assert required >= {"JAVV_OPENSEARCH_ADMIN_PASSWORD", "JAVV_OPENSEARCH_PASSWORD"}
    steps = _compose_up_steps()
    assert {where.split(" ")[0] for where, _ in steps} == {"ci.yml", "release-please.yml"}
    for where, names in steps:
        assert required <= names, f"{where} leaves {sorted(required - names)} unset"
