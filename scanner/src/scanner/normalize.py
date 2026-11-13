"""Severity canonicalization (D16).

Scanner severity words vary in vocabulary and casing (Trivy `CRITICAL`, Grype `Critical`/
`Negligible`). We map each to one of six canonical buckets while the caller keeps the verbatim
word in `_source` for evidence/display. Grype's Negligible/Unknown are kept distinct, never
folded — the muted "other" grouping is a UI concern. Scanner input is untrusted: anything
unrecognized or non-string maps to `unknown` (never `critical`) and this never raises.

D46 (#274): the canonical vocabulary is the FULL words — for every standard scanner word
canonical == verbatim-lowercase. The historical `crit`/`med` shorthand survives only as count
COLUMN names on the envelope (`COUNT_COLUMN` — documented physical names, part of the immutable
wire/history; renaming them buys nothing a human ever types).

The file paths of a finding (issue 1077) are cleaned here too, to the rules of the backend.
"""

import unicodedata
from collections.abc import Iterable
from typing import NamedTuple

# Fixed order map, highest → lowest (AUDIT-RESPONSE, vocabulary per D46):
#   critical > high > medium > low > negligible > unknown
SEVERITIES: tuple[str, ...] = ("critical", "high", "medium", "low", "negligible", "unknown")

# canonical bucket → envelope count COLUMN name (identity where the words already coincide)
COUNT_COLUMN: dict[str, str] = {"critical": "crit", "medium": "med"}

# Verbatim scanner word (lowercased) → canonical bucket. Canonical tokens map to themselves
# so the function is idempotent; the legacy short tokens fold in for the same reason.
_CANONICAL: dict[str, str] = {
    "critical": "critical",
    "crit": "critical",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "low": "low",
    "negligible": "negligible",
    "unknown": "unknown",
    **{tok: tok for tok in SEVERITIES},
}


def canonical_severity(raw: object) -> str:
    """Map a scanner severity to its canonical bucket; `unknown` for anything unrecognized."""
    if not isinstance(raw, str):
        return "unknown"
    return _CANONICAL.get(raw.strip().lower(), "unknown")


# The caps of docs/INGEST-CONTRACT.md, which the backend holds with a 422 for the whole envelope:
# 64 paths in one entry, 1,024 characters in one path.
PATH_CAP = 64
_PATH_CHARS = 1024
# a control character, a line or paragraph separator, a format character (bidi, zero-width), and
# a lone surrogate, which has no UTF-8 form: the envelope could not be written with it
_UNSHOWN = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})


class CleanPaths(NamedTuple):
    paths: tuple[str, ...]
    dropped: int  # refused by the rules of the backend
    over_cap: int  # valid, but past the first 64


def _valid(path: object) -> bool:
    return (
        isinstance(path, str)
        and 0 < len(path) <= _PATH_CHARS
        and not any(unicodedata.category(c) in _UNSHOWN for c in path)
    )


def clean_paths(raw: Iterable[object]) -> CleanPaths:
    """The paths of one entry as the backend takes them: each starts with `/` (operator ruling,
    issue 1077), no repeats, the first 64 in sorted order. A file name comes from the image, so a
    path that the backend would refuse is dropped here, not the push of the whole image."""
    kept: set[str] = set()
    dropped = 0
    for path in raw:
        if isinstance(path, str) and path and not path.startswith("/"):
            path = f"/{path}"
        if _valid(path):
            kept.add(str(path))
        else:
            dropped += 1
    ordered = sorted(kept)
    return CleanPaths(tuple(ordered[:PATH_CAP]), dropped, max(0, len(ordered) - PATH_CAP))
