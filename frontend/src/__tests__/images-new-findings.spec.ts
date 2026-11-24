/**
 * The New findings strip on Images (issue 1292, ruling 1): it takes the Scanner, Namespace, Image
 * and Tag filters of the screen, with their "is not" side, and says that only these apply.
 */
import { describe, expect, it } from 'vitest'

import { screenFilters, stripFilters, stripFiltersNote } from '@/images/imageFilters'

describe('stripFilters (pure)', () => {
  it('keeps the four filters that mean the same on the findings, and drops the others', () => {
    const query = stripFilters('c-1', {
      scanner: ['grype'],
      namespace: ['shop', 'pay'],
      repo: ['shop/app'],
      tag: ['1.4.1'],
      severity: ['critical'],
      attr: ['fixable'],
      q: ['ssl'],
    })
    expect(query).toEqual({
      cluster_id: 'c-1',
      scanner: 'grype',
      namespace: ['shop', 'pay'],
      image_repo: ['shop/app'],
      tag: ['1.4.1'],
    })
  })

  it('an "is not" filter goes as its exclude side', () => {
    expect(stripFilters('c-1', { tag: ['latest'], scanner: ['trivy'] }, { tag: 'not', scanner: 'not' })).toEqual({
      cluster_id: 'c-1',
      exclude_tag: ['latest'],
      exclude_scanner: 'trivy',
    })
  })

  it('no filter is the whole cluster', () => {
    expect(stripFilters('c-1', {})).toEqual({ cluster_id: 'c-1' })
  })

  it('the note names the filters with the labels of the filter bar', () => {
    expect(stripFiltersNote()).toBe('Only the Scanner, Namespace, Image and Tag filters apply.')
  })
})

describe('screenFilters (pure): all the filters of Images, for Scan ingest (issue 1293)', () => {
  it('holds every filter of the screen, so the strip knows which ones it does not apply', () => {
    const query = screenFilters(
      'c-1',
      { q: ['nginx'], severity: ['critical'], scanner: ['trivy'], attr: ['fixable'], namespace: ['shop'], repo: ['app'], tag: ['1.4'] },
      { namespace: 'not' },
    )
    expect(query).toEqual({
      cluster_id: 'c-1',
      q: 'nginx',
      severity: ['critical'],
      scanner: 'trivy',
      fixable: true,
      exclude_namespace: ['shop'],
      image_repo: ['app'],
      tag: ['1.4'],
    })
  })
})
