/**
 * The settings sub-nav registry (SCREENS §13): one row per section — sub-route, icon,
 * capability gate (the section is HIDDEN from the sub-nav without it, A-4; the router guard
 * reroutes direct hits) and the scope marker saying what blast radius an edit has.
 */
import type { IconName } from '@/components/ui/AppIcon.vue'

export type SettingsScope = 'cluster' | 'scanner' | 'org'

export interface SettingsSection {
  key: string // path segment under /settings
  label: string
  icon: IconName
  scope: SettingsScope
  capability: string
}

export const SCOPE_COPY: Record<SettingsScope, { label: string; note: string }> = {
  cluster: {
    label: 'Per cluster',
    note: 'Applies to the selected cluster only. Other clusters keep their own settings.',
  },
  scanner: {
    label: 'Per scanner',
    note: 'Shown for each scanner, Trivy and Grype, on its own.',
  },
  org: {
    label: 'Organization',
    note: 'Shared across every cluster and user.',
  },
}

// §13 section order (13.1 → 13.8). Ignore rules (13.4) has NO entry by operator ruling
// (2026-07-15): decisions live on /approvals + finding detail — a settings pointer earns nothing.
export const SETTINGS_SECTIONS: SettingsSection[] = [
  { key: 'scan-scope', label: 'Scan scope', icon: 'filter', scope: 'cluster', capability: 'can_manage_settings' },
  { key: 'scanning', label: 'Scanning', icon: 'shield', scope: 'scanner', capability: 'can_manage_settings' },
  { key: 'sla', label: 'SLA policy', icon: 'alert', scope: 'org', capability: 'can_manage_settings' },
  { key: 'tokens', label: 'Access & tokens', icon: 'key', scope: 'org', capability: 'can_manage_tokens' },
  { key: 'ai-agents', label: 'AI agents (MCP)', icon: 'cpu', scope: 'org', capability: 'can_manage_tokens' },
  { key: 'users', label: 'Users & roles', icon: 'users', scope: 'org', capability: 'can_manage_users' },
  { key: 'data-opensearch', label: 'Data & OpenSearch', icon: 'database', scope: 'cluster', capability: 'can_manage_retention' },
  { key: 'cluster', label: 'Cluster', icon: 'gear', scope: 'cluster', capability: 'can_manage_settings' },
]
