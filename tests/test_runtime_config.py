"""Verify safe runtime settings, atomic saves, and per-execution isolation."""

import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from deciflow import server
from deciflow.app_settings import load_settings, save_settings
from deciflow.config import get_engine, get_model
from deciflow.runtime_config import configuration_description, effective_values


def test_overrides_persist_and_engine_budgets_are_frozen() -> None:
    save_settings(
        {
            "resultsPerPage": 30,
            "runtimeOverrides": {
                "DECISION_ENGINE": "laya",
                "LAYA_MODEL": "english",
                "LAYA_HEAD_TOKENS": "192",
                "LAYA_CONCURRENCY": "2",
            },
        }
    )
    first = get_engine()
    assert first.context_tokens == 512 and first.head_tokens == 192
    assert first.concurrency == 2
    save_settings(
        {
            "resultsPerPage": 50,
            "runtimeOverrides": {
                "DECISION_ENGINE": "jev",
                "JEV_MAX_INPUT_BYTES": "12000",
            },
        }
    )
    second = get_engine()
    assert second.name == "jev" and second.input_bytes == 12000
    save_settings({"resultsPerPage": 10, "runtimeOverrides": {}})
    assert first.context_tokens == 512 and first.head_tokens == 192
    assert second.input_bytes == 12000
    assert load_settings()["runtimeOverrides"] == {}
    assert effective_values()["DECISION_ENGINE"] == "jev"


@pytest.mark.parametrize(
    "overrides",
    [
        {"JEV_API_KEY": "do-not-store"},
        {"PORT": "5000"},
        {"DECISION_ENGINE": "other"},
        {"LAYA_MODEL": "english", "LAYA_HEAD_TOKENS": "512"},
        {"LAYA_API_URL": "https://user:password@example.invalid/v1/systemone"},
        {"JEV_CONCURRENCY": "0"},
        {"JEV_MAX_INPUT_BYTES": "30001"},
        {"OPENAI_CRITERIA_MODEL": ""},
        {"LAYA_HEAD_TOKENS": True},
    ],
)
def test_invalid_settings_never_partially_save(overrides: dict[str, Any]) -> None:
    before = load_settings()
    with pytest.raises(ValueError):
        save_settings({"resultsPerPage": 100, "runtimeOverrides": overrides})
    assert load_settings() == before


def test_missing_paid_key_blocks_explicit_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    with pytest.raises(ValueError, match="JEV_API_KEY"):
        save_settings(
            {"resultsPerPage": 30, "runtimeOverrides": {"DECISION_ENGINE": "jev"}}
        )


def test_legacy_page_size_save_preserves_runtime_overrides() -> None:
    save_settings(
        {"resultsPerPage": 30, "runtimeOverrides": {"JEV_MODEL": "jev-preview"}}
    )
    save_settings({"resultsPerPage": 10})
    assert get_engine().model == "jev-preview"


@pytest.mark.anyio
async def test_configuration_api_requires_origin_and_never_returns_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "private-synthetic-value")
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    monkeypatch.setattr(server.app.state, "restart_requested", False, raising=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/configuration")).status_code == 403
        client.headers["Origin"] = "http://localhost"
        response = await client.post("/api/configuration")
        assert response.status_code == 200
        assert "private-synthetic-value" not in response.text
        assert response.json()["credentials"]["OPENAI_API_KEY"] is True
        response = await client.put(
            "/api/configuration",
            json={
                "resultsPerPage": 50,
                "runtimeOverrides": {"DECISION_ENGINE": "laya"},
            },
        )
        assert response.status_code == 200
        assert get_engine().name == "laya"
        assert (
            next(
                field
                for field in response.json()["fields"]
                if field["key"] == "DECISION_ENGINE"
            )["source"]
            == "UI Override"
        )
        monkeypatch.setattr(server.app.state, "restart_requested", True)
        assert (await client.put("/api/configuration", json={})).status_code == 409


def test_reference_help_is_from_template_and_contains_no_secret_values() -> None:
    fields = configuration_description()["fields"]
    model = next(field for field in fields if field["key"] == "LAYA_MODEL")
    assert "multilingual" in model["reference"]
    assert "100+ languages" in model["reference"]


@pytest.mark.anyio
async def test_restart_requires_confirmation_and_conflicts_with_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    monkeypatch.setattr(server.app.state, "restart_requested", False, raising=False)
    calls = []

    async def shutdown() -> None:
        calls.append(True)

    monkeypatch.setattr(server, "handle_reset_shutdown", shutdown)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/restart", json={})).status_code == 403
        client.headers["Origin"] = "http://localhost"
        assert (await client.post("/api/restart", json={})).status_code == 400
        assert not calls
        response = await client.post(
            "/api/restart", json={"confirmation": "RESTART DECIFLOW"}
        )
        assert response.status_code == 202 and calls == [True]
        assert (await client.post("/api/restart", json={})).status_code == 409
        assert (
            await client.post("/api/reset", json={"confirmation": "RESET DECIFLOW"})
        ).status_code == 409


@pytest.mark.anyio
async def test_restart_preserves_data_and_suspends_instead_of_stopping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    marker = root / "keep"
    marker.write_text("preserve")
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(root))
    calls = []

    async def initialize() -> None:
        server.load_actions()

    class ActiveJob:
        task: Any = type("Task", (), {"done": lambda self: False})()

        async def suspend(self) -> None:
            calls.append("suspend")

        async def stop(self) -> None:
            raise AssertionError("Restart must preserve recoverable runs")

    monkeypatch.setattr(server, "initialize_default_action", initialize)
    monkeypatch.setattr(server, "restart_process", lambda: calls.append("restart"))
    async with server.lifespan(server.app):
        await asyncio.sleep(0.03)
        server.JOBS["synthetic"] = ActiveJob()  # type: ignore[assignment]
        server.app.state.restart_requested = True
    assert calls == ["suspend", "restart"] and marker.read_text() == "preserve"


def test_ui_model_override_does_not_change_separate_laya_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LAYA_MODEL", "multilingual")
    save_settings(
        {
            "resultsPerPage": 30,
            "runtimeOverrides": {
                "DECISION_ENGINE": "laya",
                "LAYA_MODEL": "english",
                "LAYA_HEAD_TOKENS": "192",
            },
        }
    )
    assert get_engine().model == "english"
    assert get_model("laya") == "multilingual"
