// Video 1, from a scan to a finding: All clusters, one cluster, its findings, one finding's
// evidence from each scanner. Read-only: this walk changes nothing.
import { BASE, record } from './common.mjs'

await record('v1', async ({ page, shot, hoverShot, settle }) => {
  await page.goto(`${BASE}/clusters`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const cluster = page.locator('table tbody tr').filter({ hasText: 'prod-eu-1' }).first()
  await shot('clusters', { cluster, table: page.locator('table').first() })
  await hoverShot('clusters', cluster)

  await cluster.click()
  await page.waitForURL(/overview/, { timeout: 15000 })
  await settle()
  await page.waitForTimeout(800)
  const findingsLink = page.getByRole('link', { name: /^Findings$/ })
  await shot('overview', { head: page.locator('.head-card').first(), findingsLink })
  await hoverShot('overview', findingsLink)

  await findingsLink.click()
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const row = page.locator('table tbody tr').first()
  const scannerFacet = page.locator('.facet').filter({ has: page.locator('.facet-title', { hasText: /^scanner$/i }) }).first()
  const scannerCol = page.locator('table thead th').filter({ hasText: /scanner/i }).first()
  await shot('findings', { row, scannerFacet, table: page.locator('table').first(), head: page.locator('.head-card').first() })
  console.log('scanner column found:', await scannerCol.count())
  await hoverShot('findings', row)

  await row.click()
  await page.waitForSelector('aside.triage', { timeout: 15000 })
  await settle()
  const evidence = page.locator('section.card').filter({ hasText: 'Per-scanner evidence' })
  await shot('finding', { evidence, panel: page.locator('aside.triage'), head: page.locator('h1').first() })
})
