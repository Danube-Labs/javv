# Indices and data

This page tells you which OpenSearch indices JAVV uses, what each index holds, and how long JAVV
keeps the data. It also tells you what a snapshot holds. For the disk space and the shards that the
data needs, see [Sizing OpenSearch](opensearch-sizing.md).

JAVV keeps all of its data in one OpenSearch:

- The name of each index of JAVV is `findings`, or it starts with `javv-` or `system-`.
- The `javv` role of OpenSearch permits only these indices, and the `restored-*` copies that a
  restore writes ([An OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own)).

## See the indices

1. Sign in as a user with the permission `can_inspect_store`.
2. Open the **Data inspector**.
3. Send `GET _cat/indices`. The answer shows only the indices of JAVV, with the number of documents
    and the size of each index.

## Change how long JAVV keeps the history

1. Sign in as a user with the permission `can_manage_retention`.
2. Go to **Settings › Data & OpenSearch**.
3. In **Retention**, set the days for all clusters, or for one cluster.

- The lifecycle sweep deletes the history indices that are older than the new retention at its
  next run (03:00 by default).
- After that, time travel cannot show that period.
- [Retention and rollover](../CONFIGURATION.md#retention-and-rollover) gives the settings.

## Back up the data

A snapshot from **Settings › Data & OpenSearch › Snapshot now**:

- **Holds** `findings`, `javv-images-*` and `system-*`, except `system-sessions`. These indices hold
  the current state, the triage, the decisions, the users, the settings and the audit log.
- **Does not hold the sessions.** A sign-out only marks its session as ended, so a restored copy
  could make an ended session valid again. After a restore, the users sign in again.
- **Does not hold the scan history** (`javv-finding-occurrences-*`, `javv-scan-events-*`,
  `javv-inventory-runs-*` and `javv-ingest-failures-*`), `javv-scan-orders` or
  `javv-scan-watermarks`. Thus a restore does not bring back the history that time travel reads.

Also:

- JAVV does not make scheduled snapshots yet.
- A restore writes `restored-*` copies, and never writes over the live indices.
- [Snapshots](../CONFIGURATION.md#snapshots) tells you how to set up the snapshot repository.

## The history indices

Each cluster has its own series of each of these indices:

- JAVV makes the first index of a series when the cluster sends its first data.
- The lifecycle sweep starts a new index in a series at 30 days, 5,000,000 documents or 50 GB, the
  first limit that the series gets to.
- The sweep deletes an index when its newest data is older than the retention of the cluster (90
  days by default).
- Each limit is a setting ([Retention and rollover](../CONFIGURATION.md#retention-and-rollover)).

| Index | What it holds |
|---|---|
| `javv-finding-occurrences-<cluster_id>-*` | One document for each finding in each scan. Time travel reads it. It holds almost all of the data of JAVV. |
| `javv-scan-events-<cluster_id>-*` | One document for each image and scanner in each scan. It holds the count of each severity, the versions of the scanner and of its database, and the scan settings. |
| `javv-images-<cluster_id>-*` | The images of each scan cycle, with their counts. The **Images** page reads it. |
| `javv-inventory-runs-<cluster_id>-*` | One document for each scan cycle: the number of images that the scanner expected, and the number that JAVV received. |
| `javv-ingest-failures-<cluster_id>-*` | One document for each push that JAVV refused after the token check. The **Failed ingests** table reads it. |

## The audit log

| Index | What it holds | How long JAVV keeps it |
|---|---|---|
| `system-audit-log-*` | One document for each change and each sign-in, with the user and the time | JAVV starts a new index at the limits for all clusters (not the limits of one cluster). It never deletes an index of the audit log. |

## The current state and the settings

Each of these is one index. JAVV makes it at the first start of the backend.

| Index | What it holds | How long JAVV keeps it |
|---|---|---|
| `findings` | The current state of each finding, with its triage | The findings cleanup deletes a finding that no scan found for longer than its window (180 days by default, [Findings cleanup](../CONFIGURATION.md#findings-cleanup)). |
| `javv-scan-watermarks` | For each image and scanner, the newest scan that JAVV applied | The findings cleanup deletes the document of an image when `findings` has no row for the image. The last scan of the image must also be older than the cleanup window. |
| `javv-scan-orders` | The `scan_order` counter of each cluster and scanner | JAVV never deletes it. |
| `system-decisions` | The decisions, for example the risk acceptances, also the revoked ones | JAVV never deletes them. |
| `system-users` and `system-roles` | The users and the roles | JAVV never deletes them. An admin can disable a user. |
| `system-tokens` | The ingest tokens, as a hash | A revoked token stays, disabled. |
| `system-sessions` | The sign-in sessions | The session sweep deletes a session 24 hours after it ends (`JAVV_SESSION_SWEEP_GRACE_HOURS`). |
| `system-config` | The runtime settings, the cluster names and the retirement records | Until you change them |
| `system-views` | The saved views | Until the owner or a user with `can_manage_settings` deletes them |
| `system-dashboards` | The saved dashboards: their panels and who can see them | Until the owner or a user with `can_manage_settings` deletes them |
| `system-notifications` | The notifications of the bell | Until the user deletes them. The retirement sweep deletes a retirement notice when the cluster scans again. |
| `system-reports` and `system-report-chunks` | The queued exports and bulk actions, and the results of the exports | The report sweep deletes a finished export after the export lifetime (24 hours by default), and a failed job after the same time. |
| `system-jobs` | The last run of each background job | One document for each job, which JAVV writes again at each run |

## When you delete a cluster

A delete of a retired cluster deletes its history indices and its tokens. It also deletes its
documents in `findings`, `javv-scan-watermarks`, `javv-scan-orders`, `system-decisions`,
`system-notifications`, `system-reports` and `system-config`. It keeps its rows in the audit log
([Delete a cluster](../API.md#delete-a-cluster)).

JAVV never reads the `restored-*` copies, and it never deletes them. Delete them yourself when you
do not need them.
