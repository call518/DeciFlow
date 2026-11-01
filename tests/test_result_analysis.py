"""Analyze canonical saved evidence only on demand, using a separate OpenAI model."""

import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from deciflow import result_analysis, server
from deciflow.profiles import GENERAL_PROFILE_ID, PROFILES
from deciflow.result_store import open_result_store

RUN = "a" * 32


@pytest.fixture
def saved_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    profile = deepcopy(PROFILES[GENERAL_PROFILE_ID])
    profile["instructions"] = "Frozen execution instructions."
    snapshot = {
        "jobId": RUN,
        "state": "completed",
        "settings": {
            "profileSnapshot": {GENERAL_PROFILE_ID: profile},
            "mode": "batch",
        },
    }
    item = {
        "input": "application: service started normally",
        "decisionInput": "service started normally",
        "profileId": GENERAL_PROFILE_ID,
        "decisionDefinitions": {"category": profile["questions"]["category"]},
        "decisions": {
            "category": {
                "type": "choice",
                "choice": "normal",
                "probabilities": {
                    "normal": 1,
                    "warning": 0,
                    "error": 0,
                    "security": 0,
                    "other": 0,
                },
            }
        },
        "engine": "laya",
        "model": "multilingual",
        "elapsedMs": 1,
        "providerResponse": {"usage": {"truncated": True}},
    }
    store = open_result_store(tmp_path)
    store.create(RUN, snapshot)
    store.append(RUN, {"type": "result", "index": 0, "result": item}, snapshot)
    return store, snapshot, item


@pytest.mark.parametrize(
    "key,model,available",
    [
        ("", "", False),
        ("key", "", False),
        ("", "analysis-model", False),
        ("key", "analysis-model", True),
        (" ", "model", False),
    ],
)
def test_availability_requires_both_environment_values(
    monkeypatch, key, model, available
):
    monkeypatch.setenv("OPENAI_API_KEY", key)
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", model)
    monkeypatch.setenv("OPENAI_CRITERIA_MODEL", "criteria-model")
    config = result_analysis.analysis_configuration()
    assert config == {"available": available, "model": model.strip()}


@pytest.mark.anyio
async def test_preview_uses_frozen_criteria_without_inference(
    saved_result, monkeypatch
):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "")

    async def forbidden(*args):
        pytest.fail("Preview must not call OpenAI")

    monkeypatch.setattr(server, "analyze_result", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        response = await client.post(f"/api/jobs/{RUN}/analysis", json={"sequence": 1})
        assert response.status_code == 200
        data = response.json()
        assert data["configuration"]["available"] is False
        assert (
            data["context"]["criteria"]["instructions"]
            == "Frozen execution instructions."
        )
        assert data["context"]["input"] == saved_result[2]["input"]
        assert data["context"]["decisionInput"] == "service started normally"
        assert data["context"]["usage"]["truncated"] is True
        assert (await client.get("/analysis.html")).status_code == 200
        assert (await client.get("/analysis.js")).status_code == 200


@pytest.mark.anyio
async def test_generation_uses_dedicated_model_and_never_changes_results(
    saved_result, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "private-key")
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "analysis-model")
    monkeypatch.setenv("OPENAI_CRITERIA_MODEL", "criteria-model")
    original_client = httpx.AsyncClient
    sent = []

    def provider(request):
        body = json.loads(request.content)
        sent.append(body)
        assert body["model"] == "analysis-model" and body["store"] is False
        assert request.headers["Authorization"] == "Bearer private-key"
        assert (
            json.loads(body["input"])["criteria"]["instructions"]
            == "Frozen execution instructions."
        )
        assert "internal reasoning" in body["instructions"]
        assert "Write in Korean" in body["instructions"]
        assert "'판정 결과'" in body["instructions"]
        assert "'AI 검토 의견'" in body["instructions"]
        assert "without mixing in recommendations" in body["instructions"]
        assert "do not create a new decision" in body["instructions"]
        return httpx.Response(
            200,
            headers={"x-request-id": "req-test", "set-cookie": "private-cookie"},
            json={
                "status": "completed",
                "model": "actual-analysis-model",
                "id": "resp-test",
                "created_at": 1_700_000_000,
                "service_tier": "default",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 20},
                },
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Evidence supports normal."}
                        ],
                    }
                ],
            },
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(provider), **kwargs
        ),
    )
    before = saved_result[0].events(RUN)
    async with original_client(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        response = await client.post(
            f"/api/jobs/{RUN}/analysis",
            json={"sequence": 1, "generate": True, "language": "ko"},
        )
    assert response.status_code == 200
    assert response.json()["analysis"] == "Evidence supports normal."
    metadata = response.json()["metadata"]
    assert metadata["model"] == "actual-analysis-model"
    assert metadata["requestedModel"] == "analysis-model"
    assert metadata["responseId"] == "resp-test"
    assert metadata["requestId"] == "req-test"
    assert metadata["createdAt"] == 1_700_000_000
    assert metadata["serviceTier"] == "default"
    assert metadata["elapsedMs"] >= 0
    assert metadata["usage"]["total_tokens"] == 150
    assert metadata["usage"]["input_tokens_details"]["cached_tokens"] == 0
    assert "private-cookie" not in response.text
    assert "private-key" not in response.text
    assert len(sent) == 1
    assert saved_result[0].events(RUN) == before


@pytest.mark.anyio
async def test_origin_missing_result_and_invalid_requests_never_call_provider(
    saved_result, monkeypatch
):
    async def forbidden(*args):
        pytest.fail("Invalid request must not call OpenAI")

    monkeypatch.setattr(server, "analyze_result", forbidden)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        assert (
            await client.post(f"/api/jobs/{RUN}/analysis", json={"sequence": 1})
        ).status_code == 403
        client.headers["Origin"] = "http://test"
        assert (
            await client.post(
                f"/api/jobs/{RUN}/analysis", json={"sequence": 99, "generate": True}
            )
        ).status_code == 404
        for body in (
            {"sequence": True},
            {"sequence": 1, "generate": "yes"},
            {"sequence": 1, "language": "unknown"},
        ):
            assert (
                await client.post(f"/api/jobs/{RUN}/analysis", json=body)
            ).status_code == 400
        assert (
            await client.post(f"/api/jobs/{RUN}/analysis", content="x" * 4097)
        ).status_code == 400


def test_failed_or_oversized_input_is_not_analyzed(saved_result):
    _, snapshot, result = saved_result
    with pytest.raises(ValueError, match="completed decision"):
        result_analysis.analysis_context({**result, "error": "failed"}, snapshot)
    with pytest.raises(ValueError, match="nothing was sent"):
        result_analysis.analysis_context({**result, "input": "x" * 200_001}, snapshot)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "status,payload",
    [
        (401, {"error": "private provider body"}),
        (200, {"status": "incomplete", "output": []}),
        (200, {"status": "completed", "output": []}),
    ],
)
async def test_provider_failure_is_not_exposed(
    saved_result, monkeypatch, status, payload
):
    monkeypatch.setenv("OPENAI_API_KEY", "private-key")
    monkeypatch.setenv("OPENAI_ANALYSIS_MODEL", "analysis-model")
    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client_class(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, json=payload)
            ),
            **kwargs,
        ),
    )
    async with client_class(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://test",
        headers={"Origin": "http://test"},
    ) as client:
        response = await client.post(
            f"/api/jobs/{RUN}/analysis", json={"sequence": 1, "generate": True}
        )
    assert response.status_code == 400
    assert (
        "private provider body" not in response.text
        and "private-key" not in response.text
    )


def test_unset_analysis_model_uses_dedicated_default(monkeypatch):
    monkeypatch.delenv("OPENAI_ANALYSIS_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_CRITERIA_MODEL", "different-criteria-model")
    assert result_analysis.analysis_configuration() == {
        "available": True,
        "model": "gpt-5.6-terra",
    }
