// Video 3, accept a risk with an expiry date: the dialog, the result, the Approval list, revoke.
import fs from 'node:fs'
import { BASE, STATE, record, sleep } from './common.mjs'

const REASON = 'No fix yet. A WAF rule blocks the attack path.'
// six weeks ahead: the dialog refuses a date in the past
const EXPIRY = new Date(Date.now() + 42 * 864e5).toISOString().slice(0, 10)
const read = (f) => (fs.existsSync(f) ? fs.readFileSync(f, 'utf8').trim() : '')
// skip the CVEs that earlier walks changed: their Decisions card would show old rows
const avoid = [read(`${STATE}/v2-cve.txt`), read(`${STATE}/v3-cve.txt`)].filter(Boolean)

await record('v3', async ({ page, shot, hoverShot, settle, pickBothOpen }) => {
  await page.goto(`${BASE}/findings?cluster=prod-eu-1`)
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const { row, cve } = await pickBothOpen(0, avoid)
  console.log('cve', cve)
  await shot('findings', { row })
  await hoverShot('findings', row)

  await row.click()
  await page.waitForSelector('aside.triage', { timeout: 15000 })
  await settle()
  const panel = page.locator('aside.triage')
  const accept = page.getByRole('button', { name: /Risk-accept this CVE/ })
  await shot('finding', { panel, accept })
  await hoverShot('finding', accept)

  await accept.click()
  const dialog = page.getByRole('dialog').first()
  await dialog.waitFor({ timeout: 10000 })
  await settle()
  const nsField = dialog.locator('.fld, div').filter({ has: page.getByText(/Scope · namespaces/) }).last()
  const nsOption = dialog.locator('.ra-chip').first()
  const blast = dialog.locator('.ra-blast')
  const expiry = dialog.locator('#ra-expiry')
  const reason = dialog.locator('#ra-just')
  const create = dialog.getByRole('button', { name: /Create decision/ })
  const targets = () => ({ dialog, nsField, nsOption, blast, expiry, reason, create })
  await shot('dialog', targets())
  await hoverShot('dialog', nsOption)

  await nsOption.click()
  await settle()
  await shot('dialog-ns', targets())
  await hoverShot('dialog-ns', expiry)

  await expiry.click()
  await expiry.fill(EXPIRY)
  await settle()
  await shot('dialog-expiry', targets())
  await hoverShot('dialog-expiry', reason)

  // the reason, typed in steps: each step is a screen that the video shows for a few frames
  await reason.click()
  const words = REASON.split(' ')
  for (let i = 1; i <= words.length; i++) {
    await reason.fill(words.slice(0, i).join(' '))
    await page.mouse.move(5, 5)
    await sleep(60)
    await shot(`type-${i}`, i === words.length ? targets() : {})
  }
  await hoverShot(`type-${words.length}`, create)

  await create.click()
  await dialog.waitFor({ state: 'detached', timeout: 15000 }).catch(() => {})
  // the page reads its state and its cards again after the decision; wait for both to land
  await sleep(800)
  await settle()
  const approvalsLink = page.getByRole('link', { name: /^Approval list$/ })
  const decisions = page.locator('section.card').filter({ hasText: 'Decisions on this CVE' })
  await shot('accepted', { panel, decisions, decisionRow: decisions.locator('tbody tr').first(), approvalsLink })
  await hoverShot('accepted', approvalsLink)

  await approvalsLink.click()
  await page.waitForSelector('table tbody tr', { timeout: 20000 })
  await settle()
  const first = page.locator('table tbody tr').first()
  const revoke = page.getByRole('button', { name: /^Revoke$/ }).first()
  await shot('approvals', { first, revoke, table: page.locator('table').first() })
  await hoverShot('approvals', revoke)

  await revoke.click()
  await settle()
  const confirm = page.getByRole('button', { name: /Confirm revoke/ }).first()
  await shot('armed', { first, confirm })
  await hoverShot('armed', confirm)

  await confirm.click()
  await settle()
  await sleep(600)
  await shot('revoked', { empty: page.getByText(/No standing risk-acceptances/).first() })
  fs.mkdirSync(STATE, { recursive: true })
  fs.writeFileSync(`${STATE}/v3-cve.txt`, cve ?? '')
}, { view: { width: 1760, height: 990 } })
