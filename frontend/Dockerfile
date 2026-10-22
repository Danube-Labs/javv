# JAVV frontend image (issue 452). Build context = the REPO ROOT, like every JAVV image.
#   docker build -f frontend/Dockerfile -t javv-frontend .
# It serves the built SPA and forwards /api, /auth and /readyz to the backend (server/serve.mjs),
# so the browser sees one origin and nothing in front of JAVV is required. It carries no settings:
# JAVV_BACKEND_URL, JAVV_FRONTEND_PORT and JAVV_LOG_LEVEL come from the deployment.

# Node major = versions.yaml toolchain.node (check-versions.sh); tag + digest, Renovate updates both
FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914 AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# `build` runs the type-check too, which stays the gate for what ships
RUN npm run build

# the server has no runtime dependencies: the built files and server/ are all it needs
FROM node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY frontend/server ./server
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:' + (process.env.JAVV_FRONTEND_PORT || 8080) + '/').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server/serve.mjs"]
