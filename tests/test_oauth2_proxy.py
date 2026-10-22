"""Real-proxy smoke tests with verified downloads and disposable credentials."""

import base64
import hashlib
import http.client
import io
import os
import platform
import shutil
import socket
import ssl
import subprocess
import tarfile
import tempfile
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROXY_VERSION = "7.15.5"
# SHA-256 digests published on the official v7.15.5 GitHub release.
PROXY_SHA256 = {
    "linux-amd64": "f63f94bf72c5f46ab002a0a275aa8b3cf19b4d828aed08a13978cb9a62c3a1fd",
    "linux-arm64": "ebef73d06a05f76a03b0b2f95aa8424c10201228bd64621a2a7d375ce44dd637",
    "darwin-amd64": "ad0a6bec165f6c88749ab94833a14c7be0e8ebcad07987eb080de78892d732bb",
    "darwin-arm64": "b8c9c86e5ad35808753c724e2a64af59ae066f31664973fd68f85bd0a7911ee3",
}


def prepare_proxy_binary(cache: Path, target: Path) -> str:
    """Verify a cached release archive and copy only its binary to test storage."""
    supplied = os.getenv("OAUTH2_PROXY_BINARY")
    if supplied:
        binary = shutil.which(supplied)
        if not binary:
            raise ValueError("OAUTH2_PROXY_BINARY must name an executable file")
        return binary
    system = platform.system().lower()
    machine = platform.machine().lower()
    architecture = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    release = f"{system}-{architecture}"
    if release not in PROXY_SHA256:
        raise ValueError(
            "Automatic OAuth2-Proxy download supports Linux/macOS amd64/arm64; "
            "set OAUTH2_PROXY_BINARY for this platform"
        )
    stem = f"oauth2-proxy-v{PROXY_VERSION}.{release}"
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = cache / f"{stem}.tar.gz"

    def verified(path: Path) -> bool:
        with path.open("rb") as file:
            return (
                hashlib.file_digest(file, "sha256").hexdigest() == PROXY_SHA256[release]
            )

    if not archive.is_file() or not verified(archive):
        url = (
            "https://github.com/oauth2-proxy/oauth2-proxy/releases/download/"
            f"v{PROXY_VERSION}/{archive.name}"
        )
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            download = Path(directory) / archive.name
            with urlopen(url, timeout=60) as response, download.open("wb") as file:
                shutil.copyfileobj(response, file)
            if not verified(download):
                raise ValueError("OAuth2-Proxy download failed SHA-256 verification")
            download.replace(archive)
    with tarfile.open(archive, "r:gz") as bundle:
        member = bundle.getmember(f"{stem}/oauth2-proxy")
        if not member.isfile():
            raise ValueError("OAuth2-Proxy archive does not contain a regular binary")
        source = bundle.extractfile(member)
        assert source is not None
        with source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
    target.chmod(0o700)
    return str(target)


@pytest.fixture(scope="session")
def oauth2_proxy_binary(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Download once per release; never place downloaded binaries in the repository."""
    cache = Path.home() / ".cache" / "deciflow" / "test-tools"
    target = tmp_path_factory.mktemp("oauth2-proxy") / "oauth2-proxy"
    return prepare_proxy_binary(cache, target)


@pytest.fixture
def local_proxy(
    tmp_path: Path, oauth2_proxy_binary: str
) -> Iterator[tuple[int, list[str], threading.Event]]:
    """Run the production policy with disposable credentials and a local upstream."""
    if not shutil.which("openssl"):
        pytest.fail("Install OpenSSL to create the disposable test TLS certificate")
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
                [oauth2_proxy_binary, f"--config={config}"],
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


@pytest.fixture
def proxy_archive(monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, list[str]]:
    """Serve a tiny disposable release archive without network access."""
    monkeypatch.delenv("OAUTH2_PROXY_BINARY", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    payload = io.BytesIO()
    binary = b"disposable-test-binary"
    with tarfile.open(fileobj=payload, mode="w:gz") as bundle:
        member = tarfile.TarInfo(
            f"oauth2-proxy-v{PROXY_VERSION}.linux-amd64/oauth2-proxy"
        )
        member.size = len(binary)
        bundle.addfile(member, io.BytesIO(binary))
    archive = payload.getvalue()
    monkeypatch.setitem(
        PROXY_SHA256, "linux-amd64", hashlib.sha256(archive).hexdigest()
    )
    requests: list[str] = []

    def download(url: str, timeout: int) -> io.BytesIO:
        assert url == (
            "https://github.com/oauth2-proxy/oauth2-proxy/releases/download/"
            f"v{PROXY_VERSION}/oauth2-proxy-v{PROXY_VERSION}.linux-amd64.tar.gz"
        )
        requests.append(url)
        return io.BytesIO(archive)

    monkeypatch.setattr(f"{__name__}.urlopen", download)
    return archive, requests


def test_proxy_download_reuses_verified_cache_and_repairs_corruption(
    tmp_path: Path, proxy_archive: tuple[bytes, list[str]]
) -> None:
    archive, requests = proxy_archive
    cache = tmp_path / "cache"
    target = tmp_path / "oauth2-proxy"
    prepare_proxy_binary(cache, target)
    assert target.read_bytes() == b"disposable-test-binary"
    assert os.access(target, os.X_OK)
    assert len(requests) == 1
    target.unlink()
    prepare_proxy_binary(cache, target)
    assert target.read_bytes() == b"disposable-test-binary"
    assert len(requests) == 1
    stored = next(cache.glob("*.tar.gz"))
    stored.write_bytes(b"corrupt cache")
    prepare_proxy_binary(cache, target)
    assert len(requests) == 2
    assert stored.read_bytes() == archive


def test_proxy_download_rejects_checksum_mismatch(
    tmp_path: Path,
    proxy_archive: tuple[bytes, list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(PROXY_SHA256, "linux-amd64", "0" * 64)
    target = tmp_path / "oauth2-proxy"
    with pytest.raises(ValueError, match="SHA-256 verification"):
        prepare_proxy_binary(tmp_path / "cache", target)
    assert not target.exists()
    assert not list((tmp_path / "cache").glob("*.tar.gz"))


def test_explicit_proxy_binary_does_not_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "provided-proxy"
    binary.write_text("test-only")
    binary.chmod(0o700)
    monkeypatch.setenv("OAUTH2_PROXY_BINARY", str(binary))
    assert prepare_proxy_binary(tmp_path / "unused-cache", tmp_path / "unused") == str(
        binary
    )
    assert not (tmp_path / "unused-cache").exists()
