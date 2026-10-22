"""The username rule, one copy for the create route and the bootstrap admin (issue 965).

A username is the user's document id in `system-users`, so a name in lower case only makes the
create-only write itself refuse a second `alice`. A check before the write could not: two creates
at the same moment both pass it (the probe on issue 965)."""

USERNAME_PATTERN = r"^[a-z0-9._-]+$"
USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 64

# machine actor literals (audit log + fleet-wide config): a human so named would do triage that
# never charts AND blur machine-vs-human audit forensics (A-m6)
RESERVED_USERNAMES = frozenset({"system", "fleet"})


def check_username(value: str) -> str:
    """The name unchanged, or a ValueError whose message never holds the name (issue 842)."""
    if value != value.lower():
        raise ValueError("a username must be in lower case")
    if value in RESERVED_USERNAMES:
        raise ValueError("this username is reserved")
    return value
