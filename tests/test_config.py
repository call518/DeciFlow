import json

import httpx
import pytest

from classifier import Result, classify_batch, classify_log, parse_logs
from config import get_engine, get_jev_input_bytes


@pytest.mark.parametrize("value", ["0", "-1", "abc", "", "1.5", "30001"])
def test_invalid_byte_budget(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MAX_JEV_INPUT_BYTES", value)
    with pytest.raises(ValueError, match="MAX_JEV_INPUT_BYTES"):
        get_jev_input_bytes()


def test_configured_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_JEV_INPUT_BYTES", "20000")
    assert get_jev_input_bytes() == 20000


@pytest.mark.anyio
@pytest.mark.parametrize("log", ["x" * 30000, "😀" * 7500])
async def test_oversized_event_does_not_abort_batch(log: str) -> None:
    calls = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json.loads(request.content)["state"] == "small event"
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            "normal": 1,
                            "warning": 0,
                            "error": 0,
                            "security": 0,
                            "other": 0,
                        },
                    }
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(event: str) -> Result:
            return await classify_log(event, get_engine(), client)

        logs = parse_logs(log + "\nsmall event")
        results = dict([row async for row in classify_batch(logs, handle_classify)])
    assert calls == 1
    assert results[0]["log"] == log
    assert results[0]["review"] is True
    assert "preflight" in results[0]["error"]
    assert results[1]["category"] == "normal"


@pytest.mark.anyio
async def test_byte_budget_includes_question_and_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sizes: list[int] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        sizes.append(len(request.content))
        return httpx.Response(429)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="429"):
            await classify_log("x", get_engine(), client)
        size = sizes[0]
        assert size > 1
        monkeypatch.setenv("MAX_JEV_INPUT_BYTES", str(size))
        with pytest.raises(ValueError, match="429"):
            await classify_log("x", get_engine(), client)
        monkeypatch.setenv("MAX_JEV_INPUT_BYTES", str(size - 1))
        with pytest.raises(ValueError, match="preflight"):
            await classify_log("x", get_engine(), client)
    assert len(sizes) == 2
