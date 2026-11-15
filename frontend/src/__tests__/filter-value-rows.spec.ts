/**
 * The value rows of the filter bar's edit box (issue 1190): a click asks the parent to change the
 * selection, and the row of a selected value carries `facet-on`, the class the shared filter row
 * rules in base.css draw as checked. jsdom has no styles, so this pins the classes and the event;
 * the browser walk of the issue compares the drawn rows.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FilterValueRows, { type ValueRow } from '@/components/filters/FilterValueRows.vue'

const ROWS: ValueRow[] = [
  { value: 'critical', label: 'Critical', on: false, count: 12 },
  { value: 'high', label: 'High', on: true, count: 1500 },
]

describe('FilterValueRows', () => {
  it('draws one filter row for each value, with the check box and the count', () => {
    const rows = mount(FilterValueRows, { props: { rows: ROWS } }).findAll('.facet-row')
    expect(rows.map((r) => r.find('.facet-label').text())).toEqual(['Critical', 'High'])
    expect(rows.every((r) => r.find('.facet-check').exists())).toBe(true)
    expect(rows.map((r) => r.find('.facet-count').text())).toEqual(['12', '1,500'])
  })

  it('marks only the selected value with facet-on', () => {
    const rows = mount(FilterValueRows, { props: { rows: ROWS } }).findAll('.facet-row')
    expect(rows.map((r) => r.classes('facet-on'))).toEqual([false, true])
  })

  it('a click on a row asks for its value, and the new selection moves facet-on', async () => {
    const wrapper = mount(FilterValueRows, { props: { rows: ROWS } })
    await wrapper.findAll('.facet-row')[0]!.trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([['critical']])
    await wrapper.setProps({ rows: ROWS.map((r) => (r.value === 'critical' ? { ...r, on: true } : r)) })
    expect(wrapper.findAll('.facet-row').map((r) => r.classes('facet-on'))).toEqual([true, true])
  })

  it('a typed value has no count, and a removable row says so', () => {
    const rows = mount(FilterValueRows, {
      props: { rows: [{ value: 'nginx', label: 'nginx', on: true, count: null }], removable: true },
    }).findAll('.facet-row')
    expect(rows[0]!.find('.facet-count').exists()).toBe(false)
    expect(rows[0]!.attributes('aria-label')).toBe('Remove nginx')
  })
})
