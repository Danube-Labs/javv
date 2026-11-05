"""`GET /api/v1/meta`: what this backend is running (issue 261). Behind login on purpose: `/readyz`
stays anonymous for the Kubernetes probe, so the version must not ride on it. Operators without a
session read the same numbers from the `bootstrap complete` log line.

The About page (issue 341) also shows the OpenSearch and Python versions from here, to every
signed-in user. The OpenSearch version is read live, so an upgraded store shows without a backend
restart; heap, topology and paths stay on the admin-only runtime read."""

import platform
from typing import Annotated, Any, get_args

import structlog
from fastapi import APIRouter, Depends, Request
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import ConnectionTimeout

from backend.auth.principal import Principal, get_current_principal
from backend.core.bootstrap import MAPPING_VERSION
from backend.core.metrics import OS_REQUEST_ERRORS
from backend.core.settings import get_settings
from backend.models.envelope import IngestEnvelope
from backend.version import APP_VERSION

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/meta", tags=["meta"])

Authenticated = Annotated[Principal, Depends(get_current_principal)]

ENVELOPE_VERSIONS: list[int] = sorted(
    get_args(IngestEnvelope.model_fields["schema_version"].annotation)
)


def _os(request: Request) -> Any:
    return request.app.state.opensearch


async def _opensearch_version(request: Request) -> str | None:
    """The store's version, or None when it can't be reached: the rest of `/meta` still answers,
    so the sidebar and the About page keep the versions they can show during an outage."""
    try:
        info = await _os(request).info()
    except (OSConnectionError, ConnectionTimeout) as exc:
        kind = "timeout" if isinstance(exc, ConnectionTimeout) else "conn"
        OS_REQUEST_ERRORS.labels(kind).inc()
        log.warning("opensearch version unavailable", kind=kind)
        return None
    return info.get("version", {}).get("number")


@router.get("")
async def get_meta(request: Request, principal: Authenticated) -> dict[str, Any]:
    return {
        "version": APP_VERSION,
        "mapping_version": MAPPING_VERSION,
        "envelope_versions": ENVELOPE_VERSIONS,
        "opensearch_version": await _opensearch_version(request),
        "python_version": platform.python_version(),
        "mcp_enabled": get_settings().mcp_enabled,  # the Settings section of issue 1096 reads it
    }
