/**
 * The "N filters" button of a dashboard panel (issue 999, decision 2 C): the count, the popover
 * with the filters in words, its link to Findings, and its close by Escape and by a click outside.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import PanelFiltersButton from '@/components/dashboards/PanelFiltersButton.vue'

const TWO = { present: true, exclude_namespace: ['kube-system'], kev: true }

function mountButton(props: Record<string, unknown>) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
  // the popover sits next to the panel, the element with data-panel
  const host = document.createElement('div')
  host.setAttribute('data-panel', 'findings-by-namespace')
  document.body.appendChild(host)
  const w = mount(PanelFiltersButton, {
    props: { panelName: 'Findings by namespace', filters: null, ...props } as never,
    attachTo: host,
    global: { plugins: [router] },
  })
  return { w, router }
}

const popover = () => document.body.querySelector('.pop')

afterEach(() => {
  document.body.innerHTML = ''
})

describe('the filters button of a panel', () => {
  it('shows no button for a panel with no filters', () => {
    for (const filters of [null, undefined, { present: true }]) {
      const { w } = mountButton({ filters })
      expect(w.find('button').exists()).toBe(false)
      w.unmount()
    }
  })

  it('counts the filters: 1 filter, 2 filters', () => {
    expect(mountButton({ filters: { present: true, kev: true } }).w.find('button').text()).toBe('1 filter')
    const { w } = mountButton({ filters: TWO })
    expect(w.find('button').text()).toBe('2 filters')
    expect(w.find('button').attributes('aria-label')).toBe('2 filters on Findings by namespace')
  })

  it('opens a popover with one line for each filter, and a second click closes it', async () => {
    const { w } = mountButton({ filters: TWO })
    const btn = w.find('button')
    expect(btn.attributes('aria-expanded')).toBe('false')
    await btn.trigger('click')
    await flushPromises()
    expect(btn.attributes('aria-expanded')).toBe('true')
    expect(popover()?.getAttribute('aria-label')).toBe('Panel filters: Findings by namespace')
    expect([...popover()!.querySelectorAll('.pf-item')].map((li) => li.textContent)).toEqual([
      'KEV',
      'Namespace is not kube-system',
    ])
    await btn.trigger('click')
    expect(popover()).toBeNull()
  })

  it('closes on Escape and on a click outside', async () => {
    const { w } = mountButton({ filters: TWO })
    await w.find('button').trigger('click')
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(popover()).toBeNull()

    await w.find('button').trigger('click')
    await flushPromises()
    expect(popover()).not.toBeNull()
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(popover()).toBeNull()
  })

  it('Open in Findings carries the filters, and the scanner of a pinned panel', async () => {
    const { w, router } = mountButton({ filters: TWO, pinned: 'grype' })
    await w.find('button').trigger('click')
    await flushPromises()
    const open = [...popover()!.querySelectorAll('button')].find((b) => b.textContent === 'Open in Findings')!
    open.click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/findings')
    expect(router.currentRoute.value.query).toEqual({ namespace: '!kube-system', attr: 'kev', scanner: 'grype' })
    expect(popover()).toBeNull()
  })

  it('Open in Findings of a panel that follows the dashboard sends no scanner', async () => {
    const { w, router } = mountButton({ filters: TWO, pinned: null })
    await w.find('button').trigger('click')
    await flushPromises()
    ;[...popover()!.querySelectorAll('button')].find((b) => b.textContent === 'Open in Findings')!.click()
    await flushPromises()
    expect(router.currentRoute.value.query).not.toHaveProperty('scanner')
  })
})
