from collections.abc import AsyncGenerator

import anyio
import pytest

from deciflow import server
from deciflow.classifier import Result, classify_batch, classify_stream
from deciflow.config import get_engine


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("value", ["0", "-1", "abc", "", "1.5"])
def test_invalid_concurrency(
    monkeypatch: pytest.MonkeyPatch, engine: str, value: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv(f"{engine.upper()}_CONCURRENCY", value)
    with pytest.raises(ValueError, match=f"{engine.upper()}_CONCURRENCY"):
        get_engine()


@pytest.mark.parametrize("engine", ["laya", "jev"])
def test_selected_engine_concurrency(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    assert get_engine().concurrency == 4
    monkeypatch.setenv(f"{engine.upper()}_CONCURRENCY", "2")
    other = "jev" if engine == "laya" else "laya"
    monkeypatch.setenv(f"{other.upper()}_CONCURRENCY", "invalid")
    assert get_engine().concurrency == 2


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["batch", "stream"])
@pytest.mark.parametrize("concurrency", [1, 2, 6])
async def test_worker_limit(mode: str, concurrency: int) -> None:
    active = peak = 0

    async def handle_classify(log: str) -> Result:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await anyio.sleep(0.01)
        active -= 1
        return {"category": "normal"}

    async def records() -> AsyncGenerator[Result, None]:
        for index in range(9):
            yield {"log": str(index)}

    if mode == "batch":
        results = classify_batch(
            [str(index) for index in range(9)], handle_classify, concurrency
        )
    else:
        results = classify_stream(records(), handle_classify, concurrency)
    rows = [row async for row in results]
    assert len(rows) == 9
    assert peak == concurrency


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_server_uses_engine_concurrency(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv(f"{engine.upper()}_CONCURRENCY", "2")
    active = peak = 0

    async def handle_classify(*args: object) -> Result:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await anyio.sleep(0.01)
        active -= 1
        return {"category": "normal"}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    events = [event async for event in server.handle_events(["log"] * 6, get_engine())]
    assert len(events) == 8
    assert peak == 2
