"""The reset command for a forgotten password (issue 761): the way back when no admin can sign in.

It does what an admin's password-reset route does (a temporary password, `must_change`, the user's
sessions revoked, a `pwd_reset` row written first) with `system` as the actor, and it prints the
password once without ever logging it. Real OpenSearch, prefix-isolated; the `__main__` cases run
the module as an operator would, against the unprefixed store, with `u-*` users the session sweep
removes."""

import os
import subprocess
import sys
import uuid
from typing import Any

import pytest
import structlog
from opensearchpy import AsyncOpenSearch
from structlog.typing import EventDict

from backend.auth import reset_password as cli
from backend.auth.passwords import MIN_LENGTH, hash_password, verify_password
from backend.auth.reset_password import (
    ResetRefused,
    SessionsNotEnded,
    reset_password,
    temporary_password,
)
from backend.auth.sessions import lookup_session, mint_session
from os_env import OS_URL, requires_opensearch

pytestmark = requires_opensearch

OLD_PASSWORD = "the password nobody remembers"


async def _seed(client: AsyncOpenSearch, prefix: str, *, auth_source: str = "local") -> str:
    username = f"u-{uuid.uuid4().hex[:12]}"
    await client.index(
        index=f"{prefix}system-users",
        id=username,
        body={
            "username": username,
            "password_hash": hash_password(OLD_PASSWORD),
            "role": "admin",
            "capabilities": ["*"],
            "must_change": False,
            "disabled": False,
            "auth_source": auth_source,
            "external_id": None,
            "created_at": "2026-10-06T00:00:00+00:00",
        },
        params={"refresh": "true"},
    )
    return username


async def _user(client: AsyncOpenSearch, prefix: str, username: str) -> dict[str, Any]:
    return (await client.get(index=f"{prefix}system-users", id=username))["_source"]


async def _audit_rows(client: AsyncOpenSearch, prefix: str, username: str) -> list[dict[str, Any]]:
    hits = await client.search(
        index=f"{prefix}system-audit-log*",
        body={"query": {"term": {"entity_id": username}}},
        params={"ignore_unavailable": "true"},
    )
    return [h["_source"] for h in hits["hits"]["hits"]]


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> list[EventDict]:
    capture = structlog.testing.LogCapture()
    monkeypatch.setattr(cli, "log", structlog.wrap_logger(None, processors=[capture]))
    return capture.entries


def test_a_temporary_password_meets_the_policy_and_is_never_the_same_twice() -> None:
    passwords = {temporary_password() for _ in range(50)}
    assert len(passwords) == 50
    assert all(len(p) >= MIN_LENGTH for p in passwords)


async def test_the_new_password_signs_in_once_and_must_be_changed(real_os, captured) -> None:
    client, prefix = real_os
    username = await _seed(client, prefix)
    session = await mint_session(client, username, prefix=prefix)

    temp = await reset_password(client, username, prefix=prefix)

    user = await _user(client, prefix, username)
    assert verify_password(temp, user["password_hash"])
    assert not verify_password(OLD_PASSWORD, user["password_hash"])
    assert user["must_change"] is True
    assert await lookup_session(client, session, prefix=prefix) is None
    rows = await _audit_rows(client, prefix, username)
    assert [(r["actor"], r["action"], r["entity_type"]) for r in rows] == [
        ("system", "pwd_reset", "user")
    ]


async def test_the_password_is_logged_never(real_os, captured) -> None:
    client, prefix = real_os
    username = await _seed(client, prefix)

    temp = await reset_password(client, username, prefix=prefix)

    assert captured == [
        {"event": "password reset", "log_level": "info", "username": username, "actor": "system"}
    ]
    assert temp not in repr(captured)


async def test_an_unknown_user_changes_nothing(real_os, captured) -> None:
    client, prefix = real_os
    username = f"u-{uuid.uuid4().hex[:12]}"

    with pytest.raises(ResetRefused, match="no user named"):
        await reset_password(client, username, prefix=prefix)

    assert await _audit_rows(client, prefix, username) == []
    assert captured == []


async def test_a_user_of_an_identity_provider_is_refused(real_os, captured) -> None:
    client, prefix = real_os
    username = await _seed(client, prefix, auth_source="oidc")

    with pytest.raises(ResetRefused, match="identity provider"):
        await reset_password(client, username, prefix=prefix)

    user = await _user(client, prefix, username)
    assert verify_password(OLD_PASSWORD, user["password_hash"])
    assert user["must_change"] is False
    assert await _audit_rows(client, prefix, username) == []


async def test_without_its_audit_row_the_reset_does_not_happen(
    real_os, captured, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, prefix = real_os
    username = await _seed(client, prefix)
    session = await mint_session(client, username, prefix=prefix)

    async def failing_append(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(cli, "append_auth_event", failing_append)
    with pytest.raises(RuntimeError, match="audit store unavailable"):
        await reset_password(client, username, prefix=prefix)

    user = await _user(client, prefix, username)
    assert verify_password(OLD_PASSWORD, user["password_hash"])
    assert user["must_change"] is False
    assert await lookup_session(client, session, prefix=prefix) is not None


async def test_sessions_that_cannot_be_ended_still_hand_over_the_password(
    real_os, captured, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hash is written before the sessions end (a sign-in between the two would otherwise
    keep its session), so a failed revoke must not lose the password it set (issue 833)."""
    client, prefix = real_os
    username = await _seed(client, prefix)

    async def failing_revoke(*args: Any, **kwargs: Any) -> int:
        raise RuntimeError("sessions store unavailable")

    monkeypatch.setattr(cli, "revoke_all_for_user", failing_revoke)
    with pytest.raises(SessionsNotEnded) as caught:
        await reset_password(client, username, prefix=prefix)

    user = await _user(client, prefix, username)
    assert verify_password(caught.value.password, user["password_hash"])
    assert user["must_change"] is True
    assert caught.value.password not in str(caught.value)
    assert captured == [
        {
            "event": "password reset, sessions not ended",
            "log_level": "warning",
            "username": username,
            "actor": "system",
            "error": "RuntimeError",
        }
    ]


def _run_command(username: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "backend.auth.reset_password", username],
        env={**os.environ, "JAVV_OPENSEARCH_URL": OS_URL},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


async def test_the_command_prints_the_password_alone_and_logs_to_stderr() -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        username = await _seed(client, "")
        done = _run_command(username)
        user = await _user(client, "", username)
    finally:
        await client.close()

    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    assert len(lines) == 1
    assert verify_password(lines[0], user["password_hash"])
    assert '"event": "password reset"' in done.stderr
    assert lines[0] not in done.stderr


def test_the_command_exits_1_for_an_unknown_user_and_prints_no_password() -> None:
    done = _run_command(f"u-{uuid.uuid4().hex[:12]}")

    assert done.returncode == 1
    assert done.stdout == ""
    assert "not reset: no user named" in done.stderr


@pytest.mark.serial  # blocks writes to the shared sessions index while the command runs
async def test_the_command_prints_the_password_and_exits_1_when_sessions_stay() -> None:
    client = AsyncOpenSearch(hosts=[OS_URL])
    try:
        username = await _seed(client, "")
        await mint_session(client, username)
        await client.indices.put_settings(
            index="system-sessions", body={"index.blocks.write": True}
        )
        try:
            done = _run_command(username)
        finally:
            await client.indices.put_settings(
                index="system-sessions", body={"index.blocks.write": None}
            )
        user = await _user(client, "", username)
    finally:
        await client.close()

    assert done.returncode == 1
    lines = done.stdout.splitlines()
    assert len(lines) == 1
    assert verify_password(lines[0], user["password_hash"])
    assert "sessions were not ended" in done.stderr
    assert lines[0] not in done.stderr
