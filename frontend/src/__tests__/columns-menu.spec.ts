/**
 * The Columns menu of a grid (issue 1190): each column is a filter row, a shown column carries
 * `facet-on`, the class the shared filter row rules in base.css draw as checked, and a click asks
 * the parent to show or hide the column. jsdom has no styles, so this pins the classes and the
 * event; the browser walk of the issue compares the drawn rows and their hover.
 */
import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import ColumnsMenu from '@/components/findings/ColumnsMenu.vue'
import { FINDINGS_COLUMNS } from '@/findings/columns'

const COLS = [
  ['cve', 'CVE'],
  ['package', 'Package'],
  ['severity', 'Severity'],
] as const

// each open menu is attached to the page, so each test takes its menu off again
let mounted: VueWrapper | null = null
afterEach(() => {
  mounted?.unmount()
  mounted = null
})

const openMenu = async (props: { hidden: ReadonlySet<string>; reorderable?: boolean }) => {
  const wrapper = mount(ColumnsMenu, { props: { cols: COLS, dense: false, ...props }, attachTo: document.body })
  mounted = wrapper
  await wrapper.find('button').trigger('click')
  return wrapper
}

describe('ColumnsMenu', () => {
  it('draws one filter row for each column, with its check box', async () => {
    const rows = (await openMenu({ hidden: new Set() })).findAll('.facet-row')
    expect(rows.map((r) => r.find('.facet-label').text())).toEqual(['CVE', 'Package', 'Severity'])
    expect(rows.every((r) => r.find('.facet-check').exists())).toBe(true)
  })

  it('marks each shown column with facet-on, and not a hidden one', async () => {
    const rows = (await openMenu({ hidden: new Set(['package']) })).findAll('.facet-row')
    expect(rows.map((r) => r.classes('facet-on'))).toEqual([true, false, true])
  })

  it('a click on a row asks to toggle its column, and the new hidden set moves facet-on', async () => {
    const wrapper = await openMenu({ hidden: new Set() })
    await wrapper.findAll('.facet-row')[1]!.trigger('click')
    expect(wrapper.emitted('toggleCol')).toEqual([['package']])
    await wrapper.setProps({ hidden: new Set(['package']) })
    expect(wrapper.findAll('.facet-row').map((r) => r.classes('facet-on'))).toEqual([true, false, true])
  })

  it('the Findings menu has a Paths row right after Package (issue 1205)', async () => {
    const wrapper = mount(ColumnsMenu, { props: { cols: FINDINGS_COLUMNS, dense: false, hidden: new Set<string>() }, attachTo: document.body })
    mounted = wrapper
    await wrapper.find('button').trigger('click')
    const labels = wrapper.findAll('.facet-row').map((r) => r.find('.facet-label').text())
    expect(labels[labels.indexOf('Package') + 1]).toBe('Paths')
  })

  it('a reorderable menu gives each row the grip', async () => {
    const rows = (await openMenu({ hidden: new Set(), reorderable: true })).findAll('.facet-row')
    expect(rows.every((r) => r.find('.row-grip').exists() && r.classes('row-reorderable'))).toBe(true)
  })
})
