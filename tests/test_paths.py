"""Environment file selection must never merge installations."""

from pathlib import Path

import pytest

from deciflow.paths import resolve_env_path


def test_environment_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DECIFLOW_ENV_PATH", raising=False)
    local = tmp_path / ".env"
    local.touch()
    default = tmp_path / "home/.config/deciflow/.env"
    default.parent.mkdir(parents=True)
    default.touch()
    for value in [None, ""]:
        if value is None:
            monkeypatch.delenv("DECIFLOW_ENV_PATH", raising=False)
        else:
            monkeypatch.setenv("DECIFLOW_ENV_PATH", value)
        with pytest.raises(ValueError, match="Set DECIFLOW_ENV_PATH"):
            resolve_env_path()
    explicit = tmp_path / "custom.env"
    explicit.touch()
    monkeypatch.setenv("DECIFLOW_ENV_PATH", explicit.name)
    assert resolve_env_path() == explicit
    explicit.unlink()
    with pytest.raises(ValueError, match="custom.env"):
        resolve_env_path()
    monkeypatch.setenv("DECIFLOW_ENV_PATH", "~/.config/deciflow/.env")
    assert resolve_env_path() == default
