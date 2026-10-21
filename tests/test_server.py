import json
import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

import server
from classifier import Result
from config import Engine


@pytest.mark.anyio
async def test_laya_status_without_jev_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.delenv("JEV_API_KEY")
    monkeypatch.setenv("JEV_MAX_INPUT_BYTES", "unused")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        status = (await client.get("/api/status")).json()
    assert status["engine"] == "laya"
    assert status["configured"] is True
    assert status["model"] == "multilingual"
    assert status["limits"] == {"context_tokens": 8192, "head_tokens": 256}


@pytest.mark.anyio
async def test_assets_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        for path in [
            "/",
            "/app.js",
            "/stream.js",
            "/vendor/prism/prism-python-1.30.0.min.js",
            "/style.css",
            "/logo.png",
            "/images/GitHub-Logo.png",
            "/favicon.ico",
            "/icons/deciflow-icon-16.png",
            "/icons/deciflow-icon-32.png",
        ]:
            response = await client.get(path)
            assert response.status_code == 200
            expected_cache = (
                "public, max-age=31536000, immutable"
                if path.startswith("/vendor/prism/")
                else "no-store"
            )
            assert response.headers["cache-control"] == expected_cache
            assert response.headers["x-content-type-options"] == "nosniff"
            if path == "/":
                assert '<html lang="en">' in response.text
                assert 'AI-Assisted Decisions' in response.text
                assert 'Fast decisions. Faster flow.' in response.text
                assert 'src="/logo.png" alt="DeciFlow"' in response.text
                assert (
                    'href="https://github.com/call518/DeciFlow" target="_blank" '
                    'rel="noopener noreferrer"' in response.text
                )
                assert 'href="/favicon.ico?v=deciflow-1"' in response.text
                assert (
                    'sizes="32x32" href="/icons/deciflow-icon-32.png?v=deciflow-1"'
                    in response.text
                )
            if path == "/logo.png":
                assert response.headers["content-type"] == "image/png"
                assert (
                    response.content
                    == (server.ROOT / "images" / "DeciFlow-Logo.png").read_bytes()
                )
            if path == "/images/GitHub-Logo.png":
                assert response.headers["content-type"] == "image/png"
                assert response.content == (
                    server.ROOT / "images" / "GitHub-Logo.png"
                ).read_bytes()
            if path == "/favicon.ico" or path.startswith("/icons/"):
                name, media_type = server.ASSETS[path]
                assert response.headers["content-type"] == media_type
                assert response.content == (server.ROOT / "public" / name).read_bytes()
        response = await client.get("/icons/deciflow-icon-32.png?v=deciflow-1")
        assert response.status_code == 200
        assert (
            response.content
            == (server.ROOT / "images/icons/deciflow-icon-32.png").read_bytes()
        )
        status = (await client.get("/api/status")).json()
        assert status["configured"] is False
        assert status["limits"]["context_tokens"] == 32000
        assert status["model"] == "jev-1.13.0"
        assert (await client.get("/missing")).status_code == 404


@pytest.mark.anyio
async def test_upload_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/classify", json={})).status_code == 403
        headers = {"Origin": "http://test"}
        response = await client.post(
            "/api/classify", headers=headers, json={"text": ("a" * 100 + "\n") * 10000}
        )
        assert response.status_code == 503
        assert "JEV_API_KEY" in response.json()["error"]
        for body in [{}, [], {"text": ""}]:
            assert (
                await client.post("/api/classify", headers=headers, json=body)
            ).status_code == 400
        assert (
            await client.post("/api/classify", headers=headers, content="{")
        ).status_code == 400


@pytest.mark.anyio
async def test_upload_above_old_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        for text in ["x\n" * 10001, "x" * 50_000_001]:
            response = await client.post(
                "/api/classify",
                headers={"Origin": "http://test"},
                json={"text": text},
            )
            assert response.status_code == 503
            assert "JEV_API_KEY" in response.json()["error"]


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
async def test_stream_contract_and_partial_failure(
    monkeypatch: pytest.MonkeyPatch,
    engine_name: str,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    monkeypatch.setenv("LAYA_API_KEY", "test-key")

    async def handle_classify(
        log: str, engine: Engine, client: httpx.AsyncClient
    ) -> Result:
        assert engine.api_key == "test-key"
        if log == "bad":
            raise ValueError("Jev request failed (HTTP 429)")
        return {"category": "normal", "confidence": 1, "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/classify",
            headers={"Origin": "http://test"},
            json={"text": "\uc815\uc0c1 \ub85c\uadf8\nbad"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0] == {"type": "start", "total": 2, "engine": engine_name}
    assert events[-1]["type"] == "done"
    results = {event["index"]: event["result"] for event in events[1:-1]}
    assert results[0]["log"] == "\uc815\uc0c1 \ub85c\uadf8"
    assert results[1]["review"] is False
    assert "429" in results[1]["error"]
    assert [event["completed"] for event in events[1:-1]] == [1, 2]


@pytest.mark.anyio
async def test_status_identifies_log_source_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server,
        "_host_info",
        lambda: {"hostname": "log-node", "addresses": ["192.168.35.10"]},
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.get("/api/status")
    assert response.json()["host"] == {
        "hostname": "log-node",
        "addresses": ["192.168.35.10"],
    }


def test_host_info_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> None:
        raise OSError("network unavailable")

    monkeypatch.setattr(server.socket, "gethostname", lambda: "offline-node")
    monkeypatch.setattr(server.socket, "getaddrinfo", fail)
    monkeypatch.setattr(server.socket, "socket", fail)
    info = server._host_info()
    assert info["hostname"] == "offline-node"
    assert info["addresses"] == []
    assert isinstance(info["os"], str) and info["os"]


def test_host_os_uses_linux_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(server.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        server.platform,
        "freedesktop_os_release",
        lambda: {"PRETTY_NAME": "Rocky Linux 8.10 (Green Obsidian)"},
    )
    assert server._host_info()["os"] == "Rocky Linux 8.10 (Green Obsidian)"


def test_host_os_falls_back_without_release_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> dict[str, str]:
        raise OSError("missing os-release")

    monkeypatch.setattr(server.platform, "system", lambda: "Linux")
    monkeypatch.setattr(server.platform, "release", lambda: "6.6.0")
    monkeypatch.setattr(server.platform, "freedesktop_os_release", fail)
    assert server._host_info()["os"] == "Linux 6.6.0"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "origin,allowed,status",
    [
        ("https://demo.ngrok-free.app", "", 403),
        ("https://demo.ngrok-free.app", "https://*.ngrok-free.app", 400),
        ("https://another.ngrok-free.app", "https://*.ngrok-free.app", 400),
        ("http://demo.ngrok-free.app", "https://*.ngrok-free.app", 403),
        ("https://ngrok-free.app", "https://*.ngrok-free.app", 403),
        ("https://badngrok-free.app", "https://*.ngrok-free.app", 403),
        ("https://demo.ngrok-free.app.evil.example", "https://*.ngrok-free.app", 403),
        ("https://demo.ngrok-free.app:9999", "https://*.ngrok-free.app", 403),
        ("https://evil@demo.ngrok-free.app", "https://*.ngrok-free.app", 403),
        ("https://demo.ngrok-free.app/path", "https://*.ngrok-free.app", 403),
        ("https://demo.ngrok-free.app", "https://demo.ngrok-free.app", 400),
        ("https://evil.example", "https://demo.ngrok-free.app", 403),
        (
            "https://demo.ngrok-free.app.evil.example",
            "https://demo.ngrok-free.app",
            403,
        ),
    ],
)
async def test_remote_file_origin_allowlist(
    monkeypatch: pytest.MonkeyPatch, origin: str, allowed: str, status: int
) -> None:
    monkeypatch.setenv("DECIFLOW_CSRF_TRUSTED_ORIGINS", allowed)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/api/file-source", headers={"Origin": origin}, json={}
        )
    assert response.status_code == status


def test_startup_reads_changed_dotenv(tmp_path: Path) -> None:
    settings = tmp_path / ".env"
    environment = dict(os.environ)
    for name in ("DECISION_ENGINE", "PORT", "LAYA_MODEL", "LAYA_MAX_TOKENS"):
        environment.pop(name, None)
    code = (
        "import sys; from pathlib import Path; import server; "
        "server.ROOT = Path(sys.argv[1]); "
        "server.uvicorn.run = lambda app, **kwargs: "
        "print(server.get_engine().name, kwargs['host'], kwargs['port']); "
        "server.main(host='0.0.0.0')"
    )
    for engine in ("jev", "laya"):
        settings.write_text(f"DECISION_ENGINE={engine}\nPORT=4012\n")
        process = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        assert process.stdout.splitlines()[-1] == f"{engine} 0.0.0.0 4012"


@pytest.mark.anyio
async def test_realtime_mode_uses_current_source_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    path = tmp_path / "events.log"
    path.write_text("")

    async def handle_records(specs: list[Result]) -> AsyncIterator[Result]:
        for record in []:
            yield record

    monkeypatch.setattr(server, "follow_configured", handle_records)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/api/file-source",
            headers={"Origin": "http://127.0.0.1"},
            json={"mode": "realtime", "sources": [{"path": str(path)}]},
        )
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]["mode"] == "realtime"
    assert events[-1]["type"] == "done"


@pytest.mark.anyio
async def test_clean_ui_routes_support_direct_links_without_catching_api_errors() -> (
    None
):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        for path in (
            "/tasks",
            "/tasks/example/history",
            "/tasks/example/edit",
            "/tasks/new",
            "/sources/example",
            "/sources/new",
            "/criteria/general",
            "/actions/example/edit",
            "/settings",
            "/settings/configuration",
            "/settings/ssh-keys/example",
            "/settings/ssh-hosts/example/edit",
            "/runs/" + "a" * 32 + "?review=needs-review",
        ):
            response = await client.get(path)
            assert response.status_code == 200, path
            assert response.headers["content-type"].startswith("text/html")
            assert 'src="/app.js"' in response.text
            assert response.headers["cache-control"] == "no-store"
        for path in (
            "/api/unknown",
            "/missing",
            "/tasks/example/run",
            "/tasks/example/delete",
            "/unknown.js",
        ):
            response = await client.get(path)
            assert response.status_code == 404
            assert response.headers["content-type"].startswith("application/json")
        assert (await client.post("/tasks")).status_code != 200


@pytest.mark.anyio
@pytest.mark.parametrize("enabled", ["true", "false"])
async def test_status_exposes_authentication_mode_only(
    monkeypatch: pytest.MonkeyPatch, enabled: str
) -> None:
    """The browser reads identity from OAuth2-Proxy, never client-supplied headers."""
    monkeypatch.setenv("OAUTH2_PROXY_ENABLED", enabled)
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/status", headers={"X-Forwarded-Email": "forged@example.com"}
        )
    assert response.json()["authenticationEnabled"] == (enabled == "true")
    assert "forged@example.com" not in response.text
