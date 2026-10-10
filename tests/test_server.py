import json

import httpx
import pytest

import server
from classifier import Result
from config import Engine


@pytest.mark.anyio
async def test_laya_status_without_jev_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.delenv("TYPESAFE_API_KEY")
    monkeypatch.setenv("MAX_JEV_INPUT_BYTES", "unused")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        status = (await client.get("/api/status")).json()
    assert status["engine"] == "laya"
    assert status["configured"] is True
    assert status["model"] == "multilingual"
    assert status["limits"] == {"context_tokens": 8192}


@pytest.mark.anyio
async def test_assets_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        for path in ["/", "/app.js", "/stream.js", "/style.css"]:
            response = await client.get(path)
            assert response.status_code == 200
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            if path == "/":
                assert '<html lang="en">' in response.text
                assert 'id="powered-by"' in response.text
        status = (await client.get("/api/status")).json()
        assert status["configured"] is False
        assert status["limits"]["context_tokens"] == 32000
        assert status["model"] == "jev-1.13.0"
        assert (await client.get("/missing")).status_code == 404


@pytest.mark.anyio
async def test_upload_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        assert (await client.post("/api/classify", json={})).status_code == 403
        headers = {"Origin": "http://test"}
        response = await client.post(
            "/api/classify", headers=headers, json={"text": ("a" * 100 + "\n") * 10000}
        )
        assert response.status_code == 503
        assert "TYPESAFE_API_KEY" in response.json()["error"]
        for body in [{}, [], {"text": ""}]:
            assert (
                await client.post("/api/classify", headers=headers, json=body)
            ).status_code == 400
        assert (
            await client.post("/api/classify", headers=headers, content="{")
        ).status_code == 400


@pytest.mark.anyio
async def test_upload_above_old_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
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
            assert "TYPESAFE_API_KEY" in response.json()["error"]


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
    assert results[1]["review"] is True
    assert "429" in results[1]["error"]
    assert [event["completed"] for event in events[1:-1]] == [1, 2]
