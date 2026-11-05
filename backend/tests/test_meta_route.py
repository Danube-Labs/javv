"""`GET /api/v1/meta` and the version it reports (issue 261).

Pins: the route needs a session (401 without one, since `/readyz` is the anonymous endpoint and
must not carry the version); a signed-in user with no capabilities gets the running versions,
including the live OpenSearch and Python versions (issue 341); an unreachable OpenSearch empties
only its own field, counted and logged, so the rest still answers; the same versions land on the
`bootstrap complete` log line an operator reads without a session; and `APP_VERSION` equals the
release-please manifest, so a release PR that forgets to bump it fails."""

import json
import platform
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout

from backend.auth.passwords import hash_password
from backend.core import lifespan as lifespan_module
from backend.core.bootstrap import MAPPING_VERSION
from backend.core.metrics import OS_REQUEST_ERRORS
from backend.main import create_app
from backend.routers import meta as meta_module
from backend.version import APP_VERSION
from os_env import OS_URL, requires_opensearch

PASSWORD = "meta-route-password"
MANIFEST = Path(__file__).resolve().parents[2] / ".release-please-manifest.json"


def test_app_version_matches_the_release_manifest() -> None:
    assert json.loads(MANIFEST.read_text())["."] == APP_VERSION


def test_openapi_reports_the_app_version() -> None:
    assert create_app().openapi()["info"]["version"] == APP_VERSION


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://t")
    yield http, client
    await http.aclose()
    await client.close()


async def _login_without_capabilities(http: httpx.AsyncClient, client: AsyncOpenSearch) -> None:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index="system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(PASSWORD),
            "role": "custom",
            "capabilities": [],
            "must_change": False,
            "disabled": False,
            "auth_source": "local",
            "external_id": None,
            "created_at": "2026-09-29T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200


@requires_opensearch
async def test_meta_needs_a_session(env) -> None:
    http, _ = env
    assert (await http.get("/api/v1/meta")).status_code == 401


@requires_opensearch
async def test_meta_reports_the_running_versions_to_any_signed_in_user(env) -> None:
    http, client = env
    await _login_without_capabilities(http, client)
    r = await http.get("/api/v1/meta")
    assert r.status_code == 200
    assert r.json() == {
        "version": APP_VERSION,
        "mapping_version": MAPPING_VERSION,
        # the envelope versions ingest accepts: a new one lands here with the model change
        "envelope_versions": [3, 4],
        # read live from the store, so an OpenSearch upgrade shows without a backend restart
        "opensearch_version": (await client.info())["version"]["number"],
        "python_version": platform.python_version(),
        "mcp_enabled": False,  # JAVV_MCP_ENABLED is off by default (issue 1096)
    }


@requires_opensearch
@pytest.mark.parametrize(
    ("failure", "kind"),
    [
        (OSConnectionError("N/A", "unreachable", Exception("down")), "conn"),
        (ConnectionTimeout("TIMEOUT", "timed out", Exception("slow")), "timeout"),
    ],
)
async def test_an_unreachable_store_empties_only_the_opensearch_version(
    env, monkeypatch, failure: Exception, kind: str
) -> None:
    http, client = env
    await _login_without_capabilities(http, client)  # the session lookup needs the real store

    async def _info_fails(*args: Any, **kwargs: Any) -> Any:
        raise failure

    monkeypatch.setattr(client, "info", _info_fails)
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(meta_module, "log", structlog.wrap_logger(None, processors=[capture]))
    errors = OS_REQUEST_ERRORS.labels(kind)
    before = errors._value.get()

    r = await http.get("/api/v1/meta")

    assert r.status_code == 200  # the sidebar keeps its versions during an outage
    body = r.json()
    assert body["opensearch_version"] is None
    assert body["version"] == APP_VERSION
    assert body["python_version"] == platform.python_version()
    assert errors._value.get() == before + 1  # counted (observability.md §5)
    assert capture.entries == [
        {"event": "opensearch version unavailable", "log_level": "warning", "kind": kind}
    ]


class _RecordingLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **fields: Any) -> None:
        self.events.append((event, fields))


@requires_opensearch
async def test_the_bootstrap_log_line_carries_the_versions(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_OPENSEARCH_URL", OS_URL)
    recorder = _RecordingLog()
    monkeypatch.setattr(lifespan_module, "log", recorder)
    async with lifespan_module.lifespan(create_app()):
        pass
    fields = dict(recorder.events)["bootstrap complete"]
    assert fields["app_version"] == APP_VERSION
    assert fields["mapping_version"] == MAPPING_VERSION
