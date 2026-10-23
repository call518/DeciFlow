"""Verify Task scheduling, durable execution, overlap protection, and replay."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from deciflow import server
from deciflow.classifier import Result
from deciflow.config_store import get_data_directory, save_records
from deciflow.jobs import JOBS, Job
from deciflow.result_store import open_result_store
from deciflow.source_registry import load_sources, save_sources
from deciflow.tasks import (
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
            "enabled": True,
            "mode": "batch",
            "sources": [
                {
                    "sourceId": source["id"],
                    "profile": "4e6d5417-611e-49e0-8e23-2444a0f49ee4",
                    "chunkEvents": 1,
                }
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
    model = "multilingual" if engine == "laya" else "test-history-model"
    monkeypatch.setenv(f"{engine.upper()}_MODEL", model)
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
        assert run["settings"]["engine"] == engine
        assert run["settings"]["model"] == model
        job = JOBS[run["jobId"]]
        await asyncio.wait_for(job.task, 3)
        assert job.state == "completed" and job.counts["completed"] == 2
        assert sorted(calls) == ["one", "two"]
        assert task_runs(task_setup["task"]["id"])[0]["state"] == "completed"
        replay = await client.post(f"/api/jobs/{job.id}/events")
        monkeypatch.setenv("DECISION_ENGINE", "jev" if engine == "laya" else "laya")
        monkeypatch.setenv("LAYA_MODEL", "changed-model")
        monkeypatch.setenv("JEV_MODEL", "changed-model")
        JOBS.clear()  # Simulate a new server process reading the same volume.
        archived = await client.post(f"/api/jobs/{job.id}")
        assert archived.json()["counts"]["completed"] == 2
        after_restart = await client.post(f"/api/jobs/{job.id}/events")
        assert after_restart.text == replay.text
        assert sorted(calls) == ["one", "two"]
        history = await client.post(f"/api/tasks/{task_setup['task']['id']}/runs")
        assert len(history.json()["runs"]) == 1
        for stored in (archived.json(), history.json()["runs"][0]):
            assert stored["settings"]["engine"] == engine
            assert stored["settings"]["model"] == model
        page = await client.post(f"/api/jobs/{job.id}/results", json={})
        assert page.status_code == 200
        assert page.json()["snapshot"]["settings"]["engine"] == engine
        assert page.json()["snapshot"]["settings"]["model"] == model


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
                "profile": "4e6d5417-611e-49e0-8e23-2444a0f49ee4",
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
    from deciflow.tasks import set_task_enabled

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


async def test_stop_then_run_keeps_old_results_and_starts_independent_counts(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run is a new execution, while the stopped run stays replayable in History."""
    first_phase = True
    first_gate = asyncio.Event()
    second_gate = asyncio.Event()

    async def handle_classify(log: str, *args: object) -> Result:
        if first_phase and log == "two":
            await first_gate.wait()
        if not first_phase:
            await second_gate.wait()
        return {"category": "normal", "review": False, "probabilities": {"normal": 1}}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        task_id = task_setup["task"]["id"]
        first = (await client.post(f"/api/tasks/{task_id}/run")).json()
        async with asyncio.timeout(3):
            while JOBS[first["jobId"]].counts["completed"] < 1:
                await asyncio.sleep(0.01)
        await client.post(f"/api/tasks/{task_id}/stop")
        first_phase = False
        second = (await client.post(f"/api/tasks/{task_id}/run")).json()
        assert first["jobId"] != second["jobId"]
        assert second["counts"]["completed"] == 0
        history = (await client.post(f"/api/tasks/{task_id}/runs")).json()["runs"]
        runs = {run["jobId"]: run for run in history}
        assert runs[first["jobId"]]["state"] == "stopped"
        assert runs[first["jobId"]]["counts"]["completed"] == 1
        assert runs[second["jobId"]]["counts"]["completed"] == 0
        second_gate.set()
        await asyncio.wait_for(JOBS[second["jobId"]].task, 3)
        old = (await client.post(f"/api/jobs/{first['jobId']}/results", json={})).json()
        new = (
            await client.post(f"/api/jobs/{second['jobId']}/results", json={})
        ).json()
        assert old["summary"]["total"] == 1
        assert new["summary"]["total"] == 2


@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_pause_drains_inflight_and_resume_keeps_run(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    monkeypatch.setenv(f"{engine.upper()}_CONCURRENCY", "1")
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []

    async def handle_classify(log: str, *args: object) -> Result:
        calls.append(log)
        entered.set()
        await release.wait()
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    identity = task_setup["task"]["id"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        run = (await client.post(f"/api/tasks/{identity}/run")).json()
        job = JOBS[run["jobId"]]
        await asyncio.wait_for(entered.wait(), 3)
        response = await client.post(f"/api/tasks/{identity}/pause")
        assert response.json()["state"] == "pausing"
        release.set()
        async with asyncio.timeout(3):
            while job.state != "paused" or job.counts["completed"] != 1:
                await asyncio.sleep(0.01)
        assert calls == ["one"]
        assert not job.task.done()
        assert (await client.post(f"/api/tasks/{identity}/run")).status_code == 409
        assert (
            await client.request("DELETE", "/api/tasks", json={"id": identity})
        ).status_code == 409
        persisted = task_runs(identity)[0]
        assert persisted["state"] == "paused"
        resumed = (await client.post(f"/api/tasks/{identity}/resume")).json()
        assert resumed["jobId"] == run["jobId"]
        await asyncio.wait_for(job.task, 3)
        assert calls == ["one", "two"]
        assert job.state == "completed" and job.counts["completed"] == 2
        assert len(task_runs(identity)) == 1
        assert (await client.post(f"/api/tasks/{identity}/resume")).status_code == 409


async def test_paused_job_can_stop_and_is_recovered_after_restart(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def handle_classify(log: str, *args: object) -> Result:
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    job = JOBS[(await server.launch_task(task_setup["task"], "manual"))["jobId"]]
    await job.pause()
    assert job.state == "paused"
    await asyncio.wait_for(job.stop(), 3)
    assert job.state == "stopped"
    store = open_result_store(get_data_directory())
    for state in ("paused", "pausing"):
        snapshot = {
            **job.snapshot(),
            "jobId": state,
            "state": state,
            "settings": {**job.settings, "recoveryVersion": 0},
        }
        store.create(state, snapshot)
    store.recover_interrupted()
    for state in ("paused", "pausing"):
        assert store.state(state)["snapshot"]["state"] == "stopped"


@pytest.mark.parametrize("mode", ["batch", "realtime"])
async def test_paused_task_does_not_block_other_tasks_or_inflight_action(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("LAYA_CONCURRENCY", "1")
    entered = asyncio.Event()
    action_entered = asyncio.Event()
    release = asyncio.Event()
    action_release = asyncio.Event()
    calls: list[str] = []

    async def handle_classify(log: str, *args: object) -> Result:
        calls.append(log)
        if log == "one":
            entered.set()
            await release.wait()
        return {"category": "normal", "review": False}

    original_actions = server._action_results

    async def handle_actions(
        results: AsyncGenerator[tuple[int, Result], None],
        actions: list[Result],
        engine: str,
    ) -> AsyncGenerator[tuple[int, Result], None]:
        async for index, result in original_actions(results, actions, engine):
            if result["log"] == "one":
                action_entered.set()
                await action_release.wait()
            yield index, result

    async def handle_live(specs: list[Result]) -> AsyncGenerator[Result, None]:
        for log in ("one", "two"):
            yield {"log": log, "profile": "4e6d5417-611e-49e0-8e23-2444a0f49ee4"}
        await asyncio.Event().wait()

    monkeypatch.setattr(server, "classify_log", handle_classify)
    monkeypatch.setattr(server, "_action_results", handle_actions)
    monkeypatch.setattr(server, "follow_configured", handle_live)
    task = save_task({**task_setup["task"], "mode": mode})
    job = JOBS[(await server.launch_task(task, "manual"))["jobId"]]
    await asyncio.wait_for(entered.wait(), 3)
    await job.pause()
    release.set()
    await asyncio.wait_for(action_entered.wait(), 3)
    assert job.state == "pausing" and job.counts["completed"] == 0
    action_release.set()
    async with asyncio.timeout(3):
        while job.state != "paused":
            await asyncio.sleep(0.01)
    assert calls == ["one"]
    other_path = task_setup["path"].with_name("other.log")
    other_path.write_text("other\n")
    source = save_sources(
        [*load_sources(), {"name": "Other", "type": "local", "path": str(other_path)}]
    )[-1]
    other = save_task(
        {
            "name": "Other",
            "enabled": True,
            "mode": "batch",
            "sources": [{"sourceId": source["id"]}],
        }
    )
    second = JOBS[(await server.launch_task(other, "manual"))["jobId"]]
    await asyncio.wait_for(second.task, 3)
    assert second.state == "completed" and job.state == "paused"
    await job.resume()
    async with asyncio.timeout(3):
        while job.counts["completed"] != 2:
            await asyncio.sleep(0.01)
    assert calls == ["one", "other", "two"]
    if mode == "batch":
        await asyncio.wait_for(job.task, 3)
    else:
        await job.pause()
        await asyncio.wait_for(job.stop(), 3)
        assert job.state == "stopped"


async def test_task_without_sources_can_be_saved_but_not_run(
    task_setup: Result,
) -> None:
    task = save_task({**task_setup["task"], "sources": []})
    assert task["sources"] == []
    assert load_tasks()[0]["sources"] == []
    with pytest.raises(ValueError, match="Select at least one Source"):
        await server.launch_task(task, "manual")
    assert not server.TASK_STARTING


@pytest.mark.parametrize("state", ["running", "pausing", "paused", "starting"])
async def test_active_task_can_be_edited(
    task_setup: Result, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    task = task_setup["task"]
    if state == "starting":
        server.TASK_STARTING.add(task["id"])
    else:
        from types import SimpleNamespace

        monkeypatch.setattr(
            server,
            "active_task_job",
            lambda identity: SimpleNamespace(snapshot=lambda: {"state": state}),
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        response = await client.put("/api/tasks", json={**task, "sources": []})
    assert response.status_code == 200
    assert load_tasks()[0]["sources"] == []


async def test_task_without_criteria_can_be_saved_but_not_run(
    task_setup: Result,
) -> None:
    task = task_setup["task"]
    source = {**task["sources"][0], "profile": ""}
    saved = save_task({**task, "sources": [source]})
    assert saved["sources"][0]["profile"] == ""
    with pytest.raises(ValueError, match="Select Criteria for every Source"):
        await server.launch_task(saved, "manual")
    assert not server.TASK_STARTING


async def test_new_task_defaults_to_disabled(task_setup: Result) -> None:
    values = {
        key: value
        for key, value in task_setup["task"].items()
        if key not in {"id", "enabled"}
    }
    values["name"] = "New Disabled Task"
    task = save_task(values)
    assert task["enabled"] is False
    states = {item["id"]: item["enabled"] for item in load_tasks()}
    assert states[task["id"]] is False
    assert states[task_setup["task"]["id"]] is True
