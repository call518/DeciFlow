"""Keep inclusive answer tolerances stable at floating-point boundaries."""

import httpx
import pytest

from deciflow.classifier import classify_log
from deciflow.config import get_engine
from deciflow.decisions import validate_answer
from deciflow.profiles import DEFAULT_PROFILES


@pytest.mark.parametrize(
    ("score", "accepted"),
    [(2.46, True), (2.50, True), (2.459999, False), (2.500001, False)],
)
def test_score_tolerance_is_inclusive(score: float, accepted: bool) -> None:
    """Allow exactly ±0.02 without admitting a materially larger deviation."""
    question = DEFAULT_PROFILES["efb7c8ca-61c1-4785-b38d-0a86764ca758"]["questions"][
        "urgency"
    ]
    answer = {
        "type": "score",
        "score": score,
        "legend": {str(i): text for i, text in enumerate(question["criteria"])},
        "probabilities": {"0": 0.05, "1": 0.08, "2": 0.21, "3": 0.66},
    }
    if accepted:
        validate_answer(question, answer)
    else:
        with pytest.raises(ValueError, match="probability-weighted"):
            validate_answer(question, answer)


@pytest.mark.parametrize(
    ("total", "accepted"),
    [(0.98, True), (1.02, True), (0.979999, False), (1.020001, False)],
)
def test_probability_sum_tolerance_is_inclusive(total: float, accepted: bool) -> None:
    """Treat the sum tolerance identically above and below one."""
    question = {"type": "choice", "criteria": {"yes": "Yes", "no": "No"}}
    answer = {
        "type": "choice",
        "choice": "yes",
        "confidence": 1,
        "probabilities": {"yes": 0.5, "no": total - 0.5},
    }
    if accepted:
        validate_answer(question, answer)
    else:
        with pytest.raises(ValueError, match="sum to 1"):
            validate_answer(question, answer)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_reported_urgency_boundary_is_accepted_for_both_providers(
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
) -> None:
    """Accept the reported score without altering the provider's answer."""
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv("LAYA_MODEL", "multilingual")
    answers = {}
    for identity, question in DEFAULT_PROFILES["efb7c8ca-61c1-4785-b38d-0a86764ca758"][
        "questions"
    ].items():
        kind = question["type"]
        if kind == "choice":
            choice = next(iter(question["criteria"]))
            answers[identity] = {
                "type": kind,
                "choice": choice,
                "confidence": 1,
                "probabilities": {
                    key: int(key == choice) for key in question["criteria"]
                },
            }
        elif kind == "score":
            answers[identity] = {
                "type": kind,
                "score": 2.46,
                "legend": {str(i): text for i, text in enumerate(question["criteria"])},
                "probabilities": {"0": 0.05, "1": 0.08, "2": 0.21, "3": 0.66},
            }
        else:
            answers[identity] = {"type": kind, "noul": 0.15}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"answers": answers, "usage": {"truncated": False}},
            )
        )
    ) as client:
        result = await classify_log(
            "Example consultation",
            get_engine(),
            client,
            "efb7c8ca-61c1-4785-b38d-0a86764ca758",
        )
    assert result["decisions"] == answers
    assert result["decisions"]["urgency"]["score"] == 2.46
