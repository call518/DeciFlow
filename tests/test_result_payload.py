"""Verify canonical JSONL inputs and lossless shared result contexts."""

import json
from pathlib import Path

import pytest

from deciflow.result_payload import compact_result
from deciflow.result_store import SQLiteResultStore, open_result_store


def sample() -> dict:
    """Build synthetic JSONL metadata without customer records."""
    record = {"content": "상담 테스트", "caseId": "case-one"}
    return {
        "log": record["content"],
        "inputRecord": record,
        "inputFormat": "jsonl",
        "contentField": "content",
        "rawInput": json.dumps(record, ensure_ascii=False),
        "category": "normal",
        "review": False,
        "elapsedMs": 1,
        "questions": {"category": {"instructions": "Repeated request instructions"}},
        "decisionDefinitions": {
            "category": {
                "type": "choice",
                "label": "Category",
                "criteria": {"normal": "Normal"},
            }
        },
        "decisions": {"category": {"choice": "normal", "probabilities": {"normal": 1}}},
    }


def test_compaction_keeps_one_content_copy_and_is_idempotent() -> None:
    original = sample()
    packed = compact_result(original)
    assert packed["log"] == "상담 테스트"
    assert packed["inputRecord"] == {"caseId": "case-one"}
    assert packed["inputContentInLog"]
    assert "rawInput" not in packed and "questions" not in packed
    assert compact_result(packed) == packed
    assert original["inputRecord"]["content"] == "상담 테스트"
    reconstructed = {**packed["inputRecord"], packed["contentField"]: packed["log"]}
    assert reconstructed == original["inputRecord"]


def test_malformed_and_distinct_raw_input_are_retained() -> None:
    invalid = {
        "inputFormat": "jsonl",
        "log": "broken",
        "rawInput": "broken",
        "error": "Invalid JSON",
    }
    assert compact_result(invalid) == invalid
    distinct = {
        **sample(),
        "rawInput": '{"content":"different original"}',
        "error": "Provider failed",
    }
    packed = compact_result(distinct)
    assert packed["rawInput"] == distinct["rawInput"]
    assert packed["questions"] == distinct["questions"]


def test_sqlite_stores_context_once_and_hydrates_pages_reviews_and_exports(
    tmp_path: Path,
) -> None:
    store = open_result_store(tmp_path)
    assert isinstance(store, SQLiteResultStore)
    snapshot = {"jobId": "run", "state": "running", "settings": {"taskId": "task"}}
    store.create("run", snapshot)
    for index in range(3):
        store.append(
            "run", {"type": "result", "index": index, "result": sample()}, snapshot
        )
    with store.reader() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM result_contexts").fetchone()[0]
            == 1
        )
        raw = json.loads(
            connection.execute("SELECT payload FROM events LIMIT 1").fetchone()[0]
        )["result"]
        assert "decisionDefinitions" not in raw and "questions" not in raw
        assert "rawInput" not in raw and raw["inputRecord"] == {"caseId": "case-one"}
    result = store.page("run", {}, 10)["items"][0]
    assert result["result"]["decisionDefinitions"] == sample()["decisionDefinitions"]
    assert "_contextRefs" not in result["result"]
    store.review("run", result["sequence"], "category", "normal")
    exported = json.loads(store.events("run")[0][1])["result"]
    assert exported["decisionDefinitions"] == sample()["decisionDefinitions"]
    assert "rawInput" not in exported and "questions" not in exported
    store.delete_task("task")
    with store.reader() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM result_contexts").fetchone()[0]
            == 0
        )


@pytest.mark.anyio
async def test_action_receives_canonical_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deciflow import actions
    received = []

    async def execute(action: dict, payload: dict) -> dict:
        received.append(payload)
        return {"status": "success"}

    monkeypatch.setattr(actions, "_run_action", execute)
    await actions.run_action({"id": "test"}, sample())
    assert received == [compact_result(sample())]


def test_identical_provider_answers_use_canonical_decisions_but_errors_keep_diagnostics() -> (
    None
):
    original = sample()
    original["providerResponse"] = {
        "answers": original["decisions"],
        "usage": {"truncated": False},
    }
    result = compact_result(original)
    assert result["providerResponse"] == {
        "usage": {"truncated": False},
        "answersInDecisions": True,
    }
    assert original["providerResponse"]["answers"] == result["decisions"]
    assert (
        compact_result({**original, "error": "Provider validation failed"})[
            "providerResponse"
        ]
        == original["providerResponse"]
    )


def test_shared_definitions_preserve_decision_and_option_order(tmp_path: Path) -> None:
    store = open_result_store(tmp_path)
    snapshot = {"state": "running", "settings": {}}
    store.create("ordered", snapshot)
    item = sample()
    item["decisionDefinitions"]["category"]["criteria"] = {
        "normal": "Normal",
        "alpha": "Alpha",
    }
    item["decisionDefinitions"] = {
        "zeta": {"type": "noul"},
        **item["decisionDefinitions"],
    }
    store.append("ordered", {"type": "result", "result": item}, snapshot)
    definitions = store.page("ordered", {}, 10)["items"][0]["result"][
        "decisionDefinitions"
    ]
    assert list(definitions) == ["zeta", "category"]
    assert list(definitions["category"]["criteria"]) == ["normal", "alpha"]


def test_current_history_is_read_without_rewriting_stored_payload(
    tmp_path: Path,
) -> None:
    store = open_result_store(tmp_path)
    assert isinstance(store, SQLiteResultStore)
    snapshot = {"state": "completed", "settings": {}}
    store.create("current", snapshot)
    store.append(
        "current",
        {"type": "result", "result": {**sample(), "schemaVersion": 2}},
        snapshot,
    )
    original = store.connection.execute("SELECT payload FROM events").fetchone()[0]
    result = store.page("current", {}, 10)["items"][0]["result"]
    assert result["schemaVersion"] == 2
    assert result["inputRecord"] == {"caseId": "case-one"}
    assert "rawInput" not in result
    with store.reader() as connection:
        assert (
            connection.execute("SELECT payload FROM events").fetchone()[0] == original
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM result_contexts").fetchone()[0] > 0
        )
