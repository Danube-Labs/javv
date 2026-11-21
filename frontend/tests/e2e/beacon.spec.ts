/**
 * The client-events beacon at the browser seam — issue 520 slice 4 (issue 519 item 3).
 *
 * The unit tests (`client-events-beacon.spec.ts`) mock the transport, and the smoke's section 6c
 * POSTs to the route with curl. Neither proves the seam between them: a real call site in the
 * BUILT app, `sendBeacon` carrying the session cookie, and the backend re-emitting the event into
 * its own log. That log line is the evidence an operator actually reads, so it is what this spec
 * asserts on.
 *
 * Needs the backend's stdout in `development/e2e/logs/backend.log`, which is where CI's
 * frontend-smoke job and the RUNNING-THE-STACK recipe both write it.
 */
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { BASE, USER, expect, login, requirePolicy, test } from './helpers'

const BACKEND_LOG = fileURLToPath(
  new URL('../../../development/e2e/logs/backend.log', import.meta.url),
)

type LogLine = {
  event?: string
  level?: string
  client_event?: boolean
  username?: string
  fields?: Record<string, unknown>
}

/** The `client.<name>` lines carrying this run's marker. The marker is unique per run, so a line
 *  left in the file by an earlier run (or another backend sharing it) cannot match. */
function clientLines(event: string, marker: string): LogLine[] {
  const found: LogLine[] = []
  for (const raw of readFileSync(BACKEND_LOG, 'utf8').split('\n')) {
    if (!raw.includes(marker)) continue
    try {
      const line = JSON.parse(raw) as LogLine
      if (line.event === event) found.push(line)
    } catch {
      // not a JSON line (uvicorn's own access lines share the stream)
    }
  }
  return found
}

test('a browser-side warning lands in the backend log as a client.<name> line', async ({
  page,
}) => {
  expect(existsSync(BACKEND_LOG), `no backend log at ${BACKEND_LOG}`).toBe(true)

  const marker = `beacon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  // three segments fail the "<index>/<verb>" shape check with a 422 before any index is read, so
  // the rejection does not depend on what the seeded store holds
  const path = `${marker}/_search/x`

  await login(page)
  await page.goto(`${BASE}/inspect`)
  await expect(page.locator('.idx, .load-error').first()).toBeVisible({ timeout: 20_000 })
  await page.locator('.pathbox').fill(path)
  await page.locator('.pathbox').press('ControlOrMeta+Enter')
  // the call site: InspectView logs `inspect_rejected` at warn, which queues it for the beacon
  await expect(page.locator('.reject')).toContainText('422', { timeout: 20_000 })

  // Flush now rather than waiting out the 5 s batching window: `pagehide` is one of the beacon's
  // two unload signals (lib/logger.ts). The request is observed, not assumed. Its body is not:
  // Chromium does not expose a sendBeacon payload to Playwright (postData() reads ""), so the
  // content is proven where it matters, by the log line below.
  const beacon = page.waitForRequest(
    (r) => r.url().endsWith('/api/v1/client-events') && r.method() === 'POST',
    { timeout: 10_000 },
  )
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')))
  await beacon

  await expect
    .poll(() => clientLines('client.inspect_rejected', marker).length, {
      timeout: 15_000,
      message: `no client.inspect_rejected line for ${marker} in ${BACKEND_LOG}`,
    })
    .toBe(1)
  const [line] = clientLines('client.inspect_rejected', marker)
  expect(line!.level).toBe('warning')
  expect(line!.client_event).toBe(true)
  // attributed from the session the beacon carried, never from anything the browser sent
  expect(line!.username).toBe(USER)
  // the call site's fields arrive nested under `fields`, not splatted into the line
  expect(line!.fields).toMatchObject({ path, status: 422 })
})

test('a policy violation lands in the backend log one time for its route', async ({
  page,
  policyViolations,
}) => {
  expect(existsSync(BACKEND_LOG), `no backend log at ${BACKEND_LOG}`).toBe(true)
  await requirePolicy(page)

  const marker = `beacon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  // The shell shows its not-found page for an unknown address and keeps that address as the
  // route. So the route of the log line carries the marker.
  const route = `/${marker}`
  await login(page)
  await page.goto(`${BASE}${route}`)
  await expect(page.locator('main')).toBeVisible({ timeout: 20_000 })
  // five style attributes in HTML, the shape of the bug of issue 1272: one directive and one file
  await page.evaluate(() => {
    for (let i = 0; i < 5; i += 1) {
      const box = document.createElement('div')
      box.innerHTML = '<span style="color: red">refused</span>'
      document.body.append(box)
    }
  })
  await expect.poll(() => policyViolations.length, { timeout: 10_000 }).toBeGreaterThan(0)

  const beacon = page.waitForRequest(
    (r) => r.url().endsWith('/api/v1/client-events') && r.method() === 'POST',
    { timeout: 10_000 },
  )
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')))
  await beacon

  await expect
    .poll(() => clientLines('client.csp violation', marker).length, {
      timeout: 15_000,
      message: `no client.csp violation line for ${marker} in ${BACKEND_LOG}`,
    })
    .toBe(1)
  const [line] = clientLines('client.csp violation', marker)
  expect(line!.level).toBe('warning')
  expect(line!.client_event).toBe(true)
  expect(line!.username).toBe(USER)
  expect(line!.fields).toMatchObject({ directive: 'style-src-attr', route })
  expect(Object.keys(line!.fields!).sort()).toEqual(['directive', 'line', 'route', 'sample', 'source'])
  policyViolations.length = 0 // caused on purpose
})
