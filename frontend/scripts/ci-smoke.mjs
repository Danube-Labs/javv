/**
 * The CI route smoke (#383, testing.md §4): a built frontend + a fixture-seeded backend,
 * walked headless at the desktop viewport through the shared matrix (scripts/walk.mjs).
 * Desktop-only BY RULING (#387): the app has no phone layout yet — phone runs live in the
 * authoring rig (visual-capture.mjs) as screenshots, and start gating here once a
 * responsive pass exists. Gating asserts — any of these fails the job:
 *   - every route renders its data-ready selector (not just the shell);
 *   - zero console.error / pageerror anywhere in the walk;
 *   - layout sanity per route (no horizontal scroll, no off-viewport bleed, no sibling overlap);
 *   - server-side-everything: the findings grid got its rows from a backend query;
 *   - with --core-loop (CI sets it; keep local runs read-only): a triage action persists
 *     across a reload, then is reverted (the store is left as found);
 *   - one click does what it says (issue 666): every sidebar item lands on its first click, a
 *     fleet row of the cluster that is NOT selected opens that cluster's Overview (the seed
 *     carries two clusters), and with --core-loop a saved view with a 7-day window opens
 *     Findings (the view is created for the check and deleted after it).
 * A failed run saves a Playwright trace to development/e2e/logs/ci-smoke-trace.zip, which the CI
 * job uploads with the backend log (issue 786). A clean run saves nothing.
 *
 *   JAVV_BASE=http://localhost:4173 JAVV_USER=… JAVV_PASS=… node scripts/ci-smoke.mjs [--core-loop]
 *
 * Deliberately shallow: dialogs, forced states and screenshots live in the authoring rig
 * (visual-capture.mjs), which imports the same walk — keep deep interactions out of the gate.
 */
import { rm } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

import { ROUTES, VIEWPORTS, collectPageIssues, walkRoutes, clickDetail, login } from './walk.mjs'

const BASE = process.env.JAVV_BASE ?? 'http://localhost:4173'
const USER = process.env.JAVV_USER
const PASS = process.env.JAVV_PASS
const CORE_LOOP = process.argv.includes('--core-loop')
// a failed run leaves its recording (the DOM at every step, console, network) where CI uploads it
// (issue 786). No screen frames: they cost about 3 s a run, and the DOM alone showed that failure.
const TRACE = fileURLToPath(new URL('../../development/e2e/logs/ci-smoke-trace.zip', import.meta.url))
if (!USER || !PASS) {
  console.error('set JAVV_USER and JAVV_PASS')
  process.exit(2)
}

async function coreLoop(page, issues) {
  // open the first finding, acknowledge it, prove it survives a reload, put it back.
  // Every step is caught and named — a failed write must report WHAT failed, and the
  // revert only runs when the write actually landed (a no-op draft disables Save).
  const patches = []
  page.on('response', (r) => {
    if (r.request().method() === 'PATCH' && r.url().includes('/api/v1/findings')) {
      patches.push(`${r.status()} ${r.url()}`)
    }
  })
  const ok = await clickDetail(page, BASE, '/findings', '.detail-head', 'finding-core-loop', issues)
  if (!ok) return
  const url = page.url()
  const ack = page.locator('.state-opt', { hasText: 'Acknowledge' })
  const open = page.locator('.state-opt', { hasText: 'Open' })
  const save = page.locator('button', { hasText: 'Save to audit trail' })
  if (!(await ack.count()) || (await ack.isDisabled())) {
    issues.push('[core-loop] triage panel absent or not actionable for this principal')
    return
  }
  const isOn = async (loc) => ((await loc.getAttribute('class')) ?? '').includes('state-opt-on')
  const step = async (name, fn) => {
    try {
      await fn()
      return true
    } catch (e) {
      issues.push(`[core-loop] ${name}: ${e.message.split('\n')[0]} (PATCHes so far: ${patches.join(' · ') || 'none'})`)
      return false
    }
  }

  const wasAcked = await isOn(ack)
  if (!(await step('select state', () => (wasAcked ? open : ack).click({ timeout: 10_000 })))) return
  if (!(await step('save', () => save.click({ timeout: 10_000 })))) return
  await page.waitForLoadState('networkidle')
  // the reload re-READS the findings index, which refreshes ~1s behind the write (the live
  // UI never sees this — it applies the PATCH response client-side). Poll, don't assert once.
  let persisted = false
  for (let attempt = 0; attempt < 4 && !persisted; attempt++) {
    if (attempt > 0) await page.waitForTimeout(1_000)
    await page.goto(url)
    await page.waitForSelector('.detail-head', { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    persisted = (await isOn(ack)) !== wasAcked
  }
  if (!persisted) {
    issues.push(`[core-loop] triage action did not persist across reload (PATCHes: ${patches.join(' · ') || 'none'})`)
    return // nothing landed — nothing to revert
  }
  // revert — leave the store as found
  await step('revert select', () => (wasAcked ? ack : open).click({ timeout: 10_000 }))
  await step('revert save', () => save.click({ timeout: 10_000 }))
  await page.waitForLoadState('networkidle')
}

/** Navigations that change no global state first, then the two that change it on the way. */
async function oneClick(page, issues) {
  const pathIs = (want, extra = () => true) => (url) => url.pathname === want && extra(url)
  const step = async (name, fn) => {
    try {
      await fn()
    } catch (e) {
      issues.push(`[one-click] ${name}: ${e.message.split('\n')[0]} (at ${page.url().replace(BASE, '')})`)
    }
  }

  await page.goto(`${BASE}/overview`)
  await page.waitForSelector(ROUTES.find((r) => r.name === 'overview').ready, { timeout: 15_000 })
  const hrefs = await page.locator('.side-item').evaluateAll((els) => els.map((e) => e.getAttribute('href')))
  for (const href of hrefs) {
    // a link may carry its own filter (the Audit log opens without sign-ins): the path must
    // match, and every parameter the link names must arrive with it
    const link = new URL(href, BASE)
    // /settings is a redirect to its first section by design
    const want = link.pathname === '/settings' ? '/settings/scan-scope' : link.pathname
    const carries = (url) => [...link.searchParams].every(([k, v]) => url.searchParams.get(k) === v)
    await step(`sidebar ${href}`, async () => {
      await page.locator(`.side-item[href="${href}"]`).click()
      await page.waitForURL(pathIs(want, carries), { timeout: 10_000 })
    })
  }

  await step('fleet row of the cluster that is not selected', async () => {
    await page.goto(`${BASE}/clusters`)
    await page.waitForSelector('.fleet-card tbody tr')
    await page.waitForURL((url) => url.searchParams.has('cluster'))
    const selected = new URL(page.url()).searchParams.get('cluster')
    // an unnamed cluster shows its id as the name and no separate id line
    const ids = await page
      .locator('.fleet-card tbody tr')
      .evaluateAll((rows) => rows.map((r) => (r.querySelector('.cl-id') ?? r.querySelector('.cl-name'))?.textContent?.trim()))
    const other = ids.findIndex((id) => id && id !== selected)
    if (other < 0) throw new Error(`needs two clusters, the fleet lists ${ids.length}`)
    await page.locator('.fleet-card tbody tr').nth(other).locator('.cl-name').click()
    await page.waitForURL(pathIs('/overview', (url) => url.searchParams.get('cluster') === ids[other]), {
      timeout: 10_000,
    })
  })

  // an address no route matches used to render an empty body (issue 674)
  await step('unknown address shows the not-found page inside the shell', async () => {
    await page.goto(`${BASE}/no-such-page`)
    await page.getByRole('heading', { name: 'Page not found' }).waitFor({ timeout: 10_000 })
    await page.locator('.side-item').first().waitFor({ timeout: 5_000 })
    await page.getByRole('button', { name: 'Back to Overview' }).click()
    await page.waitForURL(pathIs('/overview'), { timeout: 10_000 })
  })

  if (!CORE_LOOP) return
  await step('saved view with a 7-day window', async () => {
    const created = await page.evaluate(async () => {
      const r = await fetch('/api/v1/views', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ name: 'smoke one-click 7d', workbench: { window_days: 7 } }),
      })
      return { status: r.status, id: r.ok ? (await r.json()).view_id : null }
    })
    if (!created.id) throw new Error(`could not create the view (${created.status})`)
    try {
      await page.goto(`${BASE}/views`)
      const card = page.locator('.view-card', { hasText: 'smoke one-click 7d' })
      await card.getByRole('link', { name: 'smoke one-click 7d' }).click()
      await page.waitForURL(pathIs('/findings', (url) => url.searchParams.get('win') === '7'), { timeout: 10_000 })
    } finally {
      await page.evaluate((id) => fetch(`/api/v1/views/${id}`, { method: 'DELETE' }), created.id)
    }
  })
}

async function main() {
  await rm(TRACE, { force: true }) // a trace in logs/ is always the last run's
  const browser = await chromium.launch({ headless: true })
  const issues = []

  const context = await browser.newContext({ viewport: VIEWPORTS.desktop })
  await context.tracing.start({ screenshots: false, snapshots: true })
  const page = await context.newPage()
  let failed = true
  try {
    await walk(page, issues)
    failed = issues.length > 0
  } finally {
    // a trace that cannot be written must not hide the smoke's own result
    const saved = await context.tracing.stop(failed ? { path: TRACE } : {}).then(
      () => failed,
      (e) => {
        if (failed) console.error(`trace not saved: ${e.message}`)
        return false
      },
    )
    if (saved) console.error(`trace of the failed run: ${TRACE}`)
    await browser.close()
  }
  if (issues.length) {
    console.error(`SMOKE FAILED — ${issues.length} issue(s):\n  ${issues.join('\n  ')}`)
    process.exit(1)
  }
  console.log('smoke: all routes clean (desktop)')
}

async function walk(page, issues) {
  // server-side-everything: rows must come from a backend search, not client math
  let findingsQueried = false
  page.on('request', (r) => {
    if (r.url().includes('/api/v1/findings')) findingsQueried = true
  })

  await login(page, BASE, USER, PASS).catch((e) => issues.push(`[login] ${e.message}`))
  // errors collected only post-login: the boot-time /auth/me session probe 401s by design
  // on a fresh browser, and the browser logs every non-2xx as console.error
  collectPageIssues(page, issues)
  await walkRoutes(page, BASE, issues)
  if (!findingsQueried) issues.push('[desktop] findings grid rendered without a backend query')

  await clickDetail(page, BASE, '/findings', '.detail-head', 'finding-detail', issues)
  await clickDetail(page, BASE, '/images', '.back-btn', 'image-detail', issues)
  if (CORE_LOOP) await coreLoop(page, issues)
  // after the core loop: the fleet click moves this browser's selection off the golden cluster
  await oneClick(page, issues)
}

main().catch((e) => {
  console.error('FAILED:', e.message)
  process.exit(1)
})
