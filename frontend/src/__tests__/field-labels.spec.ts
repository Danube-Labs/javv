/**
 * An audit row names the field it changed by a plain name, and shows a state or a reason by the
 * label the rest of the app uses (issue 931). The stored names and values do not change: the
 * CSV export and the API keep them.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { FIELD_LABELS, fieldLabel, fieldValue } from '@/audit/fieldLabels'

const BACKEND = resolve(process.cwd(), '..', 'backend/src/backend')

function pythonFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return pythonFiles(path)
    return name.endsWith('.py') ? [path] : []
  })
}

/** each field name the backend writes on an audit row */
function journaledFields(): Set<string> {
  const names = new Set<string>()
  for (const path of pythonFiles(BACKEND)) {
    const text = readFileSync(path, 'utf8')
    // append_field_change(..., field="x", ...)
    for (const call of text.split('append_field_change(').slice(1)) {
      const m = /\bfield="(\w+)"/.exec(call.slice(0, call.indexOf('\n)')))
      if (m) names.add(m[1]!)
    }
  }
  // the triage service builds its rows as dicts first
  const triage = readFileSync(join(BACKEND, 'triage/service.py'), 'utf8')
  for (const m of triage.matchAll(/"field": "(\w+)"/g)) names.add(m[1]!)
  return names
}

describe('the plain names of audit fields', () => {
  it('every field the backend writes on an audit row has a name', () => {
    const fields = journaledFields()
    // the reader works: it finds the triage fields and a settings field
    for (const f of ['state', 'vex_justification', 'assignee', 'notes', 'bulk_patch', 'sla_policy']) {
      expect(fields).toContain(f)
    }
    expect([...fields].filter((f) => !(f in FIELD_LABELS))).toEqual([])
  })

  it('the triage fields use the words of the triage panel', () => {
    expect(fieldLabel('state')).toBe('State')
    expect(fieldLabel('vex_justification')).toBe('Reason')
    expect(fieldLabel('assignee')).toBe('Assigned to')
    expect(fieldLabel('notes')).toBe('Note')
  })

  it('a field with no entry reads as its words, never as snake_case', () => {
    expect(fieldLabel('some_new_field')).toBe('some new field')
  })

  it('a state and a reason show their labels', () => {
    expect(fieldValue('state', 'not_affected')).toBe('Not affected')
    expect(fieldValue('vex_justification', 'component_not_present')).toBe('Component not present')
  })

  it('a value of another field, or one with no label, shows as it is', () => {
    expect(fieldValue('assignee', 'alice_b')).toBe('alice_b')
    expect(fieldValue('vex_justification', 'some_future_reason')).toBe('some_future_reason')
    expect(fieldValue('state', 'some_future_state')).toBe('some_future_state')
  })
})
