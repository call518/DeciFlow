"""Verify optional HTTP log files and bounded retention."""

import subprocess
import sys
from pathlib import Path

import pytest
from uvicorn.config import LOGGING_CONFIG

from deciflow import server
from deciflow.process_control import DAEMON_ENV


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


@pytest.mark.parametrize("daemon", [False, True])
def test_separate_rotating_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, daemon: bool
) -> None:
    monkeypatch.setenv(DAEMON_ENV, "1" if daemon else "0")
    directory = tmp_path / "nested" / "logs"
    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(directory))
    config = server.get_log_config()
    assert config["handlers"]["server_file"]["maxBytes"] == 10 * 1024 * 1024
    assert config["handlers"]["access_file"]["backupCount"] == 5
    assert LOGGING_CONFIG["loggers"]["uvicorn"]["handlers"] == ["default"]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import logging, logging.config; from deciflow import server; "
                "logging.config.dictConfig(server.get_log_config()); "
                "logging.getLogger('uvicorn.error').error('server failure'); "
                "logging.getLogger('uvicorn.access').info('%s - %s %s HTTP/%s %s', "
                "'127.0.0.1:1234', 'GET', '/api/status', '1.1', 200); "
                "logging.shutdown(); print('startup output')"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert ("/api/status" in result.stdout) is not daemon
    assert ("server failure" in result.stderr) is not daemon
    assert "startup output" in result.stdout
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


@pytest.mark.parametrize("wrapped", [False, True])
def test_operational_diagnostics_hide_exception_values(
    caplog: pytest.LogCaptureFixture, wrapped: bool
) -> None:
    from deciflow.diagnostics import log_failure

    secret = "disposable-private-value"
    try:
        try:
            raise PermissionError(13, secret, f"/private/{secret}")
        except OSError as error:
            if wrapped:
                raise RuntimeError(secret) from error
            raise
    except (OSError, RuntimeError) as error:
        log_failure("Storage operation", error)
    assert "PermissionError" in caplog.text
    assert "errno=13" in caplog.text
    assert "Permission denied" in caplog.text
    assert "test_http_logging.py:" in caplog.text
    assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.anyio
@pytest.mark.parametrize("operation", ["storage", "criteria"])
async def test_handled_operational_failures_are_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    operation: str,
) -> None:
    import httpx

    secret = "disposable-provider-secret"
    if operation == "storage":

        def fail(*args):
            raise OSError(28, secret)

        monkeypatch.setattr(server, "read_archived_run", fail)
        endpoint = "/api/jobs/" + "a" * 32 + "/results"
        expected_status = 503
        expected_reason = "errno=28"
    else:

        async def fail_generation(body):
            raise httpx.ReadTimeout(secret)

        monkeypatch.setattr(server, "generate_criteria", fail_generation)
        endpoint = "/api/criteria/generate"
        expected_status = 502
        expected_reason = "ReadTimeout"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.post(endpoint, json={})
    assert response.status_code == expected_status
    assert expected_reason in caplog.text
    assert secret not in caplog.text + response.text


def test_sqlite_diagnostic_records_error_code_without_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import sqlite3

    from deciflow.diagnostics import log_failure

    with sqlite3.connect(":memory:") as database:
        try:
            database.execute("SELECT * FROM disposable_private_table")
        except sqlite3.Error as error:
            log_failure("Result storage", error)
    assert "sqlite_errorcode=1" in caplog.text
    assert "OperationalError" in caplog.text
    assert "disposable_private_table" not in caplog.text
