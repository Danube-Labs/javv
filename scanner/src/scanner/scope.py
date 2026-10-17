"""Scan scope (D43/FR-24) — the scanner side. Mirrors the backend `ScanScope` wire shape
(`backend/admin/scan_scope.py`); the scanner fetches it from the backend at cycle start and filters
discovery *before* pull/scan. This is a **lenient reader** (unknown fields ignored) so a newer
backend adding a scope setting doesn't break an older scanner.

Fail-closed contract (D43): `fetch_scan_scope` returns `None` when the backend is unreachable — the
caller must then **not scan** (distinct from a *fetched empty* scope, which means scan everything).
"""

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict


def _matches_any(value: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(value, glob) for glob in globs)


class ScanScope(BaseModel):
    model_config = ConfigDict(frozen=True)  # lenient: ignore unknown fields (forward-compat)

    include_namespaces: tuple[str, ...] = ()  # allowlist; empty = all
    ignore_namespaces: tuple[str, ...] = ()  # denylist; wins over include
    exclude_images: tuple[str, ...] = ()  # image_ref globs to skip
    ignore_kinds: tuple[str, ...] = ()  # pod owner-reference kinds to skip

    def namespace_allowed(self, namespace: str) -> bool:
        """Namespace lists are fnmatch globs (operator ruling 2026-07-15): `kube*` covers the
        kube- family. Strictly backward compatible — k8s namespaces are DNS-1123 labels, which
        cannot contain glob metacharacters, so every pre-existing exact entry matches as before."""
        if self.include_namespaces and not _matches_any(namespace, self.include_namespaces):
            return False
        return not _matches_any(namespace, self.ignore_namespaces)  # ignore wins over include

    def kinds_allowed(self, owner_kinds: Iterable[str]) -> bool:
        return not any(k in self.ignore_kinds for k in owner_kinds)

    def ignored_kinds(self, owner_kinds: Iterable[str]) -> list[str]:
        """The listed kinds that match the pod's owner kinds (exact, with case)."""
        return [k for k in owner_kinds if k in self.ignore_kinds]

    def image_allowed(self, image_ref: str) -> bool:
        return not _matches_any(image_ref, self.exclude_images)


@dataclass
class ScopeTally:
    """What one discovery pass skipped, for the cycle's `scope applied` line (issue 891).
    Every listed kind starts at 0, so a kind that owns no pod (e.g. `CronJob`, whose pods are
    owned by a Job) shows as 0 instead of being missing."""

    pods_running: int = 0
    skipped_namespace: int = 0  # pods
    skipped_kind: dict[str, int] = field(default_factory=dict)  # pods, per listed kind
    skipped_image: int = 0  # image digests

    @classmethod
    def for_scope(cls, scope: ScanScope) -> "ScopeTally":
        return cls(skipped_kind=dict.fromkeys(scope.ignore_kinds, 0))


def fetch_scan_scope(http: httpx.Client, *, token: str | None) -> ScanScope | None:
    """GET the cluster's scan scope from the backend (keyed by the token's cluster). Returns the
    scope on success (empty scope = scan everything), or **None on any failure** (backend down,
    non-2xx, bad body) — the caller treats None as fail-closed: do not scan this cycle."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        resp = http.get("/api/v1/scan-scope", headers=headers)
        resp.raise_for_status()
        return ScanScope.model_validate(resp.json())
    except Exception:
        return None
