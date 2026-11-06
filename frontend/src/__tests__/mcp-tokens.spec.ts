/**
 * The AI agents (MCP) section of Settings (issue 1096 step 4, SCREENS §13.9): the window guards
 * mirror the backend's rules, and the section lists, makes, rotates and revokes MCP tokens.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as sdk from '@/api/generated'
import TokenOnceDialog from '@/components/settings/TokenOnceDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import McpTokensView from '@/views/settings/McpTokensView.vue'
import {
  defaultExpiryDay,
  endpointUrl,
  expiryIso,
  expiryRange,
  levelLabel,
  MCP_LEVELS,
  MAX_EXPIRY_DAYS,
  MCP_NAME,
} from '@/views/settings/mcpTokensForm'
import { tokenStatus } from '@/views/settings/tokensForm'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    getMetaApiV1MetaGet: vi.fn<() => Promise<unknown>>(),
    listTokensApiV1AdminMcpTokensGet: vi.fn<() => Promise<unknown>>(),
    makeApiV1AdminMcpTokensPost: vi.fn<() => Promise<unknown>>(),
    rotateApiV1AdminMcpTokensNameRotatePost: vi.fn<() => Promise<unknown>>(),
    revokeApiV1AdminMcpTokensNameRevokePost: vi.fn<() => Promise<unknown>>(),
  }),
)

const backendSource = (path: string) => readFileSync(resolve(process.cwd(), '..', 'backend/src/backend', path), 'utf8')

// 2026-11-06 22:30 UTC: late in the UTC day, so a local-calendar slip would show
const NOW = Date.parse('2026-11-06T22:30:00Z')

describe('expiryRange', () => {
  it('starts tomorrow in UTC and ends on the UTC day of now + 90 days', () => {
    expect(expiryRange(NOW)).toEqual({ first: '2026-11-07', last: '2027-02-04' })
  })

  it('never ends after the backend cap: 00:00 UTC of the last day is within 90 days', () => {
    for (const ms of [NOW, Date.parse('2026-11-06T00:00:00Z'), Date.parse('2026-11-06T23:59:59Z')]) {
      const last = Date.parse(`${expiryRange(ms).last}T00:00:00Z`)
      expect(last - ms).toBeLessThanOrEqual(90 * 86_400_000)
    }
  })
})

describe('expiryIso', () => {
  it('gives 00:00 UTC of a day in the range', () => {
    expect(expiryIso('2026-11-07', NOW)).toBe('2026-11-07T00:00:00.000Z')
    expect(expiryIso('2027-02-04', NOW)).toBe('2027-02-04T00:00:00.000Z')
  })

  it('refuses today, a past day and a day after the last', () => {
    expect(expiryIso('2026-11-06', NOW)).toBeNull()
    expect(expiryIso('2026-01-01', NOW)).toBeNull()
    expect(expiryIso('2027-02-05', NOW)).toBeNull()
  })

  it('refuses an empty or malformed day', () => {
    for (const bad of ['', '2026-11', '2026-13-40', 'tomorrow']) expect(expiryIso(bad, NOW)).toBeNull()
  })

  it('accepts the day the window puts in the box', () => {
    expect(defaultExpiryDay(NOW)).toBe('2026-12-06')
    expect(expiryIso(defaultExpiryDay(NOW), NOW)).not.toBeNull()
  })
})

describe('MCP_NAME', () => {
  it('takes 3 to 64 lower-case letters, digits, dots, underscores or hyphens', () => {
    expect(['cursor', 'ci.agent_2', 'a-b', 'x'.repeat(64)].filter((n) => !MCP_NAME.test(n))).toEqual([])
    expect(['ab', 'Cursor', 'my agent', 'x'.repeat(65), 'mcp:x'].filter((n) => MCP_NAME.test(n))).toEqual([])
  })
})

describe('levels', () => {
  it('offers the three levels of the backend, in order', () => {
    expect(MCP_LEVELS.map((l) => l.value)).toEqual(['read', 'write', 'write_risk_accept'])
    expect(levelLabel('write_risk_accept')).toBe('Write and risk accept')
    expect(levelLabel('later')).toBe('later')
  })
})

describe('endpointUrl', () => {
  it('is the address of the page plus the path of the endpoint', () => {
    expect(endpointUrl('https://javv.example.org')).toBe('https://javv.example.org/api/v1/mcp')
    expect(endpointUrl('http://localhost:5173/')).toBe('http://localhost:5173/api/v1/mcp')
  })
})

describe('the status of an MCP token', () => {
  const row = { disabled: false, expiry: '2026-12-01T00:00:00Z' }
  it('is the rule of the scanner tokens: revoked, then expired, then active', () => {
    expect(tokenStatus(row, new Date(NOW))).toBe('active')
    expect(tokenStatus({ ...row, expiry: '2026-11-01T00:00:00Z' }, new Date(NOW))).toBe('expired')
    expect(tokenStatus({ ...row, disabled: true }, new Date(NOW))).toBe('revoked')
  })
})

describe('the window guards are the backend rules', () => {
  it('the name rule is the username rule of the backend', () => {
    const src = backendSource('auth/usernames.py')
    const pattern = /^USERNAME_PATTERN = r"\^\[(.+)\]\+\$"$/m.exec(src)?.[1]
    const min = /^USERNAME_MIN_LENGTH = (\d+)$/m.exec(src)?.[1]
    const max = /^USERNAME_MAX_LENGTH = (\d+)$/m.exec(src)?.[1]
    expect(MCP_NAME.source).toBe(`^[${pattern}]{${min},${max}}$`)
  })

  it('the expiry cap is the cap of the route', () => {
    expect(/^MAX_EXPIRY_DAYS = (\d+)$/m.exec(backendSource('routers/mcp_tokens.py'))?.[1]).toBe(String(MAX_EXPIRY_DAYS))
  })
})

const token = (name: string, over: Record<string, unknown> = {}) => ({
  name,
  level: 'read',
  created_by: 'admin',
  created_at: '2026-10-01T00:00:00+00:00',
  expiry: '2999-01-01T00:00:00+00:00',
  disabled: false,
  last_used_at: null,
  ...over,
})

function answer(tokens: ReturnType<typeof token>[], mcpEnabled: boolean | 'fail' = false) {
  vi.mocked(sdk.getMetaApiV1MetaGet).mockResolvedValue(
    (mcpEnabled === 'fail'
      ? { response: { ok: false, status: 503 }, data: undefined }
      : { response: { ok: true }, data: { mcp_enabled: mcpEnabled } }) as never,
  )
  vi.mocked(sdk.listTokensApiV1AdminMcpTokensGet).mockResolvedValue({
    response: { ok: true },
    data: { tokens, total: tokens.length },
  } as never)
}

async function mountView() {
  useAuthStore().user = { username: 'admin', capabilities: ['can_manage_tokens'] } as never
  const w = mount(McpTokensView, { attachTo: document.body })
  await flushPromises()
  return w
}

const button = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').find((b) => b.text().trim() === text)!
const footer = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('.modal-actions button')].find((b) => b.textContent?.trim() === text)!

describe('the AI agents section', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('shows the skeletons while the reads are open', async () => {
    vi.mocked(sdk.getMetaApiV1MetaGet).mockReturnValue(new Promise(() => {}) as never)
    vi.mocked(sdk.listTokensApiV1AdminMcpTokensGet).mockReturnValue(new Promise(() => {}) as never)
    const w = mount(McpTokensView)
    await flushPromises()
    expect(w.findAll('.skel').length).toBe(2)
    expect(w.find('table').exists()).toBe(false)
  })

  it('says how to turn the endpoint on when it is off, and shows the URL', async () => {
    answer([])
    const w = await mountView()
    expect(w.text()).toContain('off')
    expect(w.text()).toContain('set JAVV_MCP_ENABLED to true on the backend')
    expect(w.get('.copy-box').text()).toBe(`${window.location.origin}/api/v1/mcp`)
  })

  it('shows on, without the turn-on line, when the endpoint is on', async () => {
    answer([], true)
    const w = await mountView()
    expect(w.text()).toContain('on')
    expect(w.text()).not.toContain('JAVV_MCP_ENABLED')
  })

  it('says when the status could not be read', async () => {
    answer([], 'fail')
    const w = await mountView()
    expect(w.text()).toContain('unknown: the status could not be read')
  })

  it('has an empty state, and a failure that names a busy store', async () => {
    answer([])
    let w = await mountView()
    expect(w.get('[role="status"].empty-note').text()).toContain('No MCP tokens yet')
    vi.mocked(sdk.listTokensApiV1AdminMcpTokensGet).mockResolvedValue({ response: { ok: false, status: 429 } } as never)
    w = await mountView()
    expect(w.get('.load-error').text()).toBe('The search backend is busy. Try again in a few seconds.')
    vi.mocked(sdk.listTokensApiV1AdminMcpTokensGet).mockResolvedValue({ response: { ok: false, status: 500 } } as never)
    w = await mountView()
    expect(w.get('.load-error').text()).toBe('The token list is not available. Check the backend connection.')
  })

  it('lists the level in words, and Rotate on an active token only', async () => {
    answer([
      token('live', { level: 'write_risk_accept' }),
      token('old', { expiry: '2020-01-01T00:00:00+00:00' }),
      token('off', { disabled: true }),
    ])
    const w = await mountView()
    const rows = w.findAll('tbody tr')
    expect(rows[0]!.text()).toContain('Write and risk accept')
    expect(rows.map((tr) => tr.findAll('.row-actions button').map((b) => b.text()))).toEqual([
      ['Rotate', 'Revoke'],
      ['Revoke'],
      [],
    ])
  })

  it('makes a token with the name, the level and the expiry, then shows it one time', async () => {
    answer([])
    vi.mocked(sdk.makeApiV1AdminMcpTokensPost).mockResolvedValue({
      response: { ok: true, status: 201 },
      data: { name: 'cursor-anna', token: 'raw-secret' },
    } as never)
    const w = await mountView()
    await button(w, 'Make token').trigger('click')
    expect(footer('Make token').disabled).toBe(true) // no name yet
    await w.get('#mcp-name').setValue('Cursor Anna')
    expect(w.get('#mcp-name').attributes('aria-invalid')).toBe('true')
    expect(footer('Make token').disabled).toBe(true)
    await w.get('#mcp-name').setValue('cursor-anna')
    await button(w, 'Write').trigger('click')
    expect(w.text()).toContain('Also sets the triage of findings')
    const day = (w.get('#mcp-expiry').element as HTMLInputElement).value
    expect(expiryIso(day, Date.now())).not.toBeNull() // 30 days is in the box
    footer('Make token').click()
    await flushPromises()
    expect(sdk.makeApiV1AdminMcpTokensPost).toHaveBeenCalledWith(
      expect.objectContaining({ body: { name: 'cursor-anna', level: 'write', expiry: `${day}T00:00:00.000Z` } }),
    )
    expect(document.body.textContent).toContain('Copy this token now')
    expect(document.querySelector('.modal .copy-box')?.textContent).toBe('raw-secret')
  })

  it('keeps the window open with the reason when the name is in use', async () => {
    answer([])
    vi.mocked(sdk.makeApiV1AdminMcpTokensPost).mockResolvedValue({ response: { ok: false, status: 409 } } as never)
    const w = await mountView()
    await button(w, 'Make token').trigger('click')
    await w.get('#mcp-name').setValue('cursor-anna')
    footer('Make token').click()
    await flushPromises()
    expect(w.get('.modal-error').text()).toBe('A token with this name exists. Choose another name.')
  })

  it('refuses an expiry after 90 days and keeps Make off', async () => {
    answer([])
    const w = await mountView()
    await button(w, 'Make token').trigger('click')
    await w.get('#mcp-name').setValue('cursor-anna')
    await w.get('#mcp-expiry').setValue(new Date(Date.now() + 120 * 86_400_000).toISOString().slice(0, 10))
    expect(w.get('#mcp-expiry').attributes('aria-invalid')).toBe('true')
    expect(footer('Make token').disabled).toBe(true)
  })

  it('rotates with a new expiry and shows the new token one time', async () => {
    answer([token('live')])
    vi.mocked(sdk.rotateApiV1AdminMcpTokensNameRotatePost).mockResolvedValue({
      response: { ok: true, status: 201 },
      data: { name: 'live', token: 'new-secret' },
    } as never)
    const w = await mountView()
    await button(w, 'Rotate').trigger('click')
    const day = (w.get('#mcp-rotate-expiry').element as HTMLInputElement).value
    footer('Rotate').click()
    await flushPromises()
    expect(sdk.rotateApiV1AdminMcpTokensNameRotatePost).toHaveBeenCalledWith(
      expect.objectContaining({ path: { name: 'live' }, body: { expiry: `${day}T00:00:00.000Z` } }),
    )
    expect(document.querySelector('.modal .copy-box')?.textContent).toBe('new-secret')
  })

  it('revokes, says so, and reads the list again', async () => {
    answer([token('live')])
    vi.mocked(sdk.revokeApiV1AdminMcpTokensNameRevokePost).mockResolvedValue({ response: { ok: true } } as never)
    const w = await mountView()
    await button(w, 'Revoke').trigger('click')
    footer('Revoke').click()
    await flushPromises()
    expect(sdk.revokeApiV1AdminMcpTokensNameRevokePost).toHaveBeenCalledWith(expect.objectContaining({ path: { name: 'live' } }))
    expect(useToastStore().toasts.map((t) => t.message)).toEqual([
      'Token live revoked. The agent that uses it is refused from now on.',
    ])
    expect(sdk.listTokensApiV1AdminMcpTokensGet).toHaveBeenCalledTimes(2)
  })
})

describe('the window that shows a token one time', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('says with a toast when the browser blocks the clipboard', async () => {
    vi.stubGlobal('navigator', { clipboard: undefined })
    const w = mount(TokenOnceDialog, { props: { token: 'raw', subtitle: 'once' }, attachTo: document.body })
    footer('Copy token').click()
    await flushPromises()
    expect(useToastStore().toasts.map((t) => t.message)).toEqual([
      "Couldn't copy: the browser blocked the clipboard. Select the text and copy it.",
    ])
    expect(footer('Copy token')).toBeDefined() // not "Copied"
    w.unmount()
    vi.unstubAllGlobals()
  })

  it('says Copied after a copy', async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve())
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const w = mount(TokenOnceDialog, { props: { token: 'raw', subtitle: 'once' }, attachTo: document.body })
    footer('Copy token').click()
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('raw')
    expect(footer('Copied ✓')).toBeDefined()
    w.unmount()
    vi.unstubAllGlobals()
  })
})
