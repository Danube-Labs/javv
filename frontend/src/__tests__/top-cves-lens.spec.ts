/**
 * Top CVEs as a dashboard panel (issue 1176): the store ranks the CVEs by findings
 * (`/findings/top-values?by=cve_id`), at most 100, and the panel pages them with the shared
 * GridPager. One scanner asks the store to rank by that scanner. A now-only read.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import TopCvesLens, { type CveRow } from '@/components/dashboards/TopCvesLens.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    topValuesFindingsApiV1FindingsTopValuesGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { topValuesFindingsApiV1FindingsTopValuesGet } from '@/api/generated'

import { okWithoutBody } from './helpers/okWithoutBody'

const readMock = vi.mocked(topValuesFindingsApiV1FindingsTopValuesGet)
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const row = (value: string, per: Record<string, Record<string, number>>): CveRow => {
  const counts = Object.fromEntries(
    Object.entries(per).map(([s, sev]) => [s, Object.values(sev).reduce((n, v) => n + v, 0)]),
  )
  return {
    value,
    count: Object.values(counts).reduce((n, v) => n + v, 0),
    count_by_scanner: counts,
    severity_by_scanner: per,
  }
}
const ROWS = [
  row('CVE-2024-0003', { trivy: { high: 3 }, grype: { critical: 2 } }),
  row('CVE-2024-0001', { grype: { medium: 2, low: 2 } }),
]

const props = { clusterId: 'c-k3d-0001', t: null, scanner: 'all' as const }

function mountLens(over: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  const w = mount(TopCvesLens, { props: { ...props, ...over }, global: { plugins: [router] } })
  return { w, router }
}

describe('TopCvesLens (self-contained panel)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('reads the ranked CVEs of the cluster, and shows them in the store order', async () => {
    readMock.mockResolvedValue(ok({ by: 'cve_id', values: ROWS }))
    const { w } = mountLens()
    await flushPromises()
    expect(readMock.mock.calls[0]![0]).toEqual({
      client: {},
      query: { cluster_id: 'c-k3d-0001', by: 'cve_id' },
    })
    const cells = w.findAll('tbody tr').map((tr) => tr.findAll('td').map((td) => td.text()))
    expect(cells.map((c) => [c[0], c[2]])).toEqual([
      ['CVE-2024-0003', '5'],
      ['CVE-2024-0001', '4'],
    ])
  })

  it('shows the highest severity among the findings in the count', async () => {
    readMock.mockResolvedValue(ok({ values: ROWS }))
    const { w } = mountLens()
    await flushPromises()
    const chips = w.findAll('tbody tr').map((tr) => tr.findAll('td')[1]!.text().toLowerCase())
    expect(chips[0]).toContain('critical') // grype's critical over trivy's high
    expect(chips[1]).toContain('medium')
  })

  it('on one scanner asks the store to rank by that scanner, and reads again on a switch', async () => {
    readMock.mockResolvedValue(ok({ values: [] }))
    const { w } = mountLens({ scanner: 'grype' })
    await flushPromises()
    expect(readMock.mock.calls[0]![0]).toMatchObject({ query: { by: 'cve_id', scanner: 'grype' } })
    await w.setProps({ scanner: 'all' })
    await flushPromises()
    expect(readMock).toHaveBeenCalledTimes(2)
    expect(readMock.mock.calls[1]![0]).not.toHaveProperty('query.scanner')
  })

  it('reads with the filters of the panel, and a row opens Findings with them and the CVE', async () => {
    readMock.mockResolvedValue(ok({ values: ROWS }))
    const filters = { namespace: ['payments'], cve_id: ['CVE-1999-0001'], present: true }
    const { w, router } = mountLens({ filters })
    await flushPromises()
    expect(readMock.mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: 'c-k3d-0001', by: 'cve_id', namespace: ['payments'], all_filters: true },
    })
    await w.find('tbody tr').trigger('click')
    await flushPromises()
    // the row's CVE takes the place of the panel's CVE filter; the namespace stays
    expect(router.currentRoute.value.path).toBe('/findings')
    expect(router.currentRoute.value.query).toMatchObject({ namespace: 'payments', cve: 'CVE-2024-0003' })
  })

  it('pages 10 rows of a long board with the shared pager, and a tall panel shows 25', async () => {
    const many = Array.from({ length: 40 }, (_, i) =>
      row(`CVE-2024-${String(1000 - i)}`, { trivy: { high: 40 - i } }),
    )
    readMock.mockResolvedValue(ok({ values: many }))
    const { w } = mountLens()
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(10)
    const tall = mountLens({ pageSize: 25 }).w
    await flushPromises()
    expect(tall.findAll('tbody tr')).toHaveLength(25)
  })

  it('at a rewound T sends no read and says the ranking is for now only', async () => {
    const { w } = mountLens({ t: '2026-10-01T00:00:00Z' })
    await flushPromises()
    expect(readMock).not.toHaveBeenCalled()
    expect(w.text()).toContain('CVE ranking is a current-state read, unavailable at a rewound T.')
  })

  it('an older answer that comes last does not replace the answer of the newer read', async () => {
    let old!: (v: unknown) => void
    readMock.mockReturnValueOnce(new Promise((r) => (old = r)) as never)
    readMock.mockResolvedValueOnce(ok({ values: [ROWS[1]] }))
    const { w } = mountLens()
    await w.setProps({ clusterId: 'c-k3d-0002' })
    await flushPromises()
    old(ok({ values: ROWS }))
    await flushPromises()
    expect(w.findAll('tbody tr').map((tr) => tr.find('td').text())).toEqual(['CVE-2024-0001'])
  })

  it('shows a loading shimmer, then the empty copy or the error', async () => {
    let resolve!: (v: unknown) => void
    readMock.mockReturnValueOnce(new Promise((r) => (resolve = r)) as never)
    const { w } = mountLens()
    expect(w.find('[aria-label="Loading top CVEs"]').exists()).toBe(true)
    expect(w.text()).not.toContain('No CVE in the findings') // no claim before evidence
    resolve(ok({ values: [] }))
    await flushPromises()
    expect(w.text()).toContain('No CVE in the findings.')
    readMock.mockResolvedValueOnce({ data: null, response: { ok: false, status: 500 } } as never)
    const failed = mountLens().w
    await flushPromises()
    expect(failed.text()).toContain('CVE ranking unavailable.')
  })

  it('an OK reply whose body could not be read is a failed read, not a throw (issue 749)', async () => {
    const thrown: string[] = []
    readMock.mockResolvedValue(okWithoutBody())
    const w = mount(TopCvesLens, {
      props,
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })],
        config: { errorHandler: (err) => void thrown.push((err as Error).message) },
      },
    })
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('CVE ranking unavailable.')
  })
})
