# JAVV backend image (issue 452). Build context = the REPO ROOT: the backend depends on the shared
# libs/javv-common by path.
#   docker build -f backend/Dockerfile -t javv-backend .
# It carries no settings. Every JAVV_* value comes from the deployment (deploy/compose/compose.yaml)
# and the defaults live in core/settings.py, so a second copy here could only drift.

# tag + digest: the digest makes the build reproducible; Renovate updates both
FROM python:3.14-alpine@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67 AS build
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
# uv's own image, tag = versions.yaml toolchain.uv (check-versions.sh), pinned by digest
COPY --from=ghcr.io/astral-sh/uv:0.13.9@sha256:d3b601f0c7b118bc1753febf7c41cc80981df678445e0254284eecf84db79a7d /uv /usr/local/bin/uv
# /app is the project; the shared lib lands at /libs so the lock's ../libs/javv-common resolves
COPY libs /libs
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
# --no-editable installs the backend and javv-common into the venv itself, so the runtime stage
# needs the venv alone, not the sources
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.14-alpine@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67
# the digest pins the start; the upgrade adds the OS security fixes released after it (issue 1172)
RUN apk upgrade --no-cache
# the apps run from their venv, so the base image's pip only brings findings (issue 1263); `rm`,
# not `pip uninstall`, which leaves 4.6 MB of files that it writes while it runs
RUN rm -rf /usr/local/lib/python3*/site-packages/pip /usr/local/lib/python3*/site-packages/pip-*.dist-info \
    /usr/local/bin/pip*
RUN addgroup -S -g 65532 javv \
 && adduser -S -D -H -u 65532 -G javv -h /nonexistent javv
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
USER 65532:65532
EXPOSE 8000
# liveness only: /healthz answers without OpenSearch, /readyz is the readiness check
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status != 200)"]
# one worker: the job scheduler and the in-process metrics assume one process (issue 691)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
