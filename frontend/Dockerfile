# JAVV frontend image (issue 452). Build context = the REPO ROOT, like every JAVV image.
#   docker build -f frontend/Dockerfile -t javv-frontend .
# It serves the built SPA and forwards /api, /auth and /readyz to the backend (server/serve.mjs),
# so the browser sees one origin and nothing in front of JAVV is required. It carries no settings:
# JAVV_BACKEND_URL, JAVV_FRONTEND_PORT and JAVV_LOG_LEVEL come from the deployment.

# Node major = versions.yaml toolchain.node (check-versions.sh); tag + digest, Renovate updates both
FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# `build` runs the type-check too, which stays the gate for what ships
RUN npm run build

# the server has no runtime dependencies: the built files and server/ are all it needs
FROM node:22-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a
# the digest pins the start; the upgrade adds the OS security fixes released after it (issue 1172)
RUN apk upgrade --no-cache
# the server has no runtime packages, so the package managers of the base image (npm, npx,
# corepack, yarn) only bring findings (issue 1263)
RUN rm -rf /usr/local/lib/node_modules /opt/yarn-v* /usr/local/bin/npm /usr/local/bin/npx \
    /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY frontend/server ./server
USER 65532:65532
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:' + (process.env.JAVV_FRONTEND_PORT || 8080) + '/').then((r) => process.exit(r.ok ? 0 : 1), () => process.exit(1))"]
CMD ["node", "server/serve.mjs"]
