# javv-scanner

![Version: 0.8.9](https://img.shields.io/badge/Version-0.8.9-informational?style=flat-square) ![AppVersion: 0.8.9](https://img.shields.io/badge/AppVersion-0.8.9-informational?style=flat-square)

This chart installs the JAVV scanners in one cluster that you scan: a Trivy CronJob and a Grype
CronJob.

- Each scanner pushes its own results to JAVV. JAVV never merges them.
- Install the chart in each cluster that you scan.
- JAVV itself, the [`javv`](../javv/README.md) chart, can run in that cluster or at each place
  that the scanners can reach over HTTP.
[Connect the scanners](../../../docs/DEPLOYING.md#connect-the-scanners) gives the full procedure.

## Install

### Prerequisites

- A running JAVV, and an address of JAVV that this cluster can connect to.
- An admin sign-in to JAVV.
- `kubectl` and Helm that can connect to this cluster, and bash.

### Steps

1. Find the id of this cluster:
    ```bash
    kubectl get namespace kube-system -o jsonpath='{.metadata.uid}'
    ```
2. Make one ingest token for each scanner, in JAVV: **Settings › Access & tokens › Mint token**.
    - For the first token, select **New cluster…** and enter the cluster id.
    - Select the name of the scanner.
3. Put each token in its own Secret, and install the chart:
    ```bash
    VERSION=0.8.9
    kubectl create namespace javv-scanner
    # asks for each token, so it is not in your shell history or the process list
    for s in trivy grype; do
      read -rs -p "$s token: " token && echo
      printf '%s' "$token" | kubectl -n javv-scanner create secret generic "javv-$s-token" \
        --from-file=token=/dev/stdin
    done; unset token
    helm install scanner oci://ghcr.io/danube-labs/charts/javv-scanner --version "$VERSION" \
      -n javv-scanner \
      --set backendUrl=http://<JAVV's address>:8080 \
      --set trivy.token.existingSecret=javv-trivy-token \
      --set grype.token.existingSecret=javv-grype-token
    helm test scanner -n javv-scanner
    ```
    `helm test` verifies that JAVV replies at `backendUrl` and accepts each token. It does not
    scan.

Each scanner then runs on its `schedule`. To start a cycle now, follow the safe sequence in
`NOTES`:

1. Pause the CronJob.
2. Wait until no Job of that scanner runs.
3. Make a Job from the CronJob.
4. Start the CronJob again.

### Where the chart comes from

- Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, and signs it
  ([Verify the images and charts](../../../docs/DEPLOYING.md#verify-the-images-and-charts)).
- From a checkout, use the folder of the chart in `deploy/helm/`.

## What the chart runs

- **One CronJob for each scanner,** with `concurrencyPolicy: Forbid`. The CronJob never starts a
  cycle while one of its own cycles runs. It does not count a Job that you make by hand, so use
  the sequence in `NOTES`. Kubernetes stops a cycle after `activeDeadlineSeconds`. The stopped
  cycle does not run again before the next schedule.
- **A cache of the vulnerability database for each scanner:** a `ReadWriteOnce`
  PersistentVolumeClaim at `/var/cache/javv`. Each run first refreshes the database there with the
  binary of the scanner, from the source of the vendor or from the source in `vulnDb`. Then it
  scans with updates off. Thus each image in a cycle gets the same database, and the scan does not
  connect to the vendor. Trivy uses the misconfiguration rules in its binary.
    - If the refresh fails, the run uses the database in the cache.
    - If the scanner cannot read the database, the refresh deletes it and downloads it one more
      time.
    - With no database that it can read, the run fails, and its log tells you why.
    - The refresh also verifies the Java database of Trivy. A damaged Java database fails no scan:
      Trivy only skips the jars that it cannot name.
    - Grype refuses a database older than 5 days.
- **Mirrors:** `trivy.vulnDb.repository` and `trivy.vulnDb.javaRepository` take OCI repositories.
  `grype.vulnDb.updateUrl` takes the address of a list of database builds. Put each other setting
  that the vendors read in `extraEnv`, for example `GRYPE_DB_CA_CERT` or the registry login for a
  private mirror.
- **Kubernetes access:** one ClusterRole. It can `list` pods, to find the running images. It can
  `get` the `kube-system` namespace, because its UID is the id of the cluster. It cannot read
  Secrets.
- **Private registries:** `<scanner>.registryAuth.existingSecret` names a
  `kubernetes.io/dockerconfigjson` Secret. Kubernetes puts its `.dockerconfigjson` key into the scan
  container as `/etc/javv/registry/config.json`, and `DOCKER_CONFIG` points the scanner at it. The
  refresh does not get the login. With no login, the scanner pulls each image with no sign-in, and
  it skips an image that it cannot pull.
- Both scanners run as the user of their images, `65532`, with a read-only root file system. They
  have the cache volume, an `emptyDir` on `/var/lib/javv` for the dead-letter file, and an
  `emptyDir` on `/tmp`.

## Images

- `image.tag` is the scanner version from `versions.yaml` in the repository. JAVV publishes that
  tag again when it changes the scanner image. Thus the default `pullPolicy` is `Always`.
- To run one exact build, set `image.digest`.
- **The chart of a release sets the digest.** For each scanner, it is the digest that the tag named
  when JAVV made the release, after cosign verified the signature of `scanner-images.yml`.
- A checkout of the repository has the tag only.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backendUrl | string | `""` | The address of JAVV, as the scanners reach it: the frontend Service of the javv chart, or what you put in front of it. Examples: `http://javv.javv.svc:8080` in the same cluster, and `https://javv.example.com` from a different cluster. You must set it. |
| clusterId | string | `""` | The id of this cluster in JAVV. When it is empty, the scanners read the UID of the `kube-system` namespace. When you set it, the scanners verify it: a cycle that reaches a different cluster stops, and does not scan. |
| grype.activeDeadlineSeconds | int | `19800` | Kubernetes stops a cycle that runs for longer than this number of seconds. |
| grype.config | object | every setting at its code default. values.yaml has the list. | The scan settings of Grype (docs/CONFIGURATION.md, "Grype settings"), at their defaults. An empty value means not set. |
| grype.enabled | bool | `true` | Run the Grype CronJob. |
| grype.extraEnv | list | `[]` | More environment variables for the refresh and the scan, in the form of Kubernetes. |
| grype.image.digest | string | `""` | `sha256:...`: run exactly that image. It replaces `tag`. It is empty in the repository. The chart of a release sets it to the digest that the tag named at the release. |
| grype.image.tag | string | `"0.120.1"` | The Grype version, from versions.yaml (`scanners.grype.current`). JAVV publishes the tag again when it changes the image for that version. Thus each run pulls the image. |
| grype.registryAuth | object | `{"existingSecret":""}` | A registry login for the images from private registries, as for Trivy. It can be the same Secret. |
| grype.schedule | string | `"30 */6 * * *"` | When a cycle starts, in the time zone of the CronJob. |
| grype.timeZone | string | `""` | The time zone of `schedule`. When it is empty, the zone of the cluster applies, which is UTC on most clusters. |
| grype.token | object | `{"existingSecret":"","key":"token","value":""}` | The ingest token that JAVV made for this cluster and Grype. Give a Secret that holds it under `key`. Or give `value`, and the chart puts it in a Secret. |
| grype.vulnDb.existingClaim | string | `""` | Your own PersistentVolumeClaim. The chart then makes no claim. |
| grype.vulnDb.size | string | `"10Gi"` | The cache volume. In October 2026, the Grype database used 3.0 GB. This size gives it space to grow. |
| grype.vulnDb.storageClass | string | `""` | When it is empty, the default StorageClass of the cluster applies. |
| grype.vulnDb.updateUrl | string | `""` | The source of the vulnerability database (`GRYPE_DB_UPDATE_URL`, the list of database builds). When it is empty, Grype uses `https://grype.anchore.io/databases`. |
| podSecurityContext | object | `{"fsGroup":65532,"runAsGroup":65532,"runAsNonRoot":true,"runAsUser":65532,"seccompProfile":{"type":"RuntimeDefault"}}` | Both scanners run as the user of their images, with a read-only root. They write only to the database cache, the dead-letter file and /tmp. |
| trivy.activeDeadlineSeconds | int | `19800` | Kubernetes stops a cycle that runs for longer than this number of seconds. Only one cycle runs at a time, so a cycle that does not end would stop each later cycle. |
| trivy.config | object | every setting at its code default. values.yaml has the list. | The scan settings of Trivy (docs/CONFIGURATION.md, "Trivy settings"), at their defaults. An empty value means not set. |
| trivy.enabled | bool | `true` | Run the Trivy CronJob. |
| trivy.extraEnv | list | `[]` | More environment variables for the refresh and the scan, in the form of Kubernetes. |
| trivy.image.digest | string | `""` | `sha256:...`: run exactly that image. It replaces `tag`. It is empty in the repository. The chart of a release sets it to the digest that the tag named at the release. |
| trivy.image.tag | string | `"0.76.1"` | The Trivy version, from versions.yaml (`scanners.trivy.current`). JAVV publishes the tag again when it changes the image for that version. Thus each run pulls the image. |
| trivy.registryAuth | object | `{"existingSecret":""}` | A registry login for the images from private registries: the name of a `kubernetes.io/dockerconfigjson` Secret in the namespace of the chart. The scan container mounts it, and `DOCKER_CONFIG` tells Trivy where it is. When it is empty, Trivy pulls each image with no login. |
| trivy.schedule | string | `"0 */6 * * *"` | When a cycle starts, in the time zone of the CronJob. A cycle each 6 hours keeps each finding well inside the 3-day staleness window of JAVV. Grype runs half an hour later, so the two downloads do not occur at the same time. |
| trivy.timeZone | string | `""` | The time zone of `schedule`, for example `Europe/Bucharest`. When it is empty, the zone of the cluster applies, which is UTC on most clusters. |
| trivy.token | object | `{"existingSecret":"","key":"token","value":""}` | The ingest token that JAVV made for this cluster and Trivy (Settings › Access & tokens). Give a Secret that holds it under `key`. Or give `value`, and the chart puts it in a Secret. |
| trivy.vulnDb.existingClaim | string | `""` | Your own PersistentVolumeClaim. The chart then makes no claim. |
| trivy.vulnDb.javaRepository | string | `""` | The source of the Java index database (`--java-db-repository`). When it is empty, Trivy uses `mirror.gcr.io/aquasec/trivy-java-db:1`, then `ghcr.io/aquasecurity/trivy-java-db:1`. |
| trivy.vulnDb.repository | string | `""` | The source of the vulnerability database (`--db-repository`, OCI repositories in sequence). When it is empty, Trivy uses `mirror.gcr.io/aquasec/trivy-db:2`, then `ghcr.io/aquasecurity/trivy-db:2`. |
| trivy.vulnDb.size | string | `"10Gi"` | The cache volume. In October 2026, the two Trivy databases used 2.9 GB. This size gives them space to grow. |
| trivy.vulnDb.storageClass | string | `""` | When it is empty, the default StorageClass of the cluster applies. |
