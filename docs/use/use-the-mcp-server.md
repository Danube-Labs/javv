# Use the MCP server

JAVV has an MCP server for AI agents. An agent can read the findings of JAVV for you, and with a
token of a higher level it can also triage them. The agent connects to the MCP endpoint of JAVV,
`/api/v1/mcp`, with an MCP token. This page tells how to turn on the endpoint, how to make a
token, and how to connect Claude Code, Codex, VS Code or Cursor.

!!! tip "For AI agents"
    Obey these rules when you call the tools of JAVV:

    - Call `list_clusters` first. Most other tools need a `cluster_id` from its answer.
    - A finding is one CVE in one package version for one scanner. The results of Trivy and
      Grype stay apart. Do not add them together, and do not merge them.
    - To get the next page of `search_findings` or `audit_log`, send `next_cursor` back as
      `cursor`. A new search with the same tool closes the cursor of your last search. Read all
      the pages that you need before you start the next search.
    - An answer with a `cut` field does not have all the rows. Ask for fewer rows. When a tool
      error tells you to ask for a smaller size, send a smaller `size`.
    - Each write tool has the hint `destructiveHint`. Ask the user before each write.
    - When a tool error has the words "the tool made the change", do not call the tool again.
    - A tool error with `403` tells you that the level of the token does not allow the tool. Tell
      the user that the token needs a higher level.
    - A tool error with `extra_forbidden` tells you that the tool does not take an argument that
      you sent. Use only the arguments of the input schema of the tool.

## Before you start

- You need the address where you open JAVV, for example `https://javv.example.com`. The URL of
  the endpoint is this address with `/api/v1/mcp` after it.
- To turn on the endpoint, you change a setting of the JAVV backend.
- To make a token, your role must allow you to manage tokens. Of the default roles, only
  `admin` allows it.
- The agent sends the token in each request. Use `https` in front of JAVV. Over plain `http`, each
  system on the network path can read the token ([http or https](../DEPLOYING.md#http-or-https)).

## Turn on the endpoint

The endpoint is off by default. When it is off, a request to it gets 404.

**With docker compose:**

1. Add this line to `.env`, in the folder of `compose.yaml`:

    ```bash
    JAVV_MCP_ENABLED=true
    ```

2. Run `docker compose up -d`. Compose starts the backend again with the new value.

**With Helm:**

1. Add the setting to your values file for the `javv` chart:

    ```yaml
    backend:
      config:
        JAVV_MCP_ENABLED: "true"
    ```

2. Set `VERSION` to the version of JAVV that you run now, and upgrade the release:

    ```bash
    helm upgrade javv oci://ghcr.io/danube-labs/charts/javv --version "$VERSION" \
      -f my-javv-values.yaml
    ```

    The chart starts the backend again with the new value.

To see the result, open **Settings › AI agents (MCP)** in JAVV. The Endpoint card shows **on**
and the URL of the endpoint.

## Make a token

1. Open **Settings › AI agents (MCP)**, and select **Make token**.
2. Type a name. The name has 3 to 64 lower-case letters, digits, dots, underscores or hyphens.
   The Audit log names the agent `mcp:` and this name, for example `mcp:weekly-report`.
3. Select the level of the token. The table in [The levels of a token](#the-levels-of-a-token)
   tells what each level can do.
4. Select the expiry. It is a day from tomorrow to 90 days from today. The token stops at 00:00
   UTC on that day.
5. Select **Make token**. JAVV shows the token one time only. Copy it, and keep it in a safe
   place, for example a password manager.

To stop a token, select **Revoke** on its row. To get a new token for the same name, select
**Rotate** and pick a new expiry. The old token then stops at once.

## Connect Claude Code

We tested these settings with Claude Code 2.1.319.

1. Put the token in the variable `JAVV_MCP_TOKEN`, in the shell that starts Claude Code.
2. Add the server. Use single quotes, so that the config keeps the name of the variable and not
   the token:

    ```bash
    claude mcp add --transport http --scope user javv https://javv.example.com/api/v1/mcp \
      --header 'Authorization: Bearer ${JAVV_MCP_TOKEN}'
    ```

3. Run `claude mcp list`. The list shows `javv` with "Connected".

With `--scope project`, the command writes the server to `.mcp.json` in your project. Claude Code
then asks you to approve the server the next time that it starts in that folder.

When `claude mcp list` shows "Server rejected the configured Authorization header (HTTP 401)",
the token is wrong, revoked or expired, or `JAVV_MCP_TOKEN` is empty. Make a token, or rotate the
token. Claude Code can tell you to use OAuth in place of the header. JAVV has no OAuth, so keep
the header.

## Connect Codex

We tested these settings with Codex 0.144.1.

1. Add the server to `~/.codex/config.toml`:

    ```toml
    [mcp_servers.javv]
    url = "https://javv.example.com/api/v1/mcp"
    bearer_token_env_var = "JAVV_MCP_TOKEN"
    ```

2. Put the token in the variable `JAVV_MCP_TOKEN`, in the shell that starts Codex.
3. Run `codex mcp list`. The list shows `javv` with the auth "Bearer token".

## Connect VS Code

We did not test this client with JAVV. Its settings come from its own documentation.

1. Add the server to `.vscode/mcp.json` in your workspace. VS Code asks for the token when the
   server starts for the first time, and it hides what you type:

    ```json
    {
      "inputs": [
        {
          "type": "promptString",
          "id": "javv-token",
          "description": "JAVV MCP token",
          "password": true
        }
      ],
      "servers": {
        "javv": {
          "type": "http",
          "url": "https://javv.example.com/api/v1/mcp",
          "headers": { "Authorization": "Bearer ${input:javv-token}" }
        }
      }
    }
    ```

## Connect Cursor

We did not test this client with JAVV. Its settings come from its own documentation.

1. Add the server to `~/.cursor/mcp.json`, or to `.cursor/mcp.json` in your project:

    ```json
    {
      "mcpServers": {
        "javv": {
          "url": "https://javv.example.com/api/v1/mcp",
          "headers": { "Authorization": "Bearer ${env:JAVV_MCP_TOKEN}" }
        }
      }
    }
    ```

2. Put the token in the variable `JAVV_MCP_TOKEN` before you start Cursor.

## The levels of a token

| Level | What the agent can do |
|---|---|
| Read | Read the data of all clusters. It changes nothing. |
| Write | Read. Also set the state, the assignee and the note of findings, also in bulk. Make, change and revoke "Not affected" decisions. |
| Write and risk accept | Write. Also accept a risk, and change or revoke a risk acceptance. |

No token can change users, roles, settings or tokens. No token can delete data. A change by an
agent gets the same checks as the same change on a screen. For example, a Write token cannot
change the state of a finding with an accepted risk.

## An agent in the Audit log

- A change by an agent writes the same rows as the same change on a screen, with the user
  `mcp:<name>`.
- Each tool call writes one row with the action **MCP tool call**. Only a user who can manage
  users sees these rows.
- **Settings › AI agents (MCP)** shows who made each token, and when an agent last used it.

## If the agent cannot connect

| What the agent gets | Cause | What to do |
|---|---|---|
| 404 | The endpoint is off. | [Turn on the endpoint](#turn-on-the-endpoint). |
| 401 `invalid token` | The token is wrong, revoked or expired. A scanner token also gets 401. | Make a token, or rotate the token. |
| 403 | The request has an `Origin` header. A browser sends this header, so a web page cannot use the endpoint. | Use an agent client. |
| 429 | The token sent more requests in one minute than `JAVV_MCP_RATE_LIMIT_PER_MINUTE` allows (60 by default). | Wait one minute. |
| A tool error: the level of this token does not allow this tool | The tool needs a higher level. | Make a token with a higher level. |
| A tool error: `extra_forbidden` | The agent sent an argument that the tool does not take, for example a filter with a typo. The tool did not run. | Tell the agent to use the arguments of the input schema of the tool. |
| An answer with a `cut` field | The answer was longer than `JAVV_MCP_MAX_ANSWER_CHARS` (50,000 characters by default). JAVV kept the first rows, and `cut` gives the number. | Ask for fewer rows. |
| A tool error: 410 `cursor closed` | The agent started a new search with the same tool, and that search closed the cursor of the last search. | Tell the agent to read all the pages that it needs before it starts a new search. |
| A tool error: ask for a smaller size | A page of rows with a next page was longer than `JAVV_MCP_MAX_ANSWER_CHARS`. | Ask for a smaller page. |

The settings of the endpoint are in [MCP endpoint](../CONFIGURATION.md#mcp-endpoint). The tools of
each level are in [The MCP endpoint](../API.md#the-mcp-endpoint).
