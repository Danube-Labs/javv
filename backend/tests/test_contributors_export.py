"""Issue 359 — GET /api/v1/contributors/export.csv against real OpenSearch.

Pins what a CSV export can get wrong that a JSON read cannot: formula-armed cells, a file that
disagrees with the screen it came from, a cap that never fires, and columns that appear and
vanish with the data (which breaks any spreadsheet built on the file).
"""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.audit.writer import append_field_change
from backend.auth.passwords import hash_password
from backend.core.metrics import EXPORT_BYTES, EXPORT_ROWS, LIMIT_REJECTIONS
from backend.core.settings import get_settings
from backend.export.contributors_csv import CONTRIBUTORS_CSV_COLUMNS
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

PASSWORD = "contrib-export-password"

pytestmark = requires_opensearch


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login() -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "custom",
                "capabilities": ["can_export"],  # the export routes need it (issue 243)
                "must_change": False,
                "disabled": False,
                "auth_source": "local",
                "external_id": None,
                "created_at": "2026-07-05T00:00:00+00:00",
            },
            params={"refresh": "true"},
        )
        http = httpx.AsyncClient(transport=transport, base_url="https://t")
        jars.append(http)
        r = await http.post("/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200
        return http

    yield login, client
    for http in jars:
        await http.aclose()
    await client.close()


async def _seed_finding(
    client: AsyncOpenSearch, cid: str, fk: str, *, first_seen: datetime
) -> None:
    await client.index(
        index="findings",
        id=fk,
        body={
            "finding_key": fk,
            "cluster_id": cid,
            "scanner": "trivy",
            "cve_id": "CVE-2024-6000",
            "image_digest": "sha256:contribexp",
            "namespaces": ["default"],
            "state": "resolved",
            "present": True,
            "severity": "critical",
            "severity_rank": 5,
            "kev": False,
            "first_seen_at": first_seen.isoformat(),
        },
        params={"refresh": "true"},
    )


async def _journal(
    client: AsyncOpenSearch, cid: str, actor: str, fk: str, action: str, field: str = "state"
) -> None:
    await append_field_change(
        client,
        actor=actor,
        action=action,
        entity_type="finding",
        entity_id=fk,
        field=field,
        old_value="open",
        new_value=action,
        revision=1,
        cluster_id=cid,
        finding_key=fk,
    )


async def _journal_at(
    client: AsyncOpenSearch, cid: str, actor: str, fk: str, action: str, when: datetime
) -> None:
    """An action stamped in the PAST. The writer always stamps `now`, and the window filters the
    ACTION's `@timestamp` (not the finding's `first_seen_at`) — so a window test has to seed the
    row directly or it silently asserts nothing."""
    event_id = uuid.uuid4().hex
    await client.index(
        index="system-audit-log",
        id=event_id,
        body={
            "@timestamp": when.isoformat(),
            "event_id": event_id,
            "schema_version": 1,
            "actor": actor,
            "action": action,
            "entity_type": "finding",
            "entity_id": fk,
            "finding_key": fk,
            "field": "state",
            "field_type": "scalar",
            "old_value": "open",
            "new_value": action,
            "revision": 1,
            "cluster_id": cid,
        },
        params={"op_type": "create", "refresh": "true"},
    )


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


async def test_export_matches_the_screen_and_neutralizes_formula_cells(env) -> None:
    """The file IS the screen's leaderboard — same numbers, because both ride `_payload`.

    The actor name is the one cell an attacker controls (it is a username), so it carries the
    injection bait: a `=cmd()` actor must land apostrophe-quoted, inert in a spreadsheet.
    """
    login, client = env
    cid = f"c-cexp-{uuid.uuid4().hex[:8]}"
    bait = "=cmd()|'/c calc'!A1"
    now = datetime.now(UTC)

    await _seed_finding(client, cid, "fk-a", first_seen=now - timedelta(days=1))
    await _journal(client, cid, bait, "fk-a", "resolve")
    await _journal(client, cid, bait, "fk-a", "assign", field="assignee")
    await _seed_finding(client, cid, "fk-b", first_seen=now - timedelta(days=3))
    await _journal(client, cid, bait, "fk-b", "acknowledge")
    await _journal(client, cid, "system", "fk-a", "resolve")  # machines never chart
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid, "days": 30})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "javv-contributors-" in r.headers["content-disposition"]

    lines = r.text.splitlines()
    assert lines[0].split(",") == list(CONTRIBUTORS_CSV_COLUMNS)  # header is our constants, raw
    rows = _rows(r.text)
    assert len(rows) == 1  # only the human actor; `system` is filtered upstream
    row = rows[0]

    # the bait is defused, and the value stays readable rather than being dropped
    assert row["actor"] == f"'{bait}"
    assert not any(ln.startswith(("=", "+", "@")) for ln in lines[1:])

    # ...and the numbers are the JSON read's, cell for cell
    j = await http.get("/api/v1/contributors", params={"cluster_id": cid, "days": 30})
    board = j.json()["leaderboard"][0]
    assert int(row["actions"]) == board["actions"] == 3
    assert int(row["handled"]) == board["handled"] == 2
    assert float(row["sla_hit_pct"]) == board["sla_hit_pct"]
    assert float(row["median_ttr_seconds"]) == board["median_ttr_seconds"]
    # the per-action split, one fixed column per action of the closed vocabulary
    assert int(row["action_resolve"]) == 1
    assert int(row["action_acknowledge"]) == 1
    assert int(row["action_assign"]) == 1
    assert int(row["action_note"]) == 0  # an action nobody performed is 0, never absent


async def test_columns_are_fixed_and_isolation_holds_on_an_empty_board(env) -> None:
    """A cluster with no triage history still answers a full header — a spreadsheet built on
    this file must not lose its columns in a quiet window. Doubles as the tenant check: the
    other cluster's rows are seeded and must not appear here."""
    login, client = env
    loud = f"c-cexp-{uuid.uuid4().hex[:8]}"
    quiet = f"c-cexp-{uuid.uuid4().hex[:8]}"
    await _seed_finding(client, loud, "fk-loud", first_seen=datetime.now(UTC) - timedelta(days=1))
    await _journal(client, loud, f"ana-{uuid.uuid4().hex[:6]}", "fk-loud", "resolve")
    await client.indices.refresh(index="system-audit-log-*")

    http = await login()
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": quiet})
    assert r.status_code == 200
    lines = r.text.splitlines()
    assert lines[0].split(",") == list(CONTRIBUTORS_CSV_COLUMNS)
    assert len(lines) == 1  # header only — no rows, and none of `loud`'s (SEC-4)
    assert "fk-loud" not in r.text


async def test_over_the_row_cap_is_413_with_the_ops_parity_pair(env, monkeypatch) -> None:
    """The cap is a backstop here, not a hot guard: the board is bounded by its own terms-agg
    size, so this only fires under a deliberately low setting — which is exactly how it is driven.

    Ops parity (the bounded-endpoint rule): the 413 logs a warning AND bumps LIMIT_REJECTIONS.
    """
    login, client = env
    cid = f"c-cexp-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    for i in range(3):
        await _seed_finding(client, cid, f"fk-{i}", first_seen=now - timedelta(days=1))
        await _journal(client, cid, f"actor-{i}-{uuid.uuid4().hex[:6]}", f"fk-{i}", "resolve")
    await client.indices.refresh(index="system-audit-log-*")
    http = await login()

    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "2")  # 3 contributors > cap 2
    get_settings.cache_clear()
    before = LIMIT_REJECTIONS.labels("export_rows")._value.get()
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid})
    assert r.status_code == 413
    assert "inline export limit" in r.json()["title"]
    assert LIMIT_REJECTIONS.labels("export_rows")._value.get() == before + 1

    monkeypatch.setenv("JAVV_EXPORT_MAX_ROWS", "50")
    get_settings.cache_clear()
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    assert len(r.text.splitlines()) == 1 + 3


async def test_stream_counts_rows_and_bytes_in_its_finally(env) -> None:
    """M-4: what actually left the building is metered, header excluded from the row count."""
    login, client = env
    cid = f"c-cexp-{uuid.uuid4().hex[:8]}"
    await _seed_finding(client, cid, "fk-m", first_seen=datetime.now(UTC) - timedelta(days=1))
    await _journal(client, cid, f"ana-{uuid.uuid4().hex[:6]}", "fk-m", "resolve")
    await client.indices.refresh(index="system-audit-log-*")
    http = await login()

    rows_before = EXPORT_ROWS.labels("contributors_csv")._value.get()
    bytes_before = EXPORT_BYTES.labels("contributors_csv")._value.get()
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid})
    assert r.status_code == 200
    assert EXPORT_ROWS.labels("contributors_csv")._value.get() == rows_before + 1  # not 2
    assert EXPORT_BYTES.labels("contributors_csv")._value.get() == bytes_before + len(r.text)


async def test_window_is_honored_and_auth_and_as_of_ride_the_read_s_seam(env) -> None:
    """`days` scopes the file exactly as it scopes the screen; the export is session-auth like
    the read it mirrors; and a past `as_of` rides the SAME D28 seam as `GET /contributors`
    rather than the findings export's flat 501."""
    login, client = env
    cid = f"c-cexp-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    recent, ancient = f"now-{uuid.uuid4().hex[:6]}", f"old-{uuid.uuid4().hex[:6]}"
    await _seed_finding(client, cid, "fk-w", first_seen=now - timedelta(days=120))
    await _journal(client, cid, recent, "fk-w", "resolve")  # stamped now
    await _journal_at(client, cid, ancient, "fk-w", "resolve", now - timedelta(days=90))
    await client.indices.refresh(index="system-audit-log-*")
    http = await login()

    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid, "days": 365})
    actors = {row["actor"] for row in _rows(r.text)}
    assert actors == {recent, ancient}
    r = await http.get("/api/v1/contributors/export.csv", params={"cluster_id": cid, "days": 1})
    assert {row["actor"] for row in _rows(r.text)} == {recent}  # the 90d-old action drops out

    bare = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=http._transport.app),  # type: ignore[attr-defined]
        base_url="https://t",
    )
    r = await bare.get("/api/v1/contributors/export.csv", params={"cluster_id": cid})
    assert r.status_code == 401
    await bare.aclose()

    json_at_t = await http.get(
        "/api/v1/contributors", params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00Z"}
    )
    csv_at_t = await http.get(
        "/api/v1/contributors/export.csv",
        params={"cluster_id": cid, "as_of": "2026-01-01T00:00:00Z"},
    )
    assert csv_at_t.status_code == json_at_t.status_code  # one seam, not two
