// @vitest-environment node
/**
 * The dev server sends the policy of the frontend server, and the build gets no fixed nonce
 * (issue 1275, D1 A). `VITE_DEVTOOLS=true` turns the Vue devtools on and the policy off, because
 * the devtools add a style with no nonce.
 */
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import { createServer, type ConfigEnv, type PluginOption, type UserConfig } from 'vite'

import { contentSecurityPolicy } from '../../server/serve.mjs'
import viteConfig, { DEV_NONCE } from '../../vite.config'

const ROOT = fileURLToPath(new URL('../..', import.meta.url))
const CONFIG_FILE = fileURLToPath(new URL('../../vite.config.ts', import.meta.url))
const DEVTOOLS = process.env.VITE_DEVTOOLS

afterEach(() => {
  if (DEVTOOLS === undefined) delete process.env.VITE_DEVTOOLS
  else process.env.VITE_DEVTOOLS = DEVTOOLS
})

async function configFor(env: ConfigEnv): Promise<UserConfig> {
  return typeof viteConfig === 'function' ? await viteConfig(env) : viteConfig
}

async function pluginNames(plugins: PluginOption[] | undefined): Promise<string[]> {
  const names: string[] = []
  for (const item of plugins ?? []) {
    const plugin = await item
    if (Array.isArray(plugin)) names.push(...(await pluginNames(plugin)))
    else if (plugin && 'name' in plugin) names.push(plugin.name)
  }
  return names
}

const SERVE: ConfigEnv = { command: 'serve', mode: 'development' }
const BUILD: ConfigEnv = { command: 'build', mode: 'production' }
// what Vite gives the config for `vite preview` (resolveConfig with isPreview)
const PREVIEW: ConfigEnv = { command: 'serve', mode: 'production', isPreview: true }

describe('the config of the dev server', () => {
  it('sends the policy of the frontend server with the dev nonce', async () => {
    delete process.env.VITE_DEVTOOLS
    const config = await configFor(SERVE)
    expect(config.server?.headers).toEqual({
      'content-security-policy': contentSecurityPolicy(DEV_NONCE),
    })
    expect(config.html?.cspNonce).toBe(DEV_NONCE)
    const names = await pluginNames(config.plugins)
    expect(names).toContain('javv-csp-nonce-meta')
    expect(names.filter((n) => n.includes('devtools'))).toEqual([])
  })

  it.each(['false', '1', ''])('keeps the devtools off for VITE_DEVTOOLS=%j', async (value) => {
    process.env.VITE_DEVTOOLS = value
    const config = await configFor(SERVE)
    expect(config.html?.cspNonce).toBe(DEV_NONCE)
    expect((await pluginNames(config.plugins)).filter((n) => n.includes('devtools'))).toEqual([])
  })

  it('turns the devtools on and the policy off for VITE_DEVTOOLS=true', async () => {
    process.env.VITE_DEVTOOLS = 'true'
    const config = await configFor(SERVE)
    expect(config.server?.headers).toBeUndefined()
    expect(config.html?.cspNonce).toBeUndefined()
    const names = await pluginNames(config.plugins)
    expect(names.filter((n) => n.includes('devtools')).length).toBeGreaterThan(0)
    expect(names).not.toContain('javv-csp-nonce-meta')
  })
})

describe('the config of the build', () => {
  it.each([undefined, 'true'])('has no nonce, no policy and no devtools (VITE_DEVTOOLS=%j)', async (value) => {
    if (value === undefined) delete process.env.VITE_DEVTOOLS
    else process.env.VITE_DEVTOOLS = value
    const config = await configFor(BUILD)
    expect(config.html?.cspNonce).toBeUndefined()
    expect(config.server?.headers).toBeUndefined()
    const names = await pluginNames(config.plugins)
    expect(names).not.toContain('javv-csp-nonce-meta')
    expect(names.filter((n) => n.includes('devtools'))).toEqual([])
  })
})

describe('the config of vite preview', () => {
  it.each([undefined, 'true'])('has no nonce, no policy and no devtools (VITE_DEVTOOLS=%j)', async (value) => {
    if (value === undefined) delete process.env.VITE_DEVTOOLS
    else process.env.VITE_DEVTOOLS = value
    const config = await configFor(PREVIEW)
    expect(config.html?.cspNonce).toBeUndefined()
    expect(config.server?.headers).toBeUndefined()
    expect(config.preview?.headers).toBeUndefined()
    const names = await pluginNames(config.plugins)
    expect(names).not.toContain('javv-csp-nonce-meta')
    expect(names.filter((n) => n.includes('devtools'))).toEqual([])
  })
})

describe('a running dev server', () => {
  it('sends the policy, and the page carries the nonce for PrimeVue and for Vite', async () => {
    delete process.env.VITE_DEVTOOLS
    const server = await createServer({
      configFile: CONFIG_FILE,
      root: ROOT,
      logLevel: 'silent',
      server: { host: '127.0.0.1', port: 0, strictPort: false, hmr: false, watch: null },
    })
    try {
      await server.listen()
      const res = await fetch(`${server.resolvedUrls!.local[0]}login`)
      expect(res.headers.get('content-security-policy')).toBe(contentSecurityPolicy(DEV_NONCE))
      const html = await res.text()
      // the tag that main.ts reads for PrimeVue
      expect(html).toContain(`<meta name="csp-nonce" content="${DEV_NONCE}">`)
      // the tag that the client of Vite reads for the styles that it adds
      expect(html).toContain(`<meta property="csp-nonce" nonce="${DEV_NONCE}">`)
      // `script-src 'self'` needs no nonce. The nonce on each script shows that html.cspNonce
      // reached the page, as it reaches the styles that Vite adds
      const scripts = html.match(/<script\b[^>]*>/g) ?? []
      expect(scripts.length).toBeGreaterThan(0)
      expect(scripts.filter((tag) => !tag.includes(`nonce="${DEV_NONCE}"`))).toEqual([])
    } finally {
      await server.close()
    }
  })
})
