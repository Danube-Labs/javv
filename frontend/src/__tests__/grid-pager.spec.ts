/**
 * The shared pager (issue 681): a table with no rows used to keep "Rows per page" and two dead
 * buttons under its own "nothing here" message. With nothing to page, there is no pager.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import GridPager from '@/components/findings/GridPager.vue'

const pager = (over: Partial<InstanceType<typeof GridPager>['$props']>) =>
  mount(GridPager, {
    props: { total: 40, page: 0, size: 25, shown: 25, hasPrev: false, hasNext: true, ...over },
  })

describe('GridPager', () => {
  it('shows the range and both buttons when there are rows', () => {
    const w = pager({})
    expect(w.find('.pager-info').text()).toBe('Showing 1–25 of 40')
    expect(w.findAll('.pager-btn')).toHaveLength(2)
  })

  it('renders nothing when the table has no rows at all', () => {
    const w = pager({ total: 0, shown: 0, hasNext: false })
    expect(w.find('.pager').exists()).toBe(false)
  })

  it('keeps a refused page in place: its range and Prev, with no rows shown (issue 833)', () => {
    const w = pager({ total: 435, page: 1, shown: 0, hasPrev: true, hasNext: false, failed: true })
    expect(w.find('.pager-info').text()).toBe('Showing 26–50 of 435')
    expect(w.findAll('.pager-btn')[0]!.attributes('disabled')).toBeUndefined()
  })

  it('caps a refused last page at the total', () => {
    const w = pager({ total: 40, page: 1, shown: 0, hasPrev: true, hasNext: false, failed: true })
    expect(w.find('.pager-info').text()).toBe('Showing 26–40 of 40')
  })

  it('the rows-per-page list is the small kit dropdown, and a pick gives the size as a number (issue 1055)', async () => {
    const w = pager({})
    const select = w.find('select')
    expect(select.classes()).toEqual(['set-select', 'set-select--small'])
    expect((select.element as HTMLSelectElement).value).toBe('25')
    await select.setValue('50')
    expect(w.emitted('update:size')).toEqual([[50]])
  })

  it('stays on an empty later page, so Prev can still get back', () => {
    const w = pager({ total: 0, page: 1, shown: 0, hasPrev: true, hasNext: false })
    expect(w.find('.pager').exists()).toBe(true)
    expect(w.find('.pager-info').text()).toBe('No results')
  })
})
