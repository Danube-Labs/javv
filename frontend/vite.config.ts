import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // `coverage/` is vitest output, gitignored and never imported. Watched, it cost a full page
    // reload PER FILE written — 80 of them on one `npm run test:ci` — so running the suite while
    // the dev server was up wiped whatever the operator had on screen mid-session.
    watch: { ignored: ['**/coverage/**'] },
    proxy: {
      // the live dev backend (uvicorn :8000) — same paths the k8s ingress will route
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/readyz': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
    },
  },
  preview: {
    // `vite preview` serves the BUILT app on a dev machine. It does not take server.proxy, so it
    // has its own. It sends no Content-Security-Policy, so CI serves the build with
    // server/serve.mjs instead (issue 1272)
    proxy: {
      '/api': 'http://localhost:8000',
      '/auth': 'http://localhost:8000',
      '/readyz': 'http://localhost:8000',
      '/metrics': 'http://localhost:8000',
    },
  },
})
