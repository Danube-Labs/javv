"""Severity canonicalization (D16): each scanner's verbatim severity word maps to one of the
six canonical buckets (crit/high/med/low/negligible/unknown). Grype's Negligible/Unknown are
kept, not folded ("other" is a UI render concern, not normalization). Unrecognized/missing
input is `unknown` — never `crit`. The verbatim word is preserved by the caller, not here."""

import json
from pathlib import Path

import pytest

from scanner.normalize import PATH_CAP, SEVERITIES, canonical_severity, clean_paths

FIXTURES = Path(__file__).parent / "fixtures"


def test_severities_are_the_fixed_order_map_highest_first() -> None:
    # AUDIT-RESPONSE: crit > high > med > low > negligible > unknown
    assert SEVERITIES == ("critical", "high", "medium", "low", "negligible", "unknown")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Trivy ramp (UPPERCASE; no "negligible")
        ("CRITICAL", "critical"),
        ("HIGH", "high"),
        ("MEDIUM", "medium"),
        ("LOW", "low"),
        ("UNKNOWN", "unknown"),
        # Grype ramp (TitleCase; adds Negligible)
        ("Critical", "critical"),
        ("High", "high"),
        ("Medium", "medium"),
        ("Low", "low"),
        ("Negligible", "negligible"),
        ("Unknown", "unknown"),
    ],
)
def test_maps_each_scanner_word_to_canonical(raw: str, expected: str) -> None:
    assert canonical_severity(raw) == expected


@pytest.mark.parametrize("raw", ["critical", "Critical", "CRITICAL", "cRiTiCaL", " critical "])
def test_is_case_and_whitespace_insensitive(raw: str) -> None:
    assert canonical_severity(raw) == "critical"


@pytest.mark.parametrize("raw", ["", "   ", "moderate", "severe", "bogus", "none", "0"])
def test_unrecognized_is_unknown_never_crit(raw: str) -> None:
    assert canonical_severity(raw) == "unknown"


@pytest.mark.parametrize("raw", [None, 123, [], {}])
def test_non_string_or_missing_is_unknown(raw: object) -> None:
    # scanner input is untrusted — must never raise
    assert canonical_severity(raw) == "unknown"  # type: ignore[arg-type]


def test_is_idempotent_on_canonical_tokens() -> None:
    for tok in SEVERITIES:
        assert canonical_severity(tok) == tok


def test_every_real_fixture_severity_canonicalizes_into_the_bucket_set() -> None:
    seen: set[str] = set()
    for fx in FIXTURES.glob("trivy-*.json"):
        d = json.loads(fx.read_text())
        for res in d.get("Results") or []:
            for v in res.get("Vulnerabilities") or []:
                seen.add(canonical_severity(v.get("Severity")))
    for fx in FIXTURES.glob("grype-*.json"):
        d = json.loads(fx.read_text())
        for m in d.get("matches") or []:
            seen.add(canonical_severity((m.get("vulnerability") or {}).get("severity")))

    assert seen, "fixtures yielded no severities"
    assert seen <= set(SEVERITIES)


# --- the file paths of an entry (issue 1077) ---


def test_a_path_gets_its_first_slash_and_repeats_go() -> None:
    """Trivy writes `usr/local/go/bin/go` and Grype `/usr/local/go/bin/go` for one file: the
    operator ruled that every path starts with `/`, so the two scanners give the same text."""
    got = clean_paths(["usr/local/go/bin/go", "/usr/local/go/bin/go", "/app/b.jar", "/app/b.jar"])
    assert got.paths == ("/app/b.jar", "/usr/local/go/bin/go")
    assert (got.dropped, got.over_cap) == (0, 0)


def test_no_path_gives_an_empty_result() -> None:
    assert clean_paths([]) == clean_paths(()) and clean_paths([]).paths == ()


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/" + "a" * 1024,  # 1,025 characters
        *("/a\x00b", "/a\nb", "/a\x7fb"),  # ASCII controls
        *("/a\x85b", "/a\u2028b"),  # a C1 control, a line separator
        *("/a\u202eb", "/a\u200bb"),  # a bidi override, a zero-width space
        "/a\udc80b",  # a lone surrogate: no UTF-8 text, so the envelope could not be written
        7,
        None,
    ],
)
def test_a_path_that_the_backend_refuses_is_dropped_and_counted(bad: object) -> None:
    """The backend refuses the whole envelope for one bad path (issue 1077, review round 1), and
    a file name comes from the image: the scanner drops the path, not the push of the image."""
    got = clean_paths(["/ok", bad])
    assert got.paths == ("/ok",)
    assert got.dropped == 1


def test_a_path_of_1024_characters_and_letters_of_any_language_pass() -> None:
    long = "/" + "a" * 1023
    assert clean_paths(["/opt/café/データ.jar", long]).paths == (long, "/opt/café/データ.jar")


def test_an_entry_keeps_the_first_64_sorted_paths() -> None:
    raw = [f"/opt/app/{i:03d}.jar" for i in reversed(range(PATH_CAP + 6))]
    got = clean_paths(raw)
    assert PATH_CAP == 64
    assert got.paths == tuple(sorted(raw)[:PATH_CAP])
    assert (got.dropped, got.over_cap) == (0, 6)
