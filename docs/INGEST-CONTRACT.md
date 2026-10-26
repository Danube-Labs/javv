# Push from your own script

This page tells you how to push scan results into JAVV from your own script, without the JAVV
scanners. Use it from each environment that can make JSON and send HTTP requests: Kubernetes,
Nomad, Docker hosts or CI pipelines.

The page gives the sequence of calls, the rules for the script, and a reference for each field.

- The machine-readable schema is **[`ingest-envelope.schema.json`](ingest-envelope.schema.json)**.
- JAVV makes the schema from the model that the backend uses to validate each push.
- A CI test compares the two, and a second CI test compares the field tables on this page with the
  model. Thus the schema and this page always agree with the backend.

!!! tip "For AI agents"
    This page and the schema file are sufficient to make a script that pushes to JAVV. Read all of
    this page before you write code. Obey each rule in [Rules for the script](#rules-for-the-script).
    Use the field tables for the names, the levels and the limits. Use
    [Where the values come from](#where-the-values-come-from) to read the output of Trivy or Grype.
    Use the [example](#example) as the template.

## Before you start

1. **Get a token.** Each token is for one cluster and one scanner. In the web app, go to
   **Settings › Access & tokens**. For a new environment, select **New cluster…** and type the
   `cluster_id`. Select the scanner, and then make the token. JAVV shows the token one time only.
   To use the API, send `POST /api/v1/admin/tokens` with `{"cluster_id", "scanner", "expiry"}` as
   a user with `can_manage_tokens`. When you make the token for a new `cluster_id`, JAVV adds the cluster.
2. **Choose the `cluster_id`.** It is the ID of your environment in JAVV, and it **never changes**.
   It has lowercase letters, digits and hyphens, 8 to 64 characters, and not a hyphen first. JAVV
   stores the data under this ID. The name that the web app shows is a different value, and you can
   change it in the web app.
3. **Choose the scanner name.** It is `trivy` or `grype`. If your script runs Trivy or Grype, use
   that name. If you use a different tool, see [Limit: two scanner names](#limit-two-scanner-names).
4. **Keep the clocks correct.** JAVV refuses a scan time more than 15 minutes ahead of its own
   clock, or older than the staleness period of the cluster. The staleness period is 3 days by
   default.

## Push one scan cycle

A scan cycle is one full scan of all the images in one environment, by one scanner. Each request
sends the token in the header `Authorization: Bearer <token>`. Do these steps in this sequence:

1. **Start the cycle.** Send `POST /api/v1/scan-runs` with no body. The reply is
   `{"scan_order": <int>}`. Keep this number for the cycle.
2. **Choose a `scan_run_id`** for the cycle. It is a text of 1 to 128 characters, for example a
   UUID. Use a new value for each cycle.
3. **Push one envelope for each image.** Send `POST /api/v1/ingest/scan` with the envelope as JSON.
   Each envelope in the cycle has the same `scan_order`, `scan_run_id` and `last_seen_at`. On
   success, JAVV replies `202` with `{"accepted", "findings", "commit"}`.
4. **Complete the cycle.** Send `POST /api/v1/inventory-runs` with
   `{"scan_run_id", "expected_count", "started_at"}`. JAVV counts the images that it received. It
   marks the cycle `committed` only when its count is equal to `expected_count`.

Optional: send `GET /api/v1/scan-scope` with the token before step 3. The reply is the scan scope
that an operator set in JAVV for this cluster: the namespaces, the images and the kinds to scan or
to skip. Your script can obey it.

## Rules for the script

Obey these rules. A push that does not obey a rule either gets an error or gives wrong data in
JAVV.

- **Get `scan_order` from step 1. Do not make up a value.** JAVV puts the scans of each cluster
  and scanner in sequence with this number. It uses the sequence to decide which data is current.
- **Scan all the images in each cycle.** Each cycle is a full scan. When a new scan of an image
  does not report a finding again, JAVV marks the finding as no longer present. Do not push only
  the changes.
- **Push one envelope for each image digest.** An image can run in many places. Put all the places
  in `namespaces` of one envelope, and the total number of instances in `replicas`.
- **Push an envelope also for an image with no findings.** Send `findings: []` and set each count
  to 0. This push tells JAVV that the image is clean.
- **Send each finding one time.** JAVV identifies a finding by the cluster, the image digest, the
  scanner, `vuln_id`, `package_name` and `package_version`. If an envelope has two entries with
  the same values, JAVV keeps one finding only, but the counts of the envelope include the two.
  Thus the counts of the image do not agree with its findings.
- **Send the severity word that the scanner wrote, with no change.** JAVV calculates its own
  severity from this word.
- **Make the counts agree.** `counts.total` is equal to the number of findings, and to the sum of
  the six severity counts.
- **Send all the required fields.** Do not send a field that is not on this page. JAVV refuses an
  unknown field at each level.
- **Put a time zone in each time.** Use ISO 8601 with `Z` or an offset, for example
  `2026-07-10T12:00:00Z`.
- **Complete each cycle with step 4.** Set `expected_count` to the number of images that you
  scanned and pushed in the cycle. Without step 4, JAVV does not use the cycle when it shows the
  images that run at a given time.
- **Push at least one time in each staleness period.** When a cluster sends no push for this
  period, JAVV marks its findings as stale.
- **Send again only after a temporary error.** After `429` or `503`, or when JAVV does not reply,
  wait and send the same envelope again. Increase the wait each time. After `400`, `401`, `403`,
  `413` or `422`, do not send again: correct the cause. To send the same envelope again is safe.
  JAVV makes the same IDs from the same data, so it keeps one copy.
- **Keep each push in the size limits.** The limit is 10 MiB as it arrives (still compressed) and
  60 MiB after decompression, by default. To send a large envelope, compress it and send the
  header `Content-Encoding: gzip`. The limit is 100,000 findings for each envelope.
- **Keep the token secret.** Do not write the token in a log or in the envelope.

## Field reference

The column **Level** tells if you must send the field. If a **required** field is not in the
envelope, JAVV refuses the push. If you do not send an **optional** field, JAVV uses its default.
The column **Type** uses JSON types. "or null" means that `null` is a correct value.

### Envelope

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `schema_version` | required | integer | `3` or `4` | The version of the envelope. Send `4`. Version 3 has no `ptype` in the findings. |
| `cluster_id` | required | string | Lowercase letters, digits and hyphens, 8 to 64 characters, not a hyphen first | The ID of your environment. Example: `my-nomad-fleet-01`. It must be the cluster of the token. |
| `scanner` | required | string | `trivy` or `grype` | The scanner that made the findings. It must be the scanner of the token. |
| `image_digest` | required | string | `sha256:` and 6 to 64 hexadecimal digits | The digest of the image. JAVV identifies each image by this value. |
| `image_ref` | required | string | 512 characters at most | The name of the image that JAVV shows. Example: `python:3.9.16-slim`. |
| `namespaces` | required | array of strings | 1,024 items at most | The places where the image runs. For Kubernetes, these are namespaces. You can also use Nomad job names, compose project names or host groups. Example: `["billing-job"]`. |
| `replicas` | required | integer | 0 or more | The number of instances of the image that run. |
| `scan_run_id` | required | string | 1 to 128 characters | The ID of the cycle. It is the same in each envelope of the cycle. |
| `scan_order` | required | integer | 0 or more. Not larger than the last value from `POST /api/v1/scan-runs`. | The number from step 1. It is the same in each envelope of the cycle. |
| `last_seen_at` | required | string | A date and time with a time zone | The time of the scan. The JAVV scanners send the start time of the cycle. |
| `scanner_version` | optional | string or null | 128 characters at most | The version of the scanner. Default: `null`. Example: `0.71.2`. |
| `scanner_db_version` | optional | string or null | 128 characters at most | The version of the vulnerability database. Default: `null`. |
| `scanner_db_built` | optional | string or null | A date and time with a time zone | The build time of the vulnerability database. Default: `null`. |
| `effective_config` | required | object | See [Scan settings](#scan-settings) | The scan settings and the scan scope of the cycle. JAVV only shows and records them. |
| `counts` | required | object | See [Counts](#counts) | The number of findings for each severity. |
| `findings` | required | array of objects | 100,000 items at most. See [Findings](#findings). | One item for each vulnerability in each package of the image. |

### Counts

Each count is an integer, 0 or more. Put a finding in the count of its severity, after JAVV
calculates the severity from the scanner word. See the column **Severity word** in
[Findings](#findings).

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `counts.crit` | required | integer | 0 or more | The findings with the severity `critical`. |
| `counts.high` | required | integer | 0 or more | The findings with the severity `high`. |
| `counts.med` | required | integer | 0 or more | The findings with the severity `medium`. |
| `counts.low` | required | integer | 0 or more | The findings with the severity `low`. |
| `counts.negligible` | required | integer | 0 or more | The findings with the severity `negligible`. |
| `counts.unknown` | required | integer | 0 or more | The findings with the severity `unknown`. |
| `counts.total` | required | integer | Equal to the number of findings, and to the sum of the six counts above | All the findings. |
| `counts.fixable` | required | integer | 0 or more | The findings with `fixable: true`. |

### Scan settings

`effective_config` holds the settings that the scanner used and the scope of the cycle. The shape
of `tuning` must agree with `scanner`. If your script does not set a value, send the default.

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `effective_config.tuning` | required | object | The Trivy shape or the Grype shape below | The settings of the scanner. |
| `effective_config.scope` | required | object | See the scope fields below | The scope of the cycle. |
| `effective_config.scope.include_namespaces` | optional | array of strings | 1,024 items at most | The namespaces that the cycle scanned. An empty list means all. Default: `[]`. |
| `effective_config.scope.ignore_namespaces` | optional | array of strings | 1,024 items at most | The namespaces that the cycle skipped. Default: `[]`. |
| `effective_config.scope.exclude_images` | optional | array of strings | 1,024 items at most | The image names that the cycle skipped. Default: `[]`. |
| `effective_config.scope.ignore_kinds` | optional | array of strings | 64 items at most | The kinds of workload that the cycle skipped. Default: `[]`. |

The Trivy shape, for `scanner: "trivy"`:

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `effective_config.tuning.scanners` | required | string | 128 characters at most | The value of `--scanners`. Example: `vuln`. |
| `effective_config.tuning.ignore_unfixed` | required | boolean | | `true` when the scan used `--ignore-unfixed`. |
| `effective_config.tuning.severities` | optional | string or null | 128 characters at most | The value of `--severity`. Default: `null`. |
| `effective_config.tuning.pkg_types` | optional | string or null | 128 characters at most | The value of `--pkg-types`. Default: `null`. |
| `effective_config.tuning.timeout` | optional | string or null | 64 characters at most | The value of `--timeout`. Default: `null`. Example: `10m`. |

The Grype shape, for `scanner: "grype"`:

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `effective_config.tuning.only_fixed` | required | boolean | | `true` when the scan used `--only-fixed`. |
| `effective_config.tuning.scope` | optional | string or null | 64 characters at most | The value of `--scope`. Default: `null`. Example: `squashed`. |
| `effective_config.tuning.scan_timeout` | required | integer | 1 or more | The time limit for the scan of one image, in seconds. Example: `600`. |

### Findings

Each item of `findings` is one vulnerability in one package of the image.

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `findings[].vuln_id` | required | string | 1 to 128 characters | The ID of the vulnerability. Example: `CVE-2024-5535`. |
| `findings[].package_name` | required | string | 1 to 512 characters | The name of the package. Example: `openssl`. |
| `findings[].package_version` | required | string | 256 characters at most | The installed version of the package. Example: `1.1.1n-0+deb11u2`. |
| `findings[].severity` | required | string | 64 characters at most | The severity word of the scanner, with no change. Example: `HIGH`. |
| `findings[].severity_canonical` | required | string | | The severity word in lowercase. JAVV ignores this value and calculates its own. Send it all the same, because the schema requires it. |
| `findings[].cvss` | optional | number or null | 0 to 10 | The CVSS base score. Default: `null`. |
| `findings[].fixable` | optional | boolean | | `true` when a later version of the package removes the vulnerability. Default: `false`. |
| `findings[].fixed_version` | optional | string or null | 256 characters at most | The first version of the package that removes the vulnerability. Default: `null`. |
| `findings[].epss` | optional | number or null | 0 to 1 | The EPSS probability. Default: `null`. |
| `findings[].kev` | optional | boolean | | `true` when the vulnerability is in the CISA list of known exploited vulnerabilities. Default: `false`. |
| `findings[].ptype` | optional | string or null | 64 characters at most. Lowercase letters, digits and `+ . _ -`, and a letter or digit first. | The type of the package: `os` for a package of the operating system, else the ecosystem. Default: `null`. Examples: `os`, `python-pkg`, `npm`. |

**Severity word.** JAVV calculates the severity from `severity` in lowercase, as follows:

| Scanner word | Severity in JAVV |
|---|---|
| `critical`, `crit` | `critical` |
| `high` | `high` |
| `medium`, `med`, `moderate` | `medium` |
| `low` | `low` |
| `negligible` | `negligible` |
| Each other word | `unknown` |

### Body of the inventory run

The body of `POST /api/v1/inventory-runs` in step 4.

| Field | Level | Type | Limits | Meaning and example |
|---|---|---|---|---|
| `inventory.scan_run_id` | required | string | 1 to 128 characters | The `scan_run_id` of the cycle. |
| `inventory.expected_count` | required | integer | 0 to 1,000,000 | The number of images that you scanned and pushed in the cycle. |
| `inventory.started_at` | required | string | A date and time with a time zone | The time when the cycle started. |

## Where the values come from

If your script runs Trivy or Grype, read the values from the JSON output as the JAVV scanners do.
The JAVV scanners run `trivy image --format json <image>` and `grype <image> -o json`.

| Field | Trivy | Grype |
|---|---|---|
| One finding | Each item of `Results[].Vulnerabilities[]` | Each item of `matches[]` |
| `vuln_id` | `VulnerabilityID` | `vulnerability.id` |
| `package_name` | `PkgName` | `artifact.name` |
| `package_version` | `InstalledVersion` | `artifact.version` |
| `severity` | `Severity`, for example `HIGH` | `vulnerability.severity`, for example `High` |
| `cvss` | The largest `V3Score` of all the sources in `CVSS`. If there is no `V3Score`, the largest `V2Score`. | The largest `metrics.baseScore` in `vulnerability.cvss[]` |
| `fixable` | `true` when `FixedVersion` is not empty | `true` when `vulnerability.fix.state` is `fixed`, or when `vulnerability.fix.versions` is not empty |
| `fixed_version` | `FixedVersion` | The first item of `vulnerability.fix.versions` |
| `epss` | Trivy does not give it. Send `null`. | `vulnerability.epss[0].epss` |
| `kev` | Trivy does not give it. Send `false`. | `true` when `vulnerability.knownExploited` is not empty |
| `ptype` | `os` when `Results[].Class` is `os-pkgs`. Else `Results[].Type` in lowercase. | `artifact.type` in lowercase |
| `scanner_version` | `Trivy.Version` | `descriptor.version` |
| `scanner_db_version` | `VulnerabilityDB.Version` from `trivy version --format json` | `descriptor.db.status.schemaVersion` |
| `scanner_db_built` | `VulnerabilityDB.UpdatedAt` from `trivy version --format json` | `descriptor.db.status.built` |

The JAVV scanners skip an entry that has no vulnerability ID or no package name.

## Errors

JAVV validates the envelope at each level, and it refuses each field that this page does not
have. JAVV refuses the envelope with `422` in these conditions:

- **The counts do not agree.** `counts.total` must be equal to the sum of the six severity counts,
  **and** to the number of findings.
- **`cluster_id` has a different shape** from lowercase letters, digits and hyphens, 8 to 64
  characters, with no hyphen first. JAVV puts the ID into index names, so it refuses all other
  characters.
- **`image_digest`** does not agree with `^sha256:[a-fA-F0-9]{6,64}$`.
- **`scanner` and `effective_config.tuning` do not agree**, for example a `trivy` envelope with
  Grype settings.
- **`schema_version`** is not 3 or 4.
- **A time has no time zone.**
- **`scan_order` is larger than the largest one that step 1 gave** to this cluster and scanner.
  The reason in the reply is `unallocated_order`.
- **`last_seen_at` is wrong for the clock of the backend:** more than 15 minutes ahead (the
  `JAVV_INGEST_FUTURE_TOLERANCE_MINUTES` setting), or older than the staleness period of the
  cluster. The reason in the reply is `clock_skew`.

| Status | Cause | Send again? |
|---|---|---|
| `202` | JAVV accepted the envelope. | No |
| `400` | The body is not valid gzip or not valid JSON. | No. Correct the body. |
| `401` | The token is missing, not valid, disabled or expired. | No. Get a new token. |
| `403` | The `cluster_id` or the `scanner` of the envelope is not the one of the token. | No. Use the correct token. |
| `413` | The body is larger than its limit. | No. Compress the body, or make it smaller. |
| `422` | The envelope is not valid. | No. Correct the envelope. |
| `429` | The token sent too many pushes in one minute. The limit is 120 by default. | Yes, after a wait. |
| `503` | OpenSearch could not keep the data, or it is not reachable. | Yes, after a wait. |

[`API.md`](API.md#ingest-a-scan) tells the sequence in which JAVV validates a push. It also tells the logs of a refused push.
The **Failed ingests** table on the **Scanner status** page shows each push that JAVV refused
after it validated the token.

## Example

This example is a complete envelope with one finding. The example is a real finding, and a test
validates the envelope on this page. For a larger example with 29 findings, see
`backend/tests/fixtures/envelope-trivy-golden.json` in the repository.

```bash
TOKEN=…            # from "Before you start": the token of my-nomad-fleet-01 for Trivy
ORDER=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  https://javv.example/api/v1/scan-runs | jq .scan_order)

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://javv.example/api/v1/ingest/scan -d @- <<EOF
{
  "schema_version": 4,
  "cluster_id": "my-nomad-fleet-01",
  "scanner": "trivy",
  "image_digest": "sha256:aa11bb22cc33dd44ee55ff667788990011223344556677889900aabbccddeeff",
  "image_ref": "python:3.9.16-slim",
  "namespaces": ["billing-job"],
  "replicas": 3,
  "scan_run_id": "cycle-2026-07-10-a",
  "scan_order": $ORDER,
  "last_seen_at": "2026-07-10T12:00:00Z",
  "scanner_version": "0.71.2",
  "scanner_db_version": "2",
  "scanner_db_built": "2026-07-10T01:09:26Z",
  "effective_config": {
    "tuning": {
      "scanners": "vuln",
      "ignore_unfixed": false,
      "severities": null,
      "pkg_types": null,
      "timeout": null
    },
    "scope": {
      "include_namespaces": [],
      "ignore_namespaces": [],
      "exclude_images": [],
      "ignore_kinds": []
    }
  },
  "counts": {
    "crit": 0, "high": 1, "med": 0, "low": 0,
    "negligible": 0, "unknown": 0, "total": 1, "fixable": 1
  },
  "findings": [
    {
      "vuln_id": "CVE-2024-5535",
      "package_name": "openssl",
      "package_version": "1.1.1n-0+deb11u2",
      "severity": "HIGH",
      "cvss": 9.1,
      "fixable": true,
      "fixed_version": "1.1.1w-0+deb11u2",
      "epss": null,
      "kev": false,
      "ptype": "deb",
      "severity_canonical": "high"
    }
  ]
}
EOF

# end of the cycle: expected_count is the number of images that you pushed
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://javv.example/api/v1/inventory-runs \
  -d "{\"scan_run_id\": \"cycle-2026-07-10-a\", \"expected_count\": 1, \"started_at\": \"2026-07-10T11:55:00Z\"}"
```

## Limit: two scanner names

`scanner` is `"trivy"` or `"grype"`. Thus **a different tool must make output that agrees with
Trivy or with Grype, and push as that scanner.** Get the token for that scanner, and use the
settings shape of that scanner.

JAVV keeps the results of each scanner apart, and it never merges them. JAVV supports only these
two scanners.

If you use a different tool (for example Snyk or Clair), convert its output to the fields of one
of the two scanners. Use the same conversion each time.

## Related pages

- [`API.md`](API.md): all the endpoints, with authentication, errors and metrics.
- [Configuring JAVV](CONFIGURATION.md#scanner-pushes): the limits of a push and their defaults.
