import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import type { FacetsResponse } from '@/filters/facets'
import { FINDINGS_FIELDS, emptySelections, type FilterField } from '@/filters/fields.config'

const FACETS: FacetsResponse = {
  severity: [
    { key: 'critical', count: 194, by_scanner: { grype: 135, trivy: 59 } },
    { key: 'negligible', count: 360, by_scanner: { grype: 360 } },
  ],
  scanner: [{ key: 'trivy', count: 2080, by_scanner: { trivy: 2080 } }],
  kev: [{ key: 'true', count: 41, by_scanner: { trivy: 22, grype: 19 } }],
  os: [{ key: 'alpine', count: 999, by_scanner: { trivy: 1, grype: 2 } }],
  ptype: [{ key: 'deb', count: 1783, by_scanner: { trivy: 900, grype: 883 } }],
  namespaces: [{ key: 'payments', count: 41, by_scanner: { trivy: 20, grype: 21 } }],
  assignee: [{ key: 'admin', count: 3, by_scanner: { trivy: 1, grype: 2 } }],
}

const mountBoth = (fields: readonly FilterField[]) => {
  const props = { fields, selections: emptySelections(fields), facets: FACETS }
  return { rail: mount(FacetRail, { props }), bar: mount(FilterBar, { props }) }
}

describe('one config drives both components (PLAN gate)', () => {
  it('a field added to the config surfaces in FacetRail AND FilterBar with no component edits', async () => {
    const extended: FilterField[] = [
      ...FINDINGS_FIELDS,
      { key: 'os', label: 'Operating system', type: 'terms', param: 'os_name', facetKey: 'os' },
    ]
    const { rail, bar } = mountBoth(extended)

    expect(rail.text()).toContain('Operating system')
    expect(rail.text()).toContain('alpine')

    await bar.find('.add-filter').trigger('click')
    const fieldItems = bar.findAll('.filter-field').map((b) => b.text())
    expect(fieldItems.some((t) => t.includes('Operating system'))).toBe(true)
  })

  it('renders every listable findings field in both, and text fields only in the bar', async () => {
    const { rail, bar } = mountBoth(FINDINGS_FIELDS)

    for (const label of ['Severity', 'Scanner', 'Attribute', 'State', 'Package type', 'Namespace', 'Assignee']) {
      expect(rail.text()).toContain(label) // Namespace/Assignee are rail dims since slice 4
    }
    expect(rail.text()).not.toContain('Image') // text field: no buckets, bar-only
    // issue 492: CVE and Package are bar-and-cell only. A rail dim over unbounded package
    // cardinality is not a browsing surface, and the server 422s them as facets. Asserted on
    // the rendered group titles, not on rail.text() — "Package" is a substring of the
    // "Package type" group that legitimately IS in the rail
    const railGroups = rail.findAll('.facet-title').map((t) => t.text())
    expect(railGroups).not.toContain('CVE')
    expect(railGroups).not.toContain('Package')
    expect(railGroups).toContain('Package type')

    await bar.find('.add-filter').trigger('click')
    const fieldItems = bar.findAll('.filter-field').map((b) => b.text())
    for (const f of FINDINGS_FIELDS) {
      expect(fieldItems.some((t) => t.includes(f.label))).toBe(true)
    }
  })
})

describe('FacetRail per-scanner display (FR-12)', () => {
  it('shows the server count verbatim and the split as tooltip — no client-side arithmetic', () => {
    const fields: FilterField[] = [
      { key: 'os', label: 'OS', type: 'terms', param: 'os_name', facetKey: 'os' },
    ]
    const rail = mount(FacetRail, {
      props: { fields, selections: emptySelections(fields), facets: FACETS },
    })
    const row = rail.find('.facet-row')
    // 999 ≠ 1+2: proves the displayed number is the server's, never a client sum
    expect(row.find('.facet-count').text()).toBe('999')
    expect(row.attributes('title')).toBe('trivy 1 · grype 2')
  })

  it('emits toggle with field key and value on row click', async () => {
    const { rail } = mountBoth(FINDINGS_FIELDS)
    await rail.find('.facet-row').trigger('click')
    expect(rail.emitted('toggle')?.[0]).toEqual(['severity', 'critical'])
  })
})

/**
 * Issue 499: the images screen's two top-32 data-driven groups made the rail ~2× the
 * viewport. Long groups collapse to the top 8 behind a "show all N" expander; a selected
 * value never collapses out of sight.
 */
describe('FacetRail long groups (issue 499)', () => {
  const bucket = (i: number) => ({ key: `repo-${i}`, count: 100 - i, by_scanner: {} })
  const fields: FilterField[] = [
    { key: 'repo', label: 'Image', type: 'terms', param: 'image_repo', facetKey: 'repos' },
  ]
  const mountLong = (selected: string[] = []) =>
    mount(FacetRail, {
      props: {
        fields,
        selections: { repo: selected },
        facets: { repos: Array.from({ length: 20 }, (_, i) => bucket(i)) },
      },
    })

  it('collapses past 8 rows behind a "show all N" expander; short groups get none', () => {
    const rail = mountLong()
    expect(rail.findAll('.facet-row')).toHaveLength(8)
    expect(rail.find('.facet-more').text()).toBe('show all 20')

    const { rail: short } = mountBoth(FINDINGS_FIELDS)
    expect(short.find('.facet-more').exists()).toBe(false)
  })

  it('expands to the full list and collapses back', async () => {
    const rail = mountLong()
    await rail.find('.facet-more').trigger('click')
    expect(rail.findAll('.facet-row')).toHaveLength(20)
    expect(rail.find('.facet-more').text()).toBe('show fewer')
    expect(rail.find('.facet-more').attributes('aria-expanded')).toBe('true')
    await rail.find('.facet-more').trigger('click')
    expect(rail.findAll('.facet-row')).toHaveLength(8)
  })

  it('a selected value beyond the fold stays visible while collapsed', () => {
    const rail = mountLong(['repo-15'])
    const labels = rail.findAll('.facet-row').map((r) => r.text())
    expect(labels.some((t) => t.includes('repo-15'))).toBe(true)
    expect(rail.findAll('.facet-row')).toHaveLength(9) // top 8 + the selected one
  })
})

describe('FilterBar interactions', () => {
  it('shows pills for active selections and emits clearField / clearAll', async () => {
    const selections = { ...emptySelections(FINDINGS_FIELDS), severity: ['critical', 'high'] }
    const bar = mount(FilterBar, {
      props: { fields: FINDINGS_FIELDS, selections, facets: FACETS },
    })

    const pill = bar.find('.fpill')
    expect(pill.text()).toContain('Severity')
    expect(pill.text()).toContain('is one of')

    await pill.find('.fpill-x').trigger('click')
    expect(bar.emitted('clearField')?.[0]).toEqual(['severity'])

    await bar.find('.clear-all').trigger('click')
    expect(bar.emitted('clearAll')).toHaveLength(1)
  })

  it('drills into a field and emits toggle for a picked value', async () => {
    const bar = mount(FilterBar, {
      props: { fields: FINDINGS_FIELDS, selections: emptySelections(FINDINGS_FIELDS), facets: FACETS },
    })
    await bar.find('.add-filter').trigger('click')
    const sevItem = bar.findAll('.filter-field').find((b) => b.text().includes('Severity'))
    await sevItem?.trigger('click')
    await bar.find('.facet-row').trigger('click')
    expect(bar.emitted('toggle')?.[0]).toEqual(['severity', 'critical'])
  })

  it('gives a one-value text field an input and emits setText on Enter', async () => {
    const fields: FilterField[] = [{ key: 'image', label: 'Image', type: 'text', param: 'image_repo' }]
    const bar = mount(FilterBar, {
      props: { fields, selections: emptySelections(fields), facets: FACETS },
    })
    await bar.find('.add-filter').trigger('click')
    await bar.find('.filter-field').trigger('click')
    const input = bar.find('.filter-vsearch input')
    await input.setValue('nginx')
    await input.trigger('keydown.enter')
    expect(bar.emitted('setText')?.[0]).toEqual(['image', 'nginx'])
  })
})

/** Issue 949 PR C: Image, CVE and Package take several typed values (ruled 2026-10-21: the
 * values listed under the edit box). */
describe('FilterBar several typed values', () => {
  const openImage = async (image: string[]) => {
    const bar = mount(FilterBar, {
      props: {
        fields: FINDINGS_FIELDS,
        selections: { ...emptySelections(FINDINGS_FIELDS), image },
        facets: FACETS,
        maxValues: 32,
      },
    })
    await bar.find('.add-filter').trigger('click')
    await bar.findAll('.filter-field').find((b) => b.text().includes('Image'))?.trigger('click')
    return bar
  }

  it('Enter adds the typed value, empties the input and keeps the box open', async () => {
    const bar = await openImage(['api'])
    const input = bar.find('.filter-vsearch input')
    expect((input.element as HTMLInputElement).value).toBe('') // the values list below holds `api`
    await input.setValue('  web ')
    await input.trigger('keydown.enter')
    expect(bar.emitted('toggle')?.[0]).toEqual(['image', 'web'])
    expect(bar.emitted('setText')).toBeUndefined()
    expect((input.element as HTMLInputElement).value).toBe('')
    expect(bar.find('.filter-menu').exists()).toBe(true)
  })

  it('a value already in the list or an empty input adds nothing', async () => {
    const bar = await openImage(['api'])
    const input = bar.find('.filter-vsearch input')
    await input.setValue('api')
    await input.trigger('keydown.enter')
    await input.setValue('   ')
    await input.trigger('keydown.enter')
    expect(bar.emitted('toggle')).toBeUndefined()
  })

  it('lists the values under the input; a click on one takes it out', async () => {
    const bar = await openImage(['api', 'web'])
    const rows = bar.findAll('.filter-menu .facet-row')
    expect(rows.map((r) => r.text())).toEqual(['api', 'web'])
    expect(rows.every((r) => r.classes('facet-on'))).toBe(true)
    expect(rows[1]!.attributes('title')).toBe('Remove web')
    await rows[1]!.trigger('click')
    expect(bar.emitted('toggle')?.[0]).toEqual(['image', 'web'])
  })

  it('a pasted comma list adds each value', async () => {
    const bar = await openImage([])
    const input = bar.find('.filter-vsearch input')
    await input.setValue('api, web')
    await input.trigger('keydown.enter')
    expect(bar.emitted('toggle')).toEqual([
      ['image', 'api'],
      ['image', 'web'],
    ])
  })

  it('at 32 values the box says so and Enter adds nothing', async () => {
    const bar = await openImage(Array.from({ length: 32 }, (_, i) => `img-${i}`))
    expect(bar.find('.filter-note').text()).toBe('A filter takes at most 32 values.')
    const input = bar.find('.filter-vsearch input')
    expect(bar.find('.filter-note').attributes('role')).toBe('status')
    await input.setValue('one-more')
    await input.trigger('keydown.enter')
    expect(bar.emitted('toggle')).toBeUndefined()
    // what did not fit stays in the input
    expect((input.element as HTMLInputElement).value).toBe('one-more')
  })

  it('at 32 values a facet field says so too', async () => {
    const ns = Array.from({ length: 32 }, (_, i) => `ns-${i}`)
    const bar = mount(FilterBar, {
      props: {
        fields: FINDINGS_FIELDS,
        selections: { ...emptySelections(FINDINGS_FIELDS), namespace: ns },
        facets: FACETS,
        maxValues: 32,
      },
    })
    await bar.find('.add-filter').trigger('click')
    await bar.findAll('.filter-field').find((b) => b.text().includes('Namespace'))?.trigger('click')
    expect(bar.find('.filter-note').exists()).toBe(true)
  })

  it('with no cap (Running images), no note shows', async () => {
    const ns = Array.from({ length: 40 }, (_, i) => `ns-${i}`)
    const bar = mount(FilterBar, {
      props: { fields: FINDINGS_FIELDS, selections: { ...emptySelections(FINDINGS_FIELDS), namespace: ns }, facets: FACETS },
    })
    await bar.find('.add-filter').trigger('click')
    await bar.findAll('.filter-field').find((b) => b.text().includes('Namespace'))?.trigger('click')
    expect(bar.find('.filter-note').exists()).toBe(false)
  })

  it('a removable row names its action for a screen reader; CVE keeps its capitals', async () => {
    const bar = mount(FilterBar, {
      props: {
        fields: FINDINGS_FIELDS,
        selections: { ...emptySelections(FINDINGS_FIELDS), cve: ['CVE-1'] },
        facets: FACETS,
      },
    })
    await bar.find('.add-filter').trigger('click')
    await bar.findAll('.filter-field').find((b) => b.text().includes('CVE'))?.trigger('click')
    expect(bar.find('.filter-vsearch input').attributes('placeholder')).toBe('Add CVE…')
    expect(bar.find('.filter-menu .facet-row').attributes('aria-label')).toBe('Remove CVE-1')
    expect(bar.find('.filter-clear-field').text()).toBe('Clear CVE')
  })

  it('the pill reads "is one of" for two typed values', () => {
    const bar = mount(FilterBar, {
      props: {
        fields: FINDINGS_FIELDS,
        selections: { ...emptySelections(FINDINGS_FIELDS), cve: ['CVE-1', 'CVE-2'] },
        facets: FACETS,
      },
    })
    const pill = bar.find('.fpill')
    expect(pill.text()).toContain('CVE')
    expect(pill.text()).toContain('is one of')
    expect(pill.text()).toContain('CVE-1, CVE-2')
    // the pill truncates long values; the title holds them all
    expect(pill.find('.fpill-vals').attributes('title')).toBe('CVE-1, CVE-2')
  })
})
