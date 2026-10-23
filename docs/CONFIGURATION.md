# Configuring JAVV

This page lists the settings of JAVV, for the people who install and operate JAVV. For each
setting, it gives:

- The default.
- What the setting does.
- Where you set it.

## Where the settings are

| Kind | Where you set it | When a change applies |
|---|---|---|
| Backend, frontend server and scanner settings | Environment variables: `.env` for compose, the chart values for Helm | When the container starts again. A scanner reads its settings at the start of each cycle. |
| [Runtime settings](#runtime-settings): retention, staleness, SLA, scan scope, retirement | The **Settings** pages of the web app, or the API | JAVV keeps them in OpenSearch. Each reader uses the new value at its next read. |
| Scanner and OpenSearch versions | The image tag | When you change the tag. The web app has no control to select a version. |
| [Frontend build settings](#frontend-build-settings) | The build of the frontend image | Only when you build a new image. A published image has the default values. |

**Credentials:**

- Credentials go only in a secret store: `.env`, a Kubernetes Secret or the OpenSearch keystore.
- JAVV never keeps a credential in an image or in its runtime settings.
- In the tables below, a **Secret** row holds a credential.

**Checks at start:** the backend checks its settings when it starts. A value that is not valid
stops the start, and the error names the setting. Thus a bad value does not let the backend pass
`/readyz` and then fail each request. Examples of bad values:

- a limit of zero or less
- a keep-alive that is not a duration
- a compressed limit larger than the decompressed limit
- a bulk inline limit larger than the bulk maximum.

## Change a setting

### With docker compose

1. Add `NAME=value` to the `.env` file next to `compose.yaml`.
2. Run `docker compose up -d`. Compose starts again each container whose settings changed.

[`compose.yaml`](../deploy/compose/compose.yaml) lists each setting, with its default and a short
description.

### With Helm

1. Set the value in your values file, or with `--set`:
    - a backend setting: `backend.config.<NAME>` in the `javv` chart
    - a frontend server setting: `frontend.config.<NAME>` in the `javv` chart
    - a scanner setting: `trivy.config.<NAME>` or `grype.config.<NAME>` in the `javv-scanner` chart.
2. Run `helm upgrade` with your values. Kubernetes starts new pods with the new value.

### In the web app

1. Sign in as a user with the permission that the setting needs ([Runtime settings](#runtime-settings)).
2. Open **Settings**, then the page that holds the setting.
3. Change the value, then save it.

## Backend settings

The backend reads these environment variables.

- It ignores a `JAVV_` name that it does not know.
- [`compose.yaml`](../deploy/compose/compose.yaml) lists each one with its default.
- The `javv` chart sets each one under `backend.config`.
- `backend/tests/test_compose_settings.py` keeps both equal to the code.

### Deployment

| Setting | Default | What it does |
|---|---|---|
| `JAVV_ENV` | `dev` | The deployment profile. `prod` or `production` changes dev conveniences into start failures. At this time, the start stops when `JAVV_SECRET_KEY` has its dev value. Set `prod` on each real deployment. |
| `JAVV_LOG_LEVEL` | `info` | The log level: `debug`, `info`, `warning` or `error`. A different value stops the start. At `debug`, the log also shows one line for each OpenSearch request, with its method, path, status and time. The log never shows the body of a request or a reply. All lines go to one JSON stream, with the same redaction. |
| `JAVV_SECRET_KEY` | `dev-only-secret-key` | **Secret.** The secret key of the backend. The backend hashes each ingest token and session id with it before it stores them. It also signs the download links of reports with it. **Set it to a long random string on each deployment, and keep it**. If you change it, each scanner gets 401, each user must sign in again, and each open download link stops working. The stored data cannot restore them: each scanner needs a new token. With `JAVV_ENV=production`, the dev default **stops the start**. Before 0.7.0, the name was `JAVV_TOKEN_PEPPER`. A backend that finds that name stops at start ([Upgrading](UPGRADING.md#version-notes)). |
| `JAVV_BOOTSTRAP_ADMIN_USERNAME` | `admin` | The username of the first admin. It has the same rule as each other username: 3 to 64 lower-case letters, digits, dots, underscores or hyphens, and not `system` or `fleet`. A different value stops the backend at start ([Upgrading](UPGRADING.md#version-notes)). |
| `JAVV_BOOTSTRAP_ADMIN_PASSWORD` | empty: no first admin | **Secret.** The password of the first admin. The backend uses it only when that admin does not exist. A later change of this value has no effect: change the password in the web app. The first admin must change the password at the first sign-in. At most 256 characters: a longer value stops the backend at start. The backend accepts fewer than 12 characters, because the first sign-in changes the password. |

### Connection to OpenSearch

| Setting | Default | What it does |
|---|---|---|
| `JAVV_OPENSEARCH_URL` | `http://localhost:9200` | The address of OpenSearch. A URL that holds a user or a password stops the start. Examples are `https://user:pass@host`, and `user:pass@host` with no scheme, which the client reads as plain `http`. Put the credentials in the two settings below. |
| `JAVV_OPENSEARCH_USERNAME` | empty: no sign-in | The OpenSearch user that JAVV signs in as. Set it together with the password. Leave both empty only for an OpenSearch without its security plugin. The user needs the `javv` role ([An OpenSearch of your own](DEPLOYING.md#an-opensearch-of-your-own)). Compose makes the user `javv` and sets it here. |
| `JAVV_OPENSEARCH_PASSWORD` | empty | **Secret.** The password of that user. The backend never writes it: not in a log line, a settings error or a start error. If OpenSearch replies 401 or 403 at start, the backend stops with "OpenSearch refused the credentials…". With an `http://` URL, the credentials go in clear text. Then the backend starts with a warning and `javv_config_warnings_total{setting="JAVV_OPENSEARCH_URL"}`. |
| `JAVV_OPENSEARCH_CA_BUNDLE` | empty: the CAs of the system and of certifi | The path to a PEM file of CA certificates, for an OpenSearch certificate from a private CA. A path with no readable file stops the start. An empty value means no file. |
| `JAVV_OPENSEARCH_VERIFY_CERTS` | `true` | Check the certificate and the host name of OpenSearch on an `https` URL. Set `false` only for an OpenSearch that you trust for other reasons. An example is the demo certificates of OpenSearch on a network that nothing else can reach. With `false`, the backend starts with one warning and `javv_config_warnings_total{setting="JAVV_OPENSEARCH_VERIFY_CERTS"}`. `false` together with a CA bundle stops the start, because the backend would not use the bundle. |
| `JAVV_REQUEST_TIMEOUT` | `30.0` | Seconds that the backend waits for OpenSearch to reply to a request. |
| `JAVV_BOOTSTRAP_ON_STARTUP` | `true` | Before it serves, the backend checks OpenSearch and creates or updates its indices. If the check fails, the backend stops. Keep `true` on a deployment. With `false`, the backend checks nothing at start. Then a wrong OpenSearch password shows only later: `/readyz` replies 503, and each request to OpenSearch fails. opensearch-py logs each failure at `warning`, with the 401. |

### Sign-in

| Setting | Default | What it does |
|---|---|---|
| `JAVV_SESSION_TTL_HOURS` | `24.0` | Hours that a sign-in lasts. The session record on the server decides. The lifetime of the cookie is only advice to the browser. |
| `JAVV_SESSION_COOKIE_SECURE` | `true` | The `Secure` flag of the session cookie. A browser keeps a `Secure` cookie only from `https` or `localhost`. If users open JAVV over plain `http`, set `false`. Else the sign-in fails, and the sign-in page says that the browser refused the session cookie. An example is a machine on a LAN with no TLS in front. Keep `true` behind each proxy that ends TLS. JAVV cannot see that proxy, so it never sets the flag itself. Sign-out clears the cookie with the same flag. |
| `JAVV_SESSION_SWEEP_GRACE_HOURS` | `24.0` | Hours that the record of an expired session stays before the session sweep deletes it. A revoked session goes the same way after this time. An expired record cannot sign in, and it holds only a hash of the cookie. Thus a longer time costs only disk space. `0` deletes the record when it expires. Each run writes one `session_sweep_run` entry to the audit log, with its counts. |
| `JAVV_LOGIN_MAX_ATTEMPTS` | `5` | Failed sign-ins for one username in the window, in all cases of the name together (`Alice` and `alice` are one count). After this number, the backend replies 429. |
| `JAVV_LOGIN_LOCKOUT_MINUTES` | `15.0` | The window of the sign-in lock, in minutes. The backend keeps the count in its memory. |

### Scanner pushes

| Setting | Default | What it does |
|---|---|---|
| `JAVV_INGEST_MAX_COMPRESSED_BYTES` | `10485760` (10 MiB) | The largest push as it arrives, still compressed. The backend counts the bytes while it reads them. |
| `JAVV_INGEST_MAX_BODY_BYTES` | `62914560` (60 MiB) | The largest push after decompression. This limit stops a zip bomb. |
| `JAVV_INGEST_RATE_LIMIT_PER_MINUTE` | `120` | Pushes for each token in one minute. |
| `JAVV_INGEST_FUTURE_TOLERANCE_MINUTES` | `15` | How far ahead of the backend's clock a scan time (`last_seen_at`) can be. A push with a later time gets 422 (`clock_skew`): with it, the finding would stay open until that date. A scan time older than the cluster's staleness period also gets 422, so a wrong clock cannot make findings stale either. |

### Triage, search and exports

| Setting | Default | What it does |
|---|---|---|
| `JAVV_BULK_INLINE_LIMIT` | `5000` | A bulk triage action on this number of findings or fewer applies at once. The reply is 200 with the result, and the audit log gets one entry. Above this number, the backend replies 413. Then make the selection smaller, or use a scheduled bulk action. |
| `JAVV_BULK_MAX_TARGETS` | `10000` | The most findings that a bulk selection can hold. A selection that matches more gets 413 ("selector too broad"). This limit bounds the memory that a bulk action uses. |
| `JAVV_SEARCH_PIT_KEEP_ALIVE` | `2m` | How long a findings search (a point in time, PIT) stays open between two pages. Each page starts this time again. A search that the client stops using closes itself after this time. A longer time lets a client wait longer between pages. A shorter time keeps fewer searches open. |
| `JAVV_EXPORT_MAX_ROWS` | `50000` | The most rows of an immediate ("run now") export: findings CSV and VEX, audit CSV, contributors CSV and approvals CSV. Before it reads the rows, the backend counts them. Above the limit, it replies 413. Then make the filters smaller, or use a scheduled export. The contributors CSV counts its rows only after the query. Its list holds 100 people at most, so it does not get to this limit. Scheduled exports do not use this limit. |
| `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL` | `10` | The most searches and exports that one user or token can keep open at one time. Above this number, the backend replies 429 with `Retry-After`. The backend keeps the count in its memory. The web app closes each search that it stops using (`POST /api/v1/cursors/close`). A search that the client does not close frees its slot 30 seconds after its keep-alive ends. |
| `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE` | `60` | Batches of browser warnings and errors that one user can send in one minute. A batch holds 20 events at most. The browser never sends a batch again, so a 429 here loses those events without a sign. Thus the default is well above the rate of a normal session. This limit controls only the volume of the log. The shape limits of a batch are part of the API ([Fixed values](#fixed-values)). |

### Scheduled exports

| Setting | Default | What it does |
|---|---|---|
| `JAVV_EXPORT_TTL_HOURS` | `24` | Hours that JAVV keeps a finished export. After this time, the report sweep deletes the export, and a download gets 410. **Settings › Data & OpenSearch** can change it. This value applies until you save a value there. |
| `JAVV_EXPORT_MAX_BYTES` | `524288000` (500 MiB) | The largest single export. The report drain marks a larger export as failed. Thus one export cannot fill OpenSearch. |
| `JAVV_REPORT_DRAIN_SLEEP_MS` | `200` | The pause between two pages of an export, in milliseconds. Thus a large export does not slow the scanner pushes. |
| `JAVV_REPORT_LEASE_TTL_SECONDS` | `300` | Seconds that a running export or background job holds its lease. The worker writes a heartbeat. After this time with no heartbeat, the next run takes the work and counts one retry. Make this time fit `JAVV_JOB_REPORT_DRAIN_CRON`. A background job with no heartbeat for this time shows as `stale`, and a new start can take it. |

### Data inspector

| Setting | Default | What it does |
|---|---|---|
| `JAVV_INSPECT_MAX_HITS` | `500` | The largest `size` of one search in the Data inspector. A larger request gets 422, with the reason. |
| `JAVV_INSPECT_MAX_RESPONSE_BYTES` | `2097152` (2 MiB) | The largest reply of the Data inspector. A larger reply gets 413 ("narrow the query"). The backend also logs a warning and adds one to `javv_limit_rejections_total{limit="inspect_bytes"}`. |
| `JAVV_INSPECT_TIMEOUT_SECONDS` | `10.0` | Seconds that a query of the Data inspector can run in OpenSearch. This time is shorter than `JAVV_REQUEST_TIMEOUT`. Thus a query in the inspector cannot hold OpenSearch for long. |

### Cluster retirement

| Setting | Default | What it does |
|---|---|---|
| `JAVV_CLUSTER_RETIRE_AFTER_DAYS` | `45` | Days with no accepted scan before the daily sweep retires a cluster. A retired cluster is not on the cluster list, and JAVV keeps its data. `0` means never. This value must be larger than `JAVV_CLUSTER_RETIREMENT_WARN_DAYS`. The backend checks this at start. **Settings › Cluster** can change it. This value applies until you save a value there. |
| `JAVV_CLUSTER_RETIREMENT_WARN_DAYS` | `7` | Days before the retirement when the warning banner starts and each user with `can_manage_settings` gets a notification. **Settings › Cluster** can change it. This value applies until you save a value there. |

### Background jobs

| Setting | Default | What it does |
|---|---|---|
| `JAVV_SCHEDULER_ENABLED` | `true` | The backend runs its background jobs itself. Thus a deployment is one backend container and one frontend container, with no CronJob for a job. `false` stops all the schedules and keeps the values below. You can still run a job by hand (`python -m backend.jobs.<name>`), or from the Data inspector. |
| `JAVV_JOB_REPORT_DRAIN_CRON` | `*/5 * * * *` | When the report drain runs. It builds the queued exports and bulk actions. When several jobs are due, this job starts first. |
| `JAVV_JOB_REPORT_SWEEP_CRON` | `15 * * * *` | When the report sweep runs. It deletes expired exports, old failures and their remaining chunks. |
| `JAVV_JOB_STALENESS_SWEEP_CRON` | `0 2 * * *` | When the staleness sweep runs. It marks findings stale on the two [staleness](#staleness) timers. It also opens findings again when their risk acceptance expires. |
| `JAVV_JOB_LIFECYCLE_SWEEP_CRON` | `0 3 * * *` | When the lifecycle sweep runs. It starts new history indices (rollover), and it deletes the indices that are older than the [retention](#retention-and-rollover) of each cluster. |
| `JAVV_JOB_FINDINGS_CLEANUP_CRON` | `0 4 * * *` | When the findings cleanup runs. It deletes rows of the `findings` cache that no scan found for longer than the [cleanup window](#findings-cleanup). |
| `JAVV_JOB_CLUSTER_RETIREMENT_CRON` | `15 4 * * *` | When the retirement sweep runs. It retires the clusters that sent no scan for longer than their [window](#cluster-retirement-window). It returns the clusters that scan again. It also deletes the rows that arrived after the deletion of their cluster, and first writes an audit row with their counts. |
| `JAVV_JOB_SESSION_SWEEP_CRON` | `30 4 * * *` | When the session sweep runs. It deletes the sessions that expired longer ago than `JAVV_SESSION_SWEEP_GRACE_HOURS`. |

### Job schedules and the time zone

Each `JAVV_JOB_<KIND>_CRON` is a cron expression with five fields: minute, hour, day of month,
month and day of week.

- The backend does not accept shortcuts such as `@daily`.
- An empty value means that the job never runs on a schedule.
- An expression that is not valid stops the start, and the error names the setting.

- One job runs at a time. When several jobs are due, the report drain starts first.
- A job does not run because the backend started. Each job waits for its next scheduled time.
- A restart can stop a job before it ends. That job runs again when its lease becomes stale
  (`JAVV_REPORT_LEASE_TTL_SECONDS`).
- `rebuild_state` has no schedule. You run it only by hand.

The backend reads the expressions in its local time zone. It finds the zone in this sequence:

1. the `TZ` environment variable, for example `TZ=Europe/Bucharest`
2. the zone that `/etc/localtime` links to
3. UTC.

- A `TZ` name that the zone database does not know also gives UTC, and the backend still starts.
- The log line `scheduler started` shows the zone that the backend uses, in `zone` and
  `zone_source` (`TZ`, `system` or `default`). Examine that line after you change `TZ`.
- A container has no zone of its own. Thus set `TZ` if `0 3 * * *` must mean 03:00 local time.
- Backends that use the same OpenSearch must use the same zone.
- When the clock goes back one hour, a local time that occurs two times runs one time. When the
  clock goes forward, a local time that does not exist runs at the first time after the gap. Thus
  a daily job runs on each day.

### The javv chart

The `javv` chart sets each backend setting under `backend.config`, by its environment name and at
its default.

- To change one, use `--set backend.config.<NAME>=<value>` or your values file.
- The secrets are not in `backend.config`.

These values are not settings of the backend:

| Value | Default | What it does |
|---|---|---|
| `secrets.existingSecret` | `""` | **Secret.** A Secret with the keys `secret-key` (`JAVV_SECRET_KEY`) and `bootstrap-admin-password` (`JAVV_BOOTSTRAP_ADMIN_PASSWORD`). Or set `secrets.secretKey` and `secrets.bootstrapAdminPassword`, and the chart puts them in a Secret. Without them, the install fails. The chart never makes a secret key. |
| `opensearch.passwordSecret.name` / `.key` | `""` / `password` | **Secret.** The Secret with the password of `javv` (`JAVV_OPENSEARCH_PASSWORD`). Use the backend Secret of the `javv-opensearch` chart, never the admin password. Without it, the install fails. |
| `opensearch.caSecret.name` / `.key` | `""` / `ca.crt` | A Secret with the CA of the OpenSearch certificate. When you set it, the chart mounts it at `/etc/javv/opensearch-ca/`. The chart then sets `JAVV_OPENSEARCH_CA_BUNDLE` to it and `JAVV_OPENSEARCH_VERIFY_CERTS` to `true`. These are the only settings that the chart calculates. |
| `backend.startupProbe` | `GET /healthz`, each 10 s, 30 tries | 300 s for the first start, which is ten `JAVV_REQUEST_TIMEOUT` periods. The backend creates or updates the indices before it opens its port. |
| `backend.readinessProbe` / `livenessProbe` | `GET /readyz` each 10 s / `GET /healthz` each 20 s, 3 failures each | While OpenSearch is unreachable, the Service sends no requests to the backend. It restarts the backend only when the backend itself does not reply. |
| `frontend.config` | `JAVV_BACKEND_URL` empty (the backend Service of the chart), `JAVV_BACKEND_CONNECT_TIMEOUT` `5`, `JAVV_LOG_LEVEL` `info` | The [frontend server settings](#frontend-server-settings). |
| `frontend.replicas` / `frontend.service.type` / `.port` | `1` / `ClusterIP` / `8080` | The Service that browsers and scanners use. The chart makes no Ingress. |

The backend runs as one replica with `strategy: Recreate`. No value changes this.

## Scanner settings

Each scanner runs as a CronJob in a cluster that you scan. It keeps no state from one cycle to the
next.

- The scanner checks each value that you set when it starts.
- A value that is not valid stops the scanner with exit code 2, and the error names the setting.
  Examples are an unknown scanner name, a URL with no scheme, a cluster id with a bad shape and an
  unknown flag.
- A setting that you do not set always has the default in the table.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_SCANNER` | `trivy` | The scanner that this pod runs: `trivy` or `grype`. Each image sets it in its `ENV`. A different value stops the scanner with exit code 2. |
| `JAVV_LOG_LEVEL` | `info` | The log level, as for the backend. At `info`, the log shows the progress of each image (`scanning image`, then `scan done` with the findings and the time) and a summary of the cycle. At `warning`, it shows the skipped images and the dead-letter entries. The line for a skipped image has `reason`: `scanner_exit`, `timeout` or `error`. With `scanner_exit`, it also has `exit_code` and `scanner_stderr`. `scanner_stderr` holds the last 5 lines of the error output of the scanner, 1000 characters at most. With `timeout`, it also has `timeout_s`. The `scope applied` line gives the pods that the scan scope skipped: `pods_running`, `skipped_namespace`, `skipped_kind` and `skipped_image`. `skipped_kind` gives a count for each listed kind. A listed kind with 0 skipped no pod. The `cycle complete` line gives `discovered`, `scanned` and `scan_failed`. Each line has `scanner`, `cluster_id` and `scan_run_id`. |
| `JAVV_BACKEND_URL` | `http://localhost:8000` | The JAVV address that the scanner pushes to. |
| `JAVV_TOKEN` | not set | **Secret.** The ingest token, with the `push:findings` scope. You must set it. At the start of a cycle, the scanner gets its scan scope from JAVV. Without a token, that request gets 401, and the scanner skips the cycle. |
| `JAVV_CLUSTER_ID` | the UID of `kube-system` | The id of the cluster in JAVV: the UID of the `kube-system` namespace, which never changes. JAVV never uses the cluster name for this. When you set it, the scanner compares it with the UID of the cluster that it connected to. If the two are different, the scanner stops the cycle with exit code 2. |
| `JAVV_KUBE_CONTEXT` | the current context | Only outside a cluster: the kubeconfig context to scan. Inside a cluster, the scanner ignores it. When you do not set it, the scanner uses the current context. For this reason, `JAVV_CLUSTER_ID` can check the cluster. |
| `JAVV_DEAD_LETTER` | `<scanner>.dead-letter.jsonl`. The images set `/var/lib/javv/<scanner>.dead-letter.jsonl`. | The file for the pushes that JAVV did not accept. The scanner adds each of these pushes to the file as one JSON line, logs `envelope dead-lettered`, and continues with the next image. A refusal with a 4xx that is not 429 goes there immediately. A 429, a 5xx or no answer goes there when the retry budget is spent. The scanner does not send the file again. An image whose scan failed is not in this file: the log has it (`scan failed, image skipped`). |
| `JAVV_PUSH_RETRY_BUDGET_SECONDS` | `360` | How long one cycle can try again, in total, when JAVV does not accept a push or the inventory commit. Examples are a 429, a 5xx or no answer. The scanner waits longer each time, at most 30 seconds. The time counts from the first failure of a push to its end. When the cycle used all of it, a push that fails goes to the dead-letter file with no wait. The log then shows `push retry budget spent` one time. The default is longer than the 300 seconds that a `helm upgrade` of JAVV gives the backend to start. A value that is not a whole number above 0 stops the scanner with exit code 2. |

### Files that the scanner writes

- The published scanner images run as a user that is not root, `65532:65532`.
- The entrypoint is `python -m scanner`, from the virtual environment of the project.
- The process writes to three places only. Thus the root file system can be read-only.

| Path | Set by | What it holds |
|---|---|---|
| `/var/cache/javv/<scanner>` | `TRIVY_CACHE_DIR` or `GRYPE_DB_CACHE_DIR`, in the `ENV` of the image | The cache of the vulnerability database. The `javv-scanner` chart mounts a volume for each scanner at `/var/cache/javv`. |
| `/var/lib/javv` | `JAVV_DEAD_LETTER`, in the `ENV` of the image | The dead-letter file. |
| `/tmp` | the scanners | The image layers that a scan pulls. |

- You can change each path for each CronJob.
- User 65532 must be able to write to each path that you mount.
- Outside a cluster, user 65532 must also be able to read the kubeconfig that you mount.

### Scan scope, scan settings and versions

- **Scan scope** (the namespaces, images and kinds to scan) is a
  [runtime setting](#scan-scope). At the start of each cycle, the scanner gets the scope from JAVV
  (`GET /api/v1/scan-scope`). The scanner never reads OpenSearch. If JAVV does not reply, the
  scanner skips the cycle. An empty scope means: scan all.
- **What the scanner scans:** the containers of the pods that run. It does not scan init
  containers or ephemeral containers. It pulls each image by the digest that the pod runs
  (`repo@sha256:…`), so a tag that moved since the pod started does not change the scan. If the
  registry no longer has that digest, the scanner skips the image and logs a warning.
- **Image entries of the scope** (`exclude_images`) are globs on the name of the image that JAVV
  shows. For a pod started by a tag, the name is the tag, for example `registry.io/app:1.2`. For a
  pod started by a digest, the name is `registry.io/app@sha256:…`. Thus, to skip a repository with
  any tag or digest, add two entries: `registry.io/app:*` and `registry.io/app@*`.
- **Scan settings** (the [Trivy](#trivy-settings) and [Grype](#grype-settings) tables) are
  environment variables only. The web app shows them on the card of each scanner, but it cannot
  change them. Each push holds the scan settings and the scope of its cycle, and JAVV keeps them
  with the scan.
- **Versions** of the scanners and of their databases come from the image. To change a version,
  change the image tag. The web app shows the version and has no control to select one.

### The javv-scanner chart

The `javv-scanner` chart runs one CronJob for each scanner in a cluster that you scan.

- Each scanner block (`trivy`, `grype`) has its own image, token, schedule, database source and
  cache.
- Each block also has `config`: its settings from the [Trivy](#trivy-settings) or
  [Grype](#grype-settings) table, `JAVV_LOG_LEVEL` and `JAVV_PUSH_RETRY_BUDGET_SECONDS`, by
  environment name, at their defaults. An empty value means not set.
- `scanner/tests/test_helm_config.py` keeps them equal to the code.

The other values:

| Value | Default | What it does |
|---|---|---|
| `backendUrl` | `""` | `JAVV_BACKEND_URL`: the frontend Service of JAVV, at the address that this cluster uses for it. Without it, the install fails. |
| `clusterId` | `""` | `JAVV_CLUSTER_ID`. When it is empty, the scanners read the UID of `kube-system`. |
| `<scanner>.token.existingSecret` / `.key` / `.value` | `""` / `token` / `""` | **Secret.** `JAVV_TOKEN`: the Secret of that scanner, or a value that the chart puts in a Secret. Without it, the install fails. |
| `<scanner>.registryAuth.existingSecret` | `""` | **Secret.** A login for private registries: the name of a `kubernetes.io/dockerconfigjson` Secret in the namespace of the chart. Kubernetes puts its `.dockerconfigjson` key into the scan container as `/etc/javv/registry/config.json`, and the chart sets `DOCKER_CONFIG` to `/etc/javv/registry`. The refresh container does not get the login. When the value is empty, the scanner pulls each image with no login. |
| `<scanner>.schedule` | `0 */6 * * *` (Trivy), `30 */6 * * *` (Grype) | When a cycle starts. `timeZone` sets the zone. |
| `<scanner>.activeDeadlineSeconds` | `19800` | Kubernetes stops a cycle that runs for longer than 5 h 30 min. The CronJob does not start a cycle while one of its own cycles runs (`Forbid`). It does not count a Job that you make by hand: the `NOTES` of the chart give the safe sequence. A stopped cycle does not run again before the next schedule. |
| `<scanner>.image.tag` / `.digest` / `.pullPolicy` | `scanners.<s>.current` in `versions.yaml` / `""` / `Always` | The scanner version. `check-versions.sh` keeps the tag equal to `versions.yaml`. JAVV publishes the tag again when it changes the image for that version, thus `Always`. A digest runs one exact build. The chart of a release sets each digest to the build that its tag named at the release, with a verified signature. The chart in the repository has no digest. |
| `trivy.vulnDb.repository` / `.javaRepository` | `""` | `TRIVY_DB_REPOSITORY` / `TRIVY_JAVA_DB_REPOSITORY` for the refresh. Empty means the source of Trivy: `mirror.gcr.io/aquasec/trivy-db:2`, then `ghcr.io/aquasecurity/trivy-db:2`. The Java database works the same way. |
| `grype.vulnDb.updateUrl` | `""` | `GRYPE_DB_UPDATE_URL` for the refresh. Empty means the source of Grype (`https://grype.anchore.io/databases`). |
| `<scanner>.vulnDb.size` / `.storageClass` / `.existingClaim` | `10Gi` / `""` / `""` | The cache volume of the scanner, `ReadWriteOnce`. In October 2026, the two Trivy databases used 2.9 GB, and the Grype database used 3.0 GB. |

### The database refresh

Each cycle starts with an init container on the image of the scanner:

1. This container refreshes the database in the cache volume.
2. Then the scan runs with the update switches of the vendor off: `TRIVY_SKIP_DB_UPDATE`,
    `TRIVY_SKIP_JAVA_DB_UPDATE`, `TRIVY_SKIP_CHECK_UPDATE` and `GRYPE_DB_AUTO_UPDATE=false`. The
    chart sets them.

Thus a cycle reads one database and does not connect to the vendor during the scan.

- If the refresh fails, the scan uses the database in the cache. With no database in the cache,
  the cycle fails.
- The refresh checks the database with a lookup. If the scanner cannot read the database, the
  refresh deletes it and downloads it one more time. If that also fails, the cycle fails.
- Trivy gets two lookups, because a damaged Java database does not fail a scan. Trivy skips each
  jar that it cannot look up, and exits with 0. Thus its lookup must find a known CVE in a jar
  that only the Java database can name.
- Grype refuses a database older than 5 days. To change this, set
  `GRYPE_DB_MAX_ALLOWED_BUILT_AGE` in `extraEnv`.
- Misconfiguration scans (`JAVV_TRIVY_SCANNERS` with `misconfig`) use the checks in the Trivy
  binary. Thus they also do not connect to the vendor during the scan.
- The install runs the same refresh one time, as a Job. This Job also binds the volume. An upgrade
  runs it again when the refresh container changes: the image, the database source, `extraEnv`,
  `resources` or `pullPolicy`.

## Trivy settings

The scanner reads these environment variables.

- Set them on the CronJob of the scanner, or in `trivy.config` of the `javv-scanner` chart.
- A setting that you do not set has the default in the table.
- The output format stays `json`, because the parser of JAVV needs it.

The scanner checks each value against the values that the pinned Trivy binary accepts:

- scanners: `vuln`, `misconfig`, `secret`, `license`
- severities: `UNKNOWN`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- package types: `os`, `library`
- timeout: a Go duration.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_TRIVY_SCANNERS` | `vuln` | `--scanners`, for example `vuln,secret,misconfig`. |
| `JAVV_TRIVY_IGNORE_UNFIXED` | `false` | Adds `--ignore-unfixed`. |
| `JAVV_TRIVY_SEVERITIES` | not set: all | `--severity`, for example `CRITICAL,HIGH`. |
| `JAVV_TRIVY_PKG_TYPES` | not set | `--pkg-types`, for example `os,library`. |
| `JAVV_TRIVY_TIMEOUT` | not set: the Trivy default | `--timeout`, for example `5m0s`. |
| **Trivy version** | `0.76.1` | `scanners.trivy.current` in `versions.yaml`, and the `ARG` in the Dockerfile. To change it, use a different image tag. |
| **Vulnerability database** | schema 2 | `versions.yaml` holds the schema. A database with a different schema fails with a clear error. The `javv-scanner` chart refreshes the database at the start of each cycle. Without the chart, Trivy refreshes it at scan time. Each push holds the database version, from `trivy version --format json` in each cycle. |

## Grype settings

The scanner reads these environment variables.

- Set them on the CronJob of the scanner, or in `grype.config` of the `javv-scanner` chart.
- A setting that you do not set has the default in the table.
- The output format stays `json`, because the parser of JAVV needs it.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_GRYPE_ONLY_FIXED` | `false` | Adds `--only-fixed`. |
| `JAVV_GRYPE_SCOPE` | not set: the Grype default | `--scope`: `squashed`, `all-layers` or `deep-squashed`. The scanner checks the value. |
| `JAVV_GRYPE_SCAN_TIMEOUT` | `600` | Seconds before the scanner stops one Grype scan. Grype has no flag for a scan time limit. A value that is not a whole number stops the scanner with a clear error. |
| **Grype version** | `0.120.1` | `scanners.grype.current` in `versions.yaml`, and the `ARG` in the Dockerfile. To change it, use a different image tag. |
| **Vulnerability database** | schema 6, from Grype 0.88.0 | `versions.yaml` holds the schema. The `javv-scanner` chart refreshes the database at the start of each cycle. Without the chart, Grype refreshes it at scan time. |

## Frontend settings

### Frontend server settings

The frontend image runs a small Node server.

- The server sends the web app to the browser, and sends the requests to `/api`, `/auth` and
  `/readyz` on to the backend. Thus the browser uses one address.
- The server reads these settings when its container starts. A restart applies a change, with no
  new build.

The server sends these headers on each reply, so that JAVV needs no proxy to add them:

- `Content-Security-Policy`: the browser loads scripts, styles, fonts and data only from the JAVV
  address. Each page gets a new nonce for the styles of the web app. No inline script runs.
- `X-Frame-Options: DENY` and `frame-ancestors 'none'`: no other site can show JAVV in a frame.
- `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`.

- The server does not send on the `Server` header of the backend.
- If a proxy in front of JAVV sets its own security headers, make sure that they do not replace
  these headers with weaker ones.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_BACKEND_URL` | `http://backend:8000` | The address of the backend, as the frontend container sees it: a compose service name, a Kubernetes Service or an IP address. `http` or `https`. When nothing replies there, the server replies 502 with the error envelope. The web app shows this as "backend down". |
| `JAVV_BACKEND_CONNECT_TIMEOUT` | `5` | Seconds that a connection to the backend can take to open. For an `https` backend, this time includes the TLS handshake. After this time, the reply is the same 502, and the warning line gives `reason: connect timeout`. The server measures only the opening. It never stops a slow reply, for example an export. Kubernetes refuses a connection at once when a Service has no ready pod. But an address whose pod stopped, and that is still in the Service, does not reply. Without this time, the request would wait with no end. A value that is not a number of seconds above 0 stops the server at start. |
| `JAVV_FRONTEND_PORT` | `8080` | The port that the server listens on in its container. |
| `JAVV_LOG_LEVEL` | `info` | The log level of the server: `debug`, `info`, `warning` or `error`. An unknown name stops the server at start, as in the backend. |

### Frontend build settings

These settings apply only when you build the frontend image yourself.

- Vite writes them into the web app at build time.
- To change one, build the image again.
- A published image has the defaults.

| Setting | Default | What it does |
|---|---|---|
| `VITE_LOG_LEVEL` | `debug` in a dev build, `warn` in a production build | The level of the logger in the browser console: `debug`, `info`, `warn` or `error`. An unknown value gives the default. |
| `VITE_DB_AGE_WARN_DAYS` | `7` | Days after which the scanner card shows the vulnerability database as old: amber `· N days old` next to **DB built**. A scanner with an old database finds fewer vulnerabilities. To fix it, use a newer scanner image. A value that is not a number above 0 gives the default. |
| `VITE_EXPIRY_WARN_DAYS` | `7` | Days before a risk acceptance expires when its chip in the Approvals queue turns amber: `expires in Nd`. At the expiry, the chip turns red, and the findings of the acceptance open again. A value that is not a number above 0 gives the default. |
| `VITE_CLIENT_EVENTS` | not set: on in a production build, off in a dev build | When it is on, the browser also sends each `logger.warn` and `logger.error` to `POST /api/v1/client-events`. Thus an error stays in the log after the user closes the tab. `false` or `0` turns it off. Each other value turns it on. See the [browser warnings](#browser-warnings-and-errors) below. |

#### Browser warnings and errors

The browser sends its warnings and errors in batches, and it accepts some loss:

- The browser never sends a batch again.
- The queue holds one batch of 20 events. The browser sends it each 5 seconds, and also when the
  tab closes or goes to the background. Thus a flood of errors loses events, but it does not go
  above `JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE`. A 429 would also lose the events.
- When a window loses events, its next batch starts with a `beacon events dropped` entry, with the
  count. Thus a gap in the log shows as a flood, not as a quiet session.
- That count includes only the events lost in a flood. The browser drops an event that it cannot
  send, for example an event with a bad name, without a count. Otherwise a fault in one call
  would report a new flood each time that screen opens.
- The browser cuts each field value to 512 characters, the limit of the endpoint. Thus one long
  value cannot cause a 422 for its batch. A cut value ends in `…`. A value of 512 characters or
  fewer arrives with no change.

## OpenSearch settings

These settings belong to OpenSearch.

- The compose file and the `javv-opensearch` chart set them.
- When you operate your own OpenSearch, you set them.
- `datastore.opensearch` in [`versions.yaml`](../versions.yaml) gives the version that JAVV
  supports.

| Setting | Compose value | What it does | With your own OpenSearch |
|---|---|---|---|
| image | `opensearchproject/opensearch:3.9.0` | The OpenSearch version, from `versions.yaml`. | Use the same version. CI tests JAVV with it. |
| `discovery.type` | `single-node` | One node. | Your choice. CI tests JAVV with one node. |
| Security plugin | on, with the demo certificates of OpenSearch | Sign-in and TLS for OpenSearch. | On, with your own certificates. Set `JAVV_OPENSEARCH_USERNAME`, `JAVV_OPENSEARCH_PASSWORD` and `JAVV_OPENSEARCH_CA_BUNDLE` ([Connection to OpenSearch](#connection-to-opensearch)). |
| `plugins.security.audit.type` | `noop` | The audit log of OpenSearch. With the demo security setup, it writes a new `security-auditlog-<date>` index each day. JAVV turns off index state management, so nothing deletes these indices. JAVV keeps its own audit log in `system-audit-log`. | Your choice. JAVV does not read it. |
| `OPENSEARCH_INITIAL_ADMIN_PASSWORD` | from `JAVV_OPENSEARCH_ADMIN_PASSWORD` in `.env` | **Secret.** The password of `admin`, which the demo security setup makes at the first start with security on. The backend never gets it: it signs in as `javv`. OpenSearch ignores later changes of this value ([Change an OpenSearch password](UPGRADING.md#change-an-opensearch-password)). A weak password stops the container. | Not used. |
| `OPENSEARCH_JAVV_PASSWORD` | from `JAVV_OPENSEARCH_PASSWORD` in `.env` | **Secret.** The password of `javv`, the user that the backend signs in as. The `opensearch` entrypoint of compose hashes it into the users file with `hash.sh` of OpenSearch. An empty password stops the container. OpenSearch reads it at its first start with security on, as for `admin`. | Not used. |
| Users | `admin` and `javv` | Who can sign in to OpenSearch. The demo security setup loads each user in `config/opensearch-security/internal_users.yml` of the image. Six of these users have their own name as password, and no setting turns them off. The `opensearch` entrypoint of compose keeps only `_meta` and `admin` in that file, and adds `javv`. OpenSearch reads the file at its first start with security on. The demo admin certificate in the image (`kirk.pem`) also has full access, with no password. | Your users. JAVV signs in as `JAVV_OPENSEARCH_USERNAME`. |
| Roles and role mapping | the `javv` role, `admin` on `all_access`, `javv` on `javv` | What each user can do. Compose mounts its own `roles.yml` and `roles_mapping.yml` in place of the demo files. OpenSearch reads them at its first start with security on. [Upgrading](UPGRADING.md) tells you how to load them into an older OpenSearch. | Make the `javv` role from [An OpenSearch of your own](DEPLOYING.md#an-opensearch-of-your-own). |
| `OPENSEARCH_JAVA_OPTS` | `-Xms1g -Xmx1g` | The JVM heap. | Size it for each node ([Sizing OpenSearch](runbooks/opensearch-sizing.md)). |
| `path.repo` | `/usr/share/opensearch/data/snapshots` | The root of the file system snapshot repository. **Settings › Data & OpenSearch** makes its snapshots there. | An S3 or MinIO repository. Its credentials go in the keystore. |
| Snapshot repository credentials | none | **Secret.** The access key and the secret key of an S3 repository. | Only in the OpenSearch keystore, never in a JAVV setting. |

### The javv-opensearch chart

The `javv-opensearch` chart runs the same OpenSearch settings as compose, as values of the
official chart under `opensearch:`.

- The keys of JAVV are under `opensearch.javv`. A wrapper chart cannot calculate the values of its
  subchart, so these keys are at a place that both charts can read.
- The [chart README](../deploy/helm/javv-opensearch/README.md) gives the full list, with the keys
  of the official chart that this chart sets.

| Value | Default | What it does |
|---|---|---|
| `opensearch.javv.auth.existingSecret` | `""` | **Secret.** A Secret with the admin password under `password`. Set this value or `password`. With neither or both, the install fails. |
| `opensearch.javv.auth.password` | `""` | **Secret.** The admin password. The chart puts it in the Secret `<release>-javv-opensearch-admin`. OpenSearch reads it at its first start only. |
| `opensearch.javv.backend.existingSecret` | `""` | **Secret.** A Secret with the password of `javv` under `password`. `javv` is the user that the backend of JAVV signs in as, and it holds only the `javv` role. Set this value or `password`. With neither or both, the install fails. |
| `opensearch.javv.backend.password` | `""` | **Secret.** The password of `javv`. The chart puts it in the Secret `<release>-javv-opensearch-backend`, which `opensearch.passwordSecret` of the `javv` chart names. OpenSearch reads it at its first start only. |
| `opensearch.javv.tls.existingSecret` | `""` | A Secret with `tls.crt`, `tls.key` (PKCS#8) and `ca.crt`. It turns off the demo certificates. |
| `opensearch.javv.tls.certManager.enabled` / `.issuerRef` | `false` / `{}` | A cert-manager `Certificate` for the Service, in `<release>-javv-opensearch-tls`. It turns off the demo certificates. |
| `opensearch.javv.tls.adminDn` | `[]` | The DNs of the client certificates that can run `securityadmin.sh` with your own certificates. |
| `opensearch.singleNode` | `true` | One node. With `false`, the install fails. |
| `opensearch.image.tag` | `datastore.opensearch` in `versions.yaml` | The tag of the OpenSearch image. `check-versions.sh` keeps it equal to `versions.yaml`. |

## Runtime settings

JAVV keeps these settings as data in OpenSearch, in the `system-config` index.

- You change them in the web app or with the API, while JAVV runs. You do not need a new build or
  a restart.
- Each change writes an entry to the audit log.
- A per-cluster value replaces the fleet value for that cluster.

| Setting | Default | Scope | Where in the web app | Permission to change it |
|---|---|---|---|---|
| [Snapshots](#snapshots) | no repository | fleet | **Settings › Data & OpenSearch** | `can_manage_retention`. A restore needs `can_restore_snapshot`. |
| [Retention and rollover](#retention-and-rollover) | 90 days. Rollover at 30 days, 5,000,000 documents or 50 GB. | fleet and per cluster | **Settings › Data & OpenSearch** | `can_manage_retention` |
| [Export lifetime](#export-lifetime) | `JAVV_EXPORT_TTL_HOURS` (24 hours) | fleet | **Settings › Data & OpenSearch** | `can_manage_retention` |
| [Findings cleanup](#findings-cleanup) | 180 days | fleet and per cluster | **Settings › Data & OpenSearch** | `can_manage_retention` |
| [Staleness](#staleness) | 3 days and 7 days | fleet and per cluster | **Settings › Scanning** | `can_manage_settings` |
| [Cluster retirement window](#cluster-retirement-window) | `JAVV_CLUSTER_RETIRE_AFTER_DAYS` (45 days), warning `JAVV_CLUSTER_RETIREMENT_WARN_DAYS` (7 days) | fleet and per cluster | **Settings › Cluster** | `can_manage_settings` |
| [SLA policy](#sla-policy) | critical 2, high 7, medium 30, low 90 days. KEV 1 day. | fleet | **Settings › SLA policy** | `can_manage_settings` |
| [Scan scope](#scan-scope) | empty: scan all | per cluster | **Settings › Scan scope** | `can_manage_settings` |
| [Ingest tokens](#ingest-tokens) | none | per cluster and scanner | **Settings › Access & tokens** | `can_manage_tokens` |
| [Users and roles](#users-and-roles) | the first admin, four roles | fleet | **Settings › Users & roles** | `can_manage_users` |

### Snapshots

- `GET /api/v1/admin/snapshots` lists the snapshots, and `POST /api/v1/admin/snapshots` makes one.
- `POST /api/v1/admin/snapshots/{name}/restore` restores a snapshot into `restored-*` copies. It
  never writes over the live indices.
- You register the snapshot repository when you deploy, with its credentials in the keystore of
  OpenSearch. The `system-config` document `snapshot_repo` holds its name, with no credentials.
- A snapshot holds `findings`, `javv-images-*` and `system-*`, except `system-sessions`: the
  current state, the triage, the decisions, the users, the settings and the audit log. A snapshot
  does not hold the sessions, because a restored copy could make an ended session valid again.
- A snapshot does not hold the scan history (`javv-finding-occurrences-*`, `javv-scan-events-*`,
  `javv-inventory-runs-*` and `javv-ingest-failures-*`). Time travel reads this history. A snapshot
  also does not hold `javv-scan-orders` and `javv-scan-watermarks`. Thus a restore from a snapshot
  does not bring back the history.
- JAVV does not make scheduled snapshots yet.

### Retention and rollover

- **Retention** (`retention_days`) is the number of days that JAVV keeps history. The daily
  lifecycle sweep deletes each history index that is older than the retention of its cluster. It
  deletes complete indices only, never single documents.
- **Rollover** starts a new history index when the current index gets to one limit:
  `max_age_days`, `max_docs` or `max_size_gb`.
- The history indices are `javv-scan-events`, `javv-images`, `javv-finding-occurrences`,
  `javv-inventory-runs` and `javv-ingest-failures`. The records of failed pushes thus have the same
  retention.
- The fleet value is the `lifecycle` document. A `lifecycle:<cluster_id>` document replaces it for
  one cluster. The sweep reads them at each run.
- API: `PUT /api/v1/settings/retention` and `PUT /api/v1/settings/rollover`.
- Command line:
  `python -m backend.jobs.lifecycle --set-max-age-days N --set-max-docs N --set-max-size-gb N --set-retention-days N [--cluster <id>]`.

### Export lifetime

- The hours that JAVV keeps a finished export: the `report_ttl` document. Until you save a value,
  JAVV uses `JAVV_EXPORT_TTL_HOURS`.
- The report drain writes the expiry time on each export. The report sweep deletes the failed
  exports that are older than this time.
- API: `PUT /api/v1/settings/report-ttl`.

### Findings cleanup

- `cleanup_days`: the cleanup deletes each row of the `findings` cache that is not present
  (`present=false`) and whose `resolved_at` is older than this window. It also deletes the scan
  watermarks of an image with no rows left.
- The fleet value is the `findings_cleanup` document. A `findings_cleanup:<cluster_id>` document
  replaces it for one cluster. The cleanup runs for each cluster with its own window, and reads
  the window at each run.
- The cleanup never changes the history indices. Its window is independent of the staleness timers
  and of the retention, and much longer than both.
- The backend runs it on `JAVV_JOB_FINDINGS_CLEANUP_CRON`. You can also run it by hand:
  `python -m backend.jobs.findings_cleanup`.
- Each run writes its counts to the audit log (`findings_cleanup_run`).
- API: `PUT /api/v1/settings/findings-cleanup`.

### Staleness

- The two timers of the daily staleness sweep: `freshness_days` (3) and `scanner_down_days` (7).
  The sweep reads them at each run.
- The fleet value is the `staleness` document. A `staleness:<cluster_id>` document replaces it for
  one cluster.
- API: `PUT /api/v1/settings/staleness`.
- Command line:
  `python -m backend.jobs.staleness --set-freshness-days N --set-scanner-down-days M [--cluster <id>]`.

### Cluster retirement window

- `retire_after_days`: the days that a cluster can go with no accepted scan. After this time, the
  retirement sweep retires the cluster. `null` means never. `warn_days`: the days of warning before
  the retirement.
- The fleet value is the `retirement` document. A `retirement:<cluster_id>` document replaces it
  for one cluster. Until you save a fleet value, JAVV uses `JAVV_CLUSTER_RETIRE_AFTER_DAYS` and
  `JAVV_CLUSTER_RETIREMENT_WARN_DAYS`.
- A retired cluster is not on the cluster list. JAVV keeps its data and does not change its
  tokens. Its next scan returns it.
- A retirement by hand revokes the tokens of the cluster. The cluster returns when it sends a scan
  with a new token, or when you return it by hand.
- JAVV refuses a window that is not longer than the scanner-down timer of the cluster
  ([Staleness](#staleness)), with 422. The sweep never uses a window shorter than that timer. Thus
  an outage that is only long enough to make findings stale never retires a cluster.
- The silence starts at the newest accepted scan. For a cluster that never sent a scan, it starts
  when JAVV made its first token. When a cluster returns from retirement, JAVV writes `returned_at`
  on the record, and the silence starts again from that time. Thus the next sweep does not retire
  the cluster again at once.
- Sometimes clusters are due, but no cluster had a scan accepted within its scanner-down timer.
  Then the sweep retires nothing and logs a warning (`javv_cluster_retirement_held_total`). This
  points at JAVV, not at the clusters.
- When a cluster enters its last `warn_days`, the sweep sends one notification for each silence to
  each user with `can_manage_settings` (`cluster_retiring`, in the bell). The web app also shows a
  banner with the count of days. A change of these settings does not send or delete a
  notification. JAVV deletes the notification when the cluster scans again, or when a return from
  retirement starts a new silence. A retired cluster keeps its notification.
- The sweep never retires the only cluster on the list. That cluster gets no notification, and
  the banner says that JAVV does not retire it automatically.
- The backend runs the sweep on `JAVV_JOB_CLUSTER_RETIREMENT_CRON`. The same run also looks at
  deleted clusters for rows that arrived after their deletion.
- API: `GET /api/v1/settings/retirement` (each signed-in user) and
  `PUT /api/v1/settings/retirement`. The audit log entry is `retirement_window_change`.

### SLA policy

- The days to fix a finding, for each severity: critical 2, high 7, medium 30, low 90. A finding
  in the KEV catalog has `kev_days`, 1 day. `negligible` and `unknown` have no SLA.
- The `sla` document holds the policy, for all clusters.
- JAVV calculates "overdue" when it reads. The clock starts at the earliest `first_seen_at` for
  each CVE and image. A new package version does not start the clock again.
- API: `GET /api/v1/settings/sla` (each signed-in user or token) and `PUT /api/v1/settings/sla`.
  The audit log keeps the full old and new policy.

### Scan scope

- The namespaces, images and kinds that the scanners of one cluster scan: the
  `scan_scope:<cluster_id>` document.
- The scanner gets it at the start of each cycle with `GET /api/v1/scan-scope`
  ([Scanner settings](#scan-scope-scan-settings-and-versions)).

### Ingest tokens

- `POST /api/v1/admin/tokens` makes a token, and `GET /api/v1/admin/tokens` lists the tokens.
  `/{id}/rotate` and `/{id}/revoke` rotate and revoke one. The lists use pages (`size`, `offset`).
- JAVV shows the raw token one time only.
- A new token can have an expiry. A rotation keeps the same expiry: a rotation does not extend a
  token.
- Command line: `python -m backend.core.tokens --cluster <id> --scanner <trivy|grype>`.

### Users and roles

- `POST /api/v1/admin/users` makes a user, and `GET /api/v1/admin/users` lists the users.
  `PATCH /api/v1/admin/users/{u}/role`, `PATCH /api/v1/admin/users/{u}/disabled` and
  `POST /api/v1/admin/users/{u}/password-reset` change one.
- A new user, and a user after a password reset, gets a temporary password and must change it.
- A role change sets the role and its capabilities together, and ends the sessions of the user. A
  user that you disable also loses the sessions.
- You cannot demote or disable the last enabled admin: the reply is 409.
- The roles are documents in `system-roles`: `viewer`, `triager`, `security_lead` and `admin`
  (all capabilities). JAVV makes them at the first start and never writes them again. To change a
  role, edit its document. The web app shows the four roles, but cannot change them.
- Each user has a role and a copy of the capabilities of that role, in `system-users`.

## Fixed values

Some values in the code never change. They are not `JAVV_*` settings and not runtime settings:

- A setting for them would add work for operators.
- A wrong value would hide a bug, not change a workload.

To decide, ask this question: does an operator have a reason to change the value for their
workload?

- If yes, the value is a setting.
- If the only reason is "a bug makes us get to the limit", the value stays in the code: fix the
  bug.
- For example, the bulk limit is a setting (`JAVV_BULK_MAX_TARGETS`), but the page size of a bulk
  selection (`_FREEZE_PAGE`) stays in the code.

| Kind | Values | Why they are not settings |
|---|---|---|
| **Scheduler tick:** how frequently the backend looks for a due job | `jobs/scheduler.TICK_SECONDS` (30 s) | A schedule is a minute or longer, so two looks each minute never miss one. A shorter tick gives nothing. A longer tick can start a job late. The schedules themselves are settings (`JAVV_JOB_<KIND>_CRON`). |
| **Queue order:** the due job that starts first | `jobs/schedule.FIRST_IN_QUEUE` (`report_drain`), then the order of `jobs/registry.JOBS` | A person waits for an export. Nobody waits for a sweep. |
| **Scanner error text in the log:** how much of the error output of a failed scan one log line holds | `scanner/run.STDERR_TAIL_LINES` (5), `STDERR_TAIL_CHARS` (1000) | These values bound one log line. The scanner writes its final error last. JAVV does not keep the full output of the scanner. |
| **Scanner waits between tries:** the first wait and the longest one | `scanner/push.FIRST_WAIT_S` (0.5 s), `WAIT_CAP_S` (30 s) | The setting `JAVV_PUSH_RETRY_BUDGET_SECONDS` decides how long the scanner tries. These values only space the tries: each wait is a random time up to its limit, which doubles from the first. |
| **Read page size:** the reader reads in pages, so this value is a batch size, not a limit on results | `decisions/reproject._PAGE` (10k), `triage/bulk._FREEZE_PAGE` (10k), `services/disagreement._SEARCH_PAGE` (10k), `jobs/rebuild_state._PAGE` (1k), `export/sweep._PAGE_SIZE` (500), `routers/findings._GROUP_CLOCK_PAGE` (1k), `routers/contributors._ROWS_PAGE_SIZE` (10k), `query/pit._ROW_PAGE` (10k), `query/human_at._ROW_PAGE` (10k), and the row walks of `jobs/rebuild_state` and `jobs/staleness` (10k). All `search_after` walks use `query/paging.search_to_exhaustion`. | Each value is at or below the `from`/`size` limit of OpenSearch, 10k. A sweep uses a smaller value to keep its memory constant. The caller reads pages until there are no more, so each value gives complete results. A value changes only the number of round trips and the memory. |
| **Conflict retries:** a guard against a loop, not a dial | `decisions/reproject._CONFLICT_RETRIES` (8), `services/reconcile._CONFLICT_RETRIES` (10), `services/merge._CONFLICT_RETRIES` (10), `decisions/lifecycle._CAS_RETRIES` (8), `triage/service._CAS_RETRIES` (8), `services/scan_orders._CAS_RETRIES` (32), `services/watermarks._CAS_RETRIES` (32), `admin/cluster_delete._RETRIES` (5) | Real contention is about 1: one CronJob for each scanner, with `Forbid`. A run that gets to the limit shows a fault to examine. A larger limit would hide the fault. A cluster delete refreshes the index before each retry, because a row that changed since the last refresh conflicts with every pass until then. The two values of 10 guard the same commit race from the two sides. They wait longer after each retry with `repositories/bulk.race_backoff_delay`: from 0.02 s to 2 s, about 8.5 s in total. This total is longer than the `_bulk` backoff of a racing pass, 7.5 s at most. |
| **Shape of a client-events request:** the contract of the API, not a dial | `routers/client_events._MAX_BATCH` (20), `_MAX_KEYS_PER_OBJECT` (25), `_MAX_DEPTH` (3), `_MAX_KEY_CHARS` (64), `_MAX_VALUE_CHARS` (512), `_MAX_LIST_ITEMS` (20), `_EVENT_NAME` (`^[a-z0-9][a-z0-9 ._-]{0,63}$`) | These values are the OpenAPI schema. They are in the generated client, so a change is a contract change for the backend and the frontend. As settings, they would make a 422 depend on the deployment. The input comes from the browser and is not trusted, so the check of value types is an allowlist. The name pattern accepts spaces, as in `backend degraded`. It refuses newlines, tabs, quotes and control characters, which could break the `client.<name>` name. The rate limit for each user is a setting (`JAVV_CLIENT_EVENTS_RATE_LIMIT_PER_MINUTE`). |
| **Idle connections to the backend:** how long the frontend server keeps an idle connection to the backend open | `frontend/server/serve.mjs`: `BACKEND_IDLE_MS` (4 s) | The backend closes an idle connection after 5 s, the default of uvicorn. The frontend server must close the connection first. If not, a request that it sends at the same moment gets a reset, and the browser gets a 502. An operator cannot change the 5 s of the backend, so this value has no reason to change. `test_frontend_pool_idle.py` fails when the frontend value is not at least 0.5 s shorter. |
| **Store warning window:** how frequently the backend logs that OpenSearch is not reachable | `core/errors.STORE_WARN_WINDOW_S` (10 s) | Any sender can repeat a request while OpenSearch is away, so the warning must not follow the requests. The counter `javv_store_unavailable_total` counts each one. The frontend server logs its 502 with the same window. |
| **Password length:** the rule for each local password | `auth/passwords.MIN_LENGTH` (12), `MAX_LENGTH` (256). The frontend has a copy in `frontend/src/stores/auth.ts`: `PASSWORD_MIN_LENGTH` and `PASSWORD_MAX_LENGTH`. | A security minimum, not a dial. The password form shows the minimum and refuses a shorter password before it sends it, so the frontend keeps a copy. `password-change.spec.ts` reads the backend file and fails when the two are different. The server makes the decision. |
| **Fixed aggregation sizes:** sized to a domain with a known limit | `query/aggs._FACET_TERMS_SIZE` (32, at least the largest facet vocabulary), `query/contributors._BOARD_SIZE` (100 people on the leaderboard) | The data model and the product set these limits, not the workload. A larger value would ask for buckets that cannot exist. |

## CI gate values

These values belong to the CI of JAVV. They look like settings, but they are not.

| Gate | Value and place | Rule |
|---|---|---|
| Backend coverage minimum | `--cov-fail-under=90`, in the backend job of `.github/workflows/ci.yml` | On 2026-07-15, the line coverage was 92.4%. The minimum is 2 points below. **Increase the minimum when coverage increases. Never decrease it.** A PR that does not meet the minimum adds tests. It does not move the minimum. |
| Frontend coverage minimum | `thresholds.lines: 77`, in `frontend/vitest.config.ts` | On 2026-07-15, the line coverage was 79.7%. The count includes the TypeScript logic modules only. The route smoke test covers the views, and the build generates `src/api/generated`. The same rule applies. |
| Smoke search limit | `JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL=50`, in the env of the CI smoke job | The [backend setting](#triage-search-and-exports), larger for the smoke test only. The test opens pages faster than a person, and slots become free slower than it opens pages. Do not use this value in production. |
| Smoke data | `backend/tests/fixtures/envelope-trivy-golden.json`, through `development/scripts/seed-smoke.sh` | The golden fixture of the contract is the seed. Thus there is one source of truth. A change of the ingest contract changes both in the same PR. The script pushes it to two clusters, with the second cluster id changed at seed time. Thus the smoke test can go from one cluster to the other. |
