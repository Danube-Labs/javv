// The built app of the video stack, on loopback only (the server's own entry listens on every
// interface), with /api and /auth sent to the video backend.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createLogger } from '../../../frontend/server/log.mjs'
import { createFrontendServer } from '../../../frontend/server/serve.mjs'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..')
const server = createFrontendServer({
  backendUrl: `http://127.0.0.1:${process.env.BACKEND_PORT ?? 8010}`,
  distDir: path.join(repo, 'frontend', 'dist'),
  log: createLogger('info'),
})
server.listen(Number(process.env.APP_PORT ?? 8091), '127.0.0.1')
