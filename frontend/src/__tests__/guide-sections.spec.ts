/**
 * The Guide's sections (issue 341). Facts the copy states come from the app's own definitions
 * where one exists (filter labels, the states a person can set, the VEX reasons), so these
 * tests pin that the sections render those, plus the list-level rules: every section in the
 * table of contents has a body, ids are unique, and no copy carries an em dash.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { GUIDE_SECTIONS } from '@/about/guide'
import ContributorsSection from '@/components/about/guide/ContributorsSection.vue'
import DashboardsSection from '@/components/about/guide/DashboardsSection.vue'
import ExportsSection from '@/components/about/guide/ExportsSection.vue'
import InspectorSection from '@/components/about/guide/InspectorSection.vue'
import { ACTION_LABELS } from '@/audit/actionLabels'
import McpSection from '@/components/about/guide/McpSection.vue'
import NowVsNewSection from '@/components/about/guide/NowVsNewSection.vue'
import SavedViewsSection from '@/components/about/guide/SavedViewsSection.vue'
import { SECTION_BODY } from '@/components/about/guide/sections'
import StateOrAcceptanceSection from '@/components/about/guide/StateOrAcceptanceSection.vue'
import TimeRangeSection from '@/components/about/guide/TimeRangeSection.vue'
import TriageSection from '@/components/about/guide/TriageSection.vue'
import TwoScannersSection from '@/components/about/guide/TwoScannersSection.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { PANEL_SCANNER_OPTS } from '@/dashboards/edit'
import { CISA_JUSTIFICATIONS, PANEL_TARGETS } from '@/findings/triageRules'
import { endpointUrl, MCP_LEVELS } from '@/views/settings/mcpTokensForm'

const read = (path: string) => readFileSync(join(__dirname, '..', path), 'utf8')

describe('GUIDE_SECTIONS', () => {
  it('has unique ids', () => {
    const ids = GUIDE_SECTIONS.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('gives every section a body', () => {
    expect(GUIDE_SECTIONS.filter((s) => SECTION_BODY[s.id] === undefined)).toEqual([])
  })

  it('has no em dashes in titles or summaries', () => {
    for (const s of GUIDE_SECTIONS) expect(`${s.title} ${s.summary}`).not.toContain('—')
  })
})

describe('the voice of the Guide (issue 1142)', () => {
  // the reader is "you": no first person, and no reader named in the third person. Other people
  // stay where they are the data of a screen, for example the users that a token cannot change.
  // (case-sensitive past the first letter: "the User column" names a column, not the reader)
  const NOT_THE_READER = /\b([Ww]e|[Oo]ur|[Uu]s|I|[Aa] user|[Tt]he user|[Aa]n admin|[Aa]dmins|[Aa] person)\b/

  it('titles and summaries name the reader as you', () => {
    for (const s of GUIDE_SECTIONS) expect(`${s.title} ${s.summary}`).not.toMatch(NOT_THE_READER)
  })

  it.each(GUIDE_SECTIONS.map((s) => [s.id]))('%s names the reader as you', (id) => {
    expect(mount(SECTION_BODY[id as keyof typeof SECTION_BODY]).text()).not.toMatch(NOT_THE_READER)
  })
})

describe('section bodies', () => {
  it.each(GUIDE_SECTIONS.map((s) => [s.id]))('%s renders text with no em dash', (id) => {
    const text = mount(SECTION_BODY[id as keyof typeof SECTION_BODY]).text()
    expect(text.length).toBeGreaterThan(0)
    expect(text).not.toContain('—')
  })

  it('Now vs new names the New in range filter by its live label', () => {
    const flags = FINDINGS_FIELDS.find((f) => f.type === 'flags')!
    const label = flags.type === 'flags' ? flags.values.find((v) => v.key === 'new')!.label : ''
    expect(mount(NowVsNewSection).find('.ui-name').text()).toBe(label)
  })

  it('Two scanners shows both scanner tags', () => {
    const tags = mount(TwoScannersSection).findAll('.scanner-tag').map((t) => t.text())
    expect(tags).toEqual(['trivy', 'grype'])
  })

  it('Trivy and Grype: the title and the text say what All scanners counts (issue 1140, R4)', () => {
    expect(GUIDE_SECTIONS.find((g) => g.id === 'two-scanners')!.title).toBe('Trivy and Grype side by side')
    const text = mount(TwoScannersSection).text()
    expect(text).toContain('All scanners shows Trivy and Grype together: a CVE that both report counts once for each.')
    expect(text).not.toContain('never added together')
    expect(GUIDE_SECTIONS.map((g) => `${g.title} ${g.summary}`).join(' ')).not.toContain('never merged')
  })

  it('The time range names the Approval list by its menu name', () => {
    const names = mount(TimeRangeSection).findAll('.ui-name').map((n) => n.text())
    expect(names).toContain('Approval list')
    expect(mount(TimeRangeSection).text()).not.toContain('approvals queue')
  })

  it('Two scanners says that JAVV counts findings, not the entries of a scanner report', () => {
    const text = mount(TwoScannersSection).find('.count-unit').text()
    expect(text).toContain('JAVV counts findings.')
    expect(text).toContain('one time for each file that holds the package')
  })

  it('Triage shows six states: the ones a person sets, risk accepted, and stale', () => {
    const w = mount(TriageSection)
    const states = w.findAll('.state-tag').map((t) => t.text())
    expect(states).toHaveLength(6)
    const personLabels = w.findAll('.state-row .state-tag').map((t) => t.text())
    expect(personLabels).toHaveLength(PANEL_TARGETS.length)
    expect(states).toContain('Risk accepted')
    expect(states).toContain('Stale')
  })

  it('Triage lists the five VEX reasons from the triage rules', () => {
    const reasons = mount(TriageSection).findAll('.reasons li').map((li) => li.text())
    expect(reasons).toHaveLength(CISA_JUSTIFICATIONS.length)
    CISA_JUSTIFICATIONS.forEach((j, i) => expect(reasons[i]).toContain(j.label))
  })
  it('A state or a risk acceptance shows the states a person sets, from the triage rules', () => {
    const w = mount(StateOrAcceptanceSection)
    expect(w.findAll('.state-row .state-tag')).toHaveLength(PANEL_TARGETS.length)
    expect(w.text()).toContain('Risk accepted')
  })

  it('A state or a risk acceptance says what the Approval list is, with two numbered examples', () => {
    const w = mount(StateOrAcceptanceSection)
    expect(w.text()).toContain('No item on the Approval list waits for approval.')
    expect(w.text()).toContain('Those are states, not risk acceptances.')
    expect(w.findAll('ol')).toHaveLength(2)
    expect(w.text()).toContain(`for example ${CISA_JUSTIFICATIONS[0].label}`)
  })

  it('A state or a risk acceptance has no semicolon (Simplified Technical English)', () => {
    expect(mount(StateOrAcceptanceSection).text()).not.toContain(';')
  })

  it('AI agents gives each level in the words of the Settings section', () => {
    const items = mount(McpSection).findAll('.levels li').map((li) => li.text())
    MCP_LEVELS.forEach((level, i) => expect(items[i]).toBe(`${level.label}. ${level.note}`))
  })

  it('AI agents names the tool call row by the action name of the Audit log', () => {
    const names = mount(McpSection).findAll('.ui-name').map((n) => n.text())
    expect(names).toContain(ACTION_LABELS.mcp_tool_call)
  })

  it('AI agents gives the URL of this JAVV in the copy box of the Settings section', () => {
    const w = mount(McpSection)
    expect(w.find('.copy-box').text()).toBe(endpointUrl(window.location.origin))
    expect(w.find('button[aria-label="Copy the URL"]').exists()).toBe(true)
  })

  it('AI agents links the docs page and has no semicolon (Simplified Technical English)', () => {
    const w = mount(McpSection)
    expect(w.find('a.docs-link').attributes('href')).toMatch(/\/docs\/use\/use-the-mcp-server\.md$/)
    expect(w.text()).not.toContain(';')
  })

  it('Saved views says what a view keeps, who deletes it, and what its count is (issue 1142)', () => {
    const w = mount(SavedViewsSection)
    expect(w.text()).toContain('the filters, the columns, the row density, the sort and the time window')
    expect(w.text()).toContain('It does not keep the cluster.')
    expect(w.text()).toContain('The admin role can delete each view.')
    expect(w.text()).toContain('To change a view, delete it and save it again.')
    expect(w.find('.view-count').text()).toContain('in the selected cluster, at the end of the time range')
    expect(read('components/findings/SaveViewDialog.vue')).toContain('>Save view</UiButton>')
  })

  it('Dashboards gives the words of the panel scanner setting and links Build a dashboard (issue 1142)', () => {
    const w = mount(DashboardsSection)
    expect(w.find('.panel-scanner .ui-name').text()).toBe(PANEL_SCANNER_OPTS[0].label)
    expect(w.find('a.docs-link').attributes('href')).toMatch(/\/docs\/use\/build-a-dashboard\.md$/)
    expect(w.text()).toContain('Only the owner and the admin role can change it.')
    expect(w.text()).not.toContain(';')
  })

  it('Contributors names the four handled actions by the action names of the Audit log (issue 1142)', () => {
    const text = mount(ContributorsSection).find('.handled').text()
    const names = (['acknowledge', 'not_affected', 'risk_accept', 'resolve'] as const).map((a) => ACTION_LABELS[a])
    expect(text).toBe(`Handled counts these actions: ${names.slice(0, -1).join(', ')} and ${names.at(-1)}.`)
    expect(mount(ContributorsSection).text()).toContain('The table shows at most 100 people.')
  })

  it('Exports gives the tab names of the export window, the two defaults and the VEX rule (issue 1142)', () => {
    const w = mount(ExportsSection)
    const names = w.findAll('.ui-name').map((n) => n.text())
    expect(names).toEqual(expect.arrayContaining(['Run now', 'In the background']))
    const dialog = read('components/findings/ExportDialog.vue')
    expect(dialog).toContain("label: 'Run now'")
    expect(dialog).toContain("label: 'In the background'")
    expect(w.text()).toContain('50,000 rows by default')
    expect(w.text()).toContain('24 hours by default')
    expect(w.text()).toContain('A VEX file holds the findings of one scanner.')
    expect(w.text()).not.toContain(';')
  })

  it('Data inspector names the three repair jobs of the job card and the admin role (issue 1142)', () => {
    const w = mount(InspectorSection)
    const card = read('components/system/RepairActionsCard.vue')
    for (const job of ['Rebuild state', 'Staleness sweep', 'Lifecycle sweep']) {
      expect(w.find('.repair-jobs').text()).toContain(job)
      expect(card).toContain(`'${job}'`)
    }
    expect(w.text()).toContain('you need the admin role')
    expect(w.text()).not.toContain(';')
  })
})
