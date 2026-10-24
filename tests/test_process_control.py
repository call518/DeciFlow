"""Exercise CLI lifecycle with real detached processes and a local engine stub."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest

from deciflow import cli, process_control

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("disconnected", ["send", "read", "eof"])
def test_control_request_during_shutdown(tmp_path, monkeypatch, disconnected) -> None:
    from unittest.mock import MagicMock

    client = MagicMock()
    client.__enter__.return_value = client
    if disconnected == "send":
        client.sendall.side_effect = BrokenPipeError(32, "Broken pipe")
    elif disconnected == "read":
        client.makefile.return_value.readline.side_effect = ConnectionResetError()
    else:
        client.makefile.return_value.readline.return_value = b""
    monkeypatch.setattr(process_control.socket, "socket", lambda *args: client)
    # A shutdown can close the control connection after connect succeeds.
    assert process_control.request(tmp_path, "stop") is None


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def installation(tmp_path: Path) -> Iterator[tuple[Path, dict[str, str]]]:
    import socket

    engine = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    worker = Thread(target=engine.serve_forever, daemon=True)
    worker.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    directory = tmp_path / "configuration"
    cli.prepare_workspace(directory)
    for name in ("data", "logs"):
        (directory / name).mkdir()
    (directory / ".env").write_text(
        f"DECISION_ENGINE=laya\nLAYA_API_URL=http://127.0.0.1:{engine.server_port}/v1/systemone\n"
        "LAYA_API_KEY=\nOAUTH2_PROXY_ENABLED=false\nDECIFLOW_BIND_HOST=127.0.0.1\n"
        f"PORT={port}\nDECIFLOW_DATA_DIR={directory / 'data'}\n"
        f"DECIFLOW_LOG_DIR={directory / 'logs'}\n"
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DECIFLOW_", "LAYA_", "JEV_", "OAUTH2_", "_DECIFLOW_"))
        and key not in {"DECISION_ENGINE", "PORT"}
    }
    env["PYTHONPATH"] = str(ROOT)
    try:
        yield directory, env
    finally:
        invoke(directory, env, "stop")
        engine.shutdown()
        engine.server_close()
        worker.join()


def invoke(
    directory: Path, env: dict[str, str], *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "deciflow.cli", *args, "--config-dir", str(directory)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )


def test_daemon_lifecycle_and_restart(installation) -> None:
    directory, env = installation
    result = invoke(directory, env, "start", "--daemon")
    assert result.returncode == 0, result.stdout + result.stderr
    info = process_control.request(directory)
    assert info and info["state"] == "Running" and info["daemon"]
    pid = info["pid"]
    assert f"PID {pid}" in result.stdout
    assert "daemon.log" in result.stdout
    assert (directory / "logs/daemon.log").stat().st_mode & 0o777 == 0o600
    assert invoke(directory, env, "status").returncode == 0
    duplicate = invoke(directory, env, "start", "--daemon")
    assert duplicate.returncode == 1 and "already running" in duplicate.stderr
    base = info["url"]
    restart = urllib.request.Request(
        base + "/api/restart",
        data=b'{"confirmation":"RESTART DECIFLOW"}',
        headers={"Origin": base, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(restart, timeout=5) as response:
        assert response.status == 202
        previous = json.load(response)["instanceId"]
    deadline = time.monotonic() + 15
    while True:
        status = urllib.request.Request(
            base + "/api/reset/status", headers={"Origin": base}, method="POST"
        )
        try:
            with urllib.request.urlopen(status, timeout=1) as response:
                if json.load(response)["instanceId"] != previous:
                    break
        except OSError:
            pass
        assert time.monotonic() < deadline, (directory / "logs/daemon.log").read_text()
        time.sleep(0.1)
    restarted = process_control.request(directory)
    assert restarted and restarted["pid"] == pid
    assert invoke(directory, env, "start").returncode == 1
    configuration = directory / ".env"
    original = configuration.read_bytes()
    configuration.write_text("DECISION_ENGINE=invalid\n")
    assert invoke(directory, env, "status").returncode == 0
    result = invoke(directory, env, "stop")
    assert result.returncode == 0, result.stdout + result.stderr
    configuration.write_bytes(original)
    assert invoke(directory, env, "status").returncode == 3
    result = invoke(directory, env, "stop")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (directory / "data/deciflow.sqlite3").exists()
    # A released lock and stale control path must not prevent another launch.
    assert invoke(directory, env, "start", "--daemon").returncode == 0
    result = invoke(directory, env, "stop")
    assert result.returncode == 0, result.stdout + result.stderr


def test_failed_daemon_never_reports_success(installation) -> None:
    directory, env = installation
    path = directory / ".env"
    path.write_text(
        "\n".join(
            "LAYA_API_URL=http://127.0.0.1:1/v1/systemone"
            if line.startswith("LAYA_API_URL=")
            else line
            for line in path.read_text().splitlines()
        )
        + "\n"
    )
    result = invoke(directory, env, "start", "--daemon")
    assert result.returncode == 1
    assert "Config Test Failed" in result.stdout
    assert not process_control.locked(directory)
    assert process_control.request(directory) is None


def test_daemon_requires_file_logging(installation) -> None:
    directory, env = installation
    path = directory / ".env"
    path.write_text(path.read_text() + "DECIFLOW_LOG_DIR=\n")
    result = invoke(directory, env, "start", "--daemon")
    assert result.returncode == 1 and "DECIFLOW_LOG_DIR" in result.stderr
    assert not process_control.locked(directory)


def test_status_does_not_initialize(tmp_path: Path) -> None:
    directory = tmp_path / "absent"
    result = invoke(directory, dict(os.environ), "status")
    assert result.returncode == 3 and "Not Running" in result.stdout
    assert not directory.exists()


def test_daemon_stops_real_oauth2_proxy(installation, tmp_path: Path) -> None:
    import base64
    import shutil
    import socket

    from test_oauth2_proxy import prepare_proxy_binary

    directory, env = installation
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    target = binary_dir / "oauth2-proxy"
    binary = prepare_proxy_binary(Path.home() / ".cache/deciflow/test-tools", target)
    if Path(binary) != target:
        shutil.copyfile(binary, target)
        target.chmod(0o700)
    env["PATH"] = str(binary_dir) + os.pathsep + env["PATH"]
    tls = directory / "oauth2-proxy/tls"
    tls.mkdir()
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(tls / "privkey.pem"),
            "-out",
            str(tls / "fullchain.pem"),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost",
        ],
        check=True,
        capture_output=True,
    )
    (tls / "privkey.pem").chmod(0o600)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    proxy = directory / "oauth2-proxy"
    policy = proxy / "oauth2-proxy.cfg"
    policy.write_text(policy.read_text().replace("0.0.0.0:4443", f"127.0.0.1:{port}"))
    (proxy / "allowed-emails.txt").write_text("approved@example.com\n")
    path = directory / ".env"
    path.write_text(
        path.read_text().replace(
            "OAUTH2_PROXY_ENABLED=false", "OAUTH2_PROXY_ENABLED=true"
        )
        + f"OAUTH2_PROXY_PUBLIC_URL=https://localhost:{port}\n"
        "OAUTH2_PROXY_CLIENT_ID=local-test\nOAUTH2_PROXY_CLIENT_SECRET=local-test\n"
        f"OAUTH2_PROXY_COOKIE_SECRET={base64.urlsafe_b64encode(b't' * 32).decode()}\n"
    )
    result = invoke(directory, env, "start", "--daemon")
    assert result.returncode == 0, (
        result.stdout + result.stderr + (directory / "logs/daemon.log").read_text()
    )
    assert f"https://localhost:{port}" in result.stdout
    info = process_control.request(directory)
    assert info
    pid = info["pid"]
    ui_port = next(
        line.split("=", 1)[1]
        for line in path.read_text().splitlines()
        if line.startswith("PORT=")
    )
    base = f"http://127.0.0.1:{ui_port}"
    origin = f"https://localhost:{port}"
    restart = urllib.request.Request(
        base + "/api/restart",
        data=b'{"confirmation":"RESTART DECIFLOW"}',
        headers={"Origin": origin, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(restart, timeout=5) as response:
        assert response.status == 202
        previous = json.load(response)["instanceId"]
    deadline = time.monotonic() + 20
    while True:
        status = urllib.request.Request(
            base + "/api/reset/status", headers={"Origin": origin}, method="POST"
        )
        try:
            with urllib.request.urlopen(status, timeout=1) as response:
                info = process_control.request(directory)
                if (
                    json.load(response)["instanceId"] != previous
                    and info
                    and info["state"] == "Running"
                ):
                    assert info["pid"] == pid
                    break
        except OSError:
            pass
        assert time.monotonic() < deadline, (directory / "logs/daemon.log").read_text()
        time.sleep(0.1)
    result = invoke(directory, env, "stop")
    assert result.returncode == 0, result.stdout + result.stderr
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=0.2)


def test_failed_child_reports_log_path(tmp_path, monkeypatch, capsys) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(
        process_control.subprocess,
        "Popen",
        lambda *args, **kwargs: SimpleNamespace(poll=lambda: 1),
    )
    with (
        process_control.RunLock(tmp_path) as lock,
        pytest.raises(RuntimeError, match="Daemon startup failed.*daemon.log"),
    ):
        process_control.launch_daemon(tmp_path, lock)
    assert "Running" not in capsys.readouterr().out
    assert not process_control.locked(tmp_path)
