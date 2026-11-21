/**
 * The browser logs each violation of the policy as a warning, with two filters: no violation from
 * a browser extension, and one entry for each directive and file on a screen (issue 1275, option
 * A). The e2e case in `tests/e2e/beacon.spec.ts` shows the entry in the backend log.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { logger } from '@/lib/logger'
import {
  logPolicyViolations,
  policyViolationEntry,
  type CurrentRoute,
  type PolicyViolation,
} from '@/lib/policyViolations'

const STYLE_ATTR: PolicyViolation = {
  effectiveDirective: 'style-src-attr',
  blockedURI: 'inline',
  sourceFile: 'https://javv.example/assets/useBucketRewind-5S-J3M-k.js?v=1#x',
  lineNumber: 14,
  sample: '',
}

function violation(fields: Partial<PolicyViolation> = {}): Event {
  return Object.assign(new Event('securitypolicyviolation'), STYLE_ATTR, fields)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('policyViolationEntry', () => {
  it('gives the directive, the file name, the line, the sample and the route', () => {
    expect(policyViolationEntry({ ...STYLE_ATTR, sample: 'color: red' }, '/overview')).toEqual({
      directive: 'style-src-attr',
      source: 'useBucketRewind-5S-J3M-k.js',
      line: 14,
      sample: 'color: red',
      route: '/overview',
    })
  })

  it('keeps no fragment when the address has no query', () => {
    const entry = policyViolationEntry({ ...STYLE_ATTR, sourceFile: 'https://javv.example/a/c.js#y' }, '/')
    expect(entry?.source).toBe('c.js')
  })

  it('names the page, not the last part of its address, for a violation in the page itself', () => {
    const page = 'https://javv.example/images/sha256-abc?cluster=x'
    const sourceFile = 'https://javv.example/images/sha256-abc'
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile }, '/images/sha256-abc', page)?.source).toBe(
      'the page',
    )
  })

  it('keeps no origin, path, query or fragment of the file address', () => {
    const entry = policyViolationEntry(
      { ...STYLE_ATTR, sourceFile: 'https://javv.example/a/b/c.js?token=x#y' },
      '/',
    )
    expect(entry?.source).toBe('c.js')
  })

  it('names the page when the browser gives no file', () => {
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile: '' }, '/')?.source).toBe('the page')
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile: undefined }, '/')?.source).toBe(
      'the page',
    )
    // an address that ends in a slash names no file
    const folder = { ...STYLE_ATTR, sourceFile: 'https://javv.example/assets/' }
    expect(policyViolationEntry(folder, '/', 'https://javv.example/overview')?.source).toBe('the page')
  })

  it('cuts the sample to 60 characters', () => {
    const sample = 'x'.repeat(61)
    expect(policyViolationEntry({ ...STYLE_ATTR, sample }, '/')?.sample).toBe('x'.repeat(60))
    expect(policyViolationEntry({ ...STYLE_ATTR, sample: undefined }, '/')?.sample).toBe('')
  })

  it.each([
    'chrome-extension://abcdef/content.js',
    'moz-extension://1234-5678/inject.js',
    'safari-extension://com.example.ext/page.js',
    'safari-web-extension://ABCD/script.js',
  ])('drops a violation whose file is in an extension: %s', (sourceFile) => {
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile }, '/')).toBeNull()
  })

  it.each(['chrome-extension', 'moz-extension://1234-5678/style.css'])(
    'drops a violation whose blocked address is an extension: %s',
    (blockedURI) => {
      expect(policyViolationEntry({ ...STYLE_ATTR, blockedURI }, '/')).toBeNull()
    },
  )

  it('keeps a file of the app whose query names an extension', () => {
    const sourceFile = 'https://javv.example/assets/app.js?from=chrome-extension://abc'
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile }, '/')).not.toBeNull()
  })

  it('keeps a file whose name only contains the word extension', () => {
    const sourceFile = 'https://javv.example/assets/chrome-extension-notes.js'
    expect(policyViolationEntry({ ...STYLE_ATTR, sourceFile }, '/')).not.toBeNull()
  })
})

const OVERVIEW: CurrentRoute = { path: '/overview', name: 'overview' }

describe('logPolicyViolations', () => {
  it('logs a violation as the warning csp violation', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    logPolicyViolations(target, () => OVERVIEW)
    target.dispatchEvent(violation())
    expect(warned).toHaveBeenCalledExactlyOnceWith('csp violation', {
      directive: 'style-src-attr',
      source: 'useBucketRewind-5S-J3M-k.js',
      line: 14,
      sample: '',
      route: '/overview',
    })
  })

  it('logs one entry for each directive and file on a screen', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    let route: CurrentRoute = OVERVIEW
    logPolicyViolations(target, () => route)
    for (let i = 0; i < 50; i += 1) target.dispatchEvent(violation({ lineNumber: i }))
    expect(warned).toHaveBeenCalledTimes(1)

    target.dispatchEvent(violation({ effectiveDirective: 'script-src-elem' }))
    target.dispatchEvent(violation({ sourceFile: 'https://javv.example/assets/other.js' }))
    expect(warned).toHaveBeenCalledTimes(3)

    route = { path: '/findings', name: 'findings' }
    target.dispatchEvent(violation())
    target.dispatchEvent(violation())
    expect(warned).toHaveBeenCalledTimes(4)
    expect(warned.mock.calls.map(([, fields]) => fields?.route)).toEqual([
      '/overview',
      '/overview',
      '/overview',
      '/findings',
    ])
  })

  it('logs one entry for two addresses of the same screen, with the address of the first', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    let route: CurrentRoute = { path: '/images/sha256-a', name: 'image-detail' }
    logPolicyViolations(target, () => route)
    target.dispatchEvent(violation())
    route = { path: '/images/sha256-b', name: 'image-detail' }
    target.dispatchEvent(violation())
    expect(warned).toHaveBeenCalledOnce()
    expect(warned.mock.calls[0]![1]?.route).toBe('/images/sha256-a')
  })

  it('uses the path as the screen of a route with no name', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    let route: CurrentRoute = { path: '/a' }
    logPolicyViolations(target, () => route)
    target.dispatchEvent(violation())
    route = { path: '/b' }
    target.dispatchEvent(violation())
    expect(warned).toHaveBeenCalledTimes(2)
  })

  it('logs nothing for a violation from an extension', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    logPolicyViolations(target, () => ({ path: '/', name: 'overview' }))
    target.dispatchEvent(violation({ sourceFile: 'chrome-extension://abcdef/content.js' }))
    target.dispatchEvent(violation({ blockedURI: 'moz-extension' }))
    expect(warned).not.toHaveBeenCalled()
  })

  it('an extension violation does not hide a later violation of the app', () => {
    const warned = vi.spyOn(logger, 'warn').mockImplementation(() => {})
    const target = new EventTarget()
    logPolicyViolations(target, () => ({ path: '/', name: 'overview' }))
    target.dispatchEvent(violation({ blockedURI: 'chrome-extension' }))
    target.dispatchEvent(violation())
    expect(warned).toHaveBeenCalledTimes(1)
  })
})
