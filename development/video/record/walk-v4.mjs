// Video 4, many findings at once: filter Low, one bulk change to Acknowledged with a note, then a
// filter that a bulk change cannot follow, which blocks it.
import { BASE, record, sleep } from './common.mjs'

const NOTE = 'Low risk. We review these in the next release.'

await record('v4', async ({ page, shot, hoverShot, settle }) => {
  await page.goto(`${BASE}/findings?cluster=prod-eu-1`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const facet = (title) => page.locator('.facet').filter({ has: page.locator('.facet-title', { hasText: new RegExp(`^${title}$`, 'i') }) }).first()
  const sevFacet = facet('severity')
  const low = sevFacet.locator('.facet-row').filter({ has: page.locator('.facet-text', { hasText: /\blow\b/i }) }).first()
  const bulkBtn = page.getByRole('button', { name: /Bulk triage/ })
  const head = page.locator('.head-card').first()
  await shot('findings', { sevFacet, low, head })
  await hoverShot('findings', low)

  await low.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  await shot('low', { head, bulkBtn, table: page.locator('table').first(), sevFacet })
  await hoverShot('low', bulkBtn)

  await bulkBtn.click()
  const dialog = page.getByRole('dialog').first()
  await dialog.waitFor({ timeout: 10000 })
  await settle()
  const filters = dialog.locator('.lens-row')
  const ack = dialog.getByRole('radio', { name: /Acknowledge/ })
  const notes = dialog.locator('#bulk-notes')
  const apply = dialog.getByRole('button', { name: /Apply to matching findings/ })
  const targets = () => ({ dialog, filters, ack, notes, apply, states: dialog.locator('.state-grid') })
  await shot('bulk', targets())
  await hoverShot('bulk', ack)

  await ack.click()
  await settle()
  await shot('bulk-ack', targets())
  await hoverShot('bulk-ack', notes)

  await notes.click()
  const words = NOTE.split(' ')
  for (let i = 1; i <= words.length; i++) {
    await notes.fill(words.slice(0, i).join(' '))
    await page.mouse.move(5, 5)
    await sleep(60)
    await shot(`type-${i}`, i === words.length ? targets() : {})
  }
  await hoverShot(`type-${words.length}`, apply)

  await apply.click()
  await dialog.locator('.bulk-done').waitFor({ timeout: 20000 })
  await settle()
  // the footer button, not the corner one (both are named Close)
  const close = dialog.locator('button:not(.modal-close)', { hasText: /^Close$/ })
  await shot('done', { dialog, done: dialog.locator('.bulk-done'), close })
  await hoverShot('done', close)

  await close.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  await page.waitForTimeout(800)
  const scanFacet = facet('scanner')
  const trivy = scanFacet.locator('.facet-row').filter({ has: page.locator('.facet-text', { hasText: /trivy/i }) }).first()
  const stateFacet = facet('state')
  await shot('after', { table: page.locator('table').first(), stateFacet, scanFacet, trivy, head })
  await hoverShot('after', trivy)

  await trivy.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  await shot('trivy', { bulkBtn, scanFacet })
  await hoverShot('trivy', bulkBtn)

  await bulkBtn.click()
  await page.getByRole('dialog').first().waitFor({ timeout: 10000 })
  await settle()
  await shot('blocked', { dialog: page.getByRole('dialog').first(), blocked: page.locator('.bulk-blocked').first() })
})
