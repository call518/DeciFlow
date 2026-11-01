"""Keep per-run pause measurements durable without counting server downtime."""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from deciflow import jobs


@pytest.mark.anyio
async def test_repeated_pauses_exclude_draining_and_survive_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 0.0
    monkeypatch.setattr(jobs, "perf_counter", lambda: now)
    deliver = asyncio.Event()

    async def events() -> AsyncGenerator[str, None]:
        await deliver.wait()
        yield json.dumps({"type": "result", "index": 0, "result": {"input": "test"}})
        await asyncio.Event().wait()

    job = jobs.Job({"mode": "batch", "taskId": "pause-test"}, events(), tmp_path)
    try:
        job.control.active = 1
        await job.pause()
        now = 2.0
        assert job.snapshot()["pausedMs"] == 0
        deliver.set()

        async def wait_until_paused() -> None:
            while job.state != "paused":
                await asyncio.sleep(0)

        await asyncio.wait_for(wait_until_paused(), 2)
        now = 5.0
        await job.pause()
        assert job.snapshot()["pausedMs"] == 3000
        now = 7.0
        await job.resume()
        now = 9.0
        assert job.snapshot()["pausedMs"] == 5000
        await job.pause()
        now = 11.0
        job.append({"type": "timing"})
        saved = jobs.read_archived_run(tmp_path, job.id)
        assert saved is not None and saved["pausedMs"] == 7000
        now = 12.0
        await job.stop()
        now = 20.0
        assert job.snapshot()["pausedMs"] == 8000
        saved = jobs.read_archived_run(tmp_path, job.id)
        assert saved is not None and saved["pausedMs"] == 8000
        assert json.loads(job.events[-1])["pausedMs"] == 8000
        next_run = jobs.Job(job.settings, events(), tmp_path)
        await next_run.stop()
        history = {run["jobId"]: run for run in job.store.history("pause-test", 50)}
        assert history[job.id]["pausedMs"] == 8000
        assert history[next_run.id]["pausedMs"] == 0
    finally:
        await job.stop()


@pytest.mark.anyio
async def test_pause_recovery_excludes_server_downtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 0.0
    monkeypatch.setattr(jobs, "perf_counter", lambda: now)

    async def events() -> AsyncGenerator[str, None]:
        await asyncio.Event().wait()
        yield ""

    job = jobs.Job({"mode": "realtime", "recoveryVersion": 1}, events(), tmp_path)
    await job.pause()
    now = 5.0
    await job.suspend()
    saved = jobs.read_archived_run(tmp_path, job.id)
    assert saved is not None and saved["pausedMs"] == 5000
    now = 100.0
    restored = jobs.Job(job.settings, events(), tmp_path, restored=saved)
    try:
        assert restored.id == job.id and restored.state == "paused"
        now = 102.0
        assert restored.snapshot()["pausedMs"] == 7000
        await restored.resume()
        now = 200.0
        assert restored.snapshot()["pausedMs"] == 7000
    finally:
        await restored.stop()


@pytest.mark.anyio
async def test_failure_finishes_pause_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 0.0
    monkeypatch.setattr(jobs, "perf_counter", lambda: now)
    fail = asyncio.Event()

    async def events() -> AsyncGenerator[str, None]:
        await fail.wait()
        raise ValueError("test failure")
        yield ""

    job = jobs.Job({"mode": "batch"}, events())
    await job.pause()
    now = 3.0
    fail.set()
    await job.task
    now = 9.0
    assert job.state == "failed"
    assert job.snapshot()["pausedMs"] == 3000
