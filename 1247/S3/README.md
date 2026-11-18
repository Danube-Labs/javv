# Issue 1247, slice S3

Each folder holds one screen: `before.png`, `after.png` and `ab.png` (both, side by side).
A row with "no picture" is a tooltip, a toast, a screen-reader label or a state that the stack cannot show.

## For triage

- **Release 1.1.** Three old texts said that a past time works "until the v1.1 metrics rollup" (rows 61, 77 and 81). The pictures are `05-all-clusters-past` and `07-scanner-status-past`. The new text keeps the fact: "only from release 1.1". Keep this promise, or remove the release from the text?
- **Two ruled texts.** Rows 20 and 42 change the words of older operator rulings. S1 did the same for its six rulings. The ruled behavior stays: Riskiest images still tells "no inventory" apart from "no findings", and the strip still shows "-" when its read fails.
- **A label now wraps.** On Scanner status, "findings · last scan" is longer than "findings · last run". It wraps to two lines (picture `06-scanner-status`). The cell beside it wrapped before this change too.
- **Kept as it is.** The titles "Vulnerabilities over time", "Scan ingest" and "Failed ingests" stay (D1 ruling for the panel titles). The refused-scans table still names no retry action, as its spec requires.
- **Export lines.** S3 writes "JAVV did not export the file." S2 wrote "JAVV could not export the file." on the Approval list. S2 takes the S3 form when it is rebased.


| # | Picture | File | Before | After |
|---|---|---|---|---|
| 1 | [`01-overview`](01-overview/ab.png) | `views/OverviewView.vue` | Current state across <b class="mono-cell">…- · last sweep … | The state of <b class="mono-cell">…- now. The last scan arrived at …. |
| 2 | [`03-overview-failed`](03-overview-failed/ab.png) | `views/OverviewView.vue` | Overview unavailable. Check the backend connection. | JAVV cannot show the overview. Check the backend connection. |
| 3 | [`02-overview-empty`](02-overview-empty/ab.png) | `views/OverviewView.vue` | No sweep has landed yet" hint="KPIs and trends appear after the first scanner cycle commits. Scanner status shows per-scanner progress. | No scans yet" hint="JAVV shows the numbers and the charts when a scanner completes its first scan cycle. Scanner status shows the progress of each scanner. |
| 4 | [`01-overview`](01-overview/ab.png) | `views/OverviewView.vue` | new per day · … · resolved = scan-observed | New findings for each day · …. Resolved: a scan did not find the finding again. |
| 5 | no picture | `views/OverviewView.vue` | Trend at daily resolution: chart covers the last 1 day. | The chart has one bar for each day. It shows all of the last day. |
| 6 | no picture | `components/overview/OverviewStatBands.vue` | alert">Findings summary unavailable. | alert">JAVV cannot show the findings summary. Check the backend connection. |
| 7 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | Open findings filtered to … | Open the … findings |
| 8 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | Open findings with a fix available | Open the findings with a fix |
| 9 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | … findings patchable today | … findings have a fix now |
| 10 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | Open known-exploited findings | Open the known-exploited findings |
| 11 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | Open findings where the scanners disagree | Open the findings where the scanners do not agree |
| 12 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | Open the untriaged queue | Open the findings that are not triaged |
| 13 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewStatBands.vue` | … ack · | … acknowledged · |
| 14 | [`01-overview`](01-overview/ab.png) | `components/overview/PackageTypeCard.vue` | share of findings | The share of the findings in each package type. |
| 15 | no picture | `components/overview/PackageTypeCard.vue` | alert">Package-type counts unavailable. | alert">JAVV cannot show the package types. Check the backend connection. |
| 16 | [`01-overview`](01-overview/ab.png) | `components/overview/PackageTypeCard.vue` | Open … findings | Open the … findings |
| 17 | no picture | `components/overview/PackageTypeCard.vue` | Awaiting package-type data. Populates as the next scan cycles re-observe images. | No package types yet. JAVV shows them after the next scan cycles find the images again. |
| 18 | [`01-overview`](01-overview/ab.png) | `components/overview/RiskiestImagesCard.vue` | ranked by critical, then high | The images in order of their critical findings, then their high findings. |
| 19 | no picture | `components/overview/RiskiestImagesCard.vue` | alert">Riskiest images unavailable. | alert">JAVV cannot show the riskiest images. Check the backend connection. |
| 20 | no picture **ruled** (operator 2026-10-25) | `components/overview/RiskiestImagesCard.vue` | No inventory committed yet. Images show once a scanner cycle completes.' : 'No inventory committed at this point in time. | No inventory yet. JAVV shows the images when a scanner completes a scan cycle.' : 'No inventory at this time. |
| 21 | no picture | `components/overview/RiskiestImagesCard.vue` | No image findings in the running inventory. | The running images have no findings. |
| 22 | [`01-overview`](01-overview/ab.png) | `components/overview/TopComponentsCard.vue` | by unique vulnerabilities | The packages with the most vulnerabilities. |
| 23 | [`04-overview-past`](04-overview-past/ab.png) | `components/overview/TopComponentsCard.vue` | Component ranking is a current-state read, unavailable at a rewound T. | This panel shows only the time now, not the past time that you selected. To see the components, select Back to now. |
| 24 | no picture | `components/overview/TopComponentsCard.vue` | alert">Component ranking unavailable. | alert">JAVV cannot show the top components. Check the backend connection. |
| 25 | no picture | `components/overview/TopComponentsCard.vue` | No component data yet. | No components yet. |
| 26 | [`01-overview`](01-overview/ab.png) | `components/overview/TopComponentsCard.vue` | <th class="r fit">Unique vulns | <th class="r fit">Vulnerabilities |
| 27 | [`01-overview`](01-overview/ab.png) | `components/overview/TopComponentsCard.vue` | Open findings mentioning … | Open the findings of … |
| 28 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewNamespacesCard.vue` | top … by findings | The … namespaces with the most findings. |
| 29 | no picture | `components/overview/OverviewNamespacesCard.vue` | alert">Namespace counts unavailable. | alert">JAVV cannot show the namespaces. Check the backend connection. |
| 30 | no picture | `components/overview/OverviewNamespacesCard.vue` | empty-row">No namespace data in range. | empty-row">No namespaces in this range. |
| 31 | [`01-overview`](01-overview/ab.png) | `components/overview/OverviewNamespacesCard.vue` | Open findings in … | Open the findings in … |
| 32 | [`12-dashboard`](12-dashboard/ab.png) | `components/dashboards/FindingsTrendPanel.vue` | new per day · … · resolved = scan-observed | New findings for each day · …. Resolved: a scan did not find the finding again. |
| 33 | no picture | `components/dashboards/FindingsTrendPanel.vue` | alert">Vulnerability trend unavailable. | alert">JAVV cannot show the findings over time. Check the backend connection. |
| 34 | no picture | `components/dashboards/FindingsTrendPanel.vue` | Trend at daily resolution: chart covers the last 1 day. | The chart has one bar for each day. It shows all of the last day. |
| 35 | [`01-overview`](01-overview/ab.png) | `charts/buildFindingsTrendOption.ts` | resolved (scan-observed) · ${ | resolved by a scan · ${ |
| 36 | [`12-dashboard`](12-dashboard/ab.png) | `components/dashboards/TopCvesPanel.vue` | by findings | The vulnerabilities with the most findings. |
| 37 | no picture | `components/dashboards/TopCvesPanel.vue` | alert">Vulnerability ranking unavailable. | alert">JAVV cannot show the top vulnerabilities. Check the backend connection. |
| 38 | no picture | `components/dashboards/TopCvesPanel.vue` | empty-row">No vulnerability in the findings. | empty-row">No vulnerabilities yet. |
| 39 | no picture | `components/dashboards/IngestLens.vue` | { subject: 'the table' }, ) const timeTravel = useTimeTravelStore( | { subject: 'the table' }, ) const timeTravel = useTimeTravelStore() /** the subject starts a sentence in the strip text */ const subjectCap = computed(() => props.subject.charAt(0).toUpperCase() + props.subject.slice(1 |
| 40 | [`01-overview`](01-overview/ab.png) | `components/dashboards/IngestLens.vue` | runs per … · … (daily bars: covers the last 1 day) · … shows the state at the end of this range</span | Scans for each … · …. The chart has one bar for each day. It shows all of the last day. … shows the state at the end of this range.</span |
| 41 | [`01-overview`](01-overview/ab.png) | `components/dashboards/IngestLens.vue` | last ingest … · … ({{ | last scan … · … ({{ |
| 42 | no picture **ruled** (operator 2026-10-12) | `components/dashboards/IngestLens.vue` | il-last mono-cell">last ingest - | il-last mono-cell">last scan - |
| 43 | no picture | `components/dashboards/IngestLens.vue` | Loading ingest activity | Loading the scans |
| 44 | no picture | `components/dashboards/IngestLens.vue` | Ingest activity unavailable. | JAVV cannot show the scans. Check the backend connection. |
| 45 | no picture | `components/dashboards/IngestLens.vue` | No scans committed in this range: … shows the state last updated …, … ago</template >. | No scans in this range. … shows the state of the last scan, …, … ago.</template |
| 46 | no picture | `components/dashboards/IngestLens.vue` | Click a day to view the whole app as of the end of that day | Select a day to see the app as it was at the end of that day |
| 47 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/dashboards/FailedIngestsLens.vue` | pushes the backend refused per … | The scans that the backend refused, for each …. |
| 48 | no picture | `components/dashboards/FailedIngestsLens.vue` | Failed-ingest activity unavailable. | JAVV cannot show the refused scans. Check the backend connection. |
| 49 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/dashboards/FailedIngestsLens.vue` | No refused pushes in this range. | No refused scans in this range. |
| 50 | no picture | `components/dashboards/FailedIngestsLens.vue` | Loading failed ingests | Loading the refused scans |
| 51 | no picture | `components/dashboards/FailedIngestsLens.vue` | Click a day to view the whole app as of the end of that day | Select a day to see the app as it was at the end of that day |
| 52 | [`08-audit-log`](08-audit-log/ab.png) | `components/dashboards/AuditLens.vue` | emptyNote: 'No journaled activity in this range. Older events are still in the table below. | emptyNote: 'No events in this range. The table below still shows the older events. |
| 53 | [`08-audit-log`](08-audit-log/ab.png) | `components/dashboards/AuditLens.vue` | events per … · … · under the current filters · the table lists all events up to the range end</span | Events that match the filters, for each … · …. The table shows all events up to the end of the range.</span |
| 54 | no picture | `components/dashboards/AuditLens.vue` | Audit activity unavailable. | JAVV cannot show the audit activity. Check the backend connection. |
| 55 | no picture | `components/dashboards/AuditLens.vue` | Click a bucket to view the whole app as of its end | Select a bar to see the app as it was at the end of that bar |
| 56 | [`09-contributors`](09-contributors/ab.png) | `components/contributors/ContributorsLens.vue` | settling actions per day · … · resolved · not affected · risk accepted · acknowledged</span | Findings that people resolved, marked not affected, risk accepted or acknowledged, for each day · ….</span |
| 57 | no picture | `components/contributors/ContributorsLens.vue` | Handled-findings activity unavailable. | JAVV cannot show the handled findings. Check the backend connection. |
| 58 | [`10-contributors-empty`](10-contributors-empty/ab.png) | `components/contributors/ContributorsLens.vue` | No findings were handled in this window. The board below is empty too. | Nobody handled a finding in this range. The leaderboard below is empty too. |
| 59 | no picture | `components/contributors/ContributorsLens.vue` | Click a bucket to view the whole app as of its end | Select a bar to see the app as it was at the end of that bar |
| 60 | [`06-scanner-status`](06-scanner-status/ab.png) | `views/ScannerStatusView.vue` | committed runs only · versions are read-only provenance | This page counts only complete scans. Each scan records the version of its scanner. JAVV does not change the version. |
| 61 | [`07-scanner-status-past`](07-scanner-status-past/ab.png) | `views/ScannerStatusView.vue` | Historical scanner status is limited until the v1.1 metrics rollup" body="Freshness and provenance answer for now. The committed-run history you can rewind lives in the ingest lens above. Return to now for live scanner health. | JAVV shows the scanner status of a past time only from release 1.1" body="This page shows the last scan and the scanner versions for the time now only. The chart of scans above shows the past time. To see the scanner status now, select Back to now. |
| 62 | no picture | `views/ScannerStatusView.vue` | Scanner status unavailable. Check the backend connection. | JAVV cannot show the scanner status. Check the backend connection. |
| 63 | no picture | `views/ScannerStatusView.vue` | No scanner has reported for this cluster yet. The first committed run lands here. | No scanner has sent a scan for this cluster yet. The first scan shows here. |
| 64 | no picture | `components/scanners/ScannerStatusCard.vue` | No committed run yet: this scanner has never reported for this cluster. | No scan yet. This scanner has not sent a scan for this cluster. |
| 65 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/ScannerStatusCard.vue` | images · last run | images · last scan |
| 66 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/ScannerStatusCard.vue` | findings · last run | findings · last scan |
| 67 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/ScannerStatusCard.vue` | fixable · last run | fixable · last scan |
| 68 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/ScannerStatusCard.vue` | last ingest<template | last scan<template |
| 69 | no picture | `components/scanners/ScannerStatusCard.vue` | A running scanner with a stale vulnerability database quietly under-reports. Refresh the published image | A scanner with an old vulnerability database does not find the newest vulnerabilities. Update the scanner image. |
| 70 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/ScannerRunsTable.vue` | <th class="fit">Committed{{ atCap ? · last … : '' }} Run | <th class="fit">Complete{{ atCap ? · last … : '' }} Scan |
| 71 | no picture | `components/scanners/IngestFailuresTable.vue` | Failed ingests for … | Failed ingests of … |
| 72 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/IngestFailuresTable.vue` | pushes the backend refused in this range · retries stay with the scanner | The scans that the backend refused in this range. Only the scanner can send a scan again. |
| 73 | no picture | `components/scanners/IngestFailuresTable.vue` | Loading failed ingests | Loading the refused scans |
| 74 | no picture | `components/scanners/IngestFailuresTable.vue` | alert">Failed ingests unavailable. | alert">JAVV cannot show the refused scans. Check the backend connection. |
| 75 | [`06-scanner-status`](06-scanner-status/ab.png) | `components/scanners/IngestFailuresTable.vue` | empty-row">No failed ingests in this range. | empty-row">No refused scans in this range. |
| 76 | no picture | `components/scanners/IngestFailuresTable.vue` | the push carried no image JAVV could read | The scan has no image that JAVV can read. |
| 77 | [`05-all-clusters-past`](05-all-clusters-past/ab.png) | `views/AllClustersView.vue` | Historical fleet view, limited until the v1.1 rollup | JAVV shows all clusters at a past time only from release 1.1. |
| 78 | [`04-all-clusters`](04-all-clusters/ab.png) | `views/AllClustersView.vue` | Fleet current state <!-- | The state of all clusters now <!-- |
| 79 | no picture | `views/AllClustersView.vue` | Cluster list unavailable. Check the backend connection. | JAVV cannot show the clusters. Check the backend connection. |
| 80 | no picture | `views/AllClustersView.vue` | A cluster appears here once its scanner token is minted and the first sweep lands. Tokens are minted in Settings. | A cluster shows here when its first scan arrives. Create a scanner token in Settings, then deploy the scanners. |
| 81 | [`05-all-clusters-past`](05-all-clusters-past/ab.png) | `components/dashboards/LimitedHistoricalNotice.vue` | title: 'Historical all-clusters view is limited until the v1.1 metrics rollup', body: 'Single-cluster screens rewind fully. Pick a cluster and travel from its Overview. Fleet-wide numbers at a past T need the metrics rollup (v1.1); until then this screen only answers for now. | title: 'JAVV shows all clusters at a past time only from release 1.1', body: 'The pages of one cluster can show any past time. Select a cluster, then select the time on its Overview. This page shows the numbers of all clusters for the time now only. |
| 82 | [`04-all-clusters`](04-all-clusters/ab.png) | `components/dashboards/FleetTable.vue` | <th class="r">Last sweep | <th class="r">Last scan |
| 83 | [`04-all-clusters`](04-all-clusters/ab.png) | `components/dashboards/FleetTable.vue` | Each cluster's scanner module pushes independently over HTTPS with its own API token: a cluster going quiet shows up here, not as missing data downstream. | The scanners of each cluster send their scans over HTTPS with a scanner token of that cluster. When a cluster stops sending scans, this table shows it. |
| 84 | [`04-all-clusters`](04-all-clusters/ab.png) | `components/dashboards/FleetTable.vue` | Open … overview | Open the overview of … |
| 85 | no picture | `components/dashboards/MixBar.vue` | …'s committed scan | last scan of … |
| 86 | [`08-audit-log`](08-audit-log/ab.png) | `views/AuditTrailView.vue` | immutable, per user · window bounded by audit-log retention | Nobody can change or delete an event. The log keeps the events for its retention period. |
| 87 | no picture | `views/AuditTrailView.vue` | Audit log unavailable. Check the backend connection, then retry. | JAVV cannot show the audit log. Check the backend connection, then try again. |
| 88 | no picture | `views/AuditTrailView.vue` | Export failed (…). Check the backend connection. : 'Export failed. Check the backend connection. | JAVV did not export the file (…). Check the backend connection. : 'JAVV did not export the file. Check the backend connection. |
| 89 | no picture | `components/audit/AuditTable.vue` | Revision: same-field edits replay in this order, not by timestamp, because the revision is the finding's version when the edit landed, so a retried or near-simultaneous edit can't jump ahead. | Revision: the version of the finding when this change arrived. Changes to one field apply in the order of their revisions, not of their times. Thus a change that arrives late, or at the same time, cannot go before another change. |
| 90 | [`08-audit-log`](08-audit-log/ab.png) | `components/audit/AuditTable.vue` | data.decision.type === 'risk_accepted' ? 'risk accept' : | data.decision.type === 'risk_accepted' ? 'risk acceptance' : |
| 91 | no picture | `audit/actionLabels.ts` | cluster_unretire: 'Cluster un-retired | cluster_unretire: 'Cluster brought back |
| 92 | no picture | `audit/actionLabels.ts` | Store inspected | Database inspected |
| 93 | no picture | `audit/actionLabels.ts` | Token minted | Token created |
| 94 | no picture | `audit/auditDetail.ts` | findings (frozen set | findings (the set at the time of the action |
| 95 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | derived from the audit trail · triage actions, not scan deltas | JAVV counts the triage actions of people from the audit log. It does not count the changes that scans make. |
| 96 | no picture | `views/ContributorsView.vue` | onCapped: () => toast.info('Too many rows to export at once. Narrow the window first. | onCapped: () => toast.info('Too many rows to export at once. Select a shorter time range first. |
| 97 | no picture | `views/ContributorsView.vue` | Export failed (…). Check the backend connection. : 'Export failed. Check the backend connection. | JAVV did not export the file (…). Check the backend connection. : 'JAVV did not export the file. Check the backend connection. |
| 98 | no picture | `views/ContributorsView.vue` | Contributors unavailable. Check the backend connection. | JAVV cannot show the contributors. Check the backend connection. |
| 99 | [`10-contributors-empty`](10-contributors-empty/ab.png) | `views/ContributorsView.vue` | No triage activity in this window. Handled findings chart contributors here. | No triage in this range. This page shows the people who handle findings. |
| 100 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | Open resolve actions in the audit log | Open the resolve actions in the audit log |
| 101 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | Open acknowledge actions in the audit log | Open the acknowledge actions in the audit log |
| 102 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | />median time-to-resolve | />median time to resolve |
| 103 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | pooled across the team | for all people together |
| 104 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | of SLA-bearing handled findings | of the handled findings with an SLA |
| 105 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | Open resolve actions in the audit log: all severities. This count is criticals only | Open the resolve actions in the audit log, of all severities. This number counts the critical findings only. |
| 106 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | most findings resolved · … | The people who resolved the most findings · …. |
| 107 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | all contributors · ranked by resolved | All contributors, with the most resolved findings first. |
| 108 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | now · Trivy and Grype together | The state now for Trivy and Grype together. |
| 109 | [`09-contributors`](09-contributors/ab.png) | `views/ContributorsView.vue` | from the audit trail | The newest triage actions in the audit log. |
| 110 | no picture | `components/contributors/ActivityFeed.vue` | Recent activity unavailable. Check the backend connection. | JAVV cannot show the recent activity. Check the backend connection. |
| 111 | [`10-contributors-empty`](10-contributors-empty/ab.png) | `components/contributors/ActivityFeed.vue` | No journaled activity yet. Triage actions land here as they happen. | No activity yet. This list shows each triage action when it occurs. |
| 112 | no picture | `components/contributors/ProgressPanel.vue` | Triage progress unavailable. Check the backend connection. | JAVV cannot show the triage progress. Check the backend connection. |
| 113 | [`10-contributors-empty`](10-contributors-empty/ab.png) | `components/contributors/ProgressPanel.vue` | No findings in the store yet. Progress appears after the first committed scan. | No findings yet. JAVV shows the progress after the first scan. |
| 114 | [`09-contributors`](09-contributors/ab.png) | `components/contributors/ProgressPanel.vue` | Open the … untriaged … findings | Open the … … findings that are not triaged |
| 115 | [`09-contributors`](09-contributors/ab.png) | `components/contributors/LeaderboardTable.vue` | <th class="r fit">Ack. | <th class="r fit">Acknowledged |
| 116 | [`11-dashboards`](11-dashboards/ab.png) | `views/DashboardsView.vue` | the dashboards that you can see · each panel reads the selected cluster | The dashboards that you can see. Each panel shows the data of the selected cluster. |
| 117 | no picture | `views/DashboardsView.vue` | Dashboards unavailable. Check the backend, then reload. | JAVV cannot show the dashboards. Check the backend connection, then reload the page. |
| 118 | no picture | `views/DashboardsView.vue` | onCapped: () => toast.error('The export failed. Try again.'), onFailed: (status) => toast.error(readFailureCopy(status, 'The export failed. Check the backend, then try again. | onCapped: () => toast.error('JAVV did not export the file. Try again.'), onFailed: (status) => toast.error(readFailureCopy(status, 'JAVV did not export the file. Check the backend connection, then try again. |
| 119 | no picture | `views/DashboardView.vue` | onCapped: () => toast.error('The export failed. Try again.'), onFailed: (status) => toast.error(readFailureCopy(status, 'The export failed. Check the backend, then try again. | onCapped: () => toast.error('JAVV did not export the file. Try again.'), onFailed: (status) => toast.error(readFailureCopy(status, 'JAVV did not export the file. Check the backend connection, then try again. |
| 120 | no picture | `views/DashboardView.vue` | The dashboard is unavailable. Check the backend, then reload. | JAVV cannot show the dashboard. Check the backend connection, then reload the page. |
| 121 | [`14-dashboard-details`](14-dashboard-details/ab.png) | `components/dashboards/DashboardDetailsDialog.vue` | the scanner switch when the page opens | The scanner that the page shows first. |
| 122 | [`13-import`](13-import/ab.png) | `components/dashboards/ImportDashboardsDialog.vue` | A file from Export: one dashboard on each line | A file from Export, with one dashboard on each line |
| 123 | [`13-import`](13-import/ab.png) | `components/dashboards/ImportDashboardsDialog.vue` | a copy gets a new ID; an ID that exists is not made again | A copy gets a new ID. If a dashboard ID exists, JAVV does not make that dashboard again. |
| 124 | [`15-add-panel`](15-add-panel/ab.png) | `dashboards/catalog.ts` | Scan runs that reached JAVV in the time range, per scanner, and the last one. | The scans that reached JAVV in the time range, for each scanner, and the last scan. |
| 125 | [`15-add-panel`](15-add-panel/ab.png) | `dashboards/catalog.ts` | Scan reports that JAVV refused in the time range, per scanner. | The scans that JAVV refused in the time range, for each scanner. |
| 126 | [`15-add-panel`](15-add-panel/ab.png) | `dashboards/catalog.ts` | Findings that people resolved, marked not affected, accepted or acknowledged, per day. | The findings that people resolved, marked not affected, risk accepted or acknowledged, for each day. |
| 127 | no picture | `dashboards/catalog.ts` | finding states and decisions that people changed | The finding states and decisions that people changed. |
| 128 | no picture | `dashboards/details.ts` | The store is read-only: its disk is full. JAVV did not delete the dashboard. | The database is read-only because its disk is full. JAVV did not delete the dashboard. |
| 129 | no picture | `dashboards/details.ts` | The store is busy. JAVV did not delete the dashboard. Try again in a few seconds. | The database is busy. JAVV did not delete the dashboard. Try again in a few seconds. |
| 130 | no picture | `dashboards/details.ts` | JAVV did not delete the dashboard. Check the backend, then try again. | JAVV did not delete the dashboard. Check the backend connection, then try again. |
| 131 | no picture | `dashboards/details.ts` | The store is read-only: its disk is full. JAVV did not make the dashboard. | The database is read-only because its disk is full. JAVV did not make the dashboard. |
| 132 | no picture | `dashboards/details.ts` | The store is busy. JAVV did not make the dashboard. Try again in a few seconds. | The database is busy. JAVV did not make the dashboard. Try again in a few seconds. |
| 133 | no picture | `dashboards/details.ts` | JAVV did not make the dashboard. Check the backend, then try again. | JAVV did not make the dashboard. Check the backend connection, then try again. |
| 134 | no picture | `dashboards/edit.ts` | The store is read-only: its disk is full. JAVV did not save the dashboard. | The database is read-only because its disk is full. JAVV did not save the dashboard. |
| 135 | no picture | `dashboards/edit.ts` | The store is busy. JAVV did not save your changes. Try again in a few seconds. | The database is busy. JAVV did not save your changes. Try again in a few seconds. |
| 136 | no picture | `dashboards/edit.ts` | JAVV did not save your changes. Check the backend, then try again. | JAVV did not save your changes. Check the backend connection, then try again. |
| 137 | no picture | `dashboards/files.ts` | The search backend was busy, so the import stopped. | The database was busy, so the import stopped. |
