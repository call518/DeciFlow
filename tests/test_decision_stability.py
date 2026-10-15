import json

import httpx
import pytest
from conftest import DECISION_ANSWERS

from classifier import Result, _decision_input, classify_batch, classify_log
from config import get_engine
from profiles import PROFILES


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("service", ["sshd", "auth-gateway"])
@pytest.mark.parametrize(
    "message",
    [
        "error: kex_exchange_identification: Connection closed by remote host",
        "Authentication negotiation ended before completion",
        "Client terminated session before authentication",
    ],
)
async def test_auth_messages_share_input_but_preserve_original_logs(
    monkeypatch: pytest.MonkeyPatch, engine: str, service: str, message: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    logs = [
        f"Oct 10 20:47:21 host-a {service}[583553]: {message}",
        f"Oct 10 20:47:41 host-b {service}[583612]: {message}",
    ]
    states: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        states.append(payload["state"])
        question = payload["questions"]["category"]
        assert question["criteria"] == PROFILES["authentication"]["criteria"]
        assert message not in json.dumps(question)

        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "warning",
                        "confidence": 0.9,
                        "probabilities": {
                            key: float(key == "warning")
                            for key in PROFILES["general"]["criteria"]
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, get_engine(), client, "authentication")

        results = dict([row async for row in classify_batch(logs, handle_classify)])
    assert states == [f"{service}: {message}"] * 2
    assert [results[i]["log"] for i in range(2)] == logs
    assert results[0]["decisionInput"] == results[1]["decisionInput"]
    assert results[0]["inputNormalization"] == "single_line_syslog_header"


def test_normalization_keeps_multiline_and_semantic_fields() -> None:
    first = "Oct 10 20:47:21 node sshd[123]: Failed password for root from 10.1.2.3 port 5000"
    second = "Oct 10 20:47:41 node sshd[124]: Accepted password for root from 10.1.2.3 port 5001"
    assert (
        _decision_input(first, "authentication")
        == "sshd: Failed password for root from 10.1.2.3 port 5000"
    )
    assert (
        _decision_input(first + "\n" + second, "authentication")
        == first + "\n" + second
    )
    assert _decision_input(first, "general") == first
    assert (
        _decision_input("unrecognized format 123", "authentication")
        == "unrecognized format 123"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize(
    ("confidence", "probabilities", "expected"),
    [
        (
            0.9,
            [0.5, 0.45, 0.03, 0.01, 0.01],
            ["low_answer_probability", "close_probabilities"],
        ),
        (0.9, [0.5, 0.4, 0.05, 0.03, 0.02], ["low_answer_probability"]),
        (
            0.26,
            [0.01, 0.18, 0.41, 0.0, 0.4],
            ["low_answer_probability", "close_probabilities"],
        ),
        (0.16, [0.9, 0.04, 0.03, 0.02, 0.01], []),
        (0.99, [0.5039, 0.1924, 0.1316, 0.0884, 0.0837], ["low_answer_probability"]),
        (0.4, [0.7, 0.15, 0.1, 0.03, 0.02], []),
    ],
)
async def test_uncertainty_preserves_model_choice(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
    confidence: float,
    probabilities: list[float],
    expected: list[str],
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    distribution = dict(
        zip(PROFILES["general"]["criteria"], probabilities, strict=True)
    )
    choice = max(distribution, key=lambda key: distribution[key])

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": choice,
                        "confidence": confidence,
                        "probabilities": distribution,
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("log", get_engine(), client)
    assert result["category"] == choice
    assert result["probabilities"] == distribution
    assert result["confidence"] == confidence
    assert result["answerProbability"] == distribution[choice]
    assert result["uncertaintyBasis"] == "selected_category_probability"
    assert result["reviewReasons"] == expected
    assert result["uncertain"] is bool(expected)
    assert result["review"] is bool(expected)
