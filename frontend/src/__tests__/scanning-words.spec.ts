/**
 * "All scanners" adds the counts of the two scanners, because a finding includes its scanner
 * (issue 1076). The words of Scanning and of a finding's Affected card say so, and do not say
 * "never merged" (issue 1140, R4).
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { SCOPE_COPY } from '@/views/settings/sections'

const read = (path: string) => readFileSync(join(__dirname, '..', path), 'utf8')

describe('the words about the two scanners', () => {
  it('the scope strip of Scanning does not say never merged', () => {
    expect(SCOPE_COPY.scanner.note).toBe('Shown for each scanner, Trivy and Grype, on its own.')
  })

  it('the banner of Scanning says what All scanners counts', () => {
    const banner = read('views/settings/ScanningView.vue').split('class="scanner-banner"')[1]!.split('</div>')[0]!
    expect(banner.replace(/\s+/g, ' ')).toContain(
      '<b>All scanners</b> shows Trivy and Grype together: a CVE that both report counts once for each.',
    )
    expect(banner).not.toMatch(/never merged|double-counting/)
  })

  it('the head note of Findings says how the two scanners count, in plain words (issue 1152)', () => {
    const src = read('views/FindingsView.vue').split('<template>')[1]!
    expect(src).toContain(
      '<p class="head-note">Trivy and Grype count apart: a CVE that both report counts once for each</p>',
    )
    expect(src).not.toMatch(/cross-merge|per-scanner/)
  })

  it('the Affected card of a finding does not say never merged', () => {
    const src = read('components/finding/AffectedCard.vue').split('<template>')[1]!
    expect(src).toContain('sub="across the last committed inventory · one row for each image and package, with its scanners"')
    expect(src).not.toContain('never merged')
  })
})
