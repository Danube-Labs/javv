#!/usr/bin/env python3
"""PreToolUse guard for Bash: refuse the footguns that have each cost us a session.

Each is written down in CLAUDE.md and each still fired after being written down, which is
the whole argument for making them mechanical. Blocking here costs one retry; the failures
they cause cost a debugging session each.

Two kinds of guard live here:
- **String guards** (`offending_reason`): the command is refused on sight — `git add -A`,
  `pkill -f`. Pure, so `test_guard_bash.py` can cover them exhaustively.
- **The lint-gate guard** (`lint_gate_reason`): a chain that publishes (commit, push, a gh
  post) is refused when the exit code of the text linter cannot stop it: the linter is piped
  (`ste-lint.py F | tail && gh ...` gates on `tail`), or followed by `;`, `||` or `&`. Each
  form posted or pushed text with a hard finding, eleven times by 2026-11-18.
- **The index-lock guard** (`index_lock_blocker`): git commands that take `.git/index.lock`
  are SERIALIZED rather than refused. Two git commands issued as parallel Bash calls in one
  turn race for that lock; the loser dies with "Unable to create '.git/index.lock'", and when
  the loser is a `commit`, pre-commit surfaces it as a stack trace and the commit silently
  does not land — which is exactly how it bit twice on 2026-07-28.

  Known limit: this narrows the window, it does not close it. If both hooks run before
  either command has taken the lock, both are allowed and the race still happens. It fixes
  the common case (one command already holds the lock) and turns the rest into a named
  diagnosis instead of a pre-commit traceback. The real rule is still "don't issue git
  commands in parallel", and the message says so.

Reads the hook payload on stdin, exits 2 with a reason on stderr to block, 0 to allow.
"""

import json
import re
import shlex
import sys
import time
from pathlib import Path

ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Words that can sit in front of the real command. `until ! pgrep -f ...` is not a hypothetical:
# it is the exact loop that hung two sessions, so the guard has to see past them.
LEADING_NOISE = {
    "!",
    "until",
    "while",
    "if",
    "then",
    "do",
    "else",
    "elif",
    "time",
    "sudo",
    "env",
    "nohup",
    "command",
    "exec",
    "builtin",
}

# `git add -A` has swept gitignored files into commits; `pkill -f` matches the Bash tool's own
# wrapper process, so it kills the shell running it or hangs a wait-loop forever.
GUARDS = [
    (
        ("git", "add"),
        {"-A", "--all", "."},
        (
            "`git add -A` / `git add .` has swept gitignored files into commits here.\n"
            "Stage explicit paths instead:  git add path/one path/two"
        ),
    ),
    (
        ("pkill",),
        {"-f"},
        (
            "`pkill -f` matches the Bash tool's own wrapper process — it kills the shell running\n"
            "it, or hangs a wait-loop forever. Find the PID and kill that:  ss -ltnp | grep <port>"
        ),
    ),
    (
        ("pgrep",),
        {"-f"},
        (
            "`pgrep -f` matches the Bash tool's own wrapper, so it always reports a match and an\n"
            "`until ! pgrep -f ...` loop never exits. Use `ss -ltnp` or match without -f."
        ),
    ),
]

# Anything after a heredoc marker is data (a commit message, a PR body), not commands to run.
SEPARATORS = {"&&", "||", "|", ";", "&", "(", ")", "{", "}"}

# Linters whose exit code is the only gate for public text (ste-lint exits 1 on a hard finding).
TEXT_LINTERS = {"ste-lint.py", "check-release-notes.py"}
# Separators after which the linter's failure no longer stops the next command.
UNGATED_AFTER_LINT = {"|", "|&", ";", "||", "&"}
GH_PUBLISH = {
    ("pr", "create"),
    ("pr", "edit"),
    ("pr", "comment"),
    ("pr", "merge"),
    ("pr", "review"),
    ("issue", "create"),
    ("issue", "edit"),
    ("issue", "comment"),
    ("release", "create"),
    ("release", "edit"),
}
GH_API_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}

# git subcommands that take `.git/index.lock`. Read-only ones (status, log, diff, show) are
# deliberately absent — they never contend, and waiting on them would tax every poll.
INDEX_LOCK_SUBCOMMANDS = {
    "add",
    "am",
    "apply",
    "checkout",
    "cherry-pick",
    "commit",
    "merge",
    "mv",
    "pull",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "switch",
}
# git's own global flags that carry a value — walked past to reach the subcommand.
GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
LOCK_WAIT_SECONDS = 10.0


def _segments(command: str) -> list[list[str]]:
    """The command chain, split on separators, each stripped of leading env/noise words."""
    body = command.split("<<", 1)[0]
    try:
        tokens = shlex.split(body, comments=True)
    except ValueError:
        return []  # unbalanced quotes: not parseable, so not confidently anything
    out, start = [], 0
    for i, tok in enumerate(tokens + [";"]):
        if tok not in SEPARATORS:
            continue
        segment = tokens[start:i]
        start = i + 1
        while segment and (
            ENV_ASSIGNMENT.match(segment[0]) or segment[0] in LEADING_NOISE
        ):
            segment = segment[1:]  # FOO=bar git add -A · until ! pgrep -f …
        if segment:
            out.append(segment)
    return out


def _git_subcommand(segment: list[str]) -> str | None:
    """`git -C repo -c k=v commit` -> "commit". None when the segment is not git at all."""
    if not segment or segment[0] != "git":
        return None
    rest = iter(segment[1:])
    for tok in rest:
        if tok in GIT_VALUE_FLAGS:
            next(rest, None)
            continue
        if tok.startswith("-"):
            continue
        return tok
    return None


def takes_index_lock(command: str) -> bool:
    """True when any command in the chain would take `.git/index.lock`."""
    return any(
        _git_subcommand(seg) in INDEX_LOCK_SUBCOMMANDS for seg in _segments(command)
    )


def _git_dir(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        candidate = d / ".git"
        if candidate.is_dir():
            return candidate
    return None


def index_lock_blocker(cwd: str, wait_seconds: float = LOCK_WAIT_SECONDS) -> str | None:
    """Wait out a live index lock; report a reason if it outlasts the wait."""
    git_dir = _git_dir(Path(cwd or "."))
    if git_dir is None:
        return None
    lock = git_dir / "index.lock"
    deadline = time.monotonic() + wait_seconds
    while lock.exists():
        if time.monotonic() >= deadline:
            return (
                f"{lock} is still held after {wait_seconds:.0f}s.\n\n"
                "Another git command is running — almost always a sibling Bash call issued in\n"
                "the SAME turn. Git commands must run one at a time: put them in one Bash call\n"
                "chained with && , or wait for the first to return before issuing the next.\n\n"
                "If no git process is alive (`ps -C git`), the lock is stale from a crash —\n"
                "delete it and retry:  rm .git/index.lock"
            )
        time.sleep(0.2)
    return None


def _chain(command: str) -> list[tuple[list[str], str]]:
    """Each command of the chain with the separator that follows it ("" at the end).

    Unlike `_segments`, this keeps the separators, and splits on `|` or `;` even without
    spaces around them. A newline separates commands like `;` does.
    """
    body = command.split("<<", 1)[0].replace("\n", " ; ")
    lexer = shlex.shlex(body, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out, segment = [], []
    for tok in tokens:
        if tok in SEPARATORS or tok == "|&":
            out.append((segment, tok))
            segment = []
        else:
            segment.append(tok)
    out.append((segment, ""))
    return out


def _strip_noise(segment: list[str]) -> list[str]:
    while segment and (ENV_ASSIGNMENT.match(segment[0]) or segment[0] in LEADING_NOISE):
        segment = segment[1:]
    return segment


def _publishes(segment: list[str]) -> bool:
    seg = _strip_noise(segment)
    if _git_subcommand(seg) in {"push", "commit"}:
        return True
    if not seg or seg[0] != "gh":
        return False
    if tuple(seg[1:3]) in GH_PUBLISH:
        return True
    if len(seg) > 1 and seg[1] == "api":
        for i, tok in enumerate(seg):
            if tok in {"-X", "--method"} and i + 1 < len(seg):
                method = seg[i + 1]
            elif tok.startswith("--method="):
                method = tok.split("=", 1)[1]
            else:
                continue
            if method.upper() in GH_API_WRITE_METHODS:
                return True
    return False


def lint_gate_reason(command: str) -> str | None:
    """Refuse a publishing chain whose text linter cannot stop the publish."""
    chain = _chain(command)
    if not any(_publishes(seg) for seg, _ in chain):
        return None
    for i, (segment, sep) in enumerate(chain):
        if not any(Path(tok).name in TEXT_LINTERS for tok in segment):
            continue
        following = chain[i + 1][0] if i + 1 < len(chain) else []
        if sep == ";" and following[:1] == ["then"]:
            continue  # `if lint F; then gh ...; fi` gates on the linter itself
        if sep in UNGATED_AFTER_LINT:
            return (
                f"The text linter is followed by `{sep}` in a chain that commits, pushes or\n"
                "posts. Its exit code then does not stop the publish: a pipe gates on the LAST\n"
                "command, and `;`, `||` or `&` run the next command anyway. This posted or pushed\n"
                "text with a hard finding eleven times by 2026-11-18.\n\n"
                "Gate on the linter itself, with no pipe:\n"
                "  python3 development/scripts/ste-lint.py F && gh issue comment N --body-file F\n"
                "  if python3 development/scripts/ste-lint.py F; then git push; fi\n"
                "Or run the linter in its own call, read the exit code, then publish."
            )
    return None


def offending_reason(command: str) -> str | None:
    # shlex has already collapsed quoted strings into single tokens, so a literal
    # "git add -A" inside a commit message cannot trigger this
    for segment in _segments(command):
        for prefix, flags, reason in GUARDS:
            if len(segment) < len(prefix) or tuple(segment[: len(prefix)]) != prefix:
                continue
            if flags & set(segment[len(prefix) :]):
                return reason
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    reason = offending_reason(command) or lint_gate_reason(command)
    if reason is None and takes_index_lock(command):
        # serialize rather than refuse: a lock held by a sibling call clears on its own
        reason = index_lock_blocker(payload.get("cwd", ""))
    if reason is None:
        return 0
    print(
        f"Blocked by the repo's Bash guard (.claude/hooks/guard_bash.py):\n\n{reason}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
