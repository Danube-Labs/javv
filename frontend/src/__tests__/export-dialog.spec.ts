/**
 * The export dialog shows why an export is blocked and turns its button off, on the tab the user
 * is on (issue 962). The rules themselves are pinned in export-params.spec.ts; this spec pins
 * that the dialog uses them.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ExportDialog from '@/components/findings/ExportDialog.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { useClusterStore } from '@/stores/cluster'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    enqueueReportApiV1ReportsPost: vi.fn<() => Promise<unknown>>(),
    getReportApiV1ReportsReportIdGet: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

const button = (text: string) =>
  [...document.body.querySelectorAll('button')].find((b) => b.textContent!.trim() === text)!
// the past-time note shares the .ex-blocked style; the block message is the other one
const blockText = () =>
  [...document.body.querySelectorAll('.ex-blocked')]
    .map((p) => p.textContent!.trim())
    .find((text) => !text.startsWith('Rewound'))

async function openWith(
  selections: Record<string, string[]>,
  modes: Record<string, 'is' | 'not'> = {},
  historical = false,
) {
  mount(ExportDialog, {
    props: { fields: FINDINGS_FIELDS, selections, modes, historical },
    attachTo: document.body,
  })
  button('Export CSV').click()
  await flushPromises()
}

describe('ExportDialog blocks what the backend refuses', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'c-1' }] as never
    useClusterStore().selectedId = 'c-1'
  })

  it('Assignee with Unassigned: both tabs say why and turn their button off', async () => {
    await openWith({ assignee: ['bob'], attr: ['unassigned'] })
    const message = 'An export cannot use Assignee and Unassigned together. Clear one of them.'
    expect(blockText()).toBe(message)
    expect(button('Download').disabled).toBe(true)
    button('Schedule off-peak').click()
    await flushPromises()
    expect(blockText()).toBe(message)
    expect(button('Schedule').disabled).toBe(true)
  })

  it('Scanner is not trivy: CSV can download, VEX is blocked', async () => {
    await openWith({ scanner: ['trivy'] }, { scanner: 'not' })
    expect(blockText()).toBeUndefined()
    expect(button('Download').disabled).toBe(false)
    button('VEX (OpenVEX)').click()
    await flushPromises()
    expect(blockText()).toBe('A VEX file covers one scanner. Clear the Scanner filter first.')
    expect(button('Download').disabled).toBe(true)
  })

  it('Scanner is grype: the VEX file starts on grype, and trivy is blocked', async () => {
    await openWith({ scanner: ['grype'] })
    button('VEX (OpenVEX)').click()
    await flushPromises()
    expect(blockText()).toBeUndefined()
    button('trivy').click()
    await flushPromises()
    expect(blockText()).toBe('This screen shows grype findings only. Pick grype for the VEX file.')
    expect(button('Download').disabled).toBe(true)
  })

  it('at a past time, Search blocks the schedule', async () => {
    await openWith({ q: ['openssl'] }, {}, true)
    expect(blockText()).toBe('At a past time, a schedule cannot use these filters: Search. Clear them.')
    expect(button('Schedule').disabled).toBe(true)
  })
})
