# Scan a Docker Compose host

Two containers scan the images of the running containers of a Docker host and push the results to
JAVV. `trivy` uses Trivy. `grype` uses Grype. JAVV then shows the Docker host as it shows a
Kubernetes cluster.

The Compose file is an example. Change it for your host: for example, the schedule, the source of
the tokens or the cache volumes. The script `javv_docker_push.py` does the work. It reads the
running containers from the Docker API, scans their images and pushes the results to JAVV.

**Tested with:** JAVV 0.9.8, Docker 29.9.3 with the containerd image store, Docker Compose 5.7.0,
and the images `javv-scanner-trivy:0.76.2` and `javv-scanner-grype:0.121.1`.

## How the containers work

- Each container runs one scan cycle when it starts, then one cycle every 6 hours.
- The container reads the running containers from the Docker socket.
- It scans the image of each container from the Docker daemon, by its image ID. Thus it scans the
  image that the container runs, also an image that you built on the host.
- It gets the digest of each image from the output of the scanner.
- It pushes one scan cycle to JAVV, as [Push from your own script](../../docs/INGEST-CONTRACT.md)
  tells.
- It does not scan a container with the label `javv.scan=true`. The two scan containers have this
  label. The log names each container that the scan skips for this reason.

JAVV shows each Compose project as a namespace:

| Container | Namespace in JAVV |
|---|---|
| A container of the Compose project `shop`, for example `shop-web-1` | `shop` |
| A container with no Compose project, for example from `docker run --name lonely` | `lonely` |

## Before you start

- The scan containers need the Docker socket `/var/run/docker.sock`. Access to the socket is the
  same as root access on the host.
- The host must reach JAVV and the download sites of the scanner databases.
- The cache volumes of the scanners need about 7 GB of disk. On 2026-11-08, the Trivy cache used
  3.3 GB and the Grype cache used 3.4 GB.
- You need the files of the folder [`deploy/docker`](https://github.com/Danube-Labs/javv/tree/main/deploy/docker):
  [`compose.yaml`](https://github.com/Danube-Labs/javv/blob/main/deploy/docker/compose.yaml),
  [`.env.example`](https://github.com/Danube-Labs/javv/blob/main/deploy/docker/.env.example) and
  [`javv_docker_push.py`](https://github.com/Danube-Labs/javv/blob/main/deploy/docker/javv_docker_push.py).

## Install the containers

Run the commands in the folder that holds the files.

1. In JAVV, make two tokens for the host: one for `trivy`, one for `grype`. See
   [Before you start](../../docs/INGEST-CONTRACT.md#before-you-start) of the push page.
2. Make the file `.env` from `.env.example`. Only you can read the file:

    ```bash
    cp .env.example .env
    chmod 600 .env
    stat -c %g /var/run/docker.sock    # the value of DOCKER_GID
    ```

3. In `.env`, set the address of JAVV, the ID of the host in JAVV, the two tokens and `DOCKER_GID`.
4. Start the containers, and read the log of the first cycle:

    ```bash
    docker compose up -d
    docker compose logs -f trivy
    ```

5. In JAVV, select the cluster and open **Running images**.

## Settings

- To change a setting, add it to the `environment` of the service in `compose.yaml`. Then run
  `docker compose up -d` again.
- To change the schedule, change `sleep 21600` (6 hours) in `compose.yaml`.
- To see what a cycle scans without a push, set `JAVV_DRY_RUN` to `true`.

| Setting | Default | What it does |
|---|---|---|
| `JAVV_DOCKER_SKIP_PROJECTS` | Empty | The namespaces in JAVV to skip: Compose projects, or names of containers with no project. Separate them with commas. A `*` is a pattern. Example: `test-*,legacy`. |
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | The Docker socket. The script and the scanners read it. |
| `JAVV_DRY_RUN` | `false` | `true`: the cycle writes the images to its log, and pushes nothing. |

The containers also use these settings of the JAVV scanners, with the same names and defaults:

- [Trivy settings](../../docs/CONFIGURATION.md#trivy-settings), for example `JAVV_TRIVY_SEVERITIES`.
- [Grype settings](../../docs/CONFIGURATION.md#grype-settings), for example `JAVV_GRYPE_ONLY_FIXED`.
- `JAVV_PUSH_RETRY_BUDGET_SECONDS` (`360`) and `JAVV_LOG_LEVEL` (`info`).

## Skip containers from JAVV

The containers obey the scan scope of the cluster in JAVV (**Settings › Scan scope**):

| Field in JAVV | For Docker |
|---|---|
| Included namespaces, ignored namespaces | The namespace in JAVV of a container, for example `shop` or `test-*` |
| Excluded image patterns | The image of a container, for example `redis:*` |
| Skip workload kinds | Not used: a Docker container has no kind |

If JAVV does not send the scope, the container does not scan in this cycle.

## When a cycle fails

- The log of the cycle has an `ERROR` line for each of these causes:
    - JAVV or the Docker API did not reply. If the Docker API refuses access, check `DOCKER_GID`.
    - A scan failed, or a scanner gave no repository digest.
    - JAVV refused a push or the end of the cycle.
- A container can run an image that has no name now: a newer image has its tag. The scanners give
  no repository digest for this image. Start the container again with the newer image, for example
  with `docker compose up -d` in its project.
- If a setting is not valid, the log tells the correct values.
- The next cycle starts 6 hours later.
- If no image scanned, the cycle stays `partial`. JAVV keeps the images of the last good cycle.
- If some images scanned, the cycle is `committed` with only those images. The log has an `ERROR`
  line for each image that is not in the cycle.

## Known gaps

- Tested only with Docker 29.9.3 and the containerd image store, on one host.
- The classic image store (`overlay2` with no containerd) is not tested. There, an image built on
  the host has no repository digest, and the cycle does not scan it.
- Rootless Docker, Podman, Docker Swarm services and a Docker API on TCP are not tested. The script
  refuses a `DOCKER_HOST` that is not a socket.
- A read-only mount of the socket does not limit the Docker API. The scan containers can do all
  that root can do on the host.
- On a host that Nomad or k3d also uses, their containers have no Compose project. JAVV shows each
  one under its container name, for example `nginx-03d996fa-595c-aca0-dfbb-2d52b9ad0a24`. Skip
  them with `JAVV_DOCKER_SKIP_PROJECTS`, and scan a Nomad cluster with its own jobs.
- A container that runs only between two cycles is not in the scan.
- When an image stops, its findings stay open until the staleness sweep marks them stale (3 days by
  default).
- The scanners read the images from the Docker daemon, not from a registry. An image from a
  private registry is not tested.
- A mirror of the scanner databases (`TRIVY_DB_REPOSITORY`, `GRYPE_DB_UPDATE_URL`) is not tested.
- The owner of a container can add the label `javv.scan=true`. Then the scan containers skip it.
  The log names it.
- The web app uses words of Kubernetes, for example **Namespace** and "pods".
