# JAVV ingest contract

This page tells you how to push scan results into JAVV **without the JAVV scanners**. Use it from
any environment that can make the envelope JSON: Kubernetes, Nomad, Docker hosts or CI pipelines.

The page gives the schema of the envelope, the sequence of calls, and the validation rules. JAVV
accepts only two scanner names, `trivy` and `grype`. Thus you must push as one of them (see
[Limit: two scanner names](#limit-two-scanner-names)).

The machine-readable schema is
**[`ingest-envelope.schema.json`](ingest-envelope.schema.json)**. JAVV makes it from the model that
the backend uses to validate each envelope. A CI test compares the two, so the schema always agrees
with the backend.

## Push one scan cycle

A scan cycle is one full scan of all images in one cluster, by one scanner. Do these calls in this
sequence:

| Step | Call | Authentication | When |
|---|---|---|---|
| 0 | `GET/POST /api/v1/admin/tokens`: create a machine token for your `(cluster_id, scanner)` pair | An admin session with `can_manage_tokens`, or `python -m backend.core.tokens` | One time. Rotate or revoke the token with the admin API. |
| 1 | `POST /api/v1/scan-runs`. The reply is `{"scan_order": <int>}`. | The machine token | One time for each scan **cycle**, before the pushes |
| 2 | `POST /api/v1/ingest/scan`: one envelope for each image | The machine token | For each image in the cycle |
| 3 | `POST /api/v1/inventory-runs`, with the body `{"scan_run_id", "expected_count", "started_at"}` | The machine token | One time, at the **end** of the cycle |

Obey these rules:

- **Get `scan_order` from step 1. Do not make up a value.** JAVV puts the scans of each cluster and
  scanner in sequence with this number, and it uses the sequence to decide which data is current.
  Each envelope in the cycle has the same `scan_order` and the same `scan_run_id`. You choose the
  `scan_run_id`.
- **Scan all images in each cycle.** Each cycle is a full scan. JAVV marks each finding that a completed
  cycle does not report again as no longer present. Do not push only the changes.
- **Step 3 completes the cycle.** Set `expected_count` to the number of images that you found. JAVV
  counts the images that it received. It marks the inventory run `committed` only when the two
  numbers agree. Without step 3, the "running at a time" queries do not use the cycle.
- **The token is for one cluster and one scanner.** JAVV refuses with `403` each envelope whose
  `cluster_id` or `scanner` is different from the token.

## Fields

None of these fields is specific to Kubernetes.

| Field | Meaning |
|---|---|
| `cluster_id` | An environment ID that **never changes**: lowercase letters, digits and hyphens, 8–64 characters. JAVV stores the data under this ID. Do not change it. The names that JAVV shows for a cluster are in a different place. |
| `namespaces` | A `list[str]` of labels that tell where the image runs. For Kubernetes, these are namespaces. You can also use Nomad job names, compose project names or host groups. |
| `replicas` | The number of instances of the image in that group: an integer, 0 or more. |
| `image_digest` | `sha256:<hex>`. JAVV identifies each image by this digest. |
| `last_seen_at` and the other times | Each time must include a **time zone**, in ISO-8601 (`…Z` or an offset). |
| `severity` | The word that the scanner gave, **exactly as the scanner wrote it**. JAVV calculates its own severity from this word. JAVV ignores the `severity_canonical` that you send. Send it all the same, because the schema requires it. The scanner word in lowercase is correct. |
| `effective_config` | The scan settings and the scope that the cycle used. JAVV only shows and records them, but the field is **required**. The shape of `tuning` must agree with `scanner`. |

## Validation

JAVV validates the envelope with `extra="forbid"` at each level. An unknown field anywhere causes a
refusal, not a warning. JAVV refuses the envelope with `422` in these conditions:

- **The counts do not agree.** `counts.total` must be equal to the sum of the six severity counts,
  **and** to `len(findings)`. The count fields have short names (`crit`, `med`). The severity values
  are always full words.
- **`cluster_id` has a different shape** from lowercase letters, digits and hyphens, 8–64
  characters. JAVV puts the ID into index names, so it refuses all other characters.
- **`image_digest`** does not agree with `^sha256:[a-fA-F0-9]{6,64}$`.
- **`scanner` and `effective_config.tuning` do not agree**, for example a `trivy` envelope with
  Grype settings.
- **`schema_version`** is not 3 or 4. Version 4 added `ptype`. Version 3 findings have no `ptype`.
- **A time has no time zone.**
- **`scan_order` is larger than the largest one that step 1 gave** to this cluster and scanner.
  Thus a value that you make up cannot move the sequence of your scans.
- **`last_seen_at` is wrong for the backend's clock:** more than 15 minutes ahead (the
  `JAVV_INGEST_FUTURE_TOLERANCE_MINUTES` setting), or older than the staleness period of the cluster
  (3 days by default, set in **Settings**). Keep the clocks of your scan hosts correct.

[`API.md`](API.md#ingest-a-scan) has the full list of errors for
`POST /ingest/scan`: 400, 401, 403, 413, 422, 429 and 503, gzip and the size limits. On success,
JAVV replies `202` with `{accepted, findings, commit}`. JAVV makes the same document IDs from the
same data. Thus you can send a failed cycle again with no risk, while its `last_seen_at` is newer
than the staleness period of the cluster. After that, scan again.

## Example

This example is a complete envelope with one finding. The example is a real finding, and a test
validates it. For a larger example with 29 findings, see
`backend/tests/fixtures/envelope-trivy-v3-golden.json` in the repository.

```bash
TOKEN=…            # from step 0, scoped to (my-nomad-fleet-01, trivy)
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

# cycle end: certify the inventory (expected_count = images you discovered this cycle)
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  https://javv.example/api/v1/inventory-runs \
  -d "{\"scan_run_id\": \"cycle-2026-07-10-a\", \"expected_count\": 1, \"started_at\": \"2026-07-10T11:55:00Z\"}"
```

## Limit: two scanner names

`scanner` is `"trivy"` or `"grype"`. Thus **a different tool must make output that agrees with Trivy
or with Grype, and push as that scanner.** Create the token for that scanner, and use the settings
shape of that scanner.

JAVV keeps the results of each scanner apart, and it never merges them. Thus each scanner name
changes many parts of JAVV: the severity calculation, the comparison between scanners, and the
tokens. A list of registered scanners will permit more names
([issue 327](https://github.com/Danube-Labs/javv-poc/issues/327)). That change also adds a general
settings shape.

Until then, if you use a different tool (for example Snyk or Clair), convert its output to one of
the two scanners, and keep your conversion the same each time.

## Related pages

- [`API.md`](API.md): all the endpoints, with authentication, errors and metrics.
