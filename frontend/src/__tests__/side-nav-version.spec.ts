/**
 * The sidebar footer's version line (issue 261): every number comes from `/api/v1/meta`, none is
 * typed into the template. A failed read says so on screen and in the log, instead of showing a stale
 * or blank version.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import SideNav from '@/components/chrome/SideNav.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    getMetaApiV1MetaGet: vi.fn<() => Promise<unknown>>(),
    changePasswordAuthPasswordPost: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    loginAuthLoginPost: vi.fn<() => Promise<unknown>>(),
    logoutAuthLogoutPost: vi.fn<() => Promise<unknown>>(),
    meAuthMeGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))
vi.mock('@/lib/logger', () => ({
  logger: {
    debug: vi.fn<() => void>(),
    info: vi.fn<() => void>(),
    warn: vi.fn<() => void>(),
    error: vi.fn<() => void>(),
  },
}))

import { getMetaApiV1MetaGet } from '@/api/generated'
import { logger } from '@/lib/logger'

const metaMock = vi.mocked(getMetaApiV1MetaGet)

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

async function versionLines(): Promise<string[]> {
  const wrapper = mount(SideNav, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper.findAll('.side-version span').map((s) => s.text())
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.clear()
  metaMock.mockReset()
  vi.mocked(logger.warn).mockReset()
})

describe('SideNav version line', () => {
  it('shows the release, the store schema and the newest scanner schema, one per line', async () => {
    metaMock.mockResolvedValue({
      data: { version: '0.6.0', mapping_version: 18, envelope_versions: [3, 4] },
      response: { ok: true, status: 200 },
    } as never)
    expect(await versionLines()).toEqual(['v0.6.0', 'database schema 18', 'scanner schema 4'])
    expect(logger.warn).not.toHaveBeenCalled()
  })

  it('links the version lines to the About page, where the full stack is listed (issue 341)', async () => {
    metaMock.mockResolvedValue({
      data: { version: '0.6.0', mapping_version: 18, envelope_versions: [3, 4] },
      response: { ok: true, status: 200 },
    } as never)
    const wrapper = mount(SideNav, { global: { plugins: [router] } })
    await flushPromises()
    const link = wrapper.find('a.side-version')
    expect(link.exists()).toBe(true)
    expect(link.attributes('href')).toBe('/about')
    expect(link.attributes('title')).toContain('About')
  })

  it('says the version is unavailable when the read fails, and logs why', async () => {
    metaMock.mockResolvedValue({ data: undefined, response: { ok: false, status: 503 } } as never)
    expect(await versionLines()).toEqual(['no version'])
    expect(logger.warn).toHaveBeenCalledWith('meta_read_failed', { status: 503 })
  })
})
