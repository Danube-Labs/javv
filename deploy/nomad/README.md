# Scan a Nomad cluster

Two Nomad jobs scan the running Docker images of a Nomad cluster and push the results to JAVV.
`javv-scan-trivy` uses Trivy. `javv-scan-grype` uses Grype. JAVV then shows the Nomad cluster as it
shows a Kubernetes cluster.

**We tested these files with Nomad 2.1.1:** one agent, ACLs on, the Docker task driver. The jobs
ran the images `javv-scanner-trivy:0.76.2` and `javv-scanner-grype:0.121.1`.

## How the jobs work

- Each job is a periodic batch job. It runs every 6 hours.
- The job reads the running allocations of all the namespaces from the Nomad API.
- It scans each image of a running task of the Docker driver.
- It gets the digest of each image from the output of the scanner.
- It pushes one scan cycle to JAVV, as [Push from your own script](../../docs/INGEST-CONTRACT.md)
  tells.
- It does not scan itself.

JAVV shows each Nomad job as a namespace:

| Nomad namespace | Nomad job | Namespace in JAVV |
|---|---|---|
| `default` | `web` | `web` |
| `billing` | `web` | `billing/web` |
| Each | A run of a periodic job, for example `nightly/periodic-1794157382` | `nightly` |

## Before you start

- You need a Nomad token that can apply ACL policies, write variables and create volumes.
- The clients need the Docker task driver.
- The clients must reach `ghcr.io`, the registries of your images, and JAVV.
- You need the files of this folder: [`javv-scan-trivy.nomad.hcl`](javv-scan-trivy.nomad.hcl),
  [`javv-scan-grype.nomad.hcl`](javv-scan-grype.nomad.hcl),
  [`javv-scan.policy.hcl`](javv-scan.policy.hcl),
  [`javv-trivy-cache.volume.hcl`](javv-trivy-cache.volume.hcl),
  [`javv-grype-cache.volume.hcl`](javv-grype-cache.volume.hcl) and
  [`javv_nomad_push.py`](javv_nomad_push.py).

## Install the jobs

Run the commands in the folder that holds the files.

1. In JAVV, make two tokens for the cluster: one for `trivy`, one for `grype`. See
   [Before you start](../../docs/INGEST-CONTRACT.md#before-you-start) of the push page.
2. Put each token in the Nomad variable of its job. Only that job can read it:

    ```bash
    nomad var put nomad/jobs/javv-scan-trivy javv_token=<the Trivy token>
    nomad var put nomad/jobs/javv-scan-grype javv_token=<the Grype token>
    ```

3. Make the volumes for the databases of the scanners:

    ```bash
    nomad volume create javv-trivy-cache.volume.hcl
    nomad volume create javv-grype-cache.volume.hcl
    ```

4. Run the jobs. Set the address of JAVV and the ID of the cluster in JAVV:

    ```bash
    nomad job run -var javv_url=https://javv.example.com -var cluster_id=nomad-prod-01 \
      javv-scan-trivy.nomad.hcl
    nomad job run -var javv_url=https://javv.example.com -var cluster_id=nomad-prod-01 \
      javv-scan-grype.nomad.hcl
    ```

5. Give the jobs read access to the jobs of all the namespaces:

    ```bash
    nomad acl policy apply -namespace default -job javv-scan-trivy \
      javv-scan-trivy javv-scan.policy.hcl
    nomad acl policy apply -namespace default -job javv-scan-grype \
      javv-scan-grype javv-scan.policy.hcl
    ```

6. Start a first run, and read its log:

    ```bash
    nomad job periodic force javv-scan-trivy
    nomad job status javv-scan-trivy          # the runs, with their allocations
    nomad alloc logs -stderr <allocation ID> push
    ```

7. In JAVV, select the cluster and open **Running images**.

The jobs get the Nomad token from Nomad (`identity { env = true }`). You do not make a Nomad token
for them.

## Settings

- To change a setting, add it to the `env` block of the job. Then run the job again.
- To see what a job scans without a push, set `JAVV_DRY_RUN` to `true`.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_NOMAD_SKIP_JOBS` | Empty | The Nomad job IDs to skip, separated by commas. A `*` is a pattern. Example: `batch-*,legacy-api`. |
| `JAVV_NOMAD_NAMESPACES` | `*` | The Nomad namespaces to read. Example: `default,billing`. |
| `JAVV_DRY_RUN` | `false` | `true`: the job writes the images to its log, and pushes nothing. |

The jobs also use these settings of the JAVV scanners, with the same names and defaults:

- [Trivy settings](../../docs/CONFIGURATION.md#trivy-settings), for example `JAVV_TRIVY_SEVERITIES`.
- [Grype settings](../../docs/CONFIGURATION.md#grype-settings), for example `JAVV_GRYPE_ONLY_FIXED`.
- `JAVV_PUSH_RETRY_BUDGET_SECONDS` (`360`) and `JAVV_LOG_LEVEL` (`info`).

## Skip jobs from JAVV

The jobs obey the scan scope of the cluster in JAVV (**Settings › Scan scope**):

| Field in JAVV | For Nomad |
|---|---|
| Included namespaces, ignored namespaces | The namespace in JAVV of a job, for example `web` or `billing/*` |
| Excluded image patterns | The image of a task, for example `redis:*` |
| Skip workload kinds | The type of a Nomad job: `service`, `batch`, `system` or `sysbatch` |

If JAVV does not send the scope, the job does not scan in this run.

## When a run fails

- Exit code `1`: JAVV did not reply, or a scan or a push failed.
- Exit code `2`: a setting is not valid. The log tells the correct values.
- Nomad does not start a failed run again. The next run of the schedule tries again.
- If no image scanned, the cycle stays `partial`. JAVV keeps the images of the last good cycle.

## Known gaps

- We tested the jobs with Nomad 2.1.1 only, with one agent in dev mode.
- The jobs scan tasks of the Docker driver only. They do not scan tasks of other drivers.
- The scanner gets the image by its tag at the time of the scan. If the tag moved after the task
  started, JAVV shows the new image. Use images by digest (`image@sha256:…`) to prevent this.
- A batch job that does not run at the time of the scan is not in the scan.
- When an image stops, its findings stay open until the staleness sweep marks them stale (3 days by
  default).
- The job reads the Nomad API at `http://127.0.0.1:4646`, on the network of the host. We did not
  test a Nomad API with TLS.
- A private registry needs its credentials in the job, in the variables of Trivy or Grype. We did
  not test this.
- We did not test a mirror of the scanner databases (`TRIVY_DB_REPOSITORY`, `GRYPE_DB_UPDATE_URL`).
- Each cache volume is on one client. Nomad runs the job only on the client with its volume.
- The web app uses words of Kubernetes, for example **Namespace** and "pods".
