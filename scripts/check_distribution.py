"""Install a wheel as a uv tool and smoke-test it outside the source checkout."""

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class HealthEndpoint(BaseHTTPRequestHandler):
    """Serve only the non-inference Laya health response used by cli_config."""

    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/health" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format: str, *args: object) -> None:
        pass


def main() -> None:
    """Verify packaged resources, isolated installation, startup, and shutdown."""
    wheel = Path(sys.argv[1]).resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for resource in (
            "deciflow/cli.py",
            "deciflow/cli_config.py",
            "deciflow/public/index.html",
            "deciflow/public/app.js",
            "deciflow/public/vendor/prism/prism-python-1.30.0.min.js",
            "deciflow/images/DeciFlow-Logo.png",
            "deciflow/profiles/general.json",
            "deciflow/.env.example",
            "deciflow/docs/criteria.md",
            "deciflow/oauth2-proxy/oauth2-proxy.cfg",
        ):
            assert resource in names, resource
        assert not any(
            Path(name).name
            in {".env", "privkey.pem", "fullchain.pem", "allowed-emails.txt"}
            or any(
                part in {".git", ".aws", ".codex", ".agents"}
                for part in Path(name).parts
            )
            for name in names
        ), "Private configuration must not enter the wheel"
    with (
        tempfile.TemporaryDirectory(prefix="deciflow-distribution-") as temporary,
        ExitStack() as cleanup,
    ):
        root = Path(temporary)
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(
                ("DECIFLOW_", "LAYA_", "JEV_", "OAUTH2_PROXY_", "OPENAI_")
            )
            and key not in {"DECISION_ENGINE", "PORT", "PYTHONPATH", "VIRTUAL_ENV"}
        }
        env.update(UV_TOOL_DIR=str(root / "tools"), UV_TOOL_BIN_DIR=str(root / "bin"))
        subprocess.run(
            ["uv", "tool", "install", "--python", sys.executable, str(wheel)],
            cwd=root,
            env=env,
            check=True,
        )
        executable = root / "bin" / "deciflow"
        workspace = root / "workspace"
        command = [str(executable), "start", "--config-dir", workspace.name]
        subprocess.run([str(executable), "--help"], cwd=root, env=env, check=True)
        uninitialized = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        assert uninitialized.returncode == 1 and not workspace.exists()
        assert "deciflow init" in uninitialized.stderr
        subprocess.run(
            [str(executable), "init", "--config-dir", workspace.name],
            cwd=root,
            env=env,
            check=True,
        )
        assert (workspace / ".env").is_file()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        (workspace / ".env").write_text(
            "DECISION_ENGINE=laya\nLAYA_API_URL=http://127.0.0.1:1/v1/systemone\n"
            "LAYA_API_KEY=\nOAUTH2_PROXY_ENABLED=false\nDECIFLOW_BIND_HOST=127.0.0.1\n"
            f"PORT={port}\nDECIFLOW_DATA_DIR={workspace / 'data'}\n"
            f"DECIFLOW_LOG_DIR={workspace / 'logs'}\n"
        )
        (workspace / "data").mkdir()
        (workspace / "logs").mkdir()
        engine = cleanup.enter_context(
            ThreadingHTTPServer(("127.0.0.1", 0), HealthEndpoint)
        )
        thread = Thread(target=engine.serve_forever, daemon=True)
        thread.start()
        config = workspace / ".env"
        config.write_text(
            config.read_text().replace(
                "http://127.0.0.1:1/v1/systemone",
                f"http://127.0.0.1:{engine.server_port}/v1/systemone",
            )
        )
        cleanup.callback(thread.join)
        cleanup.callback(engine.shutdown)
        subprocess.run(
            [str(executable), "config", "test", "--config-dir", workspace.name],
            cwd=root,
            env=env,
            check=True,
        )
        assert not (workspace / "data" / "deciflow.sqlite3").exists()
        saved = config.read_bytes()
        config.write_text(
            config.read_text().replace(
                f"http://127.0.0.1:{engine.server_port}/v1/systemone",
                "http://127.0.0.1:1/v1/systemone",
            )
        )
        unavailable = subprocess.run(
            [str(executable), "config", "test", "--config-dir", workspace.name],
            check=False,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        assert unavailable.returncode == 1
        assert "[Failed] Laya Connection" in unavailable.stdout
        assert "Config Test Failed" in unavailable.stdout
        blocked = subprocess.run(
            command,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        assert blocked.returncode == 1 and "Config Test Failed" in blocked.stdout
        assert "deciflow config test" in blocked.stderr
        assert not (workspace / "data" / "deciflow.sqlite3").exists()
        config.write_bytes(saved)
        subprocess.run(
            [str(executable), "config", "list", "--config-dir", workspace.name],
            cwd=root,
            env=env,
            check=True,
        )
        log = root / "startup.log"
        with log.open("w") as output:
            process = subprocess.Popen(
                command, cwd=root, env=env, stdout=output, stderr=output
            )
        try:
            base = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90
            while True:
                if process.poll() is not None:
                    raise AssertionError(f"Installed server exited:\n{log.read_text()}")
                try:
                    with urllib.request.urlopen(
                        base + "/api/status", timeout=2
                    ) as response:
                        assert json.load(response)["authenticationEnabled"] is False
                    break
                except (OSError, urllib.error.URLError):
                    if time.monotonic() >= deadline:
                        raise AssertionError(
                            f"Installed server startup timed out:\n{log.read_text()}"
                        )
                    time.sleep(0.1)
            for path in ("/", "/app.js", "/style.css", "/logo.png", "/favicon.ico"):
                with urllib.request.urlopen(base + path, timeout=5) as response:
                    assert response.status == 200 and response.read(), path
            request = urllib.request.Request(
                base + "/api/configuration", headers={"Origin": base}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
            restart = urllib.request.Request(
                base + "/api/restart",
                data=json.dumps({"confirmation": "RESTART DECIFLOW"}).encode(),
                headers={"Origin": base, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(restart, timeout=5) as response:
                assert response.status == 202
                previous_instance = json.load(response)["instanceId"]
            deadline = time.monotonic() + 30
            while True:
                if process.poll() is not None:
                    raise AssertionError(
                        f"Installed restart failed:\n{log.read_text()}"
                    )
                status = urllib.request.Request(
                    base + "/api/reset/status", headers={"Origin": base}, method="POST"
                )
                try:
                    with urllib.request.urlopen(status, timeout=2) as response:
                        if json.load(response)["instanceId"] != previous_instance:
                            break
                except (OSError, urllib.error.URLError):
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError(
                        f"Installed restart timed out:\n{log.read_text()}"
                    )
                time.sleep(0.1)
        finally:
            process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                raise AssertionError(
                    "Installed server did not stop after SIGINT"
                ) from None
        assert process.returncode == 0, log.read_text()
        managed = [str(executable), "status", "--config-dir", workspace.name]
        shutdown = [str(executable), "stop", "--config-dir", workspace.name]
        try:
            subprocess.run(
                command + ["--daemon"], cwd=root, env=env, check=True, timeout=90
            )
            subprocess.run(managed, cwd=root, env=env, check=True)
            duplicate = subprocess.run(
                command, cwd=root, env=env, capture_output=True, text=True, check=False
            )
            assert duplicate.returncode == 1 and "already running" in duplicate.stderr
        finally:
            subprocess.run(shutdown, cwd=root, env=env, check=True, timeout=40)
        stopped = subprocess.run(
            managed, cwd=root, env=env, capture_output=True, check=False
        )
        assert stopped.returncode == 3
        print("Installed wheel smoke test passed outside the source checkout.")


if __name__ == "__main__":
    main()
