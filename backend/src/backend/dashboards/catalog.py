"""The dashboard panels the backend accepts (issue 440): the same closed list as the frontend's
`src/dashboards/catalog.ts`, which panel-catalog-ids.spec.ts holds equal to this one. A saved
panel names its height (`short` or `tall`), and the backend checks only that name: the rows are
the frontend's first height for a new panel in edit mode, before its content sets the height
(issue 1045), so a new measurement of the heights changes no saved dashboard."""

from dataclasses import dataclass
from typing import Literal

PanelId = Literal[
    "findings-summary",
    "package-type",
    "findings-by-namespace",
    "riskiest-images",
    "top-components",
    "scan-ingest",
    "failed-ingests",
    "triage-activity",
    "handled-findings",
    "triage-progress",
]
PanelHeight = Literal["short", "tall"]


@dataclass(frozen=True)
class CatalogPanel:
    # grid rows of each height the panel can take
    heights: dict[PanelHeight, int]
    uses_scanner: bool


PANELS: dict[str, CatalogPanel] = {
    "findings-summary": CatalogPanel({"short": 7}, uses_scanner=True),
    "package-type": CatalogPanel({"short": 12}, uses_scanner=True),
    "findings-by-namespace": CatalogPanel({"short": 11, "tall": 24}, uses_scanner=True),
    "riskiest-images": CatalogPanel({"short": 13, "tall": 26}, uses_scanner=True),
    "top-components": CatalogPanel({"short": 13, "tall": 26}, uses_scanner=True),
    "scan-ingest": CatalogPanel({"short": 4}, uses_scanner=False),
    "failed-ingests": CatalogPanel({"short": 4}, uses_scanner=False),
    "triage-activity": CatalogPanel({"short": 5}, uses_scanner=False),
    "handled-findings": CatalogPanel({"short": 5}, uses_scanner=False),
    "triage-progress": CatalogPanel({"short": 10}, uses_scanner=False),
}
