"""The published ingest contract (docs/ingest-envelope.schema.json) must never drift from the
wire model — the schema file is GENERATED from `IngestEnvelope.model_json_schema()` and this
test is the CI gate that keeps the two identical. Regenerate after any envelope change:

    cd backend && uv run python -c "
    import json
    from backend.models.envelope import IngestEnvelope
    with open('../docs/ingest-envelope.schema.json', 'w') as f:
        json.dump(IngestEnvelope.model_json_schema(), f, indent=2, sort_keys=True)
        f.write('\\n')"
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel

from backend.models.envelope import (
    GrypeTuning,
    IngestCounts,
    IngestEffectiveConfig,
    IngestEnvelope,
    IngestFinding,
    IngestScope,
    TrivyTuning,
)
from backend.routers.inventory_runs import CommitInventoryRun

SCHEMA_DOC = Path(__file__).parents[2] / "docs" / "ingest-envelope.schema.json"

# the page names each field by its full path; Trivy and Grype tuning share a prefix and never a name
_FIELD_GROUPS: list[tuple[str, type[BaseModel]]] = [
    ("", IngestEnvelope),
    ("counts.", IngestCounts),
    ("effective_config.", IngestEffectiveConfig),
    ("effective_config.tuning.", TrivyTuning),
    ("effective_config.tuning.", GrypeTuning),
    ("effective_config.scope.", IngestScope),
    ("findings[].", IngestFinding),
    ("inventory.", CommitInventoryRun),
]


def test_published_schema_matches_the_wire_model() -> None:
    committed = json.loads(SCHEMA_DOC.read_text())
    generated = IngestEnvelope.model_json_schema()
    assert committed == generated, (
        "docs/ingest-envelope.schema.json drifted from IngestEnvelope — regenerate it "
        "(command in this file's docstring) and commit both in the same PR"
    )


def test_golden_fixture_validates_against_the_published_contract() -> None:
    # a schema 3 envelope still validates: the contract accepts versions 3 and 4
    fixture = Path(__file__).parent / "fixtures" / "envelope-trivy-v3-golden.json"
    IngestEnvelope.model_validate_json(fixture.read_text())


def test_the_example_on_the_contract_page_validates() -> None:
    """docs/INGEST-CONTRACT.md says that a test validates its example envelope: this one. The
    envelope is the heredoc of the page's curl example, with `$ORDER` from the scan-runs call."""
    page = (SCHEMA_DOC.parent / "INGEST-CONTRACT.md").read_text()
    [heredoc] = re.findall(r"<<EOF\n(.*?)\nEOF\n", page, re.S)
    envelope = IngestEnvelope.model_validate_json(heredoc.replace("$ORDER", "1"))
    assert (envelope.schema_version, len(envelope.findings)) == (4, 1)


def _page_field_levels() -> dict[str, str]:
    """`{path: level}` from the rows of the page's "Field reference" tables."""
    page = (SCHEMA_DOC.parent / "INGEST-CONTRACT.md").read_text()
    [section] = re.findall(r"^## Field reference\n(.*?)^## ", page, re.S | re.M)
    rows = re.findall(r"^\| `([^`]+)` \| (required|optional) \|", section, re.M)
    paths = [path for path, _ in rows]
    assert len(paths) == len(set(paths)), "a field has two rows on the page"
    return dict(rows)


def test_the_field_reference_on_the_page_matches_the_wire_model() -> None:
    """The page tells a script author, or an agent, each field and whether to send it: a field the
    model gained, lost, or made optional must show on the page in the same PR."""
    expected = {
        prefix + name: "required" if field.is_required() else "optional"
        for prefix, model in _FIELD_GROUPS
        for name, field in model.model_fields.items()
    }
    assert _page_field_levels() == expected
