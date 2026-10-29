---
paths:
  - "frontend/src/**/*.vue"
  - "frontend/src/**/*.ts"
  - "frontend/src/**/*.css"
  - "frontend/DESIGN.md"
---

# UI: the settled choices (binding — `frontend/DESIGN.md` is the contract)

Loaded only when you touch frontend source. `frontend/DESIGN.md` remains the contract;
this is the always-check-first digest of it.

Every line here was ruled on once and cost a rebuild to learn. Re-deciding any of them needs a live
operator ruling on a **built specimen** (DESIGN.md §8.5), not an argument in a PR.

**Where the grammar comes from — three sources, in this order**
1. **The prototype** (`handoff/v4/` jsx + `handoff/docs/SCREENS.md`) is the reference point for a
   screen's composition. Build with it open; a screen's grammar is the prototype's (§8). It is a
   *reference point, not a 1:1 contract* — deviate deliberately, not by forgetting to look.
2. **[ui.nuxt.com](https://ui.nuxt.com)** and **[framework7.io](https://framework7.io)** — the two
   design references, used the same way: borrow **composition grammar** (how a panel, a form row, a
   command palette is assembled) *and* **transition/animation style**, then re-express both in JAVV
   tokens. **Never the library itself**, never its colors or type. Framework7 is the stronger source
   for motion — press feedback, sheet/slideover entrances, the feel of a transition — which is
   exactly where a screen most often feels unfinished. Land what you borrow on the **existing** motion
   layer rather than a new curve: `t-pop` = floating panels (dropdowns/popovers), fade + 4px rise,
   quick both ways; `t-fade` = banners and in-flow appearances, crossfade only, **never animate
   height**. Page entry is in the shell, not in the views: `.page-motion` on the main area fades
   each new block in and raises the outer ones 6px (issue 902), so a view adds no entry motion
   of its own. DESIGN.md §9 permits two layout animations: the sidebar collapse and the
   header card stretch (`composables/useStretchWidth.ts`). Skeletons are shared: the pulse is `.skel` + `@keyframes skel-shimmer` in base.css,
   composed by `UiSkeleton` — a view that grows its own shimmer fails the style rules test.
   The sign that the app works after a click is the top bar's `UiLoadingBar`, fed by
   `system/pendingWork.ts` (issue 902): an API request or a page change counts by itself, so a
   view adds no loading sign of its own for it.
3. **`node .claude/skills/impeccable/scripts/detect.mjs <changed files>`** — the VENDORED detector,
   pinned with the repo. **Never `npx impeccable detect`**: unpinned, and a stale cached version
   once invented a finding that nearly bought §9 a permanent exception row (issue 484). Plus the
   `.claude/skills/impeccable` skill for critique/typography/layout. §9 of DESIGN.md lists the **ruled
   exceptions** — those are settled; don't relitigate them each pass.

**Color — pick from the right bucket; the wrong bucket is a bug (DESIGN.md §2)**
- **Brand** (`--coral --amber --teal --slate*`) = chrome, active nav, focus, links. The primary
  button is **slate**, not coral (issue 1004, 2026-10-29). Coral and amber must **never** encode
  severity. Teal is info only.
- **Severity** (`--sev-<level>-{fg,bg,line,solid}`) = **data only**, six D46 canonicals
  (`critical high medium low negligible unknown`). `negligible` is muted, **never red**. From script
  use `SEV_COLOR` / `CHART_SEV` from `@/styles/tokens`, never a literal.
  `-bg`/`-line` are **derived** from that level's `-solid` (10%/30% flattened) — never hand-picked pastels.
- **Status** (`--state-* --health-* --kev-* --scanner-{trivy,grype}-* --scope-*`) = workflow state,
  health ramp, KEV, scanner tags. State pills read **quieter** than severity by design.
- No raw hex in components. AA contrast is the floor, not a target.

**Type — two families, fixed scale (§3)**
**Hanken Grotesk** (`--font-ui`) for all UI text; **Spline Sans Mono** (`--font-mono`) for code-like data:
CVE ids, versions, namespaces, image refs, counts, timestamps, table headers, ids. No third family,
no ad-hoc sizes — use the scale tokens (`--text-page-title`, `--text-card-title`, `--text-body`, …).
Both are served by the app (`src/styles/fonts.css`, Fontsource); a font host link fails `index-html.spec.ts`.

**Reuse before building — the kit already solves most of it**
`components/ui/` (UiButton · UiField · UiDropdown · UiSegControl · UiToggleGroup · UiDateTime · ModalShell ·
SlideoverShell · PopoverShell · ToastStack · EmptyState · UiSkeleton · UiLoadingBar · AppIcon · SectionNav · RowLink), plus `components/chips/`, the M9a filter module,
the shared table skin + GridPager, and the stat-band skin (`.stat-band`/`.stat-cell` in base.css,
composed by `components/overview/OverviewStatBands.vue` — it is a skin, not a kit component).
A **text box or dropdown** is `SettingsInput`, `UiDateTime`, or the base.css skin `.set-input` /
`.set-select` (issue 1050). A window never styles a box of its own, and neither do the form
fields outside windows (issue 1053). A **search box** is the base.css skin `.search-box`
(`.facet-search` is the same box as the rail card). A **window footer** is a `ghost` Cancel,
Close or Done and a `primary` main button (issue 1053, D2 option B).
Paging behind GridPager is two composables, never a hand-written stack: `useCursorPager`
(server `next_cursor` paging — the findings/audit stores, ImageFindingsPanel, IngestFailuresTable)
and `usePagedSlice` (a bounded row set the client already holds — saved views, a finding's
Activity/Affected cards, DecisionsCard).
Backend: `query/paging.py` + the bulk helpers.
**Grep first.** A raw parallel implementation of a solved surface fails review.
**Screen head controls** take `head` (`UiButton`, `UiSegControl`): one 30px height, the darker
line and the 1px `--control-edge` with no blur (issue 1039, option D). Never a soft blurred
shadow, and never a `:deep` restyle in the view. **Role ids** show through `roleLabel()`
(`@/lib/roleLabel`): `security_lead` reads "security lead", and the id stays the value.
**Window heads** are the slate band of the table heads, owned by `ModalShell` (issue 1049). A
window never restyles its head, and the ✕ takes the sidebar's on-slate control colors.

**Building a NEW agg-backed panel (chart, board, histogram, leaderboard)** — it is a *lens*, and
lenses are built self-contained: `(cluster_id, T, params)` in, owns its own aggregation fetch, its
own loading/empty/error states, no reliance on host state. The dashboards (issue 440) put the
panels of `src/dashboards/catalog.ts` on that contract, so a host-fed panel cannot go on a dashboard.
Full ruling incl. when host-fed is still right: **DESIGN.md §10**. Don't convert a host-fed panel
in passing.

**Non-negotiable behaviours**
- **Visual feedback is a MUST**: every interactive element ships hover (**wash + border**, never
  border-only), pressed, and focus states. Rows get the hover wash too.
- Every screen needs its **loading, empty and error** states — `EmptyState` exists for this.
- **Server-side everything**: a count or a page is an OpenSearch aggregation, never client math.
- After any design pass on a view, **`wc -l` it**. Passes accrete markup; crossing ~500 lines means
  extracting self-contained panels in the **same PR** (DataOpenSearchView hit 721 before anyone looked).

**Rendering + charts (was mis-scoped into the backend rule; it belongs here)**
- Lazy **server-side** `DataTable` — never client-side paging over a full result set.
- `shallowRef` + `markRaw` for ECharts options/instances; **manual** ECharts module imports
  (no full-bundle import).
- Test the option-builder and the emitted query params as **pure units**, not through the DOM.
