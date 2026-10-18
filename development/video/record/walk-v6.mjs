// Video 6, who did what: the Audit log, its user and action filters, the CSV export, and the
// Activity card of one finding. Read-only; run after the walks of videos 2, 3 and 4.
import { BASE, record } from './common.mjs'

await record('v6', async ({ page, shot, hoverShot, settle }) => {
  await page.goto(`${BASE}/audit?cluster=prod-eu-1`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  await page.waitForTimeout(600)
  const facet = (title) => page.locator('.facet').filter({ has: page.locator('.facet-title', { hasText: new RegExp(`^${title}$`, 'i') }) }).first()
  const row = (f, re) => f.locator('.facet-row').filter({ has: page.locator('.facet-text', { hasText: re }) }).first()
  const userFacet = facet('user')
  const actionFacet = facet('action')
  const lead = row(userFacet, /^\s*lead\s*$/)
  const bulk = row(actionFacet, /bulk triage/i)
  const table = page.locator('table').first()
  const exportBtn = page.getByRole('button', { name: /Export CSV/ })
  await shot('audit', { table, userFacet, lead, head: page.locator('.head-card').first() })
  await hoverShot('audit', lead)

  await lead.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  await shot('lead', { table, actionFacet, bulk })
  await hoverShot('lead', bulk)

  await bulk.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  const findingsLink = page.getByRole('link', { name: /^Findings$/ })
  await shot('bulk', { first: page.locator('table tbody tr').first(), exportBtn, findingsLink })
  await hoverShot('bulk', findingsLink)

  await findingsLink.click()
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  // a finding that walk 2 set to Not affected, one at a time
  const ackFilter = row(facet('state'), /not affected/i)
  await shot('findings', { ackFilter, stateFacet: facet('state') })
  await hoverShot('findings', ackFilter)

  await ackFilter.click()
  await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {})
  await settle()
  const acked = page.locator('table tbody tr').first()
  await shot('acked', { row: acked })
  await hoverShot('acked', acked)

  await acked.click()
  await page.waitForSelector('aside.triage', { timeout: 15000 })
  await settle()
  await page.waitForTimeout(600)
  await shot('finding', { activity: page.locator('section.card').filter({ hasText: 'Activity on this finding' }), panel: page.locator('aside.triage') })
})
