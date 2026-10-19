// @vitest-environment node
/**
 * The frontend container's server (server/serve.mjs, issue 452), run for real: a fake backend on
 * a free port, a throwaway dist/, and fetch against the frontend server.
 */
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import http from 'node:http'
import https from 'node:https'
import net, { type AddressInfo } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'

import { createLogger } from '../../server/log.mjs'
import {
  BACKEND_IDLE_MS,
  backendAgent,
  connectTimeoutMs,
  createFrontendServer,
  SECURITY_HEADERS,
} from '../../server/serve.mjs'

type Seen = { method?: string; url?: string; headers: http.IncomingHttpHeaders; body: string }

let dist: string
let backend: http.Server
let backendUrl: string
let seen: Seen[] = []
let lines: string[] = []
const servers: http.Server[] = []

const listen = (server: http.Server): Promise<string> =>
  new Promise((resolve) =>
    server.listen(0, '127.0.0.1', () =>
      resolve(`http://127.0.0.1:${(server.address() as AddressInfo).port}`),
    ),
  )

async function frontend(url = backendUrl, warnWindowMs?: number, connectMs?: number): Promise<string> {
  const log = createLogger('info', (line) => lines.push(line))
  const server = createFrontendServer({ backendUrl: url, distDir: dist, log, warnWindowMs, connectMs })
  servers.push(server)
  return listen(server)
}

beforeAll(async () => {
  dist = mkdtempSync(join(tmpdir(), 'javv-dist-'))
  mkdirSync(join(dist, 'assets'))
  writeFileSync(
    join(dist, 'index.html'),
    '<!doctype html><html><head><title>javv</title></head><body><div id="app"></div></body></html>',
  )
  writeFileSync(join(dist, 'assets', 'index-abc123.js'), 'console.log(1)')
  writeFileSync(join(dist, 'favicon.ico'), 'icon')

  backend = http.createServer((req, res) => {
    let body = ''
    req.on('data', (chunk: Buffer) => (body += chunk.toString()))
    req.on('end', () => {
      seen.push({ method: req.method, url: req.url, headers: req.headers, body })
      if (req.url?.startsWith('/api/v1/missing')) {
        res.writeHead(404, { 'content-type': 'application/problem+json' })
        res.end('{"title":"Not Found","status":404}')
      } else if (req.url === '/auth/login') {
        res.writeHead(200, { 'set-cookie': ['javv_session=abc; HttpOnly; Path=/', 'other=1; Path=/'] })
        res.end('{"user":{}}')
      } else if (req.url === '/api/v1/identity') {
        res.writeHead(200, { 'content-type': 'application/json', server: 'uvicorn', 'x-powered-by': 'x' })
        res.end('{}')
      } else if (req.url === '/api/v1/slow') {
        setTimeout(() => {
          res.writeHead(200, { 'content-type': 'application/json' })
          res.end('{"slow":true}')
        }, 150)
      } else if (req.url === '/api/v1/stream') {
        res.writeHead(200, { 'content-type': 'text/csv' })
        res.write('a,b\n')
        setTimeout(() => res.end('1,2\n'), 20)
      } else {
        res.writeHead(200, { 'content-type': 'application/json' })
        res.end(`{"echo":${JSON.stringify(body)}}`)
      }
    })
  })
  backendUrl = await listen(backend)
})

afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => new Promise((r) => s.close(r))))
  seen = []
  lines = []
})

afterAll(async () => {
  await new Promise((r) => backend.close(r))
  rmSync(dist, { recursive: true, force: true })
})

describe('the static files', () => {
  it('serves index.html for a history-mode route, never cached', async () => {
    const res = await fetch(`${await frontend()}/findings`)
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toMatch(/^text\/html/)
    expect(res.headers.get('cache-control')).toBe('no-cache')
    expect(await res.text()).toContain('id="app"')
  })

  it('serves a hashed asset as immutable, with its own type', async () => {
    const res = await fetch(`${await frontend()}/assets/index-abc123.js`)
    expect(res.status).toBe(200)
    expect(res.headers.get('content-type')).toMatch(/^text\/javascript/)
    expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable')
  })

  it('answers HEAD with the headers and no body', async () => {
    const res = await fetch(`${await frontend()}/assets/index-abc123.js`, { method: 'HEAD' })
    expect(res.status).toBe(200)
    expect(res.headers.get('cache-control')).toBe('public, max-age=31536000, immutable')
    expect(await res.text()).toBe('')
  })

  it('serves other root files uncached', async () => {
    const res = await fetch(`${await frontend()}/favicon.ico`)
    expect(res.headers.get('cache-control')).toBe('no-cache')
  })

  it('answers 404 for a missing hashed asset, not index.html as script', async () => {
    const res = await fetch(`${await frontend()}/assets/index-gone.js`)
    expect(res.status).toBe(404)
    expect(await res.text()).not.toContain('id="app"')
  })

  it('never serves a file from outside dist', async () => {
    // fetch would normalize dot segments; an encoded slash survives the URL parser and decodes
    // to ../ in the server, so send the raw path
    const { port } = new URL(await frontend())
    const body = await new Promise<string>((resolve, reject) => {
      http
        .get({ host: '127.0.0.1', port, path: '/..%2f..%2f..%2f..%2fetc%2fpasswd' }, (res) => {
          let text = ''
          res.on('data', (c: Buffer) => (text += c.toString()))
          res.on('end', () => resolve(text))
        })
        .on('error', reject)
    })
    expect(body).toContain('id="app"') // the SPA, not the file
    expect(body).not.toContain('root:')
  })

  it('refuses a write to a static path', async () => {
    const res = await fetch(`${await frontend()}/findings`, { method: 'POST' })
    expect(res.status).toBe(405)
  })
})

describe('the security headers (issue 892)', () => {
  const policy = (res: Response) => res.headers.get('content-security-policy') ?? ''
  const fixed = (res: Response) =>
    expect({
      frame: res.headers.get('x-frame-options'),
      sniff: res.headers.get('x-content-type-options'),
      referrer: res.headers.get('referrer-policy'),
    }).toEqual({ frame: 'DENY', sniff: 'nosniff', referrer: 'same-origin' })

  it('gives the page a new style nonce, the same in its policy and in its meta', async () => {
    const base = await frontend()
    const nonces: string[] = []
    for (let i = 0; i < 2; i++) {
      const res = await fetch(`${base}/findings`)
      fixed(res)
      const meta = /<meta name="csp-nonce" content="([^"]+)">/.exec(await res.text())?.[1]
      expect(meta).toBeTruthy()
      expect(policy(res)).toContain(`style-src 'self' 'nonce-${meta}'`)
      nonces.push(meta as string)
    }
    expect(nonces[0]).not.toBe(nonces[1]) // one per page, never reused
  })

  it('allows no inline script or style, and no frame on another site', async () => {
    const res = await fetch(`${await frontend()}/`)
    expect(policy(res)).toContain("script-src 'self';")
    expect(policy(res)).toContain("frame-ancestors 'none'")
    expect(policy(res)).not.toContain('unsafe-inline')
    expect(policy(res)).not.toContain('unsafe-eval')
  })

  it('sends them on a file, a missing asset and a refused method too', async () => {
    const base = await frontend()
    for (const res of [
      await fetch(`${base}/assets/index-abc123.js`),
      await fetch(`${base}/assets/gone-000.js`),
      await fetch(`${base}/x`, { method: 'POST' }),
    ]) {
      fixed(res)
      expect(policy(res)).toBe(SECURITY_HEADERS['content-security-policy'])
    }
  })

  it('sends them on a forwarded answer and drops the headers that name the backend software', async () => {
    const res = await fetch(`${await frontend()}/api/v1/identity`)
    fixed(res)
    expect(res.headers.get('server')).toBeNull()
    expect(res.headers.get('x-powered-by')).toBeNull()
    expect(res.headers.get('content-type')).toBe('application/json') // the rest passes on
  })

  it('sends them on the 502 when the backend does not answer', async () => {
    const res = await fetch(`${await frontend('http://127.0.0.1:1')}/api/v1/findings`)
    expect(res.status).toBe(502)
    fixed(res)
  })
})

describe('the forward to the backend', () => {
  it('forwards /api, /auth and /readyz with method, query and body', async () => {
    const base = await frontend()
    await fetch(`${base}/api/v1/findings?cluster_id=c1&q=x`, { method: 'POST', body: '{"a":1}' })
    await fetch(`${base}/readyz`)
    expect(seen.map((s) => `${s.method} ${s.url}`)).toEqual([
      'POST /api/v1/findings?cluster_id=c1&q=x',
      'GET /readyz',
    ])
    expect(seen[0]!.body).toBe('{"a":1}')
  })

  it('passes every Set-Cookie from the backend through, and the browser cookie to it', async () => {
    const res = await fetch(`${await frontend()}/auth/login`, {
      method: 'POST',
      headers: { cookie: 'javv_session=old' },
    })
    expect(res.headers.getSetCookie()).toEqual(['javv_session=abc; HttpOnly; Path=/', 'other=1; Path=/'])
    expect(seen[0]!.headers.cookie).toBe('javv_session=old')
  })

  it('passes a backend 404 under /api through, instead of the SPA', async () => {
    const res = await fetch(`${await frontend()}/api/v1/missing`)
    expect(res.status).toBe(404)
    expect(await res.json()).toEqual({ title: 'Not Found', status: 404 })
  })

  it('does not forward a path that only starts with the same letters', async () => {
    const res = await fetch(`${await frontend()}/apiary`)
    expect(seen).toHaveLength(0)
    expect(await res.text()).toContain('id="app"')
  })

  it('streams a response body through', async () => {
    const res = await fetch(`${await frontend()}/api/v1/stream`)
    expect(await res.text()).toBe('a,b\n1,2\n')
  })

  it('keeps a valid request id, and mints one when there is none', async () => {
    const base = await frontend()
    await fetch(`${base}/api/v1/x`, { headers: { 'x-request-id': 'trace-123' } })
    await fetch(`${base}/api/v1/x`, { headers: { 'x-request-id': 'bad id!' } })
    expect(seen[0]!.headers['x-request-id']).toBe('trace-123')
    expect(seen[1]!.headers['x-request-id']).toMatch(/^[0-9a-f]{16}$/)
  })
})

async function deadBackend(): Promise<string> {
  const dead = http.createServer()
  const url = await listen(dead)
  await new Promise((r) => dead.close(r)) // the port is now closed: connection refused
  return url
}

// The default connect timeout (5 s) equals vitest's test timeout, so a closed port that did not
// refuse once ended as a test timeout that could not say what the connection did (issue 811)
const DEAD_CONNECT_MS = 1_000

describe('a backend that does not answer', () => {
  it('gets a 502 with the error envelope, and one warning line', async () => {
    const deadUrl = await deadBackend()

    const res = await fetch(`${await frontend(deadUrl, undefined, DEAD_CONNECT_MS)}/readyz?x=secret`, {
      headers: { 'x-request-id': 'rid-1', authorization: 'Bearer t0ken', cookie: 'javv_session=s3' },
    })

    expect(res.status).toBe(502) // the SPA reads 502 as the backend, 503 as the store
    expect(res.headers.get('content-type')).toBe('application/problem+json')
    expect(await res.json()).toEqual({
      type: 'about:blank',
      title: 'Backend unavailable',
      status: 502,
      detail: 'The JAVV backend did not answer.',
      request_id: 'rid-1',
    })
    expect(lines).toHaveLength(1)
    const line = JSON.parse(lines[0]!)
    expect(Object.keys(line).slice(0, 3)).toEqual(['timestamp', 'level', 'event'])
    expect(line).toMatchObject({
      level: 'warning',
      event: 'backend unreachable',
      path: '/readyz',
      status: 502,
      held_back: 0,
    })
    // no query string, header or credential reaches the log
    expect(lines[0]).not.toMatch(/secret|t0ken|s3|Bearer|cookie|authorization/i)
  })

  it('logs a burst of 502s once per window, with the count it held back', async () => {
    const base = await frontend(await deadBackend(), 60_000, DEAD_CONNECT_MS)
    for (let i = 0; i < 3; i++) expect((await fetch(`${base}/readyz`)).status).toBe(502)
    expect(lines).toHaveLength(1) // any sender can repeat a 502 while the backend is down

    lines = []
    const every = await frontend(await deadBackend(), 0, DEAD_CONNECT_MS)
    await fetch(`${every}/readyz`)
    await fetch(`${every}/readyz`)
    expect(lines.map((l) => JSON.parse(l).held_back)).toEqual([0, 0])
  })
})

/** A socket that never finishes connecting: an address whose pod is gone but still listed. */
function neverConnects(): net.Socket {
  const socket = new net.Socket()
  Object.defineProperty(socket, 'connecting', { value: true })
  return socket
}

describe('the connect timeout (JAVV_BACKEND_CONNECT_TIMEOUT)', () => {
  it('answers 502 when the connection does not open in time, with the reason logged', async () => {
    const log = createLogger('info', (line) => lines.push(line))
    const server = createFrontendServer({
      backendUrl,
      distDir: dist,
      log,
      connectMs: 50,
      createConnection: () => neverConnects(),
    })
    servers.push(server)
    const started = performance.now()
    const res = await fetch(`${await listen(server)}/readyz`)
    expect(res.status).toBe(502)
    expect(performance.now() - started).toBeLessThan(2_000)
    expect((await res.json()).title).toBe('Backend unavailable')
    expect(JSON.parse(lines[0]!)).toMatchObject({ event: 'backend unreachable', reason: 'connect timeout' })
  })

  it('counts the TLS handshake as part of connecting to an https backend', async () => {
    // a peer that takes the TCP connection and never answers the handshake
    const held: net.Socket[] = []
    const silent = net.createServer((socket) => held.push(socket))
    await new Promise<void>((resolve) => silent.listen(0, '127.0.0.1', resolve))
    const log = createLogger('info', (line) => lines.push(line))
    const server = createFrontendServer({
      backendUrl: `https://127.0.0.1:${(silent.address() as AddressInfo).port}`,
      distDir: dist,
      log,
      connectMs: 50,
    })
    servers.push(server)
    try {
      const started = performance.now()
      const res = await fetch(`${await listen(server)}/readyz`)
      expect(res.status).toBe(502)
      expect(performance.now() - started).toBeLessThan(2_000)
      expect(JSON.parse(lines[0]!)).toMatchObject({ reason: 'connect timeout' })
    } finally {
      held.forEach((socket) => socket.destroy())
      silent.close()
    }
  })

  it('never cuts an answer slower than the timeout once connected', async () => {
    const log = createLogger('info', (line) => lines.push(line))
    const server = createFrontendServer({ backendUrl, distDir: dist, log, connectMs: 50 })
    servers.push(server)
    const base = await listen(server)
    for (let i = 0; i < 2; i++) {
      const res = await fetch(`${base}/api/v1/slow`) // 150 ms, three times the timeout
      expect(res.status).toBe(200)
      expect(await res.json()).toEqual({ slow: true })
    }
    expect(lines).toHaveLength(0)
  })

  it('names another failure by its code', async () => {
    // a hang after the connection opened starts no connect timer: this ends it before the test's
    // own timeout, with no log line, so each way of not refusing fails with its own message
    await fetch(`${await frontend(await deadBackend(), undefined, DEAD_CONNECT_MS)}/readyz`, {
      signal: AbortSignal.timeout(3_000),
    })
    expect(JSON.parse(lines[0]!).reason).toBe('ECONNREFUSED')
  })

  it('reads seconds, defaults to 5, and stops the server at start on a bad value', () => {
    expect(connectTimeoutMs(undefined)).toBe(5_000)
    expect(connectTimeoutMs('')).toBe(5_000)
    expect(connectTimeoutMs('0.5')).toBe(500)
    for (const bad of ['0', '-1', 'five', 'Infinity']) {
      expect(() => connectTimeoutMs(bad)).toThrow(/JAVV_BACKEND_CONNECT_TIMEOUT/)
    }
  })
})

/** A backend that keeps an idle connection for a minute, and notes when the other side ends one. */
async function patientBackend() {
  const ended: number[] = []
  const clientPorts: (number | undefined)[] = []
  const server = http.createServer((req, res) => {
    clientPorts.push(req.socket.remotePort)
    if (req.url === '/api/v1/slow') {
      setTimeout(() => res.end('{"slow":true}'), 150)
    } else {
      res.end('{}')
    }
  })
  server.keepAliveTimeout = 60_000
  server.on('connection', (socket: net.Socket) => socket.on('end', () => ended.push(performance.now())))
  const url = await listen(server)
  const stop = () => {
    server.closeAllConnections()
    return new Promise((r) => server.close(r))
  }
  return { url, ended, clientPorts, stop }
}

async function until(done: () => boolean, ms: number): Promise<boolean> {
  const end = performance.now() + ms
  while (!done() && performance.now() < end) await new Promise((r) => setTimeout(r, 10))
  return done()
}

describe('the pool to the backend (issue 924)', () => {
  // the backend closes an idle connection after 5 s; a request sent on one that it is closing gets
  // a reset, which the frontend server answers with a 502. So the frontend server must close first.
  it('closes an idle connection to the backend before the backend does', async () => {
    const patient = await patientBackend()
    try {
      const log = createLogger('info', (line) => lines.push(line))
      const server = createFrontendServer({ backendUrl: patient.url, distDir: dist, log, idleMs: 200 })
      servers.push(server)
      expect((await fetch(`${await listen(server)}/api/v1/x`)).status).toBe(200)
      const answered = performance.now()
      expect(await until(() => patient.ended.length === 1, 2_000)).toBe(true)
      expect(patient.ended[0]! - answered).toBeGreaterThanOrEqual(150)
    } finally {
      await patient.stop()
    }
  })

  it('still keeps a connection for the requests that follow soon', async () => {
    const patient = await patientBackend()
    try {
      const log = createLogger('info', (line) => lines.push(line))
      const server = createFrontendServer({ backendUrl: patient.url, distDir: dist, log, idleMs: 500 })
      servers.push(server)
      const base = await listen(server)
      await fetch(`${base}/api/v1/x`)
      await new Promise((r) => setTimeout(r, 50))
      await fetch(`${base}/api/v1/x`)
      expect(patient.clientPorts).toHaveLength(2)
      expect(patient.clientPorts[1]).toBe(patient.clientPorts[0]) // one connection, used twice
    } finally {
      await patient.stop()
    }
  })

  it('never cuts an answer slower than the idle time', async () => {
    const patient = await patientBackend()
    try {
      const log = createLogger('info', (line) => lines.push(line))
      const server = createFrontendServer({ backendUrl: patient.url, distDir: dist, log, idleMs: 50 })
      servers.push(server)
      const res = await fetch(`${await listen(server)}/api/v1/slow`) // 150 ms, three times the idle time
      expect(res.status).toBe(200)
      expect(await res.json()).toEqual({ slow: true })
      expect(lines).toHaveLength(0)
    } finally {
      await patient.stop()
    }
  })

  it('keeps connections and closes an idle one after 4 s by default, below the backend 5 s', () => {
    expect(BACKEND_IDLE_MS).toBe(4_000)
    for (const transport of [http, https]) {
      const agent = backendAgent(transport) as http.Agent & { keepAlive: boolean; options: { timeout: number } }
      expect(agent).toBeInstanceOf(transport.Agent)
      expect(agent.keepAlive).toBe(true)
      expect(agent.options.timeout).toBe(BACKEND_IDLE_MS)
      agent.destroy()
    }
  })
})

describe('the log lines', () => {
  it('follow JAVV_LOG_LEVEL, and an unknown level stops the server at start', () => {
    const out: string[] = []
    const log = createLogger('warning', (l) => out.push(l))
    log.info('quiet')
    log.warning('loud', { n: 1 })
    expect(out).toHaveLength(1)
    expect(() => createLogger('verbose')).toThrow(/unknown log level/)
  })

  it('never carry a header or a body: no log call in the server reads one', () => {
    const source = readFileSync(new URL('../../server/serve.mjs', import.meta.url), 'utf8')
    const calls = [...source.matchAll(/log\.(?:debug|info|warning|error)\(([\s\S]*?)\)\n/g)]
    expect(calls.length).toBeGreaterThan(0)
    for (const [call] of calls) expect(call).not.toMatch(/headers|cookie|authorization|body|req\.url/i)
  })
})
