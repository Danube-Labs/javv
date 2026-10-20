"""The install commands in each chart README set `VERSION=` to the version of that chart. The
template takes it from `Chart.yaml` through helm-docs, and the release PR writes the READMEs again
from the moved `Chart.yaml`. A `<version>` placeholder is not allowed: a command with one fails
when the reader pastes it."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHARTS = ("javv", "javv-opensearch", "javv-scanner")
VERSION_LINE = re.compile(r"^\s*VERSION=(?P<value>.+?)\s*$", re.M)
FROM_CHART = '{{ template "chart.version" . }}'


@pytest.mark.parametrize("chart", CHARTS)
def test_the_template_takes_each_version_from_the_chart(chart: str) -> None:
    template = (ROOT / "deploy" / "helm" / chart / "README.md.gotmpl").read_text()
    values = VERSION_LINE.findall(template)
    assert values, f"{chart}: the install commands set no VERSION"
    assert set(values) == {FROM_CHART}
    assert "<version>" not in template


@pytest.mark.parametrize("chart", CHARTS)
def test_the_readme_names_the_version_of_the_chart(chart: str) -> None:
    folder = ROOT / "deploy" / "helm" / chart
    version = yaml.safe_load((folder / "Chart.yaml").read_text())["version"]
    readme = (folder / "README.md").read_text()
    assert set(VERSION_LINE.findall(readme)) == {version}
    assert "<version>" not in readme
