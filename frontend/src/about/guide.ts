/**
 * The Guide page's sections (issue 341): one list drives the table of contents, the
 * rendered section ids and every "learn more" link elsewhere in the app. A link takes a
 * `GuideSectionId`, so pointing at a section that doesn't exist fails the type check.
 */
import type { IconName } from '@/components/ui/AppIcon.vue'

export interface GuideSection {
  id: string
  title: string
  summary: string
  icon: IconName
}

export const GUIDE_SECTIONS = [
  {
    id: 'time-range',
    title: 'The time range',
    summary: 'Tables show the state at the end of the range; charts show what happened inside it.',
    icon: 'clock',
  },
  {
    id: 'now-vs-new',
    title: 'Now vs new',
    summary: 'What is vulnerable right now, and what arrived in this range.',
    icon: 'pulse',
  },
  {
    id: 'two-scanners',
    title: 'Trivy and Grype side by side',
    summary: 'Each finding belongs to one scanner, and JAVV never picks a winner.',
    icon: 'columns',
  },
  {
    id: 'scans-and-freshness',
    title: 'Scans and freshness',
    summary: 'A scan counts once it is complete; a quiet scanner keeps its last results.',
    icon: 'check',
  },
  {
    id: 'images',
    title: 'Images are digests',
    summary: 'A tag is a pointer; rebuilding a tag makes a new image.',
    icon: 'cube',
  },
  {
    id: 'triage',
    title: 'Triage',
    summary: 'The six states, the reasons behind “not affected”, and how decisions change.',
    icon: 'shield',
  },
  {
    id: 'state-or-acceptance',
    title: 'A state or a risk acceptance',
    summary: 'Two ways to handle a finding, and what the Approval list shows.',
    icon: 'layers',
  },
  {
    id: 'saved-views',
    title: 'Saved views',
    summary: 'What a view keeps, who can delete it, and what its count shows.',
    icon: 'bookmark',
  },
  {
    id: 'dashboards',
    title: 'Dashboards',
    summary: 'The panels, the scanner of each panel, and where to find the steps.',
    icon: 'grid',
  },
  {
    id: 'contributors',
    title: 'Contributors',
    summary: 'Where the numbers come from, and what handled and SLA met count.',
    icon: 'award',
  },
  {
    id: 'exports',
    title: 'Exports',
    summary: 'Run now or in the background, the limits, and the VEX file.',
    icon: 'download',
  },
  {
    id: 'data-inspector',
    title: 'Data inspector',
    summary: 'The two job cards, and who can run a job.',
    icon: 'database',
  },
  {
    id: 'ai-agents',
    title: 'AI agents (MCP)',
    summary: 'What an agent can read and change, how the Audit log names it, and how to connect it.',
    icon: 'cpu',
  },
  {
    id: 'glossary',
    title: 'Glossary',
    summary: 'The short labels in tables and filters.',
    icon: 'list',
  },
] as const satisfies readonly GuideSection[]

export type GuideSectionId = (typeof GUIDE_SECTIONS)[number]['id']

export const guideHref = (id: GuideSectionId): string => `/guide#${id}`
