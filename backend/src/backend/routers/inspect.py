"""Data inspector (#406) — a structurally read-only proxy to the store, never a passthrough.

The route validates every request against a hard allowlist (methods, path shapes, body keys)
BEFORE it touches OpenSearch; the UI renders whatever reason a rejection carries, verbatim.
Sensitive credential indices are denied outright — the console must never become a
password-hash or session-token dump. Every executed query is journaled first (D17/D32,
strict): this console can read every tenant's rows, so the trail is non-negotiable.
"""

import fnmatch
import hashlib
import json
import re
import time
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from opensearchpy.exceptions import TransportError
from pydantic import BaseModel, Field

from backend.audit.writer import append_auth_event
from backend.auth.capabilities import require_capability
from backend.auth.principal import Principal
from backend.core.metrics import LIMIT_REJECTIONS
from backend.core.settings import get_settings

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/admin/opensearch", tags=["inspect"])

CanInspect = Annotated[Principal, Depends(require_capability("can_inspect_store"))]

# global read facts — GET only, no body, no parameters beyond what we set server-side
_GLOBAL_PATHS = frozenset({"_cluster/health", "_cat/indices", "_cat/shards", "_nodes/stats"})
# The _cat reads list JAVV's own indices only. With no index they take in every index, including
# OpenSearch's security index, which JAVV's least-privilege role cannot read (issue 729).
_CAT_INDICES = "findings,javv-*,system-*,restored-*"
# per-index verbs and the methods each admits
_INDEX_VERBS: dict[str, frozenset[str]] = {
    "_search": frozenset({"GET", "POST"}),
    "_count": frozenset({"GET", "POST"}),
    "_mapping": frozenset({"GET"}),
}
# index expression: lowercase names/patterns only — never a leading underscore or a slash,
# so no API endpoint can be smuggled through the index position
_INDEX_EXPR = re.compile(r"^[a-z0-9*][a-z0-9*._,-]*$")
# credential material lives here — denied even to capability holders (hash/session dump risk).
# A snapshot restore writes each index back as `restored-<name>` (routers/data_settings.py), so
# the copies carry the same hashes and are denied by the same check (issue 892).
_CREDENTIAL_INDICES = ("system-users", "system-sessions", "system-tokens")
_SENSITIVE_INDICES = (*_CREDENTIAL_INDICES, *(f"restored-{name}" for name in _CREDENTIAL_INDICES))
# write/script/stateful surfaces have no read-only form — reject wherever they appear in a body
_FORBIDDEN_BODY_KEYS = frozenset({"script", "script_fields", "runtime_mappings", "pit", "scroll"})


class InspectRequest(BaseModel):
    model_config = {"extra": "forbid"}

    method: str = Field(pattern=r"^(GET|POST)$")
    path: str = Field(min_length=1, max_length=400)
    body: dict[str, Any] | None = None


def _reject(reason: str) -> HTTPException:
    return HTTPException(422, f"Rejected by the allowlist — {reason}")


def _forbidden_keys(node: Any) -> str | None:
    """Depth-first walk for forbidden keys anywhere in the body."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _FORBIDDEN_BODY_KEYS:
                return key
            if (found := _forbidden_keys(value)) is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            if (found := _forbidden_keys(item)) is not None:
                return found
    return None


def _touches_sensitive(expr: str) -> bool:
    """True if any comma-separated pattern in the expression could match a credential index."""
    for pattern in expr.split(","):
        for sensitive in _SENSITIVE_INDICES:
            if fnmatch.fnmatch(sensitive, pattern):
                return True
    return False


def _validate(req: InspectRequest) -> str:
    """The allowlist gate. Returns the normalized path; raises 422 with the verbatim reason."""
    path = req.path.strip().lstrip("/")
    if path in _GLOBAL_PATHS:
        if req.method != "GET":
            raise _reject(f'"{path}" admits GET only')
        if req.body is not None:
            raise _reject(f'"{path}" takes no body')
        return path
    parts = path.split("/")
    if len(parts) != 2:
        raise _reject('the path must be "<index>/<verb>" or one of the global read endpoints')
    expr, verb = parts
    if verb not in _INDEX_VERBS:
        raise _reject(f'"{verb}" is not permitted — read-only search family only')
    if req.method not in _INDEX_VERBS[verb]:
        raise _reject(f'"{verb}" admits {" or ".join(sorted(_INDEX_VERBS[verb]))} only')
    if not _INDEX_EXPR.match(expr):
        raise _reject(f'"{expr}" is not a valid index expression')
    if _touches_sensitive(expr):
        raise _reject("credential indices (users/sessions/tokens) are not inspectable")
    if req.body is not None:
        if verb == "_mapping":
            raise _reject("_mapping takes no body")
        if (key := _forbidden_keys(req.body)) is not None:
            raise _reject(f'"{key}" is not permitted on this endpoint')
        size = req.body.get("size")
        max_hits = get_settings().inspect_max_hits
        if isinstance(size, int) and size > max_hits:
            raise _reject(f"size {size} exceeds the {max_hits}-hit ceiling")
    return path


@router.post("/inspect")
async def inspect_store(
    request: Request, body: InspectRequest, principal: CanInspect
) -> dict[str, Any]:
    path = _validate(body)
    client = request.app.state.opensearch
    settings = get_settings()

    # journal FIRST (strict) — an unjournaled inspector read must be impossible (D17)
    query_hash = hashlib.sha256(json.dumps(body.body or {}, sort_keys=True).encode()).hexdigest()[
        :12
    ]
    await append_auth_event(
        client,
        actor=principal.user_id,
        action="store_inspect",
        entity_type="store",
        entity_id=f"{body.method} {path} sha256:{query_hash}",
        strict=True,
    )

    params: dict[str, Any] = {"request_timeout": settings.inspect_timeout_seconds}
    target = f"/{path}"
    if path.startswith("_cat/"):
        params["format"] = "json"  # the UI always gets structured rows, never plaintext columns
        target = f"/{path}/{_CAT_INDICES}"
    started = time.monotonic()
    try:
        response = await client.transport.perform_request(
            body.method, target, params=params, body=body.body
        )
    except TransportError as exc:
        # the store's own 4xx (bad query DSL, unknown index) surfaces verbatim — the real errors
        status = exc.status_code if isinstance(exc.status_code, int) else 502
        raise HTTPException(status, str(exc.error)) from exc
    took_ms = int((time.monotonic() - started) * 1000)

    payload = json.dumps(response, default=str)
    if len(payload) > settings.inspect_max_response_bytes:
        log.warning(
            "inspect response capped", path=path, bytes=len(payload), actor=principal.user_id
        )
        LIMIT_REJECTIONS.labels("inspect_bytes").inc()
        raise HTTPException(
            413,
            f"response is {len(payload)} bytes — over the "
            f"{settings.inspect_max_response_bytes}-byte cap; narrow the query",
        )
    log.info("store inspect", path=path, method=body.method, took_ms=took_ms, bytes=len(payload))
    return {
        "took_ms": took_ms,
        "bytes": len(payload),
        "cap_bytes": settings.inspect_max_response_bytes,
        "body": response,
    }
