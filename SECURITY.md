# Security policy

This page tells you how to report a security problem in JAVV, and what occurs after you report it.

JAVV is a tool that manages vulnerabilities. Thus we apply to JAVV the same standard that JAVV
helps teams to apply. Thank you for your report.

## Report a vulnerability

**Do not open a public issue for a security vulnerability.**

1. Open the GitHub form
    [**Report a vulnerability**](https://github.com/Danube-Labs/javv-poc/security/advisories/new)
    (**Security** tab, then **Advisories**). The form makes a private thread that only the
    maintainers can see. When we publish the fix, we can name you in the advisory.
2. Include as much of this data as you can:
    - The component: the backend API, the ingest endpoint, the frontend, a published scanner image,
        or a job.
    - The version or the commit that you tested.
    - The steps to show the problem, a proof of concept, or a request that fails.
    - The effect of the problem, and the conditions that it needs. Examples of conditions are a
        sign-in, a specific capability, or a specific cluster configuration.

## What to expect

A small team maintains JAVV. These times are our targets. They are not a service-level agreement.

| Stage | Target |
|---|---|
| We tell you that we received your report | 3 business days or less |
| We do the first assessment and give a severity | 7 business days or less |
| We release a fix or a documented workaround for a problem that we accept as a vulnerability | As fast as the severity requires |

- While we work on the report, we tell you about our progress.
- If we decide that the problem is not a vulnerability, we tell you why.
- When we release the fix, we publish an advisory.
- Before you make the problem public, give us a reasonable time to release the fix.

## Supported versions

- JAVV is before version 1.0 and changes quickly.
- Security fixes go into `main` and into the next release.
- Thus **we support only the latest release**. See
  [Releases](https://github.com/Danube-Labs/javv-poc/releases) for the current release.

## Scope

**In scope**, all parts that JAVV owns:

- The FastAPI backend, and specially the **ingest endpoint**. This endpoint reads scanner output
  that JAVV cannot trust.
- Sign-in, sessions, ingest tokens, and the access model that uses capabilities.
- The queries that JAVV sends to OpenSearch. This includes the isolation of each cluster by
  `cluster_id`, and injection into the query DSL.
- The Vue frontend. This includes all problems that can show the data of a different cluster in a
  browser.
- The **scanner images that JAVV publishes** (`ghcr.io/danube-labs/javv-scanner-{trivy,grype}`) and
  the Dockerfiles that make them.
- The CI and release tools in this repository, where a problem can change a published artifact.

**Out of scope:**

- Vulnerabilities in **Trivy or Grype**. Report them to
  [aquasecurity/trivy](https://github.com/aquasecurity/trivy/security) or
  [anchore/grype](https://github.com/anchore/grype/security). When a scanner version that JAVV pins
  has a known problem, open a normal issue that asks for a new version. That issue is in scope.
- Vulnerabilities in OpenSearch, Kubernetes or other dependencies. The exception is a problem that
  the configuration of JAVV, or the use of the dependency by JAVV, causes.
- Problems that need an attacker who already controls a cluster, a host or an administrator
  account.
- An installation that its operator configured without security, when the documented defaults of
  JAVV are safe. Some hardening is the work of the operator. See
  [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for each setting.

## Design decisions to know before you test

We made these decisions on purpose. If you can break one of them, tell us.

- **A token protects each push. JAVV does not check a signature.** Each scanner pushes with a
  bearer token for one cluster and one scanner. JAVV keeps only a keyed hash of each token, and it
  compares hashes in constant time. A token for one cluster cannot push the data of a different
  cluster.
- **The data inspector can only read.** It permits only a fixed list of read requests. It refuses
  the indices that hold credentials. JAVV writes each query to the audit log. A write through the
  data inspector is a real finding.
- **The backend isolates each cluster.** The query layer adds an explicit `cluster_id` filter to
  each read. The frontend does not do this isolation.
- **JAVV never writes to the clusters that it scans.** The JAVV backend never connects to these
  clusters. The scanners in each cluster read only the pods, to find the images that run, and the
  `kube-system` namespace.
