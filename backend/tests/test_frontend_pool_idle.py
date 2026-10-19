"""The frontend server closes an idle pooled connection to the backend before the backend does
(issue 924). If the backend closes first, a request that the frontend server sends on that
connection at the same moment gets a reset, and the browser gets a 502.

These tests keep the order of the two times: `BACKEND_IDLE_MS` in `frontend/server/serve.mjs`
against the keep-alive time of the backend image. The image starts uvicorn, which takes that time
from `--timeout-keep-alive` or from the `UVICORN_TIMEOUT_KEEP_ALIVE` variable, else its default.
"""

import json
import re
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
FLAG = "--timeout-keep-alive"
ENV = "UVICORN_TIMEOUT_KEEP_ALIVE"
# The two timers start a few milliseconds apart and fire with some delay, so equal or nearly equal
# times would bring the race back
MARGIN_MS = 500


def _frontend_idle_ms() -> int:
    source = (ROOT / "frontend" / "server" / "serve.mjs").read_text()
    match = re.search(r"^export const BACKEND_IDLE_MS = ([\d_]+)$", source, re.MULTILINE)
    assert match, "serve.mjs no longer exports BACKEND_IDLE_MS as a number"
    return int(match.group(1).replace("_", ""))


def _backend_command() -> list[str]:
    lines = (ROOT / "backend" / "Dockerfile").read_text().splitlines()
    [cmd] = [line for line in lines if line.startswith("CMD ")]
    return json.loads(cmd.removeprefix("CMD "))


def test_the_backend_image_starts_uvicorn() -> None:
    assert _backend_command()[0] == "uvicorn"


def test_the_frontend_server_closes_an_idle_connection_first() -> None:
    command = _backend_command()
    if FLAG in command:
        keep_alive_s = float(command[command.index(FLAG) + 1])
    else:
        keep_alive_s = float(uvicorn.Config("backend.main:app").timeout_keep_alive)
    assert _frontend_idle_ms() <= keep_alive_s * 1000 - MARGIN_MS, (
        f"the frontend server keeps an idle connection {_frontend_idle_ms()} ms, the backend "
        f"{keep_alive_s} s: the frontend server must close first (issue 924)"
    )


def test_no_deployment_changes_the_backend_keep_alive_out_of_sight() -> None:
    # a change here would bypass the test above: put it in the Dockerfile's CMD instead
    places = [
        ROOT / "backend" / "Dockerfile",
        *(p for p in (ROOT / "deploy").rglob("*") if p.is_file()),
    ]
    found = [
        str(p.relative_to(ROOT))
        for p in places
        if ENV in p.read_text(errors="ignore")
        or (p.name != "Dockerfile" and FLAG in p.read_text(errors="ignore"))
    ]
    assert found == []
