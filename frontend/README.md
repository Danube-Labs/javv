# JAVV frontend

Vue 3 (`<script setup lang="ts">`) · PrimeVue · vue-echarts · Pinia · Vue Router, built with Vite.
Every number and page comes from the backend; the client never computes counts from raw findings.

**Before changing any UI, read [`DESIGN.md`](DESIGN.md)** (tokens, type, the fidelity protocol and
the ruled exceptions), then `handoff/docs/SCREENS.md` for the screen you're touching.

## Run it

Node `^22.18.0 || >=24.12.0`. The dev server needs the backend on `:8000`
(see [`development/RUNNING-THE-STACK.md`](../development/RUNNING-THE-STACK.md)).

```sh
npm install
npm run dev        # :5173; proxies /api, /auth, /readyz and /metrics to localhost:8000
```

The frontend server of the image (`server/serve.mjs`) sends `/api`, `/auth` and `/readyz` to the
backend in the same way, so the app never needs a backend URL. `vite preview` (the built app) has
the same proxy, without `/metrics`.

## The API contract

The typed client in `src/api/generated/` is generated from the committed schema snapshot
`openapi.json`. After any backend route or parameter change:

```sh
(cd ../backend && uv run python -m backend.tools.export_openapi ../frontend/openapi.json)
npm run gen:api
```

Then restart `npm run dev`: a running dev server keeps the old module graph and fails with
"does not provide an export". CI's contract gate fails the build if either the snapshot or the
generated client is stale.

## What CI runs

| Command | What it does |
|---|---|
| `npm run lint` | oxlint, ESLint and stylelint. The first two run with `--fix`, so review the diff after |
| `npm run test:ci` | `vue-tsc` type check, then vitest with the coverage floor. Run this, not `npm run test`, before pushing |
| `npm run smoke` | the route walk (`scripts/ci-smoke.mjs`): a built app against a seeded backend, desktop viewport, zero console errors, layout checks |
| `npm run test:e2e` | the Playwright specs in `tests/e2e/`, same environment as the smoke |

The last two need a running backend and `JAVV_BASE`, `JAVV_USER` and `JAVV_PASS`; see the headers
of `scripts/ci-smoke.mjs` and `playwright.config.ts`. `npm run build` type-checks and builds `dist/`.

## Where things live

| Path | What |
|---|---|
| `src/views/` | one component per route |
| `src/components/ui/` | the kit: buttons, fields, dropdowns, modal and slide-over shells, skeletons, empty states, toasts. Reuse before writing a new control |
| `src/components/chips/` | status chips and tags: severity, state, scanner, KEV, SLA, disagreement, … |
| `src/components/<area>/` | panels per screen area (findings, dashboards, settings, …) |
| `src/filters/` | the shared filter module: the field config (`fields.config.ts`) and the query builder |
| `src/composables/`, `src/stores/` | shared state and hooks |
| `src/lib/logger.ts` | the only logger. `console.*` is lint-banned |
| `src/styles/`, `src/theme/` | tokens and the PrimeVue theme |
| `scripts/` | the smoke, the authoring screenshot rig (`visual-capture.mjs`) and the demo recorder |
