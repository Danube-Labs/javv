/**
 * Token panel logic (§13.5) — pure, unit-tested. Status is derived, never stored: revoked wins
 * (`disabled` is the server truth), then a past `expiry` reads expired (ingest 401s on it), else
 * active. Mint expiry: the `datetime-local` string parses in the ADMIN'S local zone and ships as
 * ISO — the backend re-validates future-ness (contract guard mirrors its rule, omit-not-emit).
 */
export interface TokenRow {
  id: string
  cluster_id: string
  scanner: string
  scope: string | null
  created_by: string | null
  created_at: string | null
  expiry: string | null
  disabled: boolean | null
  last_ingest_at: string | null
}

export type TokenStatus = 'active' | 'expired' | 'revoked'

export function tokenStatus(row: TokenRow, now: Date): TokenStatus {
  if (row.disabled) return 'revoked'
  if (row.expiry !== null && new Date(row.expiry) <= now) return 'expired'
  return 'active'
}

export const TOKEN_STATUS_TONE = { active: 'ok', expired: 'warn', revoked: 'muted' } as const

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/

/** The UiDateTime halves → the mint body's expiry. Distinguishes the three cases so a
 * half-filled pair can never silently mean "no expiry": both halves empty = `omit`; a valid
 * FUTURE local datetime = `iso`; anything else (half-filled, malformed HH:mm, past) =
 * `invalid` — and an invalid expiry never rides the request (the 422 is unreachable). */
export function mintExpiry(
  parts: { date: string; time: string },
  now: Date,
): { kind: 'omit' } | { kind: 'iso'; iso: string } | { kind: 'invalid' } {
  if (parts.date === '' && parts.time === '') return { kind: 'omit' }
  if (parts.date === '' || !HHMM.test(parts.time)) return { kind: 'invalid' }
  const parsed = new Date(`${parts.date}T${parts.time}`) // the admin's local zone, by design
  if (Number.isNaN(parsed.getTime()) || parsed <= now) return { kind: 'invalid' }
  return { kind: 'iso', iso: parsed.toISOString() }
}

/** The mint picker's "New cluster…" choice. A `+` can never start a cluster id, so it cannot
 * collide with a listed one. */
export const NEW_CLUSTER = '+new'

/** Mirrors the backend's `CLUSTER_ID_RE` (`core/identifiers.py`; a spec pins the two), so a typed
 * id the API would 422 never rides the mint. */
export const CLUSTER_ID = /^[a-z0-9][a-z0-9-]{7,63}$/

export const CLUSTER_ID_PROBLEM =
  'A cluster ID is 8 to 64 characters: lowercase letters, digits and dashes, starting with a letter or digit.'

/** The cluster a mint targets: the picked one, or the typed id once it is well-formed. */
export function mintClusterId(choice: string, typed: string): string | null {
  if (choice !== NEW_CLUSTER) return choice === '' ? null : choice
  const id = typed.trim()
  return CLUSTER_ID.test(id) ? id : null
}
