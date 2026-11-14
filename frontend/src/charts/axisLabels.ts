/** The label of a day under a chart axis: the day and the short month (`3 Nov`), in the time zone
 * of the browser. */
export const dayLabel = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
