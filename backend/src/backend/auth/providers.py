"""Identity providers (M5a) — THE OIDC/LDAP seam (see the bolt README's auth design).

`IdentityProvider.authenticate` answers exactly one question: "is this human authentic, and which
`system-users` row are they?" Everything after — session mint, capabilities, auditing, logout — is
provider-agnostic and never forks per provider. Post-MVP `OidcProvider`/`LdapProvider` implement
this same protocol (verifying an IdP assertion / doing an LDAP bind + JIT-provisioning the user
row with `auth_source`/`external_id`) and the rest of the app doesn't change.

`LocalPasswordProvider` (the only MVP implementation) fails with one indistinct `None` for
unknown user / wrong password / non-local user / disabled account — and ALWAYS runs an argon2id
verify (against `DUMMY_HASH` when there's no real one), so response timing never reveals which
case it was."""

from dataclasses import dataclass
from typing import Any, Protocol

from opensearchpy import AsyncOpenSearch, NotFoundError
from pydantic import BaseModel, ConfigDict, Field

from backend.auth.passwords import DUMMY_HASH, verify_password

USERS_INDEX = "system-users"


class LoginCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=256)


@dataclass(frozen=True)
class AuthResult:
    user_id: str  # == the system-users doc _id (username)
    user: dict[str, Any]  # the _source — callers must strip password_hash before responding


class IdentityProvider(Protocol):
    async def authenticate(
        self, client: AsyncOpenSearch, creds: LoginCredentials, *, prefix: str = ""
    ) -> AuthResult | None: ...


class LocalPasswordProvider:
    """argon2id against `system-users` (auth_source=local)."""

    async def authenticate(
        self, client: AsyncOpenSearch, creds: LoginCredentials, *, prefix: str = ""
    ) -> AuthResult | None:
        found = await _find_user(client, f"{prefix}{USERS_INDEX}", creds.username)
        if found is None:
            verify_password(creds.password, DUMMY_HASH)  # timing equalizer — no user oracle
            return None
        user_id, doc = found
        stored = doc.get("password_hash")
        if doc.get("auth_source", "local") != "local" or not stored:
            verify_password(creds.password, DUMMY_HASH)  # external users have no local password
            return None
        if not verify_password(creds.password, stored) or doc.get("disabled"):
            return None
        return AuthResult(user_id=user_id, user=doc)


async def _find_user(
    client: AsyncOpenSearch, index: str, typed: str
) -> tuple[str, dict[str, Any]] | None:
    """Sign-in accepts a name in any case (RFC 8265's case-mapped lookup, issue 965). New names
    are lower case only, so the lower-case id is the user; a name stored with a capital letter
    before that rule still signs in as typed, which is why the exact id is tried first."""
    for user_id in dict.fromkeys((typed, typed.lower())):
        try:
            return user_id, (await client.get(index=index, id=user_id))["_source"]
        except NotFoundError:
            continue
    return None
