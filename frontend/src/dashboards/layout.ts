/**
 * How a saved dashboard draws (issue 440, rulings Q5 to Q7): pure functions over the stored
 * panels, so the read page and its tests share one placement rule. A panel's `y` and its height
 * count grid rows of 40 px, the rows of the edit grid, so a layout reads the same in both.
 */
import type { DashboardPanel } from '@/api/generated'
import { panelById, type CatalogPanel, type PanelHeight } from '@/dashboards/catalog'
import type { ScannerLens } from '@/lib/scannerLens'
import { silentFor } from '@/system/freshness'

export interface PlacedPanel {
  stored: DashboardPanel
  panel: CatalogPanel
  /** grid rows: the catalog's rows for the stored height name, so a new measurement moves no
   * saved dashboard (decision of 2026-10-25, issue 440) */
  rows: number
}

/** The panels in reading order, `y` then `x`: the order of a narrow screen's one column and of
 * the page for a screen reader. A panel the catalog no longer lists is left out. */
export function placePanels(stored: readonly DashboardPanel[]): PlacedPanel[] {
  const placed: PlacedPanel[] = []
  for (const s of stored) {
    const panel = panelById(s.panel)
    if (!panel) continue
    const height: PanelHeight = s.h in panel.heights ? s.h : (Object.keys(panel.heights)[0] as PanelHeight)
    placed.push({ stored: s, panel, rows: panel.heights[height] ?? 1 })
  }
  return placed.sort((a, b) => a.stored.y - b.stored.y || a.stored.x - b.stored.x)
}

/** CSS custom properties for one grid cell; the read page's stylesheet places it with them,
 * so a narrow screen can drop the columns and keep the height. */
export function cellStyle(p: PlacedPanel): Record<string, string> {
  return {
    '--col': String(p.stored.x + 1),
    '--cols': String(p.stored.w),
    '--row': String(p.stored.y + 1),
    '--rows': String(p.rows),
  }
}

/** The scanner a panel reads: its pinned one, or the dashboard's switch (Q7). */
export function panelScanner(stored: DashboardPanel, switched: ScannerLens): ScannerLens {
  return stored.scanner === 'trivy' || stored.scanner === 'grype' ? stored.scanner : switched
}

export function isPinned(stored: DashboardPanel): boolean {
  return stored.scanner === 'trivy' || stored.scanner === 'grype'
}

export function parseScanner(value: unknown): ScannerLens | null {
  return value === 'all' || value === 'trivy' || value === 'grype' ? value : null
}

/** Who can see a dashboard, in the fewest words: the badge of a card and of the read page. */
export function sharingLine(sharing: string | undefined, roles: readonly string[] | undefined): string {
  if (sharing === 'everyone') return 'Everyone'
  if (sharing === 'roles') return (roles ?? []).join(', ')
  return 'Only the owner'
}

/** "changed 2 hours ago by admin": coarse on purpose, the exact time goes in the tooltip. */
export function changedLine(updatedAt: string | undefined, updatedBy: string | undefined, nowMs = Date.now()): string {
  const at = updatedAt ? Date.parse(updatedAt) : NaN
  if (!Number.isFinite(at)) return ''
  const ago = `changed ${silentFor(Math.max(0, (nowMs - at) / 1000))} ago`
  return updatedBy ? `${ago} by ${updatedBy}` : ago
}
