/**
 * The /inspect console (issue 406) at the browser seam — issue 460 §1.
 *
 * The route walk already proves /inspect RENDERS (`walk.mjs`, the `inspect` route, ready
 * `.idx, .load-error`).
 * What it cannot reach is the two interactive loops, and the backend suites
 * (`test_inspect_route.py`, `test_admin_jobs.py`) already own the contracts underneath. So this
 * file deliberately asserts only what needs a real browser: that a click on the rail reaches the
 * editor, that ⌘↵ runs, that a rejection surfaces the backend's own words instead of a generic
 * failure, that a destructive trigger cannot fire from one click, and that the capability gate
 * holds for a session that fails it.
 *
 * Response shapes are NOT re-asserted here — that would duplicate the backend tests and go stale
 * with them.
 */
import type { Page } from '@playwright/test'

import { BASE, DATA_ROW, expect, login, loginViewer, test } from './helpers'

/** A repair row found by its LABEL, never by index: the rows come from the backend's job list,
 *  so their order is the API's to change (the fixed-column-index lesson from value-actions). */
const repairRow = (page: Page, label: string) =>
  page.locator('.repair-row').filter({ has: page.locator('b', { hasText: label }) })

/**
 * How many `job_trigger` rows the audit lens holds, read from the response that renders the
 * filtered view. The lens is applied from the URL, so the first fetch can be the UNfiltered one —
 * the waiter is armed before navigating and matches only the filtered request.
 */
async function auditTriggerTotal(page: Page): Promise<number> {
  const filtered = page.waitForResponse(
    (r) => r.url().includes('/api/v1/audit?') && r.url().includes('action=job_trigger'),
    { timeout: 20_000 },
  )
  await page.goto(`${BASE}/audit?action=job_trigger`)
  // the audit read returns OpenSearch's own total object, not a flat int (query/audit.py:188)
  const body = (await (await filtered).json()) as { total: { value: number; relation: string } }
  return body.total.value
}

async function openInspect(page: Page) {
  await login(page)
  await page.goto(`${BASE}/inspect`)
  await expect(page.locator('.idx, .load-error').first()).toBeVisible({ timeout: 20_000 })
}

test('the rail reaches the editor and ⌘↵ runs the query', async ({ page }) => {
  await openInspect(page)

  // POSITIVE CONTROL for the capability spec below. That one asserts the nav link is ABSENT for
  // a viewer, and `toHaveCount(0)` passes just as happily when the SELECTOR is wrong — so the
  // same selector is proven to match here, where the capability is held.
  await expect(page.locator('nav[aria-label="Primary"] a[href="/inspect"]')).toHaveCount(1)
  // the rail can legitimately be empty-ish, but SOME index must exist on a seeded store —
  // asserted so a silently broken _cat/indices reads as a failure rather than a skipped test
  const firstIndex = page.locator('.idx').first()
  await expect(firstIndex).toBeVisible()
  const pattern = ((await firstIndex.textContent()) ?? '').trim().split(/\s/)[0]!

  await firstIndex.click()
  // clicking inserts `<pattern>/_search` and forces POST — the path the console will run
  await expect(page.locator('.pathbox')).toHaveValue(`${pattern}/_search`)

  // ⌘↵ is bound to the editor and the path box, NOT the document, so the key must be pressed
  // with focus inside one of them — a page-level press would do nothing and pass vacuously
  await page.locator('.editor').press('ControlOrMeta+Enter')

  await expect(page.locator('.response')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('.response-empty')).toHaveCount(0)
  // the byte-budget meter only renders once a response reports a cap, so its presence is itself
  // the proof that took_ms/bytes/cap_bytes came back and were read
  await expect(page.locator('.budget')).toBeVisible()
  await expect(page.locator('.budget-row')).toContainText('cap')
  await expect(page.locator('.pane-label').filter({ hasText: 'Response' })).toContainText('took')
})

test('a rejected path surfaces the backend reason verbatim and leaves the response alone', async ({
  page,
}) => {
  await openInspect(page)

  // run something legitimate first, so we can prove the rejection does not overwrite it
  await page.locator('.editor').press('ControlOrMeta+Enter')
  await expect(page.locator('.response')).toBeVisible({ timeout: 20_000 })
  const before = await page.locator('.response').textContent()

  // a credential index is refused by the allowlist (docs/API.md § Admin) — the operator has to
  // see WHY, so the pane renders the backend's `title`, not a generic "request failed"
  await page.locator('.pathbox').fill('system-users/_search')
  await page.locator('.pathbox').press('ControlOrMeta+Enter')

  const reject = page.locator('.reject')
  await expect(reject).toBeVisible({ timeout: 20_000 })
  await expect(reject).toContainText('422')
  // the reason is the backend's, so assert it is SPECIFIC rather than matching exact prose the
  // backend owns: it must name the thing refused, not just say something went wrong
  await expect(reject).toContainText(/system-users|not inspectable|allowlist|credential/i)

  // the previous good response is still on screen — a rejection is not a state reset
  expect(await page.locator('.response').textContent()).toBe(before)
})

test('the repair card triggers a job that settles to done with counts, and it lands in the audit log', async ({
  page,
}) => {
  // Count the journaled triggers BEFORE, so the assertion afterwards proves THIS run landed.
  // Matching row text alone would not: a store that has ever run this job already carries
  // `staleness_sweep` rows, so the check would pass without the trigger doing anything.
  //
  // The count comes from the RESPONSE that renders the filtered view, not from counting rows.
  // Counting the DOM raced the filter: the lens is URL-driven and applies after the first fetch,
  // so on CI a pre-filter row was counted as if it were a job_trigger (before=1 on a store that
  // had none, so the assertion demanded 2). `networkidle` does not order those. The response's
  // own `total` is also not page-limited, which row-counting is.
  await login(page)
  const triggersBefore = await auditTriggerTotal(page)

  await page.goto(`${BASE}/inspect`)
  await expect(page.locator('.idx, .load-error').first()).toBeVisible({ timeout: 20_000 })
  const row = repairRow(page, 'Staleness sweep')
  await expect(row).toBeVisible()

  const runButton = row.locator('button', { hasText: /^(Run|Running…)$/ })
  await runButton.click()

  // The in-flight state is TRANSIENT: run() refreshes immediately after the 202, and a sweep on
  // a small store can already be done by then. Asserting `running` strictly would be a race
  // against job duration, and this suite runs with retries: 0. So the deterministic assertion is
  // that the row LEAVES idle and SETTLES to done-with-counts; the bar is checked only if the
  // running state was actually caught.
  const meta = row.locator('.job-meta')
  await expect(meta).not.toHaveText('never', { timeout: 20_000 })
  if (await row.locator('.job-runbar').count()) {
    await expect(runButton).toBeDisabled()
    await expect(runButton).toHaveText('Running…')
  }
  // a done row's last-run cell is the time with its counts under it ("staled 0 · reverted 0"),
  // so the separator proves counts came back rather than an empty result blob
  await expect(meta).toContainText('·', { timeout: 40_000 })
  await expect(row.locator('.job-failed')).toHaveCount(0)

  // the trigger is journaled (D17) — the same fact the operator can audit afterwards. One MORE
  // row than before is what proves this run was recorded, rather than an old one being matched.
  expect(await auditTriggerTotal(page)).toBe(triggersBefore + 1)
  // and it is rendered: the newest row (the read's default order is desc) names the job kind.
  // NB the action column renders humanized — "Job started", not the raw `job_trigger` filtered on
  await expect(page.locator(DATA_ROW).first()).toContainText('staleness_sweep', {
    timeout: 20_000,
  })
})

test('the lifecycle sweep cannot fire from one click, and cancel changes nothing', async ({
  page,
}) => {
  await openInspect(page)
  const row = repairRow(page, 'Lifecycle sweep')
  await expect(row).toBeVisible()
  const statusBefore = await row.locator('.job-meta').textContent()

  // this job DROPS whole indices, so Run must open a confirm first
  await row.locator('button', { hasText: /^(Run|Running…)$/ }).click()
  const modal = page.locator('[role="dialog"]', { hasText: 'Run the lifecycle sweep?' })
  await expect(modal).toBeVisible()
  await expect(modal).toContainText('deleting whole aged indices')

  await modal.locator('button', { hasText: 'Cancel' }).click()
  await expect(modal).toHaveCount(0)
  // cancel is a NO-OP, not a deferred confirm: the row's status is untouched, which is the only
  // observable proof from here that no trigger was sent
  expect(await row.locator('.job-meta').textContent()).toBe(statusBefore)

  // deliberately never clicks "Run the sweep" — it would drop indices out of the seeded corpus
  // and the other specs share that store
})

test('a session without can_inspect_store gets no nav entry and cannot reach the route', async ({
  page,
}) => {
  await loginViewer(page)

  // the nav is capability-driven (the UI gates on capabilities, never role names — docs/API.md)
  await expect(page.locator('nav[aria-label="Primary"]')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator('nav[aria-label="Primary"] a[href="/inspect"]')).toHaveCount(0)

  // and typing the URL is refused too — a hidden link is not a permission check
  await page.goto(`${BASE}/inspect`)
  await expect(page).not.toHaveURL(/\/inspect/)
  await expect(page.locator('.console')).toHaveCount(0)
})
