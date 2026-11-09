# Scan a Nomad cluster

Two Nomad jobs scan the running Docker images of a Nomad cluster and push the results to JAVV.
`javv-scan-trivy` uses Trivy. `javv-scan-grype` uses Grype. JAVV then shows the Nomad cluster as it
shows a Kubernetes cluster.

The two jobs are examples. Change them for your cluster: for example, the source of the JAVV
token, the cache volumes or the schedule. The script `javv_nomad_push.py` does the work. It reads
the running images from the Nomad API, scans them and pushes the results to JAVV.

**Tested with:** JAVV 0.9.8, Nomad 2.1.1 (one agent, ACLs on), the Docker task driver, and the
images `javv-scanner-trivy:0.76.2` and `javv-scanner-grype:0.121.1`.

## How the jobs work

- Each job is a periodic batch job. It runs every 6 hours.
- The job reads the running allocations of all the namespaces from the Nomad API.
- It scans each image of a running task of the Docker driver.
- It gets the digest of each image from the output of the scanner.
- It pushes one scan cycle to JAVV, as [Push from your own script](../../docs/INGEST-CONTRACT.md)
  tells.
- It does not scan a job with the meta `javv_scan = "true"`. The two scan jobs have this meta.
  The log names each job that the scan skips for this reason.

JAVV shows each Nomad job as a namespace:

| Nomad namespace | Nomad job | Namespace in JAVV |
|---|---|---|
| `default` | `web` | `web` |
| `billing` | `web` | `billing/web` |
| `default` | A run of the periodic job `nightly`, for example `nightly/periodic-1794157382` | `nightly` |
| `billing` | A run of the periodic job `nightly` | `billing/nightly` |

## Before you start

- You need a Nomad token that can apply ACL policies, write variables and create volumes.
- The clients need the Docker task driver.
- The clients must reach `ghcr.io`, the registries of your images, and JAVV.
- You need the files of the folder [`deploy/nomad`](https://github.com/Danube-Labs/javv/tree/main/deploy/nomad):
  [`javv-scan-trivy.nomad.hcl`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv-scan-trivy.nomad.hcl),
  [`javv-scan-grype.nomad.hcl`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv-scan-grype.nomad.hcl),
  [`javv-scan.policy.hcl`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv-scan.policy.hcl),
  [`javv-trivy-cache.volume.hcl`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv-trivy-cache.volume.hcl),
  [`javv-grype-cache.volume.hcl`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv-grype-cache.volume.hcl) and
  [`javv_nomad_push.py`](https://github.com/Danube-Labs/javv/blob/main/deploy/nomad/javv_nomad_push.py).

## Install the jobs

Run the commands in the folder that holds the files.

1. In JAVV, make two tokens for the cluster: one for `trivy`, one for `grype`. See
   [Before you start](../../docs/INGEST-CONTRACT.md#before-you-start) of the push page.
2. Put each token in the Nomad variable of its job. The job can read its variable. Other tokens
   need a policy that gives them access to `nomad/jobs`. The commands read each token at a
   prompt, so the token is not in the shell history or in the process list. `-out none` stops the
   output of the variable with its token:

    ```bash
    read -rs -p 'Trivy token: ' t && echo
    printf '%s' "$t" | nomad var put -out none nomad/jobs/javv-scan-trivy javv_token=-
    read -rs -p 'Grype token: ' t && echo
    printf '%s' "$t" | nomad var put -out none nomad/jobs/javv-scan-grype javv_token=-
    unset t
    ```

    Use `printf`, not `echo`: Nomad keeps the value as it gets it, and `echo` adds a line break to
    the token.

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

6. Start a first run of each job, and read its log. The output of `periodic force` gives the
   allocation ID of the run, in the line `Allocation "<ID>" created`:

    ```bash
    nomad job periodic force javv-scan-trivy
    nomad alloc logs -stderr <allocation ID> push
    nomad job periodic force javv-scan-grype
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

- Exit code `1`: one of these causes:
    - JAVV or the Nomad API did not reply.
    - A scan failed, or a scanner gave no repository digest.
    - JAVV refused a push or the end of the cycle.
- Exit code `2`: a setting is not valid. The log tells the correct values.
- Nomad does not start a failed run again. The next run of the schedule tries again.
- If no image scanned, the cycle stays `partial`. JAVV keeps the images of the last good cycle.
- If some images scanned, the cycle is `committed` with only those images. The run exits with
  code `1`, and the log has an `ERROR` line for each image that is not in the cycle.

## Known gaps

- Tested only with Nomad 2.1.1, with one agent in dev mode.
- The jobs scan tasks of the Docker driver only. They do not scan tasks of other drivers.
- The jobs do not scan an image that Nomad sets when the task starts, for example
  `${meta.connect.sidecar_image}` of a Consul Connect sidecar. The log shows these images as a
  warning.
- The scanner gets the image by its tag at the time of the scan. If the tag moved after the task
  started, JAVV shows the new image. Use images by digest (`image@sha256:…`) to prevent this.
- A batch job that does not run at the time of the scan is not in the scan.
- When an image stops, its findings stay open until the staleness sweep marks them stale (3 days by
  default).
- The job reads the Nomad API at `http://127.0.0.1:4646`, on the network of the host. A Nomad
  API with TLS is not tested.
- A private registry needs its credentials in the job, in the variables of Trivy or Grype. This
  is not tested.
- A mirror of the scanner databases (`TRIVY_DB_REPOSITORY`, `GRYPE_DB_UPDATE_URL`) is not tested.
- Each cache volume is on one client. Nomad runs the job only on the client with its volume.
- The owner of a job can add the meta `javv_scan = "true"` to the job. Then the scan jobs skip it.
  The log names it.
- The web app uses words of Kubernetes, for example **Namespace** and "pods".
