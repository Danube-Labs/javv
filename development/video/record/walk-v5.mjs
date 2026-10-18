// Video 5, when the scanner stops: the silent-scanner banner, Scanner status, and a Stale finding.
// Run after the staleness sweep marked staging-eu Stale. Read-only.
import { BASE, record } from './common.mjs'

await record('v5', async ({ page, shot, hoverShot, settle, stateRow }) => {
  await page.goto(`${BASE}/findings?cluster=staging-eu`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  await page.waitForTimeout(800)
  const facet = (title) => page.locator('.facet').filter({ has: page.locator('.facet-title', { hasText: new RegExp(`^${title}$`, 'i') }) }).first()
  const statusLink = page.getByRole('link', { name: /^Scanner status$/ })
  const row = page.locator('table tbody tr').first()
  await shot('findings', { banner: page.locator('.sys-line.tone-down').first(), stateFacet: facet('state'), statusLink, row })
  await hoverShot('findings', statusLink)

  await statusLink.click()
  await page.waitForSelector('.scan-card', { timeout: 20000 })
  await settle()
  await page.waitForTimeout(600)
  const findingsLink = page.getByRole('link', { name: /^Findings$/ })
  await shot('status', { lanes: page.locator('.lanes').first(), card: page.locator('.scan-card').first(), findingsLink })
  await hoverShot('status', findingsLink)

  await findingsLink.click()
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  await page.waitForTimeout(600)
  await shot('findings2', { row: page.locator('table tbody tr').first() })
  await hoverShot('findings2', page.locator('table tbody tr').first())

  await page.locator('table tbody tr').first().click()
  await page.waitForSelector('aside.triage', { timeout: 15000 })
  await settle()
  await shot('finding', { panel: page.locator('aside.triage'), note: page.locator('.ro-stale').first(), evidenceState: stateRow(), state: page.locator('aside.triage .triage-head') })
})
