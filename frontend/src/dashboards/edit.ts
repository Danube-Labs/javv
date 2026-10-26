/**
 * Edit mode of a dashboard (issue 440, S8): pure rules over the stored panels, so the page and
 * its tests share them. gridstack moves the panels on screen; these functions decide who may
 * change a dashboard, what a save sends and what a failed save says.
 */
import type { DashboardPanel } from '@/api/generated'
import type { PanelHeight, PanelWidth } from '@/dashboards/catalog'
import { placeOne } from '@/dashboards/layout'

/** The backend's cap on the panels of one dashboard (MAX_PANELS, ruling Q2, docs/API.md). */
export const MAX_PANELS = 24
export const PANEL_CAP_NOTE = `A dashboard holds at most ${MAX_PANELS} panels.`

/** A panel in edit mode: the stored panel and a key that stays the same while it moves. */
export interface DraftPanel extends DashboardPanel {
  key: string
}

/** Where gridstack put a panel. */
export interface PanelPlace {
  key: string
  x: number
  y: number
}

/** The draft with the places gridstack gave; a place for a key the draft does not have is
 * ignored. */
export function withPlaces(draft: readonly DraftPanel[], places: readonly PanelPlace[]): DraftPanel[] {
  const at = new Map(places.map((p) => [p.key, p]))
  return draft.map((p) => {
    const place = at.get(p.key)
    return place ? { ...p, x: place.x, y: place.y } : p
  })
}

export type PanelScannerChoice = 'dashboard' | 'trivy' | 'grype'

/** The settings of one panel, in the panel settings and in the catalog window. */
export const PANEL_SCANNER_OPTS = [
  { value: 'dashboard', label: 'Follow the dashboard' },
  { value: 'trivy', label: 'trivy', accent: 'var(--scanner-trivy-fg)' },
  { value: 'grype', label: 'grype', accent: 'var(--scanner-grype-fg)' },
] as const
export const WIDTH_OPTS = [
  { value: 'half', label: 'Half' },
  { value: 'full', label: 'Full' },
] as const
export type WidthChoice = (typeof WIDTH_OPTS)[number]['value']
export const widthChoice = (w: PanelWidth): WidthChoice => (w === 2 ? 'full' : 'half')
export const widthOf = (choice: WidthChoice): PanelWidth => (choice === 'full' ? 2 : 1)
export const HEIGHT_OPTS = [
  { value: 'short', label: 'Short' },
  { value: 'tall', label: 'Tall' },
] as const

/** What the scanner setting does, in one sentence under it. */
export function scannerHelp(choice: PanelScannerChoice, dashboard: 'all' | 'trivy' | 'grype'): string {
  if (choice !== 'dashboard') return `The panel always shows ${choice}. The dashboard switch does not change it.`
  return `The panel shows what the dashboard switch shows: now ${dashboard === 'all' ? 'all scanners' : dashboard}.`
}

export interface PanelSettings {
  w: PanelWidth
  h: PanelHeight
  scanner: PanelScannerChoice | null
}

let nextKey = 0
export function draftKey(): string {
  return `p${++nextKey}`
}

export function toDraft(panels: readonly DashboardPanel[]): DraftPanel[] {
  return panels.map((p) => ({ ...p, key: draftKey() }))
}

export function fromDraft(draft: readonly DraftPanel[]): DashboardPanel[] {
  return draft.map(({ key: _key, ...p }) => p)
}

const panelSig = (p: DashboardPanel) => `${p.panel}|${p.x}|${p.y}|${p.w}|${p.h}|${p.scanner ?? ''}`

/** The same panels in the same places, in any order: a save then leaves out `panels`, so the
 * backend keeps the stored ones without checking them again (PR B). */
export function sameLayout(a: readonly DashboardPanel[], b: readonly DashboardPanel[]): boolean {
  if (a.length !== b.length) return false
  const sigs = b.map(panelSig).sort()
  return a
    .map(panelSig)
    .sort()
    .every((s, i) => s === sigs[i])
}

/** A panel from the catalog window, at the left edge under all the others (the kickoff of S8b). */
export function addedPanel(
  draft: readonly DraftPanel[],
  choice: { panel: DashboardPanel['panel'] } & PanelSettings,
): DraftPanel {
  const bottom = Math.max(0, ...draft.map((p) => p.y + (placeOne(p)?.rows ?? 0)))
  return {
    key: draftKey(),
    panel: choice.panel,
    x: 0,
    y: bottom,
    w: choice.w,
    h: choice.h,
    ...(choice.scanner ? { scanner: choice.scanner } : {}),
  }
}

/** A full-width panel starts at the left edge; a half-width one keeps its column. */
export function withSettings(p: DraftPanel, s: PanelSettings): DraftPanel {
  return { ...p, w: s.w, h: s.h, x: s.w === 2 ? 0 : p.x, ...(s.scanner ? { scanner: s.scanner } : {}) }
}

export const NO_EDIT_NOTE = 'Only the owner or an admin can change this dashboard.'
export const NO_EDIT_ROLE_NOTE = 'Your role cannot change dashboards.'

/** Why this user cannot change the dashboard, or null if they can: the backend's rule (D3), a
 * write needs `can_edit_dashboards`, and another user's dashboard also `can_manage_settings`. */
export function editRefusal(
  username: string | undefined,
  can: (capability: string) => boolean,
  owner: string,
): string | null {
  if (!can('can_edit_dashboards')) return NO_EDIT_ROLE_NOTE
  if (username !== owner && !can('can_manage_settings')) return NO_EDIT_NOTE
  return null
}

/** The toast of a save that the backend did not take. A lost answer can come after the save
 * was done, so it does not say that nothing changed. */
export function saveFailureCopy(status: number, readOnly: boolean): string {
  if (readOnly) return 'The store is read-only: its disk is full. JAVV did not save the dashboard.'
  if (status === 403) return `${NO_EDIT_NOTE} JAVV did not save your changes.`
  if (status === 404) return 'Somebody removed this dashboard. JAVV did not save your changes.'
  if (status === 409)
    return 'Somebody changed this dashboard after you opened it. JAVV did not save your changes. Reload the page to see the dashboard as it is now.'
  if (status === 422) return 'JAVV cannot use a value of this dashboard. JAVV did not save your changes.'
  if (status === 429) return 'The store is busy. JAVV did not save your changes. Try again in a few seconds.'
  if (status === 0 || status === 504)
    return 'JAVV did not answer. Your changes are possibly saved. Reload the page to see the dashboard as it is now.'
  return 'JAVV did not save your changes. Check the backend, then try again.'
}
