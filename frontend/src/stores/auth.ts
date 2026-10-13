/**
 * Session + capabilities (D33/A-4): ALL client gating flows from the `capabilities` array on
 * /auth/me — never role names (role is display-only). `"*"` (admin) grants everything. The client
 * gate is convenience; the server is the authority. A `must_change` session is locked to the
 * password screen by the router guard.
 */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import { detailOr, STORE_READ_ONLY_TYPE } from '@/api/problem'
import {
  loginAuthLoginPost,
  logoutAuthLogoutPost,
  meAuthMeGet,
  changePasswordAuthPasswordPost,
} from '@/api/generated'
import { logger } from '@/lib/logger'

export interface SessionUser {
  username: string
  role: string
  capabilities: string[]
  must_change: boolean
}

/** No answer, or a 5xx: the server, or the proxy in front of it, failed. That says nothing about
 * the session or the password, so it must never be reported as either (issue 675). */
export function serverFailed(status: number | undefined): boolean {
  return status === undefined || status >= 500
}

export const SERVER_DOWN_COPY = 'The server is not answering. This page checks again on its own.'

/** Sign-in and the password change write, so a store whose disk is full refuses them (issue 832,
 * ruled copy). The server answers; it only cannot save. */
export const READ_ONLY_COPY = 'The store is read-only: its disk is full.'

const refusedReadOnly = (error: unknown): boolean =>
  (error as { type?: unknown } | undefined)?.type === STORE_READ_ONLY_TYPE

export const SESSION_ENDED_COPY = 'Your session ended. Sign in again.'
export const PASSWORD_CHANGED_COPY = 'Password changed. Sign in again.'

/** Mirror `MIN_LENGTH` and `MAX_LENGTH` in `backend/src/backend/auth/passwords.py`
 * (CONFIGURATION.md, "Fixed values"), so the form can say the rule and refuse a short password
 * before sending it. The server stays the authority; `password-change.spec.ts` fails when they
 * differ. */
export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_MAX_LENGTH = 256

/** Counted in code points, as the server's `len()` counts them: `'😀'.length` is 2 in JS. */
export const passwordLength = (password: string): number => [...password].length

/** The sign-in form's message for a failed answer, or null on success. A wrong password stays
 * generic: no hint about whether the user exists. */
export function loginFailure(status: number | undefined): string | null {
  if (serverFailed(status)) return SERVER_DOWN_COPY
  if (status === 429) return 'Too many attempts. Try again later.'
  return status! >= 200 && status! < 300 ? null : 'Invalid username or password.'
}

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null as SessionUser | null, checked: false, unreachable: false }),
  getters: {
    isAuthed: (s) => s.user !== null,
    mustChange: (s) => s.user?.must_change === true,
    hasCapability: (s) => (cap: string) =>
      s.user !== null && (s.user.capabilities.includes('*') || s.user.capabilities.includes(cap)),
  },
  actions: {
    async fetchMe(): Promise<void> {
      const { data, response } = await meAuthMeGet({ client })
      if (serverFailed(response?.status)) {
        // not "signed out": `checked` stays false, so the next navigation asks again
        logger.warn('session check failed', { status: response?.status ?? null })
        this.user = null
        this.unreachable = true
        return
      }
      this.unreachable = false
      this.user =
        response?.ok && data ? ((data as { user: SessionUser }).user ?? null) : null
      this.checked = true
    },
    /** Returns null on success, or user-facing error copy (generic — no user-existence hints). */
    async login(username: string, password: string): Promise<string | null> {
      const { error, response } = await loginAuthLoginPost({
        client,
        body: { username, password },
      })
      // the server answers and only cannot save: not "not answering", and no re-check loop
      if (refusedReadOnly(error)) {
        this.unreachable = false
        return READ_ONLY_COPY
      }
      this.unreachable = serverFailed(response?.status)
      const failure = loginFailure(response?.status)
      if (failure !== null) return failure
      logger.info('login', { username })
      await this.fetchMe()
      return null
    },
    async changePassword(currentPassword: string, newPassword: string): Promise<string | null> {
      const { error, response } = await changePasswordAuthPasswordPost({
        client,
        body: { current_password: currentPassword, new_password: newPassword },
      })
      if (refusedReadOnly(error)) {
        this.unreachable = false
        return READ_ONLY_COPY
      }
      this.unreachable = serverFailed(response?.status)
      if (this.unreachable) return SERVER_DOWN_COPY
      if (response?.status === 422) {
        const rule = `Use ${PASSWORD_MIN_LENGTH} to ${PASSWORD_MAX_LENGTH} characters.`
        return detailOr(error, `The new password was refused. ${rule}`)
      }
      if (response?.status === 401) {
        // a wrong current password and an ended session are the same 401; the session check
        // tells them apart, and an ended one signs the user out, so the form becomes sign-in
        await this.fetchMe()
        if (this.unreachable) return SERVER_DOWN_COPY
        if (this.user === null) return SESSION_ENDED_COPY
      }
      if (!response?.ok) return 'Password change failed. Check the current password.'
      logger.info('password changed')
      await this.fetchMe()
      // the change landed, but the server could not make the new session (a 200 with no cookie)
      if (this.user === null) return PASSWORD_CHANGED_COPY
      return null
    },
    async logout(): Promise<void> {
      await logoutAuthLogoutPost({ client })
      logger.info('logout', { username: this.user?.username })
      this.user = null
    },
  },
})
