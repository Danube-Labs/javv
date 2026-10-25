/**
 * Dashboard files (issue 440): the import call and the words for its answers. The generated call
 * would send its string body as JSON (a quoted string, one line), and a `File.text()` read would
 * change the bytes (it drops a byte-order mark and replaces bytes that are not UTF-8). So the
 * import sends the file itself, and the backend checks the bytes the user picked.
 */
import { importDashboardsApiV1DashboardsImportPost } from '@/api/generated'

export const EXPORT_PATH = '/api/v1/dashboards/export.ndjson'
export const NO_IMPORT_NOTE = 'Your role cannot import dashboards.'
export const EMPTY_FILE_NOTE = 'The file is empty. Choose a file from Export.'

export interface ImportLineResult {
  line: number
  status: 201 | 409 | 422
  dashboard_id?: string
  errors?: { loc: (string | number)[]; msg: string; type: string }[]
}

export interface ImportOutcome {
  results: ImportLineResult[]
  created: number
  conflicts: number
  invalid: number
}

export type ImportAnswer = { ok: true; outcome: ImportOutcome } | { ok: false; status: number }

export async function importDashboards(file: Blob, copy: boolean): Promise<ImportAnswer> {
  try {
    const { response, data } = await importDashboardsApiV1DashboardsImportPost({
      body: file as unknown as string,
      query: copy ? { copy: true } : undefined,
      bodySerializer: (body: unknown) => body as string,
    })
    if (response?.ok && data) return { ok: true, outcome: data as unknown as ImportOutcome }
    return { ok: false, status: response?.status ?? 0 }
  } catch {
    return { ok: false, status: 0 }
  }
}

/** The words for an import that got no result for each line. `copy` is the mode of the import. */
export function importFailureCopy(status: number, copy: boolean): string {
  if (status === 413)
    return 'The file is too large: over the size limit of JAVV (4 MiB unless your operator changed it), or over 1,000 dashboards.'
  if (status === 403) return NO_IMPORT_NOTE
  if (status === 0) return 'The import did not reach JAVV. Check the connection, then try again.'
  // in each case below some or all lines can have made their dashboards, so the words say what a
  // second import of the same file does
  const again = copy
    ? 'If you import the file again with Make copies, JAVV makes those dashboards a second time.'
    : 'If you import the file again with Keep the IDs, JAVV does not make those dashboards again.'
  if (status >= 200 && status < 300)
    return `JAVV did the import, but its answer could not be read. The list shows the dashboards that it made. ${again}`
  // a gateway in front of JAVV gave up waiting: the backend can still be at work on the file
  if (status === 504)
    return `The answer took too long, but JAVV can still be at work on the file. Read the list again in a minute. ${again}`
  // a store failure stops the import, and the lines before it keep their dashboards (docs/API.md)
  if (status === 429 || status >= 500) {
    const why = status === 429 ? 'The search backend was busy, so the import stopped.' : 'The import stopped.'
    return `${why} The lines before the failure made their dashboards. ${again}`
  }
  return 'JAVV did not import the file. No dashboard was made.'
}

/** Plain words for the error types that a dashboard file gives most. */
const ERROR_WORDS: Record<string, string> = {
  json_invalid: 'not a line of JSON',
  dict_type: 'not a dashboard',
  unicode_decode: 'not UTF-8 text',
  too_many_fields: 'more fields than a dashboard has',
  extra_forbidden: 'a field that a dashboard does not have',
  missing: 'a field is missing',
  literal_error: 'a value that JAVV does not know',
  string_pattern_mismatch: 'an ID that is not 32 hexadecimal characters',
  too_long: 'too many items',
}

/** The words for each check of a dashboard that the backend raises as a `value_error`
 * (`routers/dashboards.py`). Its message names values from the file, so it is never shown. */
export const VALUE_ERROR_WORDS: readonly (readonly [RegExp, string])[] = [
  [/has no \S+ height/, 'a height that this panel does not have'],
  [/must fit in the two columns/, 'a panel that does not fit in the two columns'],
  [/has no scanner data/, 'a scanner on a panel that has no scanner data'],
  [/overlaps/, 'two panels in the same place'],
  [/roles go with sharing/, 'roles that do not agree with the sharing'],
]
const VALUE_ERROR_ELSE = 'a value that JAVV cannot use'

/** The singular of a list field, for "panels.0" as "panel 1". */
const ITEM_NAMES: Record<string, string> = { panels: 'panel', roles: 'role' }

/** "panels.0.panel" as "panel 1, panel": the place that a person can find in the file, with
 * the items of a list counted from 1. */
function place(loc: (string | number)[]): string {
  const parts: string[] = []
  for (let i = 0; i < loc.length; i++) {
    const part = loc[i]!
    const item = typeof part === 'string' ? ITEM_NAMES[part] : undefined
    const next = loc[i + 1]
    if (item && typeof next === 'number') {
      parts.push(`${item} ${next + 1}`)
      i++
    } else parts.push(String(part))
  }
  return parts.join(', ')
}

function errorWords(e: { msg: string; type: string }): string {
  if (e.type === 'value_error') return VALUE_ERROR_WORDS.find(([re]) => re.test(e.msg))?.[1] ?? VALUE_ERROR_ELSE
  return ERROR_WORDS[e.type] ?? e.msg
}

/** One result line in words. */
export function lineResultCopy(r: ImportLineResult): string {
  if (r.status === 201) return 'Made'
  if (r.status === 409) return 'ID exists, not made'
  const first = r.errors?.[0]
  if (!first) return 'Not correct'
  const where = first.loc.length > 0 ? ` (${place(first.loc)})` : ''
  const more = (r.errors?.length ?? 0) > 1 ? `, and ${(r.errors?.length ?? 1) - 1} more` : ''
  return `Not correct: ${errorWords(first)}${where}${more}`
}
