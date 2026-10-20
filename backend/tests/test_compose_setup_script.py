"""deploy/compose/setup.sh makes `.env` for a new compose install (issue 869): random secrets that
survive compose's rewriting of `$`, `#`, quotes and spaces, an OpenSearch admin password that
OpenSearch accepts, and the first admin password shown one time. The script runs here on a copy of
the real template, so a template that loses one of its keys fails here, not on an install."""

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).parents[2] / "deploy" / "compose"
SECRETS = (
    "JAVV_SECRET_KEY",
    "JAVV_BOOTSTRAP_ADMIN_PASSWORD",
    "JAVV_OPENSEARCH_ADMIN_PASSWORD",
    "JAVV_OPENSEARCH_PASSWORD",
)
COOKIE_LINE = "JAVV_SESSION_COOKIE_SECURE=false"
# compose takes an unquoted value like this one as it is: no `$`, `#`, quote or space
COMPOSE_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_MAP_COUNT = Path("/proc/sys/vm/max_map_count")
CI = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    for name in ("setup.sh", ".env.example"):
        shutil.copy2(COMPOSE / name, tmp_path / name)
    return tmp_path


# the tools that the script calls, for a PATH without docker
TOOLS = ("sh", "od", "tr", "grep", "awk", "mktemp", "chmod", "mv", "rm", "cat", "sed", "dirname")


def _run(
    folder: Path,
    *args: str,
    volumes: tuple[str, ...] = (),
    docker: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    # from another folder: the script works in its own folder, wherever it is called from. A
    # stand-in docker knows only `volumes`, so no test sees the volumes of the machine it runs on.
    with tempfile.TemporaryDirectory() as bin_dir:
        if docker:
            fake = Path(bin_dir) / "docker"
            fake.write_text(
                '#!/bin/sh\n[ "$1 $2" = "volume inspect" ] || exit 1\n'
                f'for v in {" ".join(volumes)}; do [ "$3" = "$v" ] && exit 0; done\nexit 1\n'
            )
            fake.chmod(0o755)
            path = bin_dir + os.pathsep + os.environ["PATH"]
        else:
            for tool in TOOLS:
                os.symlink(shutil.which(tool) or tool, Path(bin_dir) / tool)
            path = bin_dir
        run_env = {k: v for k, v in os.environ.items() if k != "COMPOSE_PROJECT_NAME"}
        return subprocess.run(
            ["sh", str(folder / "setup.sh"), *args],
            capture_output=True,
            text=True,
            cwd=folder.parent,
            env=run_env | {"PATH": path} | (env or {}),
            check=False,
        )


def _values(env_file: Path) -> dict[str, str]:
    lines = env_file.read_text().splitlines()
    pairs = (line.split("=", 1) for line in lines if line and not line.startswith("#"))
    return {key: value for key, value in pairs}


def test_the_four_secrets_are_set_and_the_rest_of_the_template_stays(folder: Path) -> None:
    result = _run(folder)
    assert result.returncode == 0, result.stderr
    values = _values(folder / ".env")
    assert all(values[key] for key in SECRETS)
    template = (folder / ".env.example").read_text().splitlines()
    made = (folder / ".env").read_text().splitlines()
    expected = [f"{line}{values[line[:-1]]}" if line[:-1] in SECRETS else line for line in template]
    assert made == expected


def test_each_secret_survives_compose_and_obeys_its_length(folder: Path) -> None:
    assert _run(folder).returncode == 0
    values = _values(folder / ".env")
    for key in SECRETS:
        assert COMPOSE_SAFE.fullmatch(values[key]), key
    assert re.fullmatch(r"[0-9a-f]{64}", values["JAVV_SECRET_KEY"])
    # the backend stops at start outside 12 to 256 characters
    assert 12 <= len(values["JAVV_BOOTSTRAP_ADMIN_PASSWORD"]) <= 256


def test_the_opensearch_admin_password_obeys_the_rules_of_opensearch(folder: Path) -> None:
    assert _run(folder).returncode == 0
    password = _values(folder / ".env")["JAVV_OPENSEARCH_ADMIN_PASSWORD"]
    assert len(password) >= 8
    for kind in (r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9]"):
        assert re.search(kind, password), kind


def test_two_installs_get_different_secrets(tmp_path: Path) -> None:
    made = []
    for name in ("one", "two"):
        target = tmp_path / name
        target.mkdir()
        for file in ("setup.sh", ".env.example"):
            shutil.copy2(COMPOSE / file, target / file)
        assert _run(target).returncode == 0
        made.append(_values(target / ".env"))
    assert all(made[0][key] != made[1][key] for key in SECRETS)


def test_the_admin_password_shows_one_time_and_no_other_secret_shows(folder: Path) -> None:
    result = _run(folder)
    values = _values(folder / ".env")
    shown = result.stdout + result.stderr
    assert shown.count(values["JAVV_BOOTSTRAP_ADMIN_PASSWORD"]) == 1
    for key in ("JAVV_SECRET_KEY", "JAVV_OPENSEARCH_ADMIN_PASSWORD", "JAVV_OPENSEARCH_PASSWORD"):
        assert values[key] not in shown, key


def test_only_the_owner_can_read_the_env_file(folder: Path) -> None:
    assert _run(folder).returncode == 0
    assert stat.S_IMODE((folder / ".env").stat().st_mode) == 0o600


def test_an_env_file_that_exists_is_never_replaced(folder: Path) -> None:
    # a new secret key would end every token and session of the install
    (folder / ".env").write_text("JAVV_SECRET_KEY=keep-me\n")
    result = _run(folder)
    assert result.returncode == 1
    assert (folder / ".env").read_text() == "JAVV_SECRET_KEY=keep-me\n"
    assert ".env exists" in result.stderr


def test_an_earlier_install_stops_the_script_and_makes_no_file(folder: Path) -> None:
    # a new .env on the volume of an earlier install fails: OpenSearch keeps the passwords of its
    # first start, so the health check of the new install gets 401
    result = _run(folder, volumes=("javv_opensearch-data",))
    assert result.returncode == 1
    assert "javv_opensearch-data" in result.stderr
    assert "docker compose down -v" in result.stderr
    assert "COMPOSE_PROJECT_NAME=" in result.stderr
    assert not (folder / ".env").exists()


def test_a_project_name_makes_a_second_install_and_goes_in_the_env_file(folder: Path) -> None:
    result = _run(
        folder, volumes=("javv_opensearch-data",), env={"COMPOSE_PROJECT_NAME": "javv-test"}
    )
    assert result.returncode == 0, result.stderr
    assert _values(folder / ".env")["COMPOSE_PROJECT_NAME"] == "javv-test"


def test_the_volume_of_that_project_name_also_stops_the_script(folder: Path) -> None:
    result = _run(
        folder, volumes=("javv-test_opensearch-data",), env={"COMPOSE_PROJECT_NAME": "javv-test"}
    )
    assert result.returncode == 1
    assert "javv-test_opensearch-data" in result.stderr
    assert not (folder / ".env").exists()


@pytest.mark.parametrize("name", ["Javv", "javv test", "-javv"])
def test_a_project_name_that_compose_refuses_stops_the_script(folder: Path, name: str) -> None:
    result = _run(folder, env={"COMPOSE_PROJECT_NAME": name})
    assert result.returncode == 2
    assert not (folder / ".env").exists()


def test_without_docker_the_script_still_makes_the_env_file(folder: Path) -> None:
    # docker can be missing here, or need sudo: the script then cannot look for a volume
    result = _run(folder, docker=False)
    assert result.returncode == 0, result.stderr
    assert (folder / ".env").exists()


def test_plain_http_keeps_the_cookie_line_and_https_removes_it(
    folder: Path, tmp_path: Path
) -> None:
    assert _run(folder).returncode == 0
    assert COOKIE_LINE in (folder / ".env").read_text().splitlines()
    https = tmp_path / "https"
    https.mkdir()
    for file in ("setup.sh", ".env.example"):
        shutil.copy2(COMPOSE / file, https / file)
    assert _run(https, "--https").returncode == 0
    assert "JAVV_SESSION_COOKIE_SECURE" not in _values(https / ".env")


def test_an_unknown_option_stops_the_script_and_makes_no_file(folder: Path) -> None:
    result = _run(folder, "--http")
    assert result.returncode == 2
    assert not (folder / ".env").exists()


def test_help_by_a_relative_path_shows_both_commands_and_makes_no_file(folder: Path) -> None:
    # `sh compose/setup.sh --help` from the parent folder: the script changes folder before it
    # reads its own help, so a relative path to it must still work
    result = subprocess.run(
        ["sh", f"{folder.name}/setup.sh", "--help"],
        capture_output=True,
        text=True,
        cwd=folder.parent,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "./setup.sh --https" in result.stdout
    assert "Use --https only when" in result.stdout
    assert not (folder / ".env").exists()


@pytest.mark.parametrize("key", [*SECRETS, "JAVV_SESSION_COOKIE_SECURE"])
def test_a_template_without_a_key_stops_the_script_and_makes_no_file(
    folder: Path, key: str
) -> None:
    template = folder / ".env.example"
    lines = template.read_text().splitlines()
    template.write_text("\n".join(line for line in lines if not line.startswith(f"{key}=")) + "\n")
    result = _run(folder, "--https") if key == "JAVV_SESSION_COOKIE_SECURE" else _run(folder)
    assert result.returncode == 1
    assert key in result.stderr
    assert not (folder / ".env").exists()


@pytest.mark.skipif(not MAX_MAP_COUNT.exists(), reason="no /proc/sys on this host")
def test_a_low_memory_map_limit_prints_the_command_and_a_good_one_prints_nothing(
    folder: Path,
) -> None:
    # the host decides which branch runs: the CI runner starts at 65530, a prepared host at 262144
    result = _run(folder)
    assert result.returncode == 0
    low = int(MAX_MAP_COUNT.read_text()) < 262144
    assert ("sysctl -w vm.max_map_count=262144" in result.stderr) is low


def test_the_compose_ci_job_installs_with_the_script() -> None:
    """The Compose stack job is the end-to-end proof: OpenSearch and the backend take what the
    script made, and the password it showed signs in. A secret in the job's env would win over
    .env in compose, and the job would then test nothing of the script."""
    job = yaml.safe_load(CI.read_text())["jobs"]["compose"]
    assert not set(job.get("env", {})) & {*SECRETS, "JAVV_SESSION_COOKIE_SECURE"}
    names = [step.get("name") for step in job["steps"]]
    runs = {step.get("name"): step.get("run", "") for step in job["steps"]}
    assert names.index("Make .env with the setup script") < names.index("Start the stack")
    assert "deploy/compose/setup.sh > setup.out" in runs["Make .env with the setup script"]
    assert "setup.out" in runs["Sign in through the frontend over plain http"]
