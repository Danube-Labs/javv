#!/usr/bin/env bash
#
# Docs-drift gate (#410 §5): fails when the two hand-maintained trackers drift from code.
#   1. docs/API.md route table vs the live OpenAPI export — every live route documented,
#      no documented route that no longer exists (combined rows like `GET/POST` count for both).
#   2. docs/CONFIGURATION.md env rows vs backend/src/backend/core/settings.py — every
#      `JAVV_<FIELD>` named in the doc corresponds to a settings field or a literal in code;
#      every settings field is mentioned in the doc.
#   3. REPO-MAP.md inventory — every workflow file, every ci.yml job name, and every file in
#      development/scripts/ and development/standards/ is named in it.
#
# Usage: development/scripts/check-docs-drift.sh [path-to-openapi.json]
# Without an argument it exports a fresh spec via the backend venv (needs deps installed).
#
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

SPEC="${1:-}"
if [ -z "$SPEC" ]; then
  SPEC=$(mktemp)
  trap 'rm -f "$SPEC"' EXIT
  (cd backend && { [ -x .venv/bin/python ] && .venv/bin/python -m backend.tools.export_openapi "$SPEC" \
    || uv run python -m backend.tools.export_openapi "$SPEC"; }) >/dev/null
fi

python3 - "$SPEC" <<'EOF'
import json, re, sys

spec = json.load(open(sys.argv[1]))
live = {f'{m.upper()} {p}' for p, ms in spec['paths'].items() for m in ms}

doc = set()
for line in open('docs/API.md'):
    m = re.match(r'\|\s*((?:GET|POST|PUT|PATCH|DELETE)(?:/(?:GET|POST|PUT|PATCH|DELETE))*)\s*\|\s*`([^`]+)`', line)
    if not m:
        continue
    methods = m.group(1).split('/')
    # a cell may hold several ·-joined paths sharing the method(s)
    paths = [p.strip('` ') for p in re.split(r'·', line.split('|')[2]) if '`' in p]
    for method in methods:
        for path in paths:
            doc.add(f'{method} {re.sub(r"`", "", path).strip()}')

failures = []
missing = sorted(r for r in live if r not in doc)
gone = sorted(r for r in doc if r not in live)
if missing:
    failures.append('routes in code but MISSING from docs/API.md:\n  ' + '\n  '.join(missing))
if gone:
    failures.append('routes in docs/API.md but GONE from code:\n  ' + '\n  '.join(gone))

src = open('backend/src/backend/core/settings.py').read()
# a field is `name: type`; a bare `try:`/`else:` at the same indent is a block, not a field
fields = set(re.findall(r'^\s{4}(\w+): \S', src, re.M))
conf = open('docs/CONFIGURATION.md').read()
import subprocess
code_literals = set(subprocess.run(
    # deploy/compose: a variable compose reads from .env is real even if no code does (issue 729).
    # deploy/nomad, deploy/docker: the scripts of the Nomad and Docker scans read their own
    # settings (issue 1155).
    ['git', 'grep', '-rho', r'JAVV_[A-Z0-9_]*', '--', 'backend/src', 'scanner/src', 'libs', 'frontend',
     'deploy/compose', 'deploy/nomad', 'deploy/docker'],
    capture_output=True, text=True).stdout.split())
# not the tail of a longer name: OPENSEARCH_JAVV_PASSWORD is not JAVV_PASSWORD
doc_vars = set(re.findall(r'(?<![A-Z0-9_])JAVV_[A-Z0-9_]+', conf))
phantom = sorted(v for v in doc_vars
                 if v.removeprefix('JAVV_').lower() not in fields and v not in code_literals)
undocumented = sorted(f for f in fields if f'JAVV_{f.upper()}' not in conf and f.upper() not in conf)
if phantom:
    failures.append('CONFIGURATION.md names env vars that exist nowhere in code:\n  ' + '\n  '.join(phantom))
if undocumented:
    failures.append('settings.py fields with no CONFIGURATION.md row:\n  ' + '\n  '.join(undocumented))

import os
repo_map = open('REPO-MAP.md').read()
norm = lambda t: re.sub(r'[\s-]+', ' ', t).strip().lower()
repo_map_norm = norm(repo_map)
unmapped = [f'.github/workflows/{f}' for f in sorted(os.listdir('.github/workflows'))
            if f.endswith(('.yml', '.yaml')) and f not in repo_map]
# a job's display name, minus any "(...)" note: "javv-common (shared lib)" -> "javv-common"
for name in re.findall(r'^  [\w-]+:\n(?:    .*\n)*?    name: (.+)$', open('.github/workflows/ci.yml').read(), re.M):
    name = re.sub(r'\s*\(.*\)$', '', name).strip()
    if norm(name) not in repo_map_norm:
        unmapped.append(f'ci.yml job "{name}"')
for folder in ('development/scripts', 'development/standards'):
    for f in sorted(os.listdir(folder)):
        if f != 'README.md' and f.removesuffix('.md') not in repo_map:
            unmapped.append(f'{folder}/{f}')
if unmapped:
    failures.append('in the repo but not named in REPO-MAP.md:\n  ' + '\n  '.join(unmapped))

if failures:
    print('DOCS DRIFT DETECTED\n')
    print('\n\n'.join(failures))
    sys.exit(1)
print(f'docs in sync: {len(live)} routes documented, {len(fields)} settings fields tracked, REPO-MAP inventory complete')
EOF
