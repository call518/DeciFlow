"""Check lifecycle command arguments without changing Docker containers."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("action", ["up", "down"])
@pytest.mark.parametrize("selection", ["explicit", "default", "cwd"])
def test_compose_script(action: str, selection: str, tmp_path: Path) -> None:
    home = tmp_path / "user home"
    configuration = {
        "explicit": tmp_path / "custom settings.env",
        "default": home / ".config/deciflow/.env",
        "cwd": tmp_path / ".env",
    }[selection]
    configuration.parent.mkdir(parents=True, exist_ok=True)
    configuration.touch()
    binary = tmp_path / "docker"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    binary.chmod(0o755)
    environment = {**os.environ, "HOME": str(home), "PATH": f"{tmp_path}:/usr/bin:/bin"}
    environment["DECIFLOW_ENV_PATH"] = str(configuration)
    result = subprocess.run(
        [str(ROOT / "compose.sh"), action],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "compose",
        "--project-directory",
        str(ROOT),
        "-f",
        str(ROOT / "docker-compose.yml"),
        "--env-file",
        str(configuration),
        action,
        *(["-d", "--remove-orphans"] if action == "up" else []),
    ]


@pytest.mark.parametrize("arguments", [[], ["restart"], ["down", "--volumes"]])
def test_compose_script_rejects_arguments(arguments: list[str]) -> None:
    result = subprocess.run(
        [str(ROOT / "compose.sh"), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "Usage:" in result.stderr


@pytest.mark.parametrize("selector", [None, ""])
def test_compose_script_requires_configuration(
    tmp_path: Path, selector: str | None
) -> None:
    (tmp_path / ".env").touch()
    environment = {**os.environ, "HOME": str(tmp_path)}
    environment.pop("DECIFLOW_ENV_PATH", None)
    if selector is not None:
        environment["DECIFLOW_ENV_PATH"] = selector
    result = subprocess.run(
        [str(ROOT / "compose.sh"), "down"],
        check=False,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "DECIFLOW_ENV_PATH" in result.stderr


def test_explicit_missing_file_does_not_fall_back(tmp_path: Path) -> None:
    (tmp_path / ".env").touch()
    result = subprocess.run(
        [str(ROOT / "compose.sh"), "up"],
        cwd=tmp_path,
        env={**os.environ, "DECIFLOW_ENV_PATH": str(tmp_path / "missing.env")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "missing.env" in result.stderr
