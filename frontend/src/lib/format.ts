/** The one number format of the app: en-US digit groups, whatever the locale of the browser. */
export const fmt = (n: number) => n.toLocaleString('en-US')

/** The label of a day, under a chart axis or in a line of text: the day and the short month
 * (`3 Nov`), in the time zone of the browser. */
export const dayLabel = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
