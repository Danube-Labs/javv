/**
 * Save this view uses the kit text box (issue 1050): the two boxes are `SettingsInput` with the
 * prose face, each label names its box, Enter saves, and the buttons are in the window footer, as
 * in the other windows.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SaveViewDialog from '@/components/findings/SaveViewDialog.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    createViewApiV1ViewsPost: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { createViewApiV1ViewsPost } from '@/api/generated'

const props = { preset: {}, workbench: { columns: [], density: 'compact', sort: [], window: '30d' } } as never

async function open() {
  const w = mount(SaveViewDialog, { props, attachTo: document.body })
  await w.find('button').trigger('click')
  return w
}

describe('Save this view (issue 1050)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(createViewApiV1ViewsPost).mockReset()
    vi.mocked(createViewApiV1ViewsPost).mockResolvedValue({ response: { ok: true, status: 201 } } as never)
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('draws the two boxes with the kit text box in the prose face', async () => {
    await open()
    for (const id of ['svd-name', 'svd-description']) {
      const box = document.getElementById(id) as HTMLInputElement
      expect(box.classList.contains('set-input'), id).toBe(true)
      expect(box.classList.contains('set-input--prose'), id).toBe(true)
    }
    expect((document.getElementById('svd-name') as HTMLInputElement).placeholder).toBe('e.g. Critical KEV backlog')
    expect((document.getElementById('svd-name') as HTMLInputElement).maxLength).toBe(128)
    expect((document.getElementById('svd-description') as HTMLInputElement).maxLength).toBe(1024)
  })

  it('links each label to its box', async () => {
    await open()
    expect(document.querySelector('label[for="svd-name"]')!.textContent).toContain('Name')
    expect(document.querySelector('label[for="svd-description"]')!.textContent).toContain('Description')
  })

  it('puts Cancel and Save view in the window footer', async () => {
    await open()
    const footer = [...document.querySelectorAll('.modal-actions button')].map((b) => b.textContent!.trim())
    expect(footer).toEqual(['Cancel', 'Save view'])
    expect(document.querySelectorAll('.modal-body button')).toHaveLength(0)
  })

  it('saves the trimmed name on Enter in a box', async () => {
    const w = await open()
    const name = w.findComponent({ name: 'SettingsInput' }).find('input')
    await name.setValue('  Critical KEV backlog  ')
    await name.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(vi.mocked(createViewApiV1ViewsPost)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(createViewApiV1ViewsPost).mock.calls[0]![0]).toMatchObject({ body: { name: 'Critical KEV backlog' } })
  })
})
