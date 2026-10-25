/**
 * Dashboard files (issue 440, slice S6 on the backend): the import call and the words for its
 * answers. The generated call would send its string body as JSON (a quoted string, one line),
 * so the import passes the file text through unchanged.
 */
import { importDashboardsApiV1DashboardsImportPost } from '@/api/generated'
import { FAILURE_COPY } from '@/findings/failureCopy'

export const EXPORT_PATH = '/api/v1/dashboards/export.ndjson'
export const NO_IMPORT_NOTE = 'Your role cannot import dashboards.'

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

export async function importDashboards(text: string, copy: boolean): Promise<ImportAnswer> {
  try {
    const { response, data } = await importDashboardsApiV1DashboardsImportPost({
      body: text,
      query: copy ? { copy: true } : undefined,
      bodySerializer: (body: unknown) => body as string,
    })
    if (response?.ok && data) return { ok: true, outcome: data as unknown as ImportOutcome }
    return { ok: false, status: response?.status ?? 0 }
  } catch {
    return { ok: false, status: 0 }
  }
}

/** The words for an import that got no result for each line. */
export function importFailureCopy(status: number): string {
  if (status === 413)
    return 'The file is too large: over the size limit of JAVV (4 MiB unless your operator changed it), or over 1,000 dashboards.'
  if (status === 403) return NO_IMPORT_NOTE
  if (status === 429) return FAILURE_COPY.busy
  if (status === 0) return 'The import did not reach JAVV. Check the connection, then try again.'
  // a store failure stops the import after the lines before it were made (docs/API.md)
  return 'The import stopped. The lines before the failure made their dashboards. Check the list before you import again.'
}

/** Plain words for the error types that a dashboard file gives most; other types keep the
 * backend's own message. */
const ERROR_WORDS: Record<string, string> = {
  json_invalid: 'not a line of JSON',
  dict_type: 'not a dashboard',
  unicode_decode: 'not UTF-8 text',
  too_many_fields: 'more fields than a dashboard has',
  extra_forbidden: 'a field that a dashboard does not have',
  missing: 'a field is missing',
  literal_error: 'a value that JAVV does not know',
  string_pattern_mismatch: 'an ID that is not 32 hexadecimal characters',
}

/** "panels.0.panel" as "panel 1, panel": the place that a person can find in the file. */
function place(loc: (string | number)[]): string {
  const words = loc.map((part, i) =>
    typeof part === 'number' && loc[i - 1] === 'panels' ? `${part + 1}` : String(part),
  )
  return words.join(' ').replace(/^panels (\d+)/, 'panel $1,')
}

/** One result line in words. */
export function lineResultCopy(r: ImportLineResult): string {
  if (r.status === 201) return 'Made'
  if (r.status === 409) return 'ID exists, not made'
  const first = r.errors?.[0]
  if (!first) return 'Not correct'
  const what = ERROR_WORDS[first.type] ?? first.msg
  const where = first.loc.length > 0 ? ` (${place(first.loc)})` : ''
  const more = (r.errors?.length ?? 0) > 1 ? `, and ${(r.errors?.length ?? 1) - 1} more` : ''
  return `Not correct: ${what}${where}${more}`
}
