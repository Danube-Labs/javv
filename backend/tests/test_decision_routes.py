"""M5c decision routes (FR-8/SEC-2) — the HTTP layer over decisions/lifecycle + projection.

Pins: risk-accept and ignore_rule (which projects risk_accepted) need `can_accept_audit_final` on
CREATE, on an EDIT that would produce one (no smuggling), and on an EDIT or REVOKE of one (an undo,
issue 892); a plain `can_triage` holder creates, edits and revokes not_affected;
double-revoke → 409; empty edit → 422; the list read REQUIRES `cluster_id` (tenant read path
discipline) and paginates. Real OpenSearch — same fixture family as test_admin_users."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from opensearchpy import AsyncOpenSearch

from backend.auth.passwords import hash_password
from backend.core.errors import EXPIRY_PASSED_TYPE
from backend.decisions.lifecycle import DECISIONS_INDEX
from backend.main import create_app
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch

PASSWORD = "route-test-password-1"
CID = "c-decision-routes"


@pytest.fixture
async def env():
    client = AsyncOpenSearch(hosts=[OS_URL])
    app = create_app()
    app.state.opensearch = client
    transport = httpx.ASGITransport(app=app)
    jars: list[httpx.AsyncClient] = []

    async def login_with(capabilities: list[str]) -> httpx.AsyncClient:
        username = f"u-{uuid.uuid4().hex[:12]}"
        await client.index(
            index="system-users",
            id=username,
            body={
                "username": username,
                "password_hash": hash_password(PASSWORD),
                "role": "custom",
                "capabilities": capabilities,
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

    yield login_with, client
    for http in jars:
        await http.aclose()
    await client.close()


def _from_now(**delta: float) -> str:
    return (datetime.now(UTC).replace(microsecond=0) + timedelta(**delta)).isoformat()


def _utc_day(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).date().isoformat()


def _body(**over) -> dict:
    body = {
        "type": "not_affected",
        "cve_id": f"CVE-{uuid.uuid4().hex[:8]}",
        "scope": {"namespaces": [], "images": []},
        "apply_both_scanners": True,
        "justification": "route test",
        "cluster_id": CID,
        **over,
    }
    if body["type"] == "not_affected" and "vex_justification" not in over:
        body["vex_justification"] = "component_not_present"  # the CISA five it requires
    return body


async def test_accept_types_need_accept_final_on_create_and_edit(env) -> None:
    login_with, _ = env
    triager = await login_with(["can_triage"])

    for kind in ("risk_accepted", "ignore_rule"):  # ignore_rule: issue 892 ruling 5
        r = await triager.post("/api/v1/decisions", json=_body(type=kind, vex_justification=None))
        assert r.status_code == 403, kind  # SEC-2

    r = await triager.post("/api/v1/decisions", json=_body())
    assert r.status_code == 201
    decision_id = r.json()["decision"]["decision_id"]

    # an EDIT flipping the type to an accept type is the smuggling arm — same gate
    for kind in ("risk_accepted", "ignore_rule"):
        r = await triager.patch(
            f"/api/v1/decisions/{decision_id}", json={"type": kind, "vex_justification": None}
        )
        assert r.status_code == 403, kind

    lead = await login_with(["can_triage", "can_accept_audit_final"])
    r = await lead.post(
        "/api/v1/decisions", json=_body(type="risk_accepted", vex_justification=None)
    )
    assert r.status_code == 201


@pytest.mark.parametrize("kind", ["risk_accepted", "ignore_rule"])
async def test_undoing_an_accept_type_needs_accept_final(env, kind) -> None:
    """issue 892 ruling 1: a triager cannot undo what only a lead may make — no revoke, and no
    edit of any field (an edit is revoke + create), even to a type the triager may create."""
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    triager = await login_with(["can_triage"])
    made = (
        await lead.post("/api/v1/decisions", json=_body(type=kind, vex_justification=None))
    ).json()["decision"]
    path = f"/api/v1/decisions/{made['decision_id']}"

    r = await triager.post(f"{path}/revoke")
    assert r.status_code == 403
    r = await triager.patch(
        path, json={"type": "not_affected", "vex_justification": "component_not_present"}
    )
    assert r.status_code == 403
    r = await triager.patch(path, json={"justification": "narrowed"})
    assert r.status_code == 403
    listed = await lead.get(
        "/api/v1/decisions",
        params={"cluster_id": CID, "cve_id": made["cve_id"], "include_revoked": True},
    )
    # still one active decision: the refusals revoked nothing and created nothing
    assert [d["revoked_at"] for d in listed.json()["decisions"]] == [None]

    # the lead may still change it: an edit of the justification alone keeps the type
    r = await lead.patch(path, json={"justification": "narrowed by the lead"})
    assert r.status_code == 200
    assert r.json()["decision"]["type"] == kind
    assert (
        await lead.post(f"/api/v1/decisions/{r.json()['decision']['decision_id']}/revoke")
    ).status_code == 200


async def test_revoke_translates_conflicts_and_unknowns(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    made = (await http.post("/api/v1/decisions", json=_body())).json()["decision"]

    assert (await http.post(f"/api/v1/decisions/{made['decision_id']}/revoke")).status_code == 200
    assert (await http.post(f"/api/v1/decisions/{made['decision_id']}/revoke")).status_code == 409
    assert (await http.post("/api/v1/decisions/nope/revoke")).status_code == 404


async def test_edit_validations(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    made = (await http.post("/api/v1/decisions", json=_body())).json()["decision"]

    r = await http.patch(f"/api/v1/decisions/{made['decision_id']}", json={})
    assert r.status_code == 422  # empty edit
    r = await http.patch(f"/api/v1/decisions/{made['decision_id']}", json={"nope": 1})
    assert r.status_code == 422  # extra=forbid
    r = await http.patch(
        f"/api/v1/decisions/{made['decision_id']}", json={"justification": "narrowed"}
    )
    assert r.status_code == 200
    got = r.json()
    assert got["revoked"]["revoked_at"] is not None
    assert got["decision"]["justification"] == "narrowed"


async def test_list_requires_cluster_and_paginates(env) -> None:
    login_with, _ = env
    http = await login_with(["can_triage"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    for _ in range(3):
        assert (await http.post("/api/v1/decisions", json=_body(cve_id=cve))).status_code == 201

    assert (await http.get("/api/v1/decisions")).status_code == 422  # cluster_id REQUIRED

    r = await http.get("/api/v1/decisions", params={"cluster_id": CID, "cve_id": cve, "size": 2})
    assert r.status_code == 200
    got = r.json()
    assert got["total"] == 3 and len(got["decisions"]) == 2
    r2 = await http.get(
        "/api/v1/decisions", params={"cluster_id": CID, "cve_id": cve, "size": 2, "offset": 2}
    )
    assert len(r2.json()["decisions"]) == 1


async def test_invalid_decision_inputs_return_422_not_500(env) -> None:
    """Audit #185: bad request shapes are client errors at the door — a not_affected decision
    without a CISA justification (A-M2), garbage expiry (A-m7), and an over-long list `cve_id`
    query (A-n) must 422, never 500 or a polluted projection."""
    login_with, _ = env
    http = await login_with(["can_triage"])

    r = await http.post(
        "/api/v1/decisions", json=_body(type="not_affected", vex_justification=None)
    )
    assert r.status_code == 422  # A-M2: not_affected needs a justification
    r = await http.post(
        "/api/v1/decisions",
        json=_body(type="not_affected", vex_justification="component_not_present", expiry="banana"),
    )
    assert r.status_code == 422  # A-m7: expiry must be ISO-8601, not free text
    r = await http.get("/api/v1/decisions", params={"cluster_id": CID, "cve_id": "x" * 5000})
    assert r.status_code == 422  # A-n: bounded query string


async def test_approvals_include_and_exclude_of_the_same_field_422(env) -> None:
    """issue 349 review: same contract as the findings edge — a field is included OR excluded,
    never both; the conflict is a 422, not a silent zero-row queue."""
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    r = await lead.get(
        "/api/v1/decisions/approvals",
        params={"cluster_id": CID, "status": "expiring", "exclude_status": "expiring"},
    )
    assert r.status_code == 422
    assert "mutually exclusive" in r.json()["title"]  # RFC 9457: detail → title
    # opposite fields compose — one included, another excluded, is a legitimate lens
    r = await lead.get(
        "/api/v1/decisions/approvals",
        params={"cluster_id": CID, "status": "active", "exclude_scanner": "trivy"},
    )
    assert r.status_code == 200


async def test_create_refuses_an_expiry_that_has_passed(env) -> None:
    """issue 984: a decision that expires before it is made has no effect, while the screens
    list it. A date passes at 00:00 UTC on that day, so today is refused too."""
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    for expiry in (_utc_day(-21), _utc_day(0), _from_now(minutes=-1)):
        r = await lead.post(
            "/api/v1/decisions",
            json=_body(type="risk_accepted", vex_justification=None, expiry=expiry),
        )
        assert (r.status_code, r.json()["type"]) == (422, EXPIRY_PASSED_TYPE), expiry
        assert expiry not in r.text  # a refusal does not echo the value (issue 842)
    for expiry in (_utc_day(1), _from_now(minutes=5), None):
        r = await lead.post(
            "/api/v1/decisions",
            json=_body(type="risk_accepted", vex_justification=None, expiry=expiry),
        )
        assert r.status_code == 201, expiry


async def test_the_expiry_check_comes_after_the_capability_check(env) -> None:
    login_with, _ = env
    triager = await login_with(["can_triage"])
    r = await triager.post(
        "/api/v1/decisions",
        json=_body(type="risk_accepted", vex_justification=None, expiry=_utc_day(-1)),
    )
    assert r.status_code == 403


async def test_edit_refuses_a_result_whose_expiry_has_passed(env) -> None:
    """issue 984: an edit is revoke + create, and the new decision takes the old expiry unless
    the edit sets one. An edit to a past date, or an edit that keeps a date that has passed,
    would make a dead decision and revoke the live one."""
    login_with, client = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    created = await lead.post(
        "/api/v1/decisions",
        json=_body(type="risk_accepted", vex_justification=None, expiry=_utc_day(30)),
    )
    decision_id = created.json()["decision"]["decision_id"]

    r = await lead.patch(f"/api/v1/decisions/{decision_id}", json={"expiry": _utc_day(-1)})
    assert r.status_code == 422

    # the decision expires while it stands: an edit of its reason alone keeps the past date
    await client.update(
        index=DECISIONS_INDEX,
        id=decision_id,
        body={"doc": {"expiry": _utc_day(-2)}},
        params={"refresh": "true"},
    )
    r = await lead.patch(f"/api/v1/decisions/{decision_id}", json={"justification": "still"})
    assert (r.status_code, r.json()["type"]) == (422, EXPIRY_PASSED_TYPE)
    doc = (await client.get(index=DECISIONS_INDEX, id=decision_id))["_source"]
    assert doc["revoked_at"] is None  # refused before anything was written

    # a new date renews it
    r = await lead.patch(f"/api/v1/decisions/{decision_id}", json={"expiry": _utc_day(14)})
    assert r.status_code == 200
    assert r.json()["decision"]["expiry"] == _utc_day(14)


async def test_an_edit_of_a_revoked_decision_stays_a_409(env) -> None:
    login_with, client = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    created = await lead.post(
        "/api/v1/decisions",
        json=_body(type="risk_accepted", vex_justification=None, expiry=_utc_day(30)),
    )
    decision_id = created.json()["decision"]["decision_id"]
    await lead.post(f"/api/v1/decisions/{decision_id}/revoke")
    await client.update(
        index=DECISIONS_INDEX,
        id=decision_id,
        body={"doc": {"expiry": _utc_day(-2)}},
        params={"refresh": "true"},
    )
    r = await lead.patch(f"/api/v1/decisions/{decision_id}", json={"justification": "again"})
    assert r.status_code == 409


async def test_approval_list_is_accept_final_only_and_sorted_by_expiry(env) -> None:
    """M5d ruling (#30): the approval list = review queue over ACTIVE risk-accepts (creation is
    already SEC-2-gated — there is no pending state), soonest-expiring first."""
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    cve = f"CVE-{uuid.uuid4().hex[:8]}"
    # #203: a UNIQUE cluster per run — /approvals is size-capped and has no cve filter, so on the
    # shared module CID the decisions other tests leave behind (this index is not prefix-isolated)
    # accumulate and page this test's own rows out. A fresh cluster scopes the query to just ours.
    cid = f"c-appr-{uuid.uuid4().hex[:8]}"
    # relative to now: the create route refuses an expiry that has passed (issue 984)
    late = _body(type="risk_accepted", cve_id=cve, cluster_id=cid, expiry=_from_now(days=800))
    soon = _body(type="risk_accepted", cve_id=cve, cluster_id=cid, expiry=_from_now(days=40))
    for body in (late, soon):
        assert (await lead.post("/api/v1/decisions", json=body)).status_code == 201
    revoked = (
        await lead.post(
            "/api/v1/decisions", json=_body(type="risk_accepted", cve_id=cve, cluster_id=cid)
        )
    ).json()["decision"]
    await lead.post(f"/api/v1/decisions/{revoked['decision_id']}/revoke")

    triager = await login_with(["can_triage"])
    assert (
        await triager.get("/api/v1/decisions/approvals", params={"cluster_id": cid})
    ).status_code == 403  # accept_final holders only

    r = await lead.get("/api/v1/decisions/approvals", params={"cluster_id": cid})
    assert r.status_code == 200
    ours = [a for a in r.json()["approvals"] if a["cve_id"] == cve]
    assert len(ours) == 2  # the revoked one is out
    assert [a["expiry"] for a in ours] == [soon["expiry"], late["expiry"]]  # soonest first


async def _accept(client: AsyncOpenSearch, cid: str, approver: str, expiry: str) -> None:
    await client.index(
        index=DECISIONS_INDEX,
        body={
            "decision_id": f"d-{uuid.uuid4().hex}",
            "type": "risk_accepted",
            "cve_id": f"CVE-{uuid.uuid4().hex[:8]}",
            "cluster_id": cid,
            "created_by": approver,
            "expiry": expiry,
            "apply_both_scanners": True,
        },
    )


async def test_the_approver_search_finds_an_approver_past_the_top_32(env) -> None:
    """issue 1064: the Approver list stops at the 32 approvers with the most acceptances. The
    search finds an approver past them, in any case, with the count of the list. It sends no
    rows. A picked approver does not hide it; the status filter, with its warn_days, does."""
    login_with, client = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    cid = f"c-appr-{uuid.uuid4().hex[:8]}"
    busy = [f"u-busy-{i:02d}" for i in range(33)]
    quiet = "Svc-Payments-Lead"  # raw casing, not pre-folded
    for approver in busy:
        for _ in range(2):
            await _accept(client, cid, approver, _from_now(days=100))
    await _accept(client, cid, quiet, _from_now(days=5))
    await client.indices.refresh(index=DECISIONS_INDEX)

    r = await lead.get("/api/v1/decisions/approvals", params={"cluster_id": cid})
    listed = {b["key"] for b in r.json()["facets"]["created_by"]}
    assert len(listed) == 32 and quiet not in listed

    search = {"cluster_id": cid, "contains": "PAYMENTS"}
    r = await lead.get("/api/v1/decisions/approvals", params=search)
    assert r.status_code == 200
    assert r.json() == {"facets": {"created_by": [{"key": quiet, "count": 1}]}, "more": False}
    r = await lead.get("/api/v1/decisions/approvals", params={**search, "created_by": [busy[0]]})
    assert [b["key"] for b in r.json()["facets"]["created_by"]] == [quiet]
    # expiring in 5 days: inside a 7-day warn window, outside a 3-day one
    for warn_days, found in ((7, [quiet]), (3, [])):
        r = await lead.get(
            "/api/v1/decisions/approvals",
            params={**search, "status": ["expiring"], "warn_days": warn_days},
        )
        assert [b["key"] for b in r.json()["facets"]["created_by"]] == found

    r = await lead.get(
        "/api/v1/decisions/approvals", params={"cluster_id": cid, "contains": "busy"}
    )
    body = r.json()
    assert len(body["facets"]["created_by"]) == 32 and body["more"] is True


async def test_the_approver_search_is_accept_final_only_and_takes_2_to_128_characters(
    env,
) -> None:
    login_with, _ = env
    lead = await login_with(["can_triage", "can_accept_audit_final"])
    triager = await login_with(["can_triage"])
    cid = f"c-appr-{uuid.uuid4().hex[:8]}"
    r = await triager.get(
        "/api/v1/decisions/approvals", params={"cluster_id": cid, "contains": "le"}
    )
    assert r.status_code == 403
    for text in ("a", "a" * 129):
        r = await lead.get(
            "/api/v1/decisions/approvals", params={"cluster_id": cid, "contains": text}
        )
        assert r.status_code == 422, len(text)
    r = await lead.get(
        "/api/v1/decisions/approvals", params={"cluster_id": cid, "contains": "a" * 128}
    )
    assert r.json() == {"facets": {"created_by": []}, "more": False}
