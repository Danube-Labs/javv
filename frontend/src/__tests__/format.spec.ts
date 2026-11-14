/**
 * The one number format of the app: en-US digit groups, whatever the browser's own locale is
 * (issue 1190, row 12).
 */
import { afterEach, describe, expect, it } from 'vitest'
import { fmt } from '@/lib/format'
import { fmt as lensFmt } from '@/lib/scannerLens'

const nativeToLocaleString = Number.prototype.toLocaleString

afterEach(() => {
  Number.prototype.toLocaleString = nativeToLocaleString
})

describe('fmt', () => {
  it('is the one function that scannerLens exports to its users', () => {
    expect(lensFmt).toBe(fmt)
  })

  it.each([
    [0, '0'],
    [999, '999'],
    [1000, '1,000'],
    [1234567, '1,234,567'],
    [-4321, '-4,321'],
    [1234.5, '1,234.5'],
  ])('writes %d as %s', (n, text) => {
    expect(fmt(n)).toBe(text)
  })

  it('keeps the en-US groups in a browser with a German locale', () => {
    // A browser in German formats with dots when no locale is given. Node has no switch for its
    // default locale, so the stub plays that browser.
    Number.prototype.toLocaleString = function (
      this: number,
      locales?: Intl.LocalesArgument,
      options?: Intl.NumberFormatOptions,
    ) {
      return nativeToLocaleString.call(this, locales ?? 'de-DE', options)
    }
    expect((1234567).toLocaleString()).toBe('1.234.567')
    expect(fmt(1234567)).toBe('1,234,567')
  })
})
