/**
 * The risk-accept dialog when the server refuses (issue 909, operator 2026-10-18): a 403 names who
 * can accept a risk, in the role names the UI shows, not the internal capability.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

async function submitWith(status: number) {
  vi.mocked(createApiV1DecisionsPost).mockResolvedValueOnce({
    error: { title: 'refused', status },
    request: {},
    response: { ok: false, status },
  } as never)
  const w = mount(RiskAcceptDialog, {
    props: { cveId: 'CVE-2026-0001', finding },
    attachTo: document.body,
  })
  const just = document.body.querySelector<HTMLTextAreaElement>('#ra-just')!
  just.value = 'No fix yet.'
  just.dispatchEvent(new Event('input'))
  await w.vm.$nextTick()
  ;[...document.body.querySelectorAll('button')].find((b) => b.textContent!.includes('Create decision'))!.click()
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
