# javv-opensearch

![Version: 0.8.9](https://img.shields.io/badge/Version-0.8.9-informational?style=flat-square) ![AppVersion: 3.9.0](https://img.shields.io/badge/AppVersion-3.9.0-informational?style=flat-square)

This chart installs OpenSearch for JAVV: one node, with its security plugin on and two users with
a password.

- `admin`: the superuser of OpenSearch.
- `javv`: the user that the JAVV backend signs in as.

The chart wraps the official
[`opensearch` chart](https://github.com/opensearch-project/helm-charts/tree/main/charts/opensearch)
3.9.0. It sets the same values as the JAVV
[compose file](../../compose/compose.yaml).

The Service is `javv-opensearch`, https on port 9200. JAVV signs in to it as `javv`, with these
settings ([Connection to OpenSearch](../../../docs/CONFIGURATION.md#connection-to-opensearch)):

- `JAVV_OPENSEARCH_URL=https://javv-opensearch:9200`
- `JAVV_OPENSEARCH_USERNAME=javv`
- `JAVV_OPENSEARCH_PASSWORD` from the Secret of `javv`

This user has only the `javv` role: the indices of JAVV, their snapshots and the health of the
cluster ([An OpenSearch of your own](../../../docs/DEPLOYING.md#an-opensearch-of-your-own)).

## Install

### Prerequisites

- A Kubernetes cluster, and `kubectl` and Helm that can connect to it.
- bash and `openssl`. The commands read the admin password at a prompt, and make the password of
  `javv` in place. Thus neither password goes into your shell history or into the arguments of a
  process.
- An admin password that OpenSearch accepts:
    - 8 characters or more, with upper case, lower case, a digit and a special character.
    - Not a common password.

### The passwords

- Each password comes from a Secret with the key `password`, or from a value that the chart puts
  in a Secret.
- The password of `admin` comes from `opensearch.javv.auth`.
- The password of `javv` comes from `opensearch.javv.backend`. Use a long random string.

### Steps

1. Make the Secrets and install the chart:
    ```bash
    VERSION=0.8.9
    read -rs -p 'OpenSearch admin password: ' pw && echo
    printf '%s' "$pw" | kubectl create secret generic javv-opensearch-admin --from-file=password=/dev/stdin
    unset pw
    kubectl create secret generic javv-opensearch-backend \
      --from-file=password=<(openssl rand -hex 24 | tr -d '\n')
    helm install javv-opensearch oci://ghcr.io/danube-labs/charts/javv-opensearch --version "$VERSION" \
      --set opensearch.javv.auth.existingSecret=javv-opensearch-admin \
      --set opensearch.javv.backend.existingSecret=javv-opensearch-backend
    helm test javv-opensearch
    ```
2. Install the [`javv`](../javv/README.md) chart with
    `opensearch.passwordSecret.name=javv-opensearch-backend`.

### Where the chart comes from

- Each JAVV release publishes this chart at `oci://ghcr.io/danube-labs/charts`, and signs it
  ([Verify the images and charts](../../../docs/DEPLOYING.md#verify-the-images-and-charts)).
- From a checkout, use the folder of the chart in `deploy/helm/`.

### What `helm test` verifies

- OpenSearch refuses a request without a sign-in.
- `admin` and `javv` are the only users in the user list of OpenSearch.
- `javv` holds only the `javv` role, and the security API refuses it.
- OpenSearch refuses `readall`, one of the demo users that OpenSearch would otherwise add.
- With your own certificate, the certificate of the https endpoint is valid for your CA.

## Certificates

| | Set | What the node uses |
|---|---|---|
| Default | nothing | The demo certificates of OpenSearch. Their private key is in the public image. Thus each system that can connect to the Service can read the traffic. The demo admin certificate in the image (`kirk.pem`) also has full access, with no password. |
| Your own | `opensearch.javv.tls.existingSecret`: a Secret with `tls.crt`, `tls.key` (PKCS#8) and `ca.crt` | That certificate, for https and for the transport layer of the node. Thus it needs server and client usage. It must name the Service: `javv-opensearch` and `javv-opensearch.<namespace>.svc`. The demo setup stays off. |
| cert-manager | `opensearch.javv.tls.certManager.enabled=true` and `issuerRef` | A `Certificate` that the chart makes for the names of the Service, in `<release>-javv-opensearch-tls`. |

- With your own certificate, the node reads a new certificate without a restart. The chart mounts
  the Secret as a folder, and sets `plugins.security.ssl.certificates_hot_reload.enabled`.
- The chart never makes a certificate itself.

## Users and roles

- The users file of the image holds `admin` and six demo users whose passwords are their own
  names. No setting turns them off.
- An init container puts a new file in its place, with only `admin` and `javv`. It hashes each
  password from its Secret with `hash.sh` of OpenSearch, which reads the password from the
  environment.
- The `javv` role and its mapping come from the `files/` folder of the chart, as in the compose
  file. The mapping is `admin` on `all_access`, and `javv` on `javv`. These files replace the demo
  files of the image.
- OpenSearch loads these files at its first start. After that, its security index holds them.

## Change a password

A new password in the Secret alone changes nothing: OpenSearch keeps the password in its security
index.

**Prerequisites:**

- The new password.
- For your own certificates: a client certificate that the CA in your Secret signed, with its
  subject in `opensearch.javv.tls.adminDn`, and its PKCS#8 key.

**Steps:**

1. Put the new password in its Secret, or in the value of the chart and run `helm upgrade`.
2. Restart the node. The init container then writes the users file with the new password:
    `kubectl rollout restart statefulset/javv-opensearch-master`. The old password still works.
3. Load the file into the security index with `securityadmin.sh` of OpenSearch. This tool signs in
    with an admin certificate. With the demo certificates, use the certificate of the image:
    ```bash
    kubectl exec javv-opensearch-master-0 -c opensearch -- \
      plugins/opensearch-security/tools/securityadmin.sh \
      -f config/opensearch-security/internal_users.yml -t internalusers -icl -nhnv \
      -cacert config/root-ca.pem -cert config/kirk.pem -key config/kirk-key.pem
    ```
    With your own certificates, copy your client certificate and its key into the pod with
    `kubectl cp`. Run the same command with
    `-cacert config/certs/ca.crt -cert <the certificate> -key <its key>`. Then delete the two files.

    The command ends with `Done with success`. From then on, the new password works and the old
    password does not.

4. For the password of `javv`, restart the JAVV backend. It then reads the new password from the
    same Secret. The name of the Deployment comes from the name of the `javv` release:
    - Release `javv`, as in [Deploying](../../../docs/DEPLOYING.md#install-on-kubernetes-with-helm):
      `kubectl rollout restart deploy/javv-backend`.
    - A release name that holds `javv`: `<release>-backend`.
    - Each other release name: `<release>-javv-backend`.

The same `securityadmin.sh` command loads the role file and the mapping file. Use
`-f config/opensearch-security/roles.yml -t roles`, then
`-f config/opensearch-security/roles_mapping.yml -t rolesmapping`. Do this for an OpenSearch that
started without these files, or for a release that changes the role.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| opensearch.image.tag | string | `"3.9.0"` | `datastore.opensearch` in versions.yaml. `check-versions.sh` keeps it equal. The chart sets it, because the version of the official chart and its OpenSearch version can be different. |
| opensearch.javv.auth.existingSecret | string | `""` | A Secret with the admin password under the key `password`. Set this value or `password`. |
| opensearch.javv.auth.password | string | `""` | The admin password. The chart puts it in a Secret. The rules of OpenSearch: 8 characters or more, with upper case, lower case, a digit and a special character, and not a common password. |
| opensearch.javv.backend.existingSecret | string | `""` | A Secret with the password of `javv`, under the key `password`. `javv` is the user that the JAVV backend signs in as. Set this value or `password`. The javv chart reads it (`opensearch.passwordSecret`). |
| opensearch.javv.backend.password | string | `""` | The password of `javv`. The chart puts it in the Secret `<release>-javv-opensearch-backend`. Use a long random string (`openssl rand -hex 24`). |
| opensearch.javv.tls.adminDn | list | `[]` | With your own certificates: the subject DNs of the client certificates that can run securityadmin.sh of OpenSearch. A change of the admin password needs this tool. The demo setup has its own. |
| opensearch.javv.tls.certManager.enabled | bool | `false` | Get the certificate from cert-manager, in the Secret `<release>-javv-opensearch-tls`. |
| opensearch.javv.tls.certManager.issuerRef | object | `{}` | The cert-manager Issuer or ClusterIssuer: `name`, and `kind` if it is not an Issuer. |
| opensearch.javv.tls.existingSecret | string | `""` | A Secret with your certificate: `tls.crt`, `tls.key` (PKCS#8) and `ca.crt`. When it is empty and `certManager.enabled` is false, OpenSearch uses its demo certificates. Their key is public. |
| opensearch.opensearchJavaOpts | string | `"-Xms1g -Xmx1g"` | The OpenSearch heap, as in compose. |
| opensearch.persistence.enableInitChown | bool | `false` | Off. When it is on, the official chart adds an init container that changes the owner of the volume. That container runs as root, on a busybox image with no pinned version. The `fsGroup` of the pod (1000, from the official chart) already lets OpenSearch write to the volume. |
| opensearch.singleNode | bool | `true` | One node: JAVV runs one OpenSearch. With a different value, the install fails. |
