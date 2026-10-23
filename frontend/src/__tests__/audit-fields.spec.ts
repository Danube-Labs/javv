/**
 * The audit rail per role (issue 892, ruling 8): the server leaves the account events (entity
 * `user` and `token`) out for a user without can_manage_users, so the rail does not offer those
 * values, nor their actions, which could only ever count 0 there.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  ACCOUNT_ACTIONS,
  AUDIT_ACTIONS,
  AUDIT_ENTITY_TYPES,
  AUDIT_FIELDS,
  AUDIT_LIST_CAP,
  auditFields,
} from '@/audit/fields.config'

const values = (fields: ReturnType<typeof auditFields>, key: string): readonly string[] => {
  const field = fields.find((f) => f.key === key)!
  return field.type === 'terms' ? (field.values ?? []) : []
}

describe('auditFields', () => {
  it('without can_manage_users: no user or token entity, and no account action', () => {
    const fields = auditFields(false)
    expect(values(fields, 'entity')).not.toContain('user')
    expect(values(fields, 'entity')).not.toContain('token')
    for (const action of ACCOUNT_ACTIONS) expect(values(fields, 'action')).not.toContain(action)
    expect(values(fields, 'entity')).toContain('finding') // the rest stays
    expect(values(fields, 'action')).toContain('risk_accept')
    expect(values(fields, 'action')).toContain('job_trigger')
  })

  it('with can_manage_users: every value, the same fields as AUDIT_FIELDS', () => {
    expect(auditFields(true)).toEqual(AUDIT_FIELDS)
  })

  it('the account actions are exactly the actions of the user and token rows', () => {
    expect([...ACCOUNT_ACTIONS].sort()).toEqual(
      ['login', 'logout', 'pwd_change', 'pwd_reset', 'role_change', 'token_mint', 'token_revoke',
        'user_create', 'user_disable', 'user_enable'].sort(),
    )
  })
})

describe('AUDIT_FIELDS (issue 952)', () => {
  it('Entity, Action and User take several values, for every role', () => {
    for (const fields of [auditFields(true), auditFields(false)])
      expect(fields.map((f) => [f.key, 'multi' in f && f.multi === true])).toEqual([
        ['entity', true],
        ['action', true],
        ['actor', true],
      ])
  })
})

describe('AUDIT_LIST_CAP (issue 983)', () => {
  it('equals the size of the backend Entity and Action counts', () => {
    const audit = readFileSync(resolve(process.cwd(), '../backend/src/backend/query/audit.py'), 'utf8')
    expect(audit.match(/^_AUDIT_LIST_TERMS_SIZE = (\d+)$/m)?.[1]).toBe(String(AUDIT_LIST_CAP))
  })

  it('is larger than the Entity and Action lists, so each value of them gets a count', () => {
    expect(AUDIT_LIST_CAP).toBeGreaterThan(AUDIT_ACTIONS.length)
    expect(AUDIT_LIST_CAP).toBeGreaterThan(AUDIT_ENTITY_TYPES.length)
  })

  it('Entity and Action carry it; User keeps the shared cap of a list with no fixed values', () => {
    expect(AUDIT_FIELDS.map((f) => [f.key, f.type === 'terms' ? f.facetCap : undefined])).toEqual([
      ['entity', AUDIT_LIST_CAP],
      ['action', AUDIT_LIST_CAP],
      ['actor', undefined],
    ])
  })
})
