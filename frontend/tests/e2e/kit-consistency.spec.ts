/**
 * The kit on every screen (issue 1055, G3). The lint rule and the footer test read the source; this
 * walk reads the rendered page. On the sign-in page, each listed route, the two detail pages, two
 * menus and the windows, every visible text box, dropdown, search box and window footer button
 * must wear the kit's line, corner and fill, and under the pointer both its fill and its line must
 * change (ui-design.md: hover is a wash and a border, never the border alone). A field is found by
 * its tag, not by a kit class, so a copy with its own class is read too.
 */
import type { Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the route owner
import { ROUTES } from '../../scripts/walk.mjs'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

import { BASE, DATA_ROW, expect, login, test } from './helpers'

type Kind = 'text box' | 'dropdown' | 'search box' | 'footer button'
interface Control {
  i: number
  kind: Kind
  name: string
  disabled: boolean
  primary: boolean
  problems: string[]
}

/** The places that keep a raw field on purpose, as in `raw-form-fields.spec.ts`. */
const KEPT_RAW: { selector: string; reason: string }[] = [
  { selector: 'textarea.editor', reason: 'the Inspect request body is a code panel, not a form field' },
  { selector: '.chip-input', reason: 'the chip row is the box, and this input inside it has no border of its own' },
]

/** Each file that draws a window, with how many. A new window changes this count and fails the
 *  test, so it goes into WINDOWS, or into the list of windows the walk does not open, by a decision.
 *  Four are not opened, because the CI store has no data that opens them; the lint rule and
 *  `window-footer-buttons.spec.ts` still read their source:
 *  - Edit risk-acceptance (EditDecisionDialog): needs a risk-acceptance decision
 *  - Copy this token now (TokensView): needs a newly made token
 *  - Restore snapshot (SnapshotsCard): needs a snapshot repository
 *  - Delete a retired cluster (ClusterDeleteDialog): needs a retired cluster */
const WINDOW_FILES: Record<string, number> = {
  'components/approvals/EditDecisionDialog.vue': 1,
  'components/dashboards/AddPanelDialog.vue': 1,
  'components/dashboards/DashboardDetailsDialog.vue': 1,
  'components/dashboards/ImportDashboardsDialog.vue': 1,
  'components/dashboards/RemoveDashboardDialog.vue': 1,
  'components/findings/ExportDialog.vue': 1,
  'components/findings/SaveViewDialog.vue': 1,
  'components/settings/ClusterDeleteDialog.vue': 1,
  'components/settings/SnapshotsCard.vue': 1,
  'components/system/RepairActionsCard.vue': 1,
  'components/triage/BulkTriageBar.vue': 1,
  'components/triage/RiskAcceptDialog.vue': 1,
  'views/settings/ClusterView.vue': 1,
  'views/settings/TokensView.vue': 3,
  'views/settings/UsersRolesView.vue': 4,
}

/** Read each control in `scope` (the page outside any window when null) at rest, and mark it for the
 *  pointer pass. The kit values come from the tokens of the page itself. */
async function readControls(page: Page, scope: string | null): Promise<Control[]> {
  await page.mouse.move(0, 0)
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  return page.evaluate(
    ({ scope, kept }) => {
      const probe = document.createElement('div')
      document.body.append(probe)
      const color = (token: string) => {
        probe.style.color = `var(${token})`
        return getComputedStyle(probe).color
      }
      const size = (token: string) => {
        probe.style.borderTopLeftRadius = `var(${token})`
        return getComputedStyle(probe).borderTopLeftRadius
      }
      const root = getComputedStyle(document.documentElement)
      const family = (token: string) => root.getPropertyValue(token).split(',')[0]!.trim().replace(/["']/g, '')
      const kit = {
        line: color('--line'),
        invalid: color('--coral-d'),
        card: color('--card'),
        panel: color('--panel'),
        rSm: size('--r-sm'),
        r: size('--r'),
        fonts: [family('--font-ui'), family('--font-mono')],
      }
      probe.remove()

      const base = scope ? document.querySelector(scope)! : document
      const visible = (el: Element) => {
        const r = el.getBoundingClientRect()
        return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
      }
      const found: { kind: string; el: HTMLElement; field: HTMLElement | null }[] = []
      for (const f of base.querySelectorAll<HTMLElement>('input, select, textarea')) {
        if (!visible(f) || (!scope && f.closest('.modal-backdrop'))) continue
        if (kept.some((k) => f.matches(k))) continue
        const row = f.closest<HTMLElement>('.search-box, .facet-search')
        if (row && found.some((c) => c.el === row)) continue
        const kind = row ? 'search box' : f.tagName === 'SELECT' ? 'dropdown' : 'text box'
        found.push({ kind, el: row ?? f, field: f })
      }
      for (const b of base.querySelectorAll<HTMLElement>('.modal-actions button')) {
        if (visible(b)) found.push({ kind: 'footer button', el: b, field: null })
      }

      return found.map(({ kind, el, field }, i) => {
        el.setAttribute('data-kit-walk', String(i))
        const cs = getComputedStyle(el)
        const problems: string[] = []
        const want = (what: string, got: string, ok: string[]) => {
          if (!ok.includes(got)) problems.push(`${what} ${got}, the kit has ${ok.join(' or ')}`)
        }
        want('line width', cs.borderWidth, ['1px'])
        want('line style', cs.borderStyle, ['solid'])
        const disabled = (field ?? el).matches(':disabled')
        const primary = el.classList.contains('ui-btn--primary')
        if (kind === 'footer button') {
          want('corner', cs.borderRadius, [kit.rSm])
          if (!primary && !el.classList.contains('ui-btn--ghost')) problems.push('not a ghost or primary kit button')
          if (/^(Cancel|Close|Done)$/.test(el.textContent!.trim()) && primary) problems.push('a way out is ghost, not primary')
        } else {
          want('line', cs.borderColor, kind === 'search box' ? [kit.line] : [kit.line, kit.invalid])
          want('corner', cs.borderRadius, [el.classList.contains('facet-search') ? kit.r : kit.rSm])
          want('fill', cs.backgroundColor, disabled ? [kit.panel] : [kit.card])
          want('type face', getComputedStyle(field!).fontFamily.split(',')[0]!.trim().replace(/["']/g, ''), kit.fonts)
        }
        const name = (field?.getAttribute('aria-label') || field?.id || el.textContent || field?.getAttribute('placeholder') || '').trim()
        return { i, kind: kind as Kind, name: name.slice(0, 40), disabled, primary, problems }
      })
    },
    { scope, kept: KEPT_RAW.map((k) => k.selector) },
  )
}

/** Move the pointer over each control and check that its fill and its line both change: to the kit's
 *  hover wash and line for a field, a search box and a ghost button, and to a new fill and line for a
 *  primary button. A disabled control has no hover. */
async function hoverControls(page: Page, controls: Control[]): Promise<void> {
  const style = (i: number) =>
    page.locator(`[data-kit-walk="${i}"]`).evaluate((el) => {
      const cs = getComputedStyle(el)
      return { fill: cs.backgroundColor, line: cs.borderColor }
    })
  const wash = await page.evaluate(() => {
    const probe = document.createElement('div')
    document.body.append(probe)
    probe.style.color = 'var(--control-hover-bg)'
    const fill = getComputedStyle(probe).color
    probe.style.color = 'var(--control-hover-line)'
    const line = getComputedStyle(probe).color
    probe.remove()
    return { fill, line }
  })
  for (const c of controls) {
    if (c.disabled) continue
    await page.mouse.move(0, 0)
    const rest = await style(c.i)
    await page.locator(`[data-kit-walk="${c.i}"]`).hover()
    const over = await style(c.i)
    if (c.primary) {
      if (over.fill === rest.fill) c.problems.push('fill does not change under the pointer')
      if (over.line === rest.line) c.problems.push('line does not change under the pointer')
    } else {
      if (over.fill !== wash.fill) c.problems.push(`fill under the pointer ${over.fill}, the kit has ${wash.fill}`)
      if (over.line !== wash.line) c.problems.push(`line under the pointer ${over.line}, the kit has ${wash.line}`)
    }
  }
}

/** Read and point at every control of one place; returns its problems and how many controls it read. */
async function check(page: Page, place: string, scope: string | null = null): Promise<{ problems: string[]; count: number }> {
  const controls = await readControls(page, scope)
  await hoverControls(page, controls)
  await page.evaluate(() => document.querySelectorAll('[data-kit-walk]').forEach((e) => e.removeAttribute('data-kit-walk')))
  const problems = controls.flatMap((c) => c.problems.map((p) => `${place}, ${c.kind} "${c.name}": ${p}`))
  return { problems, count: controls.length }
}

// The transitions of the kit take 120ms; with them off, a read right after the pointer moves is the end state.
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    addEventListener('DOMContentLoaded', () => {
      const s = document.createElement('style')
      s.textContent = '*, *::before, *::after { transition: none !important; }'
      document.head.append(s)
    })
  })
})

test('the sign-in boxes wear the kit', async ({ page }) => {
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  const { problems, count } = await check(page, 'sign-in')
  expect(problems).toEqual([])
  expect(count, 'the username and password boxes').toBe(2)
})

/** Places whose controls do not depend on the data in the store: the walk must read at least these. */
const AT_LEAST: Record<string, number> = {
  inspect: 1,
  'settings-scanning': 2,
  'settings-sla': 5,
  'settings-data': 6,
  'settings-cluster': 3,
  findings: 1,
  images: 1,
  approvals: 1,
}

test('every screen wears the kit', async ({ page }) => {
  test.setTimeout(360_000)
  await login(page)
  const problems: string[] = []
  const counts: Record<string, number> = {}
  const routes = [...(ROUTES as { name: string; path: string; ready: string }[]), { name: 'dashboards', path: '/dashboards', ready: '.screen' }]
  for (const route of routes) {
    await page.goto(`${BASE}${route.path}`)
    await page.waitForSelector(route.ready, { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    const r = await check(page, route.name)
    problems.push(...r.problems)
    counts[route.name] = r.count
  }
  for (const [list, ready, name] of [['/findings', '.detail-head', 'finding page'], ['/images', '.head-actions', 'image page']] as const) {
    await page.goto(`${BASE}${list}`)
    await page.locator(`${DATA_ROW} a.row-link`).first().click({ timeout: 20_000 })
    await page.waitForSelector(ready, { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    const r = await check(page, name)
    problems.push(...r.problems)
    counts[name] = r.count
  }

  await page.goto(`${BASE}/findings`)
  await page.waitForSelector(DATA_ROW, { timeout: 20_000 })
  await page.locator('button.time-range').click()
  let r = await check(page, 'time picker', '.time-menu')
  problems.push(...r.problems)
  counts['time picker'] = r.count
  await page.keyboard.press('Escape')
  await page.locator('button.add-filter').click()
  await page.locator('.filter-menu button.filter-field', { hasText: 'Search' }).first().click()
  r = await check(page, 'Add filter', '.filter-menu')
  problems.push(...r.problems)
  counts['Add filter'] = r.count

  expect(problems).toEqual([])
  for (const [place, n] of Object.entries(AT_LEAST)) expect(counts[place], `controls read on ${place}`).toBeGreaterThanOrEqual(n)
  expect(counts['time picker'], 'the time picker: a number box and a unit list').toBeGreaterThanOrEqual(2)
  expect(counts['Add filter'], 'the typed search of Add filter').toBe(1)
})

const viewerRow = (p: Page) => p.locator('tr', { hasText: 'smoke-viewer' })

/** A window, the screen it opens on, and the click that opens it. Each one only opens; the walk
 *  closes it with Escape and saves nothing. */
const WINDOWS: [string, string, (page: Page) => Promise<void>][] = [
  ['Save this view', '/findings', (p) => p.getByRole('button', { name: 'Save view' }).first().click()],
  ['Bulk triage', '/findings', (p) => p.getByRole('button', { name: 'Bulk triage' }).first().click()],
  ['Export', '/findings', (p) => p.getByRole('button', { name: 'Export CSV' }).click()],
  [
    'Risk-accept this CVE',
    '/findings',
    async (p) => {
      await p.locator(`${DATA_ROW} a.row-link`).first().click()
      await p.getByRole('button', { name: 'Risk-accept this CVE' }).click()
    },
  ],
  ['Invite a user', '/settings/users', (p) => p.getByRole('button', { name: 'Invite user' }).click()],
  // the seeded viewer: choosing a new role only opens the question, and Escape keeps the old role
  ['Change role?', '/settings/users', (p) => p.getByRole('combobox', { name: 'Role for smoke-viewer' }).selectOption('triager')],
  ['Disable this user?', '/settings/users', (p) => viewerRow(p).getByRole('button', { name: 'Disable', exact: true }).click()],
  ['Reset smoke-viewer\'s password', '/settings/users', (p) => viewerRow(p).getByRole('button', { name: 'Reset password' }).click()],
  ['Mint a push token', '/settings/tokens', (p) => p.getByRole('button', { name: 'Mint token' }).click()],
  ['Rotate this token?', '/settings/tokens', (p) => p.getByRole('button', { name: 'Rotate', exact: true }).first().click()],
  ['Revoke this token?', '/settings/tokens', (p) => p.getByRole('button', { name: 'Revoke', exact: true }).first().click()],
  ['Retire', '/settings/cluster', (p) => p.getByRole('button', { name: 'Retire cluster' }).click()],
  [
    'Run the lifecycle sweep?',
    '/inspect',
    (p) => p.locator('tr', { hasText: 'Lifecycle sweep' }).getByRole('button', { name: 'Run', exact: true }).click(),
  ],
  ['New dashboard', '/dashboards', (p) => p.getByRole('button', { name: 'New dashboard' }).first().click()],
  ['Import dashboards', '/dashboards', (p) => p.getByRole('button', { name: 'Import', exact: true }).first().click()],
]

async function checkWindow(page: Page, title: string, path: string, open: (page: Page) => Promise<void>) {
  await page.goto(`${BASE}${path}`)
  await page.waitForLoadState('networkidle')
  await open(page)
  const dialog = page.getByRole('dialog')
  await expect(dialog, `the window "${title}" opens`).toBeVisible({ timeout: 10_000 })
  await expect(dialog.locator('.modal-head h3')).toContainText(title)
  const r = await check(page, `window "${title}"`, '.modal')
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
  return r
}

test('each window wears the kit', async ({ page }) => {
  test.setTimeout(360_000)
  await login(page)
  const problems: string[] = []
  for (const [title, path, open] of WINDOWS) {
    const r = await checkWindow(page, title, path, open)
    problems.push(...r.problems)
    expect(r.count, `controls read in "${title}"`).toBeGreaterThanOrEqual(1)
  }

  // the three windows of a dashboard in edit mode, on a dashboard the walk makes and removes
  const made = await page.request.post(`${BASE}/api/v1/dashboards`, {
    data: { name: `e2e kit ${Date.now()}`, description: '', scanner: 'all', sharing: 'private', roles: [], panels: [] },
  })
  expect(made.status()).toBe(201)
  const { dashboard_id: id } = await made.json()
  try {
    const edit = `/dashboards/${id}?edit=1`
    for (const [title, button] of [['Add a panel', 'Add panel'], ['Name and sharing', 'Name and sharing'], ['Remove', 'Remove']]) {
      const r = await checkWindow(page, title!, edit, (p) => p.getByRole('button', { name: button, exact: true }).first().click())
      problems.push(...r.problems)
      expect(r.count, `controls read in "${title}"`).toBeGreaterThanOrEqual(1)
    }
  } finally {
    const left = await page.request.get(`${BASE}/api/v1/dashboards/${id}`)
    if (left.ok()) {
      const { revision } = await left.json()
      await page.request.delete(`${BASE}/api/v1/dashboards/${id}?revision=${revision}`)
    }
  }
  expect(problems).toEqual([])
})

test('the walk knows every window', () => {
  const src = fileURLToPath(new URL('../../src', import.meta.url))
  const files = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? files(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
    )
  const found: Record<string, number> = {}
  for (const f of files(src)) {
    const name = relative(src, f)
    if (name.startsWith('components/ui/')) continue
    const n = readFileSync(f, 'utf8').split('<ModalShell').length - 1
    if (n > 0) found[name] = n
  }
  expect(found, 'a new window goes into WINDOWS or the list of windows not opened').toEqual(WINDOW_FILES)
})
