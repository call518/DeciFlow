import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("persist", [False, True])
def test_sigint_stops_open_realtime_stream(tmp_path: Path, persist: bool) -> None:
    """Stop the actual server even when a Realtime response has no end."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    log = tmp_path / "live.log"
    log.write_text("")
    output = tmp_path / "server-output.txt"
    env = {
        **os.environ,
        "PORT": str(port),
        "DECISION_ENGINE": "laya",
        "LAYA_CONCURRENCY": "4",
        "LAYA_API_URL": "http://127.0.0.1:1/v1/systemone",
    }
    with output.open("w") as capture:
        process = subprocess.Popen(
            [sys.executable, "server.py"],
            env=env,
            stdout=capture,
            stderr=capture,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base, timeout=5) as client:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        response = client.get("/api/status")
                        response.raise_for_status()
                        break
                    except httpx.ConnectError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
                endpoint = "/api/file-source"
                payload = {"paths": str(log), "mode": "realtime"}
                if persist:
                    created = client.post(
                        endpoint,
                        headers={"Origin": base},
                        json={**payload, "persist": True},
                    )
                    created.raise_for_status()
                    endpoint = f"/api/jobs/{created.json()['jobId']}/events"
                    payload = {}
                with client.stream(
                    "POST",
                    endpoint,
                    headers={"Origin": base},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    lines = response.iter_lines()
                    assert json.loads(next(lines))["type"] == "start"
                    started = time.monotonic()
                    process.send_signal(signal.SIGINT)
                    process.wait(timeout=6)
                    assert time.monotonic() - started < 5
            assert "Finished server process" in output.read_text()
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
