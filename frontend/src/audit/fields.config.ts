/**
 * Audit screen filter config (M9d slice 1) — same shape/grammar as FINDINGS_FIELDS, driving
 * FacetRail + FilterBar through the shared module. The backend takes ONE term per field
 * (`entity_type`/`action`/`actor` on GET /api/v1/audit), so nothing here is `multi`; counts
 * come live from GET /api/v1/audit/facets (M9d rework — the rail shows the current lens's
 * numbers, server-side). entity/action keep their static D32 vocabularies (writer call sites)
 * so quiet values still list; actor is data-driven from the facet buckets.
 */
import { actionLabel } from '@/audit/actionLabels'
import type { FilterField } from '@/filters/fields.config'

/** entity_type vocabulary (D32): what kind of record the event touched. */
export const AUDIT_ENTITY_TYPES = ['finding', 'decision', 'view', 'config', 'token', 'user', 'store', 'job'] as const

/** action vocabulary (FR-7 verbs + auth/admin/config events), grouped triage-first. */
export const AUDIT_ACTIONS = [
  // triage (entity_type=finding)
  'reopen',
  'acknowledge',
  'not_affected',
  'risk_accept',
  'resolve',
  'assign',
  'note',
  'bulk_triage',
  // decisions
  'decision_create',
  'decision_revoke',
  // saved views
  'view_create',
  'view_update',
  'view_delete',
  // config
  'sla_policy_change',
  'cluster_rename',
  'cluster_retire',
  'cluster_unretire',
  'cluster_delete',
  'cluster_delete_recheck',
  // auth + admin (entity_type=user/token)
  'login',
  'logout',
  'pwd_change',
  'pwd_reset',
  'role_change',
  'user_create',
  'user_enable',
  'user_disable',
  'token_mint',
  'token_revoke',
  // data inspector + repair actions (issue 406, entity_type=store/job)
  'store_inspect',
  'job_trigger',
] as const

export const AUDIT_FIELDS: readonly FilterField[] = [
  { key: 'entity', label: 'Entity', type: 'terms', param: 'entity_type', facetKey: 'entity_type', values: AUDIT_ENTITY_TYPES, negatable: true },
  { key: 'action', label: 'Action', type: 'terms', param: 'action', facetKey: 'action', values: AUDIT_ACTIONS, negatable: true, valueLabel: actionLabel },
  // data-driven from the facet buckets (exact keyword term on the backend)
  { key: 'actor', label: 'User', type: 'terms', param: 'actor', facetKey: 'actor', negatable: true },
]

/** The actions of the account rows (entity_type `user` and `token`). */
export const ACCOUNT_ACTIONS = [
  'login',
  'logout',
  'pwd_change',
  'pwd_reset',
  'role_change',
  'user_create',
  'user_enable',
  'user_disable',
  'token_mint',
  'token_revoke',
] as const
const ACCOUNT_ENTITY_TYPES: readonly string[] = ['user', 'token']

/**
 * The rail for this user (issue 892, ruling 8): the server leaves the account rows out without
 * can_manage_users, so their entity values and actions would only ever count 0. The keys stay
 * those of AUDIT_FIELDS, so selections, the URL and saved views do not change.
 */
export function auditFields(canManageUsers: boolean): readonly FilterField[] {
  if (canManageUsers) return AUDIT_FIELDS
  const hidden = new Set<string>([...ACCOUNT_ENTITY_TYPES, ...ACCOUNT_ACTIONS])
  return AUDIT_FIELDS.map((f) =>
    f.type === 'terms' && f.values ? { ...f, values: f.values.filter((v) => !hidden.has(v)) } : f,
  )
}
