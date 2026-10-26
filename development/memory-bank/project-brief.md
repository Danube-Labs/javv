# Project brief

## What JAVV is

JAVV (Just Another Vulnerability Viewer) is a container-vulnerability triage tool for Kubernetes.
It finds the images that run in the clusters, scans them with Trivy and with Grype, and gives each
vulnerability its own triage lifecycle with an audit trail. It also gives dashboards, time travel
over the whole app, and CSV export.

The repository is `Danube-Labs/javv-poc`. The license is BSL 1.1, and it changes to Apache-2.0 on
2030-06-10 (see [`LICENSE`](../../LICENSE)).

## The problem

Vulnerability tools are in two groups:

- Triage tools (DefectDojo, Dependency-Track) have a triage lifecycle, but their reports are rigid.
- Log dashboards have flexible reports, but no audit of a finding.

JAVV gives a real triage lifecycle and flexible dashboards, over the images that run now.

## Who uses it

The roles are in [`docs/engineering/SPEC.md`](../../docs/engineering/SPEC.md) ("Actors") and in
[`docs/API.md`](../../docs/API.md) ("Roles and permissions"):

| Role | What it does |
|---|---|
| Viewer | Reads findings, images, trends and the audit log |
| Triager | Also exports, makes dashboards, triages, and makes `not_affected` decisions |
| Security lead | Also makes risk accepts and ignore rules, and reviews the approvals queue |
| Admin | All capabilities: users, roles, tokens, settings, retention, snapshots, the data inspector and the jobs |
| Scanner | A client that finds images, scans them and pushes the results |

## Three things that JAVV does differently

1. **It scans what runs, not a registry.** The scanner finds the images that the cluster runs now.
2. **Two scanners, never merged.** Trivy and Grype results stay side by side. JAVV shows where
   they do not agree, and never removes a CVE because the other scanner has it.
3. **Each vulnerability has an audit trail.** Each finding keeps who changed what and when. Time
   travel shows each screen as it was at a time in the past.

## Hard constraints

These come from [`CLAUDE.md`](../../CLAUDE.md) ("Hard constraints") and the decisions in
[`docs/engineering/PLAN.md`](../../docs/engineering/PLAN.md). A change that breaks one of them
fails review.

- **No external broker.** No Redis, Kafka or RabbitMQ. OpenSearch is the only store, and it also
  does the coordination. The backend runs its own background jobs (D47).
- **Server-side counts.** Each count and each page comes from an OpenSearch query or aggregation.
  The client never gets raw findings to count them.
- **Tenants by `cluster_id`.** Each read and each export has an explicit `cluster_id` filter in the
  query layer. Indices use `cluster_id`, never the `cluster_name` that a user can change.
- **Per scanner.** A CVE from Trivy and the same CVE from Grype are two findings. JAVV flags a
  disagreement and never merges them.
- **Our own scanner images.** One Dockerfile for each scanner, with a pinned scanner version. No
  Trivy Operator and no third-party scanner operator.
- **The build sets the scanner version (D41).** The operator changes it with a new image
  tag. JAVV never writes to a monitored cluster.
- **One file for external versions (D42).** Scanner and OpenSearch versions are in
  [`versions.yaml`](../../versions.yaml).

## What JAVV does not do

Each item has a ruling. The links are in [`rulings.md`](rulings.md).

- It does not apply its VEX export in the scanners. The export is a record of triage decisions
  (issue 41). The scanner side is issue 791, after 1.0.
- It has no maintenance switch (issue 719) and no Prometheus alert rules (issue 41).
- It has no scanners other than Trivy and Grype (issue 865).
- It does not read `imagePullSecrets` from the cluster. The operator mounts a registry login
  (issue 739).
- Single sign-on (OIDC, LDAP) is not built yet (issue 131).

## Where the project is going

The plan of record is issue 555, the roadmap.

1. The bolts M0 to M10 built the product. M10 closed on 2026-10-09.
2. The MVP release was 0.6.1 (2026-10-06). It was the first release that published the images and
   the charts.
3. Now: hardening for 1.0. Each issue open on 2026-10-10 is in the 1.0.0 milestone, unless the
   operator moved it out.
4. After 1.0: development moves to `Danube-Labs/javv` with a cleaned history (issue 926).
