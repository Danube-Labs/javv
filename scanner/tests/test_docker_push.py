"""The rules of the Docker scan script (deploy/docker/javv_docker_push.py, issue 1155): the place of
a container, the skip of the scan containers, the skip settings, the scan scope of JAVV, the scan by
image ID, the Docker API on its socket, and the parts that must stay the same as in the Nomad
script. The scripts are standalone files: the test loads them by path.
"""

import http.server
import importlib.util
import inspect
import json
import socketserver
import sys
import threading
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # inspect.getsource finds the file of a class through sys.modules
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


push = load("javv_docker_push", DEPLOY / "docker" / "javv_docker_push.py")
nomad_push = load("javv_nomad_push_for_docker", DEPLOY / "nomad" / "javv_nomad_push.py")

REQUIRED = {
    "JAVV_BACKEND_URL": "http://javv.test",
    "JAVV_TOKEN": "t",
    "JAVV_CLUSTER_ID": "docker-test-01",
    "JAVV_SCANNER": "trivy",
}
NGINX = "sha256:65645c7bb6a0"
REDIS = "sha256:c5d34a98396a"


def container(
    name: str,
    image: str,
    image_id: str,
    project: str = "",
    state: str = "running",
    labels: dict[str, str] | None = None,
):
    """One container of GET /containers/json, as Docker 29 gives it."""
    return {
        "Id": f"id-{name}",
        "Names": [f"/{name}"],
        "Image": image,
        "ImageID": image_id,
        "State": state,
        "Labels": ({"com.docker.compose.project": project} if project else {}) | (labels or {}),
    }


SCAN = {"javv.scan": "true"}
HOST = [
    container("shop-web-1", "nginx:1.27-alpine", NGINX, "shop"),
    container("shop-web-2", "nginx:1.27-alpine", NGINX, "shop"),
    container("shop-cache-1", "redis:7-alpine", REDIS, "shop"),
    container("billing-web-1", "nginx@sha256:65645c7bb6a0", NGINX, "billing"),
    container("billing-worker-1", "billing-worker:dev", "sha256:482447dafed3", "billing"),
    container("lonely", "alpine:3.20", "sha256:d9e853e87e55"),
    # the tag moved to another image after the start: the list gives the image ID
    container("moving", "sha256:d9e853e87e55", "sha256:d9e853e87e55"),
    container(
        "javv-scan-trivy-1", "javv-scanner-trivy:0.76.2", "sha256:91e8", "javv-scan", labels=SCAN
    ),
    container(
        "javv-scan-grype-1", "javv-scanner-grype:0.121.1", "sha256:b015", "javv-scan", labels=SCAN
    ),
    container("paused-1", "paused:1", "sha256:0001", "paused", state="paused"),
]
INSPECT = {"id-moving": {"Config": {"Image": "probe-moving:1"}}}


@pytest.fixture
def settings(monkeypatch):
    def make(**extra: str):
        for k, v in (REQUIRED | extra).items():
            monkeypatch.setenv(k, v)
        return push.Settings()

    return make


@pytest.fixture
def docker(monkeypatch):
    """The Docker API of HOST. Records the paths that the script asked for."""
    asked: list[str] = []

    def get(_s, path: str):
        asked.append(path)
        if path == "/containers/json":
            return HOST
        cid = path.removeprefix("/containers/").removesuffix("/json")
        if cid not in INSPECT:
            raise push.DockerError(f"GET {path}: HTTP 404")
        return INSPECT[cid]

    monkeypatch.setattr(push, "docker_get", get)
    return asked


def running_images(s, scope):
    """running_images with the containers of each image as their count: the replicas."""
    images, skipped = push.running_images(s, scope)
    return {
        i: {"refs": e["refs"], "places": e["places"], "replicas": len(e["containers"])}
        for i, e in images.items()
    }, skipped


def test_place_is_the_compose_project_else_the_container_name(settings, docker):
    images, _ = running_images(settings(), {})
    assert images[NGINX]["places"] == {"shop", "billing"}
    assert images[REDIS]["places"] == {"shop"}
    assert images["sha256:d9e853e87e55"]["places"] == {"lonely", "moving"}


def test_images_group_by_image_id_and_count_containers(settings, docker):
    images, _ = running_images(settings(), {})
    # two names of one image ID are one image: the name by tag and the name by digest
    assert images[NGINX] == {
        "refs": {"nginx:1.27-alpine", "nginx@sha256:65645c7bb6a0"},
        "places": {"shop", "billing"},
        "replicas": 3,
    }


def test_a_moved_tag_takes_the_name_from_the_container(settings, docker):
    images, _ = running_images(settings(), {})
    assert images["sha256:d9e853e87e55"]["refs"] == {"alpine:3.20", "probe-moving:1"}
    # only that container needs the second call
    assert docker == ["/containers/json", "/containers/id-moving/json"]


def test_a_moved_tag_of_a_container_that_stopped_keeps_the_image_id(settings, docker, monkeypatch):
    monkeypatch.delitem(INSPECT, "id-moving")
    images, _ = running_images(settings(), {})
    assert "sha256:d9e853e87e55" in images["sha256:d9e853e87e55"]["refs"]


def test_the_scan_containers_skip_themselves_and_each_other(settings, docker):
    images, skipped = running_images(settings(), {})
    assert skipped["scan_container"] == ["javv-scan-grype-1", "javv-scan-trivy-1"]
    assert not {"sha256:91e8", "sha256:b015"} & set(images)


def test_only_running_containers_count(settings, docker):
    images, _ = running_images(settings(), {})
    assert "sha256:0001" not in images


def test_skip_projects_takes_patterns_on_the_place(settings, docker):
    images, skipped = running_images(settings(JAVV_DOCKER_SKIP_PROJECTS="bill*, lonely"), {})
    assert skipped["project"] == ["billing", "lonely"]
    assert images[NGINX]["places"] == {"shop"}
    assert images["sha256:d9e853e87e55"]["places"] == {"moving"}


def test_the_scope_of_javv_applies_to_places_and_images(settings, docker):
    s = settings()
    images, skipped = running_images(s, {"ignore_namespaces": ["bill*"]})
    assert skipped["namespace"] == ["billing"]
    assert images[NGINX]["places"] == {"shop"}

    images, _ = running_images(s, {"include_namespaces": ["shop"]})
    assert set(images) == {NGINX, REDIS}

    images, skipped = running_images(s, {"exclude_images": ["redis:*"]})
    assert skipped["image"] == ["redis:7-alpine"]
    assert REDIS not in images

    # a Docker container has no kind
    images, skipped = running_images(s, {"ignore_kinds": ["Deployment", "CronJob"]})
    assert len(images) == 4 and "kind" not in skipped


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCKER_HOST", "tcp://10.0.0.5:2375"),
        ("JAVV_TRIVY_SEVERITIES", "URGENT"),
        ("JAVV_PUSH_RETRY_BUDGET_SECONDS", "0"),
        ("JAVV_SCANNER", "clair"),
        ("JAVV_BACKEND_URL", "javv.example.com"),
        ("JAVV_CLUSTER_ID", "Docker_Host"),
    ],
)
def test_a_setting_that_is_not_valid_stops_the_run(settings, name, value):
    with pytest.raises(push.SettingError, match=name):
        settings(**{name: value})


def test_a_backend_url_with_no_scheme_names_both_schemes(settings):
    with pytest.raises(push.SettingError, match="start it with http:// or https://"):
        settings(JAVV_BACKEND_URL="javv.example.com")


def test_docker_host_names_the_socket(settings):
    assert settings().docker_socket == "/var/run/docker.sock"
    assert settings(DOCKER_HOST="unix:///run/user/1000/docker.sock").docker_socket == (
        "/run/user/1000/docker.sock"
    )


class DockerAPI(socketserver.UnixStreamServer):
    """A Docker API on a real Unix socket: the containers on /containers/json, 404 elsewhere."""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps(HOST[:1]).encode() if self.path == "/containers/json" else b"{}"
        self.send_response(200 if self.path == "/containers/json" else 404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def address_string(self):
        return "socket"


def test_docker_get_talks_http_on_the_socket(settings, tmp_path):
    path = str(tmp_path / "docker.sock")
    server = DockerAPI(path, Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        s = settings(DOCKER_HOST=f"unix://{path}")
        assert push.docker_get(s, "/containers/json") == HOST[:1]
        with pytest.raises(push.DockerError, match="404"):
            push.docker_get(s, "/containers/gone/json")
    finally:
        server.shutdown()
        server.server_close()


def test_no_socket_is_an_os_error(settings, tmp_path):
    with pytest.raises(OSError):
        push.docker_get(settings(DOCKER_HOST=f"unix://{tmp_path}/none.sock"), "/containers/json")


# The scan and push parts of the two scripts: a fix in one goes into the other.
SHARED = [
    "SEV",
    "TRIVY_SCANNERS",
    "TRIVY_SEVERITIES",
    "TRIVY_PKG_TYPES",
    "GRYPE_SCOPES",
    "CLUSTER_ID",
    "LOG_LEVELS",
    "GO_DURATION",
    "env",
    "required",
    "flag",
    "csv",
    "choices",
    "positive_int",
    "now",
    "body_of",
    "Javv",
    "match",
    "repo_digest",
    "run",
    "scan_trivy",
    "scan_grype",
    "expected_count",
    "counts",
]


@pytest.mark.parametrize("name", SHARED)
def test_the_shared_parts_are_the_same_as_in_the_nomad_script(name):
    mine, theirs = getattr(push, name), getattr(nomad_push, name)
    if callable(mine) and not hasattr(mine, "pattern"):
        assert inspect.getsource(mine) == inspect.getsource(theirs)
    else:
        assert mine == theirs


def test_grype_reads_the_image_from_the_docker_daemon(settings, monkeypatch):
    seen = []
    report = {
        "matches": [],
        "descriptor": {},
        "source": {"target": {"repoDigests": ["a@sha256:1"]}},
    }
    monkeypatch.setattr(push, "run", lambda cmd, timeout=None: seen.append(cmd) or report)
    push.scan_grype(settings(JAVV_SCANNER="grype"), "sha256:d9e853e87e55")
    assert seen[0][:2] == ["grype", "docker:sha256:d9e853e87e55"]
    assert nomad_push.GRYPE_SOURCE == "registry"


class FakeJavv:
    """The JAVV API for main(): records each call, answers from `replies` by path."""

    def __init__(self, replies: dict[str, tuple[int | None, object]]):
        self.calls: list[tuple[str, str, object, bool]] = []
        self.replies = replies

    def __call__(self, method: str, path: str, body=None, gz: bool = False):
        self.calls.append((method, path, body, gz))
        return self.replies.get(path, (200, {}))


GOOD = {
    "/api/v1/scan-scope": (200, {}),
    "/api/v1/scan-runs": (200, {"scan_order": 7}),
    "/api/v1/ingest/scan": (202, {"accepted": True}),
    "/api/v1/inventory-runs": (200, {"status": "committed"}),
}


@pytest.fixture
def cycle(settings, docker, monkeypatch):
    """Runs main() against the fake Docker API and a fake JAVV. Records what the scanner got;
    each image ID scans to its own digest unless `digest` says otherwise."""
    scanned: list[str] = []

    def run(replies=GOOD, digest=lambda image: "sha256:repo-" + image[7:], **env):
        settings(**env)
        javv = FakeJavv(replies)
        monkeypatch.setattr(push.Javv, "call", lambda _api, *a, **k: javv(*a, **k))

        def scan(_s, image):
            scanned.append(image)
            return digest(image), [], "0.76.2", "2", None

        monkeypatch.setattr(push, "scan_trivy", scan)
        return push.main(), javv.calls, scanned

    return run


def test_a_cycle_scans_by_image_id_and_names_the_image_by_its_ref(cycle):
    code, calls, scanned = cycle()
    assert code == 0
    assert sorted(scanned) == sorted([NGINX, REDIS, "sha256:482447dafed3", "sha256:d9e853e87e55"])
    pushes = {b["image_ref"]: b for _, p, b, _ in calls if p == "/api/v1/ingest/scan"}
    assert pushes["nginx:1.27-alpine"]["namespaces"] == ["billing", "shop"]
    assert pushes["nginx:1.27-alpine"]["replicas"] == 3
    assert pushes["alpine:3.20"]["namespaces"] == ["lonely", "moving"]


def test_a_cycle_compresses_only_the_envelopes(cycle):
    code, calls, _ = cycle()
    assert code == 0
    assert {(m, p, gz) for m, p, _, gz in calls} == {
        ("GET", "/api/v1/scan-scope", False),
        ("POST", "/api/v1/scan-runs", False),
        ("POST", "/api/v1/ingest/scan", True),
        ("POST", "/api/v1/inventory-runs", False),
    }
    pushes = [b for _, p, b, _ in calls if p == "/api/v1/ingest/scan"]
    inventory = next(b for _, p, b, _ in calls if p == "/api/v1/inventory-runs")
    assert inventory["expected_count"] == len(pushes) == 4


def test_two_image_ids_of_one_digest_push_once(cycle):
    code, calls, _ = cycle(digest=lambda image: "sha256:same")
    assert code == 0
    pushes = [b for _, p, b, _ in calls if p == "/api/v1/ingest/scan"]
    assert len(pushes) == 1
    assert pushes[0]["replicas"] == 7
    assert pushes[0]["namespaces"] == ["billing", "lonely", "moving", "shop"]


def test_no_scope_from_javv_means_no_scan(cycle):
    code, calls, scanned = cycle(replies=GOOD | {"/api/v1/scan-scope": (None, {"error": "down"})})
    assert (code, scanned) == (1, [])
    assert [p for _, p, _, _ in calls] == ["/api/v1/scan-scope"]


def test_no_answer_from_docker_stops_the_run(cycle, monkeypatch):
    def down(_s, _path):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(push, "docker_get", down)
    code, calls, _ = cycle()
    assert code == 1
    assert [p for _, p, _, _ in calls] == ["/api/v1/scan-scope"]


def test_no_digest_fails_the_run_and_keeps_the_cycle_partial(cycle):
    code, calls, _ = cycle(digest=lambda image: None)
    assert code == 1
    assert not [p for _, p, _, _ in calls if p == "/api/v1/ingest/scan"]
    inventory = next(b for _, p, b, _ in calls if p == "/api/v1/inventory-runs")
    assert inventory["expected_count"] == 4  # the images found, not 0


def test_a_dry_run_pushes_nothing(cycle):
    code, calls, scanned = cycle(JAVV_DRY_RUN="true")
    assert (code, scanned) == (0, [])
    assert [p for _, p, _, _ in calls] == ["/api/v1/scan-scope"]
