"""Runtime configuration. All env vars are `JAVV_`-prefixed; unknown ones are ignored (this is a
process-level config, not an untrusted request model — those are `extra="forbid"`).

**Validated at construction (#219, major-audit 06 §2):** semantically-broken values (zero/negative
limits, garbage PIT grammar, inverted cap pairs) raise at the first `get_settings()` call — which
happens in the app lifespan, so a borked deployment CRASHES AT BOOT with the offending variable
named, instead of booting green and failing every request. `opensearch_url` stays a plain str (the
startup ping fail-fasts it with a better error), but a URL that carries a user or password is
refused: credentials go in their own settings (issue 715). The secret-key rule is owned by
`assert_production_ready` (env-profile aware), never duplicated here.

**The failure names the variable and never echoes a value** (issue 715): pydantic's own error
carries the raw input dict, secret key and passwords included, so `get_settings()` re-raises it as a
`RuntimeError` built from the messages alone."""

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.jobs.schedule import validate_cron


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JAVV_", extra="ignore")

    # deployment profile (task C / audit M3): "dev" keeps local-boot conveniences; anything
    # prod-like ("prod"/"production") turns them into startup FAILURES (assert_production_ready)
    env: str = "dev"
    opensearch_url: str = "http://localhost:9200"
    # signing in to a secured OpenSearch (issue 715): empty username = no login (the dev store, CI).
    # The CA bundle is a PEM path for a private CA; empty = the system's CAs plus certifi's.
    opensearch_username: str = ""
    opensearch_password: SecretStr = SecretStr("")
    opensearch_ca_bundle: str = ""
    opensearch_verify_certs: bool = True
    request_timeout: float = Field(default=30.0, gt=0)
    # startup contract: ping OpenSearch + run bootstrap before serving (fail-fast). Unit tests that
    # run the app without an OpenSearch set this false.
    bootstrap_on_startup: bool = True
    # The backend's secret key: it hashes every ingest token and session id before they are stored,
    # and signs report download links. It MUST be set in any real deployment (D38/M14), and kept:
    # a new value makes every stored token and session unusable. The dev default exists only so
    # the app boots locally.
    secret_key: str = "dev-only-secret-key"
    ingest_max_compressed_bytes: int = Field(default=10 * 1024 * 1024, gt=0)  # 10 MiB on the wire
    ingest_max_body_bytes: int = Field(default=60 * 1024 * 1024, gt=0)  # decompressed (zip-bomb)
    ingest_rate_limit_per_minute: int = Field(default=120, ge=1)
    # a scanner clock this far ahead is refused (issue 832); behind, the staleness period decides
    ingest_future_tolerance_minutes: float = Field(default=15, gt=0)
    # human sessions (M5a/SEC-5): server-side TTL — the cookie's own lifetime is advisory
    session_ttl_hours: float = Field(default=24.0, gt=0)
    # the session cookie's Secure flag. A browser keeps a Secure cookie only from https or
    # localhost, so an install served over plain http sets this false. It defaults to true
    # because JAVV cannot see a TLS terminator in front of it (issue 452).
    session_cookie_secure: bool = True
    # how long an expired session row stays before `jobs/session_sweep.py` deletes it (issue 532)
    session_sweep_grace_hours: float = Field(default=24.0, ge=0)
    # login lockout (M5a): N failures per sliding window locks the username (429)
    login_max_attempts: int = Field(default=5, ge=1)
    login_lockout_minutes: float = Field(default=15.0, gt=0)
    # bulk triage (M5d, audit A-Mc/#189): bounded-synchronous. A frozen set at/under the inline
    # limit applies now (200 + result); above it → 413 (narrow, or M7's scheduled bulk). The freeze
    # itself never materializes more than bulk_max_targets ids (413 "selector too broad") — bounds
    # the freeze memory independently of the apply cost. No volatile 202/async path.
    bulk_inline_limit: int = Field(default=5000, ge=1)
    bulk_max_targets: int = Field(default=10000, ge=1)
    # findings search (M6): PIT keep-alive per page — an abandoned cursor's PIT self-expires.
    # OpenSearch time-unit grammar, one unit required (validated → pit_guard parses strictly)
    search_pit_keep_alive: str = Field(default="2m", pattern=r"^\d+(ms|s|m|h)$")
    # read-path DoS bounds (audit A-M6/A-m12/#189). Inline "run now" export (CSV + VEX) hard row
    # cap — past it the request 413s and points at narrower filters / M7 scheduled export. And a
    # per-principal concurrent-PIT cap (search cursors + exports) — past it → 429; in-memory per
    # pod like the ingest/login limiters (N replicas ⇒ N× budget).
    export_max_rows: int = Field(default=50000, ge=1)
    max_concurrent_pits_per_principal: int = Field(default=10, ge=1)
    # client-events beacon (issue 453): per-principal cap on browser warn/error BATCHES per
    # minute, the same sliding-window shape as the ingest limiter and in-memory per pod (N
    # replicas ⇒ N× budget). It bounds log VOLUME, not correctness. Sized well above a normal
    # session's flush rate so an unload-time beacon burst never trips it — the client never
    # retries, so a 429 here is silent telemetry loss.
    client_events_rate_limit_per_minute: int = Field(default=60, ge=1)
    # bootstrap admin (M5a/SEC-6): password from a mounted k8s Secret; empty = don't seed.
    # Seed-once — rotating the mounted value later has no effect on an existing admin by design.
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""
    # scheduled reports (M7/#32): results are stored IN OpenSearch (chunked) and TTL-swept.
    export_ttl_hours: int = Field(default=24, ge=1)  # completed export deleted this long after
    export_max_bytes: int = Field(default=500 * 1024 * 1024, ge=1)  # per-export ceiling → failed
    report_drain_sleep_ms: int = Field(default=200, ge=0)  # 0 = no throttle (legit in dev)
    report_lease_ttl_seconds: int = Field(default=300, ge=1)  # no heartbeat past it → reclaimable
    # data inspector (#406): the read-only store console. Hit ceiling per search, serialized
    # response byte cap (past it → 413, narrow the query), and a per-request timeout tighter
    # than the client default — an inspector query must never hog the store.
    inspect_max_hits: int = Field(default=500, ge=1)
    inspect_max_response_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    inspect_timeout_seconds: float = Field(default=10.0, gt=0)
    # cluster retirement (issue 765): the seeds for the fleet-wide retirement window, used until
    # someone saves one in Settings. A cluster with no accepted scan for this many days is retired
    # by the daily sweep (0 = never); the warning banner and the admins' bell start this many
    # days before.
    cluster_retire_after_days: float = Field(default=45, ge=0)
    cluster_retirement_warn_days: float = Field(default=7, gt=0)
    # background jobs (issue 691): the backend runs its own jobs. One cron expression per job,
    # read on the LOCAL wall clock of the process (`TZ`); empty = that job never runs on a
    # schedule. The master switch stops the scheduler without touching the schedules. The field
    # names are `job_<kind>_cron` for the kinds in `jobs/registry.py`, so the lookup is mechanical.
    scheduler_enabled: bool = True
    job_report_drain_cron: str = "*/5 * * * *"
    job_report_sweep_cron: str = "15 * * * *"
    job_staleness_sweep_cron: str = "0 2 * * *"
    job_lifecycle_sweep_cron: str = "0 3 * * *"
    job_findings_cleanup_cron: str = "0 4 * * *"
    job_cluster_retirement_cron: str = "15 4 * * *"
    job_session_sweep_cron: str = "30 4 * * *"

    def job_cron(self, kind: str) -> str:
        """The kind's schedule, or "" when it has none (switched off, or `rebuild_state`, which
        is only ever run by hand)."""
        return str(getattr(self, f"job_{kind}_cron", "")).strip()

    @model_validator(mode="after")
    def _cap_pairs_are_ordered(self) -> "Settings":
        # a compressed cap above the decompressed cap silently disables the zip-bomb guard
        if self.ingest_max_compressed_bytes > self.ingest_max_body_bytes:
            raise ValueError(
                "ingest_max_compressed_bytes must be ≤ ingest_max_body_bytes — the decompressed"
                " cap is the zip-bomb guard and must be the larger bound"
            )
        # an inline limit above the freeze cap makes the two 413s bite in a confusing order
        if self.bulk_inline_limit > self.bulk_max_targets:
            raise ValueError(
                "bulk_inline_limit must be ≤ bulk_max_targets — the freeze cap bounds what the"
                " inline path may ever be offered"
            )
        # a warning as long as the window would start before the cluster had even gone quiet
        if 0 < self.cluster_retire_after_days <= self.cluster_retirement_warn_days:
            raise ValueError(
                "cluster_retirement_warn_days must be shorter than cluster_retire_after_days"
            )
        # a schedule the scheduler cannot follow would fail silently at 03:00, not at boot
        for name in type(self).model_fields:
            if name.startswith("job_") and name.endswith("_cron"):
                expression = str(getattr(self, name)).strip()
                if expression:
                    try:
                        validate_cron(expression)
                    except ValueError as exc:
                        raise ValueError(f"JAVV_{name.upper()}: {exc}") from exc
        return self

    @model_validator(mode="after")
    def _opensearch_login_is_coherent(self) -> "Settings":
        # values never go in these messages: the password is a secret, and the URL may carry one
        if bool(self.opensearch_username) != bool(self.opensearch_password.get_secret_value()):
            raise ValueError(
                "JAVV_OPENSEARCH_USERNAME and JAVV_OPENSEARCH_PASSWORD go together: set both or"
                " neither"
            )
        url = split_opensearch_url(self.opensearch_url)
        if url.username is not None or url.password is not None:
            raise ValueError(
                "JAVV_OPENSEARCH_URL carries a user or password; set JAVV_OPENSEARCH_USERNAME and"
                " JAVV_OPENSEARCH_PASSWORD instead"
            )
        bundle = self.opensearch_ca_bundle.strip()
        if bundle and not self.opensearch_verify_certs:
            raise ValueError(
                "JAVV_OPENSEARCH_CA_BUNDLE is set but JAVV_OPENSEARCH_VERIFY_CERTS is false; a CA"
                " bundle only matters when certificates are checked"
            )
        if bundle and not (Path(bundle).is_file() and os.access(bundle, os.R_OK)):
            raise ValueError("JAVV_OPENSEARCH_CA_BUNDLE: no readable file at that path")
        return self


def split_opensearch_url(url: str) -> SplitResult:
    """Parse the URL as opensearch-py does: without `://` it reads `//<url>`, so
    `user:pw@store:9200` is a host carrying credentials (plain http), not a scheme named `user`."""
    return urlsplit(url if "://" in url else "//" + url)


def describe_errors(exc: ValidationError) -> str:
    """One line per error, `JAVV_<FIELD>: <message>`, with no input value in it. A field error
    carries the name only in `loc`; a model-level error writes it into its own message."""
    lines = []
    for error in exc.errors(include_input=False, include_url=False):
        loc = error["loc"]
        lines.append(f"JAVV_{str(loc[0]).upper()}: {error['msg']}" if loc else error["msg"])
    return "invalid settings: " + "; ".join(lines)


# Retired names: a deployment still setting one stops at start, rather than running on the dev
# default and refusing every scanner token without a word.
_RENAMED = {"JAVV_TOKEN_PEPPER": "JAVV_SECRET_KEY"}


@lru_cache
def get_settings() -> Settings:
    for old, new in _RENAMED.items():
        if old in os.environ:
            raise RuntimeError(
                f"{old} is now {new}: rename it and keep the same value. A new value stops every"
                " scanner token, session and download link from working."
            )
    try:
        return Settings()
    except ValidationError as exc:
        # `from None`: the chained ValidationError would print its input dict in the traceback
        raise RuntimeError(describe_errors(exc)) from None


_DEV_SECRET_KEY = "dev-only-secret-key"


def assert_production_ready(settings: Settings) -> None:
    """Fail-fast profile guard (task C / audit M3): a prod-profile process must never run on the
    dev conveniences. Called at the top of the app lifespan — raising here aborts startup."""
    if settings.env.lower() not in ("prod", "production"):
        return
    if settings.secret_key == _DEV_SECRET_KEY:
        raise RuntimeError(
            "JAVV_ENV is production but JAVV_SECRET_KEY is the dev default: every ingest-token"
            " and session hash would be forgeable from the docs. Set a real secret."
        )
