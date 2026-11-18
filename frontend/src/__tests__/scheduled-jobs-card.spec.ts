/**
 * The Scheduled jobs card (issue 556): the jobs the backend only runs on its schedule, in the
 * same table as Repair actions, read-only, with a status chip on every row.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as sdk from '@/api/generated'
import RepairActionsCard from '@/components/system/RepairActionsCard.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listJobsApiV1AdminJobsGet: vi.fn<() => Promise<unknown>>(),
    triggerJobApiV1AdminJobsKindRunPost: vi.fn<() => Promise<unknown>>(),
    changePasswordAuthPasswordPost: vi.fn<() => Promise<unknown>>(),
    loginAuthLoginPost: vi.fn<() => Promise<unknown>>(),
    logoutAuthLogoutPost: vi.fn<() => Promise<unknown>>(),
    meAuthMeGet: vi.fn<() => Promise<unknown>>(),
  }),
)

const idle = { status: 'idle', stale: false, next_run_at: null }
const JOBS = [
  { ...idle, kind: 'rebuild_state', capability: 'can_rebuild_state', runnable: true, schedule: null, health: 'off' },
  {
    ...idle,
    kind: 'staleness_sweep',
    capability: 'can_manage_settings',
    runnable: true,
    schedule: '0 2 * * *',
    next_run_at: '2026-10-03T02:00:00+00:00',
    health: 'overdue',
  },
  {
    kind: 'report_drain',
    capability: null,
    runnable: false,
    stale: false,
    status: 'done',
    finished_at: '2026-10-02T12:55:00+00:00',
    result: { jobs: 2 },
    schedule: '*/5 * * * *',
    next_run_at: '2026-10-02T13:00:00+00:00',
    health: 'ok',
  },
  {
    kind: 'findings_cleanup',
    capability: null,
    runnable: false,
    stale: false,
    status: 'failed',
    finished_at: '2026-10-02T04:00:00+00:00',
    error: 'ConnectionTimeout',
    schedule: '0 4 * * *',
    next_run_at: '2026-10-03T04:00:00+00:00',
    health: 'failed',
  },
  { ...idle, kind: 'session_sweep', capability: null, runnable: false, schedule: null, health: 'off' },
]

const card = async (scheduler: { enabled: boolean; timezone: string }, jobs = JOBS) => {
  vi.mocked(sdk.listJobsApiV1AdminJobsGet).mockResolvedValue({
    response: { ok: true },
    data: { jobs, scheduler },
  } as never)
  const w = mount(RepairActionsCard)
  await flushPromises()
  return w
}
const ON = { enabled: true, timezone: 'Europe/Bucharest' }

describe('the Scheduled jobs card', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('lists the scheduled-only jobs in the table with schedule, last run, next run and chip, and no button', async () => {
    const w = await card(ON)
    const rows = w.findAll('section.scheduled .repair-row')
    expect(rows.map((r) => r.find('.job-id b').text())).toEqual([
      'Export queue',
      'Old findings cleanup',
      'Expired sessions',
    ])
    const cells = rows[0]!.findAll('td').map((c) => c.text())
    expect(cells[1]).toBe('*/5 * * * *')
    expect(cells[2]).toContain('jobs 2')
    expect(cells[3]).not.toBe('-')
    expect(rows[0]!.find('.dw').text()).toBe('on schedule')
    expect(rows[1]!.find('.dw').text()).toBe('failed')
    expect(rows[1]!.find('.job-failed').text()).toContain('ConnectionTimeout')
    expect(w.find('section.scheduled').findAll('button')).toHaveLength(0)
    expect(w.find('section.scheduled').findAll('th').map((t) => t.text())).toEqual([
      'Job',
      'Schedule',
      'Last run',
      'Next run',
      'Status',
    ])
  })

  it('a job switched off says so: no schedule, no next run, a "not scheduled" chip', async () => {
    const w = await card(ON)
    const off = w.findAll('section.scheduled .repair-row')[2]!
    const cells = off.findAll('td').map((c) => c.text())
    expect(cells[1]).toBe('switched off')
    expect(cells[2]).toBe('never')
    expect(cells[3]).toBe('-')
    expect(off.find('.dw').text()).toBe('not scheduled')
  })

  it('names the timezone the schedules are read in', async () => {
    const w = await card(ON)
    expect(w.find('section.scheduled .repair-sub').text()).toContain('time zone of the backend (Europe/Bucharest)')
    expect(w.find('section.scheduled .repair-sub').text()).not.toContain('The scheduler of this backend is off')
  })

  it('says so when the scheduler is switched off on this backend', async () => {
    const w = await card({ enabled: false, timezone: 'UTC' })
    expect(w.find('section.scheduled .repair-sub').text()).toContain('The scheduler of this backend is off')
  })

  it('is not drawn when the route lists no scheduled-only job', async () => {
    const w = await card(ON, JOBS.filter((j) => j.runnable))
    expect(w.find('section.scheduled').exists()).toBe(false)
  })
})

describe('Repair actions, the scheduled rows', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('the same table, with the Run buttons in a last column', async () => {
    const w = await card(ON)
    const repair = w.findAll('section')[0]!
    expect(repair.findAll('th')).toHaveLength(6)
    const [rebuild, staleness] = repair.findAll('.repair-row')
    const cells = (row: typeof rebuild) => row!.findAll('td').map((c) => c.text())
    expect(cells(staleness)[1]).toBe('0 2 * * *')
    expect(staleness!.find('.dw').text()).toBe('late')
    expect(cells(rebuild)[1]).toBe('by hand only')
    expect(cells(rebuild)[3]).toBe('-')
    expect(rebuild!.find('.dw').text()).toBe('not scheduled')
    expect(cells(rebuild)[5]).toBe('Run')
  })
})
