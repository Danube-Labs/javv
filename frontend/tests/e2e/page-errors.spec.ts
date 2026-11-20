/**
 * The e2e suite fails a test whose page logs a code error (issue 749, `helpers.ts`) or breaks the
 * policy of the frontend server (issue 1272). This spec proves the catching: it causes each kind
 * on purpose, checks the fixture saw it, then empties the list so the fixture lets the test pass. It also holds every spec (in this folder, not
 * below it) to the helpers' `test`, since one taken from Playwright directly would skip the
 * check without a word.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import {
  ABOUT_FILE,
  BASE,
  codeErrorEventInText,
  codeErrorFromConsole,
  codeErrorLine,
  expect,
  isCi,
  login,
  policyViolationLine,
  requirePolicy,
  test,
} from './helpers'

test('a page error, an app error and an uncaught rejection are each caught', async ({ page, codeErrors }) => {
  await login(page)
  // an error in a mounted hook leaves the page on screen: the boundary logs `page error`
  await page.route(ABOUT_FILE, (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: "export default { mounted() { throw new Error('forced in mounted') }, render() { return null } }",
    }),
  )
  await page.locator('.sidebar a.side-item[href^="/about"]').click()
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(1)

  // a rejection nothing caught: the page logs `app error` and the browser reports it uncaught
  await page.evaluate(() => {
    void Promise.reject(new Error('forced rejection'))
  })
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(3)

  // Vue names the hook in a development build and gives a link to its error reference in a
  // production build, so the spec passes on the dev server and on the built app (issue 1223)
  expect([...codeErrors].sort()).toEqual([
    'app error on /about (unhandled rejection): forced rejection',
    expect.stringMatching(
      /^page error on \/about \((mounted hook|https:\/\/vuejs\.org\/error-reference\/#runtime-m)\): forced in mounted$/,
    ),
    'uncaught: forced rejection',
  ])
  codeErrors.length = 0 // they were caused on purpose
})

test('a code error logged as the page leaves is still caught', async ({ page, codeErrors }) => {
  // issue 749's own case: the error lands as the spec moves on, so the object behind the console
  // line is often gone before the fixture can read it. Which path caught it varies run to run; the
  // text path alone is pinned in 'only the code-error events count'.
  await page.goto(`${BASE}/login`)
  await page.evaluate(() => {
    // the logger's field order: timestamp, level, event, then the boundary's route, message, info
    console.error({ timestamp: 't', level: 'error', event: 'page error', route: '/overview', message: 'left as the page went', info: 'watcher callback' })
    // after this evaluate returns, so it cannot be cut off by the navigation it starts
    setTimeout(() => (location.href = '/login?again'), 0)
  })
  await page.waitForURL(/again/)
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(1)
  expect(codeErrors[0]).toMatch(/^page error/)
  expect(codeErrors[0]).toContain('left as the page went')
  codeErrors.length = 0 // caused on purpose
})

test('a code error left in place fails the test', async ({ page, codeErrors }) => {
  // the fixture's own check, after the body: deleting that check turns this test red. test.fail()
  // is also met if the body itself fails, so this test does not prove the catching; the two tests
  // above do
  test.fail()
  await page.goto(`${BASE}/login`)
  await page.evaluate(() => {
    void Promise.reject(new Error('left in place'))
  })
  await expect.poll(() => codeErrors.length, { timeout: 10_000 }).toBe(2)
})

/** Puts a style attribute in the page through HTML, as the old chart tooltips did. */
const styleInHtml = () => {
  const box = document.createElement('div')
  box.innerHTML = '<span style="color: red">refused</span>'
  document.body.append(box)
}

test('a policy violation is caught', async ({ page, policyViolations }) => {
  // issue 1272: the policy of the frontend server refused the style attributes of the chart
  // tooltips, and the tooltips showed bare text with no error
  await requirePolicy(page)
  await page.goto(`${BASE}/login`)
  await page.evaluate(styleInHtml)
  await expect.poll(() => policyViolations.length, { timeout: 10_000 }).toBe(1)
  expect(policyViolations[0]).toMatch(/^style-src-attr in /)
  policyViolations.length = 0 // caused on purpose
})

test('a policy violation left in place fails the test', async ({ page, policyViolations }) => {
  // the fixture's own check, after the body. As above, test.fail() is also met if the body fails
  test.fail()
  await requirePolicy(page)
  await page.goto(`${BASE}/login`)
  await page.evaluate(styleInHtml)
  await expect.poll(() => policyViolations.length, { timeout: 10_000 }).toBe(1)
})

test('a policy violation in the last moment of a test still fails it', async ({ page }) => {
  // The page breaks the policy in a timer, after the last step of the test returns. The
  // fixture must still see the violation before its check. test.fail() turns the case red if the
  // test passes.
  test.fail()
  await requirePolicy(page)
  await page.goto(`${BASE}/login`)
  await page.evaluate((html) => {
    setTimeout(() => {
      const box = document.createElement('div')
      box.innerHTML = html
      document.body.append(box)
    }, 0)
  }, '<span style="color: red">refused</span>')
})

test('requirePolicy reads CI=false, CI=0 and an empty CI as no CI run', () => {
  expect([undefined, '', '0', 'false', 'FALSE', ' false '].map(isCi)).toEqual([false, false, false, false, false, false])
  expect(['true', '1', 'yes'].map(isCi)).toEqual([true, true, true])
})

test('the line of a violation names the directive, the file, the line and the sample', () => {
  const event = { violatedDirective: 'style-src-attr', sourceFile: 'http://h/assets/app-1.js', lineNumber: 14, sample: '' }
  expect(policyViolationLine(event)).toBe('style-src-attr in app-1.js:14')
  expect(policyViolationLine({ ...event, sample: 'color: red' })).toBe('style-src-attr in app-1.js:14: color: red')
  expect(policyViolationLine({ ...event, sourceFile: '' })).toBe('style-src-attr in the page:14')
})

test('only the code-error events count', () => {
  const line = { level: 'error', route: '/overview', info: 'watcher callback', message: 'boom' }
  expect(codeErrorLine({ ...line, event: 'page error' })).toBe('page error on /overview (watcher callback): boom')
  expect(codeErrorLine({ ...line, event: 'app error' })).toBe('app error on /overview (watcher callback): boom')
  for (const event of ['page crashed', 'page failed to load', 'overview_load_failed']) {
    expect(codeErrorLine({ ...line, event }), event).toBeNull()
  }
  expect(codeErrorLine('Failed to load resource: the server responded with a status of 503')).toBeNull()
  expect(codeErrorLine(null)).toBeNull()

  // the same decision from the console text, which is all that is left after a navigation
  expect(codeErrorEventInText('{timestamp: t, level: error, event: page error, route: /overview, info: x}')).toBe('page error')
  expect(codeErrorEventInText('{timestamp: t, level: error, event: app error, route: /about}')).toBe('app error')
  expect(codeErrorEventInText('{timestamp: t, level: error, event: page crashed, route: /about}')).toBeNull()
  expect(codeErrorEventInText('{timestamp: t, level: error, event: page error message}')).toBeNull()
  expect(codeErrorEventInText('Failed to load resource: the server responded with a status of 503')).toBeNull()

  // the whole decision: the object when the page still has it, the text once it has navigated
  const preview = '{timestamp: t, level: error, event: page error, route: /overview, message: boom}'
  expect(codeErrorFromConsole(preview, null)).toBe(`page error, logged as the page left: ${preview}`)
  expect(codeErrorFromConsole(preview, { ...line, event: 'page error' })).toBe(
    'page error on /overview (watcher callback): boom',
  )
  expect(codeErrorFromConsole('{timestamp: t, level: error, event: page crashed}', null)).toBeNull()
})

test('every spec takes test and expect from the helpers', () => {
  const dir = fileURLToPath(new URL('.', import.meta.url))
  const direct = readdirSync(dir)
    .filter((name) => name.endsWith('.spec.ts'))
    .filter((name) =>
      /import (\{[^}]*\b(test|expect)\b[^}]*\}|\* as \w+) from ['"]@playwright\/test['"]/.test(
        readFileSync(dir + name, 'utf8'),
      ),
    )
  expect(direct).toEqual([])
})
