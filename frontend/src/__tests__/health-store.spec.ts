/**
 * The health store says WHAT is down (issue 675): the backend's own 503, which says so in JSON, is
 * its store; anything else (no answer, the frontend server's 502, a proxy's or an ingress's 502,
 * 503 or 504 page) is the backend itself (issue 725). The banner and the sidebar footer word the
 * two differently.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import { logger } from '@/lib/logger'
import { client } from '@/api/client'
import { downReason, useHealthStore } from '@/stores/health'

const fetchMock = vi.fn<(url: string) => Promise<Response>>()

const DEGRADED = '{"status":"degraded","opensearch":"unreachable"}'
const json = (status: number, body: string, type = 'application/json') =>
  new Response(body, { status, headers: { 'content-type': type } })
// what an nginx ingress answers for a Service with no ready pod
const ingressPage = (status: number) =>
  new Response('<html><head><title>503 Service Temporarily Unavailable</title></head></html>', {
    status,
    headers: { 'content-type': 'text/html' },
  })
const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
vi.spyOn(logger, 'info').mockImplementation(() => {})

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock.mockReset()
  warned.mockClear()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

describe('downReason', () => {
  it("the backend's own 503 is its store", () => expect(downReason(503, true)).toBe('store'))
  it('a 503 from anything in front of the backend is the backend', () => {
    expect(downReason(503, false)).toBe('backend')
  })
  it.each([undefined, 500, 502, 504, 404])('%s is the backend itself', (status) => {
    expect(downReason(status, true)).toBe('backend')
  })
})

describe('the /readyz poll', () => {
  it("the backend's degraded answer marks the store down", async () => {
    fetchMock.mockResolvedValueOnce(json(503, DEGRADED))
    const health = useHealthStore()
    await health.check()
    expect(health.degraded).toBe(true)
    expect(health.reason).toBe('store')
    expect(health.statusLabel).toBe('Store degraded')
    expect(warned).toHaveBeenCalledWith('backend degraded', { source: 'readyz', reason: 'store' })
  })

  it.each([
    ['a proxy error', () => Promise.resolve(json(502, '{"title":"Backend unavailable"}', 'application/problem+json'))],
    ['an ingress 503 page', () => Promise.resolve(ingressPage(503))],
    ['a JSON 503 that is not the degraded answer', () => Promise.resolve(json(503, '{"status":"unavailable"}'))],
    ['a 503 whose JSON does not parse', () => Promise.resolve(json(503, 'not json'))],
    ['no answer', () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('%s marks the backend down', async (_name, reply) => {
    fetchMock.mockImplementationOnce(reply)
    const health = useHealthStore()
    await health.check()
    expect(health.reason).toBe('backend')
    expect(health.statusLabel).toBe('Backend not answering')
  })

  it('a 200 clears the flag and the reason', async () => {
    const health = useHealthStore()
    health.markDegraded('backend', 'api')
    fetchMock.mockResolvedValueOnce(json(200, '{"status":"ready"}'))
    await health.check()
    expect(health.degraded).toBe(false)
    expect(health.reason).toBeNull()
    expect(health.statusLabel).toBe('Store healthy')
  })

  it('logs once per reason, not once per poll', async () => {
    const health = useHealthStore()
    health.markDegraded('backend', 'api')
    health.markDegraded('backend', 'readyz')
    expect(warned).toHaveBeenCalledTimes(1)
    health.markDegraded('store', 'readyz')
    expect(warned).toHaveBeenCalledTimes(2)
  })

  it('a dismissed banner returns on the next signal', () => {
    const health = useHealthStore()
    health.markDegraded('store', 'api')
    health.dismiss()
    expect(health.bannerVisible).toBe(false)
    health.markDegraded('store', 'readyz')
    expect(health.bannerVisible).toBe(true)
  })
})

// issue 832: a store that answers but is read-only (its disk full) or red stays in service, and
// /readyz says so in a 200 with `checks.store`
describe('a read-only or red store', () => {
  it.each(['read-only', 'red'] as const)('a /readyz 200 with checks.store %s marks it', async (store) => {
    fetchMock.mockResolvedValueOnce(json(200, JSON.stringify({ status: 'ready', checks: { store } })))
    const health = useHealthStore()
    await health.check()
    expect([health.degraded, health.reason]).toEqual([true, store])
  })

  it('a /readyz 200 with no checks clears it', async () => {
    const health = useHealthStore()
    health.markDegraded('read-only', 'api')
    fetchMock.mockResolvedValueOnce(json(200, '{"status":"ready"}'))
    await health.check()
    expect([health.degraded, health.reason]).toEqual([false, null])
  })

  it('a write the full disk refused marks it, and the caller still reads the answer', async () => {
    const body = '{"type":"store-read-only","title":"The store is read-only: its disk is full","status":503}'
    const answer = json(503, body, 'application/problem+json')
    const result = await client.post({
      baseUrl: 'http://localhost',
      url: '/api/v1/findings/bulk-triage',
      fetch: () => Promise.resolve(answer),
    })
    expect(useHealthStore().reason).toBe('read-only')
    expect((result.error as { title?: string }).title).toBe('The store is read-only: its disk is full')
  })
})

describe('the API client', () => {
  it.each([
    { name: 'the error envelope', reply: () => json(503, '{"status":503}', 'application/problem+json'), reason: 'store' },
    { name: 'an ingress 503 page', reply: () => ingressPage(503), reason: 'backend' },
    { name: 'the frontend server 502', reply: () => json(502, '{"status":502}', 'application/problem+json'), reason: 'backend' },
    { name: 'a proxy 504 page', reply: () => ingressPage(504), reason: 'backend' },
    { name: "a gateway's JSON 503", reply: () => json(503, '{"message":"no healthy upstream"}'), reason: 'backend' },
  ])('$name marks the $reason down, and the caller still reads the answer', async ({ reply, reason }) => {
    const answer = reply()
    // Node's Request needs an absolute address; in the browser the page's origin is the base
    const result = await client.get({
      baseUrl: 'http://localhost',
      url: '/api/v1/findings',
      fetch: () => Promise.resolve(answer),
    })
    expect(useHealthStore().reason).toBe(reason)
    expect(result.response?.status).toBe(answer.status)
    expect(answer.bodyUsed).toBe(true) // read once, by the client for its caller, not by the check
  })
})

describe('BackendHealthBanner', () => {
  it('is absent while healthy', () => {
    expect(mount(BackendHealthBanner).find('[role="alert"]').exists()).toBe(false)
  })

  it('names the backend when the backend is gone', () => {
    useHealthStore().markDegraded('backend', 'api')
    const text = mount(BackendHealthBanner).get('[role="alert"]').text()
    expect(text).toContain('The backend is not answering')
    expect(text).not.toContain('OpenSearch')
  })

  it('names OpenSearch when the store is down', () => {
    useHealthStore().markDegraded('store', 'api')
    expect(mount(BackendHealthBanner).get('[role="alert"]').text()).toContain('Check OpenSearch health')
  })

  it.each([
    ['read-only', 'The store is read-only: its disk is full. Reads work; changes are not saved.'],
    ['red', 'Part of the store is not available. Some screens and changes can fail until it recovers.'],
  ] as const)('a %s store is the amber line with its ruled copy', (reason, copy) => {
    useHealthStore().markDegraded(reason, 'readyz')
    const line = mount(BackendHealthBanner).get('.sys-line')
    expect(line.text()).toContain(copy)
    expect(line.classes()).toContain('tone-degraded')
    expect(line.classes()).not.toContain('tone-down')
  })

  it('an outage stays the red line', () => {
    useHealthStore().markDegraded('store', 'api')
    expect(mount(BackendHealthBanner).get('.sys-line').classes()).toContain('tone-down')
  })
})
