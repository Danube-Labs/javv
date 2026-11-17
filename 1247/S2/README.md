# Issue 1247, slice S2: Findings, the finding page, triage, the Approval list and images

Each folder holds one screen: `before.png`, `after.png` and `ab.png` (both, side by side).
The "before" pictures show main with slice S1. Rows marked **ruled** replace the words of an older copy ruling, as you ruled for S1.
A row with "no picture" is a tooltip, a toast, a screen-reader label or a state that the stack cannot show.

| # | Picture | File | Before | After |
|---|---|---|---|---|
| 1 | no picture | `approvals/viewModel.ts` | Pick an expiry date after today. | Select an expiry date after today. |
| 2 | [`01-approval-list`](01-approval-list/ab.png) | `approvals/viewModel.ts` | (code comment) cluster-wide / ns: a, b / img: nginx +2 | whole cluster / namespace: a +1 / image: nginx +2 |
| 3 | [`01-approval-list`](01-approval-list/ab.png) | `approvals/viewModel.ts` | cluster-wide | whole cluster |
| 4 | [`01-approval-list`](01-approval-list/ab.png) | `approvals/viewModel.ts` | ns: … | namespace: … |
| 5 | [`01-approval-list`](01-approval-list/ab.png) | `approvals/viewModel.ts` | img: … | image: … |
| 6 | [`01-approval-list`](01-approval-list/ab.png) | `components/approvals/ApprovalsTable.vue` | (code: the style of the whole-cluster scope cell) | (code, no text change) |
| 7 | no picture | `components/approvals/ApprovalsTable.vue` | no expiry set | No expiry date |
| 8 | [`01-approval-list`](01-approval-list/ab.png) | `components/chips/ExpiryChip.vue` | expires today / expires in 3d | expires today / expires in 3 days |
| 9 | [`02-edit-decision`](02-edit-decision/ab.png) | `components/approvals/EditDecisionDialog.vue` | This decision was already revoked. Refresh the queue. | This decision is revoked already. Reload the Approval list. |
| 10 | no picture | `components/approvals/EditDecisionDialog.vue` | Could not apply the edit. Check the backend connection. | JAVV did not save the edit. Check the backend connection, then try again. |
| 11 | [`02-edit-decision`](02-edit-decision/ab.png) | `components/approvals/EditDecisionDialog.vue` | Edit risk-acceptance | Edit the risk acceptance |
| 12 | [`02-edit-decision`](02-edit-decision/ab.png) | `components/approvals/EditDecisionDialog.vue` | An edit is revoke + new (decisions are immutable): the current decision is revoked and a new one takes effect atomically, keeping the audit trail causal. | You cannot change a decision. An edit revokes this decision and creates a new decision. The old decision stays in the history. |
| 13 | [`02-edit-decision`](02-edit-decision/ab.png) | `components/approvals/EditDecisionDialog.vue` | Expiry · hint: empty keeps the current expiry | Expiry date · hint: If you leave it empty, the current expiry date stays. |
| 14 | [`01-approval-list`](01-approval-list/ab.png) | `components/approvals/ApprovalsTable.vue` | Justification | Reason |
| 15 | [`02-edit-decision`](02-edit-decision/ab.png) | `components/approvals/EditDecisionDialog.vue` | Justification | Reason |
| 16 | [`01-approval-list`](01-approval-list/ab.png) | `views/ApprovalsView.vue` | Approvals | Approval list |
| 17 | [`01-approval-list`](01-approval-list/ab.png) | `views/ApprovalsView.vue` | standing acceptance… | active risk acceptance… |
| 18 | [`01-approval-list`](01-approval-list/ab.png) | `views/ApprovalsView.vue` | review queue · active risk-accepts, soonest expiry first · revoked never listed | The risk acceptances that apply now. The next expiry date is first. The list does not show revoked decisions. |
| 19 | [`01-approval-list`](01-approval-list/ab.png) | `views/ApprovalsView.vue` | risk-accept creates + revokes journaled in this range. The queue below is current state | The risk acceptances that people created or revoked in this range. The list below shows the state now. |
| 20 | no picture | `views/ApprovalsView.vue` | JAVV keeps no history of the standing acceptances. The chart of decisions above shows the past time. Go back to now to review the list. | JAVV keeps no history of the active risk acceptances. The chart of decisions above shows the past time. Go back to now to see the list. |
| 21 | no picture | `views/ApprovalsView.vue` | Search acceptances by vulnerability (contains match | Search the risk acceptances by vulnerability |
| 22 | no picture | `views/ApprovalsView.vue` | Export failed (…). Check the backend connection. | JAVV could not export the file (…). Check the backend connection. |
| 23 | no picture | `views/ApprovalsView.vue` | Acceptance revoked. Its findings are Open again. | JAVV revoked the risk acceptance. Its findings are Open again. |
| 24 | no picture | `views/ApprovalsView.vue` | Revoke failed. Check the backend connection | JAVV did not revoke the risk acceptance. Check the backend connection, then try again. |
| 25 | no picture | `views/ApprovalsView.vue` | Decision re-issued (revoke + new | JAVV revoked the decision and created a new decision. |
| 26 | [`03-approval-list-failed`](03-approval-list-failed/ab.png) | `views/ApprovalsView.vue` | Could not load the queue. Check the backend connection. | JAVV cannot show the Approval list. Check the backend connection. |
| 27 | no picture | `components/finding/DetailHead.vue` | Scanners disagree on severity | The scanners do not agree on the severity. |
| 28 | no picture | `components/finding/DetailHead.vue` | Open this image's detail | Open the page of this image |
| 29 | no picture | `components/finding/EvidenceCard.vue` | verbatim from ' + c.scanner | as sent by ' + c.scanner |
| 30 | [`05-finding-no-image`](05-finding-no-image/ab.png) | `views/FindingDetailView.vue` | This link is missing the image identity. Open the finding from the grid. | This link names no image. Open the finding from the Findings table. |
| 31 | no picture | `views/FindingDetailView.vue` | No current finding for this vulnerability on this image. It may have been resolved by a newer scan, or the selected range ends before it was first seen. | This image has no current finding for this vulnerability. A newer scan may no longer report it. Or the selected time range may end before a scan found it. |
| 32 | [`06-finding-failed`](06-finding-failed/ab.png) | `views/FindingDetailView.vue` | Finding unavailable. Check the backend connection. | JAVV cannot show the finding. Check the backend connection. |
| 33 | [`07-findings`](07-findings/ab.png) | `views/FindingsView.vue` | Trivy and Grype count apart: a vulnerability that both report counts once for each | Trivy and Grype count apart. A vulnerability that both report counts once for each. |
| 34 | no picture | `views/FindingsView.vue` | Search findings (contains match | Search the findings |
| 35 | [`08-findings-counts-failed`](08-findings-counts-failed/ab.png) **ruled** | `views/FindingsView.vue` | Filter counts could not be loaded. ${readFailureCopy( | JAVV could not load the filter counts. ${readFailureCopy( |
| 36 | no picture | `views/AuditTrailView.vue` | Filter counts could not be loaded. ${readFailureCopy( | JAVV could not load the filter counts. ${readFailureCopy( |
| 37 | [`09-columns-menu`](09-columns-menu/ab.png) | `components/findings/ColumnsMenu.vue` | drag to reorder | drag to change the order |
| 38 | [`07-findings`](07-findings/ab.png) | `components/findings/GridPager.vue` | Prev< | Previous< |
| 39 | [`10-save-view`](10-save-view/ab.png) | `components/findings/SaveViewDialog.vue` | Filters, columns and time window, reusable by everyone | All users can use the filters, the columns and the time range of this view. |
| 40 | [`10-save-view`](10-save-view/ab.png) | `components/findings/SaveViewDialog.vue` | e.g. Critical KEV backlog | For example: Critical KEV backlog |
| 41 | no picture | `components/findings/SaveViewDialog.vue` | These filters can\'t be saved as a view. | You cannot save these filters as a view. |
| 42 | no picture | `components/findings/SaveViewDialog.vue` | Saving the view failed. Try again. | JAVV did not save the view. Try again. |
| 43 | [`11-export`](11-export/ab.png) | `components/findings/ExportDialog.vue` | what you are looking at now · a VEX file holds the results of one scanner | The file holds the rows that you see now. A VEX file holds the results of one scanner. |
| 44 | no picture | `components/findings/ExportDialog.vue` | Report failed. Re-run the export. | JAVV could not make the file. Start the export again. |
| 45 | no picture | `components/findings/ExportDialog.vue` | Scheduled, status: | In the background. Status: |
| 46 | no picture | `components/findings/ExportDialog.vue` | Export failed (…). Check the backend connection. : 'Export failed. Check the backend connection. | JAVV could not export the file (…). Check the backend connection. : 'JAVV could not export the file. Check the backend connection. |
| 47 | no picture | `components/findings/ExportDialog.vue` | expires in ~${ | expires in about ${ |
| 48 | no picture | `components/findings/ExportDialog.vue` | Could not schedule. Check the backend connection. | JAVV could not start the export in the background. Check the backend connection. |
| 49 | no picture | `components/findings/ExportDialog.vue` | Session expired while waiting. Sign in again: the report keeps running and rings the bell. | Your session expired. Sign in again. JAVV continues to make the file, and the bell tells you when it is ready. |
| 50 | no picture | `components/findings/ExportDialog.vue` | The scheduled report is gone (expired or removed). Re-run the export. | The file is not available any more, because it expired or somebody deleted it. Start the export again. |
| 51 | no picture | `components/findings/ExportDialog.vue` | Lost contact with the backend while polling. The bell will ring when the report is ready. | JAVV lost the connection to the backend. The bell tells you when the file is ready. |
| 52 | no picture | `findings/exportParams.ts` | A schedule cannot use these filters: | An export in the background cannot use these filters: |
| 53 | no picture | `findings/exportParams.ts` | At a past time, a schedule cannot use these filters: | At a past time, an export in the background cannot use these filters: |
| 54 | no picture | `findings/exportParams.ts` | Pick … for the VEX file. | Select … for the VEX file. |
| 55 | [`12-bulk-triage`](12-bulk-triage/ab.png) | `components/triage/BulkTriageBar.vue` | one action, one audit row, for every finding that matches your filters | One change for each finding that matches your filters. The audit log records one row. |
| 56 | [`12-bulk-triage`](12-bulk-triage/ab.png) | `components/triage/BulkTriageBar.vue` | one note on every target | JAVV adds this note to each finding. |
| 57 | [`12-bulk-triage`](12-bulk-triage/ab.png) | `components/triage/BulkTriageBar.vue` | Why this bulk action… | Write why you make this change… |
| 58 | no picture | `components/triage/BulkTriageBar.vue` | Applied to … finding(s), one audit row. | JAVV changed … finding…. The audit log has one row for this change. |
| 59 | no picture | `components/triage/BulkTriageBar.vue` | You may not change the state of these findings. | Your role does not allow you to change the state of these findings. |
| 60 | no picture | `components/triage/BulkTriageBar.vue` | Bulk failed. Check the backend connection. | JAVV did not change the findings. Check the backend connection, then try again. |
| 61 | [`12-bulk-triage`](12-bulk-triage/ab.png) | `findings/bulkSelector.ts` | …. Bulk triage only follows Severity, State, Assignee and Digest, + | …. Bulk triage uses only the Severity, State, Assignee and Digest filters, + |
| 62 | no picture | `findings/bulkSelector.ts` | Pick a single … value. Bulk triage works on exactly one at a time. | Select one … value only. Bulk triage uses one value at a time. |
| 63 | no picture | `components/triage/RiskAcceptDialog.vue` | JAVV did not create the decision. Make sure that the backend is available. | JAVV did not create the decision. Check the backend connection, then try again. |
| 64 | no picture | `findings/savedViews.ts` | No filters: everything | No filters: all findings |
| 65 | no picture | `findings/savedViews.ts` | The store is read-only: its disk is full. JAVV did not delete the view. | The database is read-only because its disk is full. JAVV did not delete the view. |
| 66 | no picture | `findings/savedViews.ts` | The store is busy. JAVV did not delete the view. | The database is busy. JAVV did not delete the view. |
| 67 | no picture | `findings/savedViews.ts` | JAVV did not answer. The view is possibly deleted. Reload the page to see. | JAVV did not answer. JAVV possibly deleted the view. Reload the page to see. |
| 68 | no picture | `findings/savedViews.ts` | JAVV did not delete the view. Check the backend, then try again. | JAVV did not delete the view. Check the backend connection, then try again. |
| 69 | [`13-saved-views`](13-saved-views/ab.png) | `views/SavedViewsView.vue` | fleet-global lenses · counts are live for the selected cluster | All users see these views. The counts are for the selected cluster now. |
| 70 | [`14-saved-views-failed`](14-saved-views-failed/ab.png) | `views/SavedViewsView.vue` | Saved views unavailable. Check the backend, then reload. | JAVV cannot show the saved views. Check the backend connection, then reload the page. |
| 71 | [`15-saved-views-empty`](15-saved-views-empty/ab.png) | `views/SavedViewsView.vue` | Set up Findings the way you want it (filters, columns, density, time window), then use “Save view” to keep it here for everyone. | On Findings, set the filters, the columns, the density and the time range. Then select Save view to keep the view here for all users. |
| 72 | no picture | `views/SavedViewsView.vue` | Custom window | Custom range |
| 73 | no picture | `components/images/DigestSubTimeline.vue` | Not yet scanned then: this T predates …'s first committed scan of this tag. | Not yet scanned then: the first scan of this tag by … is after this time. |
| 74 | no picture | `components/images/DigestSubTimeline.vue` | No committed … scans of this tag yet. | … has no scan of this tag yet. |
| 75 | [`16-image-build-history`](16-image-build-history/ab.png) | `components/images/DigestSubTimeline.vue` | · … run… · | · … scan… · |
| 76 | [`16-image-build-history`](16-image-build-history/ab.png) | `components/images/DigestSubTimeline.vue` | cycles missed | missed scan cycles |
| 77 | [`17-image-findings-failed`](17-image-findings-failed/ab.png) | `components/images/ImageFindingsPanel.vue` | Image findings unavailable. Check the backend connection. | JAVV cannot show the findings of this image. Check the backend connection. |
| 78 | no picture | `components/images/ImagesTable.vue` | No committed trivy scan of this digest | Trivy has no scan of this digest. |
| 79 | no picture | `components/images/ImagesTable.vue` | No committed grype scan of this digest | Grype has no scan of this digest. |
| 80 | no picture | `views/ImageDetailView.vue` | no inventory at this T</template | no inventory at this time</template |
| 81 | [`16-image-build-history`](16-image-build-history/ab.png) | `views/ImageDetailView.vue` | …'s committed scans of this tag · a rebuilt tag is a new digest | The scans of this tag by …. A rebuilt tag has a new digest. |
| 82 | no picture | `views/ImageDetailView.vue` | Build history unavailable. Check the backend connection. | JAVV cannot show the build history. Check the backend connection. |
| 83 | no picture | `views/ImageDetailView.vue` | No committed … scan of this tag exists at or before this T. Reach is bounded by this cluster's retained data. | … has no scan of this tag at or before this time. JAVV keeps the data of this cluster for its retention period only. |
| 84 | [`18-images`](18-images/ab.png) | `views/ImagesView.vue` | inventory as of … · one row for each image digest | The inventory of …. One row for each image digest. |
| 85 | no picture | `views/ImagesView.vue` | the latest committed inventory, per digest | The latest inventory. One row for each image digest. |
| 86 | [`19-images-failed`](19-images-failed/ab.png) | `views/ImagesView.vue` | Inventory unavailable. Check the backend connection. | JAVV cannot show the inventory. Check the backend connection. |
| 87 | no picture | `views/ImagesView.vue` | No inventory committed… | No inventory… |
| 88 | no picture | `views/ImagesView.vue` | Images appear once a scanner cycle completes and certifies its inventory. This T predates the first committed run. | Images show here when a scanner completes a scan cycle and sends its inventory. The selected time is before the first scan. |
| 89 | no picture | `views/ImagesView.vue` | Search images (contains match | Search the images |
