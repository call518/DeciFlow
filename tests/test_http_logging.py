"""Verify optional HTTP log files and bounded retention."""

import subprocess
import sys
from pathlib import Path

import pytest
from uvicorn.config import LOGGING_CONFIG

import server


def test_empty_directory_keeps_console_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECIFLOW_LOG_DIR", "")
    assert server.get_log_config() == LOGGING_CONFIG


def test_default_log_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert server.DEFAULT_LOG_DIR == "/var/log/deciflow"
    directory = tmp_path / "var" / "log" / "deciflow"
    monkeypatch.setattr(server, "DEFAULT_LOG_DIR", str(directory))
    monkeypatch.delenv("DECIFLOW_LOG_DIR", raising=False)
    config = server.get_log_config()
    assert directory.is_dir()
    assert config["handlers"]["access_file"]["filename"] == str(
        directory / "access.log"
    )


def test_separate_rotating_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directory = tmp_path / "nested" / "logs"
    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(directory))
    config = server.get_log_config()
    assert config["handlers"]["server_file"]["maxBytes"] == 10 * 1024 * 1024
    assert config["handlers"]["access_file"]["backupCount"] == 5
    assert LOGGING_CONFIG["loggers"]["uvicorn"]["handlers"] == ["default"]
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging, logging.config, server; "
                "logging.config.dictConfig(server.get_log_config()); "
                "logging.getLogger('uvicorn.error').error('server failure'); "
                "logging.getLogger('uvicorn.access').info('%s - %s %s HTTP/%s %s', "
                "'127.0.0.1:1234', 'GET', '/api/status', '1.1', 200); "
                "logging.shutdown()"
            ),
        ],
        check=True,
        capture_output=True,
    )
    server_log = (directory / "server.log").read_text()
    access_log = (directory / "access.log").read_text()
    assert "server failure" in server_log
    assert '127.0.0.1:1234 - "GET /api/status HTTP/1.1" 200' in access_log
    assert "server failure" not in access_log
    assert "/api/status" not in server_log


def test_relative_log_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(server, "ROOT", tmp_path)
    monkeypatch.setenv("DECIFLOW_LOG_DIR", "logs")
    config = server.get_log_config()
    assert config["handlers"]["server_file"]["filename"] == str(
        tmp_path / "logs" / "server.log"
    )
