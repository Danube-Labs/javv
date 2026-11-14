/**
 * The Paths column of the shared findings table (issue 1077). Only the image page turns it on:
 * off, the table is the Findings grid as before. On, a row with a path opens to list its files,
 * and the button that opens it does not open the finding.
 */
import { flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FindingPaths from '@/components/finding/FindingPaths.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import { logger } from '@/lib/logger'
import type { FindingRow } from '@/stores/findings'

const row = (key: string, over: Partial<FindingRow> = {}): FindingRow => ({
  finding_key: key,
  cve_id: 'CVE-2026-111943',
  scanner: 'trivy',
  severity: 'HIGH',
  severity_canonical: 'high',
  image_repo: 'docker.io/rancher/local-path-provisioner',
  tag: 'v0.0.36',
  package_name: 'stdlib',
  installed_version: 'v1.26.3',
  fixed_version: '1.26.10',
  fixable: true,
  epss: null,
  kev: false,
  ptype: 'gobinary',
  state: 'open',
  overdue: false,
  due_at: null,
  ...over,
})

const mountTable = (rows: FindingRow[], paths?: boolean, more: Record<string, unknown> = {}) =>
  mount(FindingsTable, {
    props: { rows, sort: 'severity_rank', order: 'desc', loading: false, settled: true, paths, ...more },
    global: { plugins: [PrimeVue] },
    attachTo: document.body,
  })

const heads = (w: ReturnType<typeof mountTable>) => w.findAll('thead th').map((th) => th.text())

describe('FindingsTable, the Paths column (issue 1077)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('off by default: no Paths column and no button, as the Findings grid was', () => {
    const w = mountTable([row('a', { locations: ['/usr/bin/x'], locations_total: 1 })])
    expect(heads(w)).not.toContain('Paths')
    expect(w.find('button.paths-btn').exists()).toBe(false)
  })

  it('on: the Paths column comes right after Package', () => {
    const h = heads(mountTable([row('a')], true))
    expect(h[h.indexOf('Package') + 1]).toBe('Paths')
  })

  it('on: a row with paths opens to list them, and the click does not open the finding', async () => {
    const paths = ['/usr/bin/local-path-provisioner', '/usr/local/go/bin/go']
    const w = mountTable([row('a', { locations: paths, locations_total: 11 })], true)
    const btn = w.find('button.paths-btn')
    expect(btn.text()).toBe('11 paths')
    expect(btn.attributes('aria-expanded')).toBe('false')

    await btn.trigger('click')
    expect(w.emitted('rowClick')).toBeUndefined()
    // the table draws the row again when it opens: read the new button
    const opened = w.find('button.paths-btn')
    expect(opened.attributes('aria-expanded')).toBe('true')
    const list = w.findComponent(FindingPaths)
    expect(list.attributes('id')).toBe(opened.attributes('aria-controls'))
    expect(list.findAll('li').map((li) => li.text())).toEqual(paths)
    expect(list.text()).toContain('Trivy found stdlib v1.26.3 at 11 paths in this image.')
    expect(list.text()).toContain('JAVV keeps the first 2 of 11 paths.')

    await opened.trigger('click')
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
  })

  it('on: a click on the chevron does not open the finding either', async () => {
    // the table ignores a click on a button, but not one on the shape inside the chevron
    const w = mountTable([row('a', { locations: ['/x'], locations_total: 1 })], true)
    const shape = w.find('button.paths-btn .paths-chev').element.firstElementChild!
    shape.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await w.vm.$nextTick()
    expect(w.emitted('rowClick')).toBeUndefined()
    expect(w.findComponent(FindingPaths).exists()).toBe(true)
  })

  it('on: a row with no path has no button, "0 paths" or "-"', () => {
    const w = mountTable([row('a', { locations: [], locations_total: 0 }), row('b')], true)
    expect(w.find('button.paths-btn').exists()).toBe(false)
    expect(w.find('.paths-none').text()).toBe('0 paths')
    expect(w.find('.muted-dash').text()).toBe('-')
  })

  it('on: a new page closes the rows that were open', async () => {
    const w = mountTable([row('a', { locations: ['/x'], locations_total: 1 })], true)
    await w.find('button.paths-btn').trigger('click')
    expect(w.findComponent(FindingPaths).exists()).toBe(true)
    await w.setProps({ rows: [row('a', { locations: ['/x'], locations_total: 1 })] })
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
  })

  it('on: the button keeps the keyboard focus when its row opens and closes (review F1)', async () => {
    // the table draws its cells again on each toggle, so the button is a new element each time
    const w = mountTable([row('a', { locations: ['/x', '/y'], locations_total: 2 })], true)
    const first = w.find('button.paths-btn').element as HTMLButtonElement
    first.focus()
    first.click()
    await flushPromises()
    const opened = w.find('button.paths-btn').element
    expect(opened.getAttribute('aria-expanded')).toBe('true')
    expect(document.activeElement).toBe(opened)
    ;(opened as HTMLButtonElement).click()
    await flushPromises()
    expect(document.activeElement).toBe(w.find('button.paths-btn').element)
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
    w.unmount()
  })

  it('a reorderable table gets no Paths column: its drag indexes have no Paths (review F4)', () => {
    const w = mountTable([row('a', { locations: ['/x'], locations_total: 1 })], true, { reorderable: true })
    expect(heads(w)).not.toContain('Paths')
    w.unmount()
  })

  it('on, with a read that did not ask for the paths: one warning, no button (review F4)', () => {
    const warn = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const w = mountTable([row('a', { locations_total: 11 }), row('b', { locations: [], locations_total: 0 })], true)
    expect(warn).toHaveBeenCalledWith('findings_table_paths_not_read', { rows: 1 })
    expect(w.find('button.paths-btn').exists()).toBe(false)
    warn.mockRestore()
    w.unmount()
  })
})
