/**
 * A 401 from a data route means the session is gone, so the client opens the sign-in page. The
 * auth routes answer 401 as a result of their own (no session yet, a wrong password), and they
 * live at /auth/*, outside /api/v1 (issue 1246: the check looked for /api/v1/auth/, matched
 * nothing, and loaded the page a second time before sign-in). The calls go through the real
 * client and SDK, so the URLs are the ones the app sends. The browser makes each request URL
 * absolute against the page origin; Node's Request refuses a relative one, so the tests give the
 * client that origin as its base.
 */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { client } from '@/api/client'
import { loginAuthLoginPost, meAuthMeGet } from '@/api/generated'

const ORIGIN = 'http://localhost:3000'
const assign = vi.fn<(url: string) => void>()

function onPage(pathname: string) {
  vi.stubGlobal('location', { origin: ORIGIN, pathname, assign })
}

beforeEach(() => {
  setActivePinia(createPinia())
  client.setConfig({ baseUrl: ORIGIN })
  assign.mockClear()
  vi.stubGlobal(
    'fetch',
    vi.fn<() => Promise<Response>>(async () =>
      new Response(JSON.stringify({ title: 'invalid credentials', status: 401 }), {
        status: 401,
        headers: { 'content-type': 'application/problem+json' },
      }),
    ),
  )
})

afterEach(() => {
  client.setConfig({ baseUrl: '' })
  vi.unstubAllGlobals()
})

describe('the client on a 401', () => {
  it('stays on the page when the session check answers 401 before sign-in', async () => {
    onPage('/')
    const { response } = await meAuthMeGet({ client })
    expect(response?.status).toBe(401)
    expect(assign).not.toHaveBeenCalled()
  })

  it('stays on the page when a sign-in answers 401', async () => {
    onPage('/')
    await loginAuthLoginPost({ client, body: { username: 'admin', password: 'wrong' } })
    expect(assign).not.toHaveBeenCalled()
  })

  it('opens the sign-in page when a data route answers 401', async () => {
    onPage('/findings')
    await client.get({ url: '/api/v1/clusters' })
    expect(assign).toHaveBeenCalledWith('/login')
  })

  it('does not open the sign-in page again from the sign-in page', async () => {
    onPage('/login')
    await client.get({ url: '/api/v1/clusters' })
    expect(assign).not.toHaveBeenCalled()
  })
})
