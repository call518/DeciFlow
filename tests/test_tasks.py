"""Verify Task scheduling, durable execution, overlap protection, and replay."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

import server
from classifier import Result
from config_store import get_data_directory, save_records
from jobs import JOBS, Job
from result_store import open_result_store
from source_registry import load_sources, save_sources
from tasks import (
    DEFAULT_TASK_ID,
    DEFAULT_TASK_NAME,
    TaskScheduler,
    ensure_default_task,
    load_tasks,
    next_run,
    recover_interrupted_runs,
    save_task,
    task_runs,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def task_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Result]:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    path = tmp_path / "input.log"
    path.write_text("one\ntwo\n")
    source = save_sources([{"name": "Input", "type": "local", "path": str(path)}])[0]
    task = save_task(
        {
            "name": "Logs",
            "mode": "batch",
            "sources": [
                {"sourceId": source["id"], "profile": "general", "chunkEvents": 1}
            ],
        }
    )
    try:
        yield {"task": task, "source": source, "path": path}
    finally:
        await asyncio.gather(*(job.stop() for job in JOBS.values()))
        JOBS.clear()
        server.TASK_STARTING.clear()
        server.SCHEDULER.due.clear()


async def test_task_validation_and_timezone(task_setup: Result) -> None:
    task = task_setup["task"]
    scheduled = save_task({**task, "cron": "0 9 * * *", "timezone": "Asia/Seoul"})
    assert next_run(scheduled, datetime(2026, 10, 15, 23, tzinfo=UTC)) == datetime(
        2026, 10, 16, tzinfo=UTC
    )
    before = load_tasks()
    for changes in [
        {"cron": "bad"},
        {"cron": "0 * * * * *"},
        {"timezone": "not/a/timezone"},
        {"mode": "paste"},
        {"mode": "realtime", "cron": "* * * * *"},
        {"enabled": "yes"},
        {"resumeOnRestart": 1},
        {"name": ""},
        {"sources": []},
        {"sources": [{"sourceId": "missing"}]},
        {"sources": [{"sourceId": task_setup["source"]["id"], "chunkEvents": 0}]},
        {"sources": [{"sourceId": task_setup["source"]["id"], "actionId": "unknown"}]},
        {"sources": task["sources"] * 2},
    ]:
        with pytest.raises((ValueError, TypeError)):
            save_task({**task, **changes})
        assert load_tasks() == before


@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_batch_runs_persist_and_replay_without_reexecution(
    task_setup: Result,
    monkeypatch: pytest.MonkeyPatch,
    engine: str,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    calls: list[str] = []

    async def handle_classify(log: str, *args: object) -> Result:
        calls.append(log)
        return {"category": "normal", "review": False, "probabilities": {"normal": 1}}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        run = (await client.post(f"/api/tasks/{task_setup['task']['id']}/run")).json()
        job = JOBS[run["jobId"]]
        await asyncio.wait_for(job.task, 3)
        assert job.state == "completed" and job.counts["completed"] == 2
        assert sorted(calls) == ["one", "two"]
        assert task_runs(task_setup["task"]["id"])[0]["state"] == "completed"
        replay = await client.post(f"/api/jobs/{job.id}/events")
        JOBS.clear()  # Simulate a new server process reading the same volume.
        archived = await client.post(f"/api/jobs/{job.id}")
        assert archived.json()["counts"]["completed"] == 2
        after_restart = await client.post(f"/api/jobs/{job.id}/events")
        assert after_restart.text == replay.text
        assert sorted(calls) == ["one", "two"]
        history = await client.post(f"/api/tasks/{task_setup['task']['id']}/runs")
        assert len(history.json()["runs"]) == 1


async def test_overlapping_manual_and_cron_runs_and_edit_snapshot(
    task_setup: Result,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = asyncio.Event()

    async def handle_classify(log: str, *args: object) -> Result:
        await gate.wait()
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    task = task_setup["task"]
    pending = asyncio.create_task(server.launch_task(task, "manual"))
    await asyncio.sleep(0)
    with pytest.raises(ValueError, match="already running"):
        await server.launch_task(task, "manual")
    run = await pending
    skipped = await server.launch_task(task, "cron")
    assert skipped["state"] == "skipped"
    saved = save_task(
        {
            **task,
            "name": "Renamed",
            "sources": [{**task["sources"][0], "chunkEvents": 2}],
        }
    )
    assert JOBS[run["jobId"]].settings["sources"][0]["chunkEvents"] == 1
    assert saved["sources"][0]["chunkEvents"] == 2
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        blocked = await client.request("DELETE", "/api/tasks", json={"id": task["id"]})
        assert blocked.status_code == 409
        assert (await client.post(f"/api/tasks/{task['id']}/stop")).status_code == 200
    assert JOBS[run["jobId"]].state == "stopped"
    gate.set()


async def test_scheduler_cron_pause_skip_downtime_and_single_due(
    task_setup: Result,
) -> None:
    task = save_task({**task_setup["task"], "cron": "* * * * *", "timezone": "UTC"})
    calls: list[str] = []

    async def launch(task: Result, trigger: str) -> Result:
        calls.append(trigger)
        return {"state": "completed"}

    scheduler = TaskScheduler(launch)
    now = datetime(2026, 10, 16, 0, 0, 30, tzinfo=UTC)
    await scheduler.tick(now)
    assert calls == []
    await scheduler.tick(now + timedelta(seconds=30))
    await scheduler.tick(now + timedelta(seconds=30))
    assert calls == ["cron"]
    # Several missed minutes produce at most one current occurrence, not catch-up.
    await scheduler.tick(now + timedelta(minutes=10))
    assert calls == ["cron", "cron"]
    save_task({**task, "enabled": False})
    await scheduler.tick(now + timedelta(minutes=11))
    assert calls == ["cron", "cron"]
    save_task({**task, "enabled": True})
    restarted = TaskScheduler(launch)
    await restarted.tick(now + timedelta(minutes=20))
    assert calls == ["cron", "cron"]


async def test_task_api_origin_and_dependencies_cannot_be_deleted(
    task_setup: Result,
) -> None:
    identity = task_setup["task"]["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        for method in ["POST", "PUT", "DELETE"]:
            assert (
                await client.request(method, "/api/tasks", json={})
            ).status_code == 403
        for operation in ["run", "stop", "runs"]:
            assert (
                await client.post(f"/api/tasks/{identity}/{operation}")
            ).status_code == 403
        headers = {"Origin": "http://localhost"}
        denied = await client.put("/api/sources", json=[], headers=headers)
        assert denied.status_code == 400 and "Task" in denied.json()["error"]
        listed = await client.post("/api/tasks", headers=headers)
        assert listed.json()["tasks"][0]["latestRun"] is None
        removed = await client.request(
            "DELETE", "/api/tasks", json={"id": identity}, headers=headers
        )
        assert removed.status_code == 200 and removed.json()["tasks"] == []


async def test_failed_preparation_is_recorded(task_setup: Result) -> None:
    task_setup["path"].unlink()
    run = await server.launch_task(task_setup["task"], "cron")
    assert run["state"] == "failed" and run["error"]
    assert task_runs(task_setup["task"]["id"])[0]["jobId"] == run["jobId"]


@pytest.mark.parametrize("failure", ["decision", "action"])
async def test_failed_results_or_actions_fail_task(
    task_setup: Result,
    failure: str,
) -> None:
    async def events() -> AsyncGenerator[str, None]:
        result = {
            "log": "one",
            **(
                {"error": "engine failed"}
                if failure == "decision"
                else {"actionExecution": {"status": "failed"}}
            ),
        }
        for event in [
            {"type": "result", "index": 0, "result": result},
            {"type": "done", "elapsedMs": 1},
        ]:
            yield json.dumps(event) + "\n"

    job = Job(
        {"taskId": task_setup["task"]["id"], "mode": "batch", "sources": []},
        events(),
        get_data_directory(),
    )
    await job.task
    assert job.state == "failed"
    assert task_runs(task_setup["task"]["id"])[0]["state"] == "failed"


async def test_interrupted_run_and_opt_in_realtime_restart(task_setup: Result) -> None:
    task = save_task(
        {**task_setup["task"], "mode": "realtime", "resumeOnRestart": True}
    )
    store = open_result_store(get_data_directory())
    store.create(
        "1" * 32,
        {
            "state": "running",
            "jobId": "1" * 32,
            "settings": {"taskId": task["id"], "mode": "realtime"},
        },
    )
    recover_interrupted_runs()
    assert store.state("1" * 32)["snapshot"]["state"] == "stopped"
    called = asyncio.Event()

    async def launch(task: Result, trigger: str) -> Result:
        assert task["mode"] == "realtime" and trigger == "restart"
        called.set()
        return {}

    scheduler = TaskScheduler(launch)
    loop = asyncio.create_task(scheduler.run())
    await asyncio.wait_for(called.wait(), 2)
    loop.cancel()
    await asyncio.gather(loop, return_exceptions=True)


async def test_history_write_failure_terminates_stream_instead_of_hanging(
    task_setup: Result,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = asyncio.Event()

    async def events() -> AsyncGenerator[str, None]:
        await gate.wait()
        yield json.dumps({"type": "start", "total": 0}) + "\n"

    job = Job(
        {"taskId": task_setup["task"]["id"], "mode": "batch", "sources": []},
        events(),
        get_data_directory(),
    )
    assert job.persistent

    def handle_failed_write(*args: object) -> None:
        raise OSError("fixture SQLite write failure")

    monkeypatch.setattr(job.store, "append", handle_failed_write)
    gate.set()
    await asyncio.wait_for(job.task, 2)
    replay = [json.loads(event) async for event in job.stream()]
    assert job.state == "failed"
    assert replay[-1]["state"] == "failed"
    assert "SQLite write failure" in replay[-2]["error"]


async def test_delete_task_removes_files_and_database_history(
    task_setup: Result,
) -> None:
    task = task_setup["task"]
    identity = "f" * 32
    snapshot = {
        "jobId": identity,
        "state": "completed",
        "settings": {"mode": "batch", "taskId": task["id"]},
        "startedAt": "2026-10-16T00:00:00Z",
    }
    store = open_result_store(get_data_directory())
    store.create(identity, snapshot)
    store.append(
        identity,
        {"type": "result", "result": {"log": "retained", "category": "normal"}},
        snapshot,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.request("DELETE", "/api/tasks", json={"id": task["id"]})
        assert response.status_code == 200
        assert not (get_data_directory() / "tasks").exists()
        assert task_setup["path"].exists()
        page = await client.post(f"/api/jobs/{identity}/results", json={})
        assert page.status_code == 404
        replay = await client.post(f"/api/jobs/{identity}/events")
        assert replay.status_code == 404
        exported = await client.post(f"/api/jobs/{identity}/export")
        assert exported.status_code == 404


async def test_default_task_restores_after_database_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DECIFLOW_LOG_DIR", str(tmp_path / "logs"))
    launches: list[Result] = []

    async def handle_launch(task: Result, trigger: str) -> Result:
        launches.append(task)
        return {}

    scheduler = TaskScheduler(handle_launch)
    loop = asyncio.create_task(scheduler.run())
    try:
        for _ in range(100):
            if load_tasks():
                break
            await asyncio.sleep(0.01)
        task = load_tasks()[0]
        assert task["id"] == DEFAULT_TASK_ID
        assert task["name"] == DEFAULT_TASK_NAME
        assert task["mode"] == "realtime"
        assert task["enabled"] is False
        assert task["resumeOnRestart"] is False
        source = load_sources()[0]
        assert source["name"] == "Sample DeciFlow Server Log"
        assert source["path"] == "\n".join(
            str(tmp_path / "logs" / name) for name in ("server.log", "access.log")
        )
        assert task["sources"] == [
            {
                "sourceId": source["id"],
                "profile": "general",
                "chunkEvents": 1,
                "actionId": "",
            }
        ]
        save_records("tasks", {})
        ensure_default_task()
        await scheduler.tick(datetime.now(UTC))
        assert load_tasks() == [task]
        assert len([s for s in load_sources() if s["id"] == source["id"]]) == 1
        assert launches == []
    finally:
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)


async def test_default_task_preserves_existing_configuration(
    task_setup: Result,
) -> None:
    original = task_setup["task"]
    ensure_default_task()
    default = next(task for task in load_tasks() if task["id"] == DEFAULT_TASK_ID)
    edited = save_task(
        {**default, "name": "My Server Monitor", "resumeOnRestart": True}
    )
    sources = load_sources()
    ensure_default_task()
    assert load_tasks() == [original, edited]
    assert load_sources() == sources


async def test_disabled_task_blocks_manual_run_and_toggle_stops_active_run(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tasks import set_task_enabled

    task = task_setup["task"]
    set_task_enabled(task["id"], False)
    with pytest.raises(ValueError, match="Enable the Task"):
        await server.launch_task(task, "manual")
    stopped = asyncio.Event()

    class RunningJob:
        async def stop(self) -> None:
            stopped.set()

    monkeypatch.setattr(server, "active_task_job", lambda identity: RunningJob())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.post(
            f"/api/tasks/{task['id']}/enabled", json={"enabled": True}
        )
        assert response.status_code == 200
        assert not stopped.is_set()
        assert load_tasks()[0]["enabled"] is True
        response = await client.post(
            f"/api/tasks/{task['id']}/enabled", json={"enabled": False}
        )
        assert response.status_code == 200
        assert stopped.is_set()
        assert load_tasks()[0]["enabled"] is False
        response = await client.post(
            f"/api/tasks/{task['id']}/enabled", json={"enabled": "false"}
        )
        assert response.status_code == 409
        assert load_tasks()[0]["enabled"] is False


async def test_disabled_realtime_task_does_not_resume(task_setup: Result) -> None:
    task = save_task(
        {
            **task_setup["task"],
            "mode": "realtime",
            "resumeOnRestart": True,
            "enabled": False,
        }
    )
    launches: list[str] = []

    async def handle_launch(task: Result, trigger: str) -> Result:
        launches.append(task["id"])
        return {}

    scheduler = TaskScheduler(handle_launch)
    loop = asyncio.create_task(scheduler.run())
    try:
        await asyncio.sleep(0.05)
        assert next(item for item in load_tasks() if item["id"] == task["id"])
        assert launches == []
    finally:
        loop.cancel()
        await asyncio.gather(loop, return_exceptions=True)


async def test_default_task_uses_uuid_and_avoids_name_collisions(
    task_setup: Result,
) -> None:
    original = save_task({**task_setup["task"], "name": DEFAULT_TASK_NAME.lower()})
    ensure_default_task()
    tasks = load_tasks()
    default = next(task for task in tasks if task["id"] == DEFAULT_TASK_ID)
    assert default["name"] == f"{DEFAULT_TASK_NAME} (2)"
    assert original in tasks
    ensure_default_task()
    assert load_tasks() == tasks
