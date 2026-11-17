/**
 * A row that opens something can be opened from the keyboard (issue 674). jsdom can prove the
 * link exists; only a browser proves Tab reaches it and Enter follows it.
 */
import type { Locator, Page } from '@playwright/test'

import { BASE, DATA_ROW, expect, login, test } from './helpers'

/** Focus the identifier link `link`, press Enter, and require the new address. */
async function openRow(page: Page, link: Locator, want: RegExp) {
  await expect(link).toBeVisible({ timeout: 20_000 })
  await link.focus()
  await expect(link).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(want, { timeout: 15_000 })
}

/** The parts of the count chip of a Running images row (`CountDisagree`). */
type CountChip = { trivy: string | null; marks: string[]; total: string | null }

/**
 * True when Trivy found at least one finding on the row's image. The image page shows Trivy by
 * default, so an image with none has no row to open (issue 1223: the dev store lists such an image
 * first). With two different counts the chip shows the Trivy count next to its mark; otherwise it
 * shows the total, with a mark for each scanner that counted it.
 */
function trivyFoundSome(chip: CountChip): boolean {
  const n = (text: string | null) => Number((text ?? '').replace(/\D/g, ''))
  if (chip.trivy !== null) return n(chip.trivy) > 0
  return chip.marks.includes('trivy') && n(chip.total) > 0
}

test('trivyFoundSome reads the Trivy count of each shape of the count chip', () => {
  expect(trivyFoundSome({ trivy: 'T1,256', marks: [], total: null })).toBe(true)
  expect(trivyFoundSome({ trivy: 'T0', marks: [], total: null })).toBe(false)
  expect(trivyFoundSome({ trivy: null, marks: ['trivy', 'grype'], total: '87' })).toBe(true)
  expect(trivyFoundSome({ trivy: null, marks: ['trivy'], total: '12' })).toBe(true)
  expect(trivyFoundSome({ trivy: null, marks: ['trivy'], total: '0' })).toBe(false)
  expect(trivyFoundSome({ trivy: null, marks: ['grype'], total: '5' })).toBe(false)
  expect(trivyFoundSome({ trivy: null, marks: [], total: '3' })).toBe(false)
})

test.beforeEach(async ({ page }) => {
  await login(page)
})

test('Findings: Tab reaches a row identifier and Enter opens the finding', async ({ page }) => {
  await page.goto(`${BASE}/findings`)
  await expect(page.locator(DATA_ROW).first()).toBeVisible({ timeout: 20_000 })
  await page.locator('.tbl thead').click() // start the tab walk at the table, not the top bar
  let reached = false
  for (let i = 0; i < 40 && !reached; i++) {
    await page.keyboard.press('Tab')
    reached = await page.evaluate(() => document.activeElement?.matches('.tbl tbody a.row-link') ?? false)
  }
  expect(reached, 'Tab never landed on a row identifier').toBe(true)
  const cve = await page.evaluate(() => document.activeElement?.textContent?.trim())
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/findings/${cve}\\?`), { timeout: 15_000 })
  await expect(page.locator('.detail-head')).toBeVisible()
})

test('Running images, and the findings panel on an image: Enter opens the row', async ({ page }) => {
  await page.goto(`${BASE}/images`)
  await expect(page.locator('.tbl tbody a.row-link').first()).toBeVisible({ timeout: 20_000 })
  const chips = await page.locator(DATA_ROW).evaluateAll((rows) =>
    rows.map((row) => {
      const trivyMark = row.querySelector('.cd-count .cd-mark[data-scanner="trivy"]')
      return {
        trivy: trivyMark?.parentElement?.textContent ?? null,
        marks: [...row.querySelectorAll('.cd-marks .cd-mark')].map((m) => m.getAttribute('data-scanner') ?? ''),
        total: row.querySelector('.cd-marks + .cd-count')?.textContent ?? null,
      }
    }),
  )
  const index = chips.findIndex(trivyFoundSome)
  expect(index, 'no image on the first page has a Trivy finding').toBeGreaterThanOrEqual(0)
  await openRow(page, page.locator(DATA_ROW).nth(index).locator('a.row-link').first(), /\/images\/sha256/)
  // any vulnerability ID: CVE, GHSA, GO and others (issue 1224)
  await openRow(page, page.locator('.tbl tbody a.row-link').first(), /\/findings\/[^/?]+\?/)
})

test('All clusters: Enter on a cluster name opens its Overview with that cluster', async ({ page }) => {
  await page.goto(`${BASE}/clusters`)
  const link = page.locator('.fleet-card tbody a.row-link').last()
  await expect(link).toBeVisible({ timeout: 20_000 })
  const cluster = new URL((await link.getAttribute('href'))!, BASE).searchParams.get('cluster')!
  await link.focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL((url) => url.pathname === '/overview' && url.searchParams.get('cluster') === cluster, {
    timeout: 15_000,
  })
})

test('Overview tables: Enter on a component, an image and a namespace each opens its target', async ({ page }) => {
  for (const [title, want] of [
    ['Top components', /\/findings\?.*q=/],
    ['Riskiest images', /\/images\/sha256/],
    ['Per namespace', /\/findings\?.*namespace=/],
  ] as const) {
    await page.goto(`${BASE}/overview`)
    const card = page.locator('section', { has: page.getByRole('heading', { name: title }) }).last()
    const link = card.locator('tbody a.row-link').first()
    await expect(link).toBeVisible({ timeout: 20_000 })
    await link.focus()
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(want, { timeout: 15_000 })
  }
})
