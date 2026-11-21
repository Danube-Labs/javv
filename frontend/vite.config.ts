import { fileURLToPath, URL } from 'node:url'

import { defineConfig, loadEnv, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

import { contentSecurityPolicy } from './server/serve.mjs'

/** The nonce of the dev server. It is the same in each page, which is safe only on a dev machine:
 *  the frontend server makes a new one for each page (server/serve.mjs). */
export const DEV_NONCE = 'javv-dev-only'

/** Writes the nonce where `main.ts` reads it for PrimeVue, as the frontend server does. Vite's own
 *  tag (`<meta property="csp-nonce" nonce>`) has a different shape. */
function nonceMeta(nonce: string): Plugin {
  return {
    name: 'javv-csp-nonce-meta',
    apply: 'serve',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { name: 'csp-nonce', content: nonce }, injectTo: 'head-prepend' },
    ],
  }
}

const HERE = fileURLToPath(new URL('.', import.meta.url))

const proxy = {
  // the live dev backend (uvicorn :8000) — same paths the k8s ingress will route
  '/api': 'http://localhost:8000',
  '/auth': 'http://localhost:8000',
  '/readyz': 'http://localhost:8000',
  '/metrics': 'http://localhost:8000',
}

// https://vite.dev/config/
export default defineConfig(({ command, mode, isPreview }) => {
  // The dev server sends the policy of the frontend server, so a violation shows while a
  // developer works (issue 1275, D1 A). The Vue devtools add a style with no nonce, so they and
  // the policy do not go together: VITE_DEVTOOLS=true turns the devtools on and the policy off.
  // The build gets neither: a fixed nonce in dist/ would be the same in each page. Vite calls this
  // with `serve` for `vite preview` too, and preview takes server.headers when it has none of its
  // own. The built page has no dev nonce, so the dev policy would refuse its styles there.
  const serve = command === 'serve' && !isPreview
  const devtools = serve && loadEnv(mode, HERE, 'VITE_').VITE_DEVTOOLS === 'true'
  const policy = serve && !devtools
  return {
    plugins: [vue(), ...(devtools ? [vueDevTools()] : []), ...(policy ? [nonceMeta(DEV_NONCE)] : [])],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    ...(policy ? { html: { cspNonce: DEV_NONCE } } : {}),
    server: {
      // `coverage/` is vitest output, gitignored and never imported. Watched, it cost a full page
      // reload PER FILE written — 80 of them on one `npm run test:ci` — so running the suite while
      // the dev server was up wiped whatever the operator had on screen mid-session.
      watch: { ignored: ['**/coverage/**'] },
      proxy: { ...proxy },
      ...(policy ? { headers: { 'content-security-policy': contentSecurityPolicy(DEV_NONCE) } } : {}),
    },
    preview: {
      // `vite preview` serves the BUILT app on a dev machine. It does not take server.proxy, so it
      // has its own. It sends no Content-Security-Policy, so CI serves the build with
      // server/serve.mjs instead (issue 1272)
      proxy: { ...proxy },
    },
  }
})
