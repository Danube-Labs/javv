"""Discovery enumerates running images from the kube API and dedups by content digest (D30):
N pods of the same digest collapse to one scan target, but every distinct digest is scanned
every cycle (stateless — no skip-unchanged). The digest comes from `container_statuses.image_id`
(content-addressed); pods without a resolved digest or not Running are ignored."""

from types import SimpleNamespace as NS

from scanner.discovery import ImageTarget, discover, running_images

DIG_NGINX = "sha256:" + "a" * 64
DIG_PY = "sha256:" + "b" * 64
DIG_ALPINE = "sha256:" + "c" * 64


def cstatus(name: str, image: str, image_id: str) -> NS:
    return NS(name=name, image=image, image_id=image_id)


def pod(ns: str, name: str, statuses: list[NS] | None, phase: str = "Running") -> NS:
    return NS(
        metadata=NS(namespace=ns, name=name),
        status=NS(phase=phase, container_statuses=statuses),
    )


def test_dedups_replicas_of_one_image_to_a_single_target() -> None:
    # The seed manifest's case: 3 nginx pods (one digest) → 1 scan, across 3 image_id formats.
    pods = [
        pod(
            "javv-smoke",
            "nginx-1",
            [cstatus("nginx", "nginx:1.21.6", f"docker-pullable://nginx@{DIG_NGINX}")],
        ),
        pod("javv-smoke", "nginx-2", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
        pod("javv-smoke", "nginx-3", [cstatus("nginx", "nginx:1.21.6", DIG_NGINX)]),
        pod("javv-smoke", "py-1", [cstatus("python", "python:3.9.16-slim", f"python@{DIG_PY}")]),
    ]
    by_digest = {t.image_digest: t for t in running_images(pods)}
    assert set(by_digest) == {DIG_NGINX, DIG_PY}
    assert by_digest[DIG_NGINX].pod_count == 3
    assert by_digest[DIG_NGINX].image_ref == "nginx:1.21.6"
    assert by_digest[DIG_PY].pod_count == 1


def test_same_digest_across_namespaces_is_one_target_spanning_both() -> None:
    pods = [
        pod("ns-a", "p1", [cstatus("c", "img:1", f"img@{DIG_ALPINE}")]),
        pod("ns-b", "p2", [cstatus("c", "img:1", f"img@{DIG_ALPINE}")]),
    ]
    targets = running_images(pods)
    assert len(targets) == 1
    assert {loc.namespace for loc in targets[0].locations} == {"ns-a", "ns-b"}
    assert targets[0].pod_count == 2
    assert targets[0].namespaces == ("ns-a", "ns-b")  # sorted distinct, spans both


def test_ignores_pods_without_a_resolved_digest_or_not_running() -> None:
    pods = [
        pod("ns", "pending", None, phase="Pending"),  # not scheduled yet
        pod("ns", "no-digest", [cstatus("c", "img:1", "")]),  # image_id not resolved
        pod("ns", "tag-only", [cstatus("c", "img:1", "img:1")]),  # no sha256 digest
        pod("ns", "succeeded", [cstatus("c", "img:1", f"img@{DIG_PY}")], phase="Succeeded"),
    ]
    assert running_images(pods) == []


def test_handles_empty_input() -> None:
    assert running_images([]) == []
    assert running_images(None) == []  # type: ignore[arg-type]


def test_output_is_deterministically_ordered() -> None:
    pods = [
        pod("ns", "b", [cstatus("c", "z", f"z@{DIG_PY}")]),
        pod("ns", "a", [cstatus("c", "a", f"a@{DIG_NGINX}")]),
    ]
    digests = [t.image_digest for t in running_images(pods)]
    assert digests == sorted(digests)


def test_discover_pulls_pods_from_the_api_and_dedups() -> None:
    pods = [
        pod("javv-smoke", "nginx-1", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
        pod("javv-smoke", "nginx-2", [cstatus("nginx", "nginx:1.21.6", f"nginx@{DIG_NGINX}")]),
    ]

    class FakeApi:
        def list_pod_for_all_namespaces(self, *, watch: bool = False) -> NS:
            return NS(items=pods)

    targets = discover(FakeApi())
    assert len(targets) == 1
    assert isinstance(targets[0], ImageTarget)
    assert targets[0].pod_count == 2


# Verbatim from a k3s 1.35 / containerd node (issue 817, finding 2): a pod started as
# `nginx@sha256:65645c…` reports the bare config id as `status.image`, which no registry serves.
NGINX_REPO_DIGEST = "sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
NGINX_CONFIG_ID = "sha256:6769dc3a703c719c1d2756bda113659be28ae16cf0da58dd5fd823d6b9a050ea"
NGINX_IMAGE_ID = f"docker.io/library/nginx@{NGINX_REPO_DIGEST}"


def test_a_digest_pinned_pod_is_pulled_by_its_image_id_reference() -> None:
    pods = [pod("hunt-probe", "by-digest", [cstatus("c", NGINX_CONFIG_ID, NGINX_IMAGE_ID)])]
    [target] = running_images(pods)
    assert target.image_digest == NGINX_REPO_DIGEST
    assert target.image_ref == NGINX_IMAGE_ID


def test_the_docker_pullable_scheme_is_stripped_from_the_fallback() -> None:
    pods = [pod("ns", "p", [cstatus("c", DIG_PY, f"docker-pullable://python@{DIG_PY}")])]
    assert running_images(pods)[0].image_ref == f"python@{DIG_PY}"


def test_a_tag_pinned_pod_keeps_its_own_reference() -> None:
    busybox = "docker.io/library/busybox:1.36"
    image_id = "docker.io/library/busybox@sha256:" + "7" * 64
    assert (
        running_images([pod("ns", "p", [cstatus("c", busybox, image_id)])])[0].image_ref == busybox
    )


def test_a_bare_id_in_both_fields_stays_as_reported() -> None:
    # nothing pullable to fall back to: the scan fails and is logged, as before
    pods = [pod("ns", "p", [cstatus("c", DIG_ALPINE, DIG_ALPINE)])]
    assert running_images(pods)[0].image_ref == DIG_ALPINE


def test_a_tagged_pod_names_a_digest_whichever_pod_comes_first() -> None:
    by_digest = cstatus("c", NGINX_CONFIG_ID, NGINX_IMAGE_ID)
    by_tag = cstatus("c", "docker.io/library/nginx:1.27", NGINX_IMAGE_ID)
    for order in ([by_digest, by_tag], [by_tag, by_digest]):
        pods = [pod("ns", f"p{i}", [cs]) for i, cs in enumerate(order)]
        [target] = running_images(pods)
        assert target.image_ref == "docker.io/library/nginx:1.27"
        assert target.pod_count == 2
