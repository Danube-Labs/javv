/** Issue 949 PR C: what one Enter in a multi text field's edit box adds. */
import { describe, expect, it } from 'vitest'

import { MAX_FILTER_VALUES } from '@/filters/fields.config'
import { inText, typedValuesToAdd } from '@/filters/typedValues'

describe('typedValuesToAdd', () => {
  it('a pasted list splits on commas, trimmed, blanks dropped', () => {
    expect(typedValuesToAdd(' CVE-1, CVE-2 ,, ', [])).toEqual(['CVE-1', 'CVE-2'])
  })

  it('a leading ! is dropped: the mode control sets is / is not, not the value', () => {
    expect(typedValuesToAdd('!web', ['api'])).toEqual(['web'])
  })

  it('a value already chosen, or typed twice, is added once', () => {
    expect(typedValuesToAdd('api, web, web', ['api'])).toEqual(['web'])
  })

  it('stops at the API cap of 32 values', () => {
    const full = Array.from({ length: MAX_FILTER_VALUES - 1 }, (_, i) => `v${i}`)
    expect(typedValuesToAdd('a, b', full)).toEqual(['a'])
    expect(typedValuesToAdd('c', [...full, 'a'])).toEqual([])
  })
})

describe('inText', () => {
  it('lowers a label inside a sentence, but keeps an all-capitals one', () => {
    expect(inText('Image')).toBe('image')
    expect(inText('CVE')).toBe('CVE')
  })
})
