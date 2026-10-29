/**
 * The name, description, sharing and opening scanner of a dashboard (issue 440, S8c). The
 * details window edits them for a new dashboard and in edit mode; in edit mode the save bar
 * saves them with the panels, and a save sends only the fields that changed.
 */
import type { DashboardFields, UpdateDashboard } from '@/api/generated'
import { roleLabel } from '@/lib/roleLabel'
import type { ScannerLens } from '@/lib/scannerLens'

export type Sharing = 'private' | 'everyone' | 'roles'

export interface DashboardDetails {
  name: string
  description: string
  scanner: ScannerLens
  sharing: Sharing
  roles: string[]
}

/** The backend's limits on the two texts (DashboardFields, docs/API.md). */
export const NAME_MAX = 128
export const DESCRIPTION_MAX = 1024

/** Who can see a dashboard (decision D2). */
export const SHARING_OPTS = [
  { value: 'private', label: 'Only me' },
  { value: 'everyone', label: 'Everyone' },
  { value: 'roles', label: 'Some roles' },
] as const

export const NO_NAME_NOTE = 'A dashboard needs a name.'
export const NO_ROLE_NOTE = 'Select a role, or share it with only you or with everyone.'

export const NEW_DETAILS: DashboardDetails = {
  name: '',
  description: '',
  scanner: 'all',
  sharing: 'private',
  roles: [],
}

export function detailsOf(doc: DashboardDetails): DashboardDetails {
  return {
    name: doc.name,
    description: doc.description,
    scanner: doc.scanner,
    sharing: doc.sharing,
    roles: [...doc.roles],
  }
}

/** Why the window cannot apply these details, or null. */
export function detailsProblem(d: DashboardDetails): string | null {
  if (!d.name.trim()) return NO_NAME_NOTE
  if (d.sharing === 'roles' && d.roles.length === 0) return NO_ROLE_NOTE
  return null
}

/** The details as the backend stores them: the texts trimmed, and the roles only with "Some
 * roles", because the backend refuses roles with any other sharing. */
export function normalized(d: DashboardDetails): DashboardDetails {
  return {
    ...d,
    name: d.name.trim(),
    description: d.description.trim(),
    roles: d.sharing === 'roles' ? [...d.roles].sort() : [],
  }
}

/** A role on, or off. */
export function toggled(roles: readonly string[], role: string): string[] {
  return roles.includes(role) ? roles.filter((r) => r !== role) : [...roles, role]
}

/** The fields of `after` that differ from `before`. The sharing and the roles go together, so a
 * change to "Everyone" also clears the roles (docs/API.md). */
export function detailsChange(before: DashboardDetails, after: DashboardDetails): Partial<UpdateDashboard> {
  const a = normalized(before)
  const b = normalized(after)
  const change: Partial<UpdateDashboard> = {}
  if (a.name !== b.name) change.name = b.name
  if (a.description !== b.description) change.description = b.description
  if (a.scanner !== b.scanner) change.scanner = b.scanner
  if (a.sharing !== b.sharing || a.roles.join() !== b.roles.join()) {
    change.sharing = b.sharing
    change.roles = b.roles
  }
  return change
}

export function sameDetails(a: DashboardDetails, b: DashboardDetails): boolean {
  return Object.keys(detailsChange(a, b)).length === 0
}

/** The body of a new dashboard: the details and no panels. */
export function newDashboardBody(d: DashboardDetails): DashboardFields {
  return { ...normalized(d), panels: [] }
}

/** The roles that the window offers: the server's list, and a role of the dashboard that the
 * list does not have, so a saved choice always shows. */
export function roleOptions(listed: readonly string[], chosen: readonly string[]) {
  return [...new Set([...listed, ...chosen])].map((r) => ({ value: r, label: roleLabel(r) }))
}

/** The message of a remove that the backend did not do. */
export function removeFailureCopy(status: number, readOnly: boolean): string {
  if (readOnly) return 'The store is read-only: its disk is full. JAVV did not remove the dashboard.'
  if (status === 403) return 'Only the owner or an admin can remove this dashboard.'
  if (status === 409)
    return 'Somebody changed this dashboard after you opened it. JAVV did not remove it. Reload the page, then try again.'
  if (status === 429) return 'The store is busy. JAVV did not remove the dashboard. Try again in a few seconds.'
  if (status === 0 || status === 504)
    return 'JAVV did not answer. The dashboard is possibly removed. Reload the page to see.'
  return 'JAVV did not remove the dashboard. Check the backend, then try again.'
}

/** The message of a new dashboard that the backend did not make. */
export function createFailureCopy(status: number, readOnly: boolean): string {
  if (readOnly) return 'The store is read-only: its disk is full. JAVV did not make the dashboard.'
  if (status === 403) return 'Your role cannot make dashboards.'
  if (status === 422) return 'JAVV cannot use a value of this dashboard, for example a role that it does not have.'
  if (status === 429) return 'The store is busy. JAVV did not make the dashboard. Try again in a few seconds.'
  if (status === 0 || status === 504)
    return 'JAVV did not answer. The dashboard is possibly made. Close this window and look at the list.'
  return 'JAVV did not make the dashboard. Check the backend, then try again.'
}
