"""Verify the released Laya server applies full-event token checks."""

from types import SimpleNamespace
from typing import Any

import pytest

import laya_server
from config import LAYA_CONTEXT_TOKENS, LAYA_HEAD_TOKENS


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
def test_exact_event_budget_before_inference(
    monkeypatch: pytest.MonkeyPatch, extra_tokens: int
) -> None:
    def build_empty(*args: Any) -> tuple[list[int], list[int]]:
        assert args[1] == ""
        assert args[3:] == (LAYA_CONTEXT_TOKENS, LAYA_HEAD_TOKENS)
        return list(range(100)), []

    monkeypatch.setattr(
        laya_server,
        "import_module",
        lambda name: SimpleNamespace(build_sequence=build_empty),
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
            {"model": "multilingual", "max_len": 8192, "head_max_len": 256}
        ]
