"""Check mode validation and native child-process supervision without Google."""

import sys
import time
from pathlib import Path

import pytest
import uvicorn

from deciflow import native_proxy


@pytest.mark.parametrize("value", ["true", "false", "TRUE", "", "flase"])
def test_mode_is_explicit(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("OAUTH2_PROXY_ENABLED", value)
    if value in {"true", "false"}:
        assert native_proxy.proxy_enabled() == (value == "true")
    else:
        with pytest.raises(ValueError, match="true or false"):
            native_proxy.proxy_enabled()


@pytest.fixture
def native_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "oauth2-proxy"
    (directory / "tls").mkdir(parents=True)
    for relative in (
        "oauth2-proxy.cfg",
        "allowed-emails.txt",
        "tls/fullchain.pem",
        "tls/privkey.pem",
    ):
        (directory / relative).write_text("test-only")
    for key in ("CLIENT_ID", "CLIENT_SECRET", "COOKIE_SECRET"):
        monkeypatch.setenv(f"OAUTH2_PROXY_{key}", "test-only")
    monkeypatch.setenv("OAUTH2_PROXY_PUBLIC_URL", "https://deciflow.example.com:4443")
    monkeypatch.setenv("DECIFLOW_CSRF_TRUSTED_ORIGINS", "")
    return tmp_path


@pytest.mark.parametrize("crash", [False, True])
def test_native_proxy_cleanup(
    native_setup: Path, monkeypatch: pytest.MonkeyPatch, crash: bool
) -> None:
    """A proxy exit stops the UI; normal UI exit terminates its child."""
    binary = native_setup / "fake-op"
    binary.write_text(
        f"#!{sys.executable}\nimport time\ntime.sleep({0 if crash else 60})\n"
    )
    binary.chmod(0o700)
    monkeypatch.setattr(native_proxy.shutil, "which", lambda name: str(binary))
    children = []
    real_popen = native_proxy.subprocess.Popen

    def spawn(command, **kwargs):
        assert "--upstream=http://127.0.0.1:4567/" in command
        assert not any("test-only" in arg for arg in command)
        child = real_popen(command, **kwargs)
        children.append(child)
        return child

    class Server:
        should_exit = False

        def __init__(self, config):
            pass

        def run(self):
            if crash:
                deadline = time.monotonic() + 5
                while not self.should_exit and time.monotonic() < deadline:
                    time.sleep(0.01)
                assert self.should_exit

    monkeypatch.setattr(native_proxy.subprocess, "Popen", spawn)
    monkeypatch.setattr(native_proxy.uvicorn, "Server", Server)
    config = uvicorn.Config("unused:app", port=4567)
    if crash:
        with pytest.raises(RuntimeError, match="OAuth2-Proxy exited"):
            native_proxy.run_with_proxy(config, native_setup)
    else:
        native_proxy.run_with_proxy(config, native_setup)
    assert children[0].poll() is not None
    assert native_proxy.os.environ["DECIFLOW_CSRF_TRUSTED_ORIGINS"] == (
        "https://deciflow.example.com:4443"
    )


def test_missing_native_credentials_fail_closed(
    native_setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_proxy.shutil, "which", lambda name: "/unused")
    monkeypatch.delenv("OAUTH2_PROXY_CLIENT_SECRET")
    with pytest.raises(ValueError, match="OAUTH2_PROXY_CLIENT_SECRET"):
        native_proxy.run_with_proxy(uvicorn.Config("unused:app"), native_setup)


@pytest.mark.parametrize("enabled", [False, True])
def test_native_entrypoint_selects_access_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool
) -> None:
    """Use one native command; protected mode ignores an external UI bind."""
    from deciflow import server
    monkeypatch.setattr(server, "load_startup_settings", lambda path: None)
    monkeypatch.setattr(server, "get_engine", lambda: None)
    monkeypatch.setattr(server, "get_log_config", lambda: None)
    monkeypatch.setenv("OAUTH2_PROXY_ENABLED", "true" if enabled else "false")
    monkeypatch.setenv("DECIFLOW_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "4567")
    calls = []

    def proxy(config, root, **kwargs):
        calls.append((config.host, config.port, "protected"))
        server.app.state.reset_requested = False
        server.app.state.restart_requested = True

    def direct(app, **kwargs):
        calls.append((kwargs["host"], kwargs["port"], "http"))

    monkeypatch.setattr(native_proxy, "run_with_proxy", proxy)
    monkeypatch.setattr(server.uvicorn, "run", direct)
    monkeypatch.setattr(server, "restart_process", lambda: calls.append("restart"))
    monkeypatch.setattr(server.app.state, "managed_native_proxy", False, raising=False)
    monkeypatch.setattr(server.app.state, "restart_requested", False, raising=False)
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    server.main(manage_proxy=True)
    if enabled:
        assert calls == [("127.0.0.1", 4567, "protected"), "restart"]
    else:
        assert calls == [("0.0.0.0", 4567, "http")]


def test_unset_mode_defaults_to_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OAUTH2_PROXY_ENABLED", raising=False)
    assert not native_proxy.proxy_enabled()


def test_missing_certificate_fails_before_starting_ui(
    native_setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native_proxy.shutil, "which", lambda name: "/unused")
    (native_setup / "oauth2-proxy/tls/privkey.pem").unlink()
    with pytest.raises(FileNotFoundError):
        native_proxy.run_with_proxy(uvicorn.Config("unused:app"), native_setup)
