"""The read tools of the MCP endpoint (issue 1096, D6). Each one is a route function, through
`tools.build`; `test_mcp_read_coverage.py` holds each read route to a tool or to the list of reads
with no tool."""

from backend.mcp.tools import ReadTool
from backend.routers import clusters

READ_TOOLS: tuple[ReadTool, ...] = (
    ReadTool(
        name="list_clusters",
        description=(
            "The clusters that JAVV knows, with their id, name and the time of their newest scan. "
            "Most other tools need a cluster_id from this list."
        ),
        routes={"": clusters.list_clusters},
    ),
)
