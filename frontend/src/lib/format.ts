/** The one number format of the app: en-US digit groups, whatever the locale of the browser. */
export const fmt = (n: number) => n.toLocaleString('en-US')
