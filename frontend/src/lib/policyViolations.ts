/**
 * The browser refuses what the policy of the frontend server does not allow (`server/serve.mjs`).
 * The browser shows a refusal only in the console of the user, where an operator never sees it. So
 * each refusal goes through `logger.warn`, and the beacon takes it to the backend log as
 * `client.csp violation`.
 *
 * Two filters keep the log useful (issue 1275, option A):
 * - A browser extension that adds a script or a style to the page also breaks the policy. That is
 *   not a fault of JAVV, so a violation whose file or blocked address is an extension is dropped.
 * - One fault can break the policy many times (issue 1272: up to 1,862 violations on one page),
 *   and the beacon sends 20 events in each 5 s. So only the first violation of a directive and a
 *   file on a screen is logged. The others would push the other warnings of that screen out. A
 *   screen is the route by its name, so each image or finding that a user opens is not a new key.
 *
 * A violation before sign-in reaches no log, because the beacon needs a session.
 */
import { logger, type LogFields } from '@/lib/logger'

/** The fields of a `SecurityPolicyViolationEvent` that the entry uses. An older browser can leave
 *  out the fields that came last in the standard. */
export type PolicyViolation = Pick<SecurityPolicyViolationEvent, 'effectiveDirective' | 'lineNumber'> &
  Partial<Pick<SecurityPolicyViolationEvent, 'blockedURI' | 'sourceFile' | 'sample'>>

/** Chromium gives an extension address as its scheme only, with no colon. */
const EXTENSION = /^(chrome|moz|safari|safari-web)-extension(:|$)/
const MAX_SAMPLE = 60

const withoutQuery = (address: string): string => address.split(/[?#]/)[0] ?? ''

/** The name of the file, with no origin, path or query, so that no address goes into a log. The
 *  browser gives the address of the page for a violation in the page itself, and the last part of
 *  that address is not a file. */
function fileName(sourceFile: string, pageUrl: string): string {
  const path = withoutQuery(sourceFile)
  if (path === '' || path === withoutQuery(pageUrl)) return 'the page'
  return path.split('/').pop() || 'the page'
}

/** The log fields of one violation, or `null` for a violation from a browser extension. */
export function policyViolationEntry(
  e: PolicyViolation,
  route: string,
  pageUrl: string = globalThis.location?.href ?? '',
): LogFields | null {
  const sourceFile = e.sourceFile ?? ''
  if (EXTENSION.test(sourceFile) || EXTENSION.test(e.blockedURI ?? '')) return null
  return {
    directive: e.effectiveDirective,
    source: fileName(sourceFile, pageUrl),
    line: e.lineNumber,
    sample: (e.sample ?? '').slice(0, MAX_SAMPLE),
    route,
  }
}

/** The route of the app as the listener reads it: its path for the log, its name for the screen. */
export type CurrentRoute = { path: string; name?: string | symbol | null }

/** Logs each violation on `target` as a warning, at most one for each directive and file on a
 *  screen. The list of the logged ones lives as long as the page. */
export function logPolicyViolations(target: EventTarget, currentRoute: () => CurrentRoute): void {
  const logged = new Set<string>()
  target.addEventListener('securitypolicyviolation', (event) => {
    const route = currentRoute()
    const entry = policyViolationEntry(event as SecurityPolicyViolationEvent, route.path)
    if (entry === null) return
    const key = `${entry.directive} ${entry.source} ${String(route.name ?? route.path)}`
    if (logged.has(key)) return
    logged.add(key)
    logger.warn('csp violation', entry)
  })
}
