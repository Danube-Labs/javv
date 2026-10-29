# javv Design System — agent contract

Read this before writing or modifying any frontend code. It condenses the binding sources —
`src/styles/tokens.css` (values) · `development/standards/ui-foundations.md` (rules) ·
`handoff/docs/SCREENS.md` (screens) — into the one file a session needs. On any
disagreement, tokens.css + ui-foundations win.

Enforced, not advisory: **stylelint** fails raw hex/`rgb()`/non-token fonts/ad-hoc font-sizes in
components; the **style rules test** (`src/__tests__/style-rules.spec.ts`) fails a color literal
anywhere else (inline styles, script, chart options) outside `styles/tokens.*` + `theme/preset.ts`,
and fails any rule pairing `--X-fg` text with its own `--X-bg` tint (the "green on green" ruling —
chips are the listed exception).

## 1. Visual theme

Warm, editorial, data-dense. Warm-paper background (`--bg`) with white cards, **dark-slate
chrome** (sidebar/brand marks on `#16232F`), coral as the single brand accent. Single light theme
by contract — no dark mode, no `prefers-color-scheme` styling (the slate sidebar is chrome, not a
theme). High information density: subtle borders and panel tints, almost no decorative shadow.

## 2. Color — pick from the right bucket (wrong bucket = bug)

| Bucket | Tokens | Rule |
|---|---|---|
| **Brand** | `--coral` `--coral-d` `--amber` `--teal` `--slate*` | Chrome, active nav, focus, links. **The primary button is slate (`--slate2`, hover `--slate`), not coral** (operator ruling 2026-10-29 on built specimens, issue 1004). Coral shares the red-orange of critical, KEV and "down". Coral/amber must **never** encode severity. Teal = info only. |
| **Severity** | `--sev-<severity>-{fg,bg,line,solid}` | **DATA ONLY.** Six D46 canonicals: `critical high medium low negligible unknown`. `negligible` is muted, never red (A-1). From script use `SEV_COLOR` / `CHART_SEV` (`@/styles/tokens`). **Chip language A (operator 2026-07-11):** `-bg`/`-line` are DERIVED from the level's `-solid` (10% / 30% flattened on white — never hand-picked pastels); weight ESCALATES: critical renders solid + inner highlight (`--chip-hi`), high the heavy `--sev-high-ring`, tails near-neutral. State pills = soft 9% tint + `--state-*-solid` dot, no ring (workflow reads quieter than severity). Alarms (KEV `--kev-grad`, SLA overdue) carry the ONE depth treatment: `inset 0 1px 0 var(--chip-hi)` + a soft drop (`--chip-crit-drop`/`--kev-drop`). Primary buttons are flat (operator 2026-07-17). **Chart ramp (issue 659):** `CHART_SEV` also steps lighter at every level, critical to unknown, so mix bars and charts keep their bands in grayscale; critical and high stay the full solids. |
| **Status** | `--state-<open\|stale\|ack\|resolved>-*` · `--health-{ok,degraded,down}-*` · `--kev-*` · `--scanner-{trivy,grype}-*` · `--scope-{cluster,scanner,org}` | Finding state pills, health ramp (the same ramp as the degraded banner), KEV tag, scanner tags, settings scope dots/badges (M9e — darkened from the prototype so the white badge label computes AA). **Status has its own hues (operator rulings 2026-10-02 on built specimens, issue 659):** open is rose, acknowledged is indigo; a status token is never a copy of a severity token (`tokens.spec.ts` fails one; `--health-down-fg` is the one listed leftover). **One caution amber:** `--hist-*` (viewing history, picker and banner alike), `--health-degraded-fg/-bg` and `--sla-tight-fg` share one set of values. **Overdue** is `--sla-over-bg`, the KEV maroon, not critical's red. **Lightness carries it too:** the triage bar (`--triage-seg-handled`, `--state-open-solid`, `--triage-seg-ack`, `--state-stale-line`) and the health dots (`--health-ok-dot` / `--health-degraded-dot`) are a lightness step apart, so they read in grayscale. |

### Surfaces & text
```
page bg        var(--bg)          cards        var(--card)
inset/panel    var(--panel)       borders      var(--line)   subtle: var(--line2)
primary text   var(--ink)         secondary    var(--soft)
row hover      var(--row-hover)   dark chrome  var(--slate)
meter track    var(--meter-track) — the unfilled part of ANY bar/gauge, never --line2
save-bar dirty var(--save-dirty-bg) + var(--save-dirty-line)  (M9e unsaved-changes surface)
table head     var(--table-head-bg) + var(--table-head-fg) + dividers var(--table-head-line)
section accent var(--sect-monitor|inventory|audit|insights|configure|help)  (decorative only;
               --sect-help aliases --side-label: neutral by ruling 2026-09-29, issue 341)
```
`--soft` is the CONTRAST FLOOR for text — AA (≥4.5:1) on every light surface. `--muted` is
decorative/disabled only (dashes, gauge fills, placeholder glyphs): it fails AA and must never
color words or numbers.

**VISUAL FEEDBACK IS A MUST (operator, 2026-07-10 — non-negotiable on every surface):** every
interactive element answers the pointer — hover wash + border shift (`--control-hover-bg` /
`--control-hover-line`), pressed state, row hover + link-styled target cells, focus ring. If a
user can click it, they must be able to SEE that before they click. No control ships without its
hover/pressed/focus states; reviews reject "border-shift-only" or feedback-less controls.

**Text color rules (operator rulings 2026-07-09 — verify ratios by computation, never by eye):**
- **Never same-hue text on its own tint** ("green on green"): prose/sentences on a tinted panel
  or banner are `--ink`; the hue lives in the icon, border, and background only. Chips/tags
  (short bold data labels) keep their hue pair, but every fg is AA-computed against its bg.
- **Interactive text is `--ink`** (facet rows, menu items, buttons, control labels) — `--soft`
  is for genuinely secondary annotations (counts, pager info, captions).
- **Coral as text = `--coral-text`** (pills, selected states, hover text); `--coral`/`--coral-d`
  are fills only — both fail AA as small text on light surfaces.
- **Times display 24-hour** (`hour12: false` / strict `HH:mm` inputs) — never AM/PM.
- **Solid severity chips are critical-only** (2026-07-09, finding-detail header): white text
  passes AA only on `--sev-critical-solid` (5.9:1) — every other solid fill fails with both
  white and ink. Default to the tinted chip (its pairs are gate-tested); reach for `solid`
  only for critical-grade emphasis. Side-stripe accents (the prototype's 4px `border-left`)
  stay banned — severity on a panel is carried by the chip, not a stripe. The same holds for
  the Settings scope strip: its 3px scope-coloured stripe is gone and the coloured badge carries
  the scope alone (operator ruling on A/B specimens, 2026-10-01, issue 652).

**Interaction & spacing rulings (operator, 2026-07-10 — issue #306):**
- **Arrow cursor everywhere** — never `cursor: pointer` (desktop-app convention: Linear/Notion;
  the hand is a web-document tell). **Sharpened 2026-07-11: no I-beam either** — `base.css`
  rules `* { cursor: default }` app-wide (text and inputs included; text stays selectable),
  ECharts series carry `cursor: 'default'`, and the style rules test fails any `cursor: pointer`
  in src. `not-allowed` on disabled stays (it's feedback — component rules outrank the
  zero-specificity universal).
- **Click affordance = row wash + link-styled TARGET cell**: the row hover wash says "this row
  is interactive"; the identifier cell that navigation anchors on (CVE now; image at M9c) turns
  `--coral-text` + underline on row hover. Transitions ~120ms ease-out with a reduced-motion
  fallback; pressed state = `--line2` wash. **Never dress a cell whose destination doesn't
  exist yet** — a false affordance is worse than a missing one.
  **That identifier is a real link** (`RowLink`, operator ruling on built specimens 2026-10-02,
  issue 674, A of two: A the identifier as a link, B the whole row taking focus): Tab reaches
  it, Enter opens the row, a ctrl or middle click opens a new tab. A row answering the mouse
  only cannot be opened from the keyboard at all; `row-links-guard.spec.ts` fails a clickable
  row with no link.
- **Every interactive control has a VISIBLE hover** (operator, 2026-07-10): the wash
  (`--control-hover-bg`) + border shift together — a border-color shift alone cannot be seen.
  Pressed = `--control-active-bg`. One global rule in `base.css` covers the control classes;
  scoped styles may add but never remove it. Segmented controls carry inner padding + per-option
  radius so selection rings never clip against the container's corners.
- **Every overlay follows one dismiss contract** (audit #311): Escape + outside-click + a
  visible close affordance — all three, on every menu and dialog. Selection state inside any
  overlay = the coral language (`--dd-on-bg` + inset `--coral`), never an ad-hoc scheme.
- **No unbounded panels** (audit #311): any list that can grow with data gets a scroll viewport
  (sticky header) or an explicit cap note naming where the full set lives — the images-affected
  card is the reference; decisions, activity, and the rail's top-32 dims follow it. "Works with
  10 rows" is not shipped until it's been asked "and with 10,000?".
- **1024px design floor** (audit ruling, 2026-07-10): JAVV is a desktop ops dashboard — layouts
  are designed for ≥1024px (clean at 1366+, verified). Below the floor the shell keeps
  `min-width: 1024px` and scrolls as one intact piece; it never crumbles into overlapping
  chrome. A true responsive/mobile pass is an M9f decision, not an accident of flex-wrap.
- **Spacing rhythm on the `--space-*` scale** (8px base, 4px sub-grid): tight WITHIN a
  functional group (`--space-1/2`), generous BETWEEN page bands (`--space-6/8`). Uniform
  spacing everywhere is the "static" feel — page headers breathe, data clusters hold together.

### Sidebar chrome (dark slate — its own text/hover ramp, promoted from the prototype shell)
```
nav text       var(--side-fg)  hover var(--side-fg-hover) on var(--side-on-fg)/(--side-on-bg)
active item    coral bar + coral icon (one accent; ruled 2026-10-02, issue 659)
collapse       var(--side-control-bg) at rest, -hover-bg, -active-bg; icon var(--side-fg)
               (a resting fill so it reads as a button; ruled on specimens 2026-10-02)
group label    var(--side-label)      brand word   var(--side-brand-fg)  credit var(--side-credit)
hover wash     var(--side-hover-bg)   pressed      var(--side-active-bg) footer var(--side-foot-*)
sweep dot      var(--health-ok-dot) + ring var(--sweep-ok-ring)          version var(--side-version)
```
Icons in chrome: `<AppIcon name="…">` — the javv stroke set ported verbatim from the prototype.
Never an icon font / emoji / other icon library in app chrome.

### Filter chrome (promoted from the prototype's filters CSS)
```
facet checkbox   var(--facet-check-line)      pill border   var(--fpill-line)
pill × hover     var(--fpill-x-hover-bg)      add-filter    var(--add-filter-line) / var(--add-filter-hover-bg)
dropdown         shadow var(--dd-shadow)      active item   var(--dd-on-bg)
value actions    chip var(--slate3), mark var(--table-head-fg), exclude var(--val-act-not-fg)
actionable cell  var(--cell-act-wash) + inset var(--cell-act-line)
```
**The chip is dark slate on BOTH surfaces** (issue 349 §2, operator ruling 2026-07-28): beside a
facet value in the rail the chip is its own surface; in a grid cell it rides a floating bar and
goes transparent so the bar is the surface. An earlier split — light cool-blue chip in the rail,
dark bar in the grid — read as two languages for one action. Coral is not available here: with
`--dd-on-bg` it is the **selected** language, so a resting chip looked switched on; it stays for
the ON state alone, as the coral fill (`--coral-text` is tuned for light washes and vanishes on
the chip). Exclusion keeps the ruled red, but as `--val-act-not-fg` — `--fpill-not-op` is the
same red for LIGHT grounds and computes 1.6:1 on slate. Never reach for a `--sev-*` token to
solve that; severity is data-only (§2). The marks are CSS bars on whole-pixel offsets, never
typed `+`/`−` (glyph metrics differ, so the box centres the line box and not the ink) and never
an `AppIcon` addition (the set is ported verbatim and has no `minus`).

**The grid bar hangs off the cell's top-LEFT corner, always upward** (operator rulings
2026-07-28, on built specimens against the running Kibana Discover). Four things are load-bearing
and none is taste:
- **Flush on the corner** (`left: 0`), never inset — Kibana measures `left: 0`, and any inset
  reads as floating near the edge rather than attached to it.
- **Every row overhangs UP, the first one included.** The first-row flip this replaces was built
  on a false premise (that the card would clip it; the real clipping ancestor starts at the
  header's top, so it does not) and it made row 1 **unusable**: the seam then held two bars, and
  reaching for either moved the pointer into the other row.
- **Row 1 inverts** to a light fill with dark marks, because on the slate head band the normal
  `--slate3` fill computes 1.17:1. `tr:first-child` is a proxy for "lands on the header" and is
  exact only because the head travels with the rows — asserted in `tests/e2e/value-actions.spec.ts`,
  not assumed. Every bar also carries a `--chip-hi` hairline so it separates regardless.
- **Square corners, and a GAP rather than a divider between the marks.** This grid cannot put the
  bar on the pixel grid at DPR 1 — the card starts at x.5, rows are 37.5px (`--text-mono-cell`
  12.5px × 1.5 = 18.75), and column edges are percentages — so a radius stair-steps and a 1px
  rule fringes. Whole-pixel rows would not rescue it; the card's own .5 origin survives.
- The reveal **lifts** (the ruled `t-pop` vocabulary, mirrored: it rises out of its cell rather
  than descending from a trigger). It previously had no transition at all.

**The cell hover is a translucent STATE LAYER, not a tint** (operator ruling 2026-07-28, on
built 4/7/11% specimens): a filterable cell washes at `--cell-act-wash` — our own on-surface
slate at low alpha — so the affordance recedes and composites correctly over whatever it lands
on (plain row, hovered row, history tint). This follows what the major systems specify: eBay
adds a semi-transparent state layer at +4% per state and explicitly uses **no complementary
colour** for hover; Material and Spectrum use transparency (Carbon and Primer buy solid shades
with many more variables). A solid cool blue was built first and rejected — an opaque patch on
warm paper is a colour *change*, and it shouted.
The filter module itself (`FacetRail`/`FilterBar` + `filters/fields.config.ts` +
`buildFilterQuery`) is M9a-owned — screens import it and pass their own `fields` config,
never re-implement it.

## 3. Typography — two families, fixed scale

**Hanken Grotesk** (`var(--font-ui)`, operator A/B ruling 2026-07-09) = all UI text.
**Spline Sans Mono** (`var(--font-mono)`, operator ruling 2026-10-12 on a built specimen against
Space Mono, Red Hat Mono, Azeret Mono and JetBrains Mono, issue 818) =
code-like data: CVE IDs, versions, namespaces, image refs, counts, timestamps, table headers,
IDs. No third family, no ad-hoc sizes — the scale tokens:

```
--text-page-title 23px/600   --text-card-title 14px/600   --text-body 13px (base)
--text-kpi 34px/600          --text-detail-mono 26px mono/700
--text-table-header 10.5px mono UPPERCASE   --text-facet-label 10px mono/700 UPPERCASE
--text-sm 11px               --text-mono-cell 12.5px mono
--text-brand-word 21px       --text-nav-item 13.5px       --text-sweep-strong 11.5px
--text-control 12px (facet rows, pills, add-filter)       --text-facet-count 10.5px mono
--text-dd-item 12.5px        --text-dd-head 9.5px mono UPPERCASE
--text-quiet-action 11.5px (clear-all/clear-field text buttons)
```

**Heading level follows the page's outline, not the look.** A page has one `h1`. A card or strip
title that sits straight under it is an `h2`, styled by its own class (`.card-head h2` sets
`--text-card-title`); a title nested inside such a section is an `h3`. Never pick the tag for
its default size. `tests/e2e/headings.spec.ts` walks every screen and fails on a skipped level
(issue 681).

**The app serves its own fonts** (issue 818). An outside font stylesheet blocks the first paint, and
behind a firewall that drops outside traffic it held the sign-in page blank for 21.8 s. The faces
ship as Fontsource packages, declared in `src/styles/fonts.css`: latin and latin-ext only, each
face with its `unicode-range` (without one, the later subset shadows the earlier), UI 400 to 700,
mono 400 and 700. Spline Sans Mono is close to Space Mono's width (0.600 em digits against
0.612 em, about 2% narrower), so mono cells truncate no sooner than before. `index-html.spec.ts` fails a link to another origin
or a token family without its faces; `tests/e2e/fonts-offline.spec.ts` loads the sign-in page with
every outside host unanswered. Neither face is on the vendored detector's overused-font list, so
§9 carries no font row.

## 4. Layout & density

- Sidebar `var(--sidebar-w)` (226px, slate) collapsible to `var(--sidebar-w-rail)` (64px);
  facet rail `var(--facet-rail-w)` (218px); section menu `var(--section-nav-w)` (198px,
  `SectionNav`: Settings' sub-pages and the Guide's sections).
- Motion: `var(--ease-out)` with `var(--dur-quick)` (120ms) / `var(--dur-panel)` (200ms) —
  the only durations/curves (see §5 "Motion").
- Content: max `var(--screen-max-w)` (1380px) centered, padding `var(--content-pad)`; grid gap `var(--grid-gap)`.
  **Data-dense table screens opt out via route `meta: { wide: true }`** (full viewport width —
  operator ruling 2026-07-09: an internal table scrollbar beside dead margin is worse than a
  wide table). Every screen outside settings carries it — Overview included (operator 2026-07-16,
  superseding the earlier "not dashboards" clause). Settings is the narrow exception, and
  `route-width.spec.ts` fails any new screen that forgets the flag.
- Radius: cards `var(--r)` (12px), controls `var(--r-sm)` (8px), chips `var(--r-chip)` (6px), pills/avatars full.
- Shadow: `var(--shadow)` on cards — nothing heavier.
- Tables: compact density default (~7px row padding); **one head register everywhere** —
  mono uppercase parchment on the solid slate band (`--table-head-bg`/`--table-head-fg`,
  operator B2 ruling 2026-07-16; supersedes both the `--panel` head and the short-lived
  settings "quiet sans head" — `tbl-quiet` is density only). On-band column dividers use
  `--table-head-line`, never the beige hairlines.
- **A table card never clips its columns** (issue 652). A hand-built `.tbl` card whose
  columns can outgrow it at the 1024 floor opts into `.tbl-scroll-pin` (base.css): the table
  scrolls sideways inside the card and its first, identity column stays pinned (All clusters,
  Approvals). Put it on the card, or on a wrapper around the table alone when the card also
  holds a pager that must stay put (Approvals). `overflow: hidden` clipping the table is the bug
  it replaces. Once the table is scrolled, a 1px line marks the pinned column's edge so the
  columns sliding under it don't read as part of it; at rest, or when the table fits, there is no
  line (operator ruling 2026-10-01: CSS only, so browsers without scroll timelines show none).
- Desktop-first. The shared breakpoint is ~1100 to 1120px (KPI strips 2-up, grids stack, facet
  rail stacks above the table).
- **A component may add its own breakpoint** (operator ruling 2026-10-01) when its content stops
  fitting at a width the shared one doesn't cover. It lives in that component's scoped styles, at
  the width measured where the content breaks, with a comment saying what stops fitting. Today:
  1180px (finding detail), 1280px (repair action rows) and 1340px (inspector facts).

## 5. Interaction

Transitions short and functional (`.12–.15s`), no decorative animation. Row hover tints
`var(--row-hover)`; clickable cards lift 1px + coral border. Focus-visible = `var(--focus-ring)`
(2px coral, 1px offset) on every interactive element. Dropdowns close on outside-click and Esc.
**Clickable cards (issue 1004, operator rulings 2026-10-29):** the card keeps its white fill on
hover, so the hover wash of a button in the card always shows. A beige card hover gave the card
and its button one color. The whole card is the link. Its title is a `RowLink`, and the `::after`
of the link covers the card. The controls in the card sit above that layer (`SavedCard.vue`).
**At-rest clickability (operator ruling 2026-07-10):** a cell/row that NAVIGATES carries a soft
trailing chevron at rest (`--dash-muted` → `--coral-text` with the hover wash) and its
identifier takes the link treatment on hover (coral + underline, the grid's `cve-link`
convention) — hover-only affordance is not discoverable.
**Cursor (operator ruling, re-affirmed 2026-07-11):** the SYSTEM DEFAULT arrow everywhere —
never `pointer`, never the I-beam over clickable text (`cursor: default` on clickable
rows/cells; text stays selectable). Affordance comes from the chevron + wash + link treatment,
never the cursor (Linear-style desktop-app convention). **One ruled exception (operator
2026-07-11, task 92): DRAG surfaces show `grab`/`grabbing`** — reorderable table headers and
menu grip rows. Drag is a different verb than click; the arrow there hid a real affordance.
`pointer` stays banned (enforced by the style rules test).

**Primary button press (operator ruling 2026-10-11, variant E chosen from five built specimens,
issue 817):** on press the primary button sinks 1px and shrinks to 97%. A slate ring
(`--slate-drop`, coral until issue 1004) shows and fades on release, so a click lands with force. The ring is a
pseudo-element whose opacity animates (transform and opacity only). Under reduced motion nothing
moves; the darker fill and the ring still show the press. Owned by `UiButton`.

**Screen head controls (operator ruling 2026-10-29 on built specimens, issue 1039, option D):**
every control in a screen head is one height, 30px: the buttons and the scanner switch. A primary
or ghost button in a head takes the padding of the `control` variant. The head sits on the page
paper, so a head button has the darker line (`--control-hover-line`) and a 1px edge under it with
no blur (`--control-edge`, as the default button of GitHub's Primer). The soft blurred shadow of
issue 1004 (`--control-lift`) LOST: a soft shadow under every outline control is the default of
shadcn/ui and Tailwind, and it read as a generic template. The kit owns the rule: `head` on
`UiButton` and `UiSegControl`, off by default. A view does not restyle its head controls with
`:deep`. `screen-head-controls.spec.ts` fails a screen head control without `head`. A card's action
slot (for example the Users card on Users and roles) is not a screen head.

### Motion (#319) — the one scale, applied through the kit

Durations/curves come from the motion tokens (`--ease-out`, `--dur-quick` 120ms,
`--dur-panel` 200ms) — never ad-hoc values. Open/close motion is BAKED INTO the kit:
`UiDropdown` animates every menu (`t-pop`: fade + 4px rise, both ways; its `closed` event
fires after the leave for teardown that must not show mid-fade), `ModalShell` animates every
dialog entrance (`t-modal`: backdrop fade + card rise; close is instant — unmount resets consumer
form state). Anything non-kit that appears/disappears in-flow (banners) wraps in
`<Transition name="t-fade">` — crossfade only, NEVER animate height/layout. All `t-*` classes
live in `base.css` and collapse under `prefers-reduced-motion`. Animate `transform`/`opacity`
only; no bounce/elastic; new appear/disappear surfaces use these classes, not new ones.

**Loading bar (operator decision 2026-10-17 on built prototypes, issue 902, D1 B).** After a
click, the user must see that the app works. `UiLoadingBar` sits on the bottom edge of the top bar.
It shows when a page change or an API request is open for more than 250 ms. A bar that shows for
less time looks like a flash (Kibana waits 250 ms, Nuxt 200 ms, GitHub 500 ms). It grows more
slowly near the end, and when the work ends it fills and fades. The background polls (the
notification bell) do not count. The main area has `aria-busy` while the work is open. The code
of the other pages loads while the browser is idle (`router/preload.ts`), so most clicks show the
new page at once.

**Page entry (operator decision 2026-10-17 on built prototypes, issue 902, D2 B).** A page must
not come in all at once. The app shell puts `.page-motion` on its main area. In `base.css`, each
block of the routed page fades in when the page inserts it (`page-fade`), and the outer blocks also
rise 6px (`page-rise`). Both run for `--dur-panel` on `--ease-out`. This covers a page change and
the data that replaces a placeholder, and a view adds no code for it. The selectors have zero
specificity (`:where()`), so a block with its own animation, such as the skeleton pulse, keeps
it. Do not add a page-level `<Transition>` on top: two fades on the same blocks gave an empty
area for about 100 ms in the prototype.

**Header card stretch (operator decision 2026-10-17 on built prototypes, issue 902, D3 A).** A
header card that gets wider when its text grows stretches to the right in `--dur-panel`, and its
text shows from left to right. A card that gets narrower changes at once. Use
`composables/useStretchWidth.ts` on the card (All clusters and Overview do). This animates width,
thus it is a ruled exception in §9.

### The UI kit (`components/ui/`) — use it, never re-roll it

These components each own one contract ONCE (feedback states, dismiss behavior, rhythm). Writing
the raw markup/CSS they encapsulate is a review failure — extend the component instead:

| Component | Owns | Use for |
|---|---|---|
| `UiButton` | hover wash + pressed + focus + disabled + arrow cursor; variants `mini` / `control` / `quiet` / `ghost` / `primary` (+`block`) | every **generic action button**. Domain-grammar controls are their own ruled patterns, not re-rolls: `stat-cell` (the stat-band skin), filter `fpill`/`facet-row`, sidebar `side-item`/`side-collapse`, picker `time-range`/`time-preset`, menu rows inside `UiDropdown` (whose table row below says menu markup stays yours), toggle-chips (`ra-chip`), segmented triage states. Each carries the global `:focus-visible` ring (base.css) + its own hover/pressed states — a NEW one-off button with none of these homes is still a review failure |
| `UiSegControl` | padded seg bar, per-option radius (ring never clipped), `aria-pressed`, the coral selection; a required `label` names the group for a screen reader (issue 1011): the text of the field label above it, or a name only the reader hears when nothing on screen names it | any pick-one bar |
| `UiToggleGroup` | a row of buttons that each turn one value on or off, `aria-pressed`, the coral selection of `UiSegControl`, an optional mono `detail` after the label; the parent owns the list | any pick-several row with few options (the scan scope's owner kinds) |
| `UiField` | mono uppercase micro-label + parenthesized `hint`, 14px band / 6px label gap (`first` zeroes the top) | any labeled control |
| `UiDropdown` | open state + outside-mousedown + document Escape + relative anchor; `trigger`/default slots (menu markup stays yours) | any popover menu |
| `ModalShell` | backdrop + card + head/✕/actions, Escape + outside-click dismiss | every dialog |
| `PopoverShell` | a card with an arrow next to the element it belongs to (`lib/placeBeside.ts`: right, else left, else over its top edge, else above the trigger), no backdrop, head/✕, Escape + outside-mousedown dismiss (a mousedown on its trigger leaves the decision to the trigger), focus in on open and back to the trigger on close, `t-pop` motion | a few settings for one thing on the page that must stay in view while the user changes it (the panel settings of a dashboard) |
| `UiLoadingBar` | the 2px coral loading bar on the bottom edge of its positioned parent. It shows only after 250 ms of work and grows more slowly near the end. When the work ends, it fills and fades. It has `role="progressbar"`. The parent owns `busy` | the top bar's sign that the app works, fed by `system/pendingWork.ts` (open page changes and API requests). Also a panel that needs its own sign |
| `UiSkeleton` | the one loading pulse (`.skel` + `skel-shimmer` in base.css) and its reduced-motion off-switch; `height` is a prop because a skeleton mirrors the panel it stands in for, `label` only when it is its own loading region | every loading placeholder. The style rules test fails any view that grows its own shimmer |
| `AppIcon` | the stroke icon set | every icon |
| `RowLink` | the identifier of a row that opens something, as a real `<a>`: focusable, the focus ring, Enter and plain click hand off to the row's own open handler, modified clicks left to the browser | the identifier cell of every clickable row (the grids take a `rowTo` prop; hand-built rows wrap the cell) |
| `ToastStack` + `useToastStore` | the confirmation channel: `success/error/info` from ANY component/store, auto-dismiss, capped stack, t-toast motion, ink text + hue on the icon | every action outcome the user would otherwise hunt for; inline contextual errors stay inline |
| `UiRoleNote` | the reason next to a control that the user's role cannot use: a key icon (`--hist-fg`) and one short sentence in `--soft`, with an `id` that the disabled control names in `aria-describedby` (a browser shows no tooltip on a disabled button) | every control that a role cannot use and that stays on the screen; the five export controls (issue 243, option A on built pictures) |
| `SectionNav` | a screen's left section menu: the sticky card, icon + label rows, hover wash + border, the coral active row, `aria-current`; a `trail` slot for a row's extra mark | Settings' sub-pages and the Guide's in-page sections; any future screen with a section list |

One layout lives outside the kit folder and is owned once the same way:
`components/system/ErrorPage.vue`, the page for anything that cannot be shown (not found, a page
that failed while it was drawn). A new "this could not be shown" page uses it; SCREENS §18.

## 6. Do / Don't

**Do**
- Reference tokens for every color, font, size, radius, shadow, and layout constant.
- Use `SEV_COLOR` / `CHART_SEV` / `STATE_COLOR` / `SCANNER_COLOR` from `@/styles/tokens` in script.
- Render per-scanner numbers side-by-side — **never summed, merged, or averaged** (per-scanner sacred).
- Use the real brand SVGs from `design/brand/` (dark variants in dark chrome) — never redraw them.
- Timestamps: relative text + absolute in the `title` tooltip; deadlines stay absolute.
- Print a stored value by its display name wherever it has one: a filter field carries
  `valueLabel` (finding states read `findings/stateLabels.ts`, audit actions
  `audit/actionLabels.ts`), and the rail, the pills, the saved-view summary and the chips all
  print through it. An audit row's field reads by `audit/fieldLabels.ts`, and a settings value
  kept as JSON by `audit/jsonChange.ts`, with the name and unit of its settings page. The value in the URL, the API and saved views never changes (operator
  ruling 2026-10-02, issue 674; `value-labels.spec.ts` fails a rail option with an underscore).
- Labels say what the user does or sees, not how it is built: no "lens", "selector", "append
  family" or implementation notes in a label or a hint.

**Don't**
- No raw `#hex` / `rgb()` / `hsl()` anywhere outside `styles/tokens.*` + `theme/preset.ts` (CI-enforced).
- No `font-family`/`font-size` literals — type-scale tokens only (CI-enforced).
- Never encode severity with brand colors, or brand chrome with severity colors.
- No purple/indigo defaults, no gradients, no rounded-everything, no shadow stacking — this app has
  a specific look; PrimeVue chrome is themed through `theme/preset.ts`, don't fight it inline.
- Don't hand-roll a severity/state/scanner chip — use (or create in M9b) the shared chip components.
- Don't build the same panel/control twice: **anything that appears on two screens is built ONCE,
  owned by the first change that needs it, and imported everywhere else** — the filter module
  (one `fields` config drives both FacetRail and FilterBar, M9a), the lazy-grid adapter (M9f),
  the chip set (M9b), the banners (M9a). If you're copying a component to a second screen,
  stop and extract it instead.

## 7. Quick reference

```
Page bg:        var(--bg)              Card:          var(--card) + var(--r) + var(--shadow)
Panel/inset:    var(--panel)           Border:        var(--line)  / subtle var(--line2)
Text:           var(--ink) / var(--soft)   (--muted = decorative only, never text)
Primary action: var(--slate2), hover var(--slate)   (issue 1004; coral stays for focus and links)
Head control:   30px, var(--control-hover-line), box-shadow var(--control-edge)   (UiButton/UiSegControl `head`, issue 1039)
Role name:      roleLabel(id) from '@/lib/roleLabel': security_lead shows as "security lead"   (issue 1039)
Severity chip:  color var(--sev-critical-fg); background var(--sev-critical-bg);
                border-color var(--sev-critical-line)   (× six severities)
Chart series:   CHART_SEV.critical … (from '@/styles/tokens' — pinned to tokens.css by test)
State pill:     var(--state-open-*) etc.   Health dot: var(--health-ok-dot)
Table head:     background var(--table-head-bg); color var(--table-head-fg)
Scanner identity: var(--scanner-trivy-*) / var(--scanner-grype-*)  (tags, seg dots, mix labels,
                and on Scanner status each lane's head + table-head band: --table-head-bg takes the
                lane's -fg hue there, the one place the slate band yields — ruling 2026-09-27 on
                built A/B/C specimens; the head text stays --table-head-fg, AA-gated on both hues)
Section accent: var(--sect-*)   (sidebar group dot + head-card top bar — never text)
Mono data:      font-family var(--font-mono); font-size var(--text-mono-cell)
Focus:          outline: var(--focus-ring); outline-offset: 1px
```

### Example component pattern
```vue
<template>
  <section class="card">
    <h2>Findings by severity</h2>
    <span class="chip" :data-sev="sev">{{ sev }}</span>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.chip {
  border-radius: var(--r-chip);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  text-transform: uppercase;
}
.chip[data-sev='critical'] {
  color: var(--sev-critical-fg);
  background: var(--sev-critical-bg);
  border: 1px solid var(--sev-critical-line);
}
</style>
```

## 8. Fidelity protocol — how we stop drifting from the prototype

The gates (stylelint and the style rules test) pin token *values*; they cannot see layout, icons, spacing rhythm, or
copy. Structural fidelity is a process rule:

1. **Build with the prototype open.** The reference is
   `handoff/v4/standalone/JAVV Prototype v4 (standalone).html` (open it in a browser) and its
   readable source `handoff/v4/prototype/app/*.jsx` + the CSS in `JAVV Prototype.html`. When
   building a screen/panel, extract the prototype's exact markup + CSS for that section FIRST
   (grep the class names), then port it onto tokens — don't restyle from memory.
   **Port STRUCTURE, never palette: tokens.css SUPERSEDES the prototype's colors, fonts and
   text sizes** (operator rulings 2026-07-09 — Hanken Grotesk, the AA-computed fg ramp,
   `--coral-text`, the ink-prose rule). The prototype's raw values are the *starting* promotion,
   not the current contract; a "faithful" port of its hexes would reintroduce retired,
   AA-failing colors. The contrast gate (`src/__tests__/contrast-gate.spec.ts`) enforces the
   values; this rule keeps ports from fighting it.
2. **Name the source in the PR.** A screen PR states which prototype component/classes it ports
   (e.g. "Sidebar → main.jsx `Sidebar` + `.side-*` CSS") so review can diff against it.
3. **Screenshots in every screen PR.** `/visual-test` captures the implementation; put them in the
   PR next to the prototype's rendering of the same section. (`/visual-test` captures with the
   committed rig `frontend/scripts/visual-capture.mjs`, which needs no MCP; the Playwright MCP is
   optional, for interactive checks.)
4. **Deviations are rulings, not taste.** Departing from the prototype requires a recorded reason
   (a SCREENS ruling, a shipped-backend constraint) noted in the PR — same discipline as the
   DECIDE register.
5. **Grammar substitutions need a LIVE ruling (operator 2026-07-12, M9d).** Swapping a screen's
   presentation grammar wholesale (the prototype's table → a timeline/cards/feed) is never covered
   by a written note alone — not even a note on the issue or a bolt-README `## Updates` entry: people write notes blind,
   before the thing exists, and the audit screen proved they don't survive contact with the built
   result. A substitution requires the operator ruling **against the built specimen (or an A/B)**
   at build time. When a spec note and the prototype disagree on grammar, the prototype is the
   default and the disagreement is a question for the operator, not a license to pick.

## 9. Anti-pattern detector — ruled exceptions

Run the **vendored** detector — `node .claude/skills/impeccable/scripts/detect.mjs <paths>` — as
part of the authoring loop; it reads source files directly and needs no network. **Never
`npx impeccable detect`** (ruling 2026-07-28, issue 484): npx is unpinned, and it resolved to a
cached 3.4.0 whose since-narrowed `side-tab` rule flagged `.head-card`'s inset box-shadow as an
AI side-stripe. That phantom finding cost an issue and nearly cost §9 a permanent exception row
for a rule that no longer exists. The vendored copy is version-pinned with the repo, so a finding
here means the same thing on every machine and on any future day.

Fix what it finds EXCEPT these ruled exceptions — they are deliberate contract choices, not
reflex defaults (operator ruling 2026-07-09):

| Finding | Ruling |
|---|---|
| `cream-palette` (`--bg` #efeadf / `--panel` #fbfaf6) | The warm-paper identity — deliberate palette, not a default. |
| `tiny-text 10–11.5px` on mono micro-scale | Ops-tool density (table headers, counts, chips) per the v4 scale. Body text stays ≥13px. |
| `low-contrast` white-on-coral (selected chips) | Prototype treatment; 13px/600 label, not body text. The primary and login buttons left it on 2026-10-29: they are slate (issue 1004). |
| `cramped-padding` on `tbl-wrap` | Full-bleed table inside the card is the prototype's design. |
| `layout-transition: width` on `.sidebar` | The collapse rail (226↔64px) — a deliberate layout animation: user-initiated, rare, and the standard sidebar pattern (Nuxt UI reference does the same). Nothing else animates layout except the header card stretch below — the `t-*` classes are transform/opacity only. **Enforced, not just stated:** `style-rules.spec.ts` fails any other width/height/padding/margin transition in `src/` (issue 484 — the triage meter had been breaking this sentence unnoticed). |
| width animation in `composables/useStretchWidth.ts` | The header card stretch (operator decision 2026-10-17, issue 902). It runs only when a card gets wider, for `--dur-panel`, and not with reduced motion. It moves one small card, not the page. `style-rules.spec.ts` permits it in this one file, and also fails a layout animation from script (`element.animate()`) anywhere else. |
| No keyboard way to move a dashboard panel (issue 440, R11) | Ruled 2026-10-24 with R10 and Q5: in edit mode a user moves a panel with the mouse, on gridstack, and nobody resizes a panel. The Move tab is a button, so it takes focus, but no key moves the panel. The width and the height are in the panel settings, which the keyboard reaches. gridstack runs with `animate: false`, so the other panels jump to their places and no layout animation is added to the two above. |
| `ai-color-palette` purple/violet | The `--scanner-grype-*` identity tokens (chip language A) — Grype's brand tone, deliberately distinct from Trivy's teal. Fires on every dump because tokens.css ships globally; not an accent choice. |

Everything else it flags (real contrast failures, hierarchy problems) gets fixed or gets its
own row here — never silently ignored.

## 10. Panels are catalog lenses — build the new ones self-contained (#440)

§6 already says a surface used twice is built ONCE. That rule fires on the *second* screen. This one
fires on the *first*, because the dashboards (#440) need panels to be portable, and
a panel is only portable if it can render somewhere its author never saw.

**What counts as a lens.** An agg-backed visual surface that could plausibly sit on a user-composed
dashboard: charts, stat boards, activity histograms, leaderboards, the trend strips
(`IngestLens`, `AuditLens`, `ContributorsLens`, StatBand, the top-components and riskiest-images
boards). **Not** lenses, and out of scope here: kit controls, modals, form rows, table cells, the
filter module — those are §5's territory and stay props-driven.

**The contract for a NEW lens**

- Takes `(cluster_id, T, params)` and **owns its own aggregation fetch**. `params` comes from the
  shared filter vocabulary, never a bespoke per-lens query shape.
- Renders standalone. No reliance on host state, host-fetched data, or the host having already
  resolved a range, a scope, or a scanner set.
- Server-side everything still holds: the lens issues an aggregation, it does not receive rows and
  count them.
- Carries its own loading, empty and error states, because on a composed page nobody else will.

**The real trade-off.** Host-fed panels are not a mistake, and the existing ones are correct as built.
Feeding several panels from one response is why per-scanner numbers on a screen cannot disagree with
each other: one response, no second fetch (`ContributorsLens` says exactly this in its header). A
self-contained lens gives that up — two lenses on one page can be a few hundred milliseconds apart.
That is the price of composability and #440 accepts it deliberately: the guarantee that matters is
per-scanner *never merged*, not per-panel simultaneity. Where a screen genuinely needs two panels to
agree to the row, keep them host-fed and say why in a comment.

**Do not refactor the existing lenses opportunistically.** #440 moved the lenses of that time onto
this contract in its first slice, deliberately and with its own tests. Converting one in passing,
inside an unrelated PR, is a review failure for the same reason any drive-by refactor is. This
section governs what you *add*.

**The catalog is the registry (#440).** `src/dashboards/catalog.ts` lists every panel a user can
put on a dashboard: an id that never changes once shipped (saved dashboards and the backend name
it), a name, a group (Findings, Scanners, People), one line that says what it shows, the
component, a default width (half or all of the two columns), the heights it can take, and if the
dashboard's scanner switch applies. Its `props(ctx)` turns what a dashboard knows (cluster, T,
window, scanner, height) into that component's own props, so a lens keeps the props its screens
already pass. A table panel takes its rows a page from its height (`TABLE_ROWS`, sizes the shared
GridPager offers). A lens that a screen feeds today keeps that feed and gains a second way in: it takes the screen's
data when it is passed, and reads its own when it is not (Overview passes one findings facets
read to the stat bands, Package type and Per namespace; Contributors passes the Handled findings
strip its series). The screen sends the same requests as before and its panels still agree, and
on a dashboard the panel stands alone. `composables/useFindingsFacets.ts` is that second way for
the facets panels: panels that ask for the same cluster and T while a read is open share it.
A lens with no card of its own sets `framed`, and the dashboard puts it in
`components/dashboards/PanelFrame.vue`, which never clips: each card draws its own `--shadow`
outside its box. `panel-catalog.spec.ts` mounts every entry alone, with only a cluster and its
settings, and fails one that does not send its own request or lacks a loading, empty or error state.
A new lens conforms to the contract, lives where it is used, and joins the catalog when a user
should be able to put it on a dashboard.

## 11. Keeping this file accurate

This file mirrors `tokens.css` — when a token is added/renamed, update both in the same PR (the
tokens unit test pins `CHART_SEV` to the CSS; the M9a DoD spot-check is "every token family in the
CSS has a table row here"). Values were promoted once from `handoff/v4/docs/DESIGN_SYSTEM.md`;
don't re-promote — evolve the tokens.
