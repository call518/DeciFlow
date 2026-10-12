import asyncio
from contextlib import aclosing
from typing import Any

import anyio
import httpx
import pytest

from classifier import CRITERIA, Result, classify_batch, classify_log, parse_logs
from config import get_engine

ANSWER: Result = {
    "choice": "error",
    "confidence": 0.6,
    "probabilities": {
        "normal": 0.1,
        "warning": 0.1,
        "error": 0.7,
        "security": 0.05,
        "other": 0.05,
    },
}


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_collapsed_options_require_review_only_for_laya(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    data = {
        "usage": {
            "truncated": False,
            "options": {"category": {"total": 5, "distinct": 3}},
        },
        "answers": {"category": ANSWER},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        result = await classify_log("original log", get_engine(), client)
    assert result["category"] == ANSWER["choice"]
    assert result["uncertain"] is (engine == "laya")
    assert result["review"] is (engine == "laya")
    assert result["reviewReasons"] == (
        ["collapsed_options"] if engine == "laya" else []
    )
    assert result["providerResponse"] == data


@pytest.mark.anyio
@pytest.mark.parametrize(
    "options", [{"total": 5, "distinct": 6}, {"total": 5, "distinct": True}, {}]
)
async def test_invalid_option_integrity_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch, options: Result
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    data = {
        "usage": {"truncated": False, "options": {"category": options}},
        "answers": {"category": ANSWER},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        with pytest.raises(ValueError, match="response format"):
            await classify_log("original log", get_engine(), client)


@pytest.mark.parametrize("text", ["", None, " \n ", 123])
def test_invalid_input(text: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        parse_logs(text)


def test_parse_crlf() -> None:
    assert parse_logs(" first\r\n\n second ") == ["first", "second"]


@pytest.mark.anyio
async def test_jev_contract() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content)
        assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert body["state"] == "connection refused"
        assert body["model"] == "jev-1.13.0"
        assert body["questions"]["category"]["type"] == "choice"
        assert body["questions"]["category"]["criteria"] == CRITERIA
        return httpx.Response(
            200, json={"model": "jev-test", "answers": {"category": ANSWER}}
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("connection refused", get_engine(), client)
    assert result["review"] is False
    assert result["answerProbability"] == 0.7
    assert result["confidence"] == 0.6
    assert result["category"] == "error"
    assert result["model"] == "jev-test"


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.parametrize(
    "answer",
    [
        {},
        {**ANSWER, "choice": "unknown"},
        {**ANSWER, "confidence": 2},
        {**ANSWER, "confidence": True},
        {**ANSWER, "confidence": float("nan")},
        {**ANSWER, "probabilities": {}},
        {**ANSWER, "probabilities": {key: 0.5 for key in CRITERIA}},
    ],
)
async def test_invalid_response(
    answer: Result, engine_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)

    def handle_request(request: httpx.Request) -> httpx.Response:
        import json

        return httpx.Response(
            200,
            content=json.dumps(
                {"answers": {"category": answer}, "usage": {"truncated": False}}
            ),
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="response format"):
            await classify_log("log", get_engine(), client)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 422, 429, 500])
async def test_http_failure(status: int) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        with pytest.raises(ValueError, match=str(status)):
            await classify_log("log", get_engine(), client)


@pytest.mark.anyio
async def test_timeout() -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="30 seconds"):
            await classify_log("log", get_engine(), client)


@pytest.mark.anyio
async def test_batch_concurrency_order_and_failures() -> None:
    active = peak = 0

    async def handle_classify(log: str) -> Result:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await anyio.sleep(0.005 if int(log) % 2 else 0.015)
        active -= 1
        if log == "3":
            raise ValueError("rate limited")
        return {"category": "normal"}

    logs = [str(index) for index in range(9)]
    results = dict([row async for row in classify_batch(logs, handle_classify)])
    assert peak == 4
    assert [results[index]["log"] for index in range(9)] == logs
    assert results[3]["error"] == "rate limited"
    assert results[3]["review"] is False
    assert results[8]["category"] == "normal"


@pytest.mark.anyio
async def test_ten_thousand_logs() -> None:
    line = '127.0.0.1 - - [10/Oct/2026:09:00:00 +0900] "GET / HTTP/1.1" 200 1024'
    text = "\n".join(f"{line} request={index}" for index in range(10000))
    assert len(text.encode()) > 500_000
    logs = parse_logs(text)

    async def handle_classify(log: str) -> Result:
        return {"category": "normal"}

    results = dict([row async for row in classify_batch(logs, handle_classify)])
    assert len(results) == 10000
    assert [results[index]["log"] for index in range(10000)] == logs


@pytest.mark.anyio
async def test_stream_closure_cancels_workers() -> None:
    calls = cancelled = 0
    started = anyio.Event()

    async def handle_classify(log: str) -> dict[str, Any]:
        nonlocal calls, cancelled
        calls += 1
        if calls == 4:
            started.set()
        if log == "0":
            await started.wait()
            return {"category": "normal"}
        try:
            await anyio.sleep_forever()
            raise AssertionError("sleep_forever unexpectedly returned")
        except asyncio.CancelledError:
            cancelled += 1
            raise

    async with aclosing(
        classify_batch([str(i) for i in range(100)], handle_classify)
    ) as stream:
        index, _ = await anext(stream)
        assert index == 0
    assert calls == 4
    assert cancelled == 3
