/**
 * The About page's Running stack card (issue 341). Every version comes from a read (`/api/v1/meta`,
 * the cluster's scanner provenance) or from `src/version.ts`, never from the template. A read that
 * fails says why on screen and in the log (audit rules 1 and 6), and "Copy diagnostics" confirms
 * both ways with a toast.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import RunningStackCard from '@/components/about/RunningStackCard.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    getMetaApiV1MetaGet: vi.fn<() => Promise<unknown>>(),
    scannerProvenanceApiV1ScannersProvenanceGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))
vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn<() => void>(),
    info: vi.fn<() => void>(),
    warn: vi.fn<() => void>(),
    error: vi.fn<() => void>(),
  },
}))

import { getMetaApiV1MetaGet, scannerProvenanceApiV1ScannersProvenanceGet } from '@/api/generated'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'
import { APP_VERSION } from '@/version'

const metaMock = vi.mocked(getMetaApiV1MetaGet)
const provMock = vi.mocked(scannerProvenanceApiV1ScannersProvenanceGet)

const META = {
  version: '0.6.0',
  mapping_version: 18,
  envelope_versions: [3, 4],
  opensearch_version: '3.8.0',
  python_version: '3.12.13',
}
const TRIVY = {
  scanner: 'trivy',
  scanner_version: '0.74.0',
  scanner_db_version: '2',
  scanner_db_built: '2026-09-29T12:00:00Z',
}

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const failed = (status: number) => ({ data: undefined, response: { ok: false, status } }) as never

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

async function mountCard(props: { clusterId: string | null; clusterName?: string | null } = { clusterId: 'c-1', clusterName: 'prod-eu' }) {
  const wrapper = mount(RunningStackCard, { props, global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

const rowValue = (wrapper: Awaited<ReturnType<typeof mountCard>>, label: string) =>
  wrapper
    .findAll('.stack-row')
    .find((r) => r.find('.set-row-title').text() === label)
    ?.find('.stack-value')
    .text()

const writeText = vi.fn<(text: string) => Promise<void>>()

beforeEach(() => {
  setActivePinia(createPinia())
  metaMock.mockReset()
  provMock.mockReset()
  vi.mocked(logger.warn).mockReset()
  writeText.mockReset()
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
})
afterEach(() => vi.useRealTimers())

describe('This install', () => {
  it('shows every version from the meta read, plus the frontend build', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    const w = await mountCard()
    expect(rowValue(w, 'JAVV release')).toBe('v0.6.0')
    expect(rowValue(w, 'Frontend build')).toBe(`v${APP_VERSION}`)
    expect(rowValue(w, 'Store schema')).toBe('v18')
    expect(rowValue(w, 'Scanner report formats')).toBe('v3, v4')
    expect(rowValue(w, 'OpenSearch')).toBe('3.8.0')
    expect(rowValue(w, 'Python')).toBe('3.12.13')
    expect(logger.warn).not.toHaveBeenCalled()
  })

  it('says unavailable for an unreachable store, and keeps the rest', async () => {
    metaMock.mockResolvedValue(ok({ ...META, opensearch_version: null }))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    const w = await mountCard()
    expect(rowValue(w, 'OpenSearch')).toBe('unavailable')
    expect(rowValue(w, 'JAVV release')).toBe('v0.6.0')
  })

  it('shows why a failed read failed, and logs it', async () => {
    metaMock.mockResolvedValue(failed(429))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    const w = await mountCard()
    expect(w.find('.stack-install .stack-error').text()).toMatch(/busy/)
    expect(logger.warn).toHaveBeenCalledWith('about_meta_failed', { status: 429 })
    expect(rowValue(w, 'Frontend build')).toBe(`v${APP_VERSION}`) // known locally, still shown
  })
})

describe('loading', () => {
  it('holds a labelled skeleton until the reads land', async () => {
    metaMock.mockReturnValue(new Promise(() => {}) as never)
    provMock.mockReturnValue(new Promise(() => {}) as never)
    const w = mount(RunningStackCard, {
      props: { clusterId: 'c-1', clusterName: 'prod-eu' },
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(w.find('.stack-install [aria-busy="true"]').exists()).toBe(true)
    expect(w.find('.stack-scanners [aria-busy="true"]').exists()).toBe(true)
  })
})

describe('Scanners', () => {
  it('reads the selected cluster only and shows each scanner with its vulnerability database', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [TRIVY] }))
    const w = await mountCard()
    expect(provMock).toHaveBeenCalledWith(
      expect.objectContaining({ query: { cluster_id: 'c-1', runs: 1 } }),
    )
    expect(w.find('.stack-scanners .stack-group-title').text()).toContain('prod-eu')
    const row = w.find('.stack-scanners .stack-row')
    expect(row.find('.stack-value').text()).toBe('v0.74.0')
    expect(row.text()).toContain('vulnerability database 2')
    expect(row.text()).not.toContain('vuln DB')
  })

  it('re-reads when the selected cluster changes, never showing the old cluster\'s rows', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValueOnce(ok({ scanners: [TRIVY] }))
    const w = await mountCard()
    provMock.mockResolvedValueOnce(ok({ scanners: [] }))
    await w.setProps({ clusterId: 'c-2', clusterName: 'staging' })
    await flushPromises()
    expect(provMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ query: { cluster_id: 'c-2', runs: 1 } }),
    )
    expect(w.find('.stack-scanners .stack-group-title').text()).toContain('staging')
    expect(w.find('.stack-scanners').text()).toMatch(/No committed scan/)
  })

  it('drops a slow answer for a cluster that is no longer selected', async () => {
    metaMock.mockResolvedValue(ok(META))
    let answerOld!: (v: unknown) => void
    provMock.mockReturnValueOnce(new Promise((r) => (answerOld = r)) as never)
    const w = await mountCard()
    provMock.mockResolvedValueOnce(ok({ scanners: [] }))
    await w.setProps({ clusterId: 'c-2', clusterName: 'staging' })
    await flushPromises()
    answerOld(ok({ scanners: [TRIVY] })) // c-1's read lands last
    await flushPromises()
    expect(w.find('.stack-scanners').text()).toMatch(/No committed scan/)
    expect(w.find('.stack-scanners').text()).not.toContain('0.74.0')
  })

  it('says so when the cluster has no committed run yet', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    const w = await mountCard()
    expect(w.find('.stack-scanners').text()).toMatch(/No committed scan/)
  })

  it('asks for a cluster instead of reading nothing', async () => {
    metaMock.mockResolvedValue(ok(META))
    const w = await mountCard({ clusterId: null })
    expect(provMock).not.toHaveBeenCalled()
    expect(w.find('.stack-scanners').text()).toMatch(/Select a cluster/)
  })

  it('shows why the provenance read failed, and logs it', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(failed(503))
    const w = await mountCard()
    expect(w.find('.stack-scanners .stack-error').text()).toMatch(/didn't answer/)
    expect(logger.warn).toHaveBeenCalledWith('about_provenance_failed', { status: 503 })
  })
})

describe('Copy diagnostics', () => {
  it('copies every version and confirms with a toast', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [TRIVY] }))
    writeText.mockResolvedValue()
    const w = await mountCard()
    await w.find('button.stack-copy').trigger('click')
    await flushPromises()
    const text = writeText.mock.calls[0]![0]
    expect(text).toContain('JAVV release (backend): 0.6.0')
    expect(text).toContain('OpenSearch: 3.8.0')
    expect(text).toContain('trivy: 0.74.0')
    expect(text).toContain('Cluster: prod-eu (c-1)')
    expect(useToastStore().toasts.map((t) => t.kind)).toEqual(['success'])
  })

  it('fails loudly where the browser offers no clipboard (plain http)', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
    const w = await mountCard()
    await w.find('button.stack-copy').trigger('click')
    await flushPromises()
    expect(useToastStore().toasts.map((t) => t.kind)).toEqual(['error'])
    expect(logger.warn).toHaveBeenCalledWith('diagnostics_copy_failed', { reason: 'NotSupportedError' })
  })

  it('says so and logs it when the clipboard refuses', async () => {
    metaMock.mockResolvedValue(ok(META))
    provMock.mockResolvedValue(ok({ scanners: [] }))
    writeText.mockRejectedValue(new DOMException('denied', 'NotAllowedError'))
    const w = await mountCard()
    await w.find('button.stack-copy').trigger('click')
    await flushPromises()
    expect(useToastStore().toasts.map((t) => t.kind)).toEqual(['error'])
    expect(logger.warn).toHaveBeenCalledWith('diagnostics_copy_failed', { reason: 'NotAllowedError' })
  })
})
