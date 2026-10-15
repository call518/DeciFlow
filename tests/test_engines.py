"""Provider parity, local Laya safety, and engine selection regression tests."""

import json

import httpx
import pytest
from conftest import DECISION_ANSWERS

from classifier import CRITERIA, Result, classify_batch, classify_log
from config import get_engine


def test_default_is_local_laya(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECISION_ENGINE")
    monkeypatch.delenv("JEV_API_KEY")
    engine = get_engine()
    assert engine.name == "laya"
    assert engine.url == "http://127.0.0.1:8000/v1/systemone"
    assert engine.api_key == "changeme"


@pytest.mark.parametrize("key", ["", "custom-key"])
def test_laya_key_override(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_API_KEY", key)
    assert get_engine().api_key == key


def test_invalid_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "unknown")
    with pytest.raises(ValueError, match="DECISION_ENGINE"):
        get_engine()


@pytest.mark.parametrize("url", ["", "file:///tmp/log", "http://key@localhost"])
def test_invalid_laya_url(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_API_URL", url)
    with pytest.raises(ValueError, match="LAYA_API_URL"):
        get_engine()


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.parametrize("status", [200, 401, 422, 429, 500])
async def test_provider_contract(
    monkeypatch: pytest.MonkeyPatch, engine_name: str, status: int
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    engine = get_engine()

    def handle_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert str(request.url) == engine.url
        assert body["state"] == "connection refused"
        assert body["questions"]["category"]["criteria"] == CRITERIA
        if engine_name == "laya":
            assert request.headers["authorization"] == "Bearer changeme"
            assert body["model"] == "multilingual"
            assert body["max_len"] == 8192
            assert body["head_max_len"] == 256
        else:
            assert request.headers["authorization"] == "Bearer test-key"
            assert "max_len" not in body
        return httpx.Response(
            status,
            json={
                "model": engine.model,
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "error",
                        "confidence": 0.9,
                        "probabilities": {
                            name: (1 if name == "error" else 0) for name in CRITERIA
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        if status != 200:
            with pytest.raises(ValueError, match=str(status)):
                await classify_log("connection refused", engine, client)
            return
        result = await classify_log("connection refused", engine, client)
    assert result["engine"] == engine_name
    assert result["category"] == "error"
    assert result["review"] is False


@pytest.mark.anyio
async def test_laya_truncation_keeps_original_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    engine = get_engine()

    def handle_request(request: httpx.Request) -> httpx.Response:
        log = json.loads(request.content)["state"]
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": log == "too long"},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            name: (1 if name == "normal" else 0) for name in CRITERIA
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, engine, client)

        results = dict(
            [
                row
                async for row in classify_batch(["too long", "small"], handle_classify)
            ]
        )
    assert results[0]["log"] == "too long"
    assert results[0]["review"] is False
    assert "partial prediction was discarded" in results[0]["error"]
    assert "category" not in results[0]
    assert results[1]["category"] == "normal"


@pytest.mark.anyio
async def test_laya_failure_never_calls_jev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_API_KEY", "local-key")
    urls: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        assert request.headers["authorization"] == "Bearer local-key"
        raise httpx.ConnectError("unavailable", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="Could not connect to Laya"):
            await classify_log("log", get_engine(), client)
    assert urls == ["http://127.0.0.1:8000/v1/systemone"]


@pytest.mark.anyio
@pytest.mark.parametrize("usage", [{}, {"truncated": "false"}])
async def test_laya_missing_token_safety_metadata(
    monkeypatch: pytest.MonkeyPatch, usage: Result
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"usage": usage})
        )
    ) as client:
        with pytest.raises(ValueError, match="Invalid Laya response"):
            await classify_log("log", get_engine(), client)


@pytest.mark.anyio
async def test_remote_laya_uses_client_settings_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_API_URL", "https://laya.example:9443/v1/systemone")
    monkeypatch.setenv("LAYA_API_KEY", "remote-test-key")
    # Server deployment variables must not override the client's endpoint.
    monkeypatch.setenv("LAYA_PORT", "8000")
    monkeypatch.setenv("LAYA_DEVICE", "cuda")
    monkeypatch.setenv("LAYA_THREADS", "unused")

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://laya.example:9443/v1/systemone"
        assert request.headers["authorization"] == "Bearer remote-test-key"
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            name: (1 if name == "normal" else 0) for name in CRITERIA
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("INFO service started", get_engine(), client)
    assert result["category"] == "normal"
    assert result["engine"] == "laya"
