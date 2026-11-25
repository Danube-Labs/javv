/**
 * The Tag column of the shared findings table (issue 1317, Q3 and Q5 accepted on built
 * pictures). Tag comes after Image, with the +/- of a table cell. While it shows, the Image cell
 * names the image only. When it is hidden, the Image cell shows the tag again.
 */
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it } from 'vitest'

import FindingsTable from '@/components/findings/FindingsTable.vue'
import type { FindingRow } from '@/stores/findings'

const row = (key: string, over: Partial<FindingRow> = {}): FindingRow => ({
  finding_key: key,
  cve_id: 'CVE-2026-111943',
  scanner: 'trivy',
  severity: 'HIGH',
  severity_canonical: 'high',
  image_repo: 'docker.io/library/postgres',
  tag: '13.4',
  package_name: 'libssl3',
  installed_version: '3.0.2',
  fixed_version: null,
  fixable: false,
  epss: null,
  kev: false,
  ptype: 'debian',
  state: 'open',
  overdue: false,
  due_at: null,
  ...over,
})

const mountTable = (rows: FindingRow[], hidden: string[] = [], selections: Record<string, string[]> = {}) =>
  mount(FindingsTable, {
    props: { rows, sort: 'severity_rank', order: 'desc', loading: false, settled: true, hidden: new Set(hidden), selections },
    global: { plugins: [PrimeVue] },
    attachTo: document.body,
  })

const heads = (w: ReturnType<typeof mountTable>) => w.findAll('thead th').map((th) => th.text())

describe('FindingsTable, the Tag column (issue 1317)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('comes right after Image and shows the tag of the row', () => {
    const w = mountTable([row('a')])
    const h = heads(w)
    expect(h[h.indexOf('Image') + 1]).toBe('Tag')
    const cell = w.find('.tag-cell')
    expect(cell.text()).toBe('13.4')
    expect(cell.attributes('title')).toBe('13.4')
  })

  it('a row with no tag shows "-", and its cell has no +/-', () => {
    const w = mountTable([row('a', { tag: null })])
    expect(w.find('.tag-cell').text()).toBe('-')
    expect(w.find('.tag-cell').element.parentElement!.querySelector('.val-act-reveal')).toBeNull()
  })

  it('while Tag shows, the Image cell names the image only; hidden, the cell shows the tag again', () => {
    expect(mountTable([row('a')]).find('.img-cell').text()).toBe('postgres')
    const hidden = mountTable([row('a')], ['tag'])
    expect(heads(hidden)).not.toContain('Tag')
    expect(hidden.find('.img-cell').text()).toBe('postgres:13.4')
    // the title keeps the full name either way
    expect(hidden.find('.img-cell').attributes('title')).toBe('docker.io/library/postgres')
  })

  it('the +/- of a Tag cell picks the Tag filter, in each mode', async () => {
    const w = mountTable([row('a')])
    const actions = w.find('.tag-cell').element.parentElement!
    const buttons = [...actions.querySelectorAll<HTMLElement>('.val-act-reveal .val-act-btn')]
    expect(buttons.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Filter to tag 13.4',
      'Filter out tag 13.4',
    ])
    buttons[0]!.click()
    buttons[1]!.click()
    expect(w.emitted('pickValue')).toEqual([
      ['tag', '13.4', 'is'],
      ['tag', '13.4', 'not'],
    ])
  })

  it('a picked tag shows its side as pressed', () => {
    const w = mountTable([row('a')], [], { tag: ['13.4'] })
    const pressed = w.find('.tag-cell').element.parentElement!.querySelectorAll('[aria-pressed="true"]')
    expect(pressed).toHaveLength(1)
  })
})

describe('the image page keeps its columns (issue 1317)', () => {
  it('hides Tag with Image: the page is one image', () => {
    const src = readFileSync(resolve(__dirname, '../components/images/ImageFindingsPanel.vue'), 'utf8')
    expect(src).toMatch(/HIDDEN_COLUMNS[^=]*= new Set\(\['image', 'tag', 'images', 'scanner'\]\)/)
  })
})
