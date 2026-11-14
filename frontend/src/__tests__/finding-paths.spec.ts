/**
 * The files of a finding (issue 1077): the cell text, the hover text and the list under a row.
 * Each entry is one finding of one scanner, so two entries are two numbers, never a sum. `null`
 * (the scan sent no paths) and `0` (the scanner gave none) must not read the same.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FindingPaths from '@/components/finding/FindingPaths.vue'
import {
  countText,
  countTitle,
  type FindingPaths as Entry,
  foundText,
  hasPaths,
  keptText,
  openLabel,
  shortDigest,
} from '@/findings/paths'

const e = (over: Partial<Entry>): Entry => ({
  scanner: 'trivy',
  digest: 'sha256:aaa',
  total: 0,
  paths: [],
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

  it('a row opens only when a finding has a path to show, one path included', () => {
    expect(hasPaths([e({ total: 0 }), e({ total: null })])).toBe(false)
    expect(hasPaths([e({ total: 1, paths: ['/usr/bin/go'] })])).toBe(true)
  })
})

describe('the sentences over the list', () => {
  it('names the scanner, the package and its version', () => {
    expect(foundText(e({ total: 11 }), 'stdlib', 'v1.26.3')).toBe(
      'Trivy found stdlib v1.26.3 at 11 paths in this image. The finding counts one time.',
    )
    expect(foundText(e({ scanner: 'grype', total: 1 }), 'go', null)).toBe(
      'Grype found go at 1 path in this image. The finding counts one time.',
    )
    expect(foundText(e({ total: 0 }), 'openssl', '3.0.1')).toBe('Trivy gave no path for openssl 3.0.1.')
    expect(foundText(e({ total: null }), 'openssl', '3.0.1')).toBe(
      'This scan of Trivy did not report the paths of openssl 3.0.1.',
    )
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
