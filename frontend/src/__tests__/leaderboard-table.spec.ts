/**
 * The Contributors leaderboard, paged with the shared GridPager (issue 1190, row 13: the paging
 * is the shared usePagedSlice).
 */
import { mount, RouterLinkStub } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LeaderboardTable from '@/components/contributors/LeaderboardTable.vue'
import type { BoardRow } from '@/contributors/viewModel'

import { bodyRows, nextPage, pagerText, pickRowsPerPage } from './helpers/pager'

// the server's order is the reverse of the ranking: user-29 resolved the most
const actor = (i: number): BoardRow => ({
  actor: `user-${String(i).padStart(2, '0')}`,
  actions: 1 + i,
  by_action: { resolve: 1 + i },
  handled: 1 + i,
  median_ttr_seconds: null,
  sla_hit_pct: null,
})
const board = (n: number) => Array.from({ length: n }, (_, i) => actor(i))

const mountTable = () =>
  mount(LeaderboardTable, {
    props: { rows: board(30), cap: 100 },
    global: { stubs: { RouterLink: RouterLinkStub } },
  })

describe('LeaderboardTable paging', () => {
  it('shows 10 people, then the next 10', async () => {
    const w = mountTable()
    expect(pagerText(w)).toBe('Rows 1 to 10 of 30')
    expect(bodyRows(w)).toBe(10)
    expect(w.find('tbody tr').text()).toContain('user-29') // the pages hold the ranked board
    await nextPage(w)
    expect(pagerText(w)).toBe('Rows 11 to 20 of 30')
    expect(w.find('tbody tr').text()).toContain('user-19')
  })

  it('a new number of rows per page shows page 1 with that number of rows', async () => {
    const w = mountTable()
    await nextPage(w)
    await pickRowsPerPage(w, 25)
    expect(pagerText(w)).toBe('Rows 1 to 25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('a new board shows page 1', async () => {
    const w = mountTable()
    await nextPage(w)
    await w.setProps({ rows: board(40) })
    expect(pagerText(w)).toBe('Rows 1 to 10 of 40')
  })
})
