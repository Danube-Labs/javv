/** A role id shows as words on every screen; the id stays the value (issue 1039). */
import { describe, expect, it } from 'vitest'

import { roleLabel } from '@/lib/roleLabel'

describe('roleLabel', () => {
  it('shows each underscore of a role id as a space', () => {
    expect(roleLabel('security_lead')).toBe('security lead')
    expect(roleLabel('a_b_c')).toBe('a b c')
  })

  it('leaves an id with no underscore as it is', () => {
    expect(roleLabel('admin')).toBe('admin')
    expect(roleLabel('')).toBe('')
  })
})
