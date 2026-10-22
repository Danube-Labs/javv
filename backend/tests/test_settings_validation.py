"""Settings validation (#219, major-audit 06 §2) — borked config fails at BOOT, never at
request N. Before this, `JAVV_SESSION_TTL_HOURS=-5` / `JAVV_EXPORT_MAX_ROWS=0` booted green and
passed /readyz while every request failed — the worst failure mode (looks healthy, is bricked).

The pepper rule is deliberately NOT here — `assert_production_ready` owns it (env-profile aware);
two overlapping guards with different profiles is how contradictions are born."""

import pytest
from pydantic import ValidationError

from backend.core.settings import Settings, get_settings
from backend.query.pit_guard import _keep_alive_s


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("JAVV_REQUEST_TIMEOUT", "0"),
        ("JAVV_REQUEST_TIMEOUT", "-1"),
        ("JAVV_INGEST_MAX_COMPRESSED_BYTES", "0"),
        ("JAVV_INGEST_MAX_BODY_BYTES", "-5"),
        ("JAVV_INGEST_RATE_LIMIT_PER_MINUTE", "0"),
        ("JAVV_SESSION_TTL_HOURS", "-5"),
        ("JAVV_LOGIN_MAX_ATTEMPTS", "0"),
        ("JAVV_LOGIN_LOCKOUT_MINUTES", "0"),
        ("JAVV_BULK_INLINE_LIMIT", "-1"),
        ("JAVV_BULK_MAX_TARGETS", "0"),
        ("JAVV_EXPORT_MAX_ROWS", "0"),
        ("JAVV_MAX_CONCURRENT_PITS_PER_PRINCIPAL", "0"),
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "banana"),
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "2"),  # bare number — unit required
        ("JAVV_SEARCH_PIT_KEEP_ALIVE", "2 m"),
        ("JAVV_EXPORT_TTL_HOURS", "0"),
        ("JAVV_EXPORT_MAX_BYTES", "0"),
        ("JAVV_REPORT_LEASE_TTL_SECONDS", "0"),
        ("JAVV_REPORT_DRAIN_SLEEP_MS", "-1"),  # 0 is legal (no throttle); negative is not
        ("JAVV_EXPORT_MAX_ROWS", "lots"),  # type garbage pinned too (pydantic coercion)
        ("JAVV_SESSION_COOKIE_SECURE", "maybe"),
    ],
)
def test_semantically_broken_values_are_rejected(monkeypatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError) as exc:
        Settings()
    # operators read pod logs: the failure must NAME the offending field
    assert var.removeprefix("JAVV_").lower() in str(exc.value)


def test_inverted_ingest_caps_are_rejected(monkeypatch) -> None:
    """compressed cap above the decompressed cap silently disables the zip-bomb guard."""
    monkeypatch.setenv("JAVV_INGEST_MAX_COMPRESSED_BYTES", str(100 * 1024 * 1024))
    monkeypatch.setenv("JAVV_INGEST_MAX_BODY_BYTES", str(10 * 1024 * 1024))
    with pytest.raises(ValidationError, match="ingest_max_compressed_bytes"):
        Settings()


def test_inverted_bulk_bounds_are_rejected(monkeypatch) -> None:
    """inline limit above the freeze cap makes the 413s bite in a confusing order."""
    monkeypatch.setenv("JAVV_BULK_INLINE_LIMIT", "20000")
    monkeypatch.setenv("JAVV_BULK_MAX_TARGETS", "10000")
    with pytest.raises(ValidationError, match="bulk_inline_limit"):
        Settings()


def test_defaults_and_legit_values_pass(monkeypatch) -> None:
    Settings()  # the shipped defaults must obviously validate
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", "1500ms")
    monkeypatch.setenv("JAVV_REPORT_DRAIN_SLEEP_MS", "0")  # 0 = no throttle, legitimate in dev
    assert Settings().search_pit_keep_alive == "1500ms"


def test_the_session_cookie_is_secure_unless_switched_off(monkeypatch) -> None:
    """Secure by default: JAVV cannot see a TLS terminator in front of it, so only an install
    served over plain http switches it off (issue 452)."""
    assert Settings().session_cookie_secure is True
    monkeypatch.setenv("JAVV_SESSION_COOKIE_SECURE", "false")
    assert Settings().session_cookie_secure is False


@pytest.mark.parametrize(
    ("ka", "seconds"),
    [("2m", 120.0), ("30s", 30.0), ("1h", 3600.0), ("1500ms", 1.5)],
)
def test_pit_horizon_parses_the_validated_grammar(monkeypatch, ka: str, seconds: float) -> None:
    """The silent 120s fallback is GONE (06 §2 ruling: silent fallbacks hide exactly this class
    of bug) — settings validation guarantees the grammar, the parser handles every unit of it."""
    monkeypatch.setenv("JAVV_SEARCH_PIT_KEEP_ALIVE", ka)
    get_settings.cache_clear()
    assert _keep_alive_s() == seconds


async def test_broken_env_aborts_startup(monkeypatch) -> None:
    """The failure surface: lifespan's get_settings() call aborts boot (crash-loop with a
    readable error beats healthy-looking-but-broken). It raises RuntimeError naming the
    variable, not pydantic's ValidationError, whose input dict would print secrets (issue 715)."""
    from backend.core.lifespan import lifespan
    from backend.main import create_app

    monkeypatch.setenv("JAVV_SESSION_TTL_HOURS", "-5")
    get_settings.cache_clear()
    app = create_app()
    with pytest.raises(RuntimeError, match="JAVV_SESSION_TTL_HOURS"):
        async with lifespan(app):
            pass


# --- background job schedules (issue 691) ----------------------------------------------

SCHEDULED_KINDS = (
    "report_drain",
    "report_sweep",
    "staleness_sweep",
    "lifecycle_sweep",
    "findings_cleanup",
    "cluster_retirement",
    "session_sweep",
)


def test_every_scheduled_kind_in_the_registry_has_a_schedule_setting() -> None:
    from backend.jobs.registry import JOBS

    settings = Settings()
    assert {kind for kind in JOBS if settings.job_cron(kind)} == set(SCHEDULED_KINDS)
    assert settings.job_cron("rebuild_state") == ""  # only ever run by hand


def test_the_default_schedules_are_the_ruled_ones(monkeypatch) -> None:
    monkeypatch.delenv("JAVV_SCHEDULER_ENABLED", raising=False)  # the suite runs with it off
    settings = Settings()
    assert settings.scheduler_enabled is True
    assert {kind: settings.job_cron(kind) for kind in SCHEDULED_KINDS} == {
        "report_drain": "*/5 * * * *",
        "report_sweep": "15 * * * *",
        "staleness_sweep": "0 2 * * *",
        "lifecycle_sweep": "0 3 * * *",
        "findings_cleanup": "0 4 * * *",
        "cluster_retirement": "15 4 * * *",
        "session_sweep": "30 4 * * *",
    }


@pytest.mark.parametrize("kind", SCHEDULED_KINDS)
def test_a_malformed_schedule_is_refused_and_names_its_variable(monkeypatch, kind: str) -> None:
    var = f"JAVV_JOB_{kind.upper()}_CRON"
    monkeypatch.setenv(var, "every night")
    with pytest.raises(ValidationError, match=var):
        Settings()


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_schedule_switches_the_job_off(monkeypatch, value: str) -> None:
    monkeypatch.setenv("JAVV_JOB_LIFECYCLE_SWEEP_CRON", value)
    settings = Settings()
    assert settings.job_cron("lifecycle_sweep") == ""
    assert settings.job_cron("staleness_sweep") == "0 2 * * *"  # the others are untouched


def test_a_schedule_can_be_overridden_and_the_scheduler_switched_off(monkeypatch) -> None:
    monkeypatch.setenv("JAVV_JOB_REPORT_DRAIN_CRON", "* * * * *")
    monkeypatch.setenv("JAVV_SCHEDULER_ENABLED", "false")
    settings = Settings()
    assert settings.job_cron("report_drain") == "* * * * *"
    assert settings.scheduler_enabled is False


async def test_a_malformed_schedule_aborts_startup(monkeypatch) -> None:
    from backend.main import create_app

    monkeypatch.setenv("JAVV_JOB_STALENESS_SWEEP_CRON", "61 * * * *")
    app = create_app()
    with pytest.raises(RuntimeError, match="JAVV_JOB_STALENESS_SWEEP_CRON"):
        async with app.router.lifespan_context(app):
            pass


def test_a_warning_as_long_as_the_retirement_window_is_refused() -> None:
    with pytest.raises(ValidationError, match="cluster_retirement_warn_days"):
        Settings(cluster_retire_after_days=5, cluster_retirement_warn_days=5)
    # 0 = never retire: any warning length is fine then
    assert Settings(cluster_retire_after_days=0, cluster_retirement_warn_days=30)


def test_the_retirement_seeds_reach_the_window_and_zero_means_never(monkeypatch) -> None:
    from backend.admin.cluster_retirement import RetirementWindow

    monkeypatch.setenv("JAVV_CLUSTER_RETIRE_AFTER_DAYS", "60")
    monkeypatch.setenv("JAVV_CLUSTER_RETIREMENT_WARN_DAYS", "10")
    get_settings.cache_clear()
    try:
        assert RetirementWindow() == RetirementWindow(retire_after_days=60, warn_days=10)
        monkeypatch.setenv("JAVV_CLUSTER_RETIRE_AFTER_DAYS", "0")
        get_settings.cache_clear()
        assert RetirementWindow().retire_after_days is None
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- the bootstrap admin password (issue 833) -------------------------------------------


async def test_a_bootstrap_password_sign_in_could_never_take_aborts_startup(monkeypatch) -> None:
    """Sign-in caps a password at 256 characters, so a longer bootstrap one could never sign in.
    The error names the variable and never holds the value."""
    from backend.main import create_app

    secret = "s3cret-" + "x" * 250  # 257 characters
    monkeypatch.setenv("JAVV_BOOTSTRAP_ADMIN_PASSWORD", secret)
    app = create_app()
    with pytest.raises(RuntimeError, match="JAVV_BOOTSTRAP_ADMIN_PASSWORD") as caught:
        async with app.router.lifespan_context(app):
            pass
    assert "s3cret" not in str(caught.value)


@pytest.mark.parametrize("length", [256, 11], ids=["at-the-cap", "under-the-minimum"])
def test_a_bootstrap_password_up_to_the_cap_is_accepted(monkeypatch, length: int) -> None:
    # under 12 stays allowed: it is a first-login password, changed at once (issue 724)
    monkeypatch.setenv("JAVV_BOOTSTRAP_ADMIN_PASSWORD", "y" * length)
    assert len(get_settings().bootstrap_admin_password) == length


# --- the bootstrap admin name (issue 965) ------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["Rootadmin", "ROOTADMIN", "system", "ab", "root admin"],
    ids=["capital", "upper", "reserved", "too-short", "space"],
)
async def test_a_bootstrap_name_the_create_route_would_refuse_aborts_startup(
    monkeypatch, name: str
) -> None:
    """The first admin follows the same username rule as every other user. The error names the
    variable and never holds the value."""
    from backend.main import create_app

    monkeypatch.setenv("JAVV_BOOTSTRAP_ADMIN_USERNAME", name)
    app = create_app()
    with pytest.raises(RuntimeError, match="JAVV_BOOTSTRAP_ADMIN_USERNAME") as caught:
        async with app.router.lifespan_context(app):
            pass
    assert name not in str(caught.value)


def test_a_lower_case_bootstrap_name_and_the_default_pass(monkeypatch) -> None:
    assert get_settings().bootstrap_admin_username == "admin"
    monkeypatch.setenv("JAVV_BOOTSTRAP_ADMIN_USERNAME", "root.admin-1")
    get_settings.cache_clear()
    assert get_settings().bootstrap_admin_username == "root.admin-1"
