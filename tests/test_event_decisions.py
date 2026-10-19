"""Exercise record input and arbitrary typed decisions across both providers."""

import json
from collections.abc import AsyncGenerator
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from classifier import DecisionError, Result, classify_log, classify_stream
from config import get_engine
from configured_sources import read_configured
from decisions import answer_value
from profiles import DEFAULT_PROFILES, use_profile_snapshot, validate_profiles
from result_store import SQLiteResultStore
from source_registry import validate_sources
from source_settings import parse_source_settings, resolve_configured_sources


def decision_answers(questions: Result) -> Result:
    """Build valid provider responses from declared criteria."""
    answers = {}
    for identity, question in questions.items():
        kind = question["type"]
        if kind == "choice":
            keys = list(question["criteria"])
            answers[identity] = {
                "type": kind,
                "choice": keys[0],
                "confidence": 1,
                "probabilities": {key: int(key == keys[0]) for key in keys},
            }
        elif kind == "score":
            answers[identity] = {
                "type": kind,
                "score": 0,
                "legend": {str(i): text for i, text in enumerate(question["criteria"])},
                "probabilities": {
                    str(i): int(i == 0) for i in range(len(question["criteria"]))
                },
            }
        else:
            answers[identity] = {"type": kind, "noul": 0.8}
    return answers


@pytest.mark.anyio
async def test_jsonl_preserves_duplicates_multiline_and_bad_records(
    tmp_path: Path,
) -> None:
    path = tmp_path / "consultations.jsonl"
    content = "Customer: Help\nAgent: I will call back."
    valid = json.dumps({"body": content, "case": 17})
    path.write_text(f'{valid}\n{{bad\n{{}}\n{{"body":1}}\n{valid}')
    specs = parse_source_settings(
        [
            {
                "path": str(path),
                "format": "jsonl",
                "contentField": "body",
                "chunkEvents": 10,
            }
        ]
    )
    assert specs[0]["chunkEvents"] == 1
    records = [row async for row in read_configured(resolve_configured_sources(specs))]
    assert len(records) == 5
    assert records[0]["log"] == records[4]["log"] == content
    assert records[0]["inputRecord"] == {"case": 17}
    assert records[0]["inputContentInLog"] is True
    assert "rawInput" not in records[0]
    assert records[1]["rawInput"] == "{bad"
    assert records[0]["recordNumber"] == 1 and records[4]["recordNumber"] == 5
    calls = []

    async def classify(text: str) -> Result:
        calls.append(text)
        return {"category": "normal"}

    async def stream() -> AsyncGenerator[Result, None]:
        for row in records:
            yield row

    results = [result async for _, result in classify_stream(stream(), classify)]
    assert len(calls) == 2 and len(results) == 5
    assert sum(bool(row.get("error")) for row in results) == 3


@pytest.mark.anyio
async def test_all_voc_rows_are_independent() -> None:
    path = Path("sample-logs/voc-asia-culture-center-consulting-qna.jsonl")
    if not path.exists():
        pytest.skip("Optional local VOC sample is unavailable.")
    count = 0
    async for row in read_configured(
        {
            path: {
                "profile": "consultation",
                "chunkEvents": 1,
                "format": "jsonl",
                "contentField": "consulting_content",
            }
        }
    ):
        assert not row.get("error")
        count += 1
    assert count == 841


@pytest.mark.parametrize("field", [None, "", "  ", 42])
def test_jsonl_requires_content_field(field: object) -> None:
    with pytest.raises(ValueError):
        validate_sources(
            [
                {
                    "name": "VOC",
                    "type": "local",
                    "path": "/voc.jsonl",
                    "format": "jsonl",
                    "contentField": field,
                }
            ]
        )


@pytest.mark.parametrize("profile_id", ["consultation", "central_gov", "local_gov"])
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.parametrize("invalid", [None, "missing", "score", "noul", "choice"])
@pytest.mark.anyio
async def test_ten_mixed_decisions_validate_each_answer(
    monkeypatch: pytest.MonkeyPatch,
    engine_name: str,
    profile_id: str,
    invalid: str | None,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    profiles = deepcopy(DEFAULT_PROFILES)
    profile = profiles[profile_id]
    questions = profile["questions"]
    for i in range(5):
        questions[f"extra_{i}"] = deepcopy(questions["urgency"])
    profiles = validate_profiles(profiles)
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        assert len(body["questions"]) == 10
        answers = decision_answers(body["questions"])
        if invalid == "missing":
            answers.pop("extra_4")
        elif invalid == "score":
            answers["extra_4"]["score"] = 1
        elif invalid == "noul":
            answers["follow_up_required"]["noul"] = True
        elif invalid == "choice":
            answers["follow_up_owner"]["probabilities"] = {"wrong": 1}
        return httpx.Response(
            200, json={"answers": answers, "usage": {"truncated": False}}
        )

    with use_profile_snapshot(profiles):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request)
        ) as client:
            if invalid:
                with pytest.raises(DecisionError, match="Invalid"):
                    await classify_log(
                        "Customer: Help", get_engine(), client, profile_id
                    )
                return
            result = await classify_log(
                "Customer: Help", get_engine(), client, profile_id
            )
    assert len(calls) == 1 and len(result["decisions"]) == 10
    assert "ticketProbability" not in result
    primary = profile["primaryQuestion"]
    assert result["primaryQuestion"] == primary
    assert result["categoryFilter"].endswith(
        ":" + next(iter(questions[primary]["criteria"]))
    )
    assert result["decisionDefinitions"] == questions


def test_custom_aggregates_filters_and_typed_review_export(tmp_path: Path) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    snapshot = {"state": "completed", "settings": {}}
    store.create("run", snapshot)
    definition = DEFAULT_PROFILES["consultation"]
    questions = definition["questions"]
    answers = decision_answers(questions)
    result = {
        "log": "Conversation",
        "category": "예약",
        "categoryFilter": "voc:예약",
        "classificationGroup": "voc",
        "primaryQuestion": "inquiry_type",
        "profileLabel": definition["label"],
        "decisionDefinitions": questions,
        "decisions": answers,
    }
    store.append("run", {"type": "result", "result": result}, snapshot)
    assert store.state("run")["summary"]["categories"]["all"]["voc:예약"] == 1
    assert len(store.page("run", {"category": "voc:예약"}, 10)["items"]) == 1
    for identity, value in [
        ("handling_status", "확인 불가"),
        ("urgency", 2.5),
        ("follow_up_required", 0.2),
    ]:
        store.review("run", 1, "", identity, value)
    reviewed = store.page("run", {}, 10)["items"][0]["result"]
    assert reviewed["decisions"] == answers
    assert reviewed["reviewerDecisions"] == {
        "handling_status": "확인 불가",
        "urgency": 2.5,
        "follow_up_required": 0.2,
    }
    assert len(store.events("run", reviewed_only=True)) == 1
    for identity in reviewed["reviewerDecisions"]:
        store.review("run", 1, "", identity, answer_value(answers[identity]))
    assert not store.events("run", reviewed_only=True)
    for identity, value in [
        ("handling_status", "bad"),
        ("urgency", 8),
        ("follow_up_required", True),
    ]:
        with pytest.raises(ValueError):
            store.review("run", 1, "", identity, value)
    store.close()


@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.anyio
async def test_secondary_choice_needs_review_without_changing_primary_certainty(
    monkeypatch: pytest.MonkeyPatch,
    engine_name: str,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    profiles = deepcopy(DEFAULT_PROFILES)

    def handle_request(request: httpx.Request) -> httpx.Response:
        questions = json.loads(request.content)["questions"]
        answers = decision_answers(questions)
        answers["handling_status"].update(
            choice="확인 불가",
            probabilities={
                key: int(key == "확인 불가")
                for key in questions["handling_status"]["criteria"]
            },
        )
        return httpx.Response(
            200, json={"answers": answers, "usage": {"truncated": False}}
        )

    with use_profile_snapshot(profiles):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handle_request)
        ) as client:
            result = await classify_log(
                "Conversation", get_engine(), client, "consultation"
            )
    assert result["review"] is True
    assert result["uncertain"] is False
    assert result["decisionReviews"]["handling_status"] == ["other_category"]
    assert result["decisionReviews"]["inquiry_type"] == []


def test_existing_sqlite_results_survive_review_schema_upgrade(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE events (run_id TEXT NOT NULL, sequence INTEGER NOT NULL, "
            "kind TEXT NOT NULL, payload TEXT NOT NULL, category TEXT, host TEXT, "
            "review INTEGER, failed INTEGER, log_folded TEXT, reviewer TEXT, "
            "PRIMARY KEY(run_id,sequence))"
        )
        event = {
            "type": "result",
            "result": {"log": "Existing result", "category": "normal"},
        }
        connection.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                "old",
                1,
                "result",
                json.dumps(event),
                "normal",
                "local",
                0,
                0,
                "existing result",
                None,
            ),
        )
    store = SQLiteResultStore(path)
    assert store.page("old", {}, 10)["items"][0]["result"]["log"] == "Existing result"
    store.review("old", 1, "error")
    assert len(store.events("old", reviewed_only=True)) == 1
    store.close()


@pytest.mark.anyio
async def test_local_gov_sample_preserves_metadata() -> None:
    """Read every local government record using its Unicode content field."""
    path = Path("sample-logs/voc-local-gov-consulting-qna.jsonl")
    originals = [json.loads(line) for line in path.read_text().splitlines()]
    specs = parse_source_settings(
        [
            {
                "path": str(path),
                "format": "jsonl",
                "contentField": "상담내용",
                "profile": "local_gov",
                "chunkEvents": 10,
            }
        ]
    )
    records = [row async for row in read_configured(resolve_configured_sources(specs))]
    assert len(records) == len(originals) == 3280
    for row, original in zip(records, originals, strict=True):
        assert "error" not in row
        assert row["log"] == original["상담내용"]
        assert row["inputRecord"] == {
            "지방자치단체명": original["지방자치단체명"],
            "상담담당부서": original["상담담당부서"],
        }
        assert row["inputContentInLog"] is True
        assert row["eventCount"] == row["chunkEvents"] == 1
    assert any(row["inputRecord"]["상담담당부서"] == "" for row in records)
