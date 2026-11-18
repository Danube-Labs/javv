/**
 * The committed runs of one scanner on Scanner status, paged with the shared GridPager (issue
 * 1190, row 13: the paging is the shared usePagedSlice).
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScannerRunsTable from '@/components/scanners/ScannerRunsTable.vue'
import type { ScanRunRow } from '@/components/scanners/ScannerStatusCard.vue'

import { bodyRows, nextPage, pagerText, pickRowsPerPage } from './helpers/pager'

const run = (i: number): ScanRunRow => ({
  scan_run_id: `run-${i}`,
  scan_order: 100 - i,
  images: 3,
  findings_total: 10,
  fixable_total: 4,
  severity: { high: 10 },
  started_at: '2026-11-01T00:00:00Z',
  finished_at: '2026-11-01T00:05:00Z',
})
const runs = (n: number) => Array.from({ length: n }, (_, i) => run(i))

const mountTable = () => mount(ScannerRunsTable, { props: { runs: runs(30), scanner: 'trivy', cap: 50 } })

describe('ScannerRunsTable paging', () => {
  it('shows 10 runs, then the next 10', async () => {
    const w = mountTable()
    expect(pagerText(w)).toBe('Rows 1 to 10 of 30')
    expect(bodyRows(w)).toBe(10)
    await nextPage(w)
    expect(pagerText(w)).toBe('Rows 11 to 20 of 30')
  })

  it('a new number of rows per page shows page 1 with that number of rows', async () => {
    const w = mountTable()
    await nextPage(w)
    await pickRowsPerPage(w, 25)
    expect(pagerText(w)).toBe('Rows 1 to 25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('new runs show page 1', async () => {
    const w = mountTable()
    await nextPage(w)
    await w.setProps({ runs: runs(40) })
    expect(pagerText(w)).toBe('Rows 1 to 10 of 40')
  })
})
