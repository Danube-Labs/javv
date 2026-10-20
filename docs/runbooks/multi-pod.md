# Scaling and failures

This page tells you how many copies of each part of JAVV run, and why. It also tells you how each
part recovers when it fails.

JAVV runs as **one backend, one frontend and one OpenSearch node**:

- The compose file and the charts install this setup.
- CI tests this setup.
- JAVV supports only this setup.

## What the charts run

| Part | Copies | Can you change the number? |
|---|---|---|
| Backend (`javv` chart) | 1, with `strategy: Recreate` | **No.** The chart refuses a `backend.replicas` value. Nobody tested more than one backend, and JAVV does not support it. |
| Frontend (`javv` chart) | `frontend.replicas`, 1 by default | The chart accepts more than one, because the frontend keeps no state. Nobody tested more than one. |
| OpenSearch (`javv-opensearch` chart, compose) | 1 node | **No.** The chart refuses all other values. For more nodes, use an OpenSearch that you operate. |
| Scanners (`javv-scanner` chart, in each cluster that you scan) | One CronJob for each scanner. Only one cycle runs at a time (`concurrencyPolicy: Forbid`). | No |

## Why one backend

The backend runs the background jobs of JAVV on schedules:

- The jobs are staleness, lifecycle, findings cleanup, cluster retirement, report drain, report
  sweep and session sweep.
- The schedules are the `JAVV_JOB_*_CRON` settings in [Configuration](../CONFIGURATION.md).
- No CronJob and no second container runs these jobs. Thus the backend is one process.

A rolling update can run two backends for a short time. To prevent this, the Deployment uses
`Recreate`: Kubernetes stops the old pod before it starts the new pod. During an upgrade, there is
a short time when no backend runs:

- The browsers show a banner that tells you that the backend is not available. The banner goes
  away when the backend replies again.
- The scanners try each push again, with a longer wait each time. When all tries fail, a scanner
  keeps the push in its dead-letter file. In its next cycle, it scans the image again.

## Failures and recovery

JAVV has no high-availability layer of its own. Each part is one copy. Kubernetes or docker compose
starts the part again when it fails.

- **The backend** stops at start when it cannot connect to OpenSearch.
    - Its restart policy starts it again until OpenSearch replies.
    - When OpenSearch stops, the backend reports that it is not ready (`/readyz`). Then its
      Service stops sending requests to it, and nothing restarts it.
- **The frontend** keeps no state. A new frontend is ready immediately. When a frontend stops during
  a scanner push, the scanner sends that push again.
- **OpenSearch** keeps its data on its volume. When OpenSearch starts again, it reads the data
  again.
    - To keep the data available when a node fails, you need more nodes and replica shards.
    - For this, use an OpenSearch that you operate. JAVV connects to it with no change. See
      [Deploying: an OpenSearch of your own](../DEPLOYING.md#an-opensearch-of-your-own) and
      [Sizing OpenSearch](opensearch-sizing.md).
- **Backups:** make a snapshot manually in **Settings › Data & OpenSearch › Snapshots**. JAVV does
  not make scheduled snapshots yet.
