"""Hardened ingest route: auth, scope binding, caps, zip bomb, and the golden round-trip
(real OpenSearch, guarded) — a real scanner envelope through the ACTUAL ingest path."""

import gzip
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from opensearchpy import AsyncOpenSearch, NotFoundError

from backend.core.metrics import INGEST_FAILURES_UNRECORDED, INGEST_REJECTED
from backend.core.security import hash_token, mint_token
from backend.core.settings import get_settings
from backend.main import create_app
from backend.repositories.bulk import BulkError
from backend.routers import ingest as ingest_mod
from os_env import OS_URL, requires_opensearch

GOLDEN = (Path(__file__).parent / "fixtures/envelope-trivy-golden.json").read_text()
CLUSTER = json.loads(GOLDEN)["cluster_id"]
GOLDEN_ORDER = json.loads(GOLDEN)["scan_order"]
PEPPER = get_settings().secret_key


class FakeOS:
    """Token lookup + write capture, no OpenSearch."""

    def __init__(self, token_doc: dict[str, Any] | None):
        self.token_doc = token_doc
        self.bulks: list[list[dict[str, Any]]] = []
        self.updates: list[dict[str, Any]] = []
        self.indexes: list[dict[str, Any]] = []
        self.ubqs: list[dict[str, Any]] = []
        self.indices = _FakeIndices()

    async def search(self, **kw: Any) -> dict[str, Any]:
        if "system-tokens" in str(kw.get("index", "")):
            hits = [{"_id": "t1", "_source": self.token_doc}] if self.token_doc else []
            return {"hits": {"hits": hits}}
        # findings / scan-events lookups (D5a recompute, D5b catalog read) — nothing seeded
        return {"hits": {"hits": []}}

    async def bulk(self, body: list[dict[str, Any]]) -> dict[str, Any]:
        self.bulks.append(body)
        return {"errors": False, "items": [{"index": {"status": 201}}] * (len(body) // 2)}

    async def update(self, **kw: Any) -> dict[str, Any]:
        self.updates.append(kw)
        return {}

    async def get(self, **kw: Any) -> dict[str, Any]:
        if kw.get("index") == "javv-scan-orders":  # the order the golden cycle was handed
            return {"_source": {"max_allocated_scan_order": GOLDEN_ORDER}}
        raise NotFoundError(404, "not_found", {})  # first commit: watermark doc absent

    async def index(self, **kw: Any) -> dict[str, Any]:
        self.indexes.append(kw)  # watermark CAS write (op_type=create on first commit)
        return {"_id": kw.get("id")}

    async def update_by_query(self, **kw: Any) -> dict[str, Any]:
        self.ubqs.append(kw)  # reconcile-on-commit — nothing absent in a single-envelope test
        return {"updated": 0, "version_conflicts": 0}


class _FakeIndices:
    async def refresh(self, **_: Any) -> dict[str, Any]:
        return {}

    async def exists_alias(self, **_: Any) -> bool:
        return True  # write alias already ensured (M4/n-2) — creation paths are test_aliases.py


def app_with(fake: FakeOS) -> httpx.AsyncClient:
    app = create_app()
    app.state.opensearch = fake
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


def token_doc(token: str, cluster: str = CLUSTER, scanner: str = "trivy") -> dict[str, Any]:
    return {
        "token_hash": hash_token(token, pepper=PEPPER),
        "cluster_id": cluster,
        "scanner": scanner,
        "disabled": False,
    }


def gz(payload: str) -> bytes:
    return gzip.compress(payload.encode())


def post(client: httpx.AsyncClient, body: bytes, token: str, **hdrs: str) -> Any:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        **hdrs,
    }
    return client.post("/api/v1/ingest/scan", content=body, headers=headers)


async def test_happy_path_writes_in_commit_then_cache_order() -> None:
    t = mint_token()
    fake = FakeOS(token_doc(t))
    async with app_with(fake) as c:
        r = await post(c, gz(GOLDEN), t)
    assert r.status_code == 202 and r.json()["findings"] == 29
    # images → occurrences → scan-events commit → findings (D39: appends BEFORE the catalog doc,
    # cache last; the occurrence snapshot landed between images and commit in M8a slice 1)
    assert len(fake.bulks) == 4
    assert fake.bulks[0][0]["index"]["_index"].startswith(f"javv-images-{CLUSTER}")
    assert fake.bulks[1][0]["index"]["_index"].startswith(f"javv-finding-occurrences-{CLUSTER}")
    assert len(fake.bulks[1]) == 2 * 29  # one (action, row) pair per finding
    assert fake.bulks[2][0]["index"]["_index"].startswith(f"javv-scan-events-{CLUSTER}")
    # findings are scripted-merge updates (D31 + M-1 guard) — update ops, never full index
    assert fake.bulks[3][0]["update"]["_index"] == "findings"
    fields = fake.bulks[3][1]["script"]["params"]["f"]
    assert "state" not in fields  # human fields never in the scanner-field params
    assert fake.updates[0]["body"]["doc"]["last_ingest_at"]  # scanner-down guard stamped
    assert fake.updates[0]["params"] == {"retry_on_conflict": "3"}  # racing pushes self-resolve


async def test_last_ingest_stamp_conflict_never_fails_a_committed_ingest() -> None:
    """Found by the #117 bench: two same-token pushes racing the `last_ingest_at` update threw
    ConflictError AFTER commit → 500 → pointless scanner retry. The stamp is best-effort
    bookkeeping (a concurrent racer just wrote a fresher timestamp); the accepted ingest wins."""
    from opensearchpy.exceptions import ConflictError

    class ConflictingOS(FakeOS):
        async def update(self, **kw: Any) -> dict[str, Any]:
            raise ConflictError(409, "version_conflict_engine_exception", {})

    t = mint_token()
    async with app_with(ConflictingOS(token_doc(t))) as c:
        r = await post(c, gz(GOLDEN), t)
    assert r.status_code == 202  # committed data is reported committed, conflict or not


async def test_an_order_scan_runs_never_handed_out_writes_nothing() -> None:
    t = mint_token()
    fake = FakeOS(token_doc(t))
    made_up = {**json.loads(GOLDEN), "scan_order": 2**63 - 1}
    async with app_with(fake) as c:
        r = await post(c, gz(json.dumps(made_up)), t)
    assert r.status_code == 422
    assert fake.bulks == [] and fake.updates == []  # no data, no counter, no catalog moved


async def test_missing_or_unknown_token_is_generic_401() -> None:
    async with app_with(FakeOS(None)) as c:
        r1 = await c.post("/api/v1/ingest/scan", content=b"x")
        r2 = await post(c, gz(GOLDEN), mint_token())
    assert r1.status_code == 401 and r2.status_code == 401  # same generic answer for both


async def test_token_scope_binding_is_enforced() -> None:
    t = mint_token()
    async with app_with(FakeOS(token_doc(t, scanner="grype"))) as c:
        r = await post(c, gz(GOLDEN), t)  # golden is trivy — cross-scanner push forbidden
    assert r.status_code == 403


async def test_disabled_token_rejected() -> None:
    t = mint_token()
    doc = {**token_doc(t), "disabled": True}
    async with app_with(FakeOS(doc)) as c:
        assert (await post(c, gz(GOLDEN), t)).status_code == 401


async def test_expired_token_rejected() -> None:
    t = mint_token()
    doc = {**token_doc(t), "expiry": "2020-01-01T00:00:00+00:00"}  # long past (m-3)
    async with app_with(FakeOS(doc)) as c:
        assert (await post(c, gz(GOLDEN), t)).status_code == 401


async def test_the_rate_cap_is_a_real_429_over_http(monkeypatch: Any) -> None:
    """Ingest's 429 had NO test — the only rate-limit case here poked the module's internals, and
    those moved to `core/rate_limit.py` (516). The eviction properties are unit-tested there; what
    belongs at this level is that the cap still reaches the wire, which a direct call cannot show.
    It also pins the setup: a leftover private copy would let the second push through."""
    from backend.routers import ingest as mod

    monkeypatch.setattr(get_settings(), "ingest_rate_limit_per_minute", 1, raising=False)
    mod._limiter.reset()  # module-level per pod, so tests would inherit each other's budget
    t = mint_token()
    try:
        async with app_with(FakeOS(token_doc(t))) as c:
            assert (await post(c, gz(GOLDEN), t)).status_code == 202
            assert (await post(c, gz(GOLDEN), t)).status_code == 429  # same token hash, same key
    finally:
        mod._limiter.reset()


async def test_zip_bomb_is_rejected_413() -> None:
    t = mint_token()
    bomb = gzip.compress(b"0" * (70 * 1024 * 1024))  # tiny wire, huge inflate
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, gz("x") * 0 + bomb, t)).status_code == 413


async def test_extra_field_envelope_is_422() -> None:
    t = mint_token()
    tampered = json.dumps({**json.loads(GOLDEN), "extra": 1})
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, gz(tampered), t)).status_code == 422


async def test_garbage_gzip_is_400() -> None:
    t = mint_token()
    async with app_with(FakeOS(token_doc(t))) as c:
        assert (await post(c, b"not-gzip", t)).status_code == 400


# --- golden round-trip: real OpenSearch (guarded) ---------------------------


@requires_opensearch
async def test_golden_envelope_round_trip_against_real_opensearch() -> None:
    from backend.core.bootstrap import bootstrap
    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    env = IngestEnvelope.model_validate(
        {**json.loads(GOLDEN), "scan_run_id": f"rt-{uuid.uuid4().hex[:8]}"}
    )
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        await bootstrap(client)  # findings + templates must exist (fresh CI)
        written = await ingest_envelope(client, env)
        assert written == 29
        await client.indices.refresh(index=f"findings,javv-scan-events-{env.cluster_id}-*")
        hits = await client.search(
            index="findings",
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"cluster_id": env.cluster_id}},
                            {"term": {"namespaces": "javv-smoke"}},  # array-contains ns filter
                            {"term": {"severity": "critical"}},  # lc normalizer folds CRITICAL
                        ]
                    }
                },
                "size": 0,
            },
        )
        assert hits["hits"]["total"]["value"] > 0  # raw preserved, normalized searchable
        ev = await client.search(
            index=f"javv-scan-events-{env.cluster_id}-*",
            body={"query": {"term": {"scan_run_id": env.scan_run_id}}},
            params={"expand_wildcards": "all"},
        )
        assert ev["hits"]["total"]["value"] == 1  # the commit doc landed
    finally:
        await client.close()


async def test_oversized_compressed_body_is_413_even_with_lying_header() -> None:
    t = mint_token()
    big = b"\x1f\x8b" + b"0" * (11 * 1024 * 1024)  # 11 MiB on the wire (> 10 MiB cap)
    async with app_with(FakeOS(token_doc(t))) as c:
        r = await post(c, big, t)
    assert r.status_code == 413


@requires_opensearch
async def test_repush_is_idempotent_counts_stay_stable() -> None:
    from backend.models.envelope import IngestEnvelope
    from backend.services.ingest import ingest_envelope

    # unique digest + run id so this test owns its finding_keys and watermark on the shared real
    # index — otherwise a prior golden ingest's watermark makes the re-push a no-op (M-1 guard)
    env = IngestEnvelope.model_validate(
        {
            **json.loads(GOLDEN),
            "scan_run_id": f"idem-{uuid.uuid4().hex[:8]}",
            "image_digest": f"sha256:{uuid.uuid4().hex}{uuid.uuid4().hex}",
        }
    )
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        from backend.core.bootstrap import bootstrap

        await bootstrap(client)  # findings must exist (fresh CI)
        q = {"query": {"term": {"last_scan_run_id": env.scan_run_id}}}
        await ingest_envelope(client, env)
        await client.indices.refresh(index="findings")
        first = (await client.count(index="findings", body=q))["count"]
        await ingest_envelope(client, env)  # same envelope again — deterministic _ids
        await client.indices.refresh(index="findings")
        second = (await client.count(index="findings", body=q))["count"]
        assert first == second == 29  # re-push overwrote, never duplicated
    finally:
        await client.close()


# --- ops parity (issue 523): which rejections log, and which only count ----------------------


@pytest.fixture
def captured(monkeypatch: Any):
    """The route's logger, wired straight to a capture. `capture_logs` swaps the GLOBAL config,
    and `app_with` → `create_app()` → `configure_logging()` swaps it back mid-test, so a logger
    that owns its processor chain is the one that survives building the app inside the test."""
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(ingest_mod, "log", structlog.wrap_logger(None, processors=[capture]))
    return capture.entries


def _rejections(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in logs if e["event"] == "ingest rejected"]


def _count(reason: str) -> float:
    return INGEST_REJECTED.labels(reason=reason)._value.get()


async def test_a_401_is_counted_but_never_logged(captured: Any) -> None:
    """An unauthenticated sender reaches 401 with no budget at all, so a line per request would
    let it choose our log volume. The metric still counts every one."""
    before = _count("bad_token")
    async with app_with(FakeOS(None)) as c:
        await c.post("/api/v1/ingest/scan", content=b"x")
        await post(c, gz(GOLDEN), mint_token())
    assert _count("bad_token") == before + 2
    assert _rejections(captured) == []


async def test_a_429_logs_once_per_key_per_window(captured: Any, monkeypatch: Any) -> None:
    """The rate limit runs before the token is verified, so the key is anything a sender puts in
    the header. One hammered key logs its first 429 in a window, never one line per request."""
    monkeypatch.setattr(get_settings(), "ingest_rate_limit_per_minute", 1, raising=False)
    ingest_mod._limiter.reset()
    ingest_mod._rate_limit_warned.reset()
    before = _count("rate_limited")
    t = mint_token()
    try:
        async with app_with(FakeOS(token_doc(t))) as c:
            assert (await post(c, gz(GOLDEN), t)).status_code == 202
            for _ in range(3):
                assert (await post(c, gz(GOLDEN), t)).status_code == 429
    finally:
        ingest_mod._limiter.reset()
        ingest_mod._rate_limit_warned.reset()
    assert _count("rate_limited") == before + 3
    [line] = _rejections(captured)
    assert (line["log_level"], line["reason"], line["status"]) == ("warning", "rate_limited", 429)
    assert "failure_id" not in line  # pre-token: nothing is recorded, so there's no row to name


# every rejection past the token check: (case, status, metric reason)
POST_AUTH_REJECTIONS = [
    ("zip_bomb", 413, "too_large"),
    ("oversized_wire", 413, "too_large"),
    ("bad_gzip", 400, "bad_gzip"),
    ("bad_json", 400, "bad_json"),
    ("deep_nesting", 400, "bad_json"),
    ("extra_field", 422, "invalid_envelope"),
    ("wrong_scanner", 403, "scope_mismatch"),
    ("unallocated_order", 422, "unallocated_order"),
    ("mapping_refused", 422, "invalid_envelope"),
    ("storage_down", 503, "storage_error"),
]


def _rejected_push(case: str, t: str, monkeypatch: Any) -> tuple[dict[str, Any], bytes]:
    """The token doc and body for one POST_AUTH_REJECTIONS case (storage_down patches ingest)."""
    doc = token_doc(t, scanner="grype") if case == "wrong_scanner" else token_doc(t)
    body = {
        "zip_bomb": gzip.compress(b"0" * (70 * 1024 * 1024)),
        "oversized_wire": b"\x1f\x8b" + b"0" * (11 * 1024 * 1024),
        "bad_gzip": b"not-gzip",
        "bad_json": gz("{not json"),
        # valid JSON nested past the decoder's recursion limit: a RecursionError, not a decode error
        "deep_nesting": gz('{"a":' * 100_000 + "1" + "}" * 100_000),
        "extra_field": gz(json.dumps({**json.loads(GOLDEN), "extra": 1})),
        "wrong_scanner": gz(GOLDEN),
        "storage_down": gz(GOLDEN),
        # an order scan-runs never handed out (made up, or from a poisoned pusher)
        "unallocated_order": gz(json.dumps({**json.loads(GOLDEN), "scan_order": GOLDEN_ORDER + 1})),
        "mapping_refused": gz(GOLDEN),
    }[case]
    if case == "mapping_refused":

        async def _refused(*_: Any, **__: Any) -> int:
            raise BulkError([{"status": 400, "error": {"type": "mapper_parsing_exception"}}])

        monkeypatch.setattr(ingest_mod, "ingest_envelope", _refused)
    if case == "storage_down":

        async def _fail(*_: Any, **__: Any) -> int:
            raise BulkError([{"index": {"status": 503}}])

        monkeypatch.setattr(ingest_mod, "ingest_envelope", _fail)
    return doc, body


@pytest.mark.parametrize(("case", "status", "reason"), POST_AUTH_REJECTIONS)
async def test_every_rejection_after_the_token_check_logs_a_warning(
    captured: Any, monkeypatch: Any, case: str, status: int, reason: str
) -> None:
    """Past the token check a sender is authenticated and already rate-limited per token, so a
    warning per rejection is bounded and tells the operator which cluster's scanner misbehaves."""
    t = mint_token()
    doc, body = _rejected_push(case, t, monkeypatch)
    before = _count(reason)
    async with app_with(FakeOS(doc)) as c:
        assert (await post(c, body, t)).status_code == status
    assert _count(reason) == before + 1
    [line] = _rejections(captured)
    assert (line["log_level"], line["reason"], line["status"]) == ("warning", reason, status)
    # the token's scope names whose scanner this is; the token itself is never logged
    assert (line["cluster_id"], line["scanner"]) == (doc["cluster_id"], doc["scanner"])
    assert t not in repr(line) and doc["token_hash"] not in repr(line)
    if case == "wrong_scanner":
        assert line["payload_scanner"] == "trivy"
    if case == "extra_field":
        assert line["errors"] >= 1


# --- failed-ingest records (issue 357) -------------------------------------------------------


def _failure_writes(fake: FakeOS) -> list[dict[str, Any]]:
    return [w for w in fake.indexes if str(w["index"]).startswith("javv-ingest-failures-")]


GOLDEN_IMAGE = json.loads(GOLDEN)["image_ref"]
STAGE = {
    "too_large": "receive",
    "bad_gzip": "decode",
    "bad_json": "decode",
    "invalid_envelope": "validate",
    "unallocated_order": "validate",
    "scope_mismatch": "authorize",
    "storage_error": "store",
}


@pytest.mark.parametrize(("case", "status", "reason"), POST_AUTH_REJECTIONS)
async def test_every_rejection_after_the_token_check_is_recorded_under_the_tokens_scope(
    captured: Any, monkeypatch: Any, case: str, status: int, reason: str
) -> None:
    t = mint_token()
    doc, body = _rejected_push(case, t, monkeypatch)
    fake = FakeOS(doc)
    async with app_with(fake) as c:
        r = await post(c, body, t)
    assert r.status_code == status
    [write] = _failure_writes(fake)
    rec = write["body"]
    # routed on the TOKEN's scope: the wrong_scanner payload claims trivy, the token is grype
    assert write["index"] == f"javv-ingest-failures-{doc['cluster_id']}"
    assert (rec["cluster_id"], rec["scanner"]) == (doc["cluster_id"], doc["scanner"])
    assert (rec["reason"], rec["status"], rec["stage"]) == (reason, status, STAGE[reason])
    assert write["id"] == rec["failure_id"]
    # the warning names the record it produced: a table row and its log line join on this id
    [line] = _rejections(captured)
    assert line["failure_id"] == rec["failure_id"]
    assert t not in repr(rec) and doc["token_hash"] not in repr(rec)
    # the image is known once the body parsed as an object; before that it is honestly absent
    parsed_as_object = case in (
        "extra_field",
        "wrong_scanner",
        "storage_down",
        "unallocated_order",
        "mapping_refused",
    )
    assert rec["image_ref"] == (GOLDEN_IMAGE if parsed_as_object else None)
    if case == "extra_field":  # the first validation error names its location, never the input
        assert rec["error"] == "envelope rejected: 1 error(s); first: extra: extra_forbidden"
    elif case == "mapping_refused":  # the store's error type, which the response leaves out
        assert rec["error"] == "the store refused a field: mapper_parsing_exception"
    else:
        assert rec["error"] == r.json()["title"]  # the text the scanner itself was sent


async def test_unauthenticated_rejections_record_nothing(monkeypatch: Any) -> None:
    """A write per anonymous request would let a sender choose our write volume: the 401 and
    the pre-token 429 only count."""
    monkeypatch.setattr(get_settings(), "ingest_rate_limit_per_minute", 1, raising=False)
    ingest_mod._limiter.reset()
    t = mint_token()
    fake = FakeOS(token_doc(t))
    try:
        async with app_with(fake) as c:
            assert (await c.post("/api/v1/ingest/scan", content=b"x")).status_code == 401
            assert (await post(c, gz(GOLDEN), mint_token())).status_code == 401
            assert (await post(c, gz(GOLDEN), t)).status_code == 202
            assert (await post(c, gz(GOLDEN), t)).status_code == 429
    finally:
        ingest_mod._limiter.reset()
        ingest_mod._rate_limit_warned.reset()
    assert _failure_writes(fake) == []


class _RecordingBroken(FakeOS):
    async def index(self, **kw: Any) -> dict[str, Any]:
        if str(kw["index"]).startswith("javv-ingest-failures-"):
            raise ConnectionError("failures index unreachable")
        return await super().index(**kw)


@pytest.mark.parametrize(("case", "status", "reason"), POST_AUTH_REJECTIONS)
async def test_a_failed_record_leaves_the_rejection_byte_identical(
    monkeypatch: Any, case: str, status: int, reason: str
) -> None:
    """Bookkeeping on a decided rejection must never turn it into something else (a 500)."""
    t = mint_token()
    doc, body = _rejected_push(case, t, monkeypatch)
    # one request id for both: the body carries it (issue 644), and it's the only per-request part
    async with app_with(FakeOS(doc)) as c:
        recorded = await post(c, body, t, **{"X-Request-ID": "record-check"})
    missed = INGEST_FAILURES_UNRECORDED.labels(reason=reason)
    before = missed._value.get()
    async with app_with(_RecordingBroken(doc)) as c:
        unrecorded = await post(c, body, t, **{"X-Request-ID": "record-check"})
    assert unrecorded.status_code == recorded.status_code == status
    assert unrecorded.content == recorded.content
    assert missed._value.get() == before + 1  # the miss is counted, not just logged
