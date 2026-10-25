"""FastAPI app factory. Conventions (api-design.md): `/api/v1` prefix for data routes, snake_case,
`extra="forbid"` request models, the single problem-details error envelope. Observability (D9):
JSON structlog with a bound `request_id`, and `/metrics` (Prometheus)."""

from fastapi import FastAPI

from backend.core.errors import register_error_handlers
from backend.core.lifespan import lifespan
from backend.core.logging import configure_logging, install_request_context
from backend.core.metrics import install_http_metrics
from backend.routers import (
    admin_jobs,
    admin_users,
    audit,
    auth,
    client_events,
    clusters,
    contributors,
    cursors,
    dashboards,
    dashboards_io,
    data_settings,
    decisions,
    exports,
    findings,
    health,
    images,
    ingest,
    inspect,
    inventory_runs,
    meta,
    metrics,
    notifications,
    reports,
    retirement_settings,
    scan_runs,
    scan_scope,
    scanners,
    staleness_settings,
    tokens,
    trends,
    triage,
    views,
)
from backend.sla import routes as sla_routes
from backend.triage import bulk_routes
from backend.version import APP_VERSION


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="JAVV backend", version=APP_VERSION, lifespan=lifespan)
    install_request_context(app)
    install_http_metrics(app)  # M-1 (#220): route-template request histogram
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(metrics.router)
    app.include_router(meta.router)
    app.include_router(ingest.router)
    app.include_router(scan_scope.router)
    app.include_router(scan_runs.router)
    app.include_router(inventory_runs.router)
    app.include_router(tokens.router)
    app.include_router(admin_users.router)
    app.include_router(admin_users.roles_router)
    app.include_router(admin_jobs.router)
    app.include_router(triage.router)
    app.include_router(findings.router)
    app.include_router(exports.router)
    app.include_router(trends.router)
    app.include_router(reports.router)
    app.include_router(notifications.router)
    app.include_router(contributors.router)
    app.include_router(decisions.router)
    app.include_router(scanners.router)
    app.include_router(audit.router)
    app.include_router(images.router)
    app.include_router(clusters.router)
    app.include_router(views.router)
    app.include_router(dashboards_io.router)  # first: export.ndjson is not a dashboard id
    app.include_router(dashboards.router)
    app.include_router(client_events.router)
    app.include_router(cursors.router)
    app.include_router(sla_routes.router)
    app.include_router(staleness_settings.router)
    app.include_router(retirement_settings.router)
    app.include_router(data_settings.router)
    app.include_router(inspect.router)
    app.include_router(bulk_routes.router)
    return app


app = create_app()
