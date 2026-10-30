/**
 * The dashboard panel catalog (issue 440): the closed list of panels a user can put on a
 * dashboard. Only panels JAVV already ships, and each one gets its own data (DESIGN.md §10), so it
 * renders on a page its author never saw. A saved dashboard names a panel by `id` and the backend
 * checks the same list, so a shipped id never changes.
 */
import type { Component } from 'vue'

import type { ViewPreset } from '@/api/generated'
import ContributorsLens from '@/components/contributors/ContributorsLens.vue'
import ProgressPanel from '@/components/contributors/ProgressPanel.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import FailedIngestsLens from '@/components/dashboards/FailedIngestsLens.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import OverviewNamespacesCard from '@/components/overview/OverviewNamespacesCard.vue'
import OverviewStatBands from '@/components/overview/OverviewStatBands.vue'
import PackageTypeCard from '@/components/overview/PackageTypeCard.vue'
import RiskiestImagesCard from '@/components/overview/RiskiestImagesCard.vue'
import TopComponentsCard from '@/components/overview/TopComponentsCard.vue'
import { daysFromWindow } from '@/contributors/viewModel'
import type { ScannerLens } from '@/lib/scannerLens'

export type PanelGroup = 'Findings' | 'Scanners' | 'People'
export type PanelHeight = 'short' | 'tall'
/** half (1) or all (2) of the dashboard's two columns */
export type PanelWidth = 1 | 2

/** What a dashboard knows when it draws a panel. Each entry turns it into its component's props. */
export interface PanelContext {
  clusterId: string
  /** the rewound T of the app's time picker, null = now */
  t: string | null
  windowDays: number
  scanner: ScannerLens
  height: PanelHeight
  /** the panel's own findings filters (issue 999); only a panel that takes filters gets them */
  filters?: ViewPreset | null
}

export interface CatalogPanel {
  id: string
  name: string
  group: PanelGroup
  /** one line that says what the panel shows */
  line: string
  component: Component
  defaultWidth: PanelWidth
  /** grid rows of 40 px for each height the panel can take, the first one its default. n rows
   * hold n × 40 px less the grid's 2 × 15 px margin. On a dashboard a panel is as tall as its
   * content (issue 1045): the rows are only the first height of a new panel in edit mode. */
  heights: Partial<Record<PanelHeight, number>>
  /** the panel splits its numbers by scanner, so the dashboard's scanner switch applies */
  usesScanner: boolean
  /** the component has no card of its own: the dashboard puts it in PanelFrame */
  framed: boolean
  /** the panel reads findings counts and takes the filters of /findings (issue 999) */
  takesFilters: boolean
  /** the filters it refuses, by API name: Triage progress splits by state itself */
  refusedFilters?: readonly string[]
  props: (ctx: PanelContext) => Record<string, unknown>
}

/** Rows per page of a table panel. Both are page sizes the shared GridPager offers. */
export const TABLE_ROWS: Record<PanelHeight, number> = { short: 10, tall: 25 }

/** The app's global read params at the dashboard's cluster and T (the `withGlobals` shape). */
export function globalQuery(ctx: PanelContext): { cluster_id: string; as_of?: string } {
  return { cluster_id: ctx.clusterId, ...(ctx.t ? { as_of: ctx.t } : {}) }
}

export const PANELS: readonly CatalogPanel[] = [
  {
    id: 'findings-summary',
    name: 'Findings summary',
    group: 'Findings',
    line: 'Findings in each severity, the share with a fix, KEV, scanner disagreement and triage progress.',
    component: OverviewStatBands,
    defaultWidth: 2,
    heights: { short: 7 },
    usesScanner: true,
    framed: false,
    takesFilters: true,
    props: (ctx) => ({ scanner: ctx.scanner, query: globalQuery(ctx), filters: ctx.filters }),
  },
  {
    id: 'package-type',
    name: 'Package type',
    group: 'Findings',
    line: 'The share of findings in each package type: OS packages and each language.',
    component: PackageTypeCard,
    defaultWidth: 1,
    heights: { short: 12 },
    usesScanner: true,
    framed: false,
    takesFilters: true,
    props: (ctx) => ({ scanner: ctx.scanner, query: globalQuery(ctx), filters: ctx.filters }),
  },
  {
    id: 'findings-by-namespace',
    name: 'Findings by namespace',
    group: 'Findings',
    line: 'The namespaces with the most findings.',
    component: OverviewNamespacesCard,
    defaultWidth: 1,
    heights: { short: 11, tall: 24 },
    usesScanner: true,
    framed: false,
    takesFilters: true,
    props: (ctx) => ({
      scanner: ctx.scanner,
      query: globalQuery(ctx),
      limit: TABLE_ROWS[ctx.height],
      filters: ctx.filters,
    }),
  },
  {
    id: 'riskiest-images',
    name: 'Riskiest images',
    group: 'Findings',
    line: 'Running images ranked by their critical and high findings: what to rebuild first.',
    component: RiskiestImagesCard,
    defaultWidth: 1,
    heights: { short: 13, tall: 26 },
    usesScanner: true,
    framed: false,
    takesFilters: false,
    props: (ctx) => ({ scanner: ctx.scanner, pageSize: TABLE_ROWS[ctx.height] }),
  },
  {
    id: 'top-components',
    name: 'Top components',
    group: 'Findings',
    line: 'The packages with the most vulnerabilities: what to upgrade first.',
    component: TopComponentsCard,
    defaultWidth: 1,
    heights: { short: 13, tall: 26 },
    usesScanner: true,
    framed: false,
    takesFilters: true,
    props: (ctx) => ({ scanner: ctx.scanner, pageSize: TABLE_ROWS[ctx.height], filters: ctx.filters }),
  },
  {
    id: 'scan-ingest',
    name: 'Scan ingest',
    group: 'Scanners',
    line: 'Scan runs that reached JAVV in the time range, per scanner, and the last one.',
    component: IngestLens,
    defaultWidth: 2,
    heights: { short: 4 },
    usesScanner: false,
    framed: false,
    takesFilters: false,
    props: (ctx) => ({ clusterId: ctx.clusterId, subject: 'this dashboard' }),
  },
  {
    id: 'failed-ingests',
    name: 'Failed ingests',
    group: 'Scanners',
    line: 'Scan reports that JAVV refused in the time range, per scanner.',
    component: FailedIngestsLens,
    defaultWidth: 1,
    heights: { short: 4 },
    usesScanner: false,
    framed: false,
    takesFilters: false,
    props: (ctx) => ({ clusterId: ctx.clusterId, t: ctx.t, windowDays: ctx.windowDays }),
  },
  {
    id: 'triage-activity',
    name: 'Triage activity',
    group: 'People',
    line: 'Triage changes that people made in the time range: finding states and decisions.',
    component: AuditLens,
    defaultWidth: 2,
    heights: { short: 5 },
    usesScanner: false,
    framed: false,
    takesFilters: false,
    props: (ctx) => ({
      // a risk accept or a not-affected decision is a decision row; a state change is a finding row
      query: { ...globalQuery(ctx), entity_type: ['finding', 'decision'] },
      title: 'Triage activity',
      sub: 'finding states and decisions that people changed',
      emptyNote: 'Nobody changed a finding in this range.',
    }),
  },
  {
    id: 'handled-findings',
    name: 'Handled findings',
    group: 'People',
    line: 'Findings that people resolved, marked not affected, accepted or acknowledged, per day.',
    component: ContributorsLens,
    defaultWidth: 2,
    heights: { short: 5 },
    usesScanner: false,
    framed: false,
    takesFilters: false,
    props: (ctx) => ({ query: { ...globalQuery(ctx), days: daysFromWindow(ctx.windowDays) } }),
  },
  {
    id: 'triage-progress',
    name: 'Triage progress',
    group: 'People',
    line: 'For each severity, how many findings people have triaged.',
    component: ProgressPanel,
    defaultWidth: 1,
    heights: { short: 10 },
    usesScanner: false,
    framed: true,
    takesFilters: true,
    refusedFilters: ['state'],
    props: (ctx) => ({ query: globalQuery(ctx), filters: ctx.filters }),
  },
]

export function panelById(id: string): CatalogPanel | undefined {
  return PANELS.find((p) => p.id === id)
}

/** The heights a panel can take, its default first. */
export function heightsOf(panel: CatalogPanel): PanelHeight[] {
  return Object.keys(panel.heights) as PanelHeight[]
}
