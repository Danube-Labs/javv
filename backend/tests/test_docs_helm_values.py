"""Each `--set <key>` of a `helm install` or `helm upgrade` in the docs is a value of the chart that
the command names (issue 1126). Helm takes an unknown key with no error, so a typo, or a key that a
chart renamed, would do nothing on the install of a reader. The keys of the OpenSearch subchart are
in its package, under the name of the subchart."""

import re
import tarfile
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHARTS = ROOT / "deploy" / "helm"
PAGES = (
    "docs/DEPLOYING.md",
    "docs/UPGRADING.md",
    "docs/use/use-the-mcp-server.md",
    "deploy/helm/javv/README.md.gotmpl",
    "deploy/helm/javv-opensearch/README.md.gotmpl",
    "deploy/helm/javv-scanner/README.md.gotmpl",
)
COMMAND = re.compile(r"\bhelm\s+(?:install|upgrade)\s+\S+\s+(?P<chart>\S+)")
SET = re.compile(r"--set\s+(?P<key>[^=\s]+)=")


def commands(text: str) -> list[str]:
    """Each helm install or upgrade in the fenced blocks, with its continued lines joined."""
    found: list[str] = []
    in_fence = False
    current = ""
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        current = f"{current} {line.strip()}" if current else line.strip()
        if current.endswith("\\"):
            current = current[:-1]
            continue
        if COMMAND.search(current):
            found.append(" ".join(current.split()))
        current = ""
    return found


def _merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in over.items():
        both = isinstance(value, dict) and isinstance(out.get(key), dict)
        out[key] = _merge(out[key], value) if both else value
    return out


def chart_values(name: str) -> dict[str, Any]:
    """The values of a chart, with the values of each packaged subchart under its name."""
    chart = CHARTS / name
    values = yaml.safe_load((chart / "values.yaml").read_text()) or {}
    for package in sorted((chart / "charts").glob("*.tgz")):
        with tarfile.open(package) as tar:
            member = next(
                m
                for m in tar.getmembers()
                if m.name.count("/") == 1 and m.name.endswith("/values.yaml")
            )
            sub = member.name.split("/")[0]
            data = tar.extractfile(member)
            assert data is not None
            values[sub] = _merge(yaml.safe_load(data.read()) or {}, values.get(sub) or {})
    return values


def unknown_keys(command: str) -> list[str]:
    match = COMMAND.search(command)
    assert match, command
    values = chart_values(match["chart"].rstrip("/").split("/")[-1])
    missing = []
    for key in SET.findall(command):
        node: Any = values
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                missing.append(key)
                break
            node = node[part]
    return missing


def test_the_rule_finds_a_key_that_the_chart_does_not_have() -> None:
    good = (
        "helm install store oci://x/javv-opensearch --set opensearch.resources.requests.memory=2Gi"
    )
    assert unknown_keys(good) == []
    assert unknown_keys(good.replace("requests.memory", "request.memory")) == [
        "opensearch.resources.request.memory"
    ]
    page = "```bash\nhelm install s deploy/helm/javv-scanner \\\n  --set backendUrl=http://j:8080\n```\n"
    assert commands(page) == [
        "helm install s deploy/helm/javv-scanner --set backendUrl=http://j:8080"
    ]


@pytest.mark.parametrize("page", PAGES)
def test_each_set_key_is_a_value_of_its_chart(page: str) -> None:
    found = commands((ROOT / page).read_text())
    assert found, f"{page} has no helm install or upgrade"
    assert {command: unknown_keys(command) for command in found} == dict.fromkeys(found, [])
