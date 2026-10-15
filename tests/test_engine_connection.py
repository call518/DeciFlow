"""Connection diagnostics distinguish transport failures from rejected decisions."""

from collections.abc import AsyncGenerator

import httpx
import pytest
from conftest import DECISION_ANSWERS

from classifier import CRITERIA, Result, classify_batch, classify_log, classify_stream
from config import get_engine


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize(
    ("kind", "connection"),
    [
        ("success", "connected"),
        ("disconnect", "disconnected"),
        ("timeout", "timeout"),
        ("http_error", "api_error"),
        ("invalid_response", "connected"),
    ],
)
@pytest.mark.anyio
async def test_engine_connection_and_failure_review(
    monkeypatch: pytest.MonkeyPatch, engine: str, kind: str, connection: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)

    def handle_request(request: httpx.Request) -> httpx.Response:
        if kind == "disconnect":
            raise httpx.ConnectError("connection refused", request=request)
        if kind == "timeout":
            raise httpx.ReadTimeout("timed out", request=request)
        if kind == "http_error":
            return httpx.Response(503, json={"error": "unavailable"})
        if kind == "invalid_response":
            return httpx.Response(200, json={})
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
                            key: int(key == "normal") for key in CRITERIA
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, get_engine(), client)

        batch = dict([row async for row in classify_batch(["event"], handle_classify)])

        async def records() -> AsyncGenerator[Result, None]:
            yield {"log": "event", "source": "test.log"}

        stream = [row async for row in classify_stream(records(), handle_classify)]
    for result in (batch[0], stream[0][1]):
        assert result["engineConnection"] == connection
        assert result["review"] is False
        assert ("error" in result) is (kind != "success")


@pytest.mark.anyio
async def test_local_rejection_does_not_report_engine_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JEV_MAX_INPUT_BYTES", "1")

    def handle_request(request: httpx.Request) -> httpx.Response:
        pytest.fail("Local rejection must not call the provider.")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, get_engine(), client)

        results = dict(
            [row async for row in classify_batch(["event"], handle_classify)]
        )
    assert "error" in results[0]
    assert results[0]["review"] is False
    assert "engineConnection" not in results[0]
