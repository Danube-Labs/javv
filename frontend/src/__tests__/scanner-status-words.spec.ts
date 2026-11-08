/**
 * The card of each scanner on Scanner status uses plain words (issue 1152): the full name of the
 * vulnerability database, as Settings › Scanning and About use it, and a note on the version that
 * is true for each source of scans (the Kubernetes chart, a Nomad job, a Compose file).
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
    expect(template).toContain('<em>Database built</em>')
    expect(template).not.toContain('DB built')
  })

  it('says where the version is set, with no words of one deploy tool', () => {
    const note = template.split('class="scan-gitops"')[1]!.split('</span')[0]!
    expect(note.replace(/\s+/g, ' ')).toContain(
      'The version is set where the scanner runs, by its image tag. JAVV does not change it.',
    )
    expect(template).not.toMatch(/GitOps|swapping the published/)
  })
})
