/**
 * A stored value is never printed raw where it has a display name (issue 674): the filter rail
 * listed `not_affected` and `risk_accept` beside pills and tags that said "Not affected" and
 * "Risk accepted". The value itself (URL, API param, saved view) does not change.
 */
import { mount } from '@vue/test-utils'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { AUDIT_ACTIONS, AUDIT_FIELDS } from '@/audit/fields.config'
import { ACTION_LABELS, actionLabel } from '@/audit/actionLabels'
import ActionTag from '@/components/chips/ActionTag.vue'
import StateTag from '@/components/chips/StateTag.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import { facetItems } from '@/filters/facets'
import { FINDINGS_FIELDS, emptySelections, valueLabel, type FilterField } from '@/filters/fields.config'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { presetSummary } from '@/findings/savedViews'
import { STATE_LABELS } from '@/findings/stateLabels'

const field = (fields: readonly FilterField[], key: string) => fields.find((f) => f.key === key)!
const STATE = field(FINDINGS_FIELDS, 'state')
const ACTION = field(AUDIT_FIELDS, 'action')

describe('display names for stored values', () => {
  it('the State rail lists the names the state pill shows', () => {
    const items = facetItems(STATE, {})!
    expect(items.map((i) => i.label)).toEqual(['Open', 'Acknowledged', 'Not affected', 'Risk accepted', 'Resolved', 'Stale'])
    // the value is untouched: it is what the URL, the API and saved views carry
    expect(items.map((i) => i.value)).toEqual(['open', 'acknowledged', 'not_affected', 'risk_accepted', 'resolved', 'stale'])
    for (const i of items) expect(mount(StateTag, { props: { state: i.value } }).text()).toBe(i.label)
  })

  it('the Action rail lists the names the action tag shows, for every action', () => {
    const items = facetItems(ACTION, {})!
    expect(items).toHaveLength(AUDIT_ACTIONS.length)
    for (const i of items) expect(mount(ActionTag, { props: { action: i.value } }).text()).toBe(i.label)
    expect(items.find((i) => i.value === 'risk_accept')!.label).toBe('Risk accepted')
    expect(items.find((i) => i.value === 'cluster_delete_recheck')!.label).toBe('Leftover rows deleted')
  })

  it('an action with no entry reads as its words, never as snake_case', () => {
    expect(ACTION_LABELS['store_inspect']).toBeUndefined() // the case this fallback exists for
    expect(actionLabel('store_inspect')).toBe('store inspect')
  })

  it('no rail option with a fixed vocabulary shows an underscore', () => {
    for (const fields of [FINDINGS_FIELDS, AUDIT_FIELDS]) {
      for (const f of fields) {
        if (f.type !== 'terms' || !f.values) continue
        const raw = facetItems(f, {})!.filter((i) => i.label.includes('_')).map((i) => `${f.key}: ${i.label}`)
        expect(raw).toEqual([])
      }
    }
  })

  it('a value that is a real name (a scanner, a namespace) is shown as it is', () => {
    expect(valueLabel(field(FINDINGS_FIELDS, 'scanner'), 'trivy')).toBe('trivy')
    expect(valueLabel(field(FINDINGS_FIELDS, 'namespace'), 'kube_system')).toBe('kube_system')
  })

  it('an unknown state falls back to the value, never to blank', () => {
    expect(STATE_LABELS['brand_new']).toBeUndefined()
    expect(valueLabel(STATE, 'brand_new')).toBe('brand_new')
  })
})

describe('where the names are printed', () => {
  const selections = { ...emptySelections(FINDINGS_FIELDS), state: ['not_affected', 'risk_accepted'] }

  it('the rail row shows the name', () => {
    const rail = mount(FacetRail, { props: { fields: FINDINGS_FIELDS, facets: {}, selections } })
    expect(rail.text()).toContain('Not affected')
    expect(rail.text()).not.toContain('not_affected')
  })

  it('the filter pill shows the name', () => {
    const bar = mount(FilterBar, { props: { fields: FINDINGS_FIELDS, facets: {}, selections } })
    expect(bar.text()).toContain('Not affected, Risk accepted')
    expect(bar.text()).not.toContain('not_affected')
  })

  // the search box appears on long lists only, so this uses the audit Action field (27 values)
  it('the value search in the filter menu finds an option by its name and by its stored value', async () => {
    for (const typed of ['risk acc', 'risk_acc']) {
      const bar = mount(FilterBar, { props: { fields: AUDIT_FIELDS, facets: {}, selections: emptySelections(AUDIT_FIELDS) } })
      await bar.find('.add-filter').trigger('click')
      await bar.findAll('.filter-field').find((b) => b.text().includes('Action'))!.trigger('click')
      await bar.find('.filter-vsearch input').setValue(typed)
      expect(bar.findAll('.facet-row').map((r) => r.text()), `typed "${typed}"`).toEqual(['Risk accepted'])
    }
  })

  it('the saved-view summary shows the name', () => {
    expect(presetSummary(FINDINGS_FIELDS, { state: ['not_affected'], exclude_state: undefined } as never)).toBe(
      'State is Not affected',
    )
  })

  it('the query the filter sends is still the stored value', () => {
    const query = buildFilterQuery(FINDINGS_FIELDS, selections, { cluster_id: 'c-1' })
    expect(query.state).toEqual(['not_affected', 'risk_accepted'])
  })
})

describe('retired wording stays retired', () => {
  // the exact phrases the operator ruled out on 2026-10-02: internal terms in user-facing copy
  const RETIRED = [
    'applies to the current lens',
    'Apply to lens',
    'Narrow the lens',
    'the current lens ·',
    'current lens is not storable',
    'What this lens is for',
    'Set up a lens',
    'VEX lifecycle',
    'never rendered as HTML',
    'Append-family retention',
    'five append families',
    'over the append families',
    'no filters active: bulk',
    'inline bulk',
  ]
  const SRC = resolve(process.cwd(), 'src')
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name)
      if (statSync(path).isDirectory()) return name === '__tests__' || name === 'generated' ? [] : walk(path)
      return /\.(vue|ts)$/.test(name) ? [path] : []
    })

  it('none of them is back in the source', () => {
    const hits = walk(SRC).flatMap((path) => {
      const text = readFileSync(path, 'utf8')
      return RETIRED.filter((phrase) => text.includes(phrase)).map((phrase) => `${relative(SRC, path)}: "${phrase}"`)
    })
    expect(hits).toEqual([])
  })
})
