"""Use typed profiles and result metadata without compatibility projections."""

from copy import deepcopy
from uuid import UUID

import httpx
import pytest

from deciflow.classifier import classify_log
from deciflow.config import get_engine
from deciflow.profiles import DEFAULT_PROFILES, SAMPLE_PROFILE_IDS, validate_profiles
from deciflow.result_payload import compact_result


def test_all_templates_use_one_profile_format() -> None:
    assert len(SAMPLE_PROFILE_IDS) == len(set(SAMPLE_PROFILE_IDS.values())) == 8
    assert set(DEFAULT_PROFILES) == set(SAMPLE_PROFILE_IDS.values())
    assert all(
        str(UUID(identity)) == identity and UUID(identity).version == 4
        for identity in DEFAULT_PROFILES
    )
    assert validate_profiles(DEFAULT_PROFILES) == DEFAULT_PROFILES
    for profile in DEFAULT_PROFILES.values():
        assert "criteria" not in profile and "primaryQuestion" not in profile
        assert profile["defaultDecision"] in profile["questions"]
        for definition in profile["questions"].values():
            assert "summary" not in definition
            if definition["type"] == "choice":
                assert isinstance(definition["reviewOptions"], list)


@pytest.mark.parametrize(
    "identity",
    [
        "general",
        "local_gov",
        "4E6D5417-611E-49E0-8E23-2444A0F49EE4",
        "4e6d5417611e49e08e232444a0f49ee4",
    ],
)
def test_criteria_ids_require_canonical_uuids(identity: str) -> None:
    with pytest.raises(ValueError, match="Criteria IDs"):
        validate_profiles({identity: next(iter(DEFAULT_PROFILES.values()))})


def test_flat_profiles_are_not_supported() -> None:
    with pytest.raises(ValueError, match="at least one decision"):
        validate_profiles(
            {
                "a9b5cb3b-1e1e-4559-8f71-365c651d176d": {
                    "label": "Custom",
                    "instructions": "Use evidence.",
                    "criteria": {"a": "A", "b": "B"},
                }
            }
        )


def test_compaction_preserves_original_response_and_input() -> None:
    result = {
        "decisionDefinitions": {"needed": {"type": "noul"}},
        "providerResponse": {"diagnostic": "Original response"},
        "log": "Original input",
        "error": "Keep failure diagnostics",
    }
    before = deepcopy(result)
    assert compact_result(result) == before
    assert result == before


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_every_decision_receives_shared_instructions(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    from conftest import DECISION_ANSWERS

    monkeypatch.setenv("DECISION_ENGINE", engine)
    profile = DEFAULT_PROFILES["4e6d5417-611e-49e0-8e23-2444a0f49ee4"]
    body = {
        "usage": {"truncated": False},
        "answers": {
            **DECISION_ANSWERS,
            "category": {
                "type": "choice",
                "choice": "normal",
                "confidence": 1,
                "probabilities": {
                    key: int(key == "normal")
                    for key in profile["questions"]["category"]["criteria"]
                },
            },
        },
    }

    def handle(request: httpx.Request) -> httpx.Response:
        import json

        for identity, question in json.loads(request.content)["questions"].items():
            assert profile["instructions"] in question["instructions"]
            assert (
                profile["questions"][identity]["instructions"]
                in question["instructions"]
            )
            assert "summary" not in question
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await classify_log("input", get_engine(), client)
    assert result["providerResponse"] == body
    assert result["decisions"] == body["answers"]
    assert not {
        "summary",
        "primaryQuestion",
        "category",
        "confidence",
        "probabilities",
        "decisionReviews",
        "classificationGroup",
        "categoryFilter",
        "urgency",
        "ticketProbability",
    }.intersection(result)
