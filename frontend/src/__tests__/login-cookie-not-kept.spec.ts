/**
 * A sign-in that answers 200 with no session after it (issue 869): the browser did not keep the
 * cookie. On plain http a browser refuses the Secure cookie, so the form names the setting and
 * https (ruled copy B, 2026-10-15); on https or localhost it says the session was not kept. Before,
 * the form reported success and the page showed sign-in again with no message.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { logger } from '@/lib/logger'
import {
  COOKIE_REFUSED_ON_HTTP_COPY,
  SERVER_DOWN_COPY,
  SESSION_NOT_KEPT_COPY,
  useAuthStore,
} from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'

type Answer = { data?: unknown; error?: unknown; response?: { ok: boolean; status: number } }
const login = vi.fn<() => Promise<Answer>>()
const me = vi.fn<() => Promise<Answer>>()
vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    meAuthMeGet: () => me(),
    loginAuthLoginPost: () => login(),
    changePasswordAuthPasswordPost: vi.fn<() => Promise<Answer>>(),
    logoutAuthLogoutPost: vi.fn<() => Promise<Answer>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))
const push = vi.fn<(to: unknown) => Promise<void>>()
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ push }),
}))

const signedIn: Answer = { data: {}, response: { ok: true, status: 200 } }
const noSession: Answer = { error: { status: 401 }, response: { ok: false, status: 401 } }
const user = { username: 'admin', role: 'admin', capabilities: ['*'], must_change: false }

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
  me.mockReset()
  push.mockReset()
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('a sign-in whose cookie the browser did not keep', () => {
  it('on plain http, names the setting and https, and stays on sign-in', async () => {
    vi.stubGlobal('isSecureContext', false)
    const warn = vi.spyOn(logger, 'warn')
    login.mockResolvedValueOnce(signedIn)
    me.mockResolvedValueOnce(noSession)
    const w = await signIn()
    expect(w.get('[role="alert"]').text()).toBe(COOKIE_REFUSED_ON_HTTP_COPY)
    expect(COOKIE_REFUSED_ON_HTTP_COPY).toBe(
      'This browser refused the session cookie, because the page uses http. Use https, or ask ' +
        'the admin to set JAVV_SESSION_COOKIE_SECURE=false.',
    )
    expect(push).not.toHaveBeenCalled()
    expect(useAuthStore().unreachable).toBe(false)
    expect(warn).toHaveBeenCalledWith('session not kept after sign-in', { secure_context: false })
  })

  it('on https or localhost, says the session was not kept', async () => {
    vi.stubGlobal('isSecureContext', true)
    login.mockResolvedValueOnce(signedIn)
    me.mockResolvedValueOnce(noSession)
    const w = await signIn()
    expect(w.get('[role="alert"]').text()).toBe(SESSION_NOT_KEPT_COPY)
    expect(SESSION_NOT_KEPT_COPY).toBe(
      'Signed in, but this browser did not keep the session. Allow cookies for this site, then ' +
        'sign in again.',
    )
    expect(push).not.toHaveBeenCalled()
  })

  it('a session check that fails on the server is "not answering", not the cookie', async () => {
    vi.stubGlobal('isSecureContext', false)
    login.mockResolvedValueOnce(signedIn)
    me.mockResolvedValueOnce({ response: { ok: false, status: 503 } })
    const w = await signIn()
    expect(w.get('[role="alert"]').text()).toBe(SERVER_DOWN_COPY)
  })

  it('a session that the browser kept signs in with no message', async () => {
    vi.stubGlobal('isSecureContext', false)
    login.mockResolvedValueOnce(signedIn)
    me.mockResolvedValueOnce({ data: { user }, response: { ok: true, status: 200 } })
    const w = await signIn()
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(push).toHaveBeenCalledWith('/overview')
  })
})
