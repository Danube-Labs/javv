# JAVV operator docs

JAVV finds the container images that run in your Kubernetes clusters. It scans each image with
Trivy and with Grype, and it keeps the results of each scanner apart. For each vulnerability, JAVV
records each triage decision in an audit log.

These pages are for the people who install and operate JAVV. To learn how to triage findings in
JAVV, read [Use JAVV](use/index.md). It has a short video for each task.

## Start here

| To do this | Read |
|---|---|
| Install JAVV with docker compose or with Helm | [Deploying](DEPLOYING.md) |
| Run the scanners in the clusters that you scan | [Deploying: connect the scanners](DEPLOYING.md#connect-the-scanners) and the [scanner chart](../deploy/helm/javv-scanner/README.md) |
| Find the scanner and OpenSearch versions that a release supports | [Supported versions](supported-versions.md) |
| Change a setting | [Configuration](CONFIGURATION.md) |
| Calculate the OpenSearch size for your clusters | [Sizing OpenSearch](runbooks/opensearch-sizing.md) |
| Learn which parts scale, and what occurs when a part fails | [Scaling and failures](runbooks/multi-pod.md) |
| Learn which indices JAVV uses, how long it keeps the data, and what a snapshot holds | [Indices and data](runbooks/indices-and-data.md) |
| Upgrade JAVV, or go back to the previous release | [Upgrading](UPGRADING.md) and the [release notes](../CHANGELOG.md) |
| Verify the published images and charts | [Deploying: verify the images and charts](DEPLOYING.md#verify-the-images-and-charts) |
| Send requests to JAVV from a script, or push results from your own tools | [API](API.md) and [Push from your own script](INGEST-CONTRACT.md) |
| Report a security problem | [Security](../SECURITY.md) |

Each JAVV release has its own version of these docs. Select the version in the version menu.
