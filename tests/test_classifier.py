import asyncio
from contextlib import aclosing
from typing import Any

import anyio
import httpx
import pytest
from conftest import DECISION_ANSWERS

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
        "answers": {**DECISION_ANSWERS, "category": ANSWER},
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        result = await classify_log("original log", get_engine(), client)
    assert result["decisions"]["category"]["choice"] == ANSWER["choice"]
    assert result["decisionAssessments"]["category"]["uncertain"] is (engine == "laya")
    assert result["review"] is (engine == "laya")
    assert result["decisionAssessments"]["category"]["reviewReasons"] == (
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
        "answers": {**DECISION_ANSWERS, "category": ANSWER},
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
            200,
            json={
                "model": "jev-test",
                "answers": {**DECISION_ANSWERS, "category": ANSWER},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("connection refused", get_engine(), client)
    assert result["review"] is False
    assert result["decisionAssessments"]["category"]["answerProbability"] == 0.7
    assert result["decisions"]["category"]["confidence"] == 0.6
    assert result["decisions"]["category"]["choice"] == "error"
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
                {
                    "answers": {**DECISION_ANSWERS, "category": answer},
                    "usage": {"truncated": False},
                }
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


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.parametrize(
    "score,levels,ticket",
    [
        (0.0, [1.0, 0.0, 0.0, 0.0], 0.0),
        (2.37, [0.0, 0.0, 0.63, 0.37], 0.91),
        (3.0, [0.0, 0.0, 0.0, 1.0], 1.0),
    ],
)
async def test_three_questions_share_one_request(
    monkeypatch: pytest.MonkeyPatch,
    engine_name: str,
    score: float,
    levels: list[float],
    ticket: float,
) -> None:
    import json

    from profiles import DEFAULT_PROFILES

    definitions = DEFAULT_PROFILES["general"]["questions"]

    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    calls = []
    answers = {
        "category": ANSWER,
        "urgency": {
            **DECISION_ANSWERS["urgency"],
            "score": score,
            "probabilities": {str(i): value for i, value in enumerate(levels)},
        },
        "ticket": {"type": "noul", "noul": ticket},
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert body["state"] == "checkout failed"
        assert set(body["questions"]) == {"category", "urgency", "ticket"}
        for name, question in definitions.items():
            sent = body["questions"][name]
            assert sent["type"] == question["type"]
            assert sent.get("criteria") == question.get("criteria")
            assert DEFAULT_PROFILES["general"]["instructions"] in sent["instructions"]
            assert question["instructions"] in sent["instructions"]
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": answers,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("checkout failed", get_engine(), client)
    assert len(calls) == 1
    assert result["decisions"]["urgency"]["score"] == score
    assert result["decisions"]["ticket"]["noul"] == ticket
    assert result["questions"] == calls[0]["questions"]
    assert "question" not in result
    assert (
        result["decisions"]["urgency"]["probabilities"]
        == answers["urgency"]["probabilities"]
    )


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("urgency", None),
        ("ticket", None),
        ("urgency", {**DECISION_ANSWERS["urgency"], "score": True}),
        ("urgency", {**DECISION_ANSWERS["urgency"], "score": 4}),
        ("urgency", {**DECISION_ANSWERS["urgency"], "score": float("nan")}),
        ("urgency", {**DECISION_ANSWERS["urgency"], "score": 1}),
        ("urgency", {**DECISION_ANSWERS["urgency"], "legend": {}}),
        ("urgency", {**DECISION_ANSWERS["urgency"], "probabilities": {}}),
        ("ticket", {"type": "noul", "noul": True}),
        ("ticket", {"type": "noul", "noul": -0.1}),
        ("ticket", {"type": "choice", "noul": 0.5}),
    ],
)
async def test_invalid_operational_answers_fail_decision(
    monkeypatch: pytest.MonkeyPatch, engine_name: str, field: str, value: Any
) -> None:
    import json

    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    answers = {**DECISION_ANSWERS, "category": ANSWER}
    if value is None:
        del answers[field]
    else:
        answers[field] = value
    data = {"usage": {"truncated": False}, "answers": answers}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=json.dumps(data))
        )
    ) as client:
        with pytest.raises(ValueError, match="response format"):
            await classify_log("checkout failed", get_engine(), client)
