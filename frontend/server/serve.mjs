// @ts-check
/**
 * The frontend container's server (issue 452). It serves the built SPA and forwards the paths the
 * SPA calls on its own origin to the backend, so the browser sees one origin: the session cookie
 * stays first-party and the backend needs no CORS. Nothing in front of JAVV is required.
 *
 * Order per request: forward `/api`, `/auth`, `/readyz` to JAVV_BACKEND_URL; otherwise a file
 * from `dist/`; otherwise `index.html` (history-mode routes). When the backend does not answer,
 * it replies 502 with the backend's own error envelope, which the SPA reads as "backend down";
 * only the backend's own 503 means the store (stores/health.ts). No runtime dependencies.
 *
 *   node server/serve.mjs
 *   (env: JAVV_BACKEND_URL, JAVV_FRONTEND_PORT, JAVV_LOG_LEVEL, JAVV_BACKEND_CONNECT_TIMEOUT)
 */

import { randomBytes } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { readFile, stat } from 'node:fs/promises'
import http from 'node:http'
import https from 'node:https'
import { extname, join, normalize, sep } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { createLogger } from './log.mjs'

/** @typedef {import('./log.mjs').Logger} Logger */

const FORWARDED = ['/api', '/auth', '/readyz']

// hop-by-hop headers belong to one connection and are never passed on (RFC 9110 §7.6.1)
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
])

// What the browser may do with JAVV's pages, sent on every answer so that JAVV needs nothing in
// front of it (issue 892): code, styles, fonts and requests from this origin only, no frame on
// another site, no MIME sniffing, and no full URL in a Referer to another origin
/** @param {string} [nonce] the page's nonce: PrimeVue's theme adds `<style>` elements at run time */
export function contentSecurityPolicy(nonce) {
  return [
    "default-src 'self'",
    "script-src 'self'",
    nonce ? `style-src 'self' 'nonce-${nonce}'` : "style-src 'self'",
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join('; ')
}
export const SECURITY_HEADERS = {
  'content-security-policy': contentSecurityPolicy(),
  'x-frame-options': 'DENY',
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'same-origin',
}

// headers that name the backend's software: of no use to the browser, so never passed on
const NOT_FORWARDED = new Set(['server', 'x-powered-by'])

// the backend's own rule for an inbound id (core/logging.py), so the id it logs is ours
const REQUEST_ID = /^[A-Za-z0-9-]{1,64}$/

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.map': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
}

// A 502 is a failure any sender can repeat while the backend is down, so it logs at most one line
// per window, with the count it held back (.claude/rules/logging.md, issue 523's rule)
const WARN_WINDOW_MS = 10_000

// Seconds a connection to the backend may take to open (JAVV_BACKEND_CONNECT_TIMEOUT). Only the
// opening is timed: once connected, a slow or streamed answer (an export) is never cut.
export const CONNECT_TIMEOUT_S = 5

// Vite puts every hashed build file under /assets/, so its name changes whenever its content does
const IMMUTABLE = 'public, max-age=31536000, immutable'

/** @param {string} path */
function isForwarded(path) {
  return FORWARDED.some((p) => path === p || path.startsWith(`${p}/`))
}

/**
 * @param {string | undefined} value JAVV_BACKEND_CONNECT_TIMEOUT
 * @returns {number} milliseconds; a value that is not a number of seconds above 0 stops the server
 */
export function connectTimeoutMs(value) {
  if (value === undefined || value === '') return CONNECT_TIMEOUT_S * 1000
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds <= 0) {
    throw new Error(`JAVV_BACKEND_CONNECT_TIMEOUT must be a number of seconds above 0, not "${value}"`)
  }
  return seconds * 1000
}

/** @param {import('node:http').IncomingHttpHeaders} headers */
function withoutHopByHop(headers) {
  return Object.fromEntries(Object.entries(headers).filter(([k]) => !HOP_BY_HOP.has(k)))
}

/** @param {import('node:http').IncomingHttpHeaders} headers the backend's answer */
function toBrowser(headers) {
  const kept = Object.entries(withoutHopByHop(headers)).filter(([k]) => !NOT_FORWARDED.has(k))
  return { ...Object.fromEntries(kept), ...SECURITY_HEADERS }
}

/**
 * @param {import('node:http').ServerResponse} res
 * @param {number} status
 * @param {string} title
 * @param {string} detail
 * @param {string | null} requestId
 */
function problem(res, status, title, detail, requestId) {
  const body = JSON.stringify({ type: 'about:blank', title, status, detail, request_id: requestId })
  res.writeHead(status, { ...SECURITY_HEADERS, 'content-type': 'application/problem+json' })
  res.end(body)
}

/**
 * @param {string} distDir
 * @param {string} path
 * @returns {Promise<string | null>} the file under distDir the path names, if one exists
 */
async function fileFor(distDir, path) {
  let decoded
  try {
    decoded = decodeURIComponent(path)
  } catch {
    return null
  }
  const file = normalize(join(distDir, decoded))
  if (file !== distDir && !file.startsWith(distDir + sep)) return null // outside dist: never
  try {
    return (await stat(file)).isFile() ? file : null
  } catch {
    return null
  }
}

/**
 * The app page, with a new nonce in its policy and in a `<meta name="csp-nonce">` that main.ts
 * hands to PrimeVue for the `<style>` elements of its theme, so that no style needs 'unsafe-inline'.
 * @param {import('node:http').ServerResponse} res
 * @param {string} index
 * @param {boolean} head
 */
async function sendIndex(res, index, head) {
  const nonce = randomBytes(16).toString('base64')
  const html = (await readFile(index, 'utf8')).replace(
    '<head>',
    `<head>\n    <meta name="csp-nonce" content="${nonce}">`,
  )
  res.writeHead(200, {
    ...SECURITY_HEADERS,
    'content-security-policy': contentSecurityPolicy(nonce),
    'content-type': TYPES['.html'],
    'cache-control': 'no-cache',
  })
  res.end(head ? undefined : html)
}

/**
 * @param {import('node:http').ServerResponse} res
 * @param {string} file
 * @param {string} cache
 * @param {boolean} head
 */
function sendFile(res, file, cache, head) {
  const type = TYPES[/** @type {keyof typeof TYPES} */ (extname(file))] ?? 'application/octet-stream'
  res.writeHead(200, { ...SECURITY_HEADERS, 'content-type': type, 'cache-control': cache })
  if (head) {
    res.end()
    return
  }
  createReadStream(file).on('error', () => res.destroy()).pipe(res)
}

/**
 * @param {{
 *   backendUrl: string, distDir: string, log: Logger, warnWindowMs?: number,
 *   connectMs?: number, createConnection?: import('node:http').RequestOptions['createConnection']
 * }} options  createConnection replaces the socket the forward opens (tests only)
 * @returns {import('node:http').Server}
 */
export function createFrontendServer({
  backendUrl,
  distDir,
  log,
  warnWindowMs = WARN_WINDOW_MS,
  connectMs = CONNECT_TIMEOUT_S * 1000,
  createConnection,
}) {
  const backend = new URL(backendUrl)
  const root = normalize(distDir)
  const index = join(root, 'index.html')
  const transport = backend.protocol === 'https:' ? https : http
  let lastWarning = -Infinity
  let heldBack = 0

  /**
   * @param {import('node:http').IncomingMessage} req
   * @param {import('node:http').ServerResponse} res
   * @param {string} target
   */
  function forward(req, res, target) {
    const started = performance.now()
    const inbound = req.headers['x-request-id']
    const requestId =
      typeof inbound === 'string' && REQUEST_ID.test(inbound) ? inbound : randomBytes(8).toString('hex')

    const upstream = transport.request({
      protocol: backend.protocol,
      hostname: backend.hostname,
      port: backend.port,
      method: req.method,
      path: target,
      headers: { ...withoutHopByHop(req.headers), host: backend.host, 'x-request-id': requestId },
      // given only in tests: with no agent named, the request uses this socket instead of one
      // from the shared pool
      ...(createConnection ? { createConnection } : {}),
    })

    // An address whose pod is gone but still listed (its node died) never answers the connection,
    // and the request would hang with no banner; a Service with no pod at all refuses at once.
    // A reused keep-alive socket is already connected and starts no timer. For https the
    // connection is open only after the TLS handshake: a peer that accepts TCP and never answers
    // it would hang the request too.
    upstream.on('socket', (socket) => {
      if (!socket.connecting) return
      const timer = setTimeout(
        () => upstream.destroy(Object.assign(new Error('connect timeout'), { code: 'CONNECT_TIMEOUT' })),
        connectMs,
      )
      socket.once(transport === https ? 'secureConnect' : 'connect', () => clearTimeout(timer))
      socket.once('close', () => clearTimeout(timer))
    })

    upstream.on('response', (answer) => {
      res.writeHead(answer.statusCode ?? 502, toBrowser(answer.headers))
      answer.pipe(res)
    })

    upstream.on('error', (/** @type {NodeJS.ErrnoException} */ error) => {
      if (res.headersSent) {
        res.destroy() // the backend went away mid-answer: cut the stream, don't fake an end
        return
      }
      const now = performance.now()
      if (now - lastWarning >= warnWindowMs) {
        log.warning('backend unreachable', {
          method: req.method ?? '',
          path: target.split('?')[0] ?? '',
          status: 502,
          duration_ms: Math.round(now - started),
          request_id: requestId,
          held_back: heldBack,
          reason: error.code === 'CONNECT_TIMEOUT' ? 'connect timeout' : (error.code ?? 'error'),
        })
        lastWarning = now
        heldBack = 0
      } else {
        heldBack += 1
      }
      problem(res, 502, 'Backend unavailable', 'The JAVV backend did not answer.', requestId)
    })

    // a browser that leaves mid-request stops the backend call too
    res.on('close', () => {
      if (!res.writableFinished) upstream.destroy()
    })

    req.pipe(upstream)
  }

  return http.createServer(async (req, res) => {
    const url = new URL(req.url ?? '/', 'http://frontend')
    const path = url.pathname

    if (isForwarded(path)) {
      forward(req, res, `${path}${url.search}`)
      return
    }

    const head = req.method === 'HEAD'
    if (req.method !== 'GET' && !head) {
      res.writeHead(405, { ...SECURITY_HEADERS, allow: 'GET, HEAD' })
      res.end()
      return
    }
    const file = await fileFor(root, path)
    if (file && file !== index) {
      sendFile(res, file, path.startsWith('/assets/') ? IMMUTABLE : 'no-cache', head)
      return
    }
    // a missing hashed asset is a 404, never index.html served as script after an upgrade
    if (path.startsWith('/assets/')) {
      res.writeHead(404, { ...SECURITY_HEADERS, 'content-type': 'text/plain; charset=utf-8' })
      res.end('not found')
      return
    }
    await sendIndex(res, index, head)
  })
}

/** Reads the environment, listens, and stops cleanly on SIGTERM (a container's stop signal). */
function main() {
  const log = createLogger(process.env.JAVV_LOG_LEVEL)
  const backendUrl = process.env.JAVV_BACKEND_URL || 'http://backend:8000'
  const port = Number(process.env.JAVV_FRONTEND_PORT || 8080)
  const connectMs = connectTimeoutMs(process.env.JAVV_BACKEND_CONNECT_TIMEOUT)
  const distDir = fileURLToPath(new URL('../dist', import.meta.url))

  const server = createFrontendServer({ backendUrl, distDir, log, connectMs })
  server.listen(port, () => log.info('frontend server started', { port, backend: new URL(backendUrl).origin }))
  for (const signal of ['SIGTERM', 'SIGINT']) {
    process.on(signal, () => {
      log.info('frontend server stopping', { signal })
      server.close(() => process.exit(0))
      server.closeAllConnections()
    })
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main()
