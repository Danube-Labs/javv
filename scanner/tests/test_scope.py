"""Scan scope (D43/FR-24), scanner side: the `ScanScope` predicates, the discovery filter
(namespace/kind at the pod level, image-glob at the target level), and the fail-closed `fetch`
(None on any backend failure = do not scan)."""

from typing import Any

import httpx

from scanner.discovery import running_images
from scanner.scope import ScanScope, ScopeTally, fetch_scan_scope

# --- predicates -------------------------------------------------------------


def test_empty_scope_allows_everything() -> None:
    s = ScanScope()
    assert s.namespace_allowed("anything")
    assert s.kinds_allowed(["Job", "DaemonSet"])
    assert s.image_allowed("registry.io/app:1")


def test_include_is_an_allowlist() -> None:
    s = ScanScope(include_namespaces=("team-a",))
    assert s.namespace_allowed("team-a")
    assert not s.namespace_allowed("team-b")


def test_ignore_wins_over_include() -> None:
    s = ScanScope(include_namespaces=("team-a",), ignore_namespaces=("team-a",))
    assert not s.namespace_allowed("team-a")


def test_namespace_lists_take_fnmatch_globs() -> None:
    # operator ruling 2026-07-15: kube* covers the kube- family; literals keep matching exactly
    s = ScanScope(include_namespaces=("kube*", "prod"))
    assert s.namespace_allowed("kube-system")
    assert s.namespace_allowed("kube-public")
    assert s.namespace_allowed("prod")
    assert not s.namespace_allowed("team-a")

    ignore = ScanScope(ignore_namespaces=("kube*",))
    assert not ignore.namespace_allowed("kube-node-lease")
    assert ignore.namespace_allowed("prod")


def test_ignore_glob_wins_over_include_glob() -> None:
    s = ScanScope(include_namespaces=("*",), ignore_namespaces=("kube*",))
    assert s.namespace_allowed("prod")
    assert not s.namespace_allowed("kube-system")


def test_kind_and_image_filters() -> None:
    s = ScanScope(ignore_kinds=("Job",), exclude_images=("registry.k8s.io/*",))
    assert not s.kinds_allowed(["Job"])
    assert s.kinds_allowed(["ReplicaSet"])
    assert not s.image_allowed("registry.k8s.io/pause:3.9")
    assert s.image_allowed("registry.io/app:1")


# --- discovery filter (fake pods) -------------------------------------------


class _CS:
    def __init__(self, image: str, image_id: str) -> None:
        self.image, self.image_id, self.name = image, image_id, "c"


class _Meta:
    def __init__(self, ns: str, name: str, kinds: list[str]) -> None:
        self.namespace, self.name = ns, name
        self.owner_references = [type("O", (), {"kind": k})() for k in kinds]


class _Pod:
    def __init__(self, ns: str, name: str, cs: list[_CS], kinds: list[str] | None = None) -> None:
        self.metadata = _Meta(ns, name, kinds or [])
        self.status = type("S", (), {"phase": "Running", "container_statuses": cs})()


def _pod(ns: str, name: str, digest: str, ref: str, kinds: list[str] | None = None) -> _Pod:
    return _Pod(ns, name, [_CS(ref, f"docker-pullable://{ref}@{digest}")], kinds)


def test_namespace_filter_drops_out_of_scope_pods() -> None:
    pods = [
        _pod("team-a", "p1", "sha256:aaa", "a:1"),
        _pod("kube-system", "p2", "sha256:bbb", "b:1"),
    ]
    scope = ScanScope(ignore_namespaces=("kube-system",))
    digests = {t.image_digest for t in running_images(pods, scope)}
    assert digests == {"sha256:aaa"}


def test_digest_kept_if_it_runs_in_any_in_scope_namespace() -> None:
    # same digest in an excluded and an allowed namespace → kept (D30 span)
    pods = [
        _pod("kube-system", "p1", "sha256:shared", "img:1"),
        _pod("team-a", "p2", "sha256:shared", "img:1"),
    ]
    scope = ScanScope(ignore_namespaces=("kube-system",))
    targets = running_images(pods, scope)
    assert [t.image_digest for t in targets] == ["sha256:shared"]
    # only the in-scope location survives
    assert [loc.namespace for loc in targets[0].locations] == ["team-a"]


def test_kind_filter_drops_by_owner_reference() -> None:
    pods = [
        _pod("team-a", "p1", "sha256:aaa", "a:1", kinds=["ReplicaSet"]),
        _pod("team-a", "j1", "sha256:bbb", "b:1", kinds=["Job"]),
    ]
    scope = ScanScope(ignore_kinds=("Job",))
    assert {t.image_digest for t in running_images(pods, scope)} == {"sha256:aaa"}


def test_image_glob_filter_drops_targets() -> None:
    pods = [
        _pod("team-a", "p1", "sha256:aaa", "registry.k8s.io/pause:3.9"),
        _pod("team-a", "p2", "sha256:bbb", "registry.io/app:1"),
    ]
    scope = ScanScope(exclude_images=("registry.k8s.io/*",))
    assert {t.image_ref for t in running_images(pods, scope)} == {"registry.io/app:1"}


def test_no_scope_scans_everything() -> None:
    pods = [_pod("kube-system", "p1", "sha256:aaa", "a:1", kinds=["Job"])]
    assert len(running_images(pods)) == 1  # default scope = scan all


# --- what the scope skipped (issue 891) ---------------------------------------


def _scoped_pods() -> list[_Pod]:
    return [
        _pod("team-a", "web", "sha256:aaa", "registry.io/app:1", kinds=["ReplicaSet"]),
        _pod("kube-system", "dns", "sha256:bbb", "registry.io/dns:1", kinds=["ReplicaSet"]),
        _pod("team-a", "batch", "sha256:ccc", "registry.io/batch:1", kinds=["Job"]),
        _pod("team-a", "pause", "sha256:ddd", "registry.k8s.io/pause:3.9", kinds=["DaemonSet"]),
    ]


_SCOPE = ScanScope(
    ignore_namespaces=("kube-system",),
    ignore_kinds=("Job", "CronJob"),
    exclude_images=("registry.k8s.io/*",),
)


def test_ignored_kinds_names_each_listed_kind_that_matches() -> None:
    assert _SCOPE.ignored_kinds(["Job"]) == ["Job"]
    assert _SCOPE.ignored_kinds(["ReplicaSet"]) == []
    assert ScanScope(ignore_kinds=("job",)).ignored_kinds(["Job"]) == []  # exact, with case


def test_tally_counts_what_each_part_of_the_scope_skipped() -> None:
    tally = ScopeTally.for_scope(_SCOPE)
    targets = running_images(_scoped_pods(), _SCOPE, tally)
    assert [t.image_ref for t in targets] == ["registry.io/app:1"]
    assert tally.pods_running == 4
    assert tally.skipped_namespace == 1
    # a listed kind that skipped no pod reads 0: CronJob owns no pod, a Job does
    assert tally.skipped_kind == {"Job": 1, "CronJob": 0}
    assert tally.skipped_image == 1


def test_running_images_without_a_tally_is_unchanged() -> None:
    assert [t.image_ref for t in running_images(_scoped_pods(), _SCOPE)] == ["registry.io/app:1"]


def test_discover_logs_what_the_scope_skipped_once_at_info() -> None:
    import structlog.testing

    from scanner import discovery

    discovery.log = structlog.get_logger()  # fresh proxy: an earlier main() cached the pipeline

    class FakeApi:
        def list_pod_for_all_namespaces(self, *, watch: bool = False) -> Any:
            return type("PodList", (), {"items": _scoped_pods()})()

    with structlog.testing.capture_logs() as logs:
        targets = discovery.discover(FakeApi(), _SCOPE)
    lines = [e for e in logs if e["event"] == "scope applied"]
    assert len(lines) == 1
    line = lines[0]
    assert line["log_level"] == "info"
    assert line["pods_running"] == 4
    assert line["skipped_namespace"] == 1
    assert line["skipped_kind"] == {"Job": 1, "CronJob": 0}
    assert line["skipped_image"] == 1
    assert line["targets"] == len(targets) == 1


# --- fail-closed fetch ------------------------------------------------------


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://backend")


def test_fetch_returns_scope_on_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer tok"
        return httpx.Response(200, json={"ignore_namespaces": ["kube-system"]})

    with _client(handler) as http:
        scope = fetch_scan_scope(http, token="tok")
    assert scope is not None and scope.ignore_namespaces == ("kube-system",)


def test_fetch_empty_scope_is_scan_all_not_none() -> None:
    with _client(lambda r: httpx.Response(200, json={})) as http:
        scope = fetch_scan_scope(http, token="tok")
    assert scope == ScanScope()  # fetched-empty ≠ None — this scans everything


def test_fetch_returns_none_on_backend_error() -> None:
    # 401 / 5xx / transport failure → None → caller must NOT scan (fail-closed)
    with _client(lambda r: httpx.Response(401)) as http:
        assert fetch_scan_scope(http, token="bad") is None

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("backend down")

    with _client(boom) as http:
        assert fetch_scan_scope(http, token="tok") is None
