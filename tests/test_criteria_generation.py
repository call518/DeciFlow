"""Verify generation boundaries, lossless mapping, and normal Criteria persistence."""

import json
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import pytest

import criteria_generation as generation
import server
from config_store import load_records
from profiles import PROFILES
from source_registry import save_sources


@pytest.fixture
def generated() -> dict[str, Any]:
    return {
        "label": "Generated consultation",
        "instructions": "Use explicit evidence at the end of the conversation.",
        "primaryQuestion": "status",
        "decisions": [
            {
                "id": "status",
                "label": "Status",
                "type": "choice",
                "instructions": "Choose the final status.",
                "summary": True,
                "options": [
                    {"id": "complete", "definition": "All work is finished."},
                    {"id": "unknown", "definition": "Evidence is insufficient."},
                ],
            },
            {
                "id": "urgency",
                "label": "Urgency",
                "type": "score",
                "instructions": "Rate explicit urgency.",
                "summary": False,
                "levels": ["Routine", "Immediate harm"],
            },
            {
                "id": "follow_up",
                "label": "Follow-up",
                "type": "noul",
                "instructions": "Does staff owe a callback?",
                "summary": True,
            },
        ],
    }


@pytest.fixture(autouse=True)
def restore_profiles() -> Iterator[None]:
    original = deepcopy(PROFILES)
    yield
    PROFILES.clear()
    PROFILES.update(original)


def test_all_fields_are_preserved(generated: dict[str, Any]) -> None:
    profile = generation.convert_generated_profile(generated)
    assert list(profile["questions"]) == ["status", "urgency", "follow_up"]
    assert profile["primaryQuestion"] == "status"
    for decision, question in zip(
        generated["decisions"], profile["questions"].values()
    ):
        for key in ("label", "instructions", "type", "summary"):
            assert question[key] == decision[key]
    assert profile["questions"]["status"]["criteria"] == {
        item["id"]: item["definition"] for item in generated["decisions"][0]["options"]
    }
    assert profile["questions"]["urgency"]["criteria"] == ["Routine", "Immediate harm"]
    assert "criteria" not in profile["questions"]["follow_up"]


@pytest.mark.parametrize(
    "invalid",
    [
        "duplicate_decision",
        "duplicate_option",
        "missing",
        "unknown",
        "primary",
        "score",
        "summary",
    ],
)
def test_invalid_generation_is_rejected(
    generated: dict[str, Any], invalid: str
) -> None:
    if invalid == "duplicate_decision":
        generated["decisions"].append(deepcopy(generated["decisions"][0]))
    elif invalid == "duplicate_option":
        options = generated["decisions"][0]["options"]
        options.append(deepcopy(options[0]))
    elif invalid == "missing":
        del generated["decisions"][0]["summary"]
    elif invalid == "unknown":
        generated["extra"] = "must not silently disappear"
    elif invalid == "primary":
        generated["primaryQuestion"] = "urgency"
    elif invalid == "score":
        generated["decisions"][1]["levels"] = ["Only one"]
    else:
        generated["decisions"][0]["summary"] = "yes"
    with pytest.raises((ValueError, TypeError)):
        generation.convert_generated_profile(generated)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("mode", ["automatic", "manual"])
@pytest.mark.parametrize("model", [None, "gpt-5.4"])
async def test_generate_then_save_and_reload(
    monkeypatch: pytest.MonkeyPatch,
    generated: dict[str, Any],
    engine: str,
    mode: str,
    model: str | None,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    if model is None:
        monkeypatch.delenv("OPENAI_CRITERIA_MODEL", raising=False)
    else:
        monkeypatch.setenv("OPENAI_CRITERIA_MODEL", model)
    original_client = httpx.AsyncClient
    calls = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer private-test-key"
        assert body["model"] == (model or "gpt-5.6-terra")
        assert body["store"] is False
        assert body["text"]["format"]["strict"] is True
        assert json.loads(body["input"]) == {
            "purposeMode": mode,
            "purpose": "Evaluate follow-up" if mode == "manual" else "",
            "samples": ["A callback is owed."],
        }
        assert engine.capitalize() in body["instructions"]
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "analysisPurpose": "Evaluate follow-up",
                                        "profile": generated,
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    async with original_client(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        monkeypatch.setattr(
            generation.httpx,
            "AsyncClient",
            lambda **kw: original_client(
                transport=httpx.MockTransport(handle_request), **kw
            ),
        )
        response = await client.post(
            "/api/criteria/generate",
            headers={"Origin": "http://localhost"},
            json={
                "purposeMode": mode,
                "purpose": "Evaluate follow-up",
                "samples": ["A callback is owed."],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["analysisPurpose"] == "Evaluate follow-up"
        assert len(calls) == 1
        assert "private-test-key" not in response.text
        assert "generated" not in PROFILES
        values = deepcopy(PROFILES)
        values["generated"] = response.json()["profile"]
        saved = await client.put(
            "/api/criteria", headers={"Origin": "http://localhost"}, json=values
        )
        assert saved.status_code == 200
        assert load_records("criteria")["generated"] == response.json()["profile"]
        loaded = await client.post(
            "/api/criteria", headers={"Origin": "http://localhost"}
        )
        assert loaded.json()["profiles"]["generated"] == response.json()["profile"]


@pytest.mark.anyio
async def test_source_preview_respects_content_field(tmp_path: Path) -> None:
    path = tmp_path / "source.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"body": f"sample {i}", "private": "excluded"})
            for i in range(12)
        )
    )
    source = save_sources(
        [
            {
                "id": "a" * 32,
                "name": "Sample",
                "type": "local",
                "path": str(path),
                "format": "jsonl",
                "contentField": "body",
            }
        ]
    )[0]
    samples = await generation.preview_samples({"sourceId": source["id"]})
    assert samples == [f"sample {i}" for i in range(8)]


@pytest.mark.anyio
async def test_generation_trust_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        for endpoint in ("generate", "samples"):
            response = await client.post(f"/api/criteria/{endpoint}", json={})
            assert response.status_code == 403
        for body in (
            {},
            [],
            {"purpose": "x", "samples": ["x" * 24001]},
            {"purpose": "x", "samples": ["sample"]},
        ):
            response = await client.post(
                "/api/criteria/generate",
                headers={"Origin": "http://localhost"},
                json=body,
            )
            assert response.status_code == 400
        assert not load_records("criteria")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"status": "incomplete", "output": []},
        {
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "refusal", "refusal": "No"}]}
            ],
        },
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": '{"label":"one","label":"two"}'}
                    ],
                }
            ],
        },
        {"status": "completed", "output": [None]},
        {"status": "completed", "output": [{"type": "message", "content": None}]},
    ],
)
async def test_bad_provider_response_never_changes_profiles(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    original = deepcopy(PROFILES)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        generation.httpx,
        "AsyncClient",
        lambda **kw: original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload)
            ),
            **kw,
        ),
    )
    with pytest.raises((TypeError, ValueError)):
        await generation.generate_criteria(
            {"purpose": "Classify", "samples": ["sample"]}
        )
    assert PROFILES == original
    assert not load_records("criteria")


@pytest.mark.anyio
async def test_ssh_preview_closes_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    closed = []
    monkeypatch.setattr(
        generation, "parse_source_settings", lambda values: [{"type": "ssh"}]
    )

    async def read_remote(spec: dict[str, Any]) -> Any:
        try:
            for i in range(20):
                yield {"log": f"remote {i}"}
        finally:
            closed.append(True)

    monkeypatch.setattr(generation, "read_remote", read_remote)
    assert await generation.preview_samples({"sourceId": "registered"}) == [
        f"remote {i}" for i in range(8)
    ]
    assert closed == [True]


def test_openai_settings_reload_without_exposing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from config import load_startup_settings

    monkeypatch.setenv("OPENAI_API_KEY", "old-test-key")
    monkeypatch.setenv("OPENAI_CRITERIA_MODEL", "old-model")
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=new-test-key\nOPENAI_CRITERIA_MODEL=gpt-4.1\n")
    load_startup_settings(path)
    assert os.environ["OPENAI_API_KEY"] == "new-test-key"
    assert os.environ["OPENAI_CRITERIA_MODEL"] == "gpt-4.1"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        {"purposeMode": "manual"},
        {"purposeMode": "manual", "purpose": "   "},
        {"purposeMode": "manual", "purpose": "x" * 4001},
        {"purposeMode": "unsupported"},
    ],
)
async def test_invalid_purpose_mode_or_manual_input(body: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        await generation.generate_criteria({**body, "samples": ["sample"]})


@pytest.mark.anyio
@pytest.mark.parametrize("purpose", [None, "", " " * 5, "x" * 4001])
async def test_generated_purpose_is_required(
    monkeypatch: pytest.MonkeyPatch, generated: dict[str, Any], purpose: object
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    original_client = httpx.AsyncClient
    payload = {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(
                            {"analysisPurpose": purpose, "profile": generated}
                        ),
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(
        generation.httpx,
        "AsyncClient",
        lambda **kw: original_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=payload)
            ),
            **kw,
        ),
    )
    with pytest.raises(ValueError, match="analysis purpose"):
        await generation.generate_criteria({"samples": ["sample"]})
