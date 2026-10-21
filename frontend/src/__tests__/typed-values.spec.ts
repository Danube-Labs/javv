/** Issue 949 PR C: what one Enter in a multi text field's edit box adds. */
import { describe, expect, it } from 'vitest'

import { MAX_FILTER_VALUES } from '@/filters/fields.config'
import { inText, typedValuesToAdd } from '@/filters/typedValues'

describe('typedValuesToAdd', () => {
  it('a pasted list splits on commas, trimmed, blanks dropped', () => {
    expect(typedValuesToAdd(' CVE-1, CVE-2 ,, ', []).add).toEqual(['CVE-1', 'CVE-2'])
  })

  it('a leading ! is dropped: the mode control sets is / is not, not the value', () => {
    expect(typedValuesToAdd('!web', ['api']).add).toEqual(['web'])
  })

  it('a value already chosen, or typed twice, is added once', () => {
    expect(typedValuesToAdd('api, web, web', ['api']).add).toEqual(['web'])
  })

  it('stops at the cap and hands back what is left over', () => {
    const full = Array.from({ length: MAX_FILTER_VALUES - 1 }, (_, i) => `v${i}`)
    expect(typedValuesToAdd('a, b, c', full, MAX_FILTER_VALUES)).toEqual({ add: ['a'], left: ['b', 'c'] })
    expect(typedValuesToAdd('d', [...full, 'a'], MAX_FILTER_VALUES)).toEqual({ add: [], left: ['d'] })
  })

  it('with no cap, adds everything (a screen that filters in the browser)', () => {
    const many = Array.from({ length: 40 }, (_, i) => `v${i}`)
    expect(typedValuesToAdd(many.join(','), []).add).toHaveLength(40)
  })
})

describe('inText', () => {
  it('lowers a label inside a sentence, but keeps an all-capitals one', () => {
    expect(inText('Image')).toBe('image')
    expect(inText('CVE')).toBe('CVE')
  })
})
