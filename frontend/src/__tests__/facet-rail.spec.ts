/**
 * A rail row with a long unbroken value (issue 652): the label truncates on one line with the
 * full value in its title, and the count and the exclude action keep their own boxes after it,
 * so they stay inside the row (EUI's facet button does the same). jsdom has no layout, so this
 * pins the structure the CSS relies on; the visual rig's layout check measures the pixels.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import type { FacetsResponse } from '@/filters/facets'
import { emptySelections, type FilterField } from '@/filters/fields.config'

const LONG = 'docker.io/rancher/mirrored-library-traefik'
const FIELDS: FilterField[] = [
  { key: 'namespace', label: 'Namespace', type: 'terms', param: 'namespace', facetKey: 'namespaces', negatable: true },
]
const FACETS: FacetsResponse = {
  namespaces: [{ key: LONG, count: 1234, by_scanner: { trivy: 600, grype: 634 } }],
}

const mountRail = () =>
  mount(FacetRail, { props: { fields: FIELDS, selections: emptySelections(FIELDS), facets: FACETS } })

describe('FacetRail row with a long value', () => {
  it('puts the value in a one-line text box with the full value in its title', () => {
    const label = mountRail().find('.facet-row .facet-label')
    expect(label.attributes('title')).toBe(LONG)
    expect(label.find('.facet-text').text()).toBe(LONG)
  })

  it('keeps the count and the action as siblings after the label, outside the box that truncates', () => {
    const row = mountRail().find('.facet-row')
    const kids = row.element.children
    const classes = [...kids].map((k) => k.className)
    const at = (c: string) => classes.findIndex((n) => n.split(' ').includes(c))
    expect(at('facet-label')).toBeGreaterThan(-1)
    expect(at('facet-count')).toBeGreaterThan(at('facet-label'))
    expect(at('val-act-reveal')).toBeGreaterThan(at('facet-count'))
    expect(row.find('.facet-label .facet-count').exists()).toBe(false)
  })

  it("keeps the row's own title for the per-scanner split", () => {
    expect(mountRail().find('.facet-row').attributes('title')).toBe('trivy 600 · grype 634')
  })
})

describe('FacetRail with counts that could not be loaded (issue 833, F9)', () => {
  it('keeps every value and shows "-" for its count', () => {
    const w = mount(FacetRail, {
      props: { fields: FIELDS, selections: emptySelections(FIELDS), facets: FACETS, countsUnknown: true },
    })
    expect(w.find('.facet-text').text()).toBe(LONG)
    expect(w.find('.facet-count').text()).toBe('-')
  })
})

describe('a picked value the server leaves out of its top 32 (issue 949)', () => {
  // the Namespace facet counts without its own filter, so a picked namespace that ranks below
  // the top 32 is not in the buckets; it must still have a row, or it cannot be taken out alone
  const MULTI: FilterField[] = [{ ...FIELDS[0]!, multi: true } as FilterField]
  const selections = { ...emptySelections(MULTI), namespace: [LONG, 'payments'] }

  it('the rail lists it after the buckets, checked, with no count', async () => {
    const w = mount(FacetRail, { props: { fields: MULTI, selections, facets: FACETS } })
    const rows = w.findAll('.facet-row')
    expect(rows.map((r) => r.find('.facet-text').text())).toEqual([LONG, 'payments'])
    expect(rows[1]!.find('.facet-count').exists()).toBe(false)
    await rows[1]!.trigger('click')
    expect(w.emitted('toggle')?.[0]).toEqual(['namespace', 'payments'])
  })

  it('the filter bar lists it too', async () => {
    const bar = mount(FilterBar, { props: { fields: MULTI, selections, facets: FACETS } })
    await bar.find('.add-filter').trigger('click')
    await bar.find('.filter-field').trigger('click')
    expect(bar.findAll('.filter-menu .facet-row').map((r) => r.text())).toEqual([
      expect.stringContaining(LONG),
      'payments',
    ])
  })
})
