# Issue 1247, slice S1: the text of the shared parts

Each folder holds one screen: `before.png` (main), `after.png` (this slice) and `ab.png` (both, side by side).
A row with "no picture" is a tooltip, a toast, a screen-reader label or a state that the stack cannot show.
[`00-ruled-copy-ab.png`](00-ruled-copy-ab.png) shows the ruled texts close up. Rows marked **ruled** replace the words of an older copy ruling (operator ruling of 2026-11-17: change all).

| # | Picture | File | Before | After |
|---|---|---|---|---|
| 1 | no picture | `components/chips/CountDisagree.vue` | Trivy and Grype both report … | Trivy and Grype both report …. |
| 2 | no picture | `components/chips/CountDisagree.vue` | Only … has a committed scan of this digest: … findings | Only … scanned this digest. It reports … findings. |
| 3 | no picture | `components/chips/EpssBar.vue` | EPSS enrichment arrives with Grype results only | Only Grype sends the EPSS score. |
| 4 | no picture | `components/chips/DisagreementBadge.vue` | Scanners disagree on this finding | The scanners do not agree on this finding. |
| 5 | [`01-top-bar-side-nav`](01-top-bar-side-nav/ab.png) | `components/chrome/ClusterSwitcher.vue` | Clusters · by cluster_id | Clusters · by ID |
| 6 | [`02-search-hint`](02-search-hint/ab.png) | `components/chrome/CommandPalette.vue` | Search vulnerability, image, namespace, or jump to a screen… | Search for a vulnerability, an image or a namespace, or go to a screen… |
| 7 | [`03-search-failed`](03-search-failed/ab.png) | `components/chrome/CommandPalette.vue` | Search unavailable. Check the backend connection. | JAVV cannot search now. Check the backend connection. |
| 8 | [`04b-search-one-letter`](04b-search-one-letter/ab.png) | `components/chrome/CommandPalette.vue` | Type …+ characters to search findings. Results are scoped to the selected cluster. | Type … or more characters to search the findings. The results come from the selected cluster only. |
| 9 | [`04-bell-open`](04-bell-open/ab.png) | `components/chrome/NotificationBell.vue` | polled · newest first | The newest is at the top. |
| 10 | [`06-bell-failed`](06-bell-failed/ab.png) | `components/chrome/NotificationBell.vue` | Notifications unavailable. The badge is paused, nothing here is stale. | JAVV cannot read the notifications now. The badge shows no count until JAVV can read them again. |
| 11 | [`05-bell-empty`](05-bell-empty/ab.png) | `components/chrome/NotificationBell.vue` | Nothing yet. SLA breaches, new assignments, ready exports and clusters about to be retired land here. | No notifications yet. This list shows SLA breaches, findings assigned to you, exports that are ready and clusters that JAVV will retire soon. |
| 12 | no picture | `components/chrome/NotificationBell.vue` | Expired. Re-run the export from Findings. | This export expired. Start the export again from Findings. |
| 13 | [`04-bell-open`](04-bell-open/ab.png) | `components/chrome/NotificationBell.vue` | Your scheduled export finished. Open to download. | Your export in the background is complete. Open it to download the file. |
| 14 | [`04-bell-open`](04-bell-open/ab.png) | `components/chrome/NotificationBell.vue` | A finding assigned to you ran past its SLA window. | A finding that is assigned to you is past its SLA deadline. |
| 15 | [`04-bell-open`](04-bell-open/ab.png) | `components/chrome/NotificationBell.vue` | … is due to be retired soon unless a scan arrives. | JAVV retires … soon if no scan arrives. |
| 16 | [`04-bell-open`](04-bell-open/ab.png) | `components/chrome/NotificationBell.vue` | … was due to be retired on … and will be retired unless a scan arrives. / … is due to be retired on … unless a scan arrives. | … was due for retirement on …. JAVV retires it if no scan arrives. / JAVV retires … on … if no scan arrives. |
| 17 | no picture | `components/chrome/NotificationBell.vue` | … has been retired. | JAVV retired …. |
| 18 | no picture | `components/chrome/NotificationBell.vue` | That export expired. Re-run it from the Findings screen. | That export expired. Start the export again from Findings. |
| 19 | [`01-top-bar-side-nav`](01-top-bar-side-nav/ab.png) | `components/chrome/SideNav.vue` | version unavailable | no version |
| 20 | [`01-top-bar-side-nav`](01-top-bar-side-nav/ab.png) | `components/chrome/SideNav.vue` | store schema v…, scanner schema v… | database schema …, scanner schema … |
| 21 | no picture | `components/chrome/SideNav.vue` | … · 2 cluster(s) (tooltip of the collapsed side bar) | … · 2 clusters |
| 22 | no picture | `components/chrome/SideNav.vue` | JAVV release · store schema (index layout) · newest scanner schema accepted. The full stack is on About. | The JAVV release, the database schema and the newest scanner schema that JAVV accepts. About shows all the versions. |
| 23 | no picture | `stores/health.ts` | Store healthy / Store degraded (footer of the side bar) | Database healthy / Database degraded |
| 24 | no picture | `components/filters/FacetRail.vue` | Could not search all values. The list shows the top …. | JAVV could not search all the values. The list shows the top …. |
| 25 | no picture | `components/filters/FilterBar.vue` | Could not search all values. The list shows the top …. | JAVV could not search all the values. The list shows the top …. |
| 26 | no picture | `components/filters/FilterPill.vue` | Click to include | Select to include |
| 27 | no picture | `components/filters/FilterPill.vue` | Click to exclude | Select to exclude |
| 28 | [`10-filter-rail`](10-filter-rail/ab.png) | `filters/fields.config.ts` | Findings past their SLA deadline under the current policy: the same rows whose SLA column shows overdue. Handled findings (risk-accepted, not-affected, resolved) are never counted. | Findings that are past their SLA deadline under the current policy. These are the rows that show overdue in the SLA column. JAVV does not count findings that are risk accepted, not affected or resolved. |
| 29 | [`10-filter-rail`](10-filter-rail/ab.png) | `filters/fields.config.ts` | Findings nobody owns yet: the untriaged backlog. This is absence, not exclusion: "assignee is not <someone>" keeps unowned rows too, so it can never ask this. | Findings that are not assigned to a person yet. The filter "Assignee is not <name>" also keeps these findings, so only this filter finds them. |
| 30 | [`10-filter-rail`](10-filter-rail/ab.png) | `filters/fields.config.ts` | Only findings first seen inside the selected time range. A quiet range shows 0. Off, the table shows everything currently present. | Only the findings that JAVV first saw in the selected time range. A range with no new findings shows 0. When this filter is off, the table shows all the findings that are present now. |
| 31 | no picture | `findings/failureCopy.ts` | This filter isn't answerable at a past point in time. Return to now, or drop the search/attribute filters. | JAVV cannot apply this filter at a past time. Go back to now, or remove the search and the attribute filters. |
| 32 | [`18-findings-bad-filter`](18-findings-bad-filter/ab.png) **ruled** | `findings/failureCopy.ts` | These filters can't be used together, or a value isn't valid. Check the filters. | You cannot use these filters together, or a value is not valid. Check the filters. |
| 33 | no picture | `findings/failureCopy.ts` | The search backend is busy. Try again in a few seconds. | The backend is busy. Try again in a few seconds. |
| 34 | [`17-findings-failed`](17-findings-failed/ab.png) | `findings/failureCopy.ts` | Findings unavailable. Check the backend connection. | JAVV cannot show the findings. Check the backend connection. |
| 35 | [`11-banner-read-only`](11-banner-read-only/ab.png) **ruled** | `components/system/BackendHealthBanner.vue` | The store is read-only: its disk is full. Reads work; changes are not saved. | The database is read-only because its disk is full. You can read the data, but JAVV does not save changes. |
| 36 | [`12-banner-red`](12-banner-red/ab.png) **ruled** | `components/system/BackendHealthBanner.vue` | Part of the store is not available. Some screens and changes can fail until it recovers. | Part of the database is not available. Some screens and changes can fail until it recovers. |
| 37 | [`14-banner-backend-down`](14-banner-backend-down/ab.png) **ruled** | `components/system/BackendHealthBanner.vue` | The backend is not answering. Screens cannot load until it is back. | The backend does not answer. Screens cannot load until it answers again. |
| 38 | [`13-banner-store-down`](13-banner-store-down/ab.png) **ruled** | `components/system/BackendHealthBanner.vue` | Search backend unavailable. Check OpenSearch health. | The database is not available. Check the health of OpenSearch. |
| 39 | no picture | `components/system/CrashBoundary.vue` | This page could not be shown | JAVV cannot show this page |
| 40 | no picture | `components/system/CrashBoundary.vue` | Something went wrong while showing this page. Your data is not affected. Try again, or go back to Overview. | An error occurred when JAVV showed this page. Your data did not change. Try again, or go back to Overview. |
| 41 | [`16-freshness-silent`](16-freshness-silent/ab.png) | `components/system/ScannerFreshnessBanner.vue` | Data may be stale on …: | The data of … can be old: |
| 42 | no picture | `components/system/ScannerFreshnessBanner.vue` | Last checked …; the latest check failed. | JAVV last checked at …. The latest check failed. |
| 43 | [`15-freshness-failed`](15-freshness-failed/ab.png) | `components/system/ScannerFreshnessBanner.vue` | Couldn't check scanner freshness on …. JAVV retries every 10 minutes. | JAVV could not check the scanner freshness of …. JAVV tries again every 10 minutes. |
| 44 | no picture | `components/system/ScannerFreshnessBanner.vue` | Scanner freshness last checked …; the latest check failed. JAVV retries every 10 minutes. | JAVV last checked the scanner freshness at …. The latest check failed. JAVV tries again every 10 minutes. |
| 45 | [`16-freshness-silent`](16-freshness-silent/ab.png) | `components/system/ScannerFreshnessBanner.vue` | … silent … | … sent no data for … |
| 46 | [`07-time-range`](07-time-range/ab.png) | `components/time-travel/GlobalTimePicker.vue` | One range drives the whole app: tables show state at the end of the range (a past end = as-scanned history) · charts aggregate the span. | One range applies to all screens. A table shows the state at the end of the range. If the end is in the past, the table shows the data as the scanners saw it then. A chart shows the full range. |
| 47 | [`07-time-range`](07-time-range/ab.png) | `components/time-travel/GlobalTimePicker.vue` | Absolute range (24h) | Exact range (24-hour clock) |
| 48 | no picture | `components/time-travel/GlobalTimePicker.vue` | Range start time (24h) | Range start time (24-hour clock) |
| 49 | no picture | `components/time-travel/GlobalTimePicker.vue` | Range end time (24h) | Range end time (24-hour clock) |
| 50 | no picture | `components/time-travel/GlobalTimePicker.vue` | Viewing state at … (UTC) | The state at … (UTC) |
| 51 | no picture | `components/ui/UiDateTime.vue` | Time (24h) | Time (24-hour clock) |
| 52 | [`20-cluster-list-failed`](20-cluster-list-failed/ab.png) | `layouts/AppShell.vue` | Cluster list unavailable, and every read needs it. Check the backend, then reload. | JAVV cannot show the cluster list, and each screen needs it. Check the backend connection, then reload the page. |
| 53 | [`08-history-line`](08-history-line/ab.png) | `layouts/AppShell.vue` | Viewing history: as scanned at … | History: the data as the scanners saw it at … |
| 54 | [`19-no-clusters`](19-no-clusters/ab.png) | `layouts/AppShell.vue` | No clusters registered yet | No clusters yet |
| 55 | [`19-no-clusters`](19-no-clusters/ab.png) | `layouts/AppShell.vue` | JAVV fills in once the first scanner envelope lands. Create a scanner token, deploy the scanner CronJobs to a cluster, and the first committed cycle appears here. | JAVV shows data when the first scan arrives. Create a scanner token, then deploy the scanners. The first scans then show here. |
| 56 | no picture | `lib/clipboard.ts` | Couldn't copy: the browser blocked the clipboard. Select the text and copy it. | JAVV could not copy the text, because the browser blocked the clipboard. Select the text and copy it. |
| 57 | no picture | `stores/auth.ts` | The server is not answering. This page checks again on its own. | The backend does not answer. This page checks again by itself. |
| 58 | no picture | `stores/auth.ts` | The store is read-only: its disk is full. | The database is read-only because its disk is full. |
| 59 | no picture **ruled** | `stores/auth.ts` | Signed in, but this browser did not keep the session. Allow cookies for this site, then sign in again. | JAVV signed you in, but this browser did not keep the session. Allow cookies for this site, then sign in again. |
| 60 | no picture | `stores/auth.ts` | The new password was refused. … | JAVV refused the new password. … |
| 61 | no picture | `stores/auth.ts` | Password change failed. Check the current password. | JAVV did not change the password. Check the current password. |
| 62 | no picture | `stores/cluster.ts` | The link points at a cluster this store does not know. Showing your default. | The link points to a cluster that JAVV does not know. JAVV shows your default cluster. |
| 63 | no picture | `stores/filters.ts` | … cleared. … and … can't be used together. | JAVV cleared the filter …. You cannot use … and … together. |
| 64 | no picture | `system/retirement.ts` | (code comment) It will be retired in 5 days unless a scan arrives. | JAVV retires it in 5 days if no scan arrives. |
| 65 | no picture | `system/retirement.ts` | It will be retired in … unless a scan arrives. | JAVV retires it in … if no scan arrives. |
| 67 | no picture | `system/retirement.ts` | It is past its retirement date: the next retirement sweep retires it unless a scan arrives, and waits while no cluster is scanning. | It is past its retirement date. The next retirement sweep retires it if no scan arrives. The sweep waits while no cluster sends scans. |

