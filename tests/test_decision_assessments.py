"""Verify decision quality, display defaults and indexed historical filtering."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from classifier import classify_log
from config import Engine
from decisions import decision_assessments, needs_review
from profiles import DEFAULT_PROFILES, use_profile_snapshot, validate_profiles
from result_store import SQLiteResultStore, empty_summary


@pytest.fixture
def profile() -> dict[str, Any]:
    return {
        "label": "Assessment Test",
        "instructions": "Use only the input.",
        "primaryQuestion": "area",
        "defaultDecision": "response",
        "questions": {
            "area": {
                "label": "Area",
                "type": "choice",
                "instructions": "Choose area.",
                "criteria": {"a": "A", "b": "B"},
                "reviewOptions": [],
            },
            "response": {
                "label": "Response",
                "type": "choice",
                "instructions": "Choose response.",
                "criteria": {"done": "Done", "pending": "Pending"},
                "reviewOptions": [],
            },
            "urgency": {
                "label": "Urgency",
                "type": "score",
                "instructions": "Rate urgency.",
                "criteria": ["Low", "High"],
            },
            "followup": {
                "label": "Follow-up",
                "type": "noul",
                "instructions": "Follow-up required?",
            },
        },
    }


def record(profile: dict[str, Any]) -> dict[str, Any]:
    """Make a record whose secondary Choice is uncertain while its primary is not."""
    return {
        "log": "Synthetic record",
        "engine": "laya",
        "primaryQuestion": "area",
        "defaultDecision": profile["defaultDecision"],
        "classificationGroup": "legacy",
        "criteriaGroup": "stable",
        "profileLabel": profile["label"],
        "category": "a",
        "decisionDefinitions": profile["questions"],
        "decisions": {
            "area": {
                "type": "choice",
                "choice": "a",
                "confidence": 0.1,
                "probabilities": {"a": 0.95, "b": 0.05},
            },
            "response": {
                "type": "choice",
                "choice": "done",
                "confidence": 1,
                "probabilities": {"done": 0.52, "pending": 0.48},
            },
            "urgency": {
                "type": "score",
                "score": 0.5,
                "legend": {"0": "Low", "1": "High"},
                "probabilities": {"0": 0.5, "1": 0.5},
            },
            "followup": {"type": "noul", "noul": 0.5},
        },
    }


@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.anyio
async def test_default_changes_do_not_change_inference_or_legacy_projection(
    profile: dict[str, Any],
    engine_name: str,
) -> None:
    requests = []
    sample = record(profile)

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"answers": sample["decisions"], "usage": {"truncated": False}}
        )

    engine = Engine(
        engine_name,
        "https://example.invalid/decision",
        "",
        "english" if engine_name == "laya" else "jev-1.13.0",
        10,
    )
    results = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        for default in ("area", "urgency", "followup"):
            profile["defaultDecision"] = default
            with use_profile_snapshot({"custom": profile}):
                results.append(
                    await classify_log("Synthetic record", engine, client, "custom")
                )
    assert requests[0] == requests[1] == requests[2]
    assert len({result["criteriaGroup"] for result in results}) == 1
    assert len({result["classificationGroup"] for result in results}) == 1
    for result in results:
        assert result["category"] == "a" and result["uncertain"] is False
        assert result["anyUncertain"] is True and result["review"] is True
        assessments = result["decisionAssessments"]
        assert assessments["response"]["uncertain"] is True
        assert assessments["response"]["candidates"] == ["done", "pending"]
        assert assessments["urgency"]["uncertain"] is None
        assert assessments["followup"]["uncertain"] is None


@pytest.mark.parametrize("unknown", ["기타·확인 불가", "custom_unknown"])
def test_review_options_are_explicit_and_separate_from_uncertainty(
    profile: dict[str, Any],
    unknown: str,
) -> None:
    item = record(profile)
    item["decisionDefinitions"]["area"]["criteria"] = {"a": "A", unknown: "No evidence"}
    if unknown == "custom_unknown":
        item["decisionDefinitions"]["area"]["reviewOptions"] = [unknown]
    else:
        item["decisionDefinitions"]["area"].pop("reviewOptions")
    item["decisions"]["area"].update(choice=unknown, probabilities={"a": 0, unknown: 1})
    assessment = decision_assessments(item)["area"]
    assert assessment["uncertain"] is False
    assert assessment["reviewReasons"] == ["other_category"]
    item["decisionDefinitions"]["area"]["reviewOptions"] = []
    assert decision_assessments(item)["area"]["reviewReasons"] == []


def test_integrity_issues_belong_to_the_affected_decision(
    profile: dict[str, Any],
) -> None:
    item = record(profile)
    item["providerResponse"] = {
        "usage": {
            "options": {"area": {"total": 2, "distinct": 1}},
            "criteria_tokens_dropped": {"urgency": 5},
        }
    }
    assessment = decision_assessments(item)
    assert assessment["area"]["reviewReasons"] == ["collapsed_options"]
    assert assessment["area"]["uncertain"] is True
    assert assessment["urgency"] == {
        "uncertain": None,
        "reviewReasons": ["criteria_shortened"],
    }
    assert assessment["followup"]["reviewReasons"] == []
    assert needs_review(item)


def test_missing_old_assessments_are_not_certain(profile: dict[str, Any]) -> None:
    item = record(profile)
    for answer in item["decisions"].values():
        answer.pop("probabilities", None)
    assert decision_assessments(item)["response"]["uncertain"] is None
    assert decision_assessments({"category": "normal"})["category"]["uncertain"] is None
    assert (
        decision_assessments({"category": "normal", "uncertain": False})["category"][
            "uncertain"
        ]
        is False
    )


@pytest.mark.parametrize("default", ["area", "response", "urgency", "followup"])
def test_any_single_existing_decision_can_be_the_default(
    profile: dict[str, Any], default: str
) -> None:
    profile["defaultDecision"] = default
    saved = validate_profiles(
        {"general": DEFAULT_PROFILES["general"], "custom": profile}
    )["custom"]
    assert saved["defaultDecision"] == default
    assert saved["primaryQuestion"] == "area"


@pytest.mark.parametrize("default", [None, [], ["area", "response"], "missing"])
def test_invalid_default_is_rejected(profile: dict[str, Any], default: Any) -> None:
    profile["defaultDecision"] = default
    with pytest.raises(ValueError, match="default chart"):
        validate_profiles({"general": DEFAULT_PROFILES["general"], "custom": profile})


@pytest.mark.parametrize("options", [["missing"], ["a", "a"], "a", [False]])
def test_review_options_are_validated(profile: dict[str, Any], options: Any) -> None:
    profile["questions"]["area"]["reviewOptions"] = options
    with pytest.raises(ValueError, match="Review options"):
        validate_profiles({"general": DEFAULT_PROFILES["general"], "custom": profile})


def test_indexed_filters_and_old_summary_upgrade_preserve_original_payload(
    tmp_path: Path,
    profile: dict[str, Any],
) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    snapshot = {"state": "completed", "settings": {"taskId": "test"}}
    store.create("run", snapshot)
    for index in range(65):
        item = record(profile)
        if index % 3 == 1:
            item["decisions"]["response"]["probabilities"] = {
                "done": 0.95,
                "pending": 0.05,
            }
        elif index % 3 == 2:
            item["decisions"]["response"].pop("probabilities")
        item["log"] = f"row {index}"
        store.append("run", {"type": "result", "result": item}, snapshot)
    summary = store.state("run")["summary"]
    assert (
        summary["decisionGroups"]["stable:response"]["counts"]["uncertain"]["done"]
        == 22
    )
    assert (
        summary["decisionGroups"]["stable:response"]["counts"]["certain"]["done"] == 22
    )
    assert (
        summary["decisionGroups"]["stable:response"]["counts"]["unassessed"]["done"]
        == 21
    )
    assert (
        sum(summary["decisionGroups"]["stable:area"]["counts"]["certain"].values())
        == 65
    )
    assert not any(
        summary["decisionGroups"]["stable:followup"]["counts"]["uncertain"].values()
    )
    filters = {
        "decision": "stable:response",
        "category": "done",
        "certainty": "uncertain",
    }
    page = store.page("run", filters, 10)
    assert len(page["items"]) == 10 and page["hasNext"]
    second = store.page("run", {**filters, "before": page["items"][-1]["sequence"]}, 30)
    assert len(second["items"]) == 12
    assert all(
        row["result"]["decisionAssessments"]["response"]["uncertain"]
        for row in page["items"]
    )
    with store.transaction() as connection:
        payloads = [row[0] for row in connection.execute("SELECT payload FROM events")]
        old = empty_summary()
        old.pop("decisionSummaryVersion")
        connection.execute("UPDATE runs SET summary=?", (json.dumps(old),))
        connection.execute("DELETE FROM result_decisions")
    # A direct page request also upgrades old indexes; no prior state() is required.
    assert len(store.page("run", filters, 30)["items"]) == 22
    assert store.state("run")["summary"]["review"] == 22
    with store.reader() as connection:
        assert [
            row[0] for row in connection.execute("SELECT payload FROM events")
        ] == payloads
    with pytest.raises(ValueError, match="Choice"):
        store.page("run", {"decision": "stable:followup", "certainty": "uncertain"}, 10)
    store.review("run", 1, "", "response", "pending")
    corrected = store.page("run", filters, 30)["items"][-1]["result"]
    assert corrected["decisions"]["response"]["choice"] == "done"
    assert corrected["decisionAssessments"]["response"]["uncertain"]
    store.delete_task("test")
    with store.reader() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM result_decisions").fetchone()[0]
            == 0
        )
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
async def test_profiles_without_choice_are_supported(
    profile: dict[str, Any], engine_name: str
) -> None:
    profile.pop("primaryQuestion")
    profile["questions"] = {
        key: value
        for key, value in profile["questions"].items()
        if value["type"] != "choice"
    }
    profile["defaultDecision"] = "followup"
    saved = validate_profiles(
        {"general": DEFAULT_PROFILES["general"], "custom": profile}
    )["custom"]
    assert "primaryQuestion" not in saved
    sample = record(profile)
    answers = {
        key: value
        for key, value in sample["decisions"].items()
        if key in profile["questions"]
    }
    engine = Engine(
        engine_name,
        "https://example.invalid/decision",
        "",
        "english" if engine_name == "laya" else "jev-1.13.0",
        10,
    )
    with use_profile_snapshot({"custom": saved}):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"answers": answers, "usage": {"truncated": False}}
                )
            )
        ) as client:
            result = await classify_log("Synthetic record", engine, client, "custom")
    assert result["primaryQuestion"] is None and "category" not in result
    assert result["review"] is False and result["anyUncertain"] is False
    assert result["defaultDecision"] == "followup"


def test_primary_uncertainty_does_not_spread_to_another_choice(
    profile: dict[str, Any],
) -> None:
    item = record(profile)
    item["decisions"]["area"]["probabilities"] = {"a": 0.52, "b": 0.48}
    item["decisions"]["response"]["probabilities"] = {"done": 0.95, "pending": 0.05}
    assessments = decision_assessments(item)
    assert assessments["area"]["uncertain"] is True
    assert assessments["response"]["uncertain"] is False
    assert assessments["response"]["reviewReasons"] == []


@pytest.mark.parametrize("engine_name", ["laya", "jev"])
@pytest.mark.anyio
async def test_nonprimary_option_integrity_is_engine_specific(
    profile: dict[str, Any],
    engine_name: str,
) -> None:
    item = record(profile)
    item["decisions"]["response"]["probabilities"] = {"done": 0.95, "pending": 0.05}
    engine = Engine(
        engine_name,
        "https://example.invalid/decision",
        "",
        "english" if engine_name == "laya" else "jev-1.13.0",
        10,
    )
    payload = {
        "answers": item["decisions"],
        "usage": {
            "truncated": False,
            "options": {"response": {"total": 2, "distinct": 1}},
        },
    }
    with use_profile_snapshot({"custom": profile}):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload)
            )
        ) as client:
            result = await classify_log("Synthetic input", engine, client, "custom")
    assert result["uncertain"] is False
    assert result["decisionAssessments"]["response"]["uncertain"] is (
        engine_name == "laya"
    )
    assert result["anyUncertain"] is (engine_name == "laya")


@pytest.mark.anyio
async def test_implicit_and_explicit_review_defaults_share_the_same_chart_identity(
    profile: dict[str, Any],
) -> None:
    item = record(profile)
    profile["questions"]["area"].pop("reviewOptions")
    engine = Engine("laya", "https://example.invalid/decision", "", "english", 10)
    results = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"answers": item["decisions"], "usage": {"truncated": False}}
            )
        )
    ) as client:
        for explicit in [False, True]:
            if explicit:
                profile["questions"]["area"]["reviewOptions"] = []
            with use_profile_snapshot({"custom": profile}):
                results.append(
                    await classify_log("Synthetic input", engine, client, "custom")
                )
    assert results[0]["criteriaGroup"] == results[1]["criteriaGroup"]
