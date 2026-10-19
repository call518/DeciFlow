"""Verify in-memory jobs, reconnection, explicit stop, and origin protection."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import httpx
import pytest

import server
from classifier import Result
from jobs import JOBS, Job


@pytest.fixture(autouse=True)
async def clean_jobs() -> AsyncIterator[None]:
    """Do not leak background jobs between test event loops."""
    yield
    await asyncio.gather(*(job.stop() for job in JOBS.values()))
    JOBS.clear()


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("mode", ["batch", "paste"])
async def test_job_reconnect_replays_without_duplicate_decisions_or_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str, mode: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    gate = asyncio.Event()
    entered = asyncio.Event()
    calls: list[str] = []
    actions: list[str] = []

    async def handle_classify(
        log: str,
        provider: object,
        client: object,
        profile: str = "4e6d5417-611e-49e0-8e23-2444a0f49ee4",
    ) -> Result:
        calls.append(log)
        entered.set()
        await gate.wait()
        return {"category": "normal", "review": False}

    async def handle_action(action: Result, result: Result) -> Result:
        actions.append(result["log"])
        return {"name": action["name"], "status": "success"}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    monkeypatch.setattr(server, "run_action", handle_action)
    monkeypatch.setattr(
        server, "load_actions", lambda: [{"id": "notify-id", "name": "notify"}]
    )
    log = tmp_path / "job.log"
    log.write_text("one\ntwo\n")
    body = (
        {"mode": mode, "sources": [{"path": str(log), "actionId": "notify-id"}]}
        if mode == "batch"
        else {"text": "one\ntwo"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.post(
            "/api/file-source" if mode == "batch" else "/api/classify",
            json={**body, "persist": True},
        )
        assert response.status_code == 202
        identifier = response.json()["jobId"]
        job = JOBS[identifier]
        stream = job.stream()
        assert json.loads(await anext(stream))["type"] == "start"
        await asyncio.wait_for(entered.wait(), timeout=2)
        await stream.aclose()
        assert not job.task.done()
        gate.set()
        await asyncio.wait_for(job.task, timeout=2)
        assert sorted(calls) == ["one", "two"]
        assert sorted(actions) == (["one", "two"] if mode == "batch" else [])
        for _ in range(2):
            replay = await client.post(f"/api/jobs/{identifier}/events")
            events = [json.loads(line) for line in replay.text.splitlines()]
            assert events[0]["type"] == "start"
            assert len([event for event in events if event["type"] == "result"]) == 2
            assert events[-1]["state"] == "completed"
        assert len(calls) == 2
        assert len(actions) == (2 if mode == "batch" else 0)
        info = (await client.post(f"/api/jobs/{identifier}")).json()
        assert info["settings"]["mode"] == mode
        assert info["state"] == "completed"


@pytest.mark.anyio
async def test_stop_preserves_results_and_closes_producer() -> None:
    closed = asyncio.Event()
    entered = asyncio.Event()

    async def handle_events() -> AsyncGenerator[str, None]:
        try:
            yield server._encode({"type": "start", "total": None})
            yield server._encode(
                {
                    "type": "result",
                    "index": 0,
                    "result": {"log": "one"},
                    "elapsedMs": 23,
                    "activeProcessingMs": 12,
                }
            )
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()

    job = Job({"mode": "realtime"}, handle_events())
    JOBS[job.id] = job
    await entered.wait()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        for _ in range(2):
            response = await client.post(f"/api/jobs/{job.id}/stop")
            assert response.json()["state"] == "stopped"
        assert closed.is_set()
        replay = await client.post(f"/api/jobs/{job.id}/events")
        events = [json.loads(line) for line in replay.text.splitlines()]
        assert events[1]["result"]["log"] == "one"
        assert events[-1] == {
            "type": "done",
            "state": "stopped",
            "elapsedMs": 23,
            "activeProcessingMs": 12,
        }


@pytest.mark.anyio
async def test_job_access_denied_and_server_restart_forgets_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))

    async def handle_events() -> AsyncGenerator[str, None]:
        yield server._encode({"type": "start"})
        await asyncio.Event().wait()

    job = Job({"mode": "realtime"}, handle_events())
    JOBS[job.id] = job
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        for suffix in ("", "/events", "/stop"):
            for headers in ({}, {"Origin": "https://evil.example"}):
                assert (
                    await client.post(f"/api/jobs/{job.id}{suffix}", headers=headers)
                ).status_code == 403
        assert not job.task.done()
        async with server.lifespan(server.app):
            pass
        assert job.task.done()
        assert not JOBS
        assert (
            await client.post(
                f"/api/jobs/{job.id}", headers={"Origin": "http://localhost"}
            )
        ).status_code == 404


@pytest.mark.anyio
async def test_stop_before_producer_starts_and_timing_is_not_accumulated() -> None:
    async def handle_events() -> AsyncGenerator[str, None]:
        yield server._encode({"type": "start"})
        await asyncio.Event().wait()

    job = Job({"mode": "realtime"}, handle_events())
    JOBS[job.id] = job
    for elapsed in range(100):
        job.append({"type": "timing", "elapsedMs": elapsed})
    assert not job.events
    await job.stop()
    events = [json.loads(event) async for event in job.stream()]
    assert events == [
        {"type": "done", "state": "stopped", "elapsedMs": 99, "activeProcessingMs": 0}
    ]


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_realtime_reads_new_logs_without_a_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    received = asyncio.Event()
    calls: list[str] = []

    async def handle_classify(log: str, provider: object, client: object) -> Result:
        calls.append(log)
        received.set()
        return {"category": "normal"}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    log = tmp_path / "live.log"
    log.write_text("")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.post(
            "/api/file-source",
            json={
                "mode": "realtime",
                "sources": [{"path": str(log)}],
                "persist": True,
            },
        )
        job = JOBS[response.json()["jobId"]]
        stream = job.stream()
        assert json.loads(await anext(stream))["type"] == "start"
        await stream.aclose()
        # Allow the follower to establish the initial EOF before appending.
        await asyncio.sleep(0.1)
        with log.open("a") as output:
            output.write("new event\n")
        await asyncio.wait_for(received.wait(), timeout=3)
        while not any(json.loads(event)["type"] == "result" for event in job.events):
            await asyncio.sleep(0.01)
        await client.post(f"/api/jobs/{job.id}/stop")
        replay = await client.post(f"/api/jobs/{job.id}/events")
        results = [
            json.loads(event)["result"]
            for event in replay.text.splitlines()
            if json.loads(event)["type"] == "result"
        ]
        assert [result["log"] for result in results] == ["new event"]
        assert calls == ["new event"]
