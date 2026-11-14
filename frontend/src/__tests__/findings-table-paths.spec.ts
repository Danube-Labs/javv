/**
 * The Paths column of the shared findings table (issue 1077). Only the image page turns it on:
 * off, the table is the Findings grid as before. On, a row with a path opens to list its files,
 * and the button that opens it does not open the finding.
 */
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import FindingPaths from '@/components/finding/FindingPaths.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
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

const mountTable = (rows: FindingRow[], paths?: boolean) =>
  mount(FindingsTable, {
    props: { rows, sort: 'severity_rank', order: 'desc', loading: false, settled: true, paths },
    global: { plugins: [PrimeVue] },
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
    expect(w.findAll('.paths-none').map((s) => s.text())).toEqual(['0 paths', '-'])
  })

  it('on: a new page closes the rows that were open', async () => {
    const w = mountTable([row('a', { locations: ['/x'], locations_total: 1 })], true)
    await w.find('button.paths-btn').trigger('click')
    expect(w.findComponent(FindingPaths).exists()).toBe(true)
    await w.setProps({ rows: [row('a', { locations: ['/x'], locations_total: 1 })] })
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
  })
})
