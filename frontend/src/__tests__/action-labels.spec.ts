/**
 * Each action the backend writes on an audit row has a plain name, and the Action filter of the
 * Audit log lists it. An action with no name shows its stored words, and one the filter does not
 * list cannot be found by action at all (issue 933).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { ACTION_LABELS } from '@/audit/actionLabels'
import { AUDIT_ACTIONS } from '@/audit/fields.config'

const BACKEND = resolve(process.cwd(), '..', 'backend/src/backend')

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return pythonFiles(path)
    return name.endsWith('.py') ? [path] : []
  })
}

/** each action name the backend writes on an audit row */
function journaledActions(): Set<string> {
  const names = new Set<string>()
  for (const path of pythonFiles(BACKEND)) {
    const text = readFileSync(path, 'utf8')
    // append_field_change(..., action="x") and append_auth_event(..., action="x")
    for (const m of text.matchAll(/\baction="(\w+)"/g)) names.add(m[1]!)
    // the triage service builds its rows as dicts first
    for (const m of text.matchAll(/"action": "(\w+)"/g)) names.add(m[1]!)
  }
  // the triage service names a state change by its target state
  const triage = readFileSync(join(BACKEND, 'triage/service.py'), 'utf8')
  const states = /_STATE_ACTIONS = \{([^}]*)\}/.exec(triage)![1]!
  for (const m of states.matchAll(/: "(\w+)"/g)) names.add(m[1]!)
  return names
}

describe('the plain names of audit actions', () => {
  const actions = journaledActions()

  it('the reader finds the actions of each kind of writer', () => {
    // a triage state, a triage dict entry, a settings change, an account event, a job run
    for (const a of ['risk_accept', 'note', 'sla_policy_change', 'login', 'session_sweep_run']) {
      expect(actions).toContain(a)
    }
  })

  it('every action the backend writes has a name', () => {
    expect([...actions].filter((a) => !(a in ACTION_LABELS))).toEqual([])
  })

  it('every action the backend writes is in the Action filter', () => {
    const listed: readonly string[] = AUDIT_ACTIONS
    expect([...actions].filter((a) => !listed.includes(a))).toEqual([])
  })

  it('a settings change is called by its setting', () => {
    expect(ACTION_LABELS['retention_change']).toBe('History retention')
    expect(ACTION_LABELS['scan_scope_change']).toBe('Scan scope')
    expect(ACTION_LABELS['sla_policy_change']).toBe('SLA policy')
  })
})
