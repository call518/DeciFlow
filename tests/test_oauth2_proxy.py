"""Optional real-proxy smoke tests; no Google calls or production credentials."""

import base64
import http.client
import os
import shutil
import socket
import ssl
import subprocess
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local_proxy(tmp_path: Path) -> Iterator[tuple[int, list[str], threading.Event]]:
    """Run the production policy with disposable credentials and a local upstream."""
    binary = os.getenv("OAUTH2_PROXY_BINARY")
    if not binary:
        pytest.skip("Set OAUTH2_PROXY_BINARY to run real-proxy smoke tests")
    if not shutil.which("openssl"):
        pytest.skip("OpenSSL is required for a disposable TLS certificate")
    requests: list[str] = []
    first_received = threading.Event()

    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.end_headers()
            self.wfile.write(b'{"event":"first"}\n')
            self.wfile.flush()
            if not first_received.wait(timeout=2):
                requests.append("stream-buffered")
            self.wfile.write(b'{"event":"last"}\n')
            self.wfile.flush()

        def log_message(self, format: str, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    tls = tmp_path / "tls"
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
        ],
        capture_output=True,
        check=True,
    )
    (tmp_path / "allowed-emails.txt").write_text("approved-user@example.com\n")
    policy = (ROOT / "oauth2-proxy/oauth2-proxy.cfg").read_text()
    policy = policy.replace("/etc/oauth2-proxy", str(tmp_path)).replace(
        "0.0.0.0:4443", f"127.0.0.1:{port}"
    )
    # Only this disposable test route bypasses login to exercise stream forwarding.
    policy += (
        f'\nupstreams = ["http://127.0.0.1:{upstream.server_port}/"]\n'
        'skip_auth_routes = ["GET=^/test-stream$"]\n'
        'client_id = "local-test-client"\n'
        'client_secret = "local-test-secret"\n'
        f'cookie_secret = "{base64.urlsafe_b64encode(b"t" * 32).decode()}"\n'
        f'redirect_url = "https://localhost:{port}/oauth2/callback"\n'
    )
    config = tmp_path / "proxy.cfg"
    config.write_text(policy)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OAUTH2_PROXY_")
    }
    log = tmp_path / "proxy.log"
    try:
        with log.open("w") as output:
            process = subprocess.Popen(
                [binary, f"--config={config}"],
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 10
                while True:
                    if process.poll() is not None:
                        pytest.fail(f"Proxy exited during startup:\n{log.read_text()}")
                    try:
                        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                            break
                    except OSError:
                        if time.monotonic() > deadline:
                            pytest.fail(f"Proxy did not start:\n{log.read_text()}")
                        time.sleep(0.05)
                yield port, requests, first_received
            finally:
                process.terminate()
                process.wait(timeout=5)
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)


def test_real_proxy_access_and_streaming(
    local_proxy: tuple[int, list[str], threading.Event],
) -> None:
    """Reject anonymous/forged requests and forward events before stream completion."""
    port, upstream_requests, first_received = local_proxy
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE  # Disposable self-signed test certificate only.

    def connect() -> http.client.HTTPSConnection:
        return http.client.HTTPSConnection(
            "127.0.0.1", port, context=context, timeout=5
        )

    for method, path in [
        ("GET", "/api/status"),
        ("GET", "/oauth2/userinfo"),
        ("POST", "/api/tasks"),
        ("PUT", "/api/sources"),
        ("DELETE", "/api/actions"),
    ]:
        connection = connect()
        connection.request(
            method,
            path,
            headers={
                "Cookie": "__Host-deciflow_session=forged",
                "X-Forwarded-Email": "approved-user@example.com",
                "X-Auth-Request-Email": "approved-user@example.com",
                "X-Forwarded-User": "approved-user@example.com",
            },
        )
        response = connection.getresponse()
        assert response.status == 401
        assert response.getheader("Location") is None
        response.read()
        connection.close()
    assert upstream_requests == []

    connection = connect()
    connection.request("GET", "/")
    response = connection.getresponse()
    assert response.status in {302, 403}
    response.read()
    connection.close()
    assert upstream_requests == []

    connection = connect()
    connection.request("GET", "/oauth2/start")
    response = connection.getresponse()
    assert response.status == 302
    location = urlsplit(response.getheader("Location") or "")
    assert location.hostname == "accounts.google.com"
    query = parse_qs(location.query)
    assert query["client_id"] == ["local-test-client"]
    assert query["redirect_uri"] == [f"https://localhost:{port}/oauth2/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert "Secure" in (response.getheader("Set-Cookie") or "")
    response.read()
    connection.close()

    connection = connect()
    connection.request("GET", "/test-stream")
    response = connection.getresponse()
    assert response.status == 200
    assert response.readline() == b'{"event":"first"}\n'
    assert upstream_requests == ["/test-stream"]
    first_received.set()
    assert response.readline() == b'{"event":"last"}\n'
    response.read()
    connection.close()
    assert upstream_requests == ["/test-stream"]
