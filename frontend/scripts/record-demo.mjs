/**
 * README demo recorder (issue 469). Standalone on purpose: it must NOT touch
 * playwright.config.ts, which is the CI smoke suite's config, since video recording there
 * would slow every CI run for no benefit.
 *
 * The walk follows the product's own narrative: the fleet, then one cluster, then the
 * findings in it, then a single CVE and its per-finding audit trail, then the approval
 * queue and the fleet-wide journal.
 *
 * Login happens in a throwaway context and is replayed via storageState, so the sign-in
 * screen is never on camera and the recording opens inside the product.
 *
 * Chromium's video capture draws no pointer, hence the synthetic cursor injected below.
 *
 *   JAVV_CLUSTER=<cluster id> JAVV_PASS=... node scripts/record-demo.mjs   # from frontend/
 *
 * Seed some triage first (a few acknowledged findings, risk acceptances, a not-affected
 * decision), or the CVE page, the approval list and the audit log are empty on camera.
 *
 * Encode the .webm it leaves in tmp/ with development/scripts/make-demo-gif.sh.
 */
import { chromium } from '@playwright/test'

const BASE = process.env.JAVV_BASE ?? 'http://localhost:5173'
const USER = process.env.JAVV_USER ?? 'admin'
const PASS = process.env.JAVV_PASS ?? ''
// no default: a cluster id belongs to one store, and a stale one fails the walk on camera
const CLUSTER = process.env.JAVV_CLUSTER ?? ''
if (!CLUSTER) {
  console.error('set JAVV_CLUSTER to the cluster id the walk is about')
  process.exit(1)
}
const OUT_DIR = process.env.JAVV_DEMO_DIR ?? '../tmp/demo'

const VIEWPORT = { width: 1280, height: 800 }

/** a visible pointer + click pulse, re-injected on every navigation */
const CURSOR = `
  (() => {
    if (window.__demoCursor) return
    window.__demoCursor = true
    const add = () => {
      const dot = document.createElement('div')
      dot.id = '__demo-cursor'
      dot.style.cssText = [
        'position:fixed', 'z-index:2147483647', 'left:0', 'top:0',
        'width:18px', 'height:18px', 'margin:-9px 0 0 -9px', 'border-radius:50%',
        'background:rgba(236,126,84,.55)', 'border:2px solid #EC7E54',
        'box-shadow:0 0 0 3px rgba(236,126,84,.18)', 'pointer-events:none',
        'transition:transform .06s linear', 'will-change:transform',
      ].join(';')
      document.body.appendChild(dot)
      document.addEventListener('mousemove', (e) => {
        dot.style.transform = 'translate(' + e.clientX + 'px,' + e.clientY + 'px)'
      }, { passive: true })
      document.addEventListener('mousedown', () => {
        dot.animate(
          [{ boxShadow: '0 0 0 3px rgba(236,126,84,.18)' },
           { boxShadow: '0 0 0 14px rgba(236,126,84,0)' }],
          { duration: 420, easing: 'ease-out' },
        )
      }, { passive: true })
    }
    document.readyState === 'loading'
      ? document.addEventListener('DOMContentLoaded', add)
      : add()
  })()
`

/** the dev server's devtools button is not part of the product */
const HIDE_DEVTOOLS = `
  document.addEventListener('DOMContentLoaded', () => {
    const style = document.createElement('style')
    style.textContent = '#__vue-devtools-container__{display:none!important}'
    document.head.appendChild(style)
  })
`

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function glide(page, locator) {
  const box = await locator.first().boundingBox()
  if (!box) return false
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 22 })
  return true
}

async function click(page, locator, { settle = 700 } = {}) {
  if (!(await glide(page, locator))) return false
  await sleep(200)
  await locator.first().click()
  await sleep(settle)
  return true
}

/** gentle scroll so a static table has motion while it is on screen */
async function drift(page, px = 260, ms = 900) {
  const steps = 14
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, px / steps)
    await sleep(ms / steps)
  }
}

async function beat(name, fn) {
  try {
    await fn()
    console.log(`  ok   ${name}`)
  } catch (err) {
    console.log(`  SKIP ${name}: ${err.message.split('\n')[0]}`)
  }
}

const browser = await chromium.launch()

// --- sign in OFF CAMERA, keep only the session ---------------------------------
const auth = await browser.newContext({ viewport: VIEWPORT })
const authPage = await auth.newPage()
await authPage.goto(`${BASE}/login`)
await authPage.locator('input[type="text"], input[autocomplete*="username" i]').first().fill(USER)
await authPage.locator('input[type="password"]').first().fill(PASS)
await authPage.locator('input[type="password"]').first().press('Enter')
await authPage.waitForURL(/overview|findings|clusters/, { timeout: 20000 })
const storageState = await auth.storageState()
await auth.close()
console.log('  ok   signed in (off camera)')

// --- the recorded context ------------------------------------------------------
const context = await browser.newContext({
  viewport: VIEWPORT,
  deviceScaleFactor: 1,
  storageState,
  recordVideo: { dir: OUT_DIR, size: VIEWPORT },
})
await context.addInitScript(CURSOR)
await context.addInitScript(HIDE_DEVTOOLS)
const page = await context.newPage()

// Exactly ONE full page load, at the very start. Every later move is a click, so the router
// swaps views client-side: a page.goto() here would blank the frame to the empty background
// for a second on each hop, which is most of what made an early cut look like a slideshow.
await beat('all clusters', async () => {
  await page.goto(`${BASE}/clusters?cluster=${CLUSTER}`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await sleep(1500)
})

// 2. drill into a cluster — the one the rest of the walk is about, so the numbers line up
await beat('pick a cluster', async () => {
  // the row shows the cluster id, so this names the same cluster as the address above
  const row = page.locator('table tbody tr').filter({ hasText: CLUSTER }).first()
  await row.waitFor({ timeout: 8000 })
  await click(page, row, { settle: 1400 })
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
})

const nav = (label) => page.getByRole('link', { name: label })

// 3. its findings, with a little motion
await beat('findings', async () => {
  await click(page, nav(/^Findings$/), { settle: 400 })
  await page.waitForSelector('table tbody tr', { timeout: 15000 })
  await sleep(1000)
  await drift(page, 170, 700) // enough to show the table moves, not enough to lose the topbar
  await sleep(400)
})

// 4. one CVE, and its own audit trail (the differentiator)
await beat('cve detail + per-finding audit', async () => {
  await click(page, page.locator('table tbody tr').first(), { settle: 1500 })
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await sleep(800)
  await drift(page, 420, 900) // down to the per-finding activity/history
  await sleep(1700)
})

// 5. the approval queue
await beat('approval list', async () => {
  await click(page, nav(/^Approval list$/), { settle: 400 })
  await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {})
  await sleep(1600)
})

// 6. the fleet-wide journal
await beat('audit log', async () => {
  await click(page, nav(/^Audit log$/), { settle: 400 })
  await page.waitForSelector('table tbody tr', { timeout: 12000 })
  await sleep(2000)
})

const videoPath = await page.video().path()
await context.close()
await browser.close()
console.log(`\nvideo: ${videoPath}`)
