/**
 * The logic of the AI agents (MCP) section (SCREENS §13.9, issue 1096 step 4): pure, unit-tested.
 * The status of a token is the rule of `tokensForm.ts`. The window guards mirror the backend's own
 * rules (`routers/mcp_tokens.py`), so a name or an expiry that the API would 422 is never sent.
 */
import { firstExpiryDate } from '@/approvals/viewModel'

export type McpLevel = 'read' | 'write' | 'write_risk_accept'

export interface McpTokenRow {
  name: string
  level: McpLevel
  created_by: string | null
  created_at: string | null
  expiry: string | null
  disabled: boolean | null
  last_used_at: string | null
}

/** The levels of D5, in the order the window offers them. `note` is the line under the choice. */
export const MCP_LEVELS: { value: McpLevel; label: string; note: string }[] = [
  { value: 'read', label: 'Read', note: 'Reads the data of all clusters. It changes nothing.' },
  {
    value: 'write',
    label: 'Write',
    note: 'Also sets the triage of findings and makes "Not affected" decisions.',
  },
  {
    value: 'write_risk_accept',
    label: 'Write and risk accept',
    note: 'Also accepts a risk, and changes or revokes a risk acceptance.',
  },
]

export const levelLabel = (level: string): string => MCP_LEVELS.find((l) => l.value === level)?.label ?? level

/** The username rule of the backend (`auth/usernames.py`): the principal `mcp:<name>` then reads
 *  like a user id in the audit log. */
export const MCP_NAME = /^[a-z0-9._-]{3,64}$/
export const MCP_NAME_HINT = '3 to 64 lower-case letters, digits, dots, underscores or hyphens'

/** The cap of D10, as the backend's `MAX_EXPIRY_DAYS` (stated in docs/API.md, not a setting). */
export const MAX_EXPIRY_DAYS = 90
/** The day the window puts in the expiry box. */
export const DEFAULT_EXPIRY_DAYS = 30

const DAY_MS = 86_400_000
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10)

/** The first and the last day the expiry box accepts, as `YYYY-MM-DD` in UTC. A day stops at
 *  00:00 UTC, so the first is tomorrow (as for a decision, issue 984), and the last is the UTC day
 *  of now + 90 days: its 00:00 is never later than the backend's cap. */
export function expiryRange(nowMs: number): { first: string; last: string } {
  return { first: firstExpiryDate(nowMs), last: isoDay(nowMs + MAX_EXPIRY_DAYS * DAY_MS) }
}

export const defaultExpiryDay = (nowMs: number): string => isoDay(nowMs + DEFAULT_EXPIRY_DAYS * DAY_MS)

/** The expiry of the request for a day of the box, or null when the API would refuse the day. */
export function expiryIso(day: string, nowMs: number): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || Number.isNaN(Date.parse(`${day}T00:00:00Z`))) return null
  const { first, last } = expiryRange(nowMs)
  return day >= first && day <= last ? `${day}T00:00:00.000Z` : null
}

export const EXPIRY_HINT = `at most ${MAX_EXPIRY_DAYS} days. The token stops at 00:00 UTC on this day`
export const EXPIRY_PROBLEM = `Pick a day after today and at most ${MAX_EXPIRY_DAYS} days from today.`

/** The path of the endpoint (`mcp/server.py`). The frontend server sends each `/api` request to the
 *  backend, so the address of this page plus the path is the URL an agent uses. */
export const MCP_PATH = '/api/v1/mcp'
export const endpointUrl = (origin: string): string => `${origin.replace(/\/+$/, '')}${MCP_PATH}`
