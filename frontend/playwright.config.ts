/**
 * The E2E smoke suite (M9f slice 5, testing.md §4): a handful of fast, deterministic specs
 * against a BUILT frontend + seeded backend — the same environment the route-walk smoke uses
 * (CI job `frontend-smoke` starts the backend, the seed and server/serve.mjs, then runs both).
 * On a dev machine, point JAVV_BASE at the app (the default is port 4173, where CI serves the
 * build) and export JAVV_USER/JAVV_PASS.
 * One worker, zero retries: the specs share one seeded store and must be deterministic —
 * a retry that hides a flake is worse than a red.
 */
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/e2e',
  timeout: 45_000,
  retries: 0,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: process.env.JAVV_BASE ?? 'http://localhost:4173',
    viewport: { width: 1920, height: 1080 }, // desktop-only gate (ruling on issue 387)
    trace: 'retain-on-failure',
  },
})
