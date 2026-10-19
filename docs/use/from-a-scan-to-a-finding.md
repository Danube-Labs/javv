# From a scan to a finding

<video controls preload="metadata" width="100%" src="videos/from-a-scan-to-a-finding.mp4"></video>

## How the results get to JAVV

Trivy and Grype run in your cluster. They scan each running image. Each scanner sends its results
to JAVV. JAVV keeps the results of each scanner separate. It never merges them.

## Steps

1. All clusters shows each cluster that sends results to JAVV. Select a cluster to open it.
2. Open Findings from the side menu. Each row is one finding: one CVE, in one package, in one
   image, from one scanner.
3. To see the findings of one scanner, use the Scanner filter.
4. Select a finding to open it. The evidence shows the result of each scanner, side by side.
5. Set the state of the finding in the triage panel. The next page shows how.

Next: [Set the state of a finding](set-the-state-of-a-finding.md).
