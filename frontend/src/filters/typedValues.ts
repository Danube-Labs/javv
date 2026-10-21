/** The typed values of a multi text field (issue 949): what one Enter in the filter bar adds. */
import { MAX_FILTER_VALUES } from '@/filters/fields.config'

/**
 * The values a typed draft adds to `chosen`. A pasted list splits on commas and a leading `!` is
 * dropped: the URL reads both as separators, so a value that kept them would mean something else
 * after a reload (the mode control sets is / is not). Values already chosen and values past the
 * API's cap are left out.
 */
export function typedValuesToAdd(draft: string, chosen: readonly string[]): string[] {
  const all = [...chosen]
  for (const part of draft.split(',')) {
    const text = part.trim().replace(/^!+/, '').trim()
    if (text && !all.includes(text) && all.length < MAX_FILTER_VALUES) all.push(text)
  }
  return all.slice(chosen.length)
}

/** A field label inside a sentence: "Add image…", "Clear package", but "Add CVE…". */
export function inText(label: string): string {
  return /^[A-Z]+$/.test(label) ? label : label.toLowerCase()
}
