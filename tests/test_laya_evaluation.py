"""Keep the live evaluation safe and honest about incorrect predictions."""

import httpx
import pytest
from conftest import DECISION_ANSWERS

from config import Engine
from scripts.evaluate_laya import evaluate, summarize


@pytest.mark.anyio
async def test_evaluation_refuses_paid_jev() -> None:
    with pytest.raises(ValueError, match="never calls paid Jev"):
        await evaluate(Engine("jev", "", "", "jev-1.13.0", 30), [])


@pytest.mark.anyio
async def test_evaluation_records_mismatches_and_provider_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "routing": {"model": "english"},
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "normal",
                        "confidence": 0.2,
                        "probabilities": {
                            "normal": 0.9,
                            "warning": 0.025,
                            "error": 0.025,
                            "security": 0.025,
                            "other": 0.025,
                        },
                    },
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    monkeypatch.setattr(httpx, "AsyncClient", lambda: client)
    rows = await evaluate(
        Engine("laya", "http://test/v1/systemone", "", "english", 120),
        [
            {"log": "routine operation", "expected": "normal"},
            {"log": "failed operation", "expected": "error"},
        ],
    )
    assert [row["correct"] for row in rows] == [True, False]
    assert rows[1]["result"]["category"] == "normal"
    assert rows[1]["result"]["providerResponse"]["routing"]["model"] == "english"
    assert rows[1]["result"]["uncertain"] is False
    summary = summarize(rows)
    assert summary["certain"] == 2
    assert summary["certainCorrect"] == 1
    assert summary["confusionMatrix"]["error"]["normal"] == 1


def test_evaluation_separates_failures_and_uncertain_predictions() -> None:
    summary = summarize(
        [
            {"expected": "warning", "correct": False, "result": {"error": "timeout"}},
            {
                "expected": "error",
                "correct": True,
                "result": {"category": "error", "uncertain": True},
            },
        ]
    )
    assert summary["failed"] == 1
    assert summary["uncertain"] == 1
    assert summary["certain"] == 0
    assert summary["confusionMatrix"]["warning"]["failed"] == 1
