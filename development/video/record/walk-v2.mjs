// Video 2, set the state of a finding: Not affected with a reason, then the record of it.
import fs from 'node:fs'
import { BASE, STATE, record } from './common.mjs'

await record('v2', async ({ page, shot, hoverShot, settle, stateRow, pickBothOpen }) => {
  await page.goto(`${BASE}/findings?cluster=prod-eu-1`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const { row, cve } = await pickBothOpen(0)
  fs.mkdirSync(STATE, { recursive: true })
  fs.writeFileSync(`${STATE}/v2-cve.txt`, cve ?? '')
  await shot('findings', { row })
  await hoverShot('findings', row)

  await row.click()
  await page.waitForSelector('aside.triage', { timeout: 15000 })
  await settle()
  const panel = page.locator('aside.triage')
  const na = page.getByRole('radio', { name: /Not affected/ })
  await shot('finding', { panel, na, evidenceState: stateRow() })
  await hoverShot('finding', na)

  await na.click()
  await settle()
  const firstReason = page.locator('.vex-chip').first()
  await shot('not-affected', { panel, reasons: page.locator('.vex-chips'), firstReason })
  await hoverShot('not-affected', firstReason)

  await firstReason.click()
  await settle()
  const save = page.getByRole('button', { name: /Save to audit trail/ })
  await shot('reason', { panel, save })
  await hoverShot('reason', save)

  await save.click()
  await page.locator('aside.triage .triage-head').getByText(/Not affected/).waitFor({ timeout: 10000 })
  await settle()
  const auditLink = page.getByRole('link', { name: /^Audit log$/ })
  const activity = page.locator('section.card').filter({ hasText: 'Activity on this finding' })
  await shot('saved', { panel, evidenceState: stateRow(), state: page.locator('aside.triage .triage-head'), activity, auditLink })
  await hoverShot('saved', auditLink)

  await auditLink.click()
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  await shot('audit', { top: page.locator('table tbody tr').first() })
})
