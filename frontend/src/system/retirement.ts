/**
 * The retirement countdown (issue 765) as a pure view-model over one `GET /api/v1/clusters` row:
 * the backend computes `warns_at` / `retires_at` from the cluster's own window, nothing here
 * re-derives a window. "No scans for N days" reads `last_scan_at`, never `silent_since`, which
 * may start at a return from retirement instead of a scan.
 */
const DAY_MS = 86_400_000

/** How often an open page moves its countdowns and re-reads the cluster list: the banner and the
 * All clusters chip share it, on the freshness banner's cadence. Fixed in code, as ruled. */
export const RETIREMENT_TICK_MS = 10 * 60_000

export interface RetirementSchedule {
  retired?: boolean
  last_scan_at?: string | null
  warns_at?: string | null
  retires_at?: string | null
}

export type RetirementStatus =
  | { kind: 'retired' }
  | { kind: 'active' }
  /** inside the warning window; `days` until retirement, never below 1 */
  | { kind: 'warning'; days: number; silentDays: number | null }
  /** past its date but not retired: the sweep is holding (no cluster is scanning) or has not run */
  | { kind: 'held'; silentDays: number | null }

export function retirementStatus(row: RetirementSchedule, nowMs: number = Date.now()): RetirementStatus {
  if (row.retired) return { kind: 'retired' }
  const warns = row.warns_at ? Date.parse(row.warns_at) : NaN
  const retires = row.retires_at ? Date.parse(row.retires_at) : NaN
  if (!Number.isFinite(warns) || !Number.isFinite(retires) || nowMs < warns) return { kind: 'active' }
  const lastScan = row.last_scan_at ? Date.parse(row.last_scan_at) : NaN
  const silentDays = Number.isFinite(lastScan) ? Math.floor((nowMs - lastScan) / DAY_MS) : null
  if (nowMs >= retires) return { kind: 'held', silentDays }
  return { kind: 'warning', days: Math.max(1, Math.ceil((retires - nowMs) / DAY_MS)), silentDays }
}

const plural = (n: number, unit: string) => `${n} ${unit}${n === 1 ? '' : 's'}`

/** The countdown alone: "It will be retired in 5 days unless a scan arrives.", or null. `alone`:
 * the only cluster listed, which the sweep never retires (no other cluster can show that scans
 * still reach JAVV), so it gets no countdown. */
export function retirementCountdown(status: RetirementStatus, alone = false): string | null {
  if (alone && (status.kind === 'warning' || status.kind === 'held')) {
    return 'As the only cluster, it is not retired automatically. Retire it by hand in Settings if it is gone.'
  }
  if (status.kind === 'warning') {
    return `It will be retired in ${plural(status.days, 'day')} unless a scan arrives.`
  }
  if (status.kind === 'held') {
    return 'It is past its retirement date: the next retirement sweep retires it unless a scan arrives, and waits while no cluster is scanning.'
  }
  return null
}

/** What the cluster's silence is, to follow its name: "has sent no scans for 40 days.", or null
 * outside the warning window. */
export function silenceClause(status: RetirementStatus): string | null {
  if (status.kind !== 'warning' && status.kind !== 'held') return null
  return status.silentDays === null
    ? 'has never sent a scan.'
    : `has sent no scans for ${plural(status.silentDays, 'day')}.`
}

/** The last day, or past its date: the red step of the health ramp rather than the amber one. */
export function isUrgent(status: RetirementStatus, alone = false): boolean {
  if (alone) return false
  return status.kind === 'held' || (status.kind === 'warning' && status.days <= 1)
}

/** The All clusters chip: "retires in 5 days" / "retirement due", or null outside the window. */
export function retirementChip(
  status: RetirementStatus,
  alone = false,
): { label: string; tone: 'warn' | 'down' } | null {
  if (alone) return null
  const tone = isUrgent(status) ? 'down' : 'warn'
  if (status.kind === 'warning') return { label: `retires in ${plural(status.days, 'day')}`, tone }
  if (status.kind === 'held') return { label: 'retirement due', tone }
  return null
}
