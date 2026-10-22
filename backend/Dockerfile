# JAVV backend image (issue 452). Build context = the REPO ROOT: the backend depends on the shared
# libs/javv-common by path.
#   docker build -f backend/Dockerfile -t javv-backend .
# It carries no settings. Every JAVV_* value comes from the deployment (deploy/compose/compose.yaml)
# and the defaults live in core/settings.py, so a second copy here could only drift.

# tag + digest: the digest makes the build reproducible; Renovate updates both
FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2 AS build
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
# uv's own image, tag = versions.yaml toolchain.uv (check-versions.sh), pinned by digest
COPY --from=ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 /uv /usr/local/bin/uv
# /app is the project; the shared lib lands at /libs so the lock's ../libs/javv-common resolves
COPY libs /libs
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
# --no-editable installs the backend and javv-common into the venv itself, so the runtime stage
# needs the venv alone, not the sources
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2
RUN groupadd --system --gid 65532 javv \
 && useradd --system --uid 65532 --gid 65532 --no-create-home --home-dir /nonexistent javv
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
