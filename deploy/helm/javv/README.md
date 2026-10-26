# javv

![Version: 0.8.9](https://img.shields.io/badge/Version-0.8.9-informational?style=flat-square) ![AppVersion: 0.8.9](https://img.shields.io/badge/AppVersion-0.8.9-informational?style=flat-square)

This chart installs the backend and the frontend of JAVV on Kubernetes.

- It uses the settings and defaults of the JAVV [compose file](../../compose/compose.yaml).
- It runs one backend, which also runs the background jobs.
- It runs a frontend Service that browsers and scanners both use.
- It makes Services only. For https, put your own Ingress, gateway or load balancer in front of
  the frontend Service.

Other charts:

- OpenSearch comes from the [`javv-opensearch`](../javv-opensearch/README.md) chart.
- The scanners come from the [`javv-scanner`](../javv-scanner/README.md) chart, in each cluster
  that you scan.

[Deploying](../../../docs/DEPLOYING.md#install-on-kubernetes-with-helm) gives the full procedure.

## Install

### Prerequisites

- A Kubernetes cluster, and `kubectl` and Helm that can connect to it.
- bash and `openssl`. The commands read each secret at a prompt, or make it in place. Thus no
  secret goes into your shell history or into the arguments of a process.
- One namespace for this chart and the [`javv-opensearch`](../javv-opensearch/README.md) chart.

### Steps

1. Install OpenSearch, with the password of `admin` and the password of `javv` in Secrets:
    ```bash
    VERSION=0.8.9
    read -rs -p 'OpenSearch admin password: ' pw && echo
    printf '%s' "$pw" | kubectl create secret generic javv-opensearch-admin --from-file=password=/dev/stdin
    unset pw
    kubectl create secret generic javv-opensearch-backend \
      --from-file=password=<(openssl rand -hex 24 | tr -d '\n')
    helm install store oci://ghcr.io/danube-labs/charts/javv-opensearch --version "$VERSION" \
      --set opensearch.javv.auth.existingSecret=javv-opensearch-admin \
      --set opensearch.javv.backend.existingSecret=javv-opensearch-backend
    ```
2. Make the two JAVV secrets:
    ```bash
    read -rs -p 'First JAVV admin password (12 characters or more): ' pw && echo
    kubectl create secret generic javv-secrets \
      --from-file=secret-key=<(openssl rand -hex 32 | tr -d '\n') \
      --from-file=bootstrap-admin-password=<(printf '%s' "$pw")
    unset pw
    ```
3. Install JAVV. The backend signs in to OpenSearch as `javv`, with the Secret of `javv`:
    ```bash
    VERSION=0.8.9
    helm install javv oci://ghcr.io/danube-labs/charts/javv --version "$VERSION" \
      --set secrets.existingSecret=javv-secrets \
      --set opensearch.passwordSecret.name=javv-opensearch-backend
    helm test javv
    ```
    If OpenSearch has its own certificate, from a Secret or from cert-manager, also add
    `--set opensearch.caSecret.name=<the Secret with its ca.crt>`. The backend then verifies the
    certificate of OpenSearch.

### Where the chart comes from

- Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, and signs it
  ([Verify the images and charts](../../../docs/DEPLOYING.md#verify-the-images-and-charts)).
- From a checkout, use the folder of the chart in `deploy/helm/`.

## What the chart runs

- **The backend:** one replica with `strategy: Recreate`, because a rolling update would run two
  backends for a short time. It has a ClusterIP Service on port 8000, and three probes. The
  startup probe gives 300 s to the first start, because the backend creates the indices before it
  opens its port.
- **The frontend:** `frontend.replicas` pods, and the Service that browsers and scanners use, on
  port 8080. The frontend sends `/api`, `/auth` and `/readyz` to the backend. It replies 502 when
  the backend does not reply.
- Both run as the user of their images, `65532`, with a read-only root file system and an
  `emptyDir` on `/tmp`.

## Settings

- Each backend setting is under `backend.config`, at its default, by the name that the backend
  reads. Each one has the comment that the compose file gives it.
  [Configuring JAVV](../../../docs/CONFIGURATION.md#backend-settings) describes each setting.
- The secrets are not settings here. The secret key and the bootstrap password come from
  `secrets`. The password and the CA of OpenSearch come from `opensearch`.
- `values.schema.json` makes the install fail for a key with a wrong name. This does not apply in
  `backend.config` and `frontend.config`, which accept each name. Thus the chart passes a setting
  with a wrong name to the backend, and the backend ignores it.
- `backend/tests/test_compose_settings.py` keeps the settings of this chart equal to the code.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend.config | object | every setting at its code default. values.yaml has the list. | Each backend setting, at its default, by the name that the backend reads (docs/CONFIGURATION.md, "Backend settings"). Set one with `--set backend.config.TZ=Europe/Bucharest`, or in your values file. The secrets are not here: see `secrets` and `opensearch`. |
| backend.extraEnv | list | `[]` | More environment variables, in the form of Kubernetes (`name`, `value` or `valueFrom`). |
| backend.image.tag | string | `"0.8.9"` | The release of this chart. release-please changes it. |
| backend.livenessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/healthz","port":"http"},"periodSeconds":20}` | Restarts a backend that does not reply. /healthz does not need OpenSearch. Thus when OpenSearch stops, the app works with less, and Kubernetes does not restart it. |
| backend.readinessProbe | object | `{"failureThreshold":3,"httpGet":{"path":"/readyz","port":"http"},"periodSeconds":10}` | While OpenSearch is unreachable, /readyz replies 503, and the Service sends no requests to the backend. |
| backend.startupProbe | object | `{"failureThreshold":30,"httpGet":{"path":"/healthz","port":"http"},"periodSeconds":10}` | Stops the liveness probe while the backend starts. The backend verifies that OpenSearch replies, and creates or updates the indices before it opens its port. 30 tries, 10 s apart: ten JAVV_REQUEST_TIMEOUT periods. |
| frontend.config | object | `{"JAVV_BACKEND_CONNECT_TIMEOUT":"5","JAVV_BACKEND_URL":"","JAVV_LOG_LEVEL":"info"}` | The settings of the frontend server (docs/CONFIGURATION.md, "Frontend server settings"). |
| frontend.image.tag | string | `"0.8.9"` | The release of this chart. release-please changes it. |
| frontend.readinessProbe | object | `{"httpGet":{"path":"/","port":"http"},"periodSeconds":10}` | The frontend serves the app without the backend. Thus it stays ready while the backend is down. It then replies 502 for /api, /auth and /readyz, and the app shows "backend down". |
| frontend.replicas | int | `1` | The frontend holds no state. Thus you can run more than one. |
| frontend.service | object | `{"port":8080,"type":"ClusterIP"}` | Browsers and scanners both use this Service. The scanners push to /api/v1/ingest/scan through it. You need nothing in front of it. Your own Ingress or gateway can point at it. |
| opensearch.caSecret | object | `{"key":"ca.crt","name":""}` | A Secret with the CA of the OpenSearch certificate. For javv-opensearch with cert-manager, it is `<its release>-javv-opensearch-tls`. When you set it, the chart mounts it, sets JAVV_OPENSEARCH_CA_BUNDLE to it and sets JAVV_OPENSEARCH_VERIFY_CERTS to true. When it is empty, the backend does not verify the demo certificates. |
| opensearch.passwordSecret | object | `{"key":"password","name":""}` | The Secret with the password of javv, the OpenSearch user that JAVV signs in as. Use the Secret of the javv-opensearch chart: `opensearch.javv.backend.existingSecret` there, or `<its release>-javv-opensearch-backend`. Never use the admin Secret: the backend needs only javv. |
| podSecurityContext | object | `{"fsGroup":65532,"runAsGroup":65532,"runAsNonRoot":true,"runAsUser":65532,"seccompProfile":{"type":"RuntimeDefault"}}` | Both containers run as the user of their images, with a read-only root and an emptyDir on /tmp. |
| secrets.bootstrapAdminPassword | string | `""` | The password of the first JAVV admin, 12 to 256 characters. A longer password stops the backend at start. The backend uses it one time, when that admin does not exist. |
| secrets.existingSecret | string | `""` | A Secret with the keys `secret-key` and `bootstrap-admin-password`. Set this value, or the two values below. The chart never makes a secret key: a new key stops each ingest token and each session. |
| secrets.secretKey | string | `""` | The secret key of the backend (`JAVV_SECRET_KEY`). It hashes the ingest tokens and the session ids, and it signs the download links. Use a long random string (`openssl rand -hex 32`), and keep it. If you change it, each scanner gets 401, and each user must sign in again. Each scanner then needs a new token. The chart puts the key in a Secret. |
