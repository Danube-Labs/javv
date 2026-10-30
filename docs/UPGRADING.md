# Upgrading JAVV

This page tells you how to move a running JAVV to a newer release:

- What to check before you start.
- The sequence of the upgrade, with docker compose or with Helm.
- How to check the result, and how to go back to the previous release.

JAVV has three parts. You upgrade each part separately:

| Part | What changes its version | Where to find the version |
|---|---|---|
| **Backend** (FastAPI) | The JAVV release | The release tag. `GET /api/v1/meta` → `version` |
| **Frontend** (Vue) | The JAVV release, together with the backend | The same release |
| **Scanner images** (Trivy, Grype) | You change the published image tag in your deployment | [`versions.yaml`](../versions.yaml) lists the supported scanner versions |

JAVV never changes a version in a cluster that you scan. You set each version as a tag in your
own deployment. To install JAVV, see [`DEPLOYING.md`](DEPLOYING.md).

## Before you upgrade

1. **Read the release notes.** Each release has a GitHub Release and an entry in
    [`CHANGELOG.md`](../CHANGELOG.md). Then read [Version notes](#version-notes) on this page. They
    tell you what a release needs from you.
2. **Make a snapshot.** The upgrade does not need it.
    - Use **Settings › Data & OpenSearch › Snapshot now**, or `POST /api/v1/admin/snapshots`. The
      request needs `can_manage_retention`.
    - The request returns 409 when OpenSearch has no snapshot repository.
      [Snapshots](CONFIGURATION.md#snapshots) tells you how to add the repository.
    - The snapshot keeps the current state, the triage, the decisions, the users, the settings and
      the audit log. **It does not keep the scan history** that time travel reads. Thus a restore
      does not bring the history back.
3. **Check the OpenSearch version.** CI tests JAVV with the version in `datastore.opensearch` in
    [`versions.yaml`](../versions.yaml).

## Sequence of the upgrade

**Upgrade the backend first, then the frontend, then the scanner images.**

1. **Backend.** Each new backend pod upgrades the indices when it starts.
    - It compares each index and template with the schema version of the release, and it adds the
      missing parts.
    - It opens its port only after this step. Thus it receives no requests before its indices are
      ready.
    - You do not need to do a step manually.
2. **Frontend.** Upgrade it together with the backend, or immediately after the backend. A newer
    frontend can send requests that an older backend does not have.
3. **Scanner images.** Change the Trivy and Grype image tags after the backend runs the new
    release. A newer scanner can send a report format (`schema_version`) that only the newer backend
    accepts. `GET /api/v1/meta` → `envelope_versions` lists the formats that the backend accepts.

There is only one backend, and an upgrade replaces it. Thus two backend releases never run at the
same time.

After you go back to an older release, an older backend reads indices that a newer backend changed.
This is safe, because each schema change until now only added fields:

- An older backend ignores the fields that it does not know.
- A newer backend reads a missing field as empty.

### With docker compose

**Prerequisites:**

- Your `.env` file. Keep it: it holds your settings.
- The `compose.yaml` of the new release. It names the backend and frontend images of that release.
- A copy of your changes to `compose.yaml`, for example the host port. Make the same changes in the
  new file.

**Steps:**

1. In the folder of your installation, keep a copy of the old file, and get the file of the new
    release. `VERSION` is the release that you upgrade to:
    <!-- x-release-please-start-version -->
    ```bash
    VERSION=0.9.4
    cp compose.yaml compose.yaml.old
    curl -fsSLO "https://raw.githubusercontent.com/Danube-Labs/javv/v$VERSION/deploy/compose/compose.yaml"
    ```
    <!-- x-release-please-end -->
2. Make your changes to `compose.yaml` again, if you had changes.
3. Pull the images and start them:
    ```bash
    docker compose pull
    docker compose up -d
    ```

JAVV is not available for some seconds, while the new backend starts and upgrades the indices. The
frontend waits until the backend reports healthy (`depends_on`).

**To go back to the previous release,** put the `compose.yaml` of that release back
(`compose.yaml.old`), and run the two commands of step 3. To go back to a release before 0.7.0,
first put back the old name of the secret key
([Go back to a previous release](#go-back-to-a-previous-release)).

#### Upgrade from 0.5.1 to 0.6.1 or later

From 0.6.0, OpenSearch requires a sign-in. 0.6.0 published no images, so use 0.6.1 or later.
Before step 3, add these two values to your `.env`:

- `JAVV_OPENSEARCH_ADMIN_PASSWORD`: the password of the OpenSearch admin.
- `JAVV_OPENSEARCH_PASSWORD`: the password of `javv`, the user that the backend signs in as.

The compose file does not start without these two values. OpenSearch refuses a weak admin password.
[`DEPLOYING.md`](DEPLOYING.md#install-with-docker-compose) gives the rules.

Your data stays:

- When OpenSearch first starts with its sign-in on, it keeps each index, and it adds its security
  configuration.
- You can also go back to a 0.5.x `compose.yaml` with the same data. Then OpenSearch runs without
  its sign-in again.

We did these steps on the real compose files, from a 0.5.1 installation with data.

#### Change an OpenSearch password

OpenSearch reads `JAVV_OPENSEARCH_ADMIN_PASSWORD` and `JAVV_OPENSEARCH_PASSWORD` only on its first
start with its sign-in on. It keeps the two passwords in its data. Thus OpenSearch ignores a new
value in `.env`:

- With a new admin password, OpenSearch never reports healthy, because its `healthcheck` uses the
  new value. The backend waits for OpenSearch, and `docker compose up -d` fails after some minutes.
- With a new `javv` password, the backend stops with "refused the credentials in
  JAVV_OPENSEARCH_USERNAME".

To change a password and keep the data:

1. Put the new password in `.env`.
2. Start only OpenSearch: `docker compose up -d opensearch`. It still accepts only the old
    password.
3. Load the new password into the security index of OpenSearch. Use the demo admin certificate in
    the image:
    ```bash
    docker compose exec opensearch plugins/opensearch-security/tools/securityadmin.sh \
      -f config/opensearch-security/internal_users.yml -t internalusers -icl -nhnv \
      -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
    ```
    The command ends with `Done with success`. The compose file writes `internal_users.yml` from
    `.env` at each start. Thus the file holds the two new passwords.
4. Run `docker compose up -d`.

Other methods do not work, or delete data:

- `docker compose down -v` also makes OpenSearch use a new password. But it deletes all JAVV data.
- The account API of OpenSearch cannot change the admin password: `admin` is a reserved user (403).

#### Only for OpenSearch started from a `main` checkout: load the missing users

Do these steps only when the security index of OpenSearch holds only `admin`. No release made this
state. A `main` checkout before 0.6.0 can make it, because OpenSearch reads the files for users,
roles and role mappings only on its first start with its sign-in on.

1. In `.env`, move the value of `JAVV_OPENSEARCH_PASSWORD` to `JAVV_OPENSEARCH_ADMIN_PASSWORD`. In
    this state, `JAVV_OPENSEARCH_PASSWORD` was the admin password.
2. Give `JAVV_OPENSEARCH_PASSWORD` a new value. This is the password of `javv`.
3. Start only OpenSearch: `docker compose up -d opensearch`.
4. Load the three files one time, with the same certificate:
    ```bash
    for f in internal_users:internalusers roles:roles roles_mapping:rolesmapping; do
      docker compose exec opensearch plugins/opensearch-security/tools/securityadmin.sh \
        -f "config/opensearch-security/${f%%:*}.yml" -t "${f#*:}" -icl -nhnv \
        -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
    done
    ```
    Each file ends with `Done with success`. Sometimes the tool then shows a
    `java.nio.channels.ClosedSelectorException`. This message comes from the HTTP client of the tool
    when it closes, after the load. You can ignore it.
5. Run `docker compose up -d`.

The same loop loads a changed `javv` role. If a release changes the role, its notes tell you. We did
these steps on the real compose files, from an OpenSearch that a `main` checkout started.

### On Kubernetes (Helm)

Each release publishes the JAVV chart and the OpenSearch chart
([`DEPLOYING.md`](DEPLOYING.md#install-on-kubernetes-with-helm)) at `oci://ghcr.io/danube-labs/charts`,
with the version of the release.

**Prerequisites:**

- Your settings in your own values files. An install with `--set`, as in `DEPLOYING.md`, writes no
  values file. Thus, before the first upgrade, write the values of each release to a file:
    ```bash
    helm get values store -o yaml > my-store-values.yaml
    helm get values javv -o yaml > my-javv-values.yaml
    helm get values scanner -n javv-scanner -o yaml > my-scanner-values.yaml   # in each scanned cluster
    ```
- These files hold each value that you set, the passwords included. Keep them as safe as your
  Secrets.

**Steps:**

1. Upgrade with the chart of the new release and the same files. `VERSION` is the release that you
    upgrade to:
    <!-- x-release-please-start-version -->
    ```bash
    VERSION=0.9.4
    helm upgrade store oci://ghcr.io/danube-labs/charts/javv-opensearch --version "$VERSION" \
      -f my-store-values.yaml
    helm upgrade javv oci://ghcr.io/danube-labs/charts/javv --version "$VERSION" -f my-javv-values.yaml
    helm test javv
    ```
    <!-- x-release-please-end -->
    - Do the `store` upgrade when the release changed the OpenSearch chart.
      [Version notes](#version-notes) tells you which releases did.
    - It is safe to do it when the chart did not change. Then the upgrade changes only labels, and
      OpenSearch does not restart.
2. Upgrade the scanners last, in each cluster that you scan, after JAVV runs the new release. Keep
    your values file (`backendUrl` and the token Secrets):
    <!-- x-release-please-start-version -->
    ```bash
    VERSION=0.9.4
    helm upgrade scanner oci://ghcr.io/danube-labs/charts/javv-scanner --version "$VERSION" \
      -n javv-scanner -f my-scanner-values.yaml
    ```
    <!-- x-release-please-end -->
    - A newer scanner can send a report format that only the newer backend accepts.
    - The `javv-scanner` chart holds the scanner versions of its release.
    - When the refresh container changes, the upgrade starts a vuln-DB refresh. The refresh
      container changes with the image, the DB source, `extraEnv`, `resources` or `pullPolicy`.
    - The next cycle uses the new image.

**While the backend restarts:**

- The backend runs as one pod with `strategy: Recreate`. The backend runs the background jobs, so
  two backends must never run at the same time. Kubernetes stops the old pod before it starts the
  new pod.
- JAVV is not available for some seconds, while the new pod checks OpenSearch and upgrades the
  indices. The startup probe gives this step 300 seconds.
- During this time, the frontend replies 502, and the web app shows "backend not answering".
- Kubernetes replaces the frontend with no gap.

**To go back to a previous revision,** use one command. `helm history javv` lists the revisions:

```bash
helm rollback javv          # to the revision before the current one
helm rollback javv 3        # or to a specific revision
```

- The settings and the images of that revision come back.
- The indices stay as the newer release left them, and an older backend can read them
  ([Go back to a previous release](#go-back-to-a-previous-release)).
- CI does an upgrade and a rollback for each change to the charts.
- For the scanners, run `helm rollback scanner` in each scanned cluster. Do this before you go back
  to the previous JAVV release.

**To change an OpenSearch password** (of `admin`, or of `javv`, the user that the backend signs in
as), see the
[`javv-opensearch` chart README](../deploy/helm/javv-opensearch/README.md#change-a-password).

- After you change the `javv` password, restart the backend. Then it reads the new password from
  the same Secret: `kubectl rollout restart deploy/javv-backend`.
- The same section of the README tells you how to load the `javv` role and its mapping into an
  OpenSearch that first started without them.

## Check what runs

| Check | Where | Expected result |
|---|---|---|
| OpenSearch replies | `GET /readyz` (no sign-in) | `200` |
| The versions that run | `GET /api/v1/meta` (with a signed-in session) | `{"version": "<release>", "mapping_version": <n>, "envelope_versions": [...]}` |
| The versions that run, in the web app | The bottom of the sidebar | Three lines: `v<release>`, `store schema v<n>`, `scanner schema v<n>` |
| What the upgrade did | The backend log, one line for each pod start | The event `bootstrap complete`, with `app_version`, `mapping_version`, and the indices in `created`, `updated` or `unchanged` |
| The scanners use the new version | The **Scanner status** page, after the next scan cycle | The new scanner version for each cluster |

On the first start of a new release, `updated` lists the indices whose schema changed. Later starts
list all indices as `unchanged`.

## Go back to a previous release

- **The indices stay safe when you go back to an older backend.** The index setup changes indices
  only to a newer schema. An older release finds the indices at a newer schema version, and it does
  not change them. The fields that the newer release added stay, and the older release does not use
  them.
- **The older release can read the settings that the newer release saved.** The newer release can
  add a field to a setting. If you saved that setting, the older release ignores the new field. The
  backend logs `stored setting has unknown keys` one time for each setting. It counts each of these
  reads in `javv_stored_setting_unknown_fields_total`
  ([`API.md` § Metrics](API.md#metrics)). If you **save** that setting while the
  older release runs, the older release saves only the fields that it knows. After you upgrade
  again, the new field has its default value. This is true when you go back to 0.4.8 or later.
- **Go back with the scanners first** when the report format changed between the two releases.
  Then the scanners do not send a format that the older backend refuses.
- **A release before 0.7.0 needs the old name of the secret key.** These releases read
  `JAVV_TOKEN_PEPPER` (docker compose) or the key `token-pepper` of `secrets.existingSecret` (Helm).
  If you deleted it after the upgrade to 0.7.0, put it back with the same value before you go back:
    - docker compose: `sed -n 's/^JAVV_SECRET_KEY=/JAVV_TOKEN_PEPPER=/p' .env >> .env`. Without it,
      `docker compose up` stops with `set JAVV_TOKEN_PEPPER in .env`, and the newer release
      continues to run.
    - Helm with `secrets.existingSecret`: copy the value of `secret-key` into `token-pepper`.
      Without it, `helm rollback javv` succeeds, but the older backend pod does not start
      (`couldn't find key token-pepper in Secret`). JAVV is not available until you copy the value.
      ```bash
      kubectl patch secret <your-secret> --type merge -p \
        "{\"data\":{\"token-pepper\":\"$(kubectl get secret <your-secret> -o jsonpath='{.data.secret-key}')\"}}"
      ```
- **CI tests a rollback from each change to the last release.** On a new docker compose store,
  CI starts the last release and writes data with it. Then CI starts the change, the last release
  again, and the change again. After each start, CI signs in and reads the same findings and the
  same SLA policy.
- **A snapshot does not give a rollback in one step.** A restore makes `restored-*` copies next to
  the live indices. It never writes over them
  (`POST /api/v1/admin/snapshots/{snapshot_name}/restore`). To use a copy, you must move it into
  place manually.

## The first run of the background jobs

From 0.5.0, **the backend starts its own background jobs.** On an installation that ran these jobs
only manually, or never, the first scheduled runs do all the work at the same time:

- **The lifecycle sweep** (03:00 by default) deletes all scan history that is older than the
  retention of each cluster (90 days by default). After this, time travel cannot show that period.
  Before the jobs run for the first time, see what the sweep will do: **Data inspector › Repair
  actions › Lifecycle sweep › Dry run**. If it deletes more than you want, increase the retention in
  **Settings › Data & OpenSearch**.
- **The staleness sweep** (02:00) marks as stale each finding that no scan found again for 3 days. It
  also marks as stale all findings of a scanner that sent nothing for 7 days.
- **The findings cleanup** (04:00) deletes the findings that no scan reported for longer than its
  period (180 days).

A job does not run because the backend started. Each job waits for its next scheduled time.

- To stop all the jobs, start the backend with `JAVV_SCHEDULER_ENABLED=false`.
- To stop one job, set its `JAVV_JOB_<KIND>_CRON` to an empty value.
- [Job schedules and the time zone](CONFIGURATION.md#job-schedules-and-the-time-zone) gives the
  schedules, and the time zone that the backend uses for them.

If you ran these jobs from your own cron or from CronJobs, delete them. The scheduler of the
backend replaces them. If both run, nothing breaks: the backend does not start a job that is
already running. But the second run is work for no result.

## Version notes

A release gets an entry here when it needs something from you. These are the conditions:

- The store schema changed (`mapping_version`).
- The report formats that the backend accepts changed (`envelope_versions`).
- The scanner images must be published again, or changed together with the release.
- The OpenSearch chart (`javv-opensearch`) changed. Then do the `store` upgrade.

The entries start with 0.6. Before 0.6, each schema change only added fields, and the backend
applied it automatically on the first start.

| Release | Store schema | Report formats accepted | What to do |
|---|---|---|---|
| 0.9.1 | 20 | 3 and 4 | Nothing. The backend adds a field to the store on the first start. |
| 0.8.9 | 19 | 3 and 4 | The notes **A new permission for the export files** and **A new permission for dashboards** below |
| 0.8.7 | 18 | 3 and 4 | The note **JAVV refuses a username with a capital letter** below |
| 0.8.0 | 18 | 3 and 4 | The note **A bootstrap admin password longer than 256 characters stops the backend** below |
| 0.7.0 | 18 | 3 and 4 | The note **`JAVV_TOKEN_PEPPER` is now `JAVV_SECRET_KEY`** below |
| 0.6.2 | 18 | 3 and 4 | The note **JAVV retires clusters that send no scans** below |
| 0.6.0 | 18 | 3 and 4 | The note **How the backend connects to OpenSearch** below |

No release from 0.4.8 to 0.8.0 changed the store schema (18) or the report formats that the
backend accepts (3 and 4).

No release up to and including 0.9.0 changed the OpenSearch chart in a way that needs the `store`
upgrade. Each release changed its version number. Some releases also changed other parts of the
chart, but not OpenSearch:

- 0.7.1 and 0.8.6 changed the text of its README and of the comments in `values.yaml`, and no
  value. 0.8.1 changed the text of its README.
- 0.8.7 changed the test pod of the chart (`helm test store`). The pod can now run in a namespace
  with the `restricted` level of the pod security standards.

### 0.8.9: a new permission for the export files

A user now needs the permission `can_export` to download a file of the data:

- the CSV and VEX files of the findings
- the CSV files of the audit log, the contributors and the approvals queue
- an export report

Without the permission, these requests get 403. The `viewer` role does not get it. A viewer can
still read the data on the screens and through the API.

A new store gives the permission to the `triager`, `security_lead` and `admin` roles. But JAVV
writes the roles only on the first start of a store. Thus on a store that you have, only `admin`
gets the permission, because `*` holds each permission. Also, each user keeps a copy of the
permissions of its role.

After the upgrade, give the permission to the `triager` and `security_lead` roles and to their
users:

1. Save this script as `can-export.sh`, in the folder of your installation:
    ```sh
    # Adds can_export to the triager and security_lead roles, and to their users.
    login=$(printf %s "$OPENSEARCH_INITIAL_ADMIN_PASSWORD" | sed 's/[\\"]/\\&/g')
    curl -sSk -K - -X POST 'https://localhost:9200/system-roles,system-users/_update_by_query?refresh=true' \
      -H 'content-type: application/json' -d '{
      "query": {"terms": {"role": ["triager", "security_lead"]}},
      "script": {"lang": "painless", "source": "def c = ctx._source.capabilities; if (c == null || c.contains(\"can_export\")) { ctx.op = \"noop\" } else { c.add(\"can_export\") }"}
    }' <<EOF
    user = "admin:$login"
    EOF
    echo
    ```
2. Run the script in the OpenSearch container:
    ```bash
    docker compose exec -T opensearch sh < can-export.sh
    ```
    The answer has `"failures":[]`. `updated` is the number of roles and users that the script
    changed. If you run the script again, it changes nothing.

The script reads the admin password in the container, as the health check of the compose file
does. Thus the password is not in your shell history or in the arguments of a process. The users
do not sign in again: JAVV reads the permissions of a user on each request.

On Kubernetes, or with an OpenSearch of your own, send the same request to your OpenSearch, with
its admin.

We did these steps on the compose files of 0.8.8, with a triager and a security lead.

### 0.8.9: a new permission for dashboards

A user needs the permission `can_edit_dashboards` to make a dashboard. The `viewer` role does not
get it.

The store schema is now 19. At its first start, the backend makes the new index
`system-dashboards`. You do not do a step for it. The `javv` role of an OpenSearch of your own
already has access to it, because its name starts with `system-`.

A new store gives the permission to the `triager`, `security_lead` and `admin` roles. On a store
that you have, only `admin` gets it, because JAVV writes the roles only on the first start of a
store. Also, each user keeps a copy of the permissions of its role.

After the upgrade, give the permission to the `triager` and `security_lead` roles and to their
users:

1. Save this script as `can-edit-dashboards.sh`, in the folder of your installation:
    ```sh
    # Adds can_edit_dashboards to the triager and security_lead roles, and to their users.
    login=$(printf %s "$OPENSEARCH_INITIAL_ADMIN_PASSWORD" | sed 's/[\\"]/\\&/g')
    curl -sSk -K - -X POST 'https://localhost:9200/system-roles,system-users/_update_by_query?refresh=true' \
      -H 'content-type: application/json' -d '{
      "query": {"terms": {"role": ["triager", "security_lead"]}},
      "script": {"lang": "painless", "source": "def c = ctx._source.capabilities; if (c == null || c.contains(\"can_edit_dashboards\")) { ctx.op = \"noop\" } else { c.add(\"can_edit_dashboards\") }"}
    }' <<EOF
    user = "admin:$login"
    EOF
    echo
    ```
2. Run the script in the OpenSearch container:
    ```bash
    docker compose exec -T opensearch sh < can-edit-dashboards.sh
    ```
    The answer has `"failures":[]`. `updated` is the number of roles and users that the script
    changed. If you run the script again, it changes nothing.

The users do not sign in again: JAVV reads the permissions of a user on each request.

On Kubernetes, or with an OpenSearch of your own, send the same request to your OpenSearch, with
its admin.

We sent the request of the script two times to OpenSearch 3.9.0, with the roles and users of
0.8.8. The first time changed the two roles and their users. The second time changed nothing.

### 0.8.7: JAVV refuses a username with a capital letter

A new username must be in lower case. Before 0.8.7, `Alice` and `alice` could be two different
users. Users that exist keep their names.

- **New users.** `POST /api/v1/admin/users` gives 422 for a username with a capital letter, with
  the message `a username must be in lower case`.
- **The first admin.** A `JAVV_BOOTSTRAP_ADMIN_USERNAME` with a capital letter stops the backend at
  each start, also when the first admin exists. The backend shows
  `invalid settings: JAVV_BOOTSTRAP_ADMIN_USERNAME: Value error, a username must be in lower case`.
  Then set the name in lower case. If no user has that name, and you set
  `JAVV_BOOTSTRAP_ADMIN_PASSWORD`, the backend makes a new first admin. The old admin stays.
- **Sign-in.** A user can type a lower-case username in any case: `ALICE` signs in as `alice`. A
  user whose name has a capital letter, for example `Alice`, must type the name exactly. The
  sign-in lock counts the failures of all cases of a name together.

### 0.8.0: a bootstrap admin password longer than 256 characters stops the backend

A sign-in accepts a password of 256 characters at most. A first admin with a longer
`JAVV_BOOTSTRAP_ADMIN_PASSWORD` could never sign in. The backend now refuses such a value at start,
and shows `invalid settings: JAVV_BOOTSTRAP_ADMIN_PASSWORD: String should have at most 256
characters`. It does this also when the first admin exists, because the backend reads the setting
at each start.

If you see this error, set a password of 256 characters or fewer. A new value does not change
the password of an admin that exists.

### 0.7.0: `JAVV_TOKEN_PEPPER` is now `JAVV_SECRET_KEY`

Only the name changes. **Keep the same value.** A backend that finds the old name stops at start,
and it shows the new name. If you change the value:

- Each scanner gets 401 and needs a new token.
- Each user must sign in again.
- Each open download link stops working.

- **docker compose:** in `.env`, add the new name with the same value. Keep the line with the old
  name until you do not need to go back to a release before 0.7.0:
  ```bash
  sed -n 's/^JAVV_TOKEN_PEPPER=/JAVV_SECRET_KEY=/p' .env >> .env
  ```
  Until you add the new name, `docker compose up` stops with `set JAVV_SECRET_KEY in .env`. The
  `compose.yaml` of 0.7.0 and later gives only `JAVV_SECRET_KEY` to the backend. Thus the old name
  in `.env` has no effect on it.
- **Helm, with the value in your values file:** change the name `secrets.tokenPepper` to
  `secrets.secretKey`, and keep its value. Until you do this, the upgrade stops with
  `additional properties 'tokenPepper' not allowed`. If you set the value with `--set`, write your
  values to a file first (see [On Kubernetes (Helm)](#on-kubernetes-helm)). Change the name in
  `my-javv-values.yaml`. Then upgrade with `-f my-javv-values.yaml`.
- **Helm, with `secrets.existingSecret`:** the chart now reads the key `secret-key` from that
  Secret. Before the upgrade, copy the value of `token-pepper` into it:
  ```bash
  kubectl patch secret <your-secret> --type merge -p \
    "{\"data\":{\"secret-key\":\"$(kubectl get secret <your-secret> -o jsonpath='{.data.token-pepper}')\"}}"
  ```
  Keep the key `token-pepper` until you do not need to go back to a release before 0.7.0. Those
  releases read only `token-pepper`. After that, you can delete it.

### 0.6.2: JAVV retires clusters that send no scans

A new daily job retires a cluster that sent no accepted scan for 45 days
(`JAVV_CLUSTER_RETIRE_AFTER_DAYS`). A retired cluster is not in the cluster list, in the cluster
selector or in All clusters. JAVV keeps all of its data and its tokens. The cluster comes back with
its next accepted scan. You can also bring it back manually:
`POST /api/v1/clusters/{cluster_id}/unretire`.

The first run (04:15 by default) retires each cluster that sent no scan for that time. An example
is a cluster that you made again: it comes back with a new ID. To keep a cluster, do one of these
steps:

- Set its period to never: `PUT /api/v1/settings/retirement` with its `cluster_id`,
  `retire_after_days: null`, and `warn_days` as before.
- Set `JAVV_CLUSTER_RETIRE_AFTER_DAYS=0` to stop retirement for all clusters.

When no cluster had an accepted scan within its scanner-down period, the job retires nothing, and
it logs a warning. This condition shows a problem in JAVV, not in the clusters.

### 0.6.0: how the backend connects to OpenSearch

There are two changes, both on purpose:

- **A `JAVV_OPENSEARCH_URL` that holds a user or a password stops the backend at start.** Earlier
  releases sent `https://user:pass@host` (or `user:pass@host`, with no scheme) to the client. Move
  the credentials into `JAVV_OPENSEARCH_USERNAME` and `JAVV_OPENSEARCH_PASSWORD`
  ([Connection to OpenSearch](CONFIGURATION.md#connection-to-opensearch)).
- **A wrong setting stops the start, with one line for each variable:**
  `invalid settings: JAVV_<NAME>: <reason>`. The line holds no value from your environment.
  Earlier releases showed part of the environment, and secrets could be in it.

The token command (`python -m backend.core.tokens`) and the scan-scope command now also use
`JAVV_REQUEST_TIMEOUT`, as the rest of the backend did before (30 seconds by default).
