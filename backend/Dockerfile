# JAVV backend image (issue 452). Build context = the REPO ROOT: the backend depends on the shared
# libs/javv-common by path.
#   docker build -f backend/Dockerfile -t javv-backend .
# It carries no settings. Every JAVV_* value comes from the deployment (deploy/compose/compose.yaml)
# and the defaults live in core/settings.py, so a second copy here could only drift.

# tag + digest: the digest makes the build reproducible; Renovate updates both
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS build
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never
# uv's own image, tag = versions.yaml toolchain.uv (check-versions.sh), pinned by digest
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /usr/local/bin/uv
# /app is the project; the shared lib lands at /libs so the lock's ../libs/javv-common resolves
COPY libs /libs
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
# --no-editable installs the backend and javv-common into the venv itself, so the runtime stage
# needs the venv alone, not the sources
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
# the digest pins the start; the upgrade adds the OS security fixes released after it (issue 1172)
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
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
