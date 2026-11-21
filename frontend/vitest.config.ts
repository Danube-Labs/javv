import { fileURLToPath } from 'node:url'
import { mergeConfig, defineConfig, configDefaults } from 'vitest/config'
import viteConfig from './vite.config'

export default defineConfig((env) =>
  mergeConfig(
    viteConfig(env),
    defineConfig({
      test: {
        environment: 'jsdom',
        exclude: [...configDefaults.exclude, 'e2e/**', 'tests/e2e/**'],
        root: fileURLToPath(new URL('./', import.meta.url)),
        coverage: {
          provider: 'v8',
          // the coverage floor's denominator is the UNIT-testable logic: TS modules (stores, query
          // builders, lib). Views/components are proven by the browser smoke (ci-smoke.mjs),
          // and src/api/generated is generated code — counting either would make the number
          // a fiction. Vue SFCs still report when tests touch them; they just don't gate.
          // server/ is the frontend container's Node server (issue 452): unit-tested logic too
          include: ['src/**/*.ts', 'server/**/*.mjs'],
          exclude: ['src/api/generated/**', 'src/main.ts'],
          // the #383 coverage floor: 79.7% lines measured 2026-07-15, floored at −2pts.
          // Raise when coverage grows, never lower (docs/CONFIGURATION.md, "CI gate values").
          thresholds: { lines: 77 },
        },
      },
    }),
  ),
)
