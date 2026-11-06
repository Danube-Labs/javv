/**
 * The shared route walk (#383 + #387): ONE route matrix + sanity asserts used by BOTH
 * the CI smoke (scripts/ci-smoke.mjs, gating) and the authoring visual rig
 * (scripts/visual-capture.mjs, screenshots + forced states). A selector or route rename
 * breaks loudly here, in one file.
 *
 * Contract per route: `ready` is a selector that only exists once the screen's data has
 * rendered (not the shell); routes without server data gate on `.screen`. Asserts are
 * viewport-agnostic — the callers decide the viewport matrix.
 */

export const VIEWPORTS = {
  desktop: { width: 1920, height: 1080 },
  phone: { width: 390, height: 844 },
}

// A row of grid data. The grid's loading and empty messages are a body row too, and the Findings
// grid shows "Loading findings…" until the cluster list arrives: a click there goes nowhere
// (issue 786). In the gate (the smoke, ci-smoke.mjs, and the e2e specs), a wait for or click on
// a grid row that could be such a message uses this, never `.tbl tbody tr`.
export const DATA_ROW = '.tbl tbody tr:not(.p-datatable-empty-message)'

// Row-click detail routes are walked by clickDetail(), not listed here (their URLs carry
// corpus-specific ids). Order matters: cheap shell screens first, data grids last so a
// dead API fails on a named data route, not a generic one.
export const ROUTES = [
  { name: 'overview', path: '/overview', ready: '.sev-band, .screen' },
  { name: 'clusters', path: '/clusters', ready: '.screen' },
  // ready = the card grid, the empty state, or the load-error line — never just the shell
  { name: 'views', path: '/views', ready: '.view-card, .empty-state, .load-error' },
  { name: 'scanner-status', path: '/scanner-status', ready: '.screen' },
  { name: 'audit', path: '/audit', ready: '.screen' },
  { name: 'contributors', path: '/contributors', ready: '.screen' },
  { name: 'approvals', path: '/approvals', ready: '.screen' },
  // /settings redirects to scan-scope (§13 order); a .set-row exists only once its data loaded
  // ready = the rail's grouped index buttons or its declared failure line — data, not shell
  { name: 'inspect', path: '/inspect', ready: '.idx, .load-error' },
  { name: 'settings', path: '/settings', ready: '.set-row' },
  // per-panel walks: tokens/users prove DATA (the smoke seed mints a token; admin always exists)
  { name: 'settings-scanning', path: '/settings/scanning', ready: '.set-row' },
  { name: 'settings-sla', path: '/settings/sla', ready: '.set-row' },
  { name: 'settings-tokens', path: '/settings/tokens', ready: DATA_ROW },
  { name: 'settings-ai-agents', path: '/settings/ai-agents', ready: '.set-row' },
  { name: 'settings-users', path: '/settings/users', ready: DATA_ROW },
  // data panel: the family ledger renders only after GET /settings/data resolved
  { name: 'settings-data', path: '/settings/data-opensearch', ready: '.fam-row' },
  { name: 'settings-cluster', path: '/settings/cluster', ready: '.set-row' },
  { name: 'findings', path: '/findings', ready: DATA_ROW },
  { name: 'images', path: '/images', ready: DATA_ROW },
  // static content: the last section's card is the page fully rendered
  { name: 'guide', path: '/guide', ready: '#glossary .gl-row' },
  // the install rows, or the visible error when /meta failed
  { name: 'about', path: '/about', ready: '.stack-install .stack-row, .stack-error' },
]

/** Log in through the real form (never an API shortcut — the form IS part of the smoke). */
export async function login(page, base, user, pass) {
  await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
  await page.fill('#username', user)
  await page.fill('#password', pass)
  await page.click('button[type=submit]')
  await page.waitForURL('**/overview', { timeout: 15_000 })
  await page.waitForLoadState('networkidle')
}

/** Attach console/pageerror collectors. Returns the (live) issues array. */
export function collectPageIssues(page, issues = []) {
  page.on('console', (m) => {
    if (m.type() === 'error') issues.push(`[console.error] ${m.text()}`)
  })
  page.on('pageerror', (e) => issues.push(`[pageerror] ${e.message}`))
  return issues
}

/**
 * Layout sanity, evaluated in-page:
 *  - the document itself must not scroll horizontally;
 *  - no element may extend past the viewport's right edge unless an ancestor scrolls it;
 *  - sibling block/flex/grid boxes must not overlap (>2px both axes) — misaligned cards
 *    and collapsed grids show up here. Chips/badges (inline, absolute) are exempt by design.
 */
export async function layoutIssues(page, routeName) {
  const found = await page.evaluate(() => {
    const out = []
    const doc = document.documentElement
    const vw = doc.clientWidth
    if (doc.scrollWidth > vw + 1) out.push(`page scrolls horizontally (${doc.scrollWidth}px > ${vw}px)`)

    const inScroller = (el) => {
      for (let p = el.parentElement; p; p = p.parentElement) {
        const s = getComputedStyle(p)
        if (/(auto|scroll)/.test(s.overflowX)) return true
      }
      return false
    }
    const sig = (el) =>
      `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`

    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect()
      if (r.width <= 0 || r.height <= 0) continue
      const s = getComputedStyle(el)
      if (s.position === 'fixed') continue
      if (r.right > vw + 1 && !inScroller(el)) out.push(`off-viewport right: ${sig(el)} (right=${Math.round(r.right)})`)
    }

    // sibling-overlap: only in-flow block-level boxes (the card/section grammar)
    const blocky = new Set(['block', 'flex', 'grid', 'table'])
    for (const parent of document.querySelectorAll('main *')) {
      const kids = [...parent.children].filter((el) => {
        const s = getComputedStyle(el)
        const r = el.getBoundingClientRect()
        return (
          r.width > 0 && r.height > 0 && s.position === 'static' && blocky.has(s.display) &&
          s.float === 'none' && parseFloat(s.marginTop) >= 0 && parseFloat(s.marginLeft) >= 0
        )
      })
      for (let i = 0; i < kids.length; i++) {
        for (let j = i + 1; j < kids.length; j++) {
          const a = kids[i].getBoundingClientRect()
          const b = kids[j].getBoundingClientRect()
          const x = Math.min(a.right, b.right) - Math.max(a.left, b.left)
          const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
          if (x > 2 && y > 2) out.push(`overlap: ${sig(kids[i])} × ${sig(kids[j])} (${Math.round(x)}×${Math.round(y)}px)`)
        }
      }
    }
    return [...new Set(out)]
  })
  return found.map((f) => `[layout ${routeName}] ${f}`)
}

/**
 * Text and control layout (issue 652), evaluated in-page. The authoring rig runs it at the 1024
 * floor, 1366 and 1920; CI's smoke keeps `layoutIssues` only. Fails on:
 *  - text that overflows its box without a deliberate ellipsis (`text-overflow: ellipsis` on a
 *    clipping box) and outside any scroller;
 *  - an interactive control that sticks out of its nearest bordered box (a card, the rail);
 *  - two interactive controls that overlap (>2px both axes), neither inside the other;
 *  - a button whose label wraps onto a second line.
 * Floating layers (absolute/fixed: menus, popovers, tooltips) are their own boxes and skipped.
 */
export async function textLayoutIssues(page, routeName) {
  const found = await page.evaluate(() => {
    const out = []
    const sig = (el) =>
      `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`
    const visible = (el) => {
      const r = el.getBoundingClientRect()
      return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'
    }
    const floating = (el) => {
      for (let p = el; p && p !== document.body; p = p.parentElement) {
        const pos = getComputedStyle(p).position
        if (pos === 'absolute' || pos === 'fixed') return true
      }
      return false
    }
    const inScroller = (el) => {
      for (let p = el; p; p = p.parentElement) {
        if (/(auto|scroll)/.test(getComputedStyle(p).overflowX)) return true
      }
      return false
    }
    const ownText = (el) =>
      [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim() !== '')

    // 1. overflowing text with no ellipsis
    for (const el of document.querySelectorAll('main *, header *')) {
      if (!ownText(el) || !visible(el) || floating(el) || inScroller(el)) continue
      if (el.scrollWidth <= el.clientWidth + 1 || el.clientWidth === 0) continue
      const s = getComputedStyle(el)
      if (s.display === 'inline') continue
      const ellipsis = s.textOverflow === 'ellipsis' && s.overflowX !== 'visible'
      if (!ellipsis) out.push(`text overflows its box: ${sig(el)} (${el.scrollWidth}px in ${el.clientWidth}px)`)
    }

    const controls = [...document.querySelectorAll('main button, main a[href], main [role=button], main input, main select, header button, header a[href]')]
      .filter((el) => visible(el) && !floating(el))

    // 2. a control outside its nearest bordered box
    for (const el of controls) {
      if (inScroller(el.parentElement ?? el)) continue
      let box = el.parentElement
      while (box && box !== document.body) {
        const s = getComputedStyle(box)
        if (parseFloat(s.borderLeftWidth) > 0 && parseFloat(s.borderRightWidth) > 0) break
        box = box.parentElement
      }
      if (!box || box === document.body) continue
      const a = el.getBoundingClientRect()
      const b = box.getBoundingClientRect()
      if (a.right > b.right + 1 || a.left < b.left - 1) {
        out.push(`control outside its box: ${sig(el)} in ${sig(box)} (${Math.round(a.left)}–${Math.round(a.right)} vs ${Math.round(b.left)}–${Math.round(b.right)})`)
      }
    }

    // 3. overlapping controls
    for (let i = 0; i < controls.length; i++) {
      for (let j = i + 1; j < controls.length; j++) {
        const [p, q] = [controls[i], controls[j]]
        if (p.contains(q) || q.contains(p)) continue
        const a = p.getBoundingClientRect()
        const b = q.getBoundingClientRect()
        const x = Math.min(a.right, b.right) - Math.max(a.left, b.left)
        const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
        if (x > 2 && y > 2) out.push(`controls overlap: ${sig(p)} × ${sig(q)} (${Math.round(x)}×${Math.round(y)}px)`)
      }
    }

    // 4. a button label that wraps (each text node's line boxes share one top). A button whose
    //    text sits in rows stacked one above another (a stat cell: label, number, caption) is a
    //    card, not a label: skipped.
    const stacked = (el) => {
      const boxes = [...el.querySelectorAll('*')].filter(ownText).map((d) => d.getBoundingClientRect())
      return boxes.some((a) => boxes.some((b) => b.top >= a.bottom - 1))
    }
    for (const el of controls) {
      if (el.tagName !== 'BUTTON' && el.getAttribute('role') !== 'button') continue
      if (stacked(el)) continue
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!n.textContent.trim()) continue
        const range = document.createRange()
        range.selectNodeContents(n)
        const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)))
        if (tops.size > 1) {
          out.push(`button label wraps: ${sig(el)} "${n.textContent.trim().slice(0, 40)}"`)
          break
        }
      }
    }
    return [...new Set(out)]
  })
  return found.map((f) => `[text-layout ${routeName}] ${f}`)
}

/** Walk every route: navigate, wait for readiness, run the layout asserts. */
export async function walkRoutes(page, base, issues, { onRoute } = {}) {
  for (const route of ROUTES) {
    await page.goto(`${base}${route.path}`)
    const ready = await page.waitForSelector(route.ready, { timeout: 15_000 }).catch(() => null)
    if (!ready) {
      issues.push(`[route ${route.name}] never became ready (${route.ready})`)
      continue
    }
    await page.waitForLoadState('networkidle')
    issues.push(...(await layoutIssues(page, route.name)))
    if (onRoute) await onRoute(route, page)
    // brief settle: back-to-back navigation opens search cursors faster than the
    // per-principal PIT budget frees itself (A-m12 429s) — no human hops routes this fast
    await page.waitForTimeout(250)
  }
}

/** Row-click into a detail screen and sanity-check it. Returns false if no rows. */
export async function clickDetail(page, base, listPath, detailReady, name, issues, { onRoute } = {}) {
  await page.goto(`${base}${listPath}`)
  // locator (not an element handle): the lazy grid re-renders rows on fetch, detaching handles
  const cell = page.locator(`${DATA_ROW} td`).first()
  const clicked = await cell
    .click({ timeout: 15_000 })
    .then(() => true)
    .catch(() => false)
  if (!clicked) {
    issues.push(`[route ${name}] no rows to click on ${listPath}`)
    return false
  }
  const ready = await page.waitForSelector(detailReady, { timeout: 15_000 }).catch(() => null)
  if (!ready) {
    issues.push(`[route ${name}] row click did not reach a detail screen (${detailReady}) — at ${page.url()}`)
    return false
  }
  await page.waitForLoadState('networkidle')
  issues.push(...(await layoutIssues(page, name)))
  if (onRoute) await onRoute({ name, path: page.url() }, page)
  return true
}
