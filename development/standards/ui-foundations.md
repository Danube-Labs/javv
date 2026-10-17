# UI foundations

How JAVV keeps **one** visual system instead of a thousand ad-hoc fonts, sizes, and hex codes. The design
*substance* is already strong (palette, type scale, semantic-color discipline) - this doc makes it
**binding and enforced**, not just reference.

> Owned by **M9a** (creates the tokens + wires the linter); every later FE bolt (M9b-f) consumes the tokens,
> never raw values.

## Single source of truth = tokens
- **`frontend/src/styles/tokens.css` + `tokens.ts` (M9a) are the binding source.** Components reference
  **tokens only** - never a raw `#hex`, never a literal `font-family`, never an arbitrary `font-size`.
- **Provenance:** the *values* come from [`.deprecated/docs/engineering/UI-GUIDELINES.md`](../../.deprecated/docs/engineering/UI-GUIDELINES.md)
  (the original v1 UI target, archived) + [`handoff/v4/docs/DESIGN_SYSTEM.md`](../../handoff/v4/docs/DESIGN_SYSTEM.md)
  (reference fidelity). They are **promoted into the tokens once**; this doc does **not** re-host hex values
  (re-hosting drifts - point, don't copy). There is one light theme with dark-slate chrome; a dark
  theme is not part of the contract (`tokens.css` says where one would go).
- PrimeVue is themed **through** the tokens (theme bridge), so component chrome and custom CSS share one scale.

## Typography - two families, fixed scale
- **Hanken Grotesk** = all UI text/headings/body (operator A/B ruling 2026-07-09, replacing Space
  Grotesk). **Spline Sans Mono** = code-like data (CVE IDs, versions, namespaces, image refs,
  counts, timestamps, IDs; operator ruling 2026-10-12 on a built specimen, replacing Space Mono).
  Both are served by the app itself (`src/styles/fonts.css`), never from a font host. **No third family. No ad-hoc sizes** - use the type-scale tokens (page `h1`,
  card title, body, KPI number, table header, mono data cell, …).

## Contrast - AA is the floor (ruled 2026-07-09)
- Every piece of **text** meets WCAG AA (≥4.5:1) on its surface: `--soft` is the darkest-allowed
  "quiet" text (AA on all light surfaces); `--muted` is **decorative/disabled only** (dashes, gauge
  fills) and must never color words or numbers. Dark-chrome text uses the AA-checked `--side-*`
  ramp. Teal as text = `--teal-text`, never `--teal`.
- Ruled exceptions (brand contract, documented in `frontend/DESIGN.md` §9): white-on-coral
  action/selected chips and the dense mono micro-scale.

## Color - pick from the right bucket (semantic, not decorative)
Three **separate** buckets; using one where another belongs is a bug:
1. **Brand** (coral / amber / teal) - chrome, accents, info only. **Coral/amber must NEVER encode severity;
   teal is info-only.**
2. **Severity** (`critical/high/medium/low/negligible/unknown` - the six D46 full-word canonicals;
   `negligible` renders muted, never red, per the A-1 ruling) - **DATA ONLY**, from the severity token
   map (`fg/bg/line/solid` + chart series). Never brand chrome.
3. **Status / semantic** - finding state (open/stale/acknowledged/resolved), **health (ok/degraded/down -
   the same ramp the OpenSearch-degraded banner uses, see [`observability.md`](observability.md))**, KEV tag,
   scanner tags (Trivy/Grype). Status has hues of its own: a status colour is never a copy of a severity
   colour (the tokens test fails one).

## Enforcement (the actual guardrail)
- **stylelint** in the frontend CI job (the `Frontend` gate in `.github/workflows/ci.yml`), with rules that
  **fail on raw `#hex`/`rgb()`, non-token `font-family`, and arbitrary `font-size`** in components - hard-coded
  values must come from a token. This is what stops the "10 000 style variants" drift.
- Severity/status colors are only ever read from the token map (lint/grep guard against literal severity hex).
- **Style rules test (M9a):** a pinned test fails CI when a component **adds** a hand-rolled severity/status
  color that bypasses the token map/badge helpers; the recorded baseline may only shrink, never grow.
  stylelint catches raw hex/fonts - the style rules test catches *semantic* bypasses (a literal red where the
  severity token belongs). **Extended (post-M9b):** it also fails any rule pairing `--X-fg` text with its
  own `--X-bg` tint - the "never same-hue text on its own tint" ruling is machine-enforced (chips are the
  listed exception).
- **Tested:** a component using a raw hex or a non-token font fails lint; the severity token map round-trips
  to the six buckets.
- **Agent-facing condensation:** `frontend/DESIGN.md` (an M9a deliverable) is the one file a session reads
  before writing FE code - token tables, do's/don'ts, quick reference, example patterns. It
  *derives from* the tokens and this doc; on disagreement, `tokens.css` + this doc win.

## Visual feedback — a MUST (operator ruling, 2026-07-10)

Every interactive element answers the pointer BEFORE it is clicked: hover wash
(`--control-hover-bg`) + border shift, pressed state (`--control-active-bg`), focus-visible
ring, and (for rows) the hover wash + link-styled target cell. A border-color shift alone is
invisible and does not count. The global rule lives in `frontend/src/styles/base.css`; scoped
styles may add to it, never remove it. Binding detail: `frontend/DESIGN.md` §2.

**Structural home (post-M9b):** the contract is baked into the UI kit
(`frontend/src/components/ui/` — UiButton, UiSegControl, UiToggleGroup, UiField, UiDropdown, ModalShell,
UiLoadingBar).
Buttons, segmented bars, labeled fields, dropdown behavior, and modals are USED from the kit,
never re-rolled per component — writing their raw markup/CSS again is a review failure
(`frontend/DESIGN.md` §5 table).

## Motion — one scale, applied through the kit (post-M9b, #319)

Open/close motion is part of the same kit contract: durations/curves come from the motion
tokens (`--ease-out`, `--dur-quick`, `--dur-panel`), applied via the shared `t-pop` / `t-fade`
/ `t-modal` Transition classes in `base.css` — transform/opacity only, never layout (the
sidebar collapse rail and the header card stretch, issue 902, are the two ruled exceptions),
everything collapses under
`prefers-reduced-motion`. UiDropdown and ModalShell carry the motion, so every menu/dialog
built through the kit animates by default; in-flow appearances (banners) use `t-fade`.
Page entry comes from the app shell (`.page-motion`): each new block of a page fades in, and
the outer blocks rise 6px. A view adds no entry motion of its own.
Feedback text (error/success notes) is deliberately INSTANT — never animate urgency.
After a click, the top bar's loading bar shows when the work takes more than 250 ms
(issue 902). A view does not add its own sign for a page change or an API request.
Binding detail: `frontend/DESIGN.md` §5 "Motion".

## Audit rules (ruled 2026-07-11, #343) — every screen, present and future

1. **Accurate errors.** A 4xx caused by user input names the input, never blames the backend.
   Every status the FE can receive (401 / 410 / 422 / 429 / 5xx) maps to distinct copy — one
   generic "check the backend connection" for everything is a bug. Findings' mapping lives in
   `src/findings/failureCopy.ts` (unit-tested); new grids follow it.
2. **Contract guards.** Any constraint the API enforces (min-length, numeric ranges) gets a
   matching guard at the input AND in the query builder (which omits, never emits, invalid
   values) — a keystroke or a pasted URL must never produce a known-invalid request. Pinned by
   builder specs.
3. **Feedback within 200ms.** Every user-triggered action (export, apply, bulk, rewind) shows
   visible feedback — toast, spinner, or state change. Silent success is indistinguishable
   from silent failure.
4. **Restorable state.** Any state that changes what the data MEANS (time range `t`/`win`,
   filters, cluster) rides the URL and survives reload — `src/system/globalUrl.ts` +
   `makeFiltersStore.toQuery/fromQuery`. Screens that own their query rewrite only their own keys:
   `router.replace({ query: { ...foreignQuery(route.query, OWN_KEYS), ...q } })`, so the global
   range, the cluster and any key the screen doesn't know about are kept.
5. **Semantics surface.** Every data-table screen carries the D28 line ("the table shows the
   state at the END of this range") — the `IngestLens` provides it; a screen that can't host
   the lens states it another visible way.
6. **Silence is a bug.** No store fetch may fail without either a visible state (alert/banner)
   or a health-store mark. `if (ok) …` with no else is a review blocker.
7. **Standing gates.** The Playwright zero-console-error walk over every route and the
   measured-parity checks (getBoundingClientRect against the findings reference) run as part
   of any UI-touching review.
