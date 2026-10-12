"""Enumerate running images from the kube API and dedup by content digest (D30).

The scanner is stateless: every cycle it lists running pods, pulls each container's
content-addressed digest from `container_statuses.image_id`, and collapses pods sharing a digest
into one scan target (N pods → 1 scan). The reference to pull is the `repo@sha256:…` in
`image_id`: a tag can have moved since the pod started, and only the digest names the image that
runs (issue 833, B5). The name shown is the tag when any pod of the digest reports one
(`_display_ref`). All distinct digests are returned every cycle — there is no skip-unchanged. The
kube client is injected so this is unit-testable without a live cluster.
"""

from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from scanner.scope import ScanScope


class Location(BaseModel):
    model_config = ConfigDict(frozen=True)  # frozen → hashable, dedups cleanly

    namespace: str
    pod: str
    container: str


class ImageTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_digest: str  # content-addressed (sha256:…)
    image_ref: str  # the name shown and matched by scope globs, e.g. nginx:1.21.6
    pull_ref: str  # what the scan pulls: repo@sha256:… whenever the runtime reports one
    locations: tuple[Location, ...]  # every pod/container running this digest

    @property
    def pod_count(self) -> int:
        return len({(loc.namespace, loc.pod) for loc in self.locations})

    @property
    def namespaces(self) -> tuple[str, ...]:
        """Distinct namespaces this digest runs in (a digest can span several)."""
        return tuple(sorted({loc.namespace for loc in self.locations}))


class _PodSource(Protocol):
    def list_pod_for_all_namespaces(self, *, watch: bool = ...) -> Any: ...


def _digest(image_id: str) -> str | None:
    """Extract the sha256 content digest from a container status `image_id`, or None.

    Handles `docker-pullable://repo@sha256:…`, `repo@sha256:…`, and a bare `sha256:…`.
    """
    s = image_id
    if "://" in s:
        s = s.split("://", 1)[1]
    if "@" in s:
        s = s.split("@", 1)[1]
    return s if s.startswith("sha256:") else None


def _pullable(image_id: str) -> str | None:
    """The `repo@sha256:…` in a container status `image_id`, or None for a bare id."""
    pullable = image_id.split("://", 1)[1] if "://" in image_id else image_id
    return pullable if "@" in pullable else None


def _display_ref(image: str, image_id: str) -> tuple[str, bool]:
    """(the name to show, whether it fell back to `image_id`). For a pod started by digest,
    containerd reports `status.image` as the bare config id (`sha256:…`), which names nothing; the
    `repo@sha256:…` is then in `image_id` (issue 817, finding 2)."""
    if not image.startswith("sha256:"):
        return image, False
    return _pullable(image_id) or image, True


def _owner_kinds(pod: Any) -> list[str]:
    """The pod's owner-reference kinds (e.g. ReplicaSet, Job, DaemonSet) for scope kind-filtering.
    Immediate owner only — a Deployment-managed pod reads as `ReplicaSet`, a CronJob's as `Job`."""
    refs = getattr(getattr(pod, "metadata", None), "owner_references", None) or []
    return [getattr(o, "kind", "") for o in refs]


def running_images(pods: Iterable[Any] | None, scope: ScanScope | None = None) -> list[ImageTarget]:
    scope = scope or ScanScope()  # empty scope = scan everything (the default)
    by_digest: dict[str, dict[str, Any]] = {}
    for p in pods or []:
        status = getattr(p, "status", None)
        if status is None or getattr(status, "phase", None) != "Running":
            continue
        # scope filter at the pod level (before dedup): a digest survives if it runs in ≥1 in-scope
        # pod (D30 — a digest can span namespaces). Image-glob is applied to the target below.
        if not scope.namespace_allowed(p.metadata.namespace):
            continue
        if not scope.kinds_allowed(_owner_kinds(p)):
            continue
        for cs in getattr(status, "container_statuses", None) or []:
            image_id = getattr(cs, "image_id", "") or ""
            digest = _digest(image_id)
            if digest is None:
                continue
            ref, fallback = _display_ref(cs.image or "", image_id)
            entry = by_digest.setdefault(
                digest, {"ref": ref, "fallback": fallback, "pull": None, "locs": set()}
            )
            if entry["fallback"] and not fallback:  # the runtime's own name keeps the tag, if any
                entry["ref"], entry["fallback"] = ref, False
            entry["pull"] = entry["pull"] or _pullable(image_id)
            entry["locs"].add(
                Location(namespace=p.metadata.namespace, pod=p.metadata.name, container=cs.name)
            )
    targets = [
        ImageTarget(
            image_digest=digest,
            image_ref=entry["ref"],
            pull_ref=entry["pull"] or entry["ref"],
            locations=tuple(
                sorted(entry["locs"], key=lambda loc: (loc.namespace, loc.pod, loc.container))
            ),
        )
        for digest, entry in sorted(by_digest.items())
    ]
    return [t for t in targets if scope.image_allowed(t.image_ref)]


def discover(api: _PodSource, scope: ScanScope | None = None) -> list[ImageTarget]:
    return running_images(api.list_pod_for_all_namespaces(watch=False).items, scope)
