/**
 * The forced password change says the rule and why a password was refused (issue 726): the form
 * showed no rule, and a 422 from the server was replaced by "check the current password and
 * policy", a policy the page never named.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  passwordLength,
  useAuthStore,
} from '@/stores/auth'
import LoginView from '@/views/LoginView.vue'

type Answer = { data?: unknown; error?: unknown; response?: { ok: boolean; status: number } }
const changePassword = vi.fn<(opts: { body: unknown }) => Promise<Answer>>()
const me = vi.fn<() => Promise<Answer>>()
const push = vi.fn<(to: unknown) => Promise<void>>(() => Promise.resolve())
vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    meAuthMeGet: () => me(),
    loginAuthLoginPost: vi.fn<() => Promise<Answer>>(),
    changePasswordAuthPasswordPost: (opts: { body: unknown }) => changePassword(opts),
    logoutAuthLogoutPost: vi.fn<() => Promise<Answer>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRouter: () => ({ push }),
}))

const refused = (status: number, error?: unknown): Answer => ({
  error,
  response: { ok: false, status },
})

const signedIn = (mustChange: boolean): Answer => ({
  data: { user: { username: 'admin', role: 'admin', capabilities: ['*'], must_change: mustChange } },
  response: { ok: true, status: 200 },
})

beforeEach(() => {
  setActivePinia(createPinia())
  changePassword.mockReset()
  me.mockReset().mockResolvedValue(signedIn(true)) // the session is live unless a test says not
  push.mockClear()
})

function mountChange() {
  useAuthStore().user = { username: 'admin', role: 'admin', capabilities: ['*'], must_change: true }
  return mount(LoginView)
}

async function submit(w: ReturnType<typeof mount>, next: string, confirm = next) {
  await w.get('#current').setValue('the-seeded-one')
  await w.get('#new').setValue(next)
  await w.get('#confirm').setValue(confirm)
  await w.get('form').trigger('submit')
  await flushPromises()
}

describe('the password rule', () => {
  it('is on the form, and the new-password field points at it', () => {
    const w = mountChange()
    const rule = w.get('#password-rule')
    expect(rule.text()).toContain(`At least ${PASSWORD_MIN_LENGTH} characters.`)
    expect(w.get('#new').attributes('aria-describedby')).toBe('password-rule')
  })

  it('is the server rule: the constants equal the backend ones', () => {
    const source = readFileSync(
      resolve(process.cwd(), '..', 'backend/src/backend/auth/passwords.py'),
      'utf8',
    )
    expect(Number(/^MIN_LENGTH = (\d+)/m.exec(source)?.[1])).toBe(PASSWORD_MIN_LENGTH)
    expect(Number(/^MAX_LENGTH = (\d+)/m.exec(source)?.[1])).toBe(PASSWORD_MAX_LENGTH)
  })

  it('counts characters the way the server does, not UTF-16 units', () => {
    expect(passwordLength('😀'.repeat(6))).toBe(6)
    expect(passwordLength('abc')).toBe(3)
  })
})

describe('a password the form refuses before sending', () => {
  it('one character short says the rule, and sends nothing', async () => {
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH - 1))
    expect(w.get('[role="alert"]').text()).toBe(
      `The new password needs at least ${PASSWORD_MIN_LENGTH} characters.`,
    )
    expect(changePassword).not.toHaveBeenCalled()
  })

  it('six emoji are six characters, so they are refused too', async () => {
    const w = mountChange()
    await submit(w, '😀'.repeat(6))
    expect(w.get('[role="alert"]').text()).toContain(`at least ${PASSWORD_MIN_LENGTH} characters`)
    expect(changePassword).not.toHaveBeenCalled()
  })

  it('at the minimum, it is sent', async () => {
    changePassword.mockResolvedValueOnce(refused(401, { title: 'invalid credentials' }))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(changePassword).toHaveBeenCalledTimes(1)
  })
})

describe('a password the server refuses', () => {
  it("a 422 shows the server's reason", async () => {
    changePassword.mockResolvedValueOnce(
      refused(422, { title: 'password must be at least 12 characters' }),
    )
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.get('[role="alert"]').text()).toBe('password must be at least 12 characters')
  })

  it('a validation 422 (too long, or empty) shows the rule instead of "Validation error"', async () => {
    changePassword.mockResolvedValueOnce(refused(422, { title: 'Validation error' }))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.get('[role="alert"]').text()).toBe(
      `The new password was refused. Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters.`,
    )
  })

  it('a 401 with the session still live says to check the current password', async () => {
    changePassword.mockResolvedValueOnce(refused(401, { title: 'invalid credentials' }))
    me.mockResolvedValueOnce(signedIn(true))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.get('[role="alert"]').text()).toBe(
      'Password change failed. Check the current password.',
    )
    expect(w.get('button').text()).toBe('Change password')
  })
})

// issue 833, F4: a dead session and a wrong current password are the same 401, and a session
// reset by an admin while the form was open read as a wrong password until a reload
describe('the session behind the form', () => {
  it('a 401 with the session ended turns the form into sign-in, emptied', async () => {
    changePassword.mockResolvedValueOnce(refused(401, { title: 'invalid credentials' }))
    me.mockResolvedValueOnce(refused(401))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.get('[role="alert"]').text()).toBe('Your session ended. Sign in again.')
    expect(w.get('button').text()).toBe('Sign in')
    expect((w.get('#password').element as HTMLInputElement).value).toBe('')
  })

  it('a change that landed with no new session asks for a sign-in, not Overview', async () => {
    changePassword.mockResolvedValueOnce({ data: {}, response: { ok: true, status: 200 } })
    me.mockResolvedValueOnce(refused(401))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.get('[role="alert"]').text()).toBe('Password changed. Sign in again.')
    expect(w.get('button').text()).toBe('Sign in')
    expect((w.get('#password').element as HTMLInputElement).value).toBe('')
    expect(push).not.toHaveBeenCalled()
  })

  it('a change with its new session goes to Overview', async () => {
    changePassword.mockResolvedValueOnce({ data: {}, response: { ok: true, status: 200 } })
    me.mockResolvedValueOnce(signedIn(false))
    const w = mountChange()
    await submit(w, 'x'.repeat(PASSWORD_MIN_LENGTH))
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(push).toHaveBeenCalledWith('/overview')
  })
})
