import json
from pathlib import Path

import httpx
import pytest
from conftest import DECISION_ANSWERS
from dotenv import dotenv_values

from classifier import Result, classify_batch, classify_log, parse_logs
from config import get_engine, get_jev_input_bytes, load_startup_settings


def test_example_laya_settings_pass_startup_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = dotenv_values(Path(__file__).resolve().parents[1] / ".env.example")
    for key, value in settings.items():
        if value is not None:
            monkeypatch.setenv(key, value)
    engine = get_engine()
    assert engine.name == "laya"
    assert engine.model == settings["LAYA_MODEL"]
    assert engine.context_tokens == (512 if engine.model == "english" else 8192)
    assert engine.head_tokens == int(settings["LAYA_HEAD_TOKENS"] or "256")


def test_english_rejects_oversized_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", "english")
    monkeypatch.setenv("LAYA_MAX_TOKENS", "8192")
    with pytest.raises(ValueError, match="LAYA_MAX_TOKENS must be between 1 and 512"):
        get_engine()


@pytest.mark.parametrize("value", ["0", "-1", "abc", "", "1.5", "30001"])
def test_invalid_byte_budget(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("JEV_MAX_INPUT_BYTES", value)
    with pytest.raises(ValueError, match="JEV_MAX_INPUT_BYTES"):
        get_jev_input_bytes()


def test_configured_byte_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_MAX_INPUT_BYTES", "20000")
    assert get_jev_input_bytes() == 20000


@pytest.mark.anyio
@pytest.mark.parametrize("log", ["x" * 30000, "😀" * 7500])
async def test_oversized_event_does_not_abort_batch(log: str) -> None:
    calls = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json.loads(request.content)["state"] == "small event"
        return httpx.Response(
            200,
            json={
                "model": "jev-1.13.0",
                "answers": {
                    **DECISION_ANSWERS,
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            "normal": 1,
                            "warning": 0,
                            "error": 0,
                            "security": 0,
                            "other": 0,
                        },
                    },
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(event: str) -> Result:
            return await classify_log(event, get_engine(), client)

        logs = parse_logs(log + "\nsmall event")
        results = dict([row async for row in classify_batch(logs, handle_classify)])
    assert calls == 1
    assert results[0]["log"] == log
    assert results[0]["review"] is False
    assert "preflight" in results[0]["error"]
    assert results[1]["category"] == "normal"


@pytest.mark.anyio
async def test_byte_budget_includes_question_and_exact_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sizes: list[int] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        sizes.append(len(request.content))
        return httpx.Response(429)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="429"):
            await classify_log("x", get_engine(), client)
        size = sizes[0]
        assert size > 1
        monkeypatch.setenv("JEV_MAX_INPUT_BYTES", str(size))
        with pytest.raises(ValueError, match="429"):
            await classify_log("x", get_engine(), client)
        monkeypatch.setenv("JEV_MAX_INPUT_BYTES", str(size - 1))
        with pytest.raises(ValueError, match="preflight"):
            await classify_log("x", get_engine(), client)
    assert len(sizes) == 2


@pytest.mark.parametrize(
    ("name", "model", "context"),
    [
        ("laya", "english", 512),
        ("laya", "typed-decisions", 8192),
        ("laya", "multilingual", 8192),
        ("jev", "jev-latest", None),
    ],
)
def test_model_selection(
    monkeypatch: pytest.MonkeyPatch, name: str, model: str, context: int | None
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", name)
    monkeypatch.setenv(f"{name.upper()}_MODEL", model)
    engine = get_engine()
    assert engine.model == model
    if context is not None:
        assert engine.context_tokens == context


@pytest.mark.parametrize(
    ("name", "model"), [("laya", ""), ("laya", "unknown"), ("jev", "")]
)
def test_invalid_model_selection(
    monkeypatch: pytest.MonkeyPatch, name: str, model: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", name)
    monkeypatch.setenv(f"{name.upper()}_MODEL", model)
    with pytest.raises(ValueError, match=f"{name.upper()}_MODEL"):
        get_engine()


@pytest.mark.anyio
@pytest.mark.parametrize("name", ["laya", "jev"])
@pytest.mark.parametrize("status", [200, 429])
async def test_response_metadata_survives_exportable_results(
    monkeypatch: pytest.MonkeyPatch, name: str, status: int
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", name)
    model = "english" if name == "laya" else "jev-latest"
    monkeypatch.setenv(f"{name.upper()}_MODEL", model)
    response_data = {
        "model": "actual-model",
        "routing": {"model": model, "repo": "checkpoint"},
        "usage": {"truncated": False, "input_tokens": 100},
        "answers": {
            **DECISION_ANSWERS,
            "category": {
                "choice": "normal",
                "confidence": 0.9,
                "answer_confidence": 0.95,
                "action": {"act_probability": 1},
                "probabilities": {
                    "normal": 1,
                    "warning": 0,
                    "error": 0,
                    "security": 0,
                    "other": 0,
                },
            },
        },
    }

    def handle_request(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == model
        if name == "laya":
            assert payload["max_len"] == 512
            assert payload["head_max_len"] == 256
        return httpx.Response(
            status,
            json=response_data,
            headers={
                "x-request-id": "request-123",
                "x-inference-time-ms": "12.5",
                "authorization": "must-not-be-exported",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, get_engine(), client)

        rows = [r async for r in classify_batch(["example"], handle_classify)]
    result = rows[0][1]
    assert result["requestedModel"] == model
    assert result["providerResponse"] == response_data
    assert result["httpStatus"] == status
    assert result["responseHeaders"] == {
        "x-request-id": "request-123",
        "x-inference-time-ms": "12.5",
    }
    assert "criteria" in result["questions"]["category"]
    assert result["requestBytes"] > 0
    assert result["requestedAt"].endswith("+00:00")
    assert ("error" in result) == (status == 429)


@pytest.mark.parametrize(
    ("model", "value"), [("english", "384"), ("multilingual", "512")]
)
@pytest.mark.anyio
async def test_configured_laya_question_budget_reaches_request_and_metadata(
    monkeypatch: pytest.MonkeyPatch, model: str, value: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", model)
    monkeypatch.setenv("LAYA_HEAD_TOKENS", value)

    def handle_request(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["head_max_len"] == int(value)
        return httpx.Response(429)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:

        async def handle_classify(log: str) -> Result:
            return await classify_log(log, get_engine(), client)

        rows = [r async for r in classify_batch(["example"], handle_classify)]
    assert rows[0][1]["inputBudget"]["head_max_len"] == int(value)


@pytest.mark.parametrize("value", ["0", "-1", "", "abc", "1.5", "512", "8192"])
def test_invalid_english_question_budget(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", "english")
    monkeypatch.setenv("LAYA_HEAD_TOKENS", value)
    with pytest.raises(ValueError, match="LAYA_HEAD_TOKENS"):
        get_engine()


def test_jev_ignores_laya_question_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "jev")
    monkeypatch.setenv("LAYA_HEAD_TOKENS", "invalid-unused-value")
    assert get_engine().name == "jev"


@pytest.mark.parametrize("value", ["0", "-1", "abc", "1.5", "8193"])
def test_invalid_laya_total_budget(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MAX_TOKENS", value)
    with pytest.raises(ValueError, match="LAYA_MAX_TOKENS"):
        get_engine()


def test_total_budget_must_leave_question_room(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MAX_TOKENS", "256")
    with pytest.raises(ValueError, match="LAYA_HEAD_TOKENS"):
        get_engine()


@pytest.mark.anyio
@pytest.mark.parametrize("model", ["multilingual", "log-specialist"])
async def test_explicit_total_budget_and_custom_model_reach_provider(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", model)
    monkeypatch.setenv("LAYA_MAX_TOKENS", "1024")

    def handle_request(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == model
        assert payload["max_len"] == 1024
        assert payload["head_max_len"] == 256
        return httpx.Response(422)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        with pytest.raises(ValueError, match="422"):
            await classify_log("original text", get_engine(), client)


@pytest.mark.parametrize("model", ["../model", "https://hub/model", "a b"])
def test_custom_model_must_be_a_registered_name(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", model)
    monkeypatch.setenv("LAYA_MAX_TOKENS", "1024")
    with pytest.raises(ValueError, match="LAYA_MODEL"):
        get_engine()


def test_jev_ignores_invalid_laya_total_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAYA_MAX_TOKENS", "invalid")
    assert get_engine().context_tokens == 32000


@pytest.mark.anyio
@pytest.mark.parametrize("routing", [{}, {"model": "english"}, {"model": "logs"}])
async def test_custom_model_requires_server_routing_confirmation(
    monkeypatch: pytest.MonkeyPatch, routing: Result
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_MODEL", "logs")
    monkeypatch.setenv("LAYA_MAX_TOKENS", "1024")
    data = {
        "routing": routing,
        "usage": {"truncated": False},
        "answers": {
            **DECISION_ANSWERS,
            "category": {
                "choice": "normal",
                "confidence": 1,
                "probabilities": {
                    "normal": 1,
                    "warning": 0,
                    "error": 0,
                    "security": 0,
                    "other": 0,
                },
            },
        },
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        if routing.get("model") == "logs":
            result = await classify_log("example", get_engine(), client)
            assert result["requestedModel"] == "logs"
        else:
            with pytest.raises(ValueError, match="confirm.*custom model"):
                await classify_log("example", get_engine(), client)


@pytest.mark.parametrize("selected", ["laya", "jev"])
def test_restart_reloads_mounted_engine_settings_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selected: str
) -> None:
    """Docker's stale engine values yield to .env; container paths remain fixed."""
    path = tmp_path / ".env"
    settings = {
        "DECISION_ENGINE": selected,
        "LAYA_API_URL": "http://laya:8000/v1/systemone",
        "LAYA_MODEL": "multilingual",
        "LAYA_API_KEY": "test-laya-new",
        "LAYA_MAX_TOKENS": "8192",
        "LAYA_HEAD_TOKENS": "256",
        "LAYA_CONCURRENCY": "2",
        "JEV_MODEL": "jev-latest",
        "JEV_API_KEY": "test-jev-new",
        "JEV_CONCURRENCY": "3",
        "JEV_MAX_INPUT_BYTES": "20000",
    }
    for key in settings:
        monkeypatch.setenv(key, "old")
    monkeypatch.setenv("PORT", "4000")
    monkeypatch.setenv("DECIFLOW_DATA_DIR", "/mounted-data")
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in settings.items())
        + "\nPORT=9999\nDECIFLOW_DATA_DIR=/other-data\n"
    )
    load_startup_settings(path)
    engine = get_engine()
    assert engine.name == selected
    assert engine.api_key == settings[f"{selected.upper()}_API_KEY"]
    assert engine.model == settings[f"{selected.upper()}_MODEL"]
    assert engine.concurrency == int(settings[f"{selected.upper()}_CONCURRENCY"])
    import os

    assert os.environ["PORT"] == "4000"
    assert os.environ["DECIFLOW_DATA_DIR"] == "/mounted-data"
    path.unlink()
    load_startup_settings(path)
    assert get_engine() == engine
