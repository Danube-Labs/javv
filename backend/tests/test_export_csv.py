"""M6 slice 5 — CSV export units: the injection sanitizer + the row serializer.

Pins: every dangerous leading char (`=`, `+`, `-`, `@`, tab, CR) is neutralized with a leading
apostrophe (the standard spreadsheet mitigation) so a cell can never execute as a formula;
benign values pass through untouched; the golden bait fixture locks the full serialized shape
(header order + quoting + sanitization) so a refactor can't silently unsanitize a column.
"""

import csv
import io
import json
import pathlib

import pytest

from backend.export.csv_stream import CSV_COLUMNS, csv_line, csv_row, sanitize_cell

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "bait", ["=cmd()", "+SUM(A1)", "-2+3", "@import", "\tpayload", "\rpayload"]
)
def test_dangerous_leading_chars_are_neutralized(bait: str) -> None:
    out = sanitize_cell(bait)
    assert out.startswith("'")
    assert out[1:] == bait  # neutralized, never mangled — the analyst still sees the raw value


def test_benign_values_pass_through() -> None:
    assert sanitize_cell("CVE-2024-1234") == "CVE-2024-1234"
    assert sanitize_cell("pkg with = inside") == "pkg with = inside"  # only the LEADING char arms
    assert sanitize_cell("") == ""


def test_csv_injection_bypass_corpus_stays_neutralized_or_inert() -> None:
    """A-m13 (audit #192): a REGRESSION lock, not a fix — review confirmed the sanitizer has
    no live bypass in the target consumers. This corpus freezes that behavior so a future refactor
    can't silently weaken it. Do NOT change the sanitizer to make these pass differently."""
    # ASCII formula leads → neutralized with a leading apostrophe
    assert sanitize_cell("=1+1") == "'=1+1"
    assert sanitize_cell("\t=formula") == "'\t=formula"  # tab is a trigger
    assert sanitize_cell("\r=formula") == "'\r=formula"  # CR is a trigger
    # list elements are sanitized ELEMENT-WISE before the ';' join — no re-split bypass
    assert sanitize_cell(["=cmd", "ok", "=x"]) == "'=cmd;ok;'=x"
    # provably inert in the target consumers (review-verified) — pass through unchanged:
    assert sanitize_cell(" =1+1") == " =1+1"  # a leading ASCII space doesn't arm the formula
    assert sanitize_cell("﻿=1") == "﻿=1"  # BOM / zero-width prefix doesn't arm
    assert sanitize_cell("＝1+1") == "＝1+1"  # full-width homoglyph is not a formula char
    assert sanitize_cell('"=1') == '"=1'  # a quote before '=' isn't a leading formula char


def test_non_strings_serialize_plainly() -> None:
    assert sanitize_cell(None) == ""
    assert sanitize_cell(True) == "true"
    assert sanitize_cell(False) == "false"
    assert sanitize_cell(7.5) == "7.5"
    assert sanitize_cell(["default", "kube-system"]) == "default;kube-system"


def test_a_negative_number_is_not_a_formula() -> None:
    # numeric -1 is data; only a STRING starting with "-" can be a formula in a spreadsheet
    assert sanitize_cell(-1) == "-1"
    assert sanitize_cell("-1") == "'-1"


def test_golden_bait_findings_serialize_sanitized() -> None:
    """The checked-in bait findings → the checked-in sanitized CSV, byte for byte."""
    docs = json.loads((FIXTURES / "csv-bait-findings.json").read_text())
    lines = [csv_line(CSV_COLUMNS)] + [csv_row(d) for d in docs]
    # bytes, not read_text: universal newlines would translate a sanitized CR bait cell
    expected = (FIXTURES / "csv-bait-golden.csv").read_bytes().decode()
    assert "".join(lines) == expected


def test_the_paths_go_one_on_each_line_of_one_cell() -> None:
    """Issue 1245, D1 A: ingest refuses a control character in a path, so a new line splits the
    paths of the cell with no doubt. A `;` or a `,` is part of a path. Each path is sanitized."""
    doc = {"locations": ["/opt/a;b,c/lib.so", "=1+1.jar", "/usr/lib/x"], "locations_total": 70}
    row = next(csv.reader(io.StringIO(csv_row(doc))))
    assert CSV_COLUMNS[-2:] == ("locations_total", "locations")
    assert row[-2] == "70"
    assert row[-1].split("\n") == ["/opt/a;b,c/lib.so", "'=1+1.jar", "/usr/lib/x"]


def test_a_finding_with_no_paths_has_empty_cells() -> None:
    """`null` (a scanner of schema 3 or 4) and `[]` (no path found) both give an empty cell; the
    count tells them apart: empty for `null`, 0 for `[]`."""
    unknown = next(csv.reader(io.StringIO(csv_row({"locations": None, "locations_total": None}))))
    none = next(csv.reader(io.StringIO(csv_row({"locations": [], "locations_total": 0}))))
    assert unknown[-2:] == ["", ""]
    assert none[-2:] == ["0", ""]
