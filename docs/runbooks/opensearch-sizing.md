# Sizing OpenSearch

This page tells you how much shard space, memory and disk OpenSearch needs for your clusters. It
also tells you which limit you get to first, and what to change when you get near a limit.

JAVV keeps all of its data in one OpenSearch: the scan results, their history, and each triage
decision. The figures marked *measured* come from one development install: 4 clusters, about 1.7
million documents, OpenSearch 3.9.0 and a 1 GB heap.

## Calculate the size of the history

Each scan writes a full copy of what it found. JAVV writes one document for each finding, for each
image, for each scanner and for each scan cycle. Time travel reads this history. The history is
almost all of the data in OpenSearch.

| Index | Contents | Measured |
|---|---|---|
| `javv-finding-occurrences-<cluster>-*` | The history: one document for each finding in each scan | 1.54 M documents, 436 MB, about **280 bytes each** |
| `findings` | The current state of each finding, with its triage | 123 k documents, 60 MB, about 490 bytes each |
| `javv-scan-events-*`, `javv-images-*`, `javv-inventory-runs-*`, `javv-ingest-failures-*` | One document for each scan, or for each image in each cycle | Less than 6 MB in total |
| `system-*` | Users, sessions, decisions, the audit log, settings and reports | Less than 4 MB in total |

The sizes are for the primary copy. To calculate the size of the history for your clusters, use
these two formulas:

```text
documents per day ≈ for each scanner: images × findings per image × scan cycles per day
history size      ≈ documents per day × (retention days + 30) × 280 bytes
```

The formula adds 30 days for two reasons:

- An index can hold up to 30 days of documents before JAVV starts a new index.
- JAVV deletes an index only when its newest document is older than the retention.

The scanner chart runs each scanner every 6 hours by default. That is 4 cycles each day.

**Example:** 500 images, 40 findings for each image, two scanners, 4 cycles each day and the
default retention of 90 days:

- 500 × 40 × 2 × 4 = 160,000 documents each day.
- 160,000 × 120 days × 280 bytes ≈ 5.4 GB.

OpenSearch also keeps each scheduled export until the export expires. The expiry time is
`JAVV_EXPORT_TTL_HOURS` (24 hours by default). The maximum size of one export is
`JAVV_EXPORT_MAX_BYTES` (500 MiB).

## Check the shard count

Shards are usually the first limit.

- Each index has **one primary shard**.
- Each cluster that you scan has five series of indices.
- JAVV starts a new index in a series at the first of these limits: 30 days, 5 million documents or
  50 GB.
- JAVV deletes an index when all of its data is older than the retention of the cluster.
- With the default settings (a new index each 30 days, a retention of 90 days), each series keeps
  about five indices. Thus **each cluster that you scan uses about 25 shards**.
- Other indices use about 15 shards. This number does not change when you add clusters.
- The audit log is not in that count. It starts a new index each 30 days, and JAVV never deletes
  it.

By default, OpenSearch permits **1,000 shards on each node** (`cluster.max_shards_per_node`):

- With the default settings, one node has space for **about 38 clusters that you scan**.
- This number is a calculation from the default settings. Nobody did a load test to get it.
- Each shard also uses heap memory, whatever its size.

To see the current shard count, do one of these steps:

- In JAVV, go to **Settings › Data & OpenSearch**. The runtime card shows the active shards.
- Send `GET _cluster/health` to OpenSearch, and read `active_shards`.

## Make space for more shards

Do these steps in this sequence. Stop when the shard count is low enough.

1. **Decrease the retention** of the clusters that do not need a long history. Go to **Settings ›
    Data & OpenSearch › Retention**, and set the retention for each cluster. A shorter retention
    also decreases how far time travel can go back.
2. **Increase the time between new indices** in the same panel. This gives fewer, larger indices.
    JAVV still starts a new index at 5 million documents or at 50 GB.
3. **Delete the clusters that stopped sending scans.** JAVV retires these clusters. A retired
    cluster uses shards until you delete it in **Settings › Cluster**.
4. **Add nodes.** For this, use an OpenSearch that you operate (see
    [Beyond one node](#beyond-one-node)). Alternatively, increase `cluster.max_shards_per_node`,
    and increase the heap by the same proportion.

## Memory

The default heap is **1 GB**:

- The compose file sets it in `OPENSEARCH_JAVA_OPTS`.
- The `javv-opensearch` chart sets it in `opensearchJavaOpts`.
- *Measured:* 4 clusters, 1.7 million documents and 42 shards used about half of the heap.

Increase the heap in these two conditions:

- The heap use stays high.
- The OpenSearch log shows `circuit_breaking_exception`. This message tells you that OpenSearch
  refuses work to protect its memory.

Follow these rules when you increase the heap:

- Give the OpenSearch container about two times the heap as memory. OpenSearch also uses memory
  outside the heap.
- Keep the heap less than 32 GB.
- In compose, set `OPENSEARCH_JAVA_OPTS`, for example `-Xms2g -Xmx2g`.
- With the chart, set `opensearchJavaOpts` and the memory `resources` of the pod together.

## Disk

At **95 %** disk use, OpenSearch makes the indices read-only. This limit is the flood-stage
watermark of OpenSearch. When it occurs:

- Writes fail.
- JAVV sends **503** in reply to each scanner push. JAVV records the refused write as
  `storage_error`.
- The scanners try the push again, with a longer wait each time. When all tries fail, a scanner
  keeps the push in its dead-letter file. In its next cycle, it scans the image again.
- In the web app, reads work. Sign-in and each change fail with
  `The store is read-only: its disk is full`, and a banner on each screen says so.
- OpenSearch keeps all the data that it stored before. New scans wait until there is disk space.
- When there is disk space again, OpenSearch lifts the block itself. JAVV needs no restart.

To prevent this condition:

- Keep the disk use **less than about 80 %**. Then a large number of scans cannot get to the limit.
- Remember that **snapshots are on the data volume**. In the compose file and in the chart,
  `path.repo` is `/usr/share/opensearch/data/snapshots`. Thus snapshots use the same disk. Delete
  old snapshots, or use a snapshot repository on different storage.
- Decrease the retention to make disk space. The lifecycle job deletes whole indices at its next
  run. It runs at 03:00 by default (`JAVV_JOB_LIFECYCLE_SWEEP_CRON`).

## Beyond one node

The compose file and the `javv-opensearch` chart run **one OpenSearch node**. The chart refuses
all other values.

For more capacity, or for OpenSearch data that stays available when a node fails:

- Operate your own OpenSearch with more nodes and with replica shards, and connect JAVV to it. See
  [Deploying: an OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own).
- JAVV needs no change for this.
- [Scaling and failures](multi-pod.md) tells you which parts of JAVV scale.
