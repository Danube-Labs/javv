/**
 * The Guide's sections (issue 341). Facts the copy states come from the app's own definitions
 * where one exists (filter labels, the states a person can set, the VEX reasons), so these
 * tests pin that the sections render those, plus the list-level rules: every section in the
 * table of contents has a body, ids are unique, and no copy carries an em dash.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { GUIDE_SECTIONS } from '@/about/guide'
import { ACTION_LABELS } from '@/audit/actionLabels'
import McpSection from '@/components/about/guide/McpSection.vue'
import NowVsNewSection from '@/components/about/guide/NowVsNewSection.vue'
import { SECTION_BODY } from '@/components/about/guide/sections'
import StateOrAcceptanceSection from '@/components/about/guide/StateOrAcceptanceSection.vue'
import TriageSection from '@/components/about/guide/TriageSection.vue'
import TwoScannersSection from '@/components/about/guide/TwoScannersSection.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { CISA_JUSTIFICATIONS, PANEL_TARGETS } from '@/findings/triageRules'
import { endpointUrl, MCP_LEVELS } from '@/views/settings/mcpTokensForm'

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
    expect(w.find('a.docs-link').attributes('href')).toMatch(/\/docs\/use\/connect-an-ai-agent\.md$/)
    expect(w.text()).not.toContain(';')
  })
})
