"""The javv-scanner chart's settings against the scanner's code (issue 725, slice 3).

Each scanner's `config` block in `deploy/helm/javv-scanner/values.yaml` sets its environment. These
tests hold it to the code, as `backend/tests/test_compose_settings.py` does for the backend:
- read by `TrivyConfig` / `GrypeConfig`, the block is exactly the code's defaults;
- every setting the code reads for that scanner is in its block;
- every `JAVV_` name the scanner reads is either in a block or set by the chart some other way
  (named below, with where), so a new setting cannot ship without its chart value.

The rendered manifests are checked in `backend/tests/test_helm_scanner.py`."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scanner.config import GrypeConfig, TrivyConfig
from scanner.push import RetryBudget

ROOT = Path(__file__).resolve().parents[2]
VALUES = ROOT / "deploy" / "helm" / "javv-scanner" / "values.yaml"
SOURCE = ROOT / "scanner" / "src" / "scanner"

# set by the chart outside `config`, or by the image, or meaningless in a cluster
ELSEWHERE = {
    "JAVV_BACKEND_URL": "backendUrl",
    "JAVV_TOKEN": "<scanner>.token, from a Secret",
    "JAVV_CLUSTER_ID": "clusterId",
    "JAVV_SCANNER": "the image's ENV (one image per scanner)",
    "JAVV_DEAD_LETTER": "the image's ENV, on the chart's /var/lib/javv emptyDir",
    "JAVV_KUBE_CONTEXT": "out of a cluster only; in one the scanner uses its ServiceAccount",
}
OWN_PREFIX = {"trivy": "JAVV_TRIVY_", "grype": "JAVV_GRYPE_"}
# one per scanner block: javv_common's logging, and the cycle's retry budget
SHARED = {"JAVV_LOG_LEVEL", "JAVV_PUSH_RETRY_BUDGET_SECONDS"}


def _config(scanner: str) -> dict[str, str]:
    values: dict[str, Any] = yaml.safe_load(VALUES.read_text())
    return {k: str(v) for k, v in values[scanner]["config"].items()}


def _read_by_the_scanner() -> set[str]:
    names = set()
    for path in SOURCE.rglob("*.py"):
        names |= set(re.findall(r'"(JAVV_[A-Z_]+)"', path.read_text()))
    return names


def test_each_block_is_the_code_default() -> None:
    assert TrivyConfig.from_env(_config("trivy")) == TrivyConfig()
    assert GrypeConfig.from_env(_config("grype")) == GrypeConfig()
    for scanner in OWN_PREFIX:
        assert _config(scanner)["JAVV_LOG_LEVEL"] == "info"  # javv_common's default
        assert RetryBudget.from_env(_config(scanner)) == RetryBudget.from_env({})


@pytest.mark.parametrize("scanner", list(OWN_PREFIX))
def test_every_setting_of_the_scanner_is_in_its_block(scanner: str) -> None:
    prefix = OWN_PREFIX[scanner]
    read = {name for name in _read_by_the_scanner() if name.startswith(prefix)}
    assert read, f"found no {prefix} setting in the scanner's source"
    assert set(_config(scanner)) == read | SHARED


def test_every_javv_name_the_scanner_reads_has_a_home_in_the_chart() -> None:
    in_blocks = set(_config("trivy")) | set(_config("grype"))
    homeless = _read_by_the_scanner() - in_blocks - set(ELSEWHERE)
    assert not homeless, f"{sorted(homeless)}: add each to a config block in {VALUES.name}"
