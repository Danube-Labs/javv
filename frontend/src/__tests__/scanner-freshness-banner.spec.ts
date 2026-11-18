/**
 * The scanner freshness banner (FR-6/D20, issue 341): it appears only when a scanner has been
 * silent past the cluster's freshness window, and then carries a "What this means" link to
 * the Guide's freshness section. The copy stays plain: no em dash (operator ruling 2026-10-01).
 * A read that fails is never silent (issue 651): it logs, and a later failure keeps the last
 * good result rather than dropping it.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { scannerFreshnessApiV1ScannersFreshnessGet } from '@/api/generated'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>().mockResolvedValue({
      data: { staleness: { freshness_days: 3, scanner_down_days: 7 }, per_cluster_override: false },
      response: { ok: true, status: 200 },
    }),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)

vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn<() => void>(),
    info: vi.fn<() => void>(),
    warn: vi.fn<() => void>(),
    error: vi.fn<() => void>(),
  },
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

const DAY = 86_400
const freshness = (silentDays: number) => ({
  data: {
    scanners: [
      { scanner: 'trivy', last_ingest_at: '2026-09-27T08:34:00Z', silent_for_seconds: silentDays * DAY },
      { scanner: 'grype', last_ingest_at: '2026-10-01T08:30:00Z', silent_for_seconds: 60 },
    ],
  },
  response: { ok: true, status: 200 },
})

async function mountBanner() {
  const w = mount(ScannerFreshnessBanner, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.selectedId = 'c-1'
})
afterEach(() => {
  vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockReset()
  vi.mocked(logger.warn).mockReset()
  vi.useRealTimers()
})

const failed = (status: number) => ({ data: undefined, response: { ok: false, status } })
const POLL_MS = 10 * 60_000

describe('ScannerFreshnessBanner', () => {
  it('stays hidden while every scanner is inside the freshness window', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(2) as never)
    const w = await mountBanner()
    expect(w.find('[role=alert]').exists()).toBe(false)
    w.unmount()
  })

  it('names the silent scanner and links to the guide section on freshness', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(4) as never)
    const w = await mountBanner()
    const banner = w.find('[role=alert]')
    expect(banner.text()).toContain('trivy sent no data for 4 days')
    expect(banner.text()).not.toContain('grype')
    const link = banner.find('a.gl-text')
    expect(link.text()).toBe('What this means')
    expect(link.attributes('href')).toBe('/guide#scans-and-freshness')
    w.unmount()
  })

  it('has no em dash in its copy', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(4) as never)
    const w = await mountBanner()
    expect(w.find('[role=alert]').text()).not.toContain('—')
    w.unmount()
  })
})

describe('ScannerFreshnessBanner when the read fails (issue 651)', () => {
  it('a good read logs nothing', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(freshness(2) as never)
    const w = await mountBanner()
    expect(logger.warn).not.toHaveBeenCalled()
    w.unmount()
  })

  it('a failed first read logs once with its status and says the check failed', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(failed(500) as never)
    const w = await mountBanner()
    expect(logger.warn).toHaveBeenCalledTimes(1)
    expect(logger.warn).toHaveBeenCalledWith('scanner_freshness_fetch_failed', { status: 500 })
    expect(w.find('[role=alert]').exists()).toBe(false)
    const line = w.find('[role=status]')
    expect(line.text()).toMatch(/^The last check of the scanner freshness of c-1 failed\. JAVV tries again every 10 minutes\.$/)
    expect(line.text()).not.toContain('—')
    w.unmount()
  })

  it('a failed later poll while the scanners were fresh says when it last checked', async () => {
    vi.useFakeTimers()
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValueOnce(freshness(2) as never)
    const w = await mountBanner()
    expect(w.find('[role=status]').exists()).toBe(false)

    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValueOnce(failed(500) as never)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    const line = w.find('[role=status]')
    expect(line.text()).toMatch(/^JAVV last checked the scanner freshness at .+\. The latest check failed\./)
    expect(line.text()).not.toContain('—')

    // the next good read clears it
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValueOnce(freshness(2) as never)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(w.find('[role=status]').exists()).toBe(false)
    w.unmount()
  })

  it('a read that never reaches the server logs with no status, never an unhandled rejection', async () => {
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockRejectedValue(new TypeError('Failed to fetch'))
    const w = await mountBanner()
    expect(logger.warn).toHaveBeenCalledWith('scanner_freshness_fetch_failed', { status: null })
    w.unmount()
  })

  it('a failed later poll keeps the last good result on screen', async () => {
    vi.useFakeTimers()
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValueOnce(freshness(4) as never)
    const w = await mountBanner()
    expect(w.find('[role=alert]').text()).toContain('trivy sent no data for 4 days')

    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValueOnce(failed(502) as never)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(logger.warn).toHaveBeenCalledWith('scanner_freshness_fetch_failed', { status: 502 })
    const banner = w.find('[role=alert]')
    expect(banner.text()).toContain('trivy sent no data for 4 days')
    expect(banner.text()).toMatch(/JAVV last checked at .+\. The latest check failed\./)
    expect(w.find('[role=status]').exists()).toBe(false)
    w.unmount()
  })

  it("ignores an answer for a cluster that's no longer selected", async () => {
    let answer: (v: unknown) => void = () => {}
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet)
      .mockImplementationOnce(() => new Promise((r) => (answer = r)) as never)
      .mockResolvedValue(freshness(2) as never)
    const w = await mountBanner()
    useClusterStore().selectedId = 'c-2'
    await flushPromises()
    answer(failed(503))
    await flushPromises()
    expect(logger.warn).not.toHaveBeenCalled()
    w.unmount()
  })
})
