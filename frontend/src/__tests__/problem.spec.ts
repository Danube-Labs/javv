/**
 * `detailOr` shows a server title verbatim, except the request-validation one, whose detail is a
 * repr and never user copy. That title is matched by its text, so it is pinned to the backend's
 * handler here (issue 833): a renamed title would otherwise reach users as "Validation error".
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { detailOr, STORE_READ_ONLY_TYPE, VALIDATION_TITLE } from '@/api/problem'

describe('the validation title', () => {
  it("is the backend handler's title", () => {
    const source = readFileSync(
      resolve(process.cwd(), '..', 'backend/src/backend/core/errors.py'),
      'utf8',
    )
    const handler = source.slice(source.indexOf('async def _validation('))
    expect(/title="([^"]+)"/.exec(handler)?.[1]).toBe(VALIDATION_TITLE)
  })
})

describe('the read-only store type', () => {
  it("is the backend's problem type for a write the full disk refused (issue 832)", () => {
    const source = readFileSync(
      resolve(process.cwd(), '..', 'backend/src/backend/core/errors.py'),
      'utf8',
    )
    expect(/^STORE_READ_ONLY_TYPE = "([^"]+)"/m.exec(source)?.[1]).toBe(STORE_READ_ONLY_TYPE)
  })
})

describe('detailOr', () => {
  it("shows a route's own message", () => {
    expect(detailOr({ title: 'cannot demote or disable the last enabled admin' }, 'fallback')).toBe(
      'cannot demote or disable the last enabled admin',
    )
  })

  it('shows the fallback for a validation error, a missing title or no body', () => {
    expect(detailOr({ title: VALIDATION_TITLE }, 'fallback')).toBe('fallback')
    expect(detailOr({}, 'fallback')).toBe('fallback')
    expect(detailOr(undefined, 'fallback')).toBe('fallback')
  })
})
