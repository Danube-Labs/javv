#!/usr/bin/env python3
"""The Python half of image-ab.sh (issue 1263): the reads, the findings, and the report.

  python3 development/e2e/image_ab.py reads <base url> <openapi.json> <cluster id> <rounds>
        the GET routes that take no path value, as the admin (JAVV_AB_PASSWORD), one JSON line
        for each: path, status, the time of each round, the body of the first round
  python3 development/e2e/image_ab.py findings <base url> <cluster id> <scanner>
        the findings that JAVV holds for that cluster and scanner, as sorted rows
  python3 development/e2e/image_ab.py vulns <trivy.json> <grype.json>
        the findings of one image in each scanner's own report: OS, language, with a fix
  python3 development/e2e/image_ab.py report <run folder>
        writes report.md, exit 1 when the two runs work differently

The run folder has `old/` and `new/`, each written by image-ab.sh:
  facts.json          the facts of each image: size, layers, config, the tools on its PATH,
                      the package count and the findings of each scanner
  times.json          start seconds, the seconds of each scan cycle, the memory of each container
  reads.jsonl         the output of `reads`
  logs/<name>.log     the output of each container and each scan cycle
  scan/<scanner>.json the exit code of the scan cycle of that scanner image, and `findings`

The report fails on a read with another status or another body, a scan cycle that failed or
left other findings, and log events at warning or error level that only the new run has. The
image facts may change: an image change is for them, so they are in the report but never fail it.
"""

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

# values that change from run to run, so the compare leaves them out
VOLATILE = re.compile(
    r"(^|_)(at|time|timestamp|took|ms|seconds|cursor|pit|session|token|expires|date|day|"
    r"created|updated|started|finished|heartbeat|until|since)$|^(id|uuid|etag|ts|scan_order)$|_ids?$"
)
# live measures: they change while the same code runs
MEASURE = re.compile(r"_(used|free)(_mb|_bytes)?$")
NOT_FAILING_LEVELS = {"debug", "info"}
# the values in a line of plain text that change from run to run
PLAIN_VALUES = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ][\d:.,]+Z?"), "<time>"),
    (
        re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"),
        "<uuid>",
    ),
    (re.compile(r"sha256:[0-9a-f]+"), "<digest>"),
    (re.compile(r"\b[a-z]+_[a-z]+\b(?=')"), "<name>"),
    (re.compile(r"\d+(\.\d+)?"), "<n>"),
]


def plain_shape(line: str) -> str:
    """A line of plain text without the values that change from run to run."""
    for pattern, placeholder in PLAIN_VALUES:
        line = pattern.sub(placeholder, line)
    return line


def normalize(value):
    """The body without the values that change between two runs of the same code."""
    if isinstance(value, dict):
        return {
            k: normalize(v)
            for k, v in sorted(value.items())
            if not VOLATILE.search(k) and not MEASURE.search(k)
        }
    if isinstance(value, list):
        return [normalize(v) for v in value]
    # a container ID (the node name of the store): each stack has its own
    if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{12}", value):
        return "<container>"
    if isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}([T ][\d:.]+)?(Z|[+-]\d{2}:?\d{2})?", value
    ):
        return "<time>"
    return value


def log_shape(lines):
    """The events of a log: each event with its keys, the levels, and the lines that are no JSON."""
    events: dict[str, set[str]] = {}
    levels: Counter[str] = Counter()
    plain: list[str] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            plain.append(plain_shape(line))
            continue
        if not isinstance(rec, dict):
            plain.append(plain_shape(line))
            continue
        name = str(rec.get("event", "<no event>"))
        events.setdefault(name, set()).update(rec)
        levels[str(rec.get("level", "<no level>")).lower()] += 1
    return {"events": events, "levels": levels, "plain": plain}


def compare_logs(old, new):
    """What changed in the shape of a log. `failing` holds the changes that fail the report."""
    o, n = log_shape(old), log_shape(new)
    only_old = sorted(set(o["events"]) - set(n["events"]))
    only_new = sorted(set(n["events"]) - set(o["events"]))
    keys = {
        e: (
            sorted(o["events"][e] - n["events"][e]),
            sorted(n["events"][e] - o["events"][e]),
        )
        for e in sorted(set(o["events"]) & set(n["events"]))
        if o["events"][e] != n["events"][e]
    }
    new_plain = sorted(set(n["plain"]) - set(o["plain"]))
    failing = []
    for e in only_new:
        lvl = {json.loads(x).get("level", "").lower() for x in new if _is_event(x, e)}
        if lvl - NOT_FAILING_LEVELS:
            failing.append(f"new event `{e}` at level {', '.join(sorted(lvl))}")
    for level in set(n["levels"]) - NOT_FAILING_LEVELS:
        if n["levels"][level] > o["levels"].get(level, 0):
            failing.append(
                f"more `{level}` lines: {o['levels'].get(level, 0)} -> {n['levels'][level]}"
            )
    if new_plain:
        failing.append(f"{len(new_plain)} new lines that are not JSON")
    return {
        "only_old": only_old,
        "only_new": only_new,
        "keys": keys,
        "levels": (dict(o["levels"]), dict(n["levels"])),
        "new_plain": new_plain,
        "failing": failing,
    }


def _is_event(line, name):
    try:
        rec = json.loads(line)
    except ValueError:
        return False
    return isinstance(rec, dict) and str(rec.get("event")) == name


def timing(samples):
    """Median and 95th percentile in milliseconds, from seconds."""
    if not samples:
        return None
    ms = sorted(s * 1000 for s in samples)
    p95 = ms[min(len(ms) - 1, max(0, round(0.95 * len(ms)) - 1))]
    return {
        "median": round(statistics.median(ms), 1),
        "p95": round(p95, 1),
        "n": len(ms),
    }


def compare_reads(old, new):
    """The reads of the two runs by path: a status or a body that differs fails the report."""
    o = {r["path"]: r for r in old}
    n = {r["path"]: r for r in new}
    rows, failing = [], []
    for path in sorted(set(o) | set(n)):
        a, b = o.get(path), n.get(path)
        if a is None or b is None:
            failing.append(f"`{path}` was read in one run only")
            continue
        same_body = normalize(a.get("body")) == normalize(b.get("body"))
        if a["status"] != b["status"]:
            failing.append(f"`{path}`: status {a['status']} -> {b['status']}")
        elif not same_body:
            failing.append(f"`{path}`: the body differs")
        rows.append(
            (
                path,
                a["status"],
                b["status"],
                same_body,
                timing(a["times"]),
                timing(b["times"]),
            )
        )
    return rows, failing


def compare_scan(old, new):
    """The findings that JAVV holds after a scan cycle of each scanner image must be the same."""
    failing = []
    if old.get("exit") != 0 or new.get("exit") != 0:
        failing.append(f"scan cycle exit {old.get('exit')} -> {new.get('exit')}")
    a = {tuple(f) for f in old.get("findings", [])}
    b = {tuple(f) for f in new.get("findings", [])}
    if a != b:
        failing.append(
            f"findings {len(a)} -> {len(b)} ({len(a - b)} only old, {len(b - a)} only new)"
        )
    return {"old": len(a), "new": len(b), "same": a == b}, failing


def _ms(t) -> str:
    return f"{t['median']}, {t['p95']}" if t else "-"


def _cell(v):
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    return str(v)


def report(run: Path) -> tuple[str, list[str]]:
    old, new = run / "old", run / "new"
    out, failing = ["# Image A/B report", ""], []

    fo, fn = (
        json.loads((old / "facts.json").read_text()),
        json.loads((new / "facts.json").read_text()),
    )
    out += ["## Images", ""]
    for name in sorted(set(fo) | set(fn)):
        a, b = fo.get(name, {}), fn.get(name, {})
        out += [f"### {name}", "", "| Fact | Old | New |", "|---|---|---|"]
        for key in sorted(set(a) | set(b)):
            va, vb = _cell(a.get(key)), _cell(b.get(key))
            mark = "" if va == vb else " **changed**"
            out.append(f"| {key}{mark} | `{va}` | `{vb}` |")
        out.append("")

    ro = [json.loads(x) for x in (old / "reads.jsonl").read_text().splitlines() if x]
    rn = [json.loads(x) for x in (new / "reads.jsonl").read_text().splitlines() if x]
    rows, f = compare_reads(ro, rn)
    failing += f
    out += [
        "## Reads",
        "",
        (
            "| Route | Status old | Status new | Same body | Old ms (median, p95) "
            "| New ms (median, p95) |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for path, sa, sb, same, ta, tb in rows:
        out.append(
            f"| `{path}` | {sa} | {sb} | {'yes' if same else '**no**'} | {_ms(ta)} | {_ms(tb)} |"
        )
    out.append("")

    out += [
        "## Scan cycles",
        "",
        "| Scanner image | Findings old | Findings new | Same |",
        "|---|---|---|---|",
    ]
    for scan in sorted(
        {p.name for p in (old / "scan").glob("*.json")}
        | {p.name for p in (new / "scan").glob("*.json")}
    ):
        a = (
            json.loads((old / "scan" / scan).read_text())
            if (old / "scan" / scan).exists()
            else {}
        )
        b = (
            json.loads((new / "scan" / scan).read_text())
            if (new / "scan" / scan).exists()
            else {}
        )
        res, f = compare_scan(a, b)
        failing += [f"{scan}: {x}" for x in f]
        same = "yes" if res["same"] else "**no**"
        out.append(
            f"| {scan.removesuffix('.json')} | {res['old']} | {res['new']} | {same} |"
        )
    out.append("")

    out += ["## Logs", ""]
    for log in sorted(
        {p.name for p in (old / "logs").glob("*.log")}
        | {p.name for p in (new / "logs").glob("*.log")}
    ):
        a = (
            (old / "logs" / log).read_text().splitlines()
            if (old / "logs" / log).exists()
            else []
        )
        b = (
            (new / "logs" / log).read_text().splitlines()
            if (new / "logs" / log).exists()
            else []
        )
        c = compare_logs(a, b)
        failing += [f"{log}: {x}" for x in c["failing"]]
        out += [
            f"### {log}",
            "",
            f"- Levels: old `{c['levels'][0]}`, new `{c['levels'][1]}`",
        ]
        out.append(
            f"- Events only in the old run: {', '.join(f'`{e}`' for e in c['only_old']) or 'none'}"
        )
        out.append(
            f"- Events only in the new run: {', '.join(f'`{e}`' for e in c['only_new']) or 'none'}"
        )
        for e, (lost, added) in c["keys"].items():
            out.append(
                f"- `{e}`: keys only old {lost or 'none'}, keys only new {added or 'none'}"
            )
        for line in c["new_plain"][:20]:
            out.append(f"- New line that is not JSON: `{line[:160]}`")
        out.append("")

    to, tn = (
        json.loads((old / "times.json").read_text()),
        json.loads((new / "times.json").read_text()),
    )
    out += ["## Times and memory", "", "| Measure | Old | New |", "|---|---|---|"]
    for key in sorted(set(to) | set(tn)):
        out.append(f"| {key} | {_cell(to.get(key))} | {_cell(tn.get(key))} |")
    out.append("")

    out += ["## Verdict", ""]
    out += (
        [f"- {x}" for x in failing]
        if failing
        else ["The new images work as the old images do."]
    )
    return "\n".join(out) + "\n", failing


# required query values that a route can take with a fixed value; a route that needs any other
# value is left out of the reads
FIXED_VALUES = {"by": "severity", "scanner": "trivy"}
# the frontend forwards /api, /auth and /readyz only (frontend/server/serve.mjs)
FORWARDED = ("/api/", "/auth/", "/readyz")
NOT_READ = ("/api/v1/mcp",)


def routes(openapi: dict) -> list[tuple[str, dict[str, str]]]:
    """The GET routes that take no path value, each with the query values it gets."""
    out = []
    for path, ops in sorted(openapi["paths"].items()):
        get = ops.get("get")
        if (
            get is None
            or "{" in path
            or not path.startswith(FORWARDED)
            or path.startswith(NOT_READ)
        ):
            continue
        params = {
            p["name"]: p for p in get.get("parameters", []) if p.get("in") == "query"
        }
        query = {}
        if "cluster_id" in params:
            query["cluster_id"] = "<cluster>"
        missing = [
            n
            for n, p in params.items()
            if p.get("required") and n != "cluster_id" and n not in FIXED_VALUES
        ]
        if missing:
            continue
        query.update(
            {
                n: FIXED_VALUES[n]
                for n, p in params.items()
                if p.get("required") and n in FIXED_VALUES
            }
        )
        out.append((path, query))
    return out


def body_of(content_type: str, raw: bytes):
    """A JSON body as it is, any other body by its first line and its line count (a CSV export)."""
    if "json" in content_type and "ndjson" not in content_type:
        try:
            return json.loads(raw)
        except ValueError:
            pass
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    return {
        "content_type": content_type.split(";")[0],
        "first_line": lines[0] if lines else "",
        "lines": len(lines),
    }


def finding_row(f: dict) -> list:
    return [
        f.get(k)
        for k in (
            "scanner",
            "cve_id",
            "package_name",
            "installed_version",
            "severity_canonical",
            "fixed_version",
            "image_repo",
        )
    ]


def summarize_vulns(trivy: dict, grype: dict) -> dict:
    """The findings of one image in each scanner's report, by OS or language, and with a fix."""
    t = [
        (r.get("Class"), v.get("Status"))
        for r in trivy.get("Results") or []
        for v in r.get("Vulnerabilities") or []
    ]
    g = [
        (m["artifact"]["type"], (m["vulnerability"].get("fix") or {}).get("state"))
        for m in grype.get("matches") or []
    ]
    return {
        "trivy_os": sum(c == "os-pkgs" for c, _ in t),
        "trivy_language": sum(c != "os-pkgs" for c, _ in t),
        "trivy_with_fix": sum(s == "fixed" for _, s in t),
        "grype_os": sum(c in ("deb", "apk", "rpm") for c, _ in g),
        "grype_language": sum(c not in ("deb", "apk", "rpm") for c, _ in g),
        "grype_with_fix": sum(s == "fixed" for _, s in g),
    }


def _session(base: str):
    import http.cookiejar
    import os
    import urllib.request

    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )
    login = json.dumps(
        {"username": "admin", "password": os.environ["JAVV_AB_PASSWORD"]}
    ).encode()
    req = urllib.request.Request(
        f"{base}/auth/login", login, {"content-type": "application/json"}
    )
    opener.open(req, timeout=30).read()
    return opener


def _get(opener, url: str):
    import time
    import urllib.error

    t0 = time.monotonic()
    try:
        with opener.open(url, timeout=120) as r:
            raw, status, ctype = r.read(), r.status, r.headers.get("content-type", "")
    except urllib.error.HTTPError as e:
        raw, status, ctype = e.read(), e.code, e.headers.get("content-type", "")
    return status, ctype, raw, time.monotonic() - t0


def cmd_reads(base: str, openapi: str, cluster: str, rounds: str) -> int:
    from urllib.parse import urlencode

    opener = _session(base)
    for path, query in routes(json.loads(Path(openapi).read_text())):
        q = {k: (cluster if v == "<cluster>" else v) for k, v in query.items()}
        url = f"{base}{path}" + (f"?{urlencode(q)}" if q else "")
        times, first = [], None
        for _ in range(int(rounds)):
            status, ctype, raw, secs = _get(opener, url)
            times.append(secs)
            first = first or (status, body_of(ctype, raw))
        sys.stdout.write(
            json.dumps(
                {"path": path, "status": first[0], "times": times, "body": first[1]}
            )
            + "\n"
        )
    return 0


def cmd_findings(base: str, cluster: str, scanner: str) -> int:
    from urllib.parse import urlencode

    opener = _session(base)
    rows, cursor = [], None
    while True:
        q = {"cluster_id": cluster, "scanner": scanner, "size": 500} | (
            {"cursor": cursor} if cursor else {}
        )
        status, _, raw, _ = _get(opener, f"{base}/api/v1/findings?{urlencode(q)}")
        if status != 200:
            raise SystemExit(f"findings read: status {status}")
        page = json.loads(raw)
        rows += [finding_row(f) for f in page["data"]]
        cursor = page.get("next_cursor")
        if not cursor:
            break
    sys.stdout.write(json.dumps(sorted(rows, key=lambda r: [str(x) for x in r])) + "\n")
    return 0


def cmd_report(run: str) -> int:
    folder = Path(run)
    text, failing = report(folder)
    (folder / "report.md").write_text(text)
    sys.stdout.write(
        f"report: {folder / 'report.md'} ({len(failing)} differences that fail)\n"
    )
    return 1 if failing else 0


def main() -> int:
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "reads":
        return cmd_reads(*args)
    if cmd == "findings":
        return cmd_findings(*args)
    if cmd == "vulns":
        sys.stdout.write(
            json.dumps(
                summarize_vulns(*(json.loads(Path(a).read_text()) for a in args))
            )
            + "\n"
        )
        return 0
    if cmd == "report":
        return cmd_report(*args)
    raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    sys.exit(main())
