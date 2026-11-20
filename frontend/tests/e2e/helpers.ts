/**
 * Spec helpers — selectors and the login flow come from scripts/walk.mjs (the ONE owner of
 * the route matrix, testing.md §4: "a renamed selector breaks one file, loudly").
 *
 * Every spec takes `test` and `expect` from here, not from Playwright: this `test` fails any test
 * whose page logs a code error (issue 749). That is the app logger's `page error` or `app error`
 * line, or an error the page never caught. Those leave a working page on screen, so a spec's own
 * assertions pass over them, and the Overview's `reading 'series'` went unseen that way.
 * `page crashed` and `page failed to load` are not on the list: they draw the error page, which a
 * spec sees, and `crash-page.spec.ts` causes them on purpose.
 *
 * The same `test` also fails a test whose page breaks the Content-Security-Policy of the frontend
 * server (issue 1272). The browser then drops a style or a script, and the page stays on screen
 * with a part missing. This check works only behind `frontend/server/serve.mjs`, as in CI.
 */
import { expect, test as base, type ConsoleMessage, type Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the selector owner
import { DATA_ROW as WALK_DATA_ROW, login as walkLogin } from '../../scripts/walk.mjs'

export const BASE = process.env.JAVV_BASE ?? 'http://localhost:4173'
/** A grid data row: never the grid's loading or empty message row (issue 786). */
export const DATA_ROW: string = WALK_DATA_ROW
export const USER = process.env.JAVV_USER ?? 'admin'
export const PASS = process.env.JAVV_PASS ?? ''

/**
 * The capability-LESS viewer seeded by `development/scripts/seed-smoke.sh` (issue 460). Proving
 * a capability gate needs a session that fails it, and the admin session can never do that.
 */
export const VIEWER = process.env.JAVV_VIEWER_USER ?? 'smoke-viewer'
export const VIEWER_PASS = process.env.JAVV_VIEWER_PASS ?? 'ci-smoke-viewer-pw'

export async function login(page: Page): Promise<void> {
  await walkLogin(page, BASE, USER, PASS)
}

export async function loginViewer(page: Page): Promise<void> {
  await walkLogin(page, BASE, VIEWER, VIEWER_PASS)
}

/** The About page's own file: `/src/views/AboutView.vue` on the dev server, a hashed chunk in a
 *  build. Specs replace it to make a page fail on purpose. */
export const ABOUT_FILE = /AboutView(\.vue|-[\w-]+\.js)(\?.*)?$/

/** The app logger's events that mean code threw and the page stayed (`system/crash.ts`). */
export const CODE_ERROR_EVENTS: readonly string[] = ['page error', 'app error']

/** One line per code error, or null for any other console message. The logger writes one object
 *  per line: `{ timestamp, level, event, ...fields }`. */
export function codeErrorLine(entry: unknown): string | null {
  if (entry === null || typeof entry !== 'object') return null
  const { event, route, info, message } = entry as Record<string, unknown>
  if (typeof event !== 'string' || !CODE_ERROR_EVENTS.includes(event)) return null
  return `${event} on ${String(route)} (${String(info)}): ${String(message)}`
}

/** The code-error event named in a console line's text, or null. Chromium prints the logger's
 *  object as `{timestamp: …, level: error, event: page error, …}`, and that text outlives the page,
 *  while the object behind it is gone once the page navigates: issue 749's own case, a spec leaving
 *  Overview while a read was still landing. */
export function codeErrorEventInText(text: string): string | null {
  const event = /(?:^|[{,]\s*)event: ([^,}]+)/.exec(text)?.[1]?.trim()
  return event !== undefined && CODE_ERROR_EVENTS.includes(event) ? event : null
}

/** One line per code error in a console error message, from its object when the page still has
 *  it (`entry`, null once the page has navigated) or else from its text. */
export function codeErrorFromConsole(text: string, entry: unknown): string | null {
  const detail = codeErrorLine(entry)
  if (detail !== null) return detail
  const event = codeErrorEventInText(text)
  return event === null ? null : `${event}, logged as the page left: ${text}`
}

async function consoleCodeError(msg: ConsoleMessage): Promise<string | null> {
  if (msg.type() !== 'error') return null
  return codeErrorFromConsole(msg.text(), await msg.args()[0]?.jsonValue().catch(() => null))
}

/** The name of the function that the page calls for each policy violation. */
const POLICY_HOOK = '__javvPolicyViolation'

/** One line for a violation of the policy that the frontend server sends: the directive, the
 *  file and line, and the start of what the browser refused. */
export function policyViolationLine(e: {
  violatedDirective: string
  sourceFile: string
  lineNumber: number
  sample: string
}): string {
  const file = e.sourceFile.split('/').pop() || 'the page'
  return `${e.violatedDirective} in ${file}:${e.lineNumber}${e.sample ? `: ${e.sample.slice(0, 60)}` : ''}`
}

/** True when the value of `CI` names a CI run. `false`, `0` and an empty value do not. */
export function isCi(value: string | undefined): boolean {
  return value !== undefined && !['', '0', 'false'].includes(value.trim().toLowerCase())
}

/** Skips a test on a server that sends no policy, for example the dev server or `vite preview`.
 *  In CI it fails the test, because the CI job serves the app with `frontend/server/serve.mjs`
 *  (issue 1272). A check under no policy passes for the wrong reason. */
export async function requirePolicy(page: Page): Promise<void> {
  const res = await page.request.get(`${BASE}/login`)
  if (res.headers()['content-security-policy']) return
  if (isCi(process.env.CI)) throw new Error(`${BASE} sends no Content-Security-Policy header`)
  test.skip(true, `${BASE} sends no Content-Security-Policy header`)
}

/** Collects each violation of the policy on a page, one line for each. Call it before the page
 *  opens its first address. The fixture `policyViolations` calls it for the page of each test. A
 *  spec that opens a page in a second browser context calls it for that page. */
export async function watchPolicy(page: Page): Promise<string[]> {
  const found: string[] = []
  await page.exposeFunction(POLICY_HOOK, (e: Parameters<typeof policyViolationLine>[0]) => {
    const line = policyViolationLine(e)
    if (!found.includes(line)) found.push(line)
  })
  // The page sends the plain fields, and this side makes the line. The policy refuses `eval`
  // in the page, so the page cannot rebuild a function from its text.
  await page.addInitScript((hook) => {
    document.addEventListener('securitypolicyviolation', (e) => {
      const send = (window as unknown as Record<string, (f: object) => void>)[hook]
      send?.({
        violatedDirective: e.violatedDirective,
        sourceFile: e.sourceFile,
        lineNumber: e.lineNumber,
        sample: e.sample,
      })
    })
  }, POLICY_HOOK)
  return found
}

/** Waits until the violations that the page already has reach the list of `watchPolicy`. The
 *  browser sends a violation event as a task of its own, and the event then goes to this process
 *  in a second step. One more task in the page runs after the event, and its answer comes back
 *  after the call of the hook. A closed page sends nothing more. */
export async function settlePolicy(page: Page): Promise<void> {
  if (page.isClosed()) return
  await page.evaluate(() => new Promise((done) => setTimeout(done, 0))).catch(() => {})
}

/** Runs in the page: adds a style with the nonce of the page. The frontend server writes the nonce
 *  in `<meta name="csp-nonce">`, and the policy allows a style with it, as it allows the styles of
 *  the app (issue 1272). A page with no policy has no nonce, and the style needs none. */
function appendStyleWithNonce(css: string): void {
  const style = document.createElement('style')
  const nonce = document.querySelector('meta[name="csp-nonce"]')?.getAttribute('content')
  if (nonce) style.nonce = nonce
  style.textContent = css
  document.head.append(style)
}

/** Adds a style for a test to the page that is open. Never `page.addStyleTag`: the policy refuses
 *  a style with no nonce. */
export async function addStyle(page: Page, css: string): Promise<void> {
  await page.evaluate(appendStyleWithNonce, css)
}

/** Adds a style for a test to each page that the test opens, when its document is ready. */
export async function addStyleOnEachPage(page: Page, css: string): Promise<void> {
  await page.addInitScript({
    content: `addEventListener('DOMContentLoaded', () => (${appendStyleWithNonce.toString()})(${JSON.stringify(css)}))`,
  })
}

export const test = base.extend<{ codeErrors: string[]; policyViolations: string[] }>({
  // A test that causes a code error on purpose reads this list and empties it.
  codeErrors: [
    async ({ page }, use) => {
      const found: string[] = []
      const reading: Promise<void>[] = []
      page.on('console', (msg) => {
        reading.push(
          consoleCodeError(msg).then((line) => {
            if (line) found.push(line)
          }),
        )
      })
      page.on('pageerror', (err) => found.push(`uncaught: ${err.message}`))
      await use(found)
      await Promise.all(reading)
      expect(found, 'the page logged a code error').toEqual([])
    },
    { auto: true },
  ],
  // The browser refuses a style or a script that the policy of the frontend server does not
  // allow, and the page stays on screen with a part missing (issue 1272). A test that breaks the
  // policy on purpose reads this list and empties it. Each line is in the list one time.
  policyViolations: [
    async ({ page }, use) => {
      const found = await watchPolicy(page)
      await use(found)
      await settlePolicy(page)
      expect(found, 'the page broke the policy of the frontend server').toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
