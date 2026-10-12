/**
 * What an audit action is CALLED on screen. One map, read by the action tag in the table and
 * by the Action filter rail and pills (issue 674): the rail used to print the stored verb
 * (`risk_accept`) beside a tag that said "Risk accepted".
 */
export const ACTION_LABELS: Record<string, string> = {
  reopen: 'Reopened',
  acknowledge: 'Acknowledged',
  not_affected: 'Not affected',
  risk_accept: 'Risk accepted',
  resolve: 'Resolved',
  assign: 'Assigned',
  note: 'Note',
  bulk_triage: 'Bulk triage',
  decision_create: 'Decision created',
  decision_revoke: 'Decision revoked',
  view_create: 'View created',
  view_update: 'View updated',
  view_delete: 'View deleted',
  sla_policy_change: 'SLA policy',
  cluster_rename: 'Cluster renamed',
  cluster_retire: 'Cluster retired',
  cluster_unretire: 'Cluster un-retired',
  cluster_delete: 'Cluster deleted',
  cluster_delete_recheck: 'Leftover rows deleted',
  pwd_change: 'Password changed',
  pwd_reset: 'Password reset',
  role_change: 'Role changed',
  user_create: 'User created',
  user_enable: 'User enabled',
  user_disable: 'User disabled',
  token_mint: 'Token minted',
  token_revoke: 'Token revoked',
  login: 'Login',
  logout: 'Logout',
}

/** The display name of an action; one with no entry reads as its words, never as snake_case. */
export const actionLabel = (action: string): string => ACTION_LABELS[action] ?? action.replace(/_/g, ' ')
