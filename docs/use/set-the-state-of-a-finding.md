# Set the state of a finding

<video controls preload="metadata" width="100%" src="videos/set-the-state-of-a-finding.mp4"></video>

!!! tip "For AI agents"
    An agent with a `write` or `write_risk_accept` token sets the state of one finding with the
    tool `set_triage`. The tool takes the `finding_key` of the finding from `search_findings`. A
    finding with an accepted risk keeps its state. [Use the MCP server](use-the-mcp-server.md) tells how to connect.

## Prerequisites

- A role that allows triage: `triager`, `security_lead` or `admin`
  ([What your role lets you do](index.md#what-your-role-lets-you-do)).

## Steps

1. Open a finding from the Findings table. The Triage cell sets the state of this one finding.
2. In the Triage cell, select Not affected. A panel opens next to the cell.
3. In the panel, select one of the five standard reasons. Not affected needs a reason.
4. Select Save. The state changes immediately.
5. Only this finding changes. The finding of the other scanner stays Open.
6. The Activity card of the finding shows who changed the state and when.
7. To see all the triage changes, open the Audit log from the side menu. The new entry is at the
   top: when, who, and what changed.

Next: [Accept a risk, with an expiry date](accept-a-risk.md).
