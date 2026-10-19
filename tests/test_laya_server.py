"""Verify the released Laya server applies full-event token checks."""

from types import SimpleNamespace
from typing import Any

import pytest

import laya_server
from config import LAYA_CONTEXT_TOKENS


class Tokenizer:
    mask_token = "[MASK]"

    def __call__(self, text: str, **kwargs: Any) -> dict[str, list[str]]:
        return {"input_ids": list(text)}


class Router:
    def __init__(self) -> None:
        self.loaded = ["multilingual"]
        self.calls: list[dict[str, Any]] = []

    def load(self, model: str) -> SimpleNamespace:
        assert model == "multilingual"
        return SimpleNamespace(tok=Tokenizer())

    def predict(self, state: str, questions: dict, **kwargs: Any) -> dict:
        self.calls.append(kwargs)
        return {"usage": {}, "answers": {}}


@pytest.mark.parametrize("extra_tokens", [0, 1])
@pytest.mark.parametrize("head_tokens", [256, 384])
def test_exact_event_budget_before_inference(
    monkeypatch: pytest.MonkeyPatch, extra_tokens: int, head_tokens: int
) -> None:
    monkeypatch.setenv("LAYA_HEAD_TOKENS", str(head_tokens))

    def build_empty(*args: Any) -> tuple[list[int], list[int]]:
        assert args[1] == ""
        assert args[3:] == (LAYA_CONTEXT_TOKENS, head_tokens)
        return list(range(100)), []

    monkeypatch.setattr(
        laya_server,
        "import_module",
        lambda name: SimpleNamespace(
            build_sequence=build_empty, render_options=lambda question: []
        ),
    )
    router = Router()
    adapter = laya_server.LogRouter(router)
    result = adapter.predict(
        "x" * (LAYA_CONTEXT_TOKENS - 100 + extra_tokens),
        {"category": {"type": "choice", "instructions": "Classify.", "criteria": {}}},
        model="multilingual",
    )
    assert adapter.loaded == ["multilingual"]
    assert result["usage"]["truncated"] is bool(extra_tokens)
    if extra_tokens:
        assert router.calls == []
    else:
        assert router.calls == [
            {"model": "multilingual", "max_len": 8192, "head_max_len": head_tokens}
        ]


@pytest.mark.parametrize("overflow_type", [None, "choice", "score", "noul"])
def test_all_question_types_checked_before_inference(
    monkeypatch: pytest.MonkeyPatch, overflow_type: str | None
) -> None:
    from profiles import DEFAULT_PROFILES

    checked = []

    def build_empty(*args: Any) -> tuple[list[int], list[int]]:
        question = args[2]
        checked.append(question["t"])
        assert question["crit"] == questions_by_type[question["t"]].get("criteria")
        return list(range(101 if question["t"] == overflow_type else 100)), []

    monkeypatch.setattr(
        laya_server,
        "import_module",
        lambda name: SimpleNamespace(
            build_sequence=build_empty, render_options=lambda question: []
        ),
    )
    questions = {
        "category": {"type": "choice", "instructions": "Classify.", "criteria": {}},
        **{
            key: DEFAULT_PROFILES["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]["questions"][
                key
            ]
            for key in ("urgency", "ticket")
        },
    }
    questions_by_type = {question["type"]: question for question in questions.values()}
    router = Router()
    result = laya_server.LogRouter(router).predict(
        "x" * (LAYA_CONTEXT_TOKENS - 100), questions, model="multilingual"
    )
    assert result["usage"]["truncated"] is (overflow_type is not None)
    assert len(router.calls) == (0 if overflow_type else 1)
    if overflow_type is None:
        assert checked == ["choice", "score", "noul"]


@pytest.mark.parametrize("dropped", [0, 1, 50])
def test_shortened_criteria_are_reported_without_dropping_the_result(
    monkeypatch: pytest.MonkeyPatch,
    dropped: int,
) -> None:
    """Report instruction or option shortening separately from state overflow."""
    options = ["first option", "second option"]
    instruction = "choice question: Classify."
    full_size = len(instruction) + sum(1 + len(" " + option) for option in options) + 4
    common = SimpleNamespace(
        build_sequence=lambda *args: (list(range(full_size - dropped)), []),
        render_options=lambda question: options,
    )
    monkeypatch.setattr(laya_server, "import_module", lambda name: common)
    router = Router()
    result = laya_server.LogRouter(router).predict(
        "input",
        {"category": {"type": "choice", "instructions": "Classify.", "criteria": {}}},
        model="multilingual",
    )
    assert len(router.calls) == 1
    assert result["usage"]["truncated"] is False
    assert result["usage"].get("criteria_tokens_dropped", {}) == (
        {"category": dropped} if dropped else {}
    )
