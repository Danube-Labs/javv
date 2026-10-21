/** The typed values of a multi text field (issue 949): what one Enter in the filter bar adds. */

/**
 * The values a typed draft adds to `chosen`, and the ones left over past `max`. A pasted list
 * splits on commas and a leading `!` is dropped: the URL reads both as separators, so a value
 * that kept them would mean something else after a reload (the mode control sets is / is not).
 * A value already chosen is dropped.
 */
export function typedValuesToAdd(
  draft: string,
  chosen: readonly string[],
  max = Number.POSITIVE_INFINITY,
): { add: string[]; left: string[] } {
  const all = [...chosen]
  const left: string[] = []
  for (const part of draft.split(',')) {
    const text = part.trim().replace(/^!+/, '').trim()
    if (!text || all.includes(text) || left.includes(text)) continue
    if (all.length < max) all.push(text)
    else left.push(text)
  }
  return { add: all.slice(chosen.length), left }
}

/** A field label inside a sentence: "Add image…", "Clear package", but "Add CVE…". */
export function inText(label: string): string {
  return /^[A-Z]+$/.test(label) ? label : label.toLowerCase()
}
