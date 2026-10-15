"""Keep published request/result examples aligned with the live classifier contract."""

import json
import re
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from classifier import Result, classify_log
from config import get_engine
from profiles import use_profile_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "examples"


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
async def test_documented_request_and_result(
    monkeypatch: pytest.MonkeyPatch, engine_name: str
) -> None:
    """Replay the documented mock answer through each engine without API calls."""
    request_example = json.loads((EXAMPLES / "laya-request.json").read_text())
    example = json.loads((EXAMPLES / "laya-result.json").read_text())
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    monkeypatch.setenv("LAYA_MODEL", example["requestedModel"])
    engine = get_engine()
    expected_request = deepcopy(request_example)
    expected_request["model"] = engine.model
    response = deepcopy(example["providerResponse"])
    if engine_name == "jev":
        del expected_request["max_len"], expected_request["head_max_len"]
        del response["usage"], response["routing"]
        response["model"] = engine.model

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content) == expected_request
        assert expected_request["state"] == example["log"]
        if engine_name == "laya":
            assert len(request.content) == example["requestBytes"]
        return httpx.Response(200, json=response)

    profiles: dict[str, Result] = {
        path.stem: json.loads(path.read_text())
        for path in (ROOT / "profiles").glob("*.json")
    }
    with use_profile_snapshot(profiles):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request)
        ) as client:
            result = await classify_log(
                example["log"], engine, client, example["profile"]
            )
    assert "question" not in example
    assert set(result["questions"]) == {"category", "urgency", "ticket"}
    assert result["providerResponse"] == response
    varying = {"requestedAt", "engine", "requestedModel", "model", "requestBytes"}
    if engine_name == "jev":
        varying.update({"inputBudget", "providerResponse"})
        assert result["inputBudget"] == {"max_jev_input_bytes": 30000}
    for field, value in result.items():
        if field not in varying:
            assert example[field] == value, field


def test_result_documents_share_examples_and_fields() -> None:
    """Require both translations to show exactly the downloadable current examples."""
    examples = [
        json.loads((EXAMPLES / name).read_text())
        for name in ("laya-request.json", "laya-result.json")
    ]
    field_sets: list[list[str]] = []
    for name in ("results.md", "results.ko.md"):
        text = (ROOT / "docs" / name).read_text()
        blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)
        assert [json.loads(block) for block in blocks] == examples
        field_sets.append(
            [
                line.split("|")[1].strip()
                for line in text.splitlines()
                if line.startswith("| `")
            ]
        )
    assert field_sets[0] == field_sets[1]
