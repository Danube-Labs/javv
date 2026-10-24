/**
 * The Roles card (issue 990, option A): one table, a row for each permission the server lists and a
 * column for each role. Words, not ids: a row shows the permission's name and what it allows. A
 * permission a role holds that the server does not list still gets a row, named by its id.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import RolesCard, { type PermissionRow, type RoleRow } from '@/components/settings/RolesCard.vue'
import UsersRolesView from '@/views/settings/UsersRolesView.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listUsersApiV1AdminUsersGet: vi.fn<() => Promise<unknown>>(() =>
      Promise.resolve({
        data: {
          users: [
            {
              username: 'lead',
              role: 'security_lead',
              capabilities: [],
              must_change: false,
              disabled: false,
              auth_source: 'local',
              created_at: null,
            },
          ],
          total: 1,
        },
        response: { ok: true, status: 200 },
      }),
    ),
    listRolesApiV1AdminRolesGet: vi.fn<() => Promise<unknown>>(() =>
      Promise.resolve({ data: { roles: ROLES, permissions: PERMISSIONS }, response: { ok: true, status: 200 } }),
    ),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

const PERMISSIONS: PermissionRow[] = [
  { id: 'can_triage', name: 'Triage findings', description: 'Change the state of a finding.' },
  { id: 'can_accept_audit_final', name: 'Accept a risk', description: 'Accept a risk.' },
  { id: 'can_manage_users', name: 'Manage users', description: 'Make users.' },
]
// the server's order: alphabetical by role id
const ROLES: RoleRow[] = [
  { role: 'admin', capabilities: ['*'] },
  { role: 'security_lead', capabilities: ['can_triage', 'can_accept_audit_final'] },
  { role: 'triager', capabilities: ['can_triage'] },
  { role: 'viewer', capabilities: [] },
]

function mountCard(roles = ROLES, permissions = PERMISSIONS, ready = true) {
  return mount(RolesCard, { props: { roles, permissions, ready } })
}

/** the marks of one row, as "role: yes|no" in column order */
function marks(w: ReturnType<typeof mountCard>, name: string): string[] {
  const row = w.findAll('tbody tr').find((tr) => tr.find('.perm-name').text() === name)
  if (!row) throw new Error(`no row named ${name}`)
  return row.findAll('[role="img"]').map((m) => m.attributes('aria-label') ?? '')
}

describe('RolesCard (issue 990)', () => {
  it('has a column for each role, fewest permissions first and admin last', () => {
    const heads = mountCard()
      .findAll('thead th')
      .map((th) => th.text())
    expect(heads).toEqual(['Permission', 'viewer', 'triager', 'security_lead', 'admin'])
  })

  it('has a row for each permission, with its name and what it allows, and no id', () => {
    const w = mountCard()
    const rows = w.findAll('tbody tr')
    expect(rows.map((r) => r.find('.perm-name').text())).toEqual(['Triage findings', 'Accept a risk', 'Manage users'])
    expect(rows[0]!.find('.perm-does').text()).toBe('Change the state of a finding.')
    expect(w.text()).not.toContain('can_')
  })

  it('marks what each role holds, and admin holds every permission', () => {
    const w = mountCard()
    expect(marks(w, 'Triage findings')).toEqual(['viewer: no', 'triager: yes', 'security_lead: yes', 'admin: yes'])
    expect(marks(w, 'Accept a risk')).toEqual(['viewer: no', 'triager: no', 'security_lead: yes', 'admin: yes'])
    expect(marks(w, 'Manage users')).toEqual(['viewer: no', 'triager: no', 'security_lead: no', 'admin: yes'])
  })

  it('gives a permission that the server does not list a row named by its id', () => {
    const roles = [...ROLES, { role: 'auditor', capabilities: ['can_export'] }]
    const w = mountCard(roles)
    expect(marks(w, 'can_export')).toEqual([
      'viewer: no',
      'triager: no',
      'auditor: yes',
      'security_lead: no',
      'admin: yes',
    ])
    const row = w.findAll('tbody tr').at(-1)!
    expect(row.find('.perm-does').exists()).toBe(false)
  })

  it('shows no table until the roles are read', () => {
    const w = mountCard(ROLES, PERMISSIONS, false)
    expect(w.find('table').exists()).toBe(false)
    expect(w.text()).toContain('To remove a person')
  })
})

describe('Settings > Users and roles (issue 990)', () => {
  async function mountView() {
    setActivePinia(createPinia())
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
    })
    const w = mount(UsersRolesView, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('gives the Roles card the permissions that the server sends', async () => {
    const card = (await mountView()).findComponent(RolesCard)
    expect(card.props('permissions')).toEqual(PERMISSIONS)
    expect(card.findAll('tbody tr')).toHaveLength(PERMISSIONS.length)
  })

  it('shows the Source of a user in the UI font, as a plain word', async () => {
    const w = await mountView()
    const cell = w.findAll('td').find((td) => td.text() === 'local')
    expect(cell).toBeDefined()
    expect(cell!.classes()).not.toContain('mono-cell')
  })
})
