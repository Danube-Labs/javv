/**
 * Data inspector (issue 406) — the pure logic behind the screen: grouping the `_cat/indices`
 * rows into the INDEX-MAP rail (append-history families collapsed to one `-*` pattern with
 * summed counts), store-level stats, and the size formatting. The backend allowlist is the
 * authority; the DENIED list here only keeps un-inspectable credential indices out of the rail.
 */

export interface CatIndexRow {
  index: string
  'docs.count'?: string
  'store.size'?: string
  'pri.store.size'?: string
  health?: string
}

export interface RailEntry {
  /** what clicking inserts into the path box — a family pattern or a literal index name */
  pattern: string
  docs: number
}

export interface RailGroups {
  history: RailEntry[]
  state: RailEntry[]
  system: RailEntry[]
}

/** time-partitioned append families (INDEX-MAP §top) — many rollover indices, one rail row each */
const HISTORY_FAMILIES = [
  'javv-finding-occurrences',
  'javv-images',
  'javv-scan-events',
  'javv-inventory-runs',
  'javv-ingest-failures',
  'system-audit-log',
  'javv-metrics',
] as const

/** denied by the backend allowlist (credential material) — showing them would be a dead click */
const DENIED = new Set(['system-users', 'system-sessions', 'system-tokens'])

export function groupIndices(rows: CatIndexRow[]): RailGroups {
  const history = new Map<string, number>()
  const state: RailEntry[] = []
  const system: RailEntry[] = []
  for (const row of rows) {
    const name = row.index
    if (name.startsWith('.') || DENIED.has(name)) continue
    const docs = Number(row['docs.count'] ?? 0) || 0
    const family = HISTORY_FAMILIES.find((f) => name === f || name.startsWith(`${f}-`))
    if (family) {
      history.set(family, (history.get(family) ?? 0) + docs)
    } else if (name.startsWith('system-') || name === 'system-config') {
      system.push({ pattern: name, docs })
    } else {
      state.push({ pattern: name, docs })
    }
  }
  return {
    history: HISTORY_FAMILIES.filter((f) => history.has(f)).map((f) => ({
      pattern: `${f}-*`,
      docs: history.get(f) ?? 0,
    })),
    state: state.sort((a, b) => b.docs - a.docs),
    system: system.sort((a, b) => a.pattern.localeCompare(b.pattern)),
  }
}

/** 1234 → "1.2k", 28400000 → "28.4M" — the rail's compact count */
export function fmtDocs(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}k`
  return String(n)
}

/** bytes → "612 KB" / "2.1 GB" — budget meter + head stat */
export function fmtBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(1)} GB`
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1).replace(/\.0$/, '')} MB`
  if (n >= 1024) return `${Math.round(n / 1024)} KB`
  return `${n} B`
}

/** a finished job's count summary → one meta line: nested rebuild sections flatten to
 * "decisions.projected 4 · presence.rebuilt 66 · …", flat sweeps to "staled 0 · reverted 2" */
export function fmtJobResult(result: Record<string, unknown> | null | undefined): string {
  if (!result) return ''
  const parts: string[] = []
  for (const [key, value] of Object.entries(result)) {
    if (value !== null && typeof value === 'object') {
      for (const [inner, n] of Object.entries(value as Record<string, unknown>)) {
        parts.push(`${key}.${inner} ${n}`)
      }
    } else {
      parts.push(`${key} ${value}`)
    }
  }
  return parts.join(' · ')
}

export type JobHealth = 'ok' | 'failed' | 'overdue' | 'never_ran' | 'off'

/** one entry of `GET /api/v1/admin/jobs` (docs/API.md) */
export interface JobDoc {
  kind: string
  status: 'idle' | 'running' | 'done' | 'failed'
  /** null on a job that cannot be started from the Data inspector */
  capability: string | null
  runnable: boolean
  stale: boolean
  /** the job's cron expression; null when it has none */
  schedule: string | null
  next_run_at: string | null
  health: JobHealth
  requested_by?: string | null
  started_at?: string | null
  finished_at?: string | null
  result?: Record<string, unknown> | null
  error?: string | null
}

/** a job's last run for its table cell: what happened, the detail under it, and whether it
 * went wrong. `fmt` turns a timestamp into the words on screen */
export function jobLastRun(
  job: JobDoc,
  fmt: (iso: unknown) => string,
): { line: string; detail: string; bad: boolean } {
  if (job.status === 'running' && job.stale)
    return { line: `no heartbeat since ${fmt(job.started_at)}`, detail: 'You can run it again', bad: true }
  if (job.status === 'running')
    return { line: `running since ${fmt(job.started_at)}`, detail: `by ${job.requested_by}`, bad: false }
  if (job.status === 'done') return { line: fmt(job.finished_at), detail: fmtJobResult(job.result), bad: false }
  if (job.status === 'failed')
    return { line: `failed ${fmt(job.finished_at)}`, detail: job.error ?? 'see the backend log', bad: true }
  return { line: 'never', detail: '', bad: false }
}

const JOB_FLAG: Record<Exclude<JobHealth, 'off'>, { tone: 'ok' | 'warn' | 'down' | 'muted'; label: string }> = {
  ok: { tone: 'ok', label: 'on schedule' },
  overdue: { tone: 'warn', label: 'late' },
  failed: { tone: 'down', label: 'failed' },
  never_ran: { tone: 'muted', label: 'not run yet' },
}

/** the status chip for a job against its schedule. `off` says which thing is off: the job has
 * no schedule, or it has one and the scheduler is not running */
export function jobFlag(job: JobDoc): { tone: 'ok' | 'warn' | 'down' | 'muted'; label: string } {
  if (job.health === 'off') return { tone: 'muted', label: job.schedule ? 'scheduler off' : 'not scheduled' }
  return JOB_FLAG[job.health]
}

/** the Schedule cell: the cron expression, or why there is none */
export function jobSchedule(job: JobDoc): string {
  return job.schedule ?? (job.runnable ? 'by hand only' : 'switched off')
}

/** the Next run cell; a dash when the job or the scheduler is switched off */
export function jobNextRun(job: JobDoc, fmt: (iso: unknown) => string): string {
  return job.next_run_at ? fmt(job.next_run_at) : '-'
}

/** total store bytes from `_cat/indices` rows (pri.store.size strings like "1.2gb") */
export function totalStoreBytes(rows: CatIndexRow[]): number {
  const UNIT: Record<string, number> = { b: 1, kb: 1024, mb: 1024 ** 2, gb: 1024 ** 3, tb: 1024 ** 4 }
  let total = 0
  for (const row of rows) {
    const raw = row['store.size'] ?? row['pri.store.size']
    const m = raw ? /^([\d.]+)(b|kb|mb|gb|tb)$/.exec(raw) : null
    if (m) total += Number(m[1]) * (UNIT[m[2] ?? 'b'] ?? 1)
  }
  return total
}

/**
 * An index name split for middle truncation (issue 652): `head` truncates with an ellipsis and
 * `tail`, its last 10 characters, always shows, because the ending is what tells similar names
 * apart (a rollover date and run number, or the `-*` of a pattern). A short name keeps at
 * least half of itself in `head`. The parts rejoin into the full name.
 */
export function splitMiddle(name: string, tailLength = 10): { head: string; tail: string } {
  const n = Math.min(tailLength, Math.floor(name.length / 2))
  return { head: name.slice(0, name.length - n), tail: name.slice(name.length - n) }
}
