/**
 * The backend keeps its own copy of the panel catalog (`backend/src/backend/dashboards/catalog.py`)
 * to check a saved dashboard: the panel ids, the heights each panel can take with their grid rows,
 * and which panels have scanner data. A copy that drifts refuses a dashboard the page lets a user
 * build, or lets two panels share a cell (issue 440).
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { PANELS, panelById } from '@/dashboards/catalog'

const CATALOG_PY = resolve(process.cwd(), '..', 'backend/src/backend/dashboards/catalog.py')

interface BackendPanel {
  heights: Record<string, number>
  usesScanner: boolean
}

/** the entries of PANELS in catalog.py, one per line: "id": CatalogPanel({...}, uses_scanner=X) */
function backendPanels(): Map<string, BackendPanel> {
  const text = readFileSync(CATALOG_PY, 'utf8')
  const panels = new Map<string, BackendPanel>()
  const entry = /^\s+"([\w-]+)": CatalogPanel\(\{([^}]*)\}, uses_scanner=(True|False)\),$/gm
  for (const m of text.matchAll(entry)) {
    const heights: Record<string, number> = {}
    for (const h of m[2]!.matchAll(/"(\w+)": (\d+)/g)) heights[h[1]!] = Number(h[2])
    panels.set(m[1]!, { heights, usesScanner: m[3] === 'True' })
  }
  return panels
}

function apiPanelIds(): string[] {
  const openapi = JSON.parse(readFileSync(resolve(process.cwd(), 'openapi.json'), 'utf8'))
  return openapi.components.schemas.DashboardPanel.properties.panel.enum
}

describe('the backend copy of the panel catalog', () => {
  const backend = backendPanels()

  it('the reader finds every entry of catalog.py', () => {
    expect(backend.size).toBe(PANELS.length)
    expect(backend.get('findings-by-namespace')).toEqual({
      heights: { short: 11, tall: 24 },
      usesScanner: true,
    })
  })

  it('the API takes the panel ids of the catalog, in its order', () => {
    expect(apiPanelIds()).toEqual(PANELS.map((p) => p.id))
    expect([...backend.keys()]).toEqual(PANELS.map((p) => p.id))
  })

  /** one value per panel id, so a failure names the panel */
  function byId<T>(pick: (id: string) => T): Record<string, T> {
    return Object.fromEntries(PANELS.map((p) => [p.id, pick(p.id)]))
  }

  it('each panel has the same heights and rows on both sides', () => {
    expect(byId((id) => backend.get(id)?.heights)).toEqual(byId((id) => panelById(id)?.heights))
  })

  it('each panel has scanner data on both sides or on neither', () => {
    expect(byId((id) => backend.get(id)?.usesScanner)).toEqual(
      byId((id) => panelById(id)?.usesScanner),
    )
  })
})
