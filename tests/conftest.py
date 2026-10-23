from pathlib import Path
from typing import Any

import pytest

from deciflow.profiles import DEFAULT_PROFILES

URGENCY_CRITERIA = DEFAULT_PROFILES["4e6d5417-611e-49e0-8e23-2444a0f49ee4"][
    "questions"
]["urgency"]["criteria"]

DECISION_ANSWERS: dict[str, Any] = {
    "urgency": {
        "type": "score",
        "score": 2.0,
        "legend": {str(i): text for i, text in enumerate(URGENCY_CRITERIA)},
        "probabilities": {"0": 0.0, "1": 0.0, "2": 1.0, "3": 0.0},
    },
    "ticket": {"type": "noul", "noul": 0.9},
}


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on the application's asyncio runtime."""
    return "asyncio"


@pytest.fixture(autouse=True)
def engine_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep provider tests independent of developer secrets and shell settings."""
    from deciflow import server
    monkeypatch.setattr(server.app.state, "reset_requested", False, raising=False)
    monkeypatch.setattr(server.app.state, "restart_requested", False, raising=False)
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DECIFLOW_LOG_DIR", "")
    monkeypatch.delenv("DECIFLOW_CSRF_TRUSTED_ORIGINS", raising=False)
    monkeypatch.setenv("DECISION_ENGINE", "jev")
    monkeypatch.setenv("JEV_API_KEY", "test-key")
    monkeypatch.delenv("LAYA_API_KEY", raising=False)
    monkeypatch.delenv("LAYA_API_URL", raising=False)
    monkeypatch.delenv("JEV_MAX_INPUT_BYTES", raising=False)
    monkeypatch.delenv("LAYA_CONCURRENCY", raising=False)
    monkeypatch.delenv("JEV_CONCURRENCY", raising=False)

    monkeypatch.delenv("LAYA_MODEL", raising=False)
    monkeypatch.delenv("JEV_MODEL", raising=False)
    monkeypatch.delenv("LAYA_HEAD_TOKENS", raising=False)
    monkeypatch.delenv("LAYA_MAX_TOKENS", raising=False)
