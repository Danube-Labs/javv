/**
 * The zero-clusters onboarding state (M9f): data screens show it while no scanner has enrolled,
 * because they would fetch nothing forever. Configure stays live (Settings → Tokens is the way
 * out) and so does Help (issue 341): the About page is what a new install needs most.
 */
import { describe, expect, it } from 'vitest'

import { isColdStart } from '@/system/coldStart'

const empty = { none: true }

describe('isColdStart', () => {
  it('holds a data screen while the registry is loaded, healthy and empty', () => {
    expect(isColdStart({ ...empty, section: 'monitor' })).toBe(true)
    expect(isColdStart({ ...empty, section: undefined })).toBe(true)
  })

  it('never holds Configure or Help', () => {
    expect(isColdStart({ ...empty, section: 'configure' })).toBe(false)
    expect(isColdStart({ ...empty, section: 'help' })).toBe(false)
  })

  it('needs the registry to have answered empty (the store\'s `none`, pinned in cluster-store.spec)', () => {
    expect(isColdStart({ none: false, section: 'monitor' })).toBe(false)
  })
})
