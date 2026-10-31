/**
 * A rail row with a long unbroken value (issue 652): the label truncates on one line with the
 * full value in its title, and the count and the exclude action keep their own boxes after it,
 * so they stay inside the row (EUI's facet button does the same). jsdom has no layout, so this
 * pins the structure the CSS relies on; the visual rig's layout check measures the pixels.
 */
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AUDIT_ACTIONS, AUDIT_FIELDS } from '@/audit/fields.config'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import { FACET_CAP, type FacetsResponse, type ValueSearch, type ValueSearchFn } from '@/filters/facets'
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
    expect(rows[1]!.classes()).toContain('facet-on')
    await rows[1]!.trigger('click')
    expect(w.emitted('toggle')?.[0]).toEqual(['namespace', 'payments'])
  })

  it('a value picked twice in the URL gets one row', () => {
    const twice = { ...emptySelections(MULTI), namespace: ['payments', 'payments'] }
    const w = mount(FacetRail, { props: { fields: MULTI, selections: twice, facets: FACETS } })
    expect(w.findAll('.facet-text').map((t) => t.text())).toEqual([LONG, 'payments'])
  })

  it('the "top 32" note counts the buckets, not the picked values added after them', async () => {
    const thirty: FacetsResponse = {
      namespaces: Array.from({ length: 30 }, (_, i) => ({ key: `ns-${i}`, count: 30 - i, by_scanner: {} })),
    }
    const picked = { ...emptySelections(MULTI), namespace: ['x', 'y'] }
    const w = mount(FacetRail, { props: { fields: MULTI, selections: picked, facets: thirty } })
    await w.find('.facet-more').trigger('click')
    expect(w.findAll('.facet-row')).toHaveLength(32)
    expect(w.find('.facet-cap').exists()).toBe(false)
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

describe('the rail at the API cap (issue 949)', () => {
  const MULTI: FilterField[] = [{ ...FIELDS[0]!, multi: true } as FilterField]
  const ns = Array.from({ length: 32 }, (_, i) => `ns-${i}`)

  it('says a filter takes at most 32 values, for a screen reader too', () => {
    const w = mount(FacetRail, {
      props: { fields: MULTI, selections: { ...emptySelections(MULTI), namespace: ns }, facets: FACETS, maxValues: 32 },
    })
    const note = w.findAll('.facet-cap').find((p) => p.text().includes('at most'))
    expect(note?.text()).toBe('A filter takes at most 32 values.')
    expect(note?.attributes('role')).toBe('status')
  })

  it('shows no note without a cap', () => {
    const w = mount(FacetRail, {
      props: { fields: MULTI, selections: { ...emptySelections(MULTI), namespace: ns }, facets: FACETS },
    })
    expect(w.findAll('.facet-cap').some((p) => p.text().includes('at most'))).toBe(false)
  })
})

describe('the "top N" note on a fixed list (issues 980 and 983)', () => {
  // a fixed list gets a 0 for each value with no rows, so it has more counted rows than buckets:
  // the note counts the server's buckets against the cap of the field
  const values = Array.from({ length: 40 }, (_, i) => `v-${i}`)
  const FIXED: FilterField = { key: 'fixed', label: 'Fixed', type: 'terms', param: 'fixed', facetKey: 'fixed', values }
  const ACTION = AUDIT_FIELDS.find((f) => f.key === 'action')!
  const open = async (field: FilterField, facets: FacetsResponse) => {
    const w = mount(FacetRail, {
      props: { fields: [field], selections: emptySelections([field]), facets },
    })
    await w.find('.facet-more').trigger('click')
    return w
  }
  const bucket = (key: string) => ({ key, count: 1, by_scanner: {} })

  it('is not shown when the server gave fewer buckets than the cap, though each value has a count', async () => {
    const w = await open(FIXED, { fixed: [bucket('v-0')] })
    expect(w.findAll('.facet-count')).toHaveLength(values.length)
    expect(w.find('.facet-cap').exists()).toBe(false)
  })

  it('is shown when the server stopped at 32 buckets', async () => {
    const w = await open(FIXED, { fixed: values.slice(0, FACET_CAP).map(bucket) })
    expect(w.find('.facet-cap').text()).toBe('Top 32 by count. Add filter finds the other values.')
  })

  it('names the cap of the field', async () => {
    const small: FilterField = { ...FIXED, facetCap: 8 } as FilterField
    const w = await open(small, { fixed: values.slice(0, 8).map(bucket) })
    expect(w.find('.facet-cap').text()).toBe('Top 8 by count. Add filter finds the other values.')
  })

  it('is not shown on the Action list with 40 actions, and each action has a count (issue 983)', async () => {
    const w = await open(ACTION, { action: AUDIT_ACTIONS.slice(0, 40).map(bucket) })
    expect(w.findAll('.facet-count')).toHaveLength(AUDIT_ACTIONS.length)
    expect(w.find('.facet-cap').exists()).toBe(false)
  })
})

/** Issue 1064, Q1 option B: a list that stopped at its cap gets a search box. The server matches
 * the text against all values of the field, and the found values show with their counts. */
describe('the search box of a list that stopped at its cap (issue 1064)', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  const NS: FilterField = FIELDS[0]!
  const AS: FilterField = { key: 'assignee', label: 'Assignee', type: 'terms', param: 'assignee', facetKey: 'assignee' }
  const bucket = (key: string, count = 1) => ({ key, count, by_scanner: { trivy: count } })
  const TOP = Array.from({ length: FACET_CAP }, (_, i) => bucket(`team-${String(i).padStart(2, '0')}`))
  const CAPPED: FacetsResponse = { namespaces: TOP, assignee: TOP.map((b) => bucket(`u-${b.key}`)) }
  const found = (...keys: string[]): ValueSearch => ({ buckets: keys.map((k) => bucket(k, 7)), more: false })
  const mountSearch = (searchValues?: ValueSearchFn, facets: FacetsResponse = CAPPED, fields = [NS]) =>
    mount(FacetRail, { props: { fields, selections: emptySelections(fields), facets, searchValues } })
  const texts = (w: ReturnType<typeof mountSearch>) => w.findAll('.facet-row .facet-text').map((r) => r.text())
  const type = async (w: ReturnType<typeof mountSearch>, text: string, at = 0) => {
    await w.findAll('.facet-vsearch input')[at]!.setValue(text)
  }

  it('is not there without a search, or on a list with fewer values than its cap', () => {
    expect(mountSearch().find('.facet-vsearch').exists()).toBe(false)
    const short = mountSearch(vi.fn<ValueSearchFn>(), { namespaces: TOP.slice(0, 5) })
    expect(short.find('.facet-vsearch').exists()).toBe(false)
  })

  it('is there on a list at its cap, and the note points to it', async () => {
    const w = mountSearch(vi.fn<ValueSearchFn>())
    expect(w.find('.facet-vsearch input').attributes('placeholder')).toBe('Find a namespace…')
    expect(w.find('.facet-vsearch input').attributes('aria-label')).toBe('Find a value of Namespace')
    await w.find('.facet-more').trigger('click')
    expect(w.find('.facet-cap').text()).toBe('Top 32 by count. The box above finds the other values.')
  })

  it('a field whose name starts with a vowel reads "an"', () => {
    const w = mountSearch(vi.fn<ValueSearchFn>(), CAPPED, [AS])
    expect(w.find('.facet-vsearch input').attributes('placeholder')).toBe('Find an assignee…')
  })

  it('asks after the pause and lists the values the server found, with their counts', async () => {
    const search = vi.fn<ValueSearchFn>(async () => found('payments-eu', 'payments-us'))
    const w = mountSearch(search)
    await type(w, 'pay')
    expect(search).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(300)
    expect(search).toHaveBeenCalledWith(NS, 'pay')
    expect(texts(w)).toEqual(['payments-eu', 'payments-us'])
    expect(w.findAll('.facet-count').map((c) => c.text())).toEqual(['7', '7'])
    expect(w.find('.facet-more').exists()).toBe(false)
    expect(w.find('.facet-body').classes()).toContain('facet-body-open')
  })

  it('a found value toggles like a listed one', async () => {
    const w = mountSearch(vi.fn<ValueSearchFn>(async () => found('payments-eu')))
    await type(w, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    await w.find('.facet-row').trigger('click')
    expect(w.emitted('toggle')).toEqual([['namespace', 'payments-eu']])
  })

  it('until the server answers, the listed values that contain the text show', async () => {
    const w = mountSearch(vi.fn<ValueSearchFn>(() => new Promise<never>(() => {})))
    await type(w, 'team-1')
    expect(texts(w)).toEqual(TOP.map((b) => b.key).filter((k) => k.includes('team-1')))
  })

  it('says when more values match, and when the search failed', async () => {
    const more = mountSearch(vi.fn<ValueSearchFn>(async () => ({ ...found('payments-eu'), more: true })))
    await type(more, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    expect(more.find('.facet-cap').text()).toBe('More values match. Type more letters.')

    const failed = mountSearch(vi.fn<ValueSearchFn>(async () => null))
    await type(failed, 'team-0')
    await vi.advanceTimersByTimeAsync(300)
    expect(failed.find('.facet-cap').text()).toBe('Could not search all values. The list shows the top 32.')
    expect(texts(failed)).toEqual(TOP.map((b) => b.key).filter((k) => k.includes('team-0')))
  })

  it('typing in one box empties the other', async () => {
    const w = mountSearch(vi.fn<ValueSearchFn>(async () => found('x')), CAPPED, [NS, AS])
    await type(w, 'pay', 0)
    await type(w, 'ann', 1)
    const boxes = w.findAll('.facet-vsearch input')
    expect((boxes[0]!.element as HTMLInputElement).value).toBe('')
    expect((boxes[1]!.element as HTMLInputElement).value).toBe('ann')
  })

  it('new counts ask again, so the found values carry them', async () => {
    const search = vi.fn<ValueSearchFn>(async () => found('payments-eu'))
    const w = mountSearch(search)
    await type(w, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    await w.setProps({ facets: { namespaces: [...TOP] } })
    await vi.advanceTimersByTimeAsync(300)
    expect(search).toHaveBeenCalledTimes(2)
  })

  it('a list that drops under its cap drops the box and its search', async () => {
    const w = mountSearch(vi.fn<ValueSearchFn>(async () => found('payments-eu')))
    await type(w, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    await w.setProps({ facets: { namespaces: TOP.slice(0, 3) } })
    expect(w.find('.facet-vsearch').exists()).toBe(false)
    expect(texts(w)).toEqual(TOP.slice(0, 3).map((b) => b.key))
  })
})
