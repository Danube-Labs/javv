# Use JAVV

These pages show how to triage the findings in JAVV, from the first scan to a finding with a
decision, and how to put panels on a dashboard. Each page in the table has a short video. The same steps are in text below each video.

| Video | What it shows |
|---|---|
| [From a scan to a finding](from-a-scan-to-a-finding.md) | How the results of the two scanners get to JAVV, and how to find one finding |
| [Set the state of a finding](set-the-state-of-a-finding.md) | How to set the state of one finding, and where JAVV records the change |
| [Accept a risk, with an expiry date](accept-a-risk.md) | How to accept the risk of one CVE in a scope, and how to stop it |
| [Change many findings at once](change-many-findings.md) | How to change the state of all the findings that match your filters |
| [When a scanner stops sending results](when-a-scanner-stops.md) | What JAVV does when a scanner is silent for too long |
| [See who changed what](who-changed-what.md) | How to find the changes in the Audit log and on a finding |
| [Build a dashboard](build-a-dashboard.md) | How to put panels on one page, share the page, and copy it to a different JAVV |

The videos use made-up clusters and data.

One page has no video:

- [Use the MCP server](use-the-mcp-server.md) tells how to turn on the MCP endpoint, how to make
  an MCP token, and how to connect Claude Code, Codex, VS Code or Cursor.

!!! tip "For AI agents"
    An AI agent can do most of these tasks through the MCP server of JAVV. With a `read` token, it
    finds and counts findings, and reads the audit log, the scanner status and the dashboards. With
    a `write` token, it also sets the state of findings and makes "Not affected" decisions. Only a
    `write_risk_accept` token can accept a risk. No token can make a dashboard. Each page tells the
    tool for its task. [Use the MCP server](use-the-mcp-server.md) tells how to connect.

## What your role lets you do

Your role sets what you can change:

- To set the state of a finding, or of many findings at once, your role must allow triage. The
  `triager`, `security_lead` and `admin` roles allow it.
- To accept a risk, or to revoke a risk acceptance, your role must allow risk acceptance. The
  `security_lead` and `admin` roles allow it.
- To download a file of the data, for example a CSV or VEX file, your role must allow export. The
  `triager`, `security_lead` and `admin` roles allow it. The `viewer` role does not. For a viewer,
  each export button is not available, and the text next to it tells you why.
- To make a dashboard, or to import one, your role must allow dashboards. The `triager`,
  `security_lead` and `admin` roles allow it. Only the owner of a dashboard or an admin can
  change it or remove it.

An administrator sets the role of each user.

## More help

The Guide in the side menu of JAVV explains the states, the reasons and the risk acceptances.
