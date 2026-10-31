/**
 * The value search of the filter bar (issue 1064): debounced from 2 letters, the newest text
 * wins, and an answer belongs to the field and text it was asked for. The findings search sends
 * the list's own query with one field and the text.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/generated', () => ({
  facetFindingsApiV1FindingsFacetsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  auditFacetsApiV1AuditFacetsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  approvalListApiV1DecisionsApprovalsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import {
  approvalListApiV1DecisionsApprovalsGet,
  auditFacetsApiV1AuditFacetsGet,
  facetFindingsApiV1FindingsFacetsGet,
} from '@/api/generated'
import { APPROVAL_FIELDS } from '@/approvals/fields.config'
import { AUDIT_FIELDS } from '@/audit/fields.config'
import {
  approvalsValueSearch,
  auditValueSearch,
  findingsValueSearch,
  useValueSearch,
} from '@/composables/useValueSearch'
import type { ValueSearch, ValueSearchFn } from '@/filters/facets'
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

const NAMESPACE = FINDINGS_FIELDS.find((f) => f.key === 'namespace')!
const ASSIGNEE = FINDINGS_FIELDS.find((f) => f.key === 'assignee')!
const CVE = FINDINGS_FIELDS.find((f) => f.key === 'cve')!
const found = (key: string): ValueSearch => ({ buckets: [{ key, count: 1, by_scanner: {} }], more: false })

describe('useValueSearch', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('asks after a pause, from 2 letters, and keeps the answer for its field and text', async () => {
    const search = vi.fn<ValueSearchFn>(async (_f, text) => found(`ns-${text}`))
    const s = useValueSearch()
    s.ask(search, NAMESPACE, 'p')
    await vi.advanceTimersByTimeAsync(300)
    expect(search).not.toHaveBeenCalled() // one letter is not a search

    s.ask(search, NAMESPACE, ' pay ')
    await vi.advanceTimersByTimeAsync(200)
    expect(search).not.toHaveBeenCalled() // still in the pause
    await vi.advanceTimersByTimeAsync(100)
    expect(search).toHaveBeenCalledWith(NAMESPACE, 'pay')
    expect(s.resultFor('namespace', 'pay')).toEqual(found('ns-pay'))
    expect(s.resultFor('namespace', 'pa')).toBeNull() // another text
    expect(s.resultFor('assignee', 'pay')).toBeNull() // another field
  })

  it('typing on sends one request, for the last text', async () => {
    const search = vi.fn<ValueSearchFn>(async (_f, text) => found(text))
    const s = useValueSearch()
    for (const text of ['pa', 'pay', 'paym']) {
      s.ask(search, NAMESPACE, text)
      await vi.advanceTimersByTimeAsync(100)
    }
    await vi.advanceTimersByTimeAsync(300)
    expect(search.mock.calls.map(([, text]) => text)).toEqual(['paym'])
  })

  it('an older answer that lands last does not replace the newer one', async () => {
    let release: (v: ValueSearch) => void = () => {}
    const slow = new Promise<ValueSearch>((r) => (release = r))
    const search = vi.fn<ValueSearchFn>((_f, text) => (text === 'pa' ? slow : Promise.resolve(found(text))))
    const s = useValueSearch()
    s.ask(search, NAMESPACE, 'pa')
    await vi.advanceTimersByTimeAsync(300)
    s.ask(search, NAMESPACE, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    release(found('old'))
    await vi.advanceTimersByTimeAsync(0)
    expect(s.resultFor('namespace', 'pay')).toEqual(found('pay'))
    expect(s.resultFor('namespace', 'pa')).toBeNull()
  })

  it('a failed search says so, and the next text clears it', async () => {
    const search = vi.fn<ValueSearchFn>(async (_f, text) => (text === 'pay' ? null : found(text)))
    const s = useValueSearch()
    s.ask(search, NAMESPACE, 'pay')
    await vi.advanceTimersByTimeAsync(300)
    expect(s.failed.value).toBe(true)
    expect(s.resultFor('namespace', 'pay')).toBeNull()
    s.ask(search, NAMESPACE, 'p')
    expect(s.failed.value).toBe(false)
  })

  it('reset drops a search in its pause and an answer in flight', async () => {
    const search = vi.fn<ValueSearchFn>(async (_f, text) => found(text))
    const s = useValueSearch()
    s.ask(search, NAMESPACE, 'pay')
    s.reset()
    await vi.advanceTimersByTimeAsync(300)
    expect(search).not.toHaveBeenCalled()
  })
})

describe('findingsValueSearch', () => {
  const ok = (body: unknown) => ({ data: body, response: { ok: true, status: 200 } })

  it('sends the query of the list with the facet of the field and the text', async () => {
    vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockResolvedValue(
      ok({ facets: { assignee: [{ key: 'paula', count: 2, by_scanner: { trivy: 2 } }] }, more: true }) as never,
    )
    const search = findingsValueSearch(() => ({ cluster_id: 'c1', scanner: 'grype', severity: ['high'] }))
    expect(await search(ASSIGNEE, 'pau')).toEqual({
      buckets: [{ key: 'paula', count: 2, by_scanner: { trivy: 2 } }],
      more: true,
    })
    expect(vi.mocked(facetFindingsApiV1FindingsFacetsGet).mock.calls.at(-1)![0]).toMatchObject({
      query: { cluster_id: 'c1', scanner: 'grype', severity: ['high'], fields: ['assignee'], contains: 'pau' },
    })
  })

  it('a refused read is a failed search', async () => {
    vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockResolvedValue({
      data: undefined,
      response: { ok: false, status: 422 },
    } as never)
    expect(await findingsValueSearch(() => ({ cluster_id: 'c1' }))(NAMESPACE, 'pay')).toBeNull()
  })

  it('no query or a field with no facet asks nothing', async () => {
    vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockClear()
    expect(await findingsValueSearch(() => null)(NAMESPACE, 'pay')).toBeNull()
    expect(await findingsValueSearch(() => ({ cluster_id: 'c1' }))(CVE as FilterField, 'pay')).toBeNull()
    expect(facetFindingsApiV1FindingsFacetsGet).not.toHaveBeenCalled()
  })
})

describe('auditValueSearch (Audit log User list)', () => {
  const ok = (body: unknown) => ({ data: body, response: { ok: true, status: 200 } })
  const USER = AUDIT_FIELDS.find((f) => f.key === 'actor')!
  const ACTION = AUDIT_FIELDS.find((f) => f.key === 'action')!

  it('sends the query of the list with the text, and reads the actor values', async () => {
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue(
      ok({ facets: { actor: [{ key: 'svc-pay', count: 3, by_scanner: {} }] }, more: true }) as never,
    )
    const search = auditValueSearch(() => ({ cluster_id: 'c1', action: ['assign'], actor: ['ann'] }))
    expect(await search(USER, 'pay')).toEqual({
      buckets: [{ key: 'svc-pay', count: 3, by_scanner: {} }],
      more: true,
    })
    expect(vi.mocked(auditFacetsApiV1AuditFacetsGet).mock.calls.at(-1)![0]).toMatchObject({
      query: { cluster_id: 'c1', action: ['assign'], actor: ['ann'], contains: 'pay' },
    })
  })

  it('a refused read is a failed search; another field or no query asks nothing', async () => {
    // a refusal carries an error body: the status decides, not the body
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue({
      data: { detail: 'contains takes no interval' },
      response: { ok: false, status: 422 },
    } as never)
    expect(await auditValueSearch(() => ({ cluster_id: 'c1' }))(USER, 'pay')).toBeNull()
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockClear()
    expect(await auditValueSearch(() => ({ cluster_id: 'c1' }))(ACTION, 'pay')).toBeNull()
    expect(await auditValueSearch(() => null)(USER, 'pay')).toBeNull()
    expect(auditFacetsApiV1AuditFacetsGet).not.toHaveBeenCalled()
  })
})

describe('approvalsValueSearch (Approvals Approver list)', () => {
  const ok = (body: unknown) => ({ data: body, response: { ok: true, status: 200 } })
  const APPROVER = APPROVAL_FIELDS.find((f) => f.key === 'approver')!
  const STATUS = APPROVAL_FIELDS.find((f) => f.key === 'status')!

  it('sends the query of the queue with the text; a bucket gets an empty scanner split', async () => {
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValue(
      ok({ facets: { created_by: [{ key: 'Lead-Pay', count: 2 }] }, more: false }) as never,
    )
    const search = approvalsValueSearch(() => ({ cluster_id: 'c1', status: ['expiring'], warn_days: 7 }))
    expect(await search(APPROVER, 'pay')).toEqual({
      buckets: [{ key: 'Lead-Pay', count: 2, by_scanner: {} }],
      more: false,
    })
    expect(vi.mocked(approvalListApiV1DecisionsApprovalsGet).mock.calls.at(-1)![0]).toMatchObject({
      query: { cluster_id: 'c1', status: ['expiring'], warn_days: 7, contains: 'pay' },
    })
  })

  it('a refused read is a failed search; another field or no query asks nothing', async () => {
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValue({
      data: undefined,
      response: { ok: false, status: 403 },
    } as never)
    expect(await approvalsValueSearch(() => ({ cluster_id: 'c1' }))(APPROVER, 'pay')).toBeNull()
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockClear()
    expect(await approvalsValueSearch(() => ({ cluster_id: 'c1' }))(STATUS, 'pay')).toBeNull()
    expect(await approvalsValueSearch(() => null)(APPROVER, 'pay')).toBeNull()
    expect(approvalListApiV1DecisionsApprovalsGet).not.toHaveBeenCalled()
  })
})
