/** Which component renders each guide section; the layouts look a section up here by id. */
import type { Component } from 'vue'

import type { GuideSectionId } from '@/about/guide'

import DashboardsSection from './DashboardsSection.vue'
import GlossarySection from './GlossarySection.vue'
import ImagesSection from './ImagesSection.vue'
import McpSection from './McpSection.vue'
import NowVsNewSection from './NowVsNewSection.vue'
import SavedViewsSection from './SavedViewsSection.vue'
import ScansSection from './ScansSection.vue'
import StateOrAcceptanceSection from './StateOrAcceptanceSection.vue'
import TimeRangeSection from './TimeRangeSection.vue'
import TriageSection from './TriageSection.vue'
import TwoScannersSection from './TwoScannersSection.vue'

export const SECTION_BODY: Record<GuideSectionId, Component> = {
  'time-range': TimeRangeSection,
  'now-vs-new': NowVsNewSection,
  'two-scanners': TwoScannersSection,
  'scans-and-freshness': ScansSection,
  images: ImagesSection,
  triage: TriageSection,
  'state-or-acceptance': StateOrAcceptanceSection,
  'saved-views': SavedViewsSection,
  dashboards: DashboardsSection,
  'ai-agents': McpSection,
  glossary: GlossarySection,
}
