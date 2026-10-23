"""Manage one CLI process per configuration directory using local IPC."""

import hashlib
import json
import os
import socket
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from threading import Event, Thread
from typing import Any, Self
from urllib.parse import urlsplit

LOCK_ENV = "_DECIFLOW_RUN_FD"
DAEMON_ENV = "_DECIFLOW_DAEMON"
START_TIMEOUT = 60
STOP_TIMEOUT = 30


def socket_path(directory: Path) -> Path:
    """Keep Unix socket names short even for long configuration paths."""
    identity = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"deciflow-{os.getuid()}" / f"{identity}.sock"


class RunLock:
    """Hold an exclusive lock across daemon launch and UI exec-based restarts."""

    def __init__(self, directory: Path) -> None:
        self.path = directory / ".run.lock"
        self.fd = -1

    def __enter__(self) -> Self:
        if os.name != "posix":
            raise ValueError("CLI process management requires Linux, WSL2, or macOS")
        import fcntl

        inherited = os.environ.pop(LOCK_ENV, None)
        if inherited:
            self.fd = int(inherited)
        else:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(self.fd)
            if inherited:
                actual = self.path.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) != (actual.st_dev, actual.st_ino):
                    raise ValueError("Invalid inherited DeciFlow process lock")
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("The process lock must be owned by the current user")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError(
                    "DeciFlow is already running for this configuration. "
                    "Use deciflow status or deciflow stop with the same --config-dir."
                ) from None
            os.set_inheritable(self.fd, True)
            os.environ[LOCK_ENV] = str(self.fd)
            return self
        except BaseException:
            os.close(self.fd)
            self.fd = -1
            raise

    def __exit__(self, *args: object) -> None:
        os.environ.pop(LOCK_ENV, None)
        if self.fd >= 0:
            # Closing, rather than unlocking, preserves the daemon child's lock.
            os.close(self.fd)


def locked(directory: Path) -> bool:
    """Inspect an existing lock without creating files or trusting a PID file."""
    import fcntl

    try:
        fd = os.open(directory / ".run.lock", os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        return False
    finally:
        os.close(fd)


def request(directory: Path, command: str = "status") -> dict[str, Any] | None:
    """Contact only the socket associated with this configuration and user."""
    if os.name != "posix":
        raise ValueError("CLI process management requires Linux, WSL2, or macOS")
    try:
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(1)
            client.connect(str(socket_path(directory)))
            client.sendall(command.encode() + b"\n")
            output = client.makefile("rb").readline(8192)
            return json.loads(output) if output else None
    except (
        TimeoutError,
        FileNotFoundError,
        ConnectionRefusedError,
        ConnectionResetError,
        BrokenPipeError,
    ):
        return None


class Runtime:
    """Answer status/stop requests without exposing a network management port."""

    def __init__(self, directory: Path, daemon: bool) -> None:
        self.directory = directory
        self.daemon = daemon
        self.stop = Event()
        self.ready = Event()
        self.closed = Event()
        self.path = socket_path(directory)
        self.listener = socket.socket(socket.AF_UNIX)
        self.thread = Thread(target=self._serve, daemon=True)
        self.proxy_address = None
        self.proxy_ready = False
        if os.getenv("OAUTH2_PROXY_ENABLED") == "true":
            policy = tomllib.loads(
                (directory / "oauth2-proxy/oauth2-proxy.cfg").read_text()
            )
            address = urlsplit("//" + policy["https_address"])
            self.proxy_address = (
                self._local_host(address.hostname),
                int(address.port or 4443),
            )
            self.url = os.environ["OAUTH2_PROXY_PUBLIC_URL"]
        else:
            host = os.getenv("DECIFLOW_BIND_HOST", "127.0.0.1")
            host = f"[{host}]" if ":" in host else host
            self.url = f"http://{host}:{os.getenv('PORT') or '4000'}"
        logs = os.getenv("DECIFLOW_LOG_DIR", "/var/log/deciflow").strip()
        self.log = str(Path(logs).resolve() / "daemon.log") if daemon else logs

    @staticmethod
    def _local_host(host: str | None) -> str:
        return {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(
            host or "", host or "127.0.0.1"
        )

    def info(self) -> dict[str, Any]:
        ready = self.ready.is_set()
        if ready and self.proxy_address and not self.proxy_ready:
            try:
                with socket.create_connection(self.proxy_address, timeout=0.2):
                    self.proxy_ready = True
            except OSError:
                ready = False
        return {
            "state": "Stopping"
            if self.stop.is_set()
            else "Running"
            if ready
            else "Starting",
            "pid": os.getpid(),
            "url": self.url,
            "log": self.log,
            "daemon": self.daemon,
            "configuration": str(self.directory / ".env"),
        }

    def _serve(self) -> None:
        while not self.closed.is_set():
            try:
                client, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            with client:
                client.settimeout(1)
                try:
                    command = client.recv(64).strip()
                    if command == b"stop":
                        self.stop.set()
                    if command in {b"status", b"stop"}:
                        client.sendall(json.dumps(self.info()).encode() + b"\n")
                except OSError:
                    pass

    def __enter__(self) -> Self:
        parent = self.path.parent
        parent.mkdir(mode=0o700, exist_ok=True)
        info = parent.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise ValueError(f"A private runtime directory is required: {parent}")
        self.path.unlink(missing_ok=True)
        self.listener.bind(str(self.path))
        self.path.chmod(0o600)
        self.listener.settimeout(0.2)
        self.listener.listen(4)
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.closed.set()
        self.listener.close()
        self.thread.join(timeout=2)
        self.path.unlink(missing_ok=True)


def print_status(info: dict[str, Any]) -> None:
    """Show the process identity and the paths useful to its operator."""
    print(f"DeciFlow: {info['state']} (PID {info['pid']})")
    print(f"URL: {info['url']}\nConfiguration: {info['configuration']}")
    print(f"Logs: {info['log'] or 'console only'}")


def status(directory: Path) -> int:
    """Return 3 when stopped, following common service-status conventions."""
    info = request(directory)
    if info:
        print_status(info)
        return 0
    if locked(directory):
        print("DeciFlow: Starting or Restarting")
        return 0
    print("DeciFlow: Not Running")
    return 3


def stop(directory: Path) -> None:
    """Request graceful shutdown, never signal a possibly reused PID."""
    deadline = time.monotonic() + STOP_TIMEOUT
    requested = False
    while locked(directory):
        requested = request(directory, "stop") is not None or requested
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "DeciFlow did not stop within 30 seconds. Check its logs."
            )
        time.sleep(0.1)
    print("DeciFlow stopped." if requested else "DeciFlow: Not Running")


def launch_daemon(directory: Path, lock: RunLock) -> None:
    """Detach the child and return only after its UI and optional proxy are ready."""
    logs = os.getenv("DECIFLOW_LOG_DIR", "/var/log/deciflow").strip()
    if not logs:
        raise ValueError("Set DECIFLOW_LOG_DIR to a writable directory for --daemon")
    log = Path(logs).resolve() / "daemon.log"
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "deciflow.cli",
                "run",
                "--config-dir",
                str(directory),
            ],
            cwd=directory,
            env={**os.environ, DAEMON_ENV: "1"},
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            pass_fds=(lock.fd,),
        )
    try:
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"Daemon startup failed. See {log}")
            info = request(directory)
            if info and info["pid"] == process.pid and info["state"] == "Running":
                print_status(info)
                return
            time.sleep(0.1)
        raise RuntimeError(f"Daemon startup timed out. See {log}")
    except BaseException:
        if process.poll() is None:
            request(directory, "stop")
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        raise
