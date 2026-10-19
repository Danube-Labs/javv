// The recorder of the triage videos (issue 699): signs in as `lead` off camera (the password
// comes from a 600 file and is never printed), opens the app at 2x, and takes full-page
// screenshots with the boxes of named controls, in page pixels. The engine animates over them:
// a screen video from Playwright or CDP ignores deviceScaleFactor, so it is never sharp.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
// the frontend's Playwright and its browser, not a second copy
import { chromium } from '../../../frontend/node_modules/@playwright/test/index.mjs'

const HERE = path.dirname(fileURLToPath(import.meta.url))
export const BASE = process.env.JAVV_VIDEO_APP_URL ?? 'http://127.0.0.1:8091'
const SECRETS = process.env.JAVV_VIDEO_SECRETS ?? path.join(HERE, '..', 'sec')
const PUBLIC = path.join(HERE, '..', 'public')
/** what one walk leaves for the next (the CVE it changed), outside the published files */
export const STATE = path.join(HERE, '..', 'out', 'state')
const DEFAULT_VIEW = { width: 1440, height: 810 }

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export async function record(dir, walk, { view: VIEW = DEFAULT_VIEW } = {}) {
  const out = `${PUBLIC}/${dir}`
  fs.mkdirSync(out, { recursive: true })
  for (const f of fs.readdirSync(out)) if (f.endsWith('.png') || f === 'shots.json') fs.unlinkSync(`${out}/${f}`)

  const browser = await chromium.launch()
  const auth = await browser.newContext({ viewport: VIEW })
  const ap = await auth.newPage()
  await ap.goto(`${BASE}/login`)
  await ap.locator('input[type="text"], input[autocomplete*="username" i]').first().fill('lead')
  await ap.locator('input[type="password"]').first().fill(fs.readFileSync(path.join(SECRETS, 'lead_pass'), 'utf8'))
  await ap.locator('input[type="password"]').first().press('Enter')
  await ap.waitForURL(/overview|findings|clusters/, { timeout: 20000 })
  const storageState = await auth.storageState()
  await auth.close()

  const ctx = await browser.newContext({ viewport: VIEW, deviceScaleFactor: 2, storageState })
  const page = await ctx.newPage()
  // motion settles before each shot: no half-faded block in a still
  await page.emulateMedia({ reducedMotion: 'reduce' })

  const shots = []
  async function box(locator) {
    // a row of a table that scrolls sideways is wider than the part on screen: keep only the
    // width that its clipping parents show, so the spotlight stops at the table's edge
    const b = await locator.first().evaluate((el) => {
      const r = el.getBoundingClientRect()
      let left = r.left
      let right = r.right
      for (let p = el.parentElement; p; p = p.parentElement) {
        if (getComputedStyle(p).overflowX === 'visible') continue
        const c = p.getBoundingClientRect()
        left = Math.max(left, c.left)
        right = Math.min(right, c.right)
      }
      return { x: left, y: r.top + window.scrollY, w: right - left, h: r.height }
    })
    if (!(b.w > 0 && b.h > 0)) throw new Error('no box for a locator')
    return b
  }
  /** a full-page screenshot and the boxes of the named controls */
  async function shot(name, targets = {}) {
    await sleep(250)
    const boxes = {}
    for (const [k, loc] of Object.entries(targets)) boxes[k] = await box(loc)
    await page.screenshot({ path: `${out}/${name}.png`, fullPage: true })
    const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }))
    shots.push({ name, file: `${name}.png`, size, boxes })
    console.log('shot', name)
  }
  /** the same screen with the pointer over the control: the engine shows it before the press */
  async function hoverShot(name, locator) {
    await locator.first().hover()
    await shot(`${name}-hover`)
  }
  async function settle() {
    await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
    await page.mouse.move(5, 5)
    await sleep(300)
  }
  const stateRow = () => page.locator('tr').filter({ has: page.locator('th, td', { hasText: /^\s*state\s*$/i }) }).first()
  /** an Open finding that both scanners report as Open; looking is read-only */
  async function pickBothOpen(skip = 0, avoidCves = []) {
    const openRows = page.locator('table tbody tr').filter({ hasText: /Open/ })
    let found = 0
    for (let i = 0; i < 40; i++) {
      const text = await openRows.nth(i).innerText()
      if (avoidCves.some((c) => text.includes(c))) continue
      await openRows.nth(i).click()
      await page.waitForSelector('aside.triage', { timeout: 15000 })
      await settle()
      const both = (await stateRow().getByText(/^Open$/).count()) === 2
      await page.goBack()
      await page.waitForSelector('table tbody tr', { timeout: 20000 })
      await settle()
      if (both && found++ === skip) return { row: openRows.nth(i), cve: text.match(/CVE-\d+-\d+/)?.[0] }
    }
    throw new Error('no finding with both scanners Open')
  }

  try {
    await walk({ page, shot, hoverShot, box, settle, stateRow, pickBothOpen })
  } finally {
    fs.writeFileSync(`${out}/shots.json`, JSON.stringify({ view: VIEW, scale: 2, shots }, null, 2))
    await browser.close()
  }
}
