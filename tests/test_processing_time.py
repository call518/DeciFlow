"""Regression checks for non-overlapping active request time."""

import asyncio
import json
from collections.abc import AsyncGenerator

import pytest

from deciflow import server
from deciflow.classifier import Result


def test_processing_clock_excludes_idle_and_counts_overlap_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 0.0
    monkeypatch.setattr(server, "perf_counter", lambda: now)
    clock = server._ProcessingClock()
    now = 2.0
    assert clock.snapshot() == {"elapsedMs": 2000, "activeProcessingMs": 0}
    clock.begin()
    now = 3.0
    clock.begin()
    now = 4.0
    clock.end()
    now = 5.0
    assert clock.snapshot()["activeProcessingMs"] == 3000
    clock.end()
    now = 8.0
    assert clock.snapshot() == {"elapsedMs": 8000, "activeProcessingMs": 3000}
    clock.begin()
    now = 9.0
    clock.end()
    assert clock.snapshot() == {"elapsedMs": 9000, "activeProcessingMs": 4000}


@pytest.mark.anyio
async def test_timing_heartbeat_keeps_pending_read_and_cancels_on_close() -> None:
    cancelled = asyncio.Event()

    async def handle_wait() -> AsyncGenerator[tuple[int, Result], None]:
        try:
            await asyncio.Event().wait()
            yield 0, {}
        finally:
            cancelled.set()

    records = handle_wait()
    clock = server._ProcessingClock()
    events = server._timed_results(records, clock)
    event = json.loads(await anext(events))
    assert event["type"] == "timing"
    assert event["elapsedMs"] >= 900
    assert event["activeProcessingMs"] == 0
    assert not cancelled.is_set()
    await events.aclose()
    assert cancelled.is_set()
    await records.aclose()


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
async def test_parallel_requests_report_active_wall_time_with_failures(
    monkeypatch: pytest.MonkeyPatch, engine_name: str
) -> None:
    now = 0.0
    entered = 0
    ready = asyncio.Event()
    monkeypatch.setattr(server, "perf_counter", lambda: now)

    async def handle_classify(log: str, *_args: object) -> Result:
        nonlocal now, entered
        entered += 1
        if entered == 4:
            now = 5.0
            ready.set()
        await ready.wait()
        if log == "failed":
            raise ValueError("failed request")
        return {"review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    engine = server.Engine(engine_name, "http://example.test", "test", "test", 30)
    events = [
        json.loads(event)
        async for event in server.handle_events(["a", "b", "c", "failed"], engine)
    ]
    assert events[-1] == {
        "type": "done",
        "elapsedMs": 5000,
        "activeProcessingMs": 5000,
    }
    results = [event for event in events if event["type"] == "result"]
    assert len(results) == 4
    assert sum("error" in event["result"] for event in results) == 1
    assert all(event["activeProcessingMs"] <= event["elapsedMs"] for event in results)
