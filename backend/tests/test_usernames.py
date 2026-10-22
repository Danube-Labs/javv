"""The one username rule (issue 965): lower case only, and the machine actor names are not free.
Pure: no store, no app."""

import re

import pytest

from backend.auth.usernames import USERNAME_PATTERN, check_username


@pytest.mark.parametrize("name", ["alice", "a.b_c-1", "nu-0a1b2c3d4e5f", "admin"])
def test_a_lower_case_name_passes_unchanged(name: str) -> None:
    assert check_username(name) == name
    assert re.fullmatch(USERNAME_PATTERN, name)


@pytest.mark.parametrize("name", ["Alice", "ALICE", "aLiCe", "alicE"])
def test_a_capital_letter_is_refused_without_the_name_in_the_message(name: str) -> None:
    with pytest.raises(ValueError, match="a username must be in lower case") as caught:
        check_username(name)
    assert name not in str(caught.value)


@pytest.mark.parametrize("name", ["system", "fleet"])
def test_the_machine_actor_names_are_refused(name: str) -> None:
    with pytest.raises(ValueError, match="reserved"):
        check_username(name)


def test_the_pattern_has_no_capital_letters() -> None:
    assert not re.fullmatch(USERNAME_PATTERN, "Alice")
    assert not re.fullmatch(USERNAME_PATTERN, "al ice")
