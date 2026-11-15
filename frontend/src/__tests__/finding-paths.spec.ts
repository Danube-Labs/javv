/**
 * The files of a finding (issue 1077): the cell text, the hover text and the list under a row.
 * Each entry is one finding of one scanner, so two entries are two numbers, never a sum. `null`
 * (the scan sent no paths) and `0` (the scanner gave none) must not read the same.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import FindingPaths from '@/components/finding/FindingPaths.vue'
import {
  countText,
  countTitle,
  type FindingPaths as Entry,
  foundText,
  hasPaths,
  isOsPackage,
  keptText,
  openLabel,
  pathsOf,
  shortDigest,
} from '@/findings/paths'
import type { FindingRow } from '@/stores/findings'

const e = (over: Partial<Entry>): Entry => ({
  scanner: 'trivy',
  digest: 'sha256:aaa',
  total: 0,
  paths: [],
  osPackage: false,
  ...over,
})

describe('the text of the Paths cell', () => {
  it('one finding: the number with its word, "-" when the scan sent no paths', () => {
    expect(countText([e({ total: 11, paths: ['/a'] })])).toBe('11 paths')
    expect(countText([e({ total: 1, paths: ['/a'] })])).toBe('1 path')
    expect(countText([e({ total: 0 })])).toBe('0 paths')
    expect(countText([e({ total: null })])).toBe('-')
  })

  it('two findings: one number for each, in their order, never added up', () => {
    expect(countText([e({ total: 0 }), e({ scanner: 'grype', total: 5 })])).toBe('0 · 5')
    expect(countText([e({ total: null }), e({ scanner: 'grype', total: 5 })])).toBe('- · 5')
  })

  it('the hover text and the button name say which scanner each number is from', () => {
    const two = [e({ total: null }), e({ scanner: 'grype', total: 0 })]
    expect(countTitle(two)).toBe('Trivy: this scan did not report paths. Grype: the scanner gave no path.')
    expect(openLabel([e({ total: 0 }), e({ scanner: 'grype', total: 5 })])).toBe(
      'Paths: Trivy 0, Grype 5. Show the paths',
    )
    expect(openLabel([e({ total: null })])).toBe('Paths: Trivy not reported. Show the paths')
  })

  it('a row of two digests names the digest in the hover text and the button name (review F2)', () => {
    const two = [
      e({ digest: 'sha256:aaaaaaaaaaaaaaaa', total: 11, paths: ['/a'] }),
      e({ digest: 'sha256:bbbbbbbbbbbbbbbb', total: 11, paths: ['/b'] }),
      e({ scanner: 'grype', digest: 'sha256:aaaaaaaaaaaaaaaa', total: 1, paths: ['/c'] }),
    ]
    expect(countText(two)).toBe('11 · 11 · 1')
    expect(countTitle(two)).toBe(
      'Trivy on sha256:aaaaaaaaaaaa: 11 paths. Trivy on sha256:bbbbbbbbbbbb: 11 paths. Grype on sha256:aaaaaaaaaaaa: 1 path.',
    )
    expect(openLabel(two)).toBe(
      'Paths: Trivy on sha256:aaaaaaaaaaaa 11, Trivy on sha256:bbbbbbbbbbbb 11, Grype on sha256:aaaaaaaaaaaa 1. Show the paths',
    )
  })

  it('a row opens only when a finding has a path to show, one path included', () => {
    expect(hasPaths([e({ total: 0 }), e({ total: null })])).toBe(false)
    expect(hasPaths([e({ total: 1, paths: ['/usr/bin/go'] })])).toBe(true)
  })
})

describe('the sentences over the list', () => {
  it('names the scanner, the package and its version', () => {
    expect(foundText(e({ total: 11 }), 'stdlib', 'v1.26.3')).toBe(
      'Trivy found stdlib v1.26.3 at 11 paths in this image. JAVV counts it as one finding.',
    )
    expect(foundText(e({ scanner: 'grype', total: 1 }), 'go', null)).toBe(
      'Grype found go at 1 path in this image. JAVV counts it as one finding.',
    )
    expect(foundText(e({ total: 0 }), 'stdlib', 'v1.26.3')).toBe('Trivy gave no path for stdlib v1.26.3.')
    expect(foundText(e({ total: null }), 'openssl', '3.0.1')).toBe(
      'The Trivy scan of this image did not report paths for openssl 3.0.1.',
    )
  })

  it('an OS package: Trivy gives no path, and Grype lists the files that show it is installed (issue 1205)', () => {
    expect(foundText(e({ total: 0, osPackage: true }), 'perl', '5.32.1')).toBe(
      'perl 5.32.1 is an OS package. Trivy gives no path for an OS package.',
    )
    expect(foundText(e({ scanner: 'grype', total: 9, osPackage: true }), 'perl', '5.32.1')).toBe(
      'Grype found perl 5.32.1 at 9 paths in this image. JAVV counts it as one finding. ' +
        'For an OS package, Grype lists the files that show that the package is installed.',
    )
    // the sentences are about the scanner that behaves so: the other scanner keeps the plain text
    expect(foundText(e({ total: 2, osPackage: true }), 'perl', null)).toBe(
      'Trivy found perl at 2 paths in this image. JAVV counts it as one finding.',
    )
    expect(foundText(e({ scanner: 'grype', total: 0, osPackage: true }), 'perl', null)).toBe('Grype gave no path for perl.')
    // a scan that sent no paths says so, an OS package too
    expect(foundText(e({ total: null, osPackage: true }), 'perl', null)).toBe(
      'The Trivy scan of this image did not report paths for perl.',
    )
  })

  it('the hover of a Trivy 0 on an OS package says why (issue 1205)', () => {
    expect(countTitle([e({ total: 0, osPackage: true }), e({ scanner: 'grype', total: 9, osPackage: true })])).toBe(
      'Trivy: no path. Trivy gives no path for an OS package. Grype: 9 paths.',
    )
    expect(countTitle([e({ scanner: 'grype', total: 0, osPackage: true })])).toBe('Grype: the scanner gave no path.')
  })

  it('says when JAVV keeps fewer paths than the scanner reported', () => {
    expect(keptText(e({ total: 70, paths: Array.from({ length: 64 }, (_, i) => `/p${i}`) }))).toBe(
      'JAVV keeps the first 64 of 70 paths.',
    )
    expect(keptText(e({ total: 2, paths: ['/a', '/b'] }))).toBeNull()
    expect(keptText(e({ total: null }))).toBeNull()
  })

  it('shortens a digest to its first 12 characters', () => {
    expect(shortDigest('sha256:1eba82e9a1b2c3d4e5f6')).toBe('sha256:1eba82e9a1b2')
  })
})

describe('FindingPaths', () => {
  const mountIt = (entries: Entry[]) =>
    mount(FindingPaths, { props: { entries, packageName: 'stdlib', version: 'v1.26.3' } })

  it('lists the paths of each finding in its own block, in the given order', () => {
    const w = mountIt([
      e({ total: 2, paths: ['/usr/bin/a', '/usr/bin/b'] }),
      e({ scanner: 'grype', total: 1, paths: ['/usr/local/go/bin/go'] }),
    ])
    const blocks = w.findAll('.paths-block')
    expect(blocks.map((b) => b.attributes('aria-label'))).toEqual(['Paths from Trivy', 'Paths from Grype'])
    expect(blocks[0]!.findAll('li').map((li) => li.text())).toEqual(['/usr/bin/a', '/usr/bin/b'])
    expect(blocks[1]!.findAll('li').map((li) => li.text())).toEqual(['/usr/local/go/bin/go'])
  })

  it('the chip of its scanner leads each block, as in the Scanners column (option B2)', () => {
    const w = mountIt([e({ total: 0 }), e({ scanner: 'grype', total: 1, paths: ['/x'] })])
    const blocks = w.findAll('.paths-block')
    expect(blocks.map((b) => b.find('.paths-say').findComponent(ScannerTag).props('name'))).toEqual(['trivy', 'grype'])
  })

  it('a path from the image shows as text, never as markup', () => {
    const evil = '/tmp/<img src=x onerror=alert(1)>'
    const w = mountIt([e({ total: 1, paths: [evil] })])
    expect(w.find('img').exists()).toBe(false)
    expect(w.find('li').text()).toBe(evil)
  })

  it('a finding with no path says why and lists nothing', () => {
    const w = mountIt([e({ total: 0 }), e({ scanner: 'grype', total: 1, paths: ['/x'] })])
    const [first] = w.findAll('.paths-block')
    expect(first!.text()).toContain('Trivy gave no path for stdlib v1.26.3.')
    expect(first!.find('ul').exists()).toBe(false)
  })

  it('an OS package: the block of each scanner says what its paths are (issue 1205)', () => {
    const w = mountIt([
      e({ total: 0, osPackage: true }),
      e({ scanner: 'grype', total: 1, paths: ['/var/lib/dpkg/status'], osPackage: true }),
    ])
    const [trivy, grype] = w.findAll('.paths-say').map((p) => p.text())
    expect(trivy).toContain('stdlib v1.26.3 is an OS package. Trivy gives no path for an OS package.')
    expect(grype).toContain('For an OS package, Grype lists the files that show that the package is installed.')
  })

  it('names the digest only when the row holds more than one', () => {
    expect(mountIt([e({ total: 1, paths: ['/x'] })]).find('.paths-digest').exists()).toBe(false)
    const w = mountIt([
      e({ digest: 'sha256:aaaaaaaaaaaaaaaa', total: 1, paths: ['/x'] }),
      e({ digest: 'sha256:bbbbbbbbbbbbbbbb', total: 1, paths: ['/y'] }),
    ])
    expect(w.findAll('.paths-digest').map((d) => d.text())).toEqual([
      'Digest sha256:aaaaaaaaaaaa.',
      'Digest sha256:bbbbbbbbbbbb.',
    ])
  })

  it('says when JAVV keeps fewer paths than the scanner reported', () => {
    const w = mountIt([e({ total: 70, paths: ['/a'] })])
    expect(w.text()).toContain('JAVV keeps the first 1 of 70 paths.')
  })
})

describe('pathsOf: the package type of the finding (issue 1205)', () => {
  const row = (ptype: string | null) => ({ scanner: 'grype', image_digest: 'sha256:a', ptype, locations_total: 1, locations: ['/x'] }) as unknown as FindingRow

  it('the OS package types of the two scanners are OS packages', () => {
    const types = ['os', 'deb', 'apk', 'rpm']
    expect(types.filter((t) => pathsOf(row(t)).osPackage)).toEqual(types)
  })

  it('a language package, a binary or no type is not', () => {
    const types = ['gobinary', 'go-module', 'binary', 'jar', 'java-archive', 'python-pkg', 'npm', null]
    expect(types.filter((t) => pathsOf(row(t)).osPackage)).toEqual([])
    expect(isOsPackage(undefined)).toBe(false)
  })
})
