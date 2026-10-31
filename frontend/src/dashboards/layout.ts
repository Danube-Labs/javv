/**
 * How a saved dashboard draws (issue 440, rulings Q5 to Q7): pure functions over the stored
 * panels, so the read page and its tests share one placement rule. A panel's `y` and its height
 * count grid rows of 40 px, the rows of the edit grid, so a layout reads the same in both.
 */
import type { DashboardPanel } from '@/api/generated'
import { panelById, type CatalogPanel, type PanelContext, type PanelHeight } from '@/dashboards/catalog'
import { panelFiltersAt } from '@/dashboards/panelFilters'
import { roleLabel } from '@/lib/roleLabel'
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
  const placed = stored.map(placeOne).filter((p): p is PlacedPanel => p !== null)
  return placed.sort((a, b) => a.stored.y - b.stored.y || a.stored.x - b.stored.x)
}

export function placeOne<T extends DashboardPanel>(s: T): (PlacedPanel & { stored: T }) | null {
  const panel = panelById(s.panel)
  if (!panel) return null
  const height: PanelHeight = s.h in panel.heights ? s.h : (Object.keys(panel.heights)[0] as PanelHeight)
  return { stored: s, panel, rows: panel.heights[height] ?? 1 }
}

/** A part of the read page: a Full panel by itself (one column), or the Half panels between two
 * Full ones (two columns, each from the top down). */
export interface PageBlock {
  full: boolean
  columns: PlacedPanel[][]
}

/** The read page in blocks. Each panel is as tall as its content, so the stored `y` gives only the
 * order: in the edit grid a Full panel never shares a row with a Half one, so it closes the block of
 * Half panels above it. The page and a screen reader read block by block, the left column first. */
export function pageBlocks(placed: readonly PlacedPanel[]): PageBlock[] {
  const blocks: PageBlock[] = []
  let open: PageBlock | null = null
  for (const p of placed) {
    if (p.stored.w >= 2) {
      blocks.push({ full: true, columns: [[p]] })
      open = null
      continue
    }
    if (!open) {
      open = { full: false, columns: [[], []] }
      blocks.push(open)
    }
    open.columns[p.stored.x >= 1 ? 1 : 0]!.push(p)
  }
  return blocks
}

/** The scanner a panel reads: its pinned one, or the dashboard's switch (Q7). */
export function panelScanner(stored: Pick<DashboardPanel, 'scanner'>, switched: ScannerLens): ScannerLens {
  return stored.scanner === 'trivy' || stored.scanner === 'grype' ? stored.scanner : switched
}

/** The scanner a panel counts, which the Add filter menu of its settings counts too: a panel
 * without scanner data counts every scanner. */
export function countedScanner(
  panel: Pick<CatalogPanel, 'usesScanner'>,
  stored: Pick<DashboardPanel, 'scanner'>,
  switched: ScannerLens,
): ScannerLens {
  return panel.usesScanner ? panelScanner(stored, switched) : 'all'
}

export function isPinned(stored: DashboardPanel): boolean {
  return stored.scanner === 'trivy' || stored.scanner === 'grype'
}

/** What a dashboard draws its panels with, before each panel's own scanner and height. */
export type DashboardContext = Omit<PanelContext, 'scanner' | 'height'> & { scanner: ScannerLens }

/** The props of each panel, by a key for its place on the page. A panel that watches its query
 * deeply fetches again on a new query object, even an equal one, so a panel keeps its props
 * object while the inputs it reads stay the same: the scanner switch reaches only the panels
 * that follow it. */
export function panelPropsCache() {
  const cache = new Map<string, { key: string; props: Record<string, unknown> }>()
  return (place: string, p: PlacedPanel, dash: DashboardContext): Record<string, unknown> => {
    const ctx: PanelContext = {
      clusterId: dash.clusterId,
      t: dash.t,
      windowDays: dash.windowDays,
      scanner: countedScanner(p.panel, p.stored, dash.scanner),
      height: p.stored.h,
      filters: p.panel.takesFilters ? panelFiltersAt(p.stored.filters, dash.windowDays) : null,
    }
    const key = `${p.panel.id}|${JSON.stringify(ctx)}`
    const kept = cache.get(place)
    if (kept?.key === key) return kept.props
    const fresh = p.panel.props(ctx)
    cache.set(place, { key, props: fresh })
    return fresh
  }
}

export function parseScanner(value: unknown): ScannerLens | null {
  return value === 'all' || value === 'trivy' || value === 'grype' ? value : null
}

/** Who can see a dashboard, in the fewest words: the badge of a card and of the read page. Role
 * ids show as words (security_lead reads "security lead"), as in the user menu. */
export function sharingLine(sharing: string | undefined, roles: readonly string[] | undefined): string {
  if (sharing === 'everyone') return 'Everyone'
  if (sharing === 'roles') return (roles ?? []).map(roleLabel).join(', ')
  return 'Only the owner'
}

/** "changed 2 hours ago by admin": coarse on purpose, the exact time goes in the tooltip. */
export function changedLine(updatedAt: string | undefined, updatedBy: string | undefined, nowMs = Date.now()): string {
  const at = updatedAt ? Date.parse(updatedAt) : NaN
  if (!Number.isFinite(at)) return ''
  const ago = `changed ${silentFor(Math.max(0, (nowMs - at) / 1000))} ago`
  return updatedBy ? `${ago} by ${updatedBy}` : ago
}
