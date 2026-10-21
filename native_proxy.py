"""Run the native HTTPS entry point alongside DeciFlow."""

import os
import shutil
import subprocess
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlsplit

import uvicorn


def proxy_enabled() -> bool:
    """Reject misspelled modes instead of silently disabling authentication."""
    value = os.getenv("OAUTH2_PROXY_ENABLED", "false")
    if value not in {"true", "false"}:
        raise ValueError("OAUTH2_PROXY_ENABLED must be true or false")
    return value == "true"


def run_with_proxy(config: uvicorn.Config, root: Path) -> None:
    """Supervise native OAuth2-Proxy and stop both processes when either exits."""
    binary = shutil.which("oauth2-proxy")
    if not binary:
        raise ValueError("Install oauth2-proxy on PATH; see docs/native.md")
    for key in (
        "OAUTH2_PROXY_CLIENT_ID",
        "OAUTH2_PROXY_CLIENT_SECRET",
        "OAUTH2_PROXY_COOKIE_SECRET",
    ):
        if not os.getenv(key):
            raise ValueError(f"Set {key} in .env; see docs/native.md")
    origin = os.getenv("OAUTH2_PROXY_PUBLIC_URL", "")
    url = urlsplit(origin)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username is not None
        or url.password is not None
        or url.path
        or url.query
        or url.fragment
    ):
        raise ValueError("OAUTH2_PROXY_PUBLIC_URL must be an HTTPS origin without a path")
    directory = root / "oauth2-proxy"
    for relative in (
        "oauth2-proxy.cfg",
        "allowed-emails.txt",
        "tls/fullchain.pem",
        "tls/privkey.pem",
    ):
        path = directory / relative
        with path.open("rb"):
            pass
    os.environ["DECIFLOW_CSRF_TRUSTED_ORIGINS"] = origin
    command = [
        binary,
        f"--config={directory / 'oauth2-proxy.cfg'}",
        f"--upstream=http://127.0.0.1:{config.port}/",
        f"--redirect-url={origin}/oauth2/callback",
        f"--authenticated-emails-file={directory / 'allowed-emails.txt'}",
        f"--tls-cert-file={directory / 'tls/fullchain.pem'}",
        f"--tls-key-file={directory / 'tls/privkey.pem'}",
    ]
    server = uvicorn.Server(config)
    stopping = Event()
    failed = Event()
    with subprocess.Popen(command, start_new_session=True) as proxy:

        def monitor() -> None:
            proxy.wait()
            if not stopping.is_set():
                failed.set()
                server.should_exit = True

        watcher = Thread(target=monitor, daemon=True)
        watcher.start()
        print(f"DeciFlow: {origin} (Google sign-in enabled)", flush=True)
        try:
            server.run()
        finally:
            stopping.set()
            if proxy.poll() is None:
                proxy.terminate()
                try:
                    proxy.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy.kill()
                    proxy.wait()
            watcher.join()
    if failed.is_set():
        raise RuntimeError("OAuth2-Proxy exited; DeciFlow stopped. Check OAuth2-Proxy logs.")
