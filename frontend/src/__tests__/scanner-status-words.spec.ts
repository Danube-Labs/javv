/**
 * The card of each scanner on Scanner status uses plain words (issue 1152): the full name of the
 * vulnerability database, as Settings › Scanning and About use it.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const template = readFileSync(
  join(__dirname, '..', 'components/scanners/ScannerStatusCard.vue'),
  'utf8',
).split('<template>')[1]!

describe('the words of the scanner card on Scanner status', () => {
  it('names the vulnerability database in full', () => {
    expect(template).toContain('<em>Vulnerability database</em>')
    expect(template).not.toMatch(/vuln DB/i)
  })
})
