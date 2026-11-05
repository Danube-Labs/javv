"""The write tools of the MCP endpoint (issue 1096 step 3, D5). Each one is a route function,
through `tools.build`, and `needs` the permission that a token level gives."""

from backend.mcp.tools import Tool

WRITE_TOOLS: tuple[Tool, ...] = ()
