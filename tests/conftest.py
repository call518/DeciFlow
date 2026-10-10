import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on the application's asyncio runtime."""
    return "asyncio"


@pytest.fixture(autouse=True)
def engine_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provider tests independent of developer secrets and shell settings."""
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
