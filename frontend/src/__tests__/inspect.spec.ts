/**
 * Data inspector pure logic (issue 406): the rail grouping — history families collapse to one
 * summed `-*` pattern, credential indices never surface, system vs materialized split — and
 * the count/byte formatting the screen renders.
 */
import { describe, expect, it } from 'vitest'

import {
  fmtBytes,
  fmtDocs,
  fmtJobResult,
  groupIndices,
  jobFlag,
  jobLastRun,
  jobNextRun,
  jobSchedule,
  type JobDoc,
  splitMiddle,
  totalStoreBytes,
} from '@/system/inspect'

const rows = [
  // real corpus names (INDEX-MAP): rollover-suffixed per-cluster append indices
  { index: 'javv-finding-occurrences-aaa-000001', 'docs.count': '1000', 'store.size': '10mb' },
  { index: 'javv-finding-occurrences-aaa-000002', 'docs.count': '2400', 'store.size': '20mb' },
  { index: 'javv-finding-occurrences-bbb-000001', 'docs.count': '600', 'store.size': '5mb' },
  { index: 'javv-images-aaa-000001', 'docs.count': '50', 'store.size': '1mb' },
  { index: 'javv-ingest-failures-aaa-000001', 'docs.count': '7', 'store.size': '1kb' },
  { index: 'javv-ingest-failures-bbb-000001', 'docs.count': '2', 'store.size': '1kb' },
  { index: 'findings', 'docs.count': '32806', 'store.size': '64mb' },
  { index: 'javv-scan-watermarks', 'docs.count': '1400', 'store.size': '2mb' },
  { index: 'system-audit-log-000001', 'docs.count': '18000', 'store.size': '8mb' },
  { index: 'system-views', 'docs.count': '12', 'store.size': '1kb' },
  // never in the rail: credential indices (backend denies them) + dot-internal
  { index: 'system-users', 'docs.count': '7', 'store.size': '1kb' },
  { index: 'system-sessions', 'docs.count': '900', 'store.size': '1mb' },
  { index: 'system-tokens', 'docs.count': '3', 'store.size': '1kb' },
  { index: '.plugins-ml-config', 'docs.count': '1', 'store.size': '1kb' },
]

describe('groupIndices', () => {
  const groups = groupIndices(rows)

  it('collapses time-partitioned families to one summed pattern', () => {
    expect(groups.history).toContainEqual({ pattern: 'javv-finding-occurrences-*', docs: 4000 })
    expect(groups.history).toContainEqual({ pattern: 'javv-images-*', docs: 50 })
    expect(groups.history).toContainEqual({ pattern: 'javv-ingest-failures-*', docs: 9 })
    expect(groups.history).toContainEqual({ pattern: 'system-audit-log-*', docs: 18000 })
  })

  it('splits materialized state from system indices', () => {
    expect(groups.state.map((e) => e.pattern)).toEqual(['findings', 'javv-scan-watermarks'])
    expect(groups.system.map((e) => e.pattern)).toEqual(['system-views'])
  })

  it('never surfaces credential or dot-internal indices', () => {
    const all = [...groups.history, ...groups.state, ...groups.system].map((e) => e.pattern)
    for (const denied of ['system-users', 'system-sessions', 'system-tokens']) {
      expect(all).not.toContain(denied)
    }
    expect(all.some((p) => p.startsWith('.'))).toBe(false)
  })
})

describe('formatting', () => {
  it('fmtDocs compacts to the rail grammar', () => {
    expect(fmtDocs(487)).toBe('487')
    expect(fmtDocs(4363)).toBe('4.4k')
    expect(fmtDocs(28_400_000)).toBe('28.4M')
    expect(fmtDocs(1000)).toBe('1k')
  })

  it('fmtBytes renders the budget meter units', () => {
    expect(fmtBytes(612 * 1024)).toBe('612 KB')
    expect(fmtBytes(2 * 1024 * 1024)).toBe('2 MB')
    expect(fmtBytes(2.26 * 1024 ** 3)).toBe('2.3 GB')
  })

  it('fmtJobResult renders flat and nested count summaries', () => {
    expect(fmtJobResult({ staled: 0, reverted: 2 })).toBe('staled 0 · reverted 2')
    expect(fmtJobResult({ presence: { rebuilt: 66 }, rolled: 1 })).toBe(
      'presence.rebuilt 66 · rolled 1',
    )
    expect(fmtJobResult(null)).toBe('')
  })

  it('totalStoreBytes sums _cat size strings', () => {
    const total = totalStoreBytes([
      { index: 'a', 'store.size': '10mb' },
      { index: 'b', 'store.size': '512kb' },
    ])
    expect(total).toBe(10 * 1024 ** 2 + 512 * 1024)
  })
})

describe('splitMiddle (issue 652: long index names truncate in the middle)', () => {
  it('keeps the ending, which tells similar names apart, in its own part', () => {
    // the last 10 characters stay whole: the date and run number, or the `-*` pattern ending
    expect(splitMiddle('top_queries-2026.10.01-59460')).toEqual({ head: 'top_queries-2026.1', tail: '0.01-59460' })
    expect(splitMiddle('javv-finding-occurrences-*')).toEqual({ head: 'javv-finding-occ', tail: 'urrences-*' })
  })

  it('the two parts always rejoin into the full name', () => {
    for (const n of ['findings', 'system-audit-log-*', 'javv-scan-watermarks', 'a']) {
      const { head, tail } = splitMiddle(n)
      expect(head + tail).toBe(n)
    }
  })

  it('a short name keeps at least half of itself in the part that truncates', () => {
    const { head, tail } = splitMiddle('findings')
    expect(tail.length).toBeLessThanOrEqual(head.length)
  })
})

describe('the job rows (issue 556)', () => {
  const fmt = (iso: unknown) => `<${iso}>`
  const job = (over: Partial<JobDoc>): JobDoc => ({
    kind: 'report_sweep',
    status: 'done',
    capability: null,
    runnable: false,
    stale: false,
    schedule: '15 * * * *',
    next_run_at: 'N',
    health: 'ok',
    finished_at: 'F',
    started_at: 'S',
    ...over,
  })

  it('jobLastRun says how the last run ended, with the detail under it', () => {
    expect(jobLastRun(job({ result: { expired: 0, retried: 2 } }), fmt)).toEqual({
      line: '<F>',
      detail: 'expired 0 · retried 2',
      bad: false,
    })
    expect(jobLastRun(job({ result: null }), fmt)).toEqual({ line: '<F>', detail: '', bad: false })
    expect(jobLastRun(job({ status: 'failed', error: 'boom' }), fmt)).toEqual({
      line: 'failed <F>',
      detail: 'boom',
      bad: true,
    })
    expect(jobLastRun(job({ status: 'failed' }), fmt).detail).toBe('see the backend log')
    expect(jobLastRun(job({ status: 'running', requested_by: 'scheduled' }), fmt)).toEqual({
      line: 'running since <S>',
      detail: 'by scheduled',
      bad: false,
    })
    expect(jobLastRun(job({ status: 'running', stale: true }), fmt)).toEqual({
      line: 'no heartbeat since <S>',
      detail: 'You can run it again',
      bad: true,
    })
    expect(jobLastRun(job({ status: 'idle' }), fmt)).toEqual({ line: 'never', detail: '', bad: false })
  })

  it('jobFlag names each health state, with a tone from the health ramp', () => {
    expect(jobFlag(job({ health: 'ok' }))).toEqual({ tone: 'ok', label: 'on schedule' })
    expect(jobFlag(job({ health: 'overdue' }))).toEqual({ tone: 'warn', label: 'late' })
    expect(jobFlag(job({ health: 'failed' }))).toEqual({ tone: 'down', label: 'failed' })
    expect(jobFlag(job({ health: 'never_ran' }))).toEqual({ tone: 'muted', label: 'not run yet' })
  })

  it('jobFlag says what is off: the scheduler, or the job has no schedule', () => {
    expect(jobFlag(job({ health: 'off' }))).toEqual({ tone: 'muted', label: 'scheduler off' })
    expect(jobFlag(job({ health: 'off', schedule: null }))).toEqual({ tone: 'muted', label: 'not scheduled' })
  })

  it('jobSchedule is the cron expression, or why there is none', () => {
    expect(jobSchedule(job({}))).toBe('15 * * * *')
    expect(jobSchedule(job({ schedule: null, runnable: true }))).toBe('by hand only')
    expect(jobSchedule(job({ schedule: null, runnable: false }))).toBe('switched off')
  })

  it('jobNextRun is a dash when nothing is going to run it', () => {
    expect(jobNextRun(job({}), fmt)).toBe('<N>')
    expect(jobNextRun(job({ next_run_at: null }), fmt)).toBe('-')
  })
})
