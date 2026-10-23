"""Run the native HTTPS entry point alongside DeciFlow."""

import os
import shutil
import signal
import subprocess
from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread, current_thread, main_thread
from urllib.parse import urlsplit

import uvicorn


def serve(
    server: uvicorn.Server,
    stop: Event | None = None,
    on_started: Callable[[], None] | None = None,
) -> None:
    """Bridge CLI readiness and cooperative shutdown to the actual server."""
    finished = Event()

    def monitor() -> None:
        notified = False
        while not finished.wait(0.05):
            if stop is not None and stop.is_set():
                server.should_exit = True
            if not notified and getattr(server, "started", False):
                if on_started is not None:
                    on_started()
                notified = True

    watcher = Thread(target=monitor, daemon=True)
    watcher.start()
    original_term = None
    if current_thread() is main_thread():
        original_term = signal.getsignal(signal.SIGTERM)

        def terminate(signum, frame) -> None:
            server.should_exit = True

        # Uvicorn re-raises handled signals; let the proxy's finally block run.
        signal.signal(signal.SIGTERM, terminate)
    try:
        try:
            server.run()
        except KeyboardInterrupt:
            pass
    finally:
        if original_term is not None:
            signal.signal(signal.SIGTERM, original_term)
        finished.set()
        watcher.join()


def proxy_enabled() -> bool:
    """Reject misspelled modes instead of silently disabling authentication."""
    value = os.getenv("OAUTH2_PROXY_ENABLED", "false")
    if value not in {"true", "false"}:
        raise ValueError("OAUTH2_PROXY_ENABLED must be true or false")
    return value == "true"


def proxy_origin() -> str:
    """Validate the public HTTPS origin shared by startup and cli_config."""
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
        raise ValueError(
            "OAUTH2_PROXY_PUBLIC_URL must be an HTTPS origin without a path"
        )
    _ = url.port
    return origin


def run_with_proxy(
    config: uvicorn.Config,
    root: Path,
    *,
    stop: Event | None = None,
    on_started: Callable[[], None] | None = None,
) -> None:
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
    origin = proxy_origin()
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
            serve(server, stop, on_started)
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
        raise RuntimeError(
            "OAuth2-Proxy exited; DeciFlow stopped. Check OAuth2-Proxy logs."
        )
