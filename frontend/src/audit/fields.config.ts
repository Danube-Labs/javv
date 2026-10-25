/**
 * Audit screen filter config (M9d slice 1) — same shape/grammar as FINDINGS_FIELDS, driving
 * FacetRail + FilterBar through the shared module. Each field takes several values (issue 952):
 * `entity_type`/`action`/`actor` are lists on GET /api/v1/audit, at most MAX_FILTER_VALUES;
 * counts come live from GET /api/v1/audit/facets (M9d rework — the rail shows the current lens's
 * numbers, server-side). entity/action keep their static D32 vocabularies (writer call sites)
 * so quiet values still list; actor is data-driven from the facet buckets.
 */
import { actionLabel } from '@/audit/actionLabels'
import type { FilterField } from '@/filters/fields.config'

/** entity_type vocabulary (D32): what kind of record the event touched. */
export const AUDIT_ENTITY_TYPES = [
  'finding',
  'decision',
  'view',
  'dashboard',
  'config',
  'token',
  'user',
  'store',
  'job',
] as const

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
  // dashboards
  'dashboard_create',
  'dashboard_update',
  'dashboard_delete',
  // config
  'sla_policy_change',
  'cluster_rename',
  'cluster_retire',
  'cluster_unretire',
  'cluster_delete',
  'cluster_delete_recheck',
  // settings (entity_type=config)
  'retention_change',
  'findings_cleanup_change',
  'report_ttl_change',
  'rollover_change',
  'retirement_window_change',
  'scan_scope_change',
  'staleness_timers_change',
  // snapshots and job runs (entity_type=config/job)
  'snapshot_taken',
  'snapshot_restored',
  'findings_cleanup_run',
  'session_sweep_run',
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

/** The most buckets the server gives for Entity and Action: backend `query/audit._AUDIT_LIST_TERMS_SIZE`,
 * a fixed size in docs/CONFIGURATION.md ("Fixed aggregation sizes"). It is larger than the
 * Action list, so each action gets a count (issue 983). */
export const AUDIT_LIST_CAP = 64

export const AUDIT_FIELDS: readonly FilterField[] = [
  { key: 'entity', label: 'Entity', type: 'terms', param: 'entity_type', multi: true, facetKey: 'entity_type', facetCap: AUDIT_LIST_CAP, values: AUDIT_ENTITY_TYPES, negatable: true },
  { key: 'action', label: 'Action', type: 'terms', param: 'action', multi: true, facetKey: 'action', facetCap: AUDIT_LIST_CAP, values: AUDIT_ACTIONS, negatable: true, valueLabel: actionLabel },
  // data-driven from the facet buckets; the backend counts users without the user filter, so a
  // picked user does not hide the others (issue 952)
  { key: 'actor', label: 'User', type: 'terms', param: 'actor', multi: true, facetKey: 'actor', negatable: true },
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

/** The rows of the saved dashboards (entity_type `dashboard`) and their actions. */
export const DASHBOARD_ENTITY_TYPES = ['dashboard'] as const
export const DASHBOARD_ACTIONS = ['dashboard_create', 'dashboard_update', 'dashboard_delete'] as const

/**
 * The rail for this user (issue 892, ruling 8): the server leaves the account rows out without
 * can_manage_users, and the dashboard rows without can_manage_settings (issue 440), so their
 * entity values and actions would only ever count 0. The keys stay those of AUDIT_FIELDS, so
 * selections, the URL and saved views do not change.
 */
export function auditFields(canManageUsers: boolean, canManageSettings: boolean): readonly FilterField[] {
  if (canManageUsers && canManageSettings) return AUDIT_FIELDS
  const hidden = new Set<string>([
    ...(canManageUsers ? [] : [...ACCOUNT_ENTITY_TYPES, ...ACCOUNT_ACTIONS]),
    ...(canManageSettings ? [] : [...DASHBOARD_ENTITY_TYPES, ...DASHBOARD_ACTIONS]),
  ])
  return AUDIT_FIELDS.map((f) =>
    f.type === 'terms' && f.values ? { ...f, values: f.values.filter((v) => !hidden.has(v)) } : f,
  )
}
