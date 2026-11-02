# From a scan to a finding

<video controls preload="metadata" width="100%" src="videos/from-a-scan-to-a-finding.mp4"></video>

## How the results get to JAVV

Trivy and Grype run in your cluster. They scan each running image. Each scanner sends its results
to JAVV. JAVV keeps the results of each scanner separate. It never merges them.

## Why JAVV shows fewer findings than the scanner report

A scanner report can show the same CVE in the same package version more than one time. Each entry
is for a different file that holds the package. JAVV keeps one finding for each CVE, package
version, image and scanner. Thus the number of findings in JAVV can be smaller than the number of
entries in the report.

Example: the Trivy report for rancher/local-path-provisioner v0.0.36 has 371 entries. The Go
standard library v1.26.3 is in 11 programs of this image. Trivy shows each CVE of this library 11
times. JAVV shows 101 findings for this image.

What one finding covers:

- A finding closes when no file in the image holds the package version. If you rebuild 9 of the
  11 programs, the finding stays open.
- A state or a risk acceptance applies to the finding. Thus it applies to all the files that hold
  the package.

## Steps

1. All clusters shows each cluster that sends results to JAVV. Select a cluster to open it.
2. Open Findings from the side menu. Each row is one finding: one CVE, in one package, in one
   image, from one scanner.
3. To see the findings of one scanner, use the Scanner filter.
4. Select a finding to open it. The evidence shows the result of each scanner, side by side.
5. Set the state of the finding in the triage panel. The next page shows how.

Next: [Set the state of a finding](set-the-state-of-a-finding.md).
