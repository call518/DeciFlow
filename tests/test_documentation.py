"""Keep published request/result examples aligned with the live classifier contract."""

import json
import re
from collections import Counter
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


@pytest.mark.parametrize("directory", [ROOT, ROOT / "docs"])
def test_readmes_keep_commands_identifiers_and_links_equivalent(
    directory: Path,
) -> None:
    """Catch technical drift while allowing translated prose and link anchors."""
    texts = [(directory / name).read_text() for name in ("README.md", "README.ko.md")]
    commands = []
    identifiers = []
    targets = []
    for text in texts:
        blocks = re.findall(r"```([^\n]*)\n(.*?)\n```", text, flags=re.DOTALL)
        commands.append(
            [
                (
                    language,
                    [line for line in body.splitlines() if not line.startswith("#")],
                )
                for language, body in blocks
            ]
        )
        without_blocks = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        identifiers.append(set(re.findall(r"`([^`\n]+)`", without_blocks)))
        targets.append(
            Counter(
                target.split("#")[0].replace(".ko.md", ".md")
                for target in re.findall(r"\]\(([^)]+)\)", text)
                if not target.startswith(("https://", "http://", "#"))
            )
        )
        for profile_name in ("consultation", "central_gov", "local_gov"):
            profile = json.loads(
                (ROOT / "profiles" / f"{profile_name}.json").read_text()
            )
            assert profile["label"] in text
    assert commands[0] == commands[1]
    assert identifiers[0] == identifiers[1]
    assert targets[0] == targets[1]
