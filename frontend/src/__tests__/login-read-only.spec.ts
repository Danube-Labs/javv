/**
 * Sign-in writes a session first, so a store whose disk is full refuses it (issue 832). The form
 * says why in the ruled words, not "The server is not answering", and it does not start the
 * server-down re-check: the server answers, it only cannot save.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { READ_ONLY_COPY, SERVER_DOWN_COPY, useAuthStore } from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'

type Answer = { data?: unknown; error?: unknown; response?: { ok: boolean; status: number } }
const login = vi.fn<() => Promise<Answer>>()
vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    meAuthMeGet: vi.fn<() => Promise<Answer>>(),
    loginAuthLoginPost: () => login(),
    logoutAuthLogoutPost: vi.fn<() => Promise<Answer>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ push: vi.fn<(to: unknown) => Promise<void>>() }),
}))

const refused = (error: unknown): Answer => ({ error, response: { ok: false, status: 503 } })

async function signIn() {
  const w = mount(LoginView)
  await w.get('#username').setValue('admin')
  await w.get('#password').setValue('the right one')
  await w.get('form').trigger('submit')
  await flushPromises()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  login.mockReset()
})

describe('sign-in against a read-only store', () => {
  it('says the store is read-only, and is not "the server is down"', async () => {
    login.mockResolvedValueOnce(
      refused({ type: 'store-read-only', title: 'The store is read-only: its disk is full', status: 503 }),
    )
    const w = await signIn()
    expect(w.get('[role="alert"]').text()).toBe('The store is read-only: its disk is full.')
    expect(READ_ONLY_COPY).toBe('The store is read-only: its disk is full.')
    expect(useAuthStore().unreachable).toBe(false)
  })

  it('any other 503 is still the server not answering', async () => {
    login.mockResolvedValueOnce(refused({ title: 'Search backend unavailable', status: 503 }))
    const w = await signIn()
    expect(w.get('[role="alert"]').text()).toBe(SERVER_DOWN_COPY)
  })
})
