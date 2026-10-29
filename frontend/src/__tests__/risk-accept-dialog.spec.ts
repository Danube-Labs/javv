/**
 * The risk-accept dialog when the server refuses (issue 909, operator 2026-10-18): a 403 names who
 * can accept a risk, in the role names the UI shows, not the internal capability. The expiry
 * starts at tomorrow in UTC, and a refused expiry names the date (issue 984).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EXPIRY_PASSED_TYPE } from '@/api/problem'
import { EXPIRY_REFUSED } from '@/approvals/viewModel'
import RiskAcceptDialog from '@/components/triage/RiskAcceptDialog.vue'
import { useClusterStore } from '@/stores/cluster'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    createApiV1DecisionsPost: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { createApiV1DecisionsPost } from '@/api/generated'

const finding = {
  finding_key: 'fk-1',
  cve_id: 'CVE-2026-0001',
  scanner: 'trivy',
  state: 'open',
  namespaces: ['shop'],
  image_repo: 'registry.example/auth',
  tag: '5.2.4',
  image_digest: 'sha256:abc',
} as never

const createButton = () =>
  [...document.body.querySelectorAll('button')].find((b) => b.textContent!.includes('Create decision'))!

async function open(expiry = '') {
  const w = mount(RiskAcceptDialog, {
    props: { cveId: 'CVE-2026-0001', finding },
    attachTo: document.body,
  })
  const just = document.body.querySelector<HTMLTextAreaElement>('#ra-just')!
  just.value = 'No fix yet.'
  just.dispatchEvent(new Event('input'))
  const date = document.body.querySelector<HTMLInputElement>('#ra-expiry')!
  date.value = expiry
  date.dispatchEvent(new Event('input'))
  await w.vm.$nextTick()
  return w
}

async function submitWith(status: number, type?: string) {
  vi.mocked(createApiV1DecisionsPost).mockResolvedValueOnce({
    error: { title: 'refused', status, ...(type ? { type } : {}) },
    request: {},
    response: { ok: false, status },
  } as never)
  await open()
  createButton().click()
  await flushPromises()
  return document.body.querySelector('.ra-error')?.textContent
}

describe('RiskAcceptDialog refusals', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = ''
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'c-1' }] as never
    useClusterStore().selectedId = 'c-1'
  })

  it('a 403 says who can accept a risk', async () => {
    expect(await submitWith(403)).toBe('Only a Security Lead or an admin can accept a risk.')
  })

  it('another failure keeps its own text', async () => {
    expect(await submitWith(503)).toBe('Could not create the decision. Check the backend connection.')
  })
})

describe('RiskAcceptDialog expiry (issue 984)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T23:30:00Z')) // east of UTC it is already the 24th
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = ''
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'c-1' }] as never
    useClusterStore().selectedId = 'c-1'
  })
  afterEach(() => vi.useRealTimers())

  it('the date field starts at tomorrow in UTC', async () => {
    await open()
    expect(document.body.querySelector('#ra-expiry')!.getAttribute('min')).toBe('2026-10-24')
  })

  it('a typed date of today or before keeps Create disabled and says why', async () => {
    for (const day of ['2026-09-30', '2026-10-23']) {
      document.body.innerHTML = ''
      await open(day)
      expect({ day, disabled: createButton().disabled }).toEqual({ day, disabled: true })
      expect(document.body.textContent).toContain(EXPIRY_REFUSED)
    }
  })

  it('uses the shared text box, and marks a refused date invalid (issue 1050)', async () => {
    await open('2026-10-23')
    const date = document.body.querySelector('#ra-expiry')!
    expect([...date.classList]).toEqual(['set-input', 'set-input--invalid'])
    expect(document.body.querySelector('textarea')!.className).toBe('set-input set-input--prose')
    document.body.innerHTML = ''
    await open('2026-10-24')
    expect([...document.body.querySelector('#ra-expiry')!.classList]).toEqual(['set-input'])
  })

  it('tomorrow, or no date, can be sent', async () => {
    for (const day of ['2026-10-24', '']) {
      document.body.innerHTML = ''
      await open(day)
      expect({ day, disabled: createButton().disabled }).toEqual({ day, disabled: false })
      expect(document.body.textContent).not.toContain(EXPIRY_REFUSED)
    }
  })

  it('the server refusing the expiry names the date', async () => {
    expect(await submitWith(422, EXPIRY_PASSED_TYPE)).toBe(EXPIRY_REFUSED)
  })

  it('another 422 keeps the general text', async () => {
    expect(await submitWith(422)).toBe('Could not create the decision. Check the backend connection.')
  })
})
