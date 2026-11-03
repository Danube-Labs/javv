/**
 * useAuditFacets (issue 1063): the Audit log counts of the audit Filters of a dashboard panel.
 * The newest query owns the counts, and a failed read says so and logs it.
 */
import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest'
import { ref } from 'vue'

vi.mock('@/api/generated', () => ({
  auditFacetsApiV1AuditFacetsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn<() => void>(),
    info: vi.fn<() => void>(),
    warn: vi.fn<() => void>(),
    error: vi.fn<() => void>(),
  },
}))

import { auditFacetsApiV1AuditFacetsGet } from '@/api/generated'
import { useAuditFacets } from '@/composables/useAuditFacets'
import { logger } from '@/lib/logger'

const read = auditFacetsApiV1AuditFacetsGet as unknown as Mock<(...args: unknown[]) => Promise<unknown>>
const answer = (status: number, data?: unknown) => ({ response: { ok: status < 400, status }, data })
const counts = (key: string) => ({ facets: { action: [{ key, count: 1 }] } })

afterEach(() => {
  vi.clearAllMocks()
})

describe('useAuditFacets', () => {
  it('reads nothing with no query', async () => {
    const { facets, failed } = useAuditFacets(() => null)
    await flushPromises()
    expect(read).not.toHaveBeenCalled()
    expect(facets.value).toEqual({})
    expect(failed.value).toBe(false)
  })

  it('keeps the counts of the newest query when an older answer comes last', async () => {
    let first: (v: unknown) => void = () => {}
    read
      .mockImplementationOnce(() => new Promise((done) => (first = done)))
      .mockResolvedValueOnce(answer(200, counts('resolve')))
    const action = ref('note')
    const { facets } = useAuditFacets(() => ({ cluster_id: 'c1', action: [action.value] }))
    action.value = 'resolve'
    await flushPromises()
    expect(facets.value.action![0]!.key).toBe('resolve')
    first(answer(200, counts('note')))
    await flushPromises()
    expect(facets.value.action![0]!.key).toBe('resolve')
  })

  it('says that the read failed and logs its status, then clears it on the next answer', async () => {
    read.mockResolvedValueOnce(answer(503)).mockResolvedValueOnce(answer(200, counts('assign')))
    const action = ref('note')
    const { facets, failed } = useAuditFacets(() => ({ cluster_id: 'c1', action: [action.value] }))
    await flushPromises()
    expect(failed.value).toBe(true)
    expect(logger.warn).toHaveBeenCalledWith('panel_audit_facets_failed', { status: 503 })
    action.value = 'assign'
    await flushPromises()
    expect(failed.value).toBe(false)
    expect(facets.value.action![0]!.key).toBe('assign')
  })
})
