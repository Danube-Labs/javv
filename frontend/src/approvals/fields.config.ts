/**
 * Approvals screen filter config (M9d slice 4b) — the prototype rail's dims (status,
 * approver, search) + the scanner column's value, all served by GET /decisions/approvals
 * (server-side; the endpoint's facets block feeds the counts). Same grammar as
 * AUDIT_FIELDS: one config drives FacetRail + FilterBar + URL sync. Status and Approver take
 * several values (issue 952); Scanner and the CVE search stay one value, as on Findings.
 */
import type { FilterField } from '@/filters/fields.config'

/** the ExpiryChip vocabulary — status is derived server-side from expiry vs warn_days */
export const APPROVAL_STATUSES = ['expired', 'expiring', 'active', 'open-ended'] as const

export const APPROVAL_FIELDS: readonly FilterField[] = [
  // CVE contains-search (escaped wildcard server-side, the findings-q discipline)
  { key: 'q', label: 'Search', type: 'text', param: 'q', minLength: 2 },
  { key: 'status', label: 'Status', type: 'terms', param: 'status', multi: true, facetKey: 'status', values: APPROVAL_STATUSES, negatable: true },
  { key: 'scanner', label: 'Scanner', type: 'terms', param: 'scanner', facetKey: 'scanner', values: ['both', 'trivy', 'grype'], negatable: true },
  // data-driven from the facet buckets; the backend counts approvers without the approver
  // filter, so a picked approver does not hide the others (issue 952)
  { key: 'approver', label: 'Approver', type: 'terms', param: 'created_by', multi: true, facetKey: 'created_by', negatable: true },
]
