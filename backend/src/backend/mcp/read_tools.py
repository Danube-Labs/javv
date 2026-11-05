"""The read tools of the MCP endpoint (issue 1096, D6). Each one is a route function, through
`tools.build`; `test_mcp_read_coverage.py` holds each read route to a tool or to `NO_TOOL`."""

from typing import Annotated

from pydantic import Field

from backend.mcp.tools import ReadTool
from backend.routers import (
    admin_jobs,
    admin_users,
    audit,
    clusters,
    contributors,
    dashboards,
    data_settings,
    decisions,
    findings,
    images,
    mcp_tokens,
    meta,
    retirement_settings,
    scan_scope,
    scanners,
    staleness_settings,
    tokens,
    trends,
)
from backend.sla import routes as sla_routes

# Q5 of the step 0 report: an agent client refused a page of 96 findings (92,789 characters) and
# read pages of 25 (about 24,500 characters) with no problem
FINDINGS_PAGE = (Annotated[int, Field(ge=1, le=25)], 20)

READ_TOOLS: tuple[ReadTool, ...] = (
    ReadTool(
        name="list_clusters",
        description=(
            "The clusters that JAVV knows, with their id, name and the time of their newest scan. "
            "Most other tools need a cluster_id from this list."
        ),
        routes={"": clusters.list_clusters},
    ),
    ReadTool(
        name="search_findings",
        description=(
            "One page of the findings of one cluster, with the filters of the Findings screen. "
            "Each finding is one CVE in one package version for one scanner: the scanners stay "
            "apart. Pass next_cursor back as cursor for the next page. A first page starts a new "
            "search. as_of reads a past time."
        ),
        routes={"": findings.search_findings},
        params={"size": FINDINGS_PAGE},
        hidden=("keep_open",),
        paged=True,
    ),
    ReadTool(
        name="count_findings",
        description=(
            "Counts of the findings of one cluster for each value of a field (severity, state, "
            "scanner, namespace, package type, assignee and more), with the same filters as "
            "search_findings. Use it before you read rows."
        ),
        routes={"": findings.facet_findings},
    ),
    ReadTool(
        name="group_findings",
        description="The findings of one cluster in groups of one field, with a count for each.",
        routes={"": findings.group_findings},
    ),
    ReadTool(
        name="top_images",
        description=(
            "The running images of one cluster with the most critical, then high, medium and low "
            "findings, with the counts of each scanner. At most 100 images."
        ),
        routes={"": findings.top_images_findings},
    ),
    ReadTool(
        name="top_components",
        description="The packages of one cluster with the most findings, with their counts.",
        routes={"": findings.top_components_findings},
    ),
    ReadTool(
        name="list_images",
        description="The running images of one cluster, from the newest inventory.",
        routes={"": images.list_running_images},
    ),
    ReadTool(
        name="image_timeline",
        description="The history of one image (repository and tag) in one cluster.",
        routes={"": images.image_timeline},
    ),
    ReadTool(
        name="trends",
        description=(
            "Changes over time in one cluster: kind findings (open findings per day), scans "
            "(scans per day) or ingest_failures (refused pushes per day)."
        ),
        routes={
            "findings": trends.findings_trend,
            "scans": trends.scans_trend,
            "ingest_failures": trends.ingest_failures_trend,
        },
    ),
    ReadTool(
        name="scanner_status",
        description=(
            "The scanners of one cluster: kind freshness (the newest scan of each scanner and if "
            "it is late) or provenance (the scanner and database versions of recent runs)."
        ),
        routes={"freshness": scanners.scanner_freshness, "provenance": scanners.scanner_provenance},
    ),
    ReadTool(
        name="scanner_ingest_failures",
        description=(
            "One page of the refused pushes of one scanner in one cluster, with the reason."
        ),
        routes={"": scanners.scanner_ingest_failures},
    ),
    ReadTool(
        name="audit_log",
        description=(
            "One page of the audit log of one cluster: who changed what and when. Pass "
            "next_cursor back as cursor for the next page. as_of reads a past time."
        ),
        routes={"": audit.read_audit_log},
        hidden=("keep_open",),
        paged=True,
    ),
    ReadTool(
        name="count_audit_log",
        description="Counts of the audit log of one cluster for each entity, action and user.",
        routes={"": audit.audit_facets},
    ),
    ReadTool(
        name="contributors",
        description="Who triaged the findings of one cluster in a time window, with their counts.",
        routes={"": contributors.contributors},
    ),
    ReadTool(
        name="list_decisions",
        description="The Not affected and risk accept decisions of one cluster, with the reasons.",
        routes={"": decisions.list_decisions},
    ),
    ReadTool(
        name="list_approvals",
        description="The risk acceptances of one cluster with their status and expiry.",
        routes={"": decisions.approval_list},
    ),
    ReadTool(
        name="list_dashboards",
        description="The saved dashboards, with their names and panels.",
        routes={"": dashboards.list_dashboards},
    ),
    ReadTool(
        name="get_dashboard",
        description="One saved dashboard by its id.",
        routes={"": dashboards.get_dashboard},
    ),
    ReadTool(
        name="read_settings",
        description=(
            "A settings page: kind about (the JAVV, schema and OpenSearch versions), scan_scope, "
            "sla, staleness, retirement, data (retention and rollover), snapshots, opensearch "
            "(the store runtime) or jobs (the background jobs and their last runs)."
        ),
        routes={
            "about": meta.get_meta,
            "scan_scope": scan_scope.get_scan_scope_session,
            "sla": sla_routes.get_sla,
            "staleness": staleness_settings.get_staleness,
            "retirement": retirement_settings.get_retirement,
            "data": data_settings.get_data_settings,
            "snapshots": data_settings.list_snapshots,
            "opensearch": data_settings.get_opensearch_runtime,
            "jobs": admin_jobs.list_jobs,
        },
    ),
    ReadTool(
        name="list_accounts",
        description=(
            "The accounts of JAVV: kind users, roles, scanner_tokens or mcp_tokens. No answer "
            "holds a password, a token or a hash."
        ),
        routes={
            "users": admin_users.list_users,
            "roles": admin_users.list_roles,
            "scanner_tokens": tokens.list_tokens,
            "mcp_tokens": mcp_tokens.list_tokens,
        },
    ),
)

# D6: the reads with no tool, and why. The coverage test holds every other GET route to a tool.
NO_TOOL: dict[str, str] = {
    "/healthz": "the platform, not JAVV data",
    "/readyz": "the platform, not JAVV data",
    "/metrics": "the platform, not JAVV data",
    "/auth/me": "the user of a session",
    "/api/v1/notifications": "the bell of one user",
    "/api/v1/views": "the saved views of one user",
    "/api/v1/scan-scope": "the scanner token route; read_settings kind scan_scope reads it",
    "/api/v1/dashboards/roles": "the role list of the share dialog of a dashboard",
    "/api/v1/reports/{report_id}": "the state of an export report",
    "/api/v1/reports/{report_id}/download": "an export file",
    "/api/v1/findings/export.csv": "an export file: search_findings reads the same rows",
    "/api/v1/findings/export.vex": "an export file: search_findings reads the same rows",
    "/api/v1/audit/export.csv": "an export file: audit_log reads the same rows",
    "/api/v1/contributors/export.csv": "an export file: contributors reads the same rows",
    "/api/v1/decisions/approvals/export.csv": "an export file: list_approvals reads the same rows",
    "/api/v1/dashboards/export.ndjson": "an export file: list_dashboards reads the same rows",
}
