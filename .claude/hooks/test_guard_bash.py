#!/usr/bin/env python3
"""Cases for the Bash guard. A guard that blocks legitimate commands is worse than no guard,
so the false-positive cases carry as much weight as the ones that must block.

    python3 .claude/hooks/test_guard_bash.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from guard_bash import (
    index_lock_blocker,
    lint_gate_reason,
    offending_reason,
    takes_index_lock,
)

MUST_BLOCK = [
    "git add -A",
    "git add .",
    "git add --all",
    "git add -A .",
    "cd frontend && git add -A",
    "git status && git add . && git commit -m 'x'",
    "GIT_AUTHOR_NAME=x git add -A",
    "pkill -f 'python -m scanner'",
    "pgrep -f uvicorn",
    'until ! pgrep -f "python -m scanner"; do sleep 2; done',
]

MUST_ALLOW = [
    # the ordinary forms
    "git add README.md",
    "git add backend/src/backend/routers/admin_jobs.py scanner/run.py",
    "git add -p",
    "git add --update backend/",
    # a path that merely starts with a dot, and a flag that merely contains one
    "git add .github/workflows/ci.yml",
    "git add --pathspec-from-file=list.txt",
    # the strings appear only as DATA — quoted in a message, or in a heredoc body.
    # this is the case a naive grep gets wrong, and we write these strings constantly.
    "git commit -m 'never use git add -A here'",
    'gh issue comment 1 --body "the rule is: no pkill -f from the Bash tool"',
    "git commit -F - <<'EOF'\nfix: stop using git add -A\nEOF",
    # kill by name without the -f matcher is fine; so is killing by PID
    "pkill nginx",
    "kill -9 12345",
    "ss -ltnp | grep 8000",
    # unrelated commands that happen to contain the substrings
    "echo 'git add -A' >> notes.md",
    "rg 'pkill -f' docs/",
]


# A publish whose text linter cannot stop it. Each shape is one that really posted or pushed.
LINT_UNGATED = [
    "python3 s/ste-lint.py c.md | grep violations && gh issue comment 1 --body-file c.md",
    "python3 s/ste-lint.py c.md | tail -2 | head -1 && gh issue comment 1 --body-file c.md",
    "python3 s/ste-lint.py F|tail -2 && git push",
    "python3 s/ste-lint.py c.md; gh issue comment 1 --body-file c.md",
    "python3 s/ste-lint.py F | tail -2 && git add F && git commit -m 'docs: x'",
    "python3 s/ste-lint.py F || gh pr edit 2 --body-file F",
    "python3 s/check-release-notes.py b.md | tail -1 && gh pr edit 3 --body-file b.md",
    "python3 s/ste-lint.py F | tail\ngh issue create --title t --body-file F",
    "python3 s/ste-lint.py F | tail && gh api -X PATCH repos/o/r/issues/comments/1 -F body=@F",
]

# A linter that gates correctly, or a pipe with nothing published.
LINT_GATED = [
    "python3 s/ste-lint.py c.md && gh issue comment 1 --body-file c.md",
    "if python3 s/ste-lint.py c.md >/dev/null; then gh issue comment 1 --body-file c.md; fi",
    "python3 s/ste-lint.py F | tail -5",
    "python3 s/ste-lint.py F > out.txt; echo rc=$?",
    "git push origin main",
    "gh api repos/o/r/pulls/1 | jq .title && python3 s/ste-lint.py F | tail",
    "git commit -m 'never pipe ste-lint.py into tail before a push'",
]


# Commands that contend for `.git/index.lock` and so must be serialized behind a live lock.
TAKES_LOCK = [
    "git commit -m 'x'",
    "git add README.md",
    "git checkout -b feat/x",
    "git rebase main",
    "git -C /repo commit -m 'x'",  # global flag with a value, walked past
    "git -c user.name=x commit -m 'y'",
    "cd frontend && git add src/main.ts",
    "git fetch --prune && git checkout main",  # the second segment contends
    # the OUTER command decides: this is a real commit, whatever its message happens to say
    "git commit -m 'about to git rebase main'",
]

# Read-only git and non-git commands must NOT pay the lock wait.
NO_LOCK = [
    "git status -sb",
    "git log --oneline -1",
    "git diff --stat",
    "git branch -vv",
    "git fetch --prune",
    "gh pr list --state open",
    "npm run test:ci",
    # git named only as DATA — inside another tool's argument, never run
    "echo 'git commit -m x' >> notes.md",
    'gh issue comment 1 --body "then git rebase main"',
    "rg 'git checkout' docs/",
]


def check_index_lock() -> list[str]:
    """The lock guard end-to-end: a present lock reports, an absent one stays silent."""
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        (repo / ".git").mkdir()
        if index_lock_blocker(str(repo), wait_seconds=0.1) is not None:
            out.append("  clean repo should not block")
        (repo / ".git" / "index.lock").touch()
        reason = index_lock_blocker(str(repo), wait_seconds=0.3)
        if reason is None:
            out.append("  held lock should report after the wait")
        elif "one at a time" not in reason:
            out.append("  lock message should name the fix, not just the symptom")
        # a directory with no .git at all is not our business
        with tempfile.TemporaryDirectory() as bare:
            if index_lock_blocker(bare, wait_seconds=0.1) is not None:
                out.append("  non-repo directory should not block")
    return out


def main() -> int:
    failures = []
    for cmd in MUST_BLOCK:
        if offending_reason(cmd) is None:
            failures.append(f"  SHOULD BLOCK but allowed: {cmd!r}")
    for cmd in MUST_ALLOW:
        reason = offending_reason(cmd)
        if reason is not None:
            failures.append(f"  SHOULD ALLOW but blocked: {cmd!r}")
    for cmd in LINT_UNGATED:
        if lint_gate_reason(cmd) is None:
            failures.append(f"  SHOULD BLOCK the ungated lint but allowed: {cmd!r}")
    for cmd in LINT_GATED:
        if lint_gate_reason(cmd) is not None:
            failures.append(f"  SHOULD ALLOW the gated lint but blocked: {cmd!r}")
    for cmd in TAKES_LOCK:
        if not takes_index_lock(cmd):
            failures.append(f"  SHOULD WAIT on the index lock: {cmd!r}")
    for cmd in NO_LOCK:
        if takes_index_lock(cmd):
            failures.append(f"  SHOULD NOT wait on the index lock: {cmd!r}")
    failures += check_index_lock()
    if failures:
        print(f"guard-bash: {len(failures)} failure(s)")
        print("\n".join(failures))
        return 1
    print(
        f"guard-bash: {len(MUST_BLOCK) + len(LINT_UNGATED)} blocked, "
        f"{len(MUST_ALLOW) + len(LINT_GATED)} allowed, "
        f"{len(TAKES_LOCK)} serialized, {len(NO_LOCK)} unaffected — all as expected"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
