/**
 * The About page's pure pieces (issue 341): the text "Copy diagnostics" puts on the clipboard,
 * the copy for a failed read, and the 24-hour UTC stamp both use. A value the page couldn't read
 * is written as `unavailable`, never dropped or guessed, so a pasted report shows what was
 * missing.
 */
import type { ProvenanceRow } from '@/components/scanners/ScannerStatusCard.vue'

/** `GET /api/v1/meta` (issues 261, 341) */
export type RunningMeta = {
  version: string
  mapping_version: number
  envelope_versions: number[]
  opensearch_version: string | null
  python_version: string
}

const UNAVAILABLE = 'unavailable'

const pad = (n: number) => String(n).padStart(2, '0')

export function formatUtc(date: Date): string {
  return (
    `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ` +
    `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`
  )
}

function scannerLine(row: ProvenanceRow): string {
  const built = row.scanner_db_built ? formatUtc(new Date(row.scanner_db_built)) : 'unknown'
  return (
    `${row.scanner}: ${row.scanner_version ?? UNAVAILABLE} · ` +
    `vulnerability database ${row.scanner_db_version ?? 'unknown'}, built ${built}`
  )
}

export function buildDiagnostics(input: {
  meta: RunningMeta | null
  frontendVersion: string
  cluster: { id: string; name: string } | null
  scanners: ProvenanceRow[]
  userAgent: string
  now: Date
}): string {
  const { meta, cluster } = input
  const lines = [
    `JAVV diagnostics · ${formatUtc(input.now)}`,
    `JAVV release (backend): ${meta?.version ?? UNAVAILABLE}`,
    `Frontend build: ${input.frontendVersion}`,
    `Store schema: ${meta ? `v${meta.mapping_version}` : UNAVAILABLE}`,
    `Scanner report formats accepted: ${
      meta ? meta.envelope_versions.map((v) => `v${v}`).join(', ') : UNAVAILABLE
    }`,
    `OpenSearch: ${meta?.opensearch_version ?? UNAVAILABLE}`,
    `Python: ${meta?.python_version ?? UNAVAILABLE}`,
    `Cluster: ${cluster ? `${cluster.name} (${cluster.id})` : 'none selected'}`,
    ...(input.scanners.length ? input.scanners.map(scannerLine) : ['Scanners: no committed run']),
    `Browser: ${input.userAgent}`,
  ]
  return lines.join('\n')
}

/** 401 never reaches here (the client sends it to login) and 503 also raises the app banner. */
export function readFailureCopy(status: number | undefined): string {
  if (status === 429) return 'The backend is busy. Try again in a few seconds.'
  if (status === undefined || status >= 500) {
    return "The backend didn't answer, so these versions can't be shown right now."
  }
  return `The backend refused this read (HTTP ${status}).`
}
