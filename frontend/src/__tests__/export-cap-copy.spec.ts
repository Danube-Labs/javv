/**
 * The message for an export that is too big names the problem in the user's words (issue 681):
 * three screens said "Over the inline export cap", which is our term for a server limit.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const view = (name: string) => readFileSync(resolve(process.cwd(), 'src/views', name), 'utf8')
const capped = (src: string) => /onCapped: \(\) => toast\.info\('([^']+)'\)/.exec(src)?.[1]

describe('the too-big export message', () => {
  it.each([
    ['ApprovalsView.vue', 'Too many rows to export at once. Narrow the filters first.'],
    ['AuditTrailView.vue', 'Too many rows to export at once. Narrow the filters first.'],
    ['ContributorsView.vue', 'Too many rows to export at once. Select a shorter time range first.'],
  ])('%s says what happened and what to do', (name, message) => {
    expect(capped(view(name))).toBe(message)
  })
})
