# JAVV API

This page describes the HTTP API of JAVV. It is for people who write scripts for JAVV or monitor
it. The tasks come first. Then the reference tables give each endpoint, error and metric.

The backend also publishes a description of its API, with each parameter and its limits. It is at
`/docs` and `/openapi.json` on the backend port, 8000. The frontend does not send these two paths
to the backend.

To push scan results from your own tools, read [Push from your own script](INGEST-CONTRACT.md). To
connect the JAVV scanners, read [Connect the scanners](DEPLOYING.md#connect-the-scanners).

## Sign in from a script

A script uses the same address as a browser. The frontend sends `/api`, `/auth` and `/readyz` to
the backend. These commands need bash, `curl` and `jq`.

1. Set the address of JAVV:
    ```bash
    JAVV=https://javv.example.com
    ```
2. Sign in. The command keeps the session cookie in the file `jar`:
    ```bash
    read -rs -p 'Password: ' pw && echo
    jq -n --arg u admin --arg p "$pw" '{username: $u, password: $p}' \
      | curl -sf -c jar -b jar -H 'Content-Type: application/json' --data @- "$JAVV/auth/login"
    ```
    The reply shows `must_change`. If it is `true`, do step 3. If it is `false`, go to step 4.
3. Change the password. The new password must have 12 characters or more:
    ```bash
    read -rs -p 'New password: ' new && echo
    jq -n --arg c "$pw" --arg n "$new" '{current_password: $c, new_password: $n}' \
      | curl -sf -c jar -b jar -H 'Content-Type: application/json' --data @- "$JAVV/auth/password"
    unset new
    ```
    JAVV ends each session of the user, then writes a new session cookie to `jar`.
4. Delete the password from the shell:
    ```bash
    unset pw
    ```
5. Send your requests with the cookie. For example, show your user and permissions:
    ```bash
    curl -sf -b jar "$JAVV/auth/me"
    ```
6. At the end of the script, sign out. JAVV then ends the session:
    ```bash
    curl -sf -b jar -X POST "$JAVV/auth/logout"
    ```

Keep the file `jar` private. Until the session ends, the cookie in it gives access as your user.

## Read a list page by page

A list endpoint gives one page of rows. [List responses](#list-responses) shows the three forms of
a list. This procedure reads all the findings of one cluster with the cursor.

1. Sign in ([Sign in from a script](#sign-in-from-a-script)).
2. Find the id of the cluster:
    ```bash
    curl -sf -b jar "$JAVV/api/v1/clusters" | jq -r '.clusters[] | "\(.cluster_id) \(.cluster_name)"'
    ```
3. Set the id:
    ```bash
    cluster=<cluster_id>
    ```
4. Read each page, 500 rows at a time. Send `next_cursor` back as `cursor` until it is `null`:
    ```bash
    cursor=
    while :; do
      page=$(curl -sfG -b jar "$JAVV/api/v1/findings" --data-urlencode "cluster_id=$cluster" \
        --data-urlencode size=500 ${cursor:+--data-urlencode "cursor=$cursor"}) || break
      jq -c '.data[] | {cve_id, scanner, severity, state}' <<<"$page"
      cursor=$(jq -r '.next_cursor // empty' <<<"$page")
      [ -n "$cursor" ] || break
    done > findings.jsonl
    ```
5. Compare the number of lines in `findings.jsonl` with `total.value` of a page. If they are not
   equal, a page failed. Read the list again.

A cursor stays valid for a short time only. If a page answers 410, start again at step 4.

To stop before the last page, close the cursor. Until then, it keeps one of your open-cursor
slots ([Exports and reports](#exports-and-reports)):
```bash
jq -n --arg c "$cursor" '{cursor: $c}' |
  curl -sf -b jar -X POST "$JAVV/api/v1/cursors/close" -H 'Content-Type: application/json' -d @-
```

## Scrape the metrics

The backend gives its metrics at `/metrics`, in the Prometheus format. This path needs no sign-in.
The frontend does not send it to the backend. [Metrics](#metrics) lists each metric.

1. Let your Prometheus connect to the backend port, 8000:
    - with docker compose: publish the port. Use the `ports` block in comments under `backend` in
      `compose.yaml` ([Ports and access](DEPLOYING.md#ports-and-access)).
    - with Helm: use the backend Service. For a release with the name `javv`, it is `javv-backend`.
2. Add a scrape of `http://<backend>:8000/metrics` to your Prometheus.
3. Look at the metrics from a machine that can connect to the port:
    ```bash
    curl -sf http://<backend>:8000/metrics | grep '^# TYPE javv_'
    ```

JAVV gives no alert rules. Make alerts from the metrics that apply to your setup.

## Authentication

Each endpoint uses one of three kinds of authentication.

| Kind | What the request sends | Endpoints |
|---|---|---|
| None | Nothing | `/healthz`, `/readyz` and `/metrics`. Control the access to these with your network. Also `POST /auth/login` and `POST /auth/logout`. |
| Scanner token | `Authorization: Bearer <token>`. Each token is for one cluster and one scanner. JAVV keeps only a hash of the token. | The scanner endpoints: ingest, scan scope, scan runs and inventory runs. A token can send data only for its own cluster and scanner. |
| Session | The `javv_session` cookie from `POST /auth/login` | All other endpoints |

The session cookie has the `HttpOnly` and `SameSite=Lax` flags. It also has the `Secure` flag,
unless `JAVV_SESSION_COOKIE_SECURE` is `false` ([http or https](DEPLOYING.md#http-or-https)).

- **Session time:** a session ends `JAVV_SESSION_TTL_HOURS` after the sign-in (default 24), or at
  sign-out. The server decides, not the cookie.
- **Failed sign-ins:** after `JAVV_LOGIN_MAX_ATTEMPTS` failures (default 5) for one username in
  `JAVV_LOGIN_LOCKOUT_MINUTES` (default 15), the sign-in answers 429. A successful sign-in sets
  the count to zero.
- **One answer for each failure:** a wrong username, a wrong password, a disabled user and an
  expired session all get the same 401. Thus the answer does not show if a username exists.
- **The login body:** `POST /auth/login` accepts only `Content-Type: application/json`. A body
  that is not JSON gets 422. A different JSON type, for example `application/merge-patch+json`,
  gets 415.

### A temporary password

The first admin, a new user and a user after a password reset have a temporary password. The user
must change it ([Sign in from a script](#sign-in-from-a-script), step 3). Until then, the session
can use only `/auth/*`: show the user, change the password, and sign out. Each other session
endpoint answers a well-formed request with 403 `password change required`, reads included. A
body that is not valid JSON gets 422 first.

Each refusal logs a `password change required` warning with the username. It also increments
`javv_auth_failures_total{reason="must_change"}`.

### A password change

`POST /auth/password` changes the password of the user of the session.

- **The new password** has 12 to 256 characters. Each character counts as one, also a character
  outside ASCII.
- **401:** the current password is wrong, or the session ended. The two get the same answer.
- **403:** an identity provider manages the password of the user.
- **422:** the new password has fewer than 12 or more than 256 characters, or the body is not
  valid.
- **The audit row comes first.** JAVV writes a `pwd_change` row to the audit log before it changes
  the password. If JAVV cannot write the row, the password does not change, and the answer is an
  error.
- **200 with no cookie:** the password changed, but JAVV could not make the new session. Each old
  session ended, so sign in again with the new password. JAVV logs a `password changed, no new
  session` warning and increments `javv_auth_failures_total{reason="session_not_minted"}`.

## Roles and permissions

Some endpoints need a permission. The tables in [Endpoints](#endpoints) name it. A user gets the
permissions of its role. The web app uses the `capabilities` from `GET /auth/me` to show or hide
its controls. The backend checks the permission again on each request.

At its first start, JAVV creates four roles:

| Role | Permissions |
|---|---|
| `viewer` | None. The user can read data only. |
| `triager` | `can_triage` |
| `security_lead` | `can_triage`, `can_accept_audit_final` |
| `admin` | All the permissions, also the permissions of later releases |

| Permission | What it allows |
|---|---|
| `can_triage` | Triage findings. Make, change and revoke decisions. |
| `can_accept_audit_final` | Accept a risk, in a decision or in triage. Read and export the approvals queue. |
| `can_manage_tokens` | Make, revoke and rotate scanner tokens |
| `can_manage_users` | Make users. Change their role, their status and their password. |
| `can_manage_settings` | Change the SLA, staleness, retirement and scan scope settings, and the cluster names. Retire a cluster, and bring it back. Read the OpenSearch facts. Start the staleness sweep. Change or delete the saved views of other users. |
| `can_manage_retention` | Read and change the data settings: retention, rollover, export lifetime and findings cleanup. Read and take snapshots. Delete a retired cluster. |
| `can_restore_snapshot` | Restore a snapshot |
| `can_inspect_store` | Use the data inspector. Read the status of the background jobs. |
| `can_rebuild_state` | Start the job that builds the current state again |
| `can_drop_index` | Start the lifecycle sweep, which deletes old indices |

Each read and export applies the cluster that the request names. Each user can read each
cluster. A `cluster_id` has 8 to 64 lowercase letters, digits or hyphens, and does not start with
a hyphen.

## Errors

Each answer that is not a success has the same body, with the type `application/problem+json`:

```json
{"type": "about:blank", "title": "invalid credentials", "status": 401, "detail": null, "request_id": "b169be4a30444fdc"}
```

- `type`: `about:blank`, or one of these. Match on `type`, not on `title`: the title can change.
    - `store-read-only` on a 503 for a write that OpenSearch refused because its disk is full.
    - `cluster-delete-unfinished` on a 409 for a cluster whose delete did not finish: a bring
      back (`POST /api/v1/clusters/{cluster_id}/unretire`) or a new token
      (`POST /api/v1/admin/tokens`). Delete the cluster again to finish it.
- `title`: a short text that names the error.
- `detail`: on a 422 from a field check, the list of the fields that are not valid, with the
  reason for each. It does not hold the value that you sent. Else it is `null`.
- `request_id`: the id of the request in the backend log. The `X-Request-ID` header of the answer
  also has it, on each answer. To set the id yourself, send `X-Request-ID` with 1 to 64 letters,
  digits or hyphens. If you send no id, or an id that is not valid, the backend makes one.

| Status | Meaning |
|---|---|
| 400 | The ingest body is not valid gzip or JSON. On the other endpoints, a body that is not valid JSON gets 422. |
| 401 | The request has no valid session or token. |
| 403 | The user does not have the permission, or must change the password first. A scanner token sent data for a different cluster or scanner. |
| 404 | The item does not exist. For an item of a different user, the answer is also 404. |
| 409 | A different request changed the item first, or the item is not in the necessary state. |
| 410 | The cursor or the export expired. Do the request again from the start. |
| 413 | The request asks for too many rows, or its body is too large. Make the request smaller. |
| 415 | The sign-in body has a JSON type that is not `application/json`. |
| 422 | A field is not valid. `detail` names the field. |
| 429 | Too many requests. Some answers have a `Retry-After` header with the seconds to wait. The title "The search backend is busy" tells that OpenSearch itself has too much work (a full queue or a circuit breaker). That answer has `Retry-After: 5`. |
| 503 | OpenSearch is not available. Do the request again later. The type `store-read-only`, with the title "The store is read-only: its disk is full", tells that the disk of OpenSearch is past its flood-stage watermark. Reads work. Each change that OpenSearch refuses, also a sign-in, gets this 503 until OpenSearch has free disk space. An ingest push gets the ingest 503 instead ([Ingest a scan](#ingest-a-scan)). |

## List responses

A list has one of three forms. The form comes from how the endpoint pages its rows.

| Paging | Form | Endpoints |
|---|---|---|
| Cursor | `{"data": [...], "next_cursor": "...", "total": {"value": N, "relation": "eq"}}` | `/findings`, `/audit`, `/scanners/ingest-failures` |
| Offset: `size` and `offset` | `{"<name>": [...], "total": N}` | `/decisions` (`decisions`), `/decisions/approvals` (`approvals`), `/admin/users` (`users`), `/admin/tokens` (`tokens`) |
| None | `{"<name>": [...]}` | `/contributors` (`leaderboard`), `/images` (`images`), `/images/timeline` (`events`), `/findings/top-components` (`components`), `/clusters` (`clusters`), `/views` (`views`), `/notifications` (`items`), `/admin/jobs` (`jobs`), `/admin/roles` (`roles`), `/admin/snapshots` (`snapshots`), `/scanners/provenance` (`scanners`), `/scanners/freshness` (`scanners`) |

- `/findings/groups` uses a cursor, but it has no `total`.
- `/notifications` puts its rows in `items`, not in a key with the name of the resource.
- Some answers have more keys next to the list. For example, `/images` also has `inventory`.
- In a cursor list, `total` is an object. In an offset list, `total` is a number.

Read a key by its name, and check that it exists. In `jq`, a key that does not exist gives `null`,
and the length of `null` is 0. That looks the same as an empty list.

## Endpoints

In the tables, the **Access** column gives the authentication, or the permission that the
endpoint needs:

- **none:** no authentication.
- **token:** a scanner token.
- **session:** any signed-in user.
- a permission name: a signed-in user with that permission ([Roles and permissions](#roles-and-permissions)).

The audit log keeps each sign-in and sign-out, and each change to triage, decisions, settings,
the scan scope, users, tokens, saved views, clusters, snapshots and jobs. It also keeps each query
of the data inspector.

### System

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/healthz` | none | Liveness. It answers 200 while the process runs. It does not use OpenSearch. |
| GET | `/readyz` | none | Readiness. It answers 200 `{"status": "ready"}` when OpenSearch answers, else 503 `{"status": "degraded"}`. OpenSearch can answer but refuse writes (its disk is past the flood-stage watermark), or be red (part of its data is not available). Then the answer is 200 with `"checks": {"store": "read-only"}` or `"red"`. Reads still work, so the backend stays in service. |
| GET | `/metrics` | none | The metrics, in the Prometheus format ([Metrics](#metrics)) |
| GET | `/api/v1/meta` | session | The versions that the backend runs: `version` (the JAVV release), `mapping_version`, `envelope_versions` (the ingest schema versions that it accepts), `opensearch_version` and `python_version`. If OpenSearch does not answer, `opensearch_version` is `null`. |

The backend also writes the release and the mapping version in its `bootstrap complete` log line.

### Scanner endpoints

The scanners use these endpoints. Each one applies to the cluster and the scanner of the token,
never to values in the body. [Push from your own script](INGEST-CONTRACT.md) gives the order of the calls
in a scan cycle.

| Method | Path | Access | What it does |
|---|---|---|---|
| POST | `/api/v1/ingest/scan` | token | Accepts the results of one scan ([Ingest a scan](#ingest-a-scan)) |
| GET | `/api/v1/scan-scope` | token | Gives the scan scope of the cluster of the token |
| POST | `/api/v1/scan-runs` | token | Gives the next `scan_order` for the cluster and scanner of the token. Each value is larger than the one before. |
| POST | `/api/v1/inventory-runs` | token | Closes the inventory of a scan cycle. Body: `{scan_run_id, expected_count, started_at}`. The backend counts the images that it received. The run is `committed` only if that count is complete. A repeated call gives the first result again. |

### Sign-in and sessions

| Method | Path | Access | What it does |
|---|---|---|---|
| POST | `/auth/login` | none | Signs in and sets the session cookie. A wrong username or password gets 401. Too many failures get 429 ([Authentication](#authentication)). |
| POST | `/auth/logout` | none | Signs out. It ends the session of the cookie on the server, if the request has a cookie, and deletes the cookie. The answer is 204, also with no session. |
| POST | `/auth/password` | session | Changes your password. Body: `{current_password, new_password}`. It ends each session of the user and sets a new cookie. The rules and the refusals are in [A password change](#a-password-change). |
| GET | `/auth/me` | session | Your user: `username`, `role`, `capabilities` and `must_change` |

### Admin

| Method | Path | Access | What it does |
|---|---|---|---|
| GET/POST | `/api/v1/admin/tokens` | `can_manage_tokens` | GET lists the scanner tokens, newest first, with `size` (1 to 1000, default 100), `offset` (0 to 9000) and an optional `cluster_id`. POST makes a token for `{cluster_id, scanner, expiry}`. The answer shows the token one time only. A cluster with a delete that did not finish gets 409. A token for a deleted cluster's ID onboards that cluster again: JAVV then keeps its new data. |
| POST | `/api/v1/admin/tokens/{token_id}/revoke` | `can_manage_tokens` | Disables a token |
| POST | `/api/v1/admin/tokens/{token_id}/rotate` | `can_manage_tokens` | Makes a new token, with a new id, for the same cluster, scanner and expiry. Then it disables the old token. |
| GET/POST | `/api/v1/admin/users` | `can_manage_users` | GET lists the users, with `size` (1 to 1000, default 100) and `offset` (0 to 9000). POST makes a user with `{username, temp_password, role}`. The usernames `system` and `fleet` get 422. |
| PATCH | `/api/v1/admin/users/{username}/role` | `can_manage_users` | Changes the role of a user, and ends each session of that user |
| PATCH | `/api/v1/admin/users/{username}/disabled` | `can_manage_users` | Disables or enables a user. A disabled user loses each session. The last enabled admin gets 409. |
| POST | `/api/v1/admin/users/{username}/password-reset` | `can_manage_users` | Sets a temporary password, which the user must change. It ends each session of that user. |
| GET | `/api/v1/admin/roles` | `can_manage_users` | The roles and their permissions |
| GET | `/api/v1/admin/snapshots` | `can_manage_retention` | The snapshots in the configured repository, newest first. With no repository, `configured` is `false`. |
| POST | `/api/v1/admin/snapshots` | `can_manage_retention` | Starts a snapshot of `findings`, `javv-images-*` and `system-*`, and answers 202 at once. The scan history is not in the snapshot ([Snapshots](CONFIGURATION.md#snapshots)). With no repository, it answers 409. |
| POST | `/api/v1/admin/snapshots/{snapshot_name}/restore` | `can_restore_snapshot` | Restores a snapshot into copies with the prefix `restored-`. It never writes to the live indices. To use a copy, move it in by hand. |
| GET | `/api/v1/admin/opensearch-runtime` | `can_manage_settings` | Facts about OpenSearch: version, health, nodes, roles, heap, `discovery.type`, `path.repo` and the security plugin. It gives only these fields. |
| POST | `/api/v1/admin/opensearch/inspect` | `can_inspect_store` | The data inspector. [The data inspector](#the-data-inspector) gives its rules. |
| GET | `/api/v1/admin/jobs` | `can_inspect_store` | The status of each of the eight background jobs, and of the scheduler ([The jobs list](#the-jobs-list)) |
| POST | `/api/v1/admin/jobs/{kind}/run` | the permission of the job | Starts a job, and answers 202 `{attempt_id}` ([Start a background job](#start-a-background-job)) |

#### The data inspector

`POST /api/v1/admin/opensearch/inspect` takes `{method, path, body}` and sends only allowed reads
to OpenSearch:

- `GET` or `POST` on `<index>/_search` and `<index>/_count`
- `GET` on `<index>/_mapping`
- `GET` on `_cat/indices`, `_cat/shards`, `_cluster/health` and `_nodes/stats`. The `_cat` reads
  show only the indices of JAVV.

These requests get 422, with the reason:

- a request on `system-users`, `system-sessions` or `system-tokens`
- a body with `script`, `script_fields`, `runtime_mappings`, `pit` or `scroll`
- a `size` larger than `JAVV_INSPECT_MAX_HITS`.

An answer larger than `JAVV_INSPECT_MAX_RESPONSE_BYTES` gets 413. A good answer is
`{took_ms, bytes, cap_bytes, body}`. The audit log keeps each query, with the user, the method and
path, and a hash of the query.

#### The jobs list

`GET /api/v1/admin/jobs` gives `{jobs, scheduler}`. `jobs` has one entry for each job kind:

- the last run: `status`, `requested_by`, `started_at`, `finished_at`, `result` and `error`. A job
  that never ran has `status: idle`.
- `stale`: `true` when a run is `running`, but it stopped its heartbeat.
- `runnable` and `capability`: if you can start the job with `POST .../run`, and the permission
  for it. `capability` is `null` for a job that you cannot start.
- `schedule`: the cron expression from `JAVV_JOB_<KIND>_CRON`, or `null`.
- `next_run_at`: the next run, in UTC. It is `null` when the job or the scheduler is off.
- `health`, one of these values. The first value that applies is the result:
    1. `failed`: the last run failed.
    2. `off`: the job has no schedule, or the scheduler is off.
    3. `never_ran`: the job has a schedule, but no run.
    4. `overdue`: two scheduled times passed after the last start.
    5. `ok`: all other cases.

`scheduler` is `{enabled, timezone}`: if this backend runs the schedules, and the time zone of the
cron expressions.

#### Start a background job

`POST /api/v1/admin/jobs/{kind}/run` starts one of three jobs:

| Kind | Permission |
|---|---|
| `rebuild_state` | `can_rebuild_state` |
| `staleness_sweep` | `can_manage_settings` |
| `lifecycle_sweep` | `can_drop_index` |

- The other five kinds, and a kind that does not exist, get 404.
- If a run of the job is in progress, the request gets 409. The scheduler applies the same rule.
  Thus one run of a kind at a time occurs.
- `?dry_run=true` applies to `lifecycle_sweep` only. It answers 200
  `{dry_run, result: {rolled, dropped, errors}}` with the counts that a run would give. It changes
  nothing. On the other kinds, `dry_run` gets 422.

### Findings: read

These endpoints need a session only. Each one needs `cluster_id`, except
`POST /api/v1/cursors/close`.

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/findings` | session | One page of findings, with a cursor ([Read a list page by page](#read-a-list-page-by-page)). `size` is 1 to 500, default 50. `sort` is `severity_rank`, `first_seen_at`, `last_scan_at`, `cvss` or `epss`. The last page closes the search of the cursor. With `keep_open=true`, a page read with a cursor keeps it open after the last page, so you can read an earlier page again. Then close it with `POST /api/v1/cursors/close`. |
| GET | `/api/v1/findings/facets` | session | The count of findings for each value of a field, for each scanner. `fields` is one or more of `severity`, `state`, `scanner`, `fixable`, `kev`, `disagree`, `present`, `ptype`, `namespaces`, `assignee`, `overdue` and `unassigned`. For `namespaces` and `assignee`, it gives the 32 largest values. |
| GET | `/api/v1/findings/groups` | session | Findings in groups, page by page with a cursor. `by` is `image_repo`, `image_digest`, `namespaces`, `cve_id`, `assignee`, `app` or `ptype`. |
| GET | `/api/v1/findings/top-components` | session | The packages with the most findings, and the count of different CVEs for each scanner. A past `as_of` gets 422. |
| GET | `/api/v1/trends/scans` · `/api/v1/trends/findings` | session | Counts for each day over `days` (1 to 365, default 30), for each scanner. [Trends](#trends) gives the details. |
| GET | `/api/v1/trends/ingest-failures` | session | The pushes that the ingest refused after the token check, for each time interval and scanner ([Trends](#trends)) |
| GET | `/api/v1/contributors` | session | The triage work of each user over `days` (1 to 365, default 30): actions, time to fix and SLA results. `totals` gives the same values for the team. |
| GET | `/api/v1/contributors/export.csv` | session | The data of `/contributors` as CSV. It has one `action_<name>` column for each triage action. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413. |
| GET | `/api/v1/scanners/freshness` | session | For each scanner of the cluster: `last_ingest_at` and `silent_for_seconds`. With no push yet, both are `null`. |
| GET | `/api/v1/scanners/ingest-failures` | session | The pushes that the ingest refused after the token check, newest first. `scanner` is necessary. `days` is 1 to 365 (default 30), and `size` is 1 to 100 (default 25). [Failed pushes](#failed-pushes) gives the fields. |
| GET | `/api/v1/scanners/provenance` | session | For each scanner: the versions and `effective_config` of the last committed run, and the last `runs` runs (1 to 50, default 10) |
| GET | `/api/v1/audit` | session | The audit log, page by page with a cursor. Filters: `entity_type`, `action`, `actor` and `finding_key`, each with an `exclude_` form except `finding_key`. `order` is `desc` (default) or `asc`. `keep_open` is as in `/findings`. Each row also shows the CVE, image and scanner of the finding or decision that it changed. |
| POST | `/api/v1/cursors/close` | session | Closes a cursor of `/findings` or `/audit` before its last page. Body: `{cursor}`. It closes the search of the cursor and frees your slot ([Exports and reports](#exports-and-reports)), and answers 204. A cursor of a different user, of a list that ended, or that expired also gets 204, and nothing changes. A cursor that is not valid gets 422. |
| GET | `/api/v1/audit/facets` | session | The counts of `entity_type`, `action` and `actor`, with the same filters. With `interval` (`day` or `hour`) and `window_days`, it also gives `activity`: the events in each interval. |
| GET | `/api/v1/audit/export.csv` | session | The audit log as CSV, with the same filters. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413. |
| GET | `/api/v1/images` | session | The running images: the images of the last committed inventory. It also shows images with no findings. If JAVV has no committed inventory, `inventory` is `null`. |
| GET | `/api/v1/images/timeline` | session | The scan history of one image tag. `image_repo` and `tag` are necessary. |
| GET | `/api/v1/clusters` | session | The clusters ([The clusters list](#the-clusters-list)) |

#### Filters

`/findings`, `/findings/facets`, `/findings/groups`, the findings exports and the saved views take
the same filters:

| Filter | What it selects |
|---|---|
| `severity` | `critical`, `high`, `medium`, `low`, `negligible` or `unknown`. The facet uses the same words. A row also shows the word of its scanner in `severity`. |
| `state` | `open`, `acknowledged`, `not_affected`, `risk_accepted`, `resolved` or `stale` |
| `scanner`, `assignee`, `namespace`, `image_repo`, `image_digest`, `cve_id`, `ptype` | The rows with that value |
| `package_name` | The rows with exactly that package name. It is not a facet. `fields=package_name` gets 422. |
| `kev`, `fixable`, `disagree` | `true` or `false` |
| `present` | `true` (default): the findings in the last scan. `false`: the findings that are gone. |
| `new_within_days` | The findings first seen in the last 1 to 365 days |
| `overdue` | `true` or `false`, from the SLA policy at the time of the request. A change of the policy changes the result at once. |
| `unassigned` | `true`: the rows with no owner. An empty `assignee` counts as no owner. |
| `q` | 2 to 128 characters. It finds the rows where `cve_id`, `image_repo`, `namespaces`, `assignee` or `package_name` contains the text, in any case. |

- Each filter except `kev`, `fixable`, `disagree`, `present`, `new_within_days`, `overdue`,
  `unassigned`, `image_digest` and `q` has an `exclude_` form, for example `exclude_severity`.
  An `exclude_` filter leaves out the rows with that value. A row with no value for the field stays.
  Thus `exclude_assignee=bob` keeps the rows with no owner.
- One field takes the filter or its `exclude_` form, not both. Both get 422.

#### A past time: `as_of`

Each read takes `as_of`. With no value, `now` or a time in the future, the read shows the current
state. With a time in the past, JAVV builds the state at that time from the history:

- `kev`, `epss`, `disagree`, `image_repo`, `tag` and `app` are not in the history. They are
  `null` in the rows.
- A filter, sort or group on one of these fields gets 422. `image_repo` and `exclude_image_repo`
  get 422 too.
- A facet on one of these fields gives no values.
- `ptype`, `package_name` and the `exclude_` filters on recorded fields apply as usual.
- The CSV and VEX exports of findings get 501. A report (`POST /api/v1/reports`) can use a past
  `as_of_t`.
- The audit log and the failed pushes end their window at that time.

#### Trends

- `/trends/scans`: the committed scans. `interval` is `day` (default) or `hour`. `hour` is
  possible only for 31 days or less, else 422. At a past `as_of`, the intervals are days.
- `/trends/findings`: the new findings and the resolved findings. `resolved` counts only the
  findings that a scan no longer showed (`resolved_semantics: "scan_resolved"`). A triage to
  `resolved` does not count. `split` is `scanner` (default) or `severity`. `split=severity` gets
  422 at a past `as_of`. `scanner` (`trivy` or `grype`) limits the series to one scanner.
- `/trends/ingest-failures`: the same `days` and `interval` as `/trends/scans`, so the two series
  align. It gives `{series: {<scanner>: [{date, count}]}, days, interval}`. With no refused push,
  `series` is `{}`.

#### Failed pushes

`GET /api/v1/scanners/ingest-failures` gives `{data, total, next_cursor}`. Each row has
`@timestamp`, `failure_id`, `scanner`, `stage`, `reason`, `status`, `error` and `image_ref`. The
`ingest rejected` log line has the same `failure_id`. The read uses no point in time. Thus a push
that fails during your read can show on a later page.

#### The clusters list

`GET /api/v1/clusters` gives each cluster that has a token, a name or a retirement record.
`cluster_name` is a name to show. JAVV never uses it in a query. Without a name, it is the
`cluster_id`. Each row has:

- `retired`. A retired cluster is in the list only with `?include_retired=true`. A cluster that
  sent a scan after its retirement is not retired.
- `last_scan_at`: the newest accepted scan, or `null`.
- `silent_since`: the start of the retirement countdown. This is the newest accepted scan, else the
  first token, or the return from retirement if that is later.
- `warns_at` and `retires_at`. `null` means that the cluster never retires.
- `delete_started`: `true` when a delete of the cluster started and did not finish. Delete it
  again.
- `retirement_mode`: `manual` or `auto` for a retired cluster, else `null`. A manual
  retirement revoked the tokens. To bring the cluster back, make a new token.

### Findings: triage and decisions

| Method | Path | Access | What it does |
|---|---|---|---|
| PATCH | `/api/v1/findings/{finding_key}/triage` | `can_triage` | Changes the state of one finding: `open`, `acknowledged`, `not_affected`, `risk_accepted` or `resolved`. `not_affected` needs a `vex_justification`. `risk_accepted` also needs `can_accept_audit_final`. |
| POST | `/api/v1/findings/bulk-triage` | `can_triage` | Changes the state of all the findings that a selector finds, now. More than `JAVV_BULK_INLINE_LIMIT` (5000) findings get 413. Use a report for more. A selector that finds more than `JAVV_BULK_MAX_TARGETS` (10000) gets 413. An empty selector gets 422. |
| POST | `/api/v1/decisions` | `can_triage` | Makes a decision. A `risk_accepted` decision also needs `can_accept_audit_final`. `expiry` is a date (`YYYY-MM-DD`), or a date and time with a time zone. JAVV keeps a date and time in UTC. |
| GET | `/api/v1/decisions` | session | Lists the decisions of the cluster, with `cve_id`, `include_revoked` (default `false`), `size` (1 to 500, default 50) and `offset` (0 to 10000) |
| PATCH | `/api/v1/decisions/{decision_id}` | `can_triage` | Changes a decision. JAVV never changes a decision. It revokes the old one and makes a new one, at the same time. |
| POST | `/api/v1/decisions/{decision_id}/revoke` | `can_triage` | Revokes a decision. Its effect on the findings stops. |
| GET | `/api/v1/decisions/approvals` | `can_accept_audit_final` | The approvals queue: the active risk acceptances, the nearest expiry first ([The approvals queue](#the-approvals-queue)) |
| GET | `/api/v1/decisions/approvals/export.csv` | `can_accept_audit_final` | The approvals queue as CSV, with the same filters ([The approvals queue](#the-approvals-queue)) |

#### The approvals queue

`GET /api/v1/decisions/approvals` takes `size` and `offset`, and these filters:

- `q`: a part of the CVE id.
- `status`: `active`, `expiring`, `expired` or `open-ended`. JAVV calculates it from `expiry` at the
  time of the request. `warn_days` (default 7) sets when `expiring` starts.
- `created_by`.
- `scanner`: `both`, `trivy` or `grype`.

Each filter except `q` has an `exclude_` form. The answer also has `facets`: the counts of `status`,
`created_by` and `scanner` with the same filters. A revoked acceptance is never in the queue.

The CSV export has the same rows. A file larger than `JAVV_EXPORT_MAX_ROWS` rows gets 413.
Two columns are different from the screen:

- JAVV calculates `status` for each row, with the same rules as the `status` filter.
- `scope_namespaces` and `scope_images` give the full lists. If both are empty, the acceptance
  applies to the full cluster.

### Settings

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/settings/sla` | session | The SLA policy: `critical_days`, `high_days`, `medium_days`, `low_days` and `kev_days` |
| PUT | `/api/v1/settings/sla` | `can_manage_settings` | Replaces the SLA policy |
| GET | `/api/v1/settings/staleness` | session | The staleness timers for `?cluster_id`: the value for the cluster, else the value for all clusters. `per_cluster_override` shows which one applies. |
| PUT | `/api/v1/settings/staleness` | `can_manage_settings` | Replaces the staleness timers. With `cluster_id` in the body, for that cluster. Without it, for all clusters. |
| GET | `/api/v1/settings/retirement` | session | The retirement window for `?cluster_id`: `retire_after_days` (`null` means never) and `warn_days`, with `per_cluster_override` |
| PUT | `/api/v1/settings/retirement` | `can_manage_settings` | Sets `retire_after_days` and `warn_days`. Both are necessary. `cluster_id` in the body applies as for staleness. A window that is not longer than the scanner-down timer gets 422. A `warn_days` that is not shorter than the window gets 422. |
| GET | `/api/v1/settings/scan-scope` | session | The scan scope of `?cluster_id` |
| PUT | `/api/v1/scan-scope` | `can_manage_settings` | Replaces the scan scope of a cluster: `include_namespaces`, `ignore_namespaces`, `exclude_images` and `ignore_kinds`. An empty include list means all namespaces. An ignore entry wins over an include entry. |
| GET | `/api/v1/settings/data` | `can_manage_retention` | The data settings for `?cluster_id`: retention, rollover, export lifetime, findings cleanup and the snapshot repository |
| PUT | `/api/v1/settings/retention` | `can_manage_retention` | Sets `retention_days`. `cluster_id` in the body applies as for staleness. |
| PUT | `/api/v1/settings/rollover` | `can_manage_retention` | Sets `max_age_days`, `max_docs` and `max_size_gb`. `cluster_id` in the body applies as for staleness. |
| PUT | `/api/v1/settings/report-ttl` | `can_manage_retention` | Sets the export lifetime in `hours`, for all clusters |
| PUT | `/api/v1/settings/findings-cleanup` | `can_manage_retention` | Sets `cleanup_days`: how long a finding that is gone stays. `cluster_id` in the body applies as for staleness. |

[Configuring JAVV](CONFIGURATION.md#runtime-settings) gives the defaults and the limits of each
runtime setting.

### Clusters

| Method | Path | Access | What it does |
|---|---|---|---|
| PUT | `/api/v1/clusters/{cluster_id}/name` | `can_manage_settings` | Changes the name that JAVV shows for a cluster. The `cluster_id` never changes. |
| POST | `/api/v1/clusters/{cluster_id}/retire` | `can_manage_settings` | Retires a cluster. It leaves the cluster list, and JAVV revokes its tokens. JAVV keeps its data. A cluster that does not exist gets 404. A retired cluster gets 409. |
| POST | `/api/v1/clusters/{cluster_id}/unretire` | `can_manage_settings` | Brings a retired cluster back to the list. Its tokens stay revoked. The retirement countdown starts again. A cluster that is not retired gets 409. A cluster with a delete that did not finish gets 409. |
| DELETE | `/api/v1/clusters/{cluster_id}` | `can_manage_retention` | Deletes a retired cluster ([Delete a cluster](#delete-a-cluster)) |

#### Delete a cluster

`DELETE /api/v1/clusters/{cluster_id}` deletes all the data of a retired cluster, except its rows
in the audit log. Snapshots from before keep the data.

1. It writes a marker for the delete.
2. It deletes the tokens of the cluster. A scanner that still pushes gets 401.
3. It deletes the history indices of the cluster.
4. It deletes the rows of the cluster in `findings`, `javv-scan-watermarks`, `javv-scan-orders`,
   `system-decisions`, `system-notifications` and `system-reports`.
5. It deletes the settings and the name of the cluster, then its retirement record.
6. It marks the delete as finished.

- A cluster that is not retired gets 409. A cluster that does not exist gets 404.
- If an admin brings the cluster back while the delete starts, only one of the two goes ahead.
  When the delete loses, it gets 409 and deletes nothing. When the bring back loses, it gets 409,
  and the delete continues.
- If a step cannot finish, or OpenSearch is not available, the request gets 503. Send the request
  again. The delete continues from the step that stopped.
- The answer is `{cluster_id, deleted: {<what>: count}}`.
- The marker stays. Each night, the retirement sweep deletes the rows that a push wrote after the
  delete. Before it deletes them, it writes an audit row with their counts. After a second pass with no rows, or if the cluster comes back, the sweep deletes the
  marker. A new token for the cluster's ID also deletes the marker: the cluster is back, and JAVV
  keeps its new data.
- A second delete of the same ID, after the cluster came back, writes its own marker.

### Saved views

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/views` | session | Lists the saved views. Each user can see each view. |
| POST | `/api/v1/views` | session | Saves a view. You are its `owner`. `preset` takes the [filters](#filters). A value that is not valid gets 422. `workbench` keeps the table setup: `columns`, `dense`, `sort`, `order` and `window_days`. |
| PATCH | `/api/v1/views/{view_id}` | session, the owner or `can_manage_settings` | Changes the name, the description, `preset` or `workbench`. A different user gets 403. A change by a different request first gets 409. |
| DELETE | `/api/v1/views/{view_id}` | session, the owner or `can_manage_settings` | Deletes a view (204). The audit log keeps a copy of it. |

### Exports and reports

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/findings/export.csv` | session | The findings of the [filters](#filters) as CSV. More than `JAVV_EXPORT_MAX_ROWS` (50000) rows get 413. Make the filter narrower, or use a report. |
| GET | `/api/v1/findings/export.vex` | session | The findings as an OpenVEX or CycloneDX document, for one scanner. `scanner` is necessary. The row limit is the same. |
| POST | `/api/v1/reports` | session, and `can_triage` for `bulk_triage` | Puts a job in the queue and answers 201. `kind: export` needs only a session. `kind: bulk_triage` needs `can_triage`, and `can_accept_audit_final` for a risk acceptance. A bulk triage keeps the list of findings at this time. Only the `JAVV_BULK_MAX_TARGETS` limit applies. Its `patch` takes the fields of `POST /api/v1/findings/bulk-triage` (`state`, `vex_justification`, `assignee` and `notes`), with the same limits. A different field gets 422. JAVV does not change a field whose value is `null`. |
| GET | `/api/v1/reports/{report_id}` | session, the owner | The status of your job. A job of a different user gets 404. When the job is `done` and not expired, the answer has a `download_token` for 15 minutes. |
| GET | `/api/v1/reports/{report_id}/download` | session, the owner, and `token` | Downloads the result. After `expires_at`, the request gets 410. With no result yet, it gets 404. A wrong or expired token gets 403. |

In each CSV file, JAVV puts an apostrophe before a cell that starts with `=`, `+`, `-`, `@`, a tab
or a carriage return. Thus a spreadsheet does not run the cell as a formula.

Each user can have `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` (default 10) open cursors and exports
at the same time. One more gets 429 with `Retry-After`. A cursor is open from its first page until
its last page, until you close it with `POST /api/v1/cursors/close`, or until
`JAVV_SEARCH_PIT_KEEP_ALIVE` plus 30 seconds after the last page that you read. JAVV keeps the result of a report in
OpenSearch for `JAVV_EXPORT_TTL_HOURS` (default 24). The `report_drain` job runs the queue, on
`JAVV_JOB_REPORT_DRAIN_CRON` (default every 5 minutes). A result larger than
`JAVV_EXPORT_MAX_BYTES` makes the job fail. Before a bulk triage job writes, it checks its patch
again. A patch that is not valid makes the job fail, and the `error` of the job names the field,
not its value. At the end of a job, a `report_ready` notification
goes to the user.

### Notifications

| Method | Path | Access | What it does |
|---|---|---|---|
| GET | `/api/v1/notifications` | session | Your 50 newest notifications, and `unread`, the count of the unread ones. Each item has `cluster_name`: the name of its cluster now, the `cluster_id` if the cluster has no name, or `null` if the item has no cluster. |
| PATCH | `/api/v1/notifications/{notification_id}/read` | session | Marks one of your notifications as read. A notification of a different user gets 404. |
| DELETE | `/api/v1/notifications/{notification_id}` | session | Deletes one of your notifications (204). A notification of a different user gets 404. |

The types are `report_ready`, `sla_breach`, `assignment` and `cluster_retiring`:

- The retirement sweep sends `cluster_retiring` to each user with `can_manage_settings` when a
  cluster starts its warning period. It sends it one time for each silence. `ref` is the
  `retires_at` of the cluster.
- The sweep deletes these notifications when the cluster scans again, or when a return from
  retirement starts a new silence. A change of the settings keeps them.

## Ingest a scan

`POST /api/v1/ingest/scan` accepts the results of one scan: an envelope with `schema_version` 3 or
4, as JSON. The body can have `Content-Encoding: gzip`. The findings of a version 3 envelope have
`ptype: null`. [Push from your own script](INGEST-CONTRACT.md) gives the schema, the order of the calls
and an example.

The backend does these checks in this order:

1. The `Authorization` header starts with `Bearer `.
2. The token is not over its rate limit. The limit applies to each token value, before the backend
   looks for the token.
3. The token exists, is not disabled, and is not expired.
4. The compressed body is not larger than its limit. The backend counts the bytes as they arrive,
   and does not trust `Content-Length`.
5. The body after gzip is not larger than its limit.
6. The body is JSON.
7. The envelope is valid. A field that the schema does not have makes it not valid.
8. The `cluster_id` and `scanner` of the envelope are the ones of the token.
9. The `scan_order` is not larger than the largest one that `POST /api/v1/scan-runs` gave to this
   cluster and scanner.
10. The `last_seen_at` is not more than `JAVV_INGEST_FUTURE_TOLERANCE_MINUTES` ahead of the
    backend's clock, and not older than the staleness period of the cluster.

Then the backend writes the findings. Each finding has a fixed id. Thus when a scanner sends the
same envelope again, JAVV keeps one copy.

| Status | When |
|---|---|
| 202 | The backend accepted the envelope: `{accepted, findings, commit}` |
| 400 | The body is not valid gzip, or not valid JSON. |
| 401 | The token is missing, not valid, disabled or expired. Each of these gets the same answer. |
| 403 | The `cluster_id` or the `scanner` of the envelope is not the one of the token. |
| 413 | The compressed body or the body after gzip is larger than its limit. |
| 422 | The envelope is not valid. Examples: a field that the schema does not have, a `cluster_id` that is not valid, or counts that do not agree. A time with no time zone and a `schema_version` that is not 3 or 4 also get 422. A `scan_order` that `POST /api/v1/scan-runs` did not give gets 422 with `reason` `unallocated_order`. A `last_seen_at` too far ahead or too old gets `clock_skew`. A value that OpenSearch refuses to store also gets 422. The scanner does not try again. |
| 429 | The token is over its rate limit. |
| 503 | OpenSearch could not keep the data, or OpenSearch is not reachable. The scanner tries again. |

[Configuring JAVV](CONFIGURATION.md#scanner-pushes) gives the limits and their defaults.

### Logs of a refused push

Each refused push increments `javv_ingest_rejected_total{reason}`. A push that the backend refused
after the token check (400, 403, 413, 422 or 503) also writes one `ingest rejected` warning. The
warning has these fields:

- always: `reason`, `status`, the `cluster_id` and `scanner` of the token, and `failure_id`
- on a 413: `limit_bytes`
- on a 422 for an envelope that is not valid: `errors`, the count of errors
- on a 422 for `unallocated_order`: `scan_order`, and `max_allocated`, the largest order given
- on a 422 for `clock_skew`: `last_seen_at`, and `freshness_days` when the time is too old
- on a 503 because OpenSearch is not reachable: `error`, the kind of the connection error
- on a 403: `payload_cluster_id` and `payload_scanner`.

The backend never logs the token. A 429 writes one warning for each token in each minute, at
most. A 401 writes no warning, so that a sender with no token cannot fill the log.

### Records of a refused push

The backend also keeps each push that it refused after the token check. It writes one document to
`javv-ingest-failures-<cluster_id>`, with the cluster and scanner of the token. The **Failed
ingests** table on the **Scanner status** page and `GET /api/v1/scanners/ingest-failures` show
these documents. A 401 and a 429 make no
record.

The answer to the scanner does not depend on the record. If the backend cannot write the record,
it logs `ingest failure not recorded` with the `failure_id`. It also increments
`javv_ingest_failures_unrecorded_total{reason}`.

## Metrics

`GET /metrics` gives these metrics, in the Prometheus format ([Scrape the metrics](#scrape-the-metrics)).

| Metric | Type | Labels | What it counts |
|---|---|---|---|
| `javv_ingest_accepted_total` | counter | `scanner` | Envelopes that the backend accepted and wrote |
| `javv_ingest_rejected_total` | counter | `reason` | Envelopes that the backend refused. `reason` is `bad_token`, `rate_limited`, `too_large`, `bad_gzip`, `bad_json`, `invalid_envelope`, `unallocated_order`, `clock_skew`, `scope_mismatch` or `storage_error`. |
| `javv_ingest_failures_unrecorded_total` | counter | `reason` | Refused pushes with no record ([Records of a refused push](#records-of-a-refused-push)). A value larger than 0 means that the **Failed ingests** table does not show all the refused pushes. |
| `javv_ingest_findings_written_total` | counter | `scanner` | Findings that the backend wrote |
| `javv_http_request_duration_seconds` | histogram | `method`, `route`, `status` | The time of each request. `route` is the route pattern, not the full path. A path with no route counts as `unmatched`. `/metrics` and the probes are not counted. |
| `javv_opensearch_request_errors_total` | counter | `kind` | Failed requests to OpenSearch: `conn` and `timeout` on reads, `429` and `503` on writes. `429` also counts each request that got 429 "The search backend is busy". The backend logs `store busy` for these at most once in 10 seconds, with `held_back`. |
| `javv_opensearch_backoff_retries_total` | counter | none | Writes that OpenSearch refused with 429 or 503, and that the backend sent again. A high rate means that OpenSearch is too busy. |
| `javv_sla_clock_missing_total` | counter | none | Pages of findings with a row that has no `sla_clock_at`. The backend calculates the value for these rows, and logs a warning. A steady rate means that the store needs the `rebuild_state` job. |
| `javv_cas_conflicts_total` | counter | `site` | Writes that lost a race to a different writer: `watermarks`, `scan_orders`, `inventory_orders`, `reconcile`, `reproject`, `merge`, `report_claim` and `retirement`. A high rate means many writers on the same data. |
| `javv_limit_rejections_total` | counter | `limit` | Requests that a limit refused: `pit_cap`, `export_rows`, `bulk_targets`, `bulk_inline`, `client_events` and `inspect_bytes` |
| `javv_pits_open` | gauge | none | The cursors and exports that are open now. A cursor that a client stopped using counts until `JAVV_SEARCH_PIT_KEEP_ALIVE` plus 30 seconds after the last page that the client read, and then stops counting. |
| `javv_export_rows_total` / `javv_export_bytes_total` | counter | `format` | The rows and bytes that the exports sent. If a client stops the download, the count shows what it received. |
| `javv_auth_failures_total` | counter | `reason` | `bad_credentials`, `locked_out`, `expired_session`, `missing_capability`, `must_change` (a session with a temporary password) or `session_not_minted` (a password change with no new session). The labels never show a username. |
| `javv_config_warnings_total` | counter | `setting` | Starts with a weak connection to OpenSearch: `JAVV_OPENSEARCH_VERIFY_CERTS` (the certificate is not checked on `https`) or `JAVV_OPENSEARCH_URL` (a password over plain `http`). Each one also logs a warning at the start. |
| `javv_stored_setting_unknown_fields_total` | counter | `setting` | Reads of a runtime setting that had fields this release does not know. The backend ignores these fields. After a rollback, a value larger than 0 means that a newer release saved that setting. `setting` is `sla`, `scan_scope`, `snapshot_repo`, `report_ttl`, `lifecycle`, `findings_cleanup`, `staleness`, `retirement` or `cluster-retirement`. |
| `javv_job_runs_total` | counter | `kind`, `outcome` | Background jobs that the scheduler started. `outcome` is `done`, `failed` or `skipped`. `skipped` means that a different run held the job. A steady `failed` rate is a job that fails each time. No `done` over the schedule of a job is a job that does not run. |
| `javv_job_last_success_timestamp_seconds` | gauge | `kind` | The Unix time of the last successful scheduled run in this process. It is 0 after a restart, until a run succeeds. Alert on `time() - value`, against the schedule of the job. |
| `javv_scheduler_tick_errors_total` | counter | none | Scheduler ticks that failed before a job started, usually because OpenSearch was not available. A steady rate means that no job runs. |
| `javv_cluster_retirement_held_total` | counter | none | Retirement sweeps that retired nothing, because no cluster sent an accepted scan in its scanner-down time. This points at JAVV, an outage or a refused scanner version, not at the clusters. Each one also logs a warning. |
| `javv_store_unavailable_total` | counter | none | Requests that got 503 because OpenSearch was not reachable or still starting. The counter counts each one. The backend logs `store unavailable` at most once in 10 seconds, with `held_back`: the count since the line before. Any sender can repeat a request while OpenSearch is away. |
| `javv_store_read_only_total` | counter | none | Writes that got 503 `store-read-only` because the disk of OpenSearch is past its flood-stage watermark. The counter counts each one. The backend logs `store read-only` at most once in 10 seconds, with `held_back`. |
| `javv_cluster_delete_incomplete_total` | counter | none | Cluster deletes that stopped and answered 503. Send the delete again to finish it. Each one also logs a warning. |
| `javv_cluster_delete_leftovers_total` | counter | none | Deleted clusters with rows that a push or a job wrote after the delete. The retirement sweep deleted those rows, after it wrote an audit row with their counts (action `cluster_delete_recheck`). Each one also logs a warning. |
| `javv_cluster_delete_recheck_failures_total` | counter | none | Deleted clusters that the retirement sweep could not check, or sweeps that could not check any. The sweep goes on to the next deleted cluster, and the next run checks them again. Each one also logs a warning. |
| `javv_cluster_retirement_notify_failures_total` | counter | none | Retirement sweeps that could not write or delete their notifications. The retirements stay, and the next run tries again. Each one also logs a warning. |

The backend also gives the default process and garbage collection metrics of `prometheus_client`.
A scrape does not use OpenSearch. Thus the metrics stay available during an OpenSearch outage.
The backend runs one process, and the metrics are for that process.

## Client events

| Method | Path | Access | What it does |
|---|---|---|---|
| POST | `/api/v1/client-events` | session | Writes the warnings and errors of the browser to the backend log, and answers 204. It keeps nothing in OpenSearch and writes no audit row. |

The body is `{events: [{level, event, fields}]}`, with 1 to 20 events:

- `level` is `warn` or `error`. Other values get 422.
- `event` matches `^[a-z0-9][a-z0-9 ._-]{0,63}$`.
- `fields` has at most 25 keys in each object, at most 3 levels, keys of at most 64 characters,
  values of at most 512 characters, and lists of at most 20 items.

A body that does not agree with these rules gets 422.

The backend writes each event as `client.<event>`, with `client_event=true` and the `username`.
Thus an event from a browser cannot look like an event of the backend. The `fields` of the event
stay under one `fields` key. Thus a browser cannot set the `username` of the log line. The log
redaction also applies inside `fields`.

Each user can send `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE` requests in each minute. One more
gets 429 with `Retry-After`. It also increments `javv_limit_rejections_total{limit="client_events"}`
and logs a warning. The backend checks the body before the rate limit. Thus a refused body writes
nothing to the log.

A session with a temporary password gets 403. A request with no session gets 401.

## Logs

The backend writes JSON log lines to its standard output.

- **Request id:** each line of a request has its `request_id`. [Errors](#errors) tells how to set
  it. Each line of a push also has the `cluster_id` and `scanner`.
- **Unexpected errors:** an error with no handler logs one `unhandled error` line at the `error`
  level, with the stack, `method`, `path` and `request_id`. The answer is a 500 with the same
  `request_id`.
- **Redaction:** the backend replaces the value of each key that contains `token`, `secret`,
  `password`, `authorization`, `pepper`, `session` or `cookie`. It also replaces each `Bearer ...`
  text. No log line has a token.
- **OpenSearch bodies:** the backend never logs the body of a request to OpenSearch, or of its
  answer, at any log level.
