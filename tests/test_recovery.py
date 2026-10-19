"""Verify durable input cursors, run identity, and conservative Action recovery."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

import server
from classifier import Result
from config_store import get_data_directory
from jobs import JOBS
from source_registry import save_sources
from tasks import save_task, task_runs

pytestmark = pytest.mark.anyio


@pytest.fixture
async def recovery_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Result]:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("DECISION_ENGINE", "laya")
    monkeypatch.setenv("LAYA_CONCURRENCY", "1")
    monkeypatch.setenv("JEV_CONCURRENCY", "1")
    path = tmp_path / "input.log"
    path.write_text("one\ntwo\nthree\n")
    source = save_sources([{"name": "Input", "type": "local", "path": str(path)}])[0]
    task = save_task(
        {"name": "Recover", "mode": "batch", "sources": [{"sourceId": source["id"]}]}
    )
    try:
        yield {"task": task, "path": path, "source": source}
    finally:
        await asyncio.gather(*(job.stop() for job in JOBS.values()))
        JOBS.clear()
        server.TASK_STARTING.clear()
        server.SCHEDULER.due.clear()


async def wait_completed(job: server.Job, count: int) -> None:
    """Wait for stored results rather than only provider completion."""
    async with asyncio.timeout(5):
        while job.counts["completed"] < count:
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("paused", [False, True])
async def test_batch_restart_keeps_id_results_and_pending_inputs(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch, engine: str, paused: bool
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    entered = asyncio.Event()
    gate = asyncio.Event()
    calls: list[str] = []

    async def classify(log: str, *args: object) -> Result:
        calls.append(log)
        if log == "two":
            entered.set()
            await gate.wait()
        return {"category": "normal", "review": False, "engine": engine}

    monkeypatch.setattr(server, "classify_log", classify)
    run = await server.launch_task(recovery_task["task"], "manual")
    job = JOBS[run["jobId"]]
    await asyncio.wait_for(entered.wait(), 5)
    await wait_completed(job, 1)
    if paused:
        await job.pause()
    await job.suspend()
    assert job.state == ("pausing" if paused else "running")
    assert job.finished_at is None
    JOBS.clear()
    assert await server.restore_task_runs() == {recovery_task["task"]["id"]}
    recovered = JOBS[job.id]
    assert recovered.id == job.id and recovered.counts["completed"] == 1
    if paused:
        assert recovered.state == "paused"
        await asyncio.sleep(0.05)
        assert calls == ["one", "two"]
        await recovered.resume()
    gate.set()
    await asyncio.wait_for(recovered.task, 5)
    assert recovered.state == "completed"
    assert recovered.counts["completed"] == 3
    assert calls == ["one", "two", "two", "three"]
    assert len(task_runs(recovery_task["task"]["id"])) == 1
    assert recovered.store.pending(job.id, 0) == []
    assert recovered.store.state(job.id)["summary"]["total"] == 3


@pytest.mark.parametrize("paused", [False, True])
async def test_realtime_restart_reads_downtime_lines_from_idle_cursor(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch, paused: bool
) -> None:
    calls: list[str] = []

    async def classify(log: str, *args: object) -> Result:
        calls.append(log)
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", classify)
    task = save_task({**recovery_task["task"], "mode": "realtime"})
    job = JOBS[(await server.launch_task(task, "manual"))["jobId"]]
    async with asyncio.timeout(5):
        while not job.store.checkpoints(job.id):
            await asyncio.sleep(0.01)
    if paused:
        await job.pause()
    await job.suspend()
    JOBS.clear()
    with recovery_task["path"].open("a") as file:
        file.write("during downtime\n")
    await server.restore_task_runs()
    recovered = JOBS[job.id]
    if paused:
        assert recovered.state == "paused"
        await asyncio.sleep(0.05)
        assert calls == []
        await recovered.resume()
    await wait_completed(recovered, 1)
    assert calls == ["during downtime"]
    assert recovered.started_at == job.started_at
    await recovered.stop()


async def test_changed_batch_file_fails_without_replaying_old_results(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()

    async def classify(log: str, *args: object) -> Result:
        entered.set()
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(server, "classify_log", classify)
    job = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
    await asyncio.wait_for(entered.wait(), 5)
    await job.suspend()
    JOBS.clear()
    recovery_task["path"].unlink()
    recovery_task["path"].write_text("replacement\n")

    async def finish(log: str, *args: object) -> Result:
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", finish)
    await server.restore_task_runs()
    recovered = JOBS[job.id]
    await asyncio.wait_for(recovered.task, 5)
    assert recovered.state == "failed"
    assert "changed since checkpoint" in (recovered.error or "")
    # The already queued original input survives; the replacement is not consumed.
    assert recovered.counts["completed"] == 1


async def test_action_intent_and_outcome_are_not_reexecuted(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    from result_store import open_result_store

    store = open_result_store(get_data_directory())
    settings, _ = await server.prepare_file_execution(
        "batch", recovery_task["task"]["sources"]
    )
    settings.update(taskId=recovery_task["task"]["id"], taskName="Recover")
    for phase in ("action", "acted"):
        snapshot = {
            "jobId": phase * 8,
            "state": "running",
            "settings": settings,
            "startedAt": "2026-10-17T00:00:00+00:00",
            "counts": {"completed": 0, "failed": 0, "actionFailed": 0},
        }
        store.create(snapshot["jobId"], snapshot)
        item = store.enqueue(
            snapshot["jobId"],
            {
                "log": "queued",
                "category": "normal",
                "review": False,
                "elapsedMs": 10,
                "actionId": "old-action",
                "actionExecution": {"status": "success"},
            },
        )
        store.action_checkpoint(snapshot["jobId"], item, phase)
    calls: list[str] = []

    async def classify(log: str, *args: object) -> Result:
        calls.append(log)
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", classify)

    # No external action may run while replaying persisted outcomes or uncertain intent.
    async def action(*args: object) -> Result:
        raise AssertionError("Recovered Action was reexecuted")

    monkeypatch.setattr(server, "run_action", action)
    await server.restore_task_runs()
    for job in JOBS.values():
        await asyncio.wait_for(job.task, 5)
        page = job.store.page(job.id, {}, 10)
        queued = next(
            item["result"]
            for item in page["items"]
            if item["result"]["log"] == "queued"
        )
        assert "_workId" not in queued and "_recoveredResult" not in queued
        assert queued["actionExecution"]["status"] == (
            "failed" if job.id.startswith("action") else "success"
        )
    assert "queued" not in calls


async def test_action_inflight_is_journaled_before_shutdown(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tasks

    recovery_task["path"].write_text("one\n")
    entered = asyncio.Event()
    action_calls: list[str] = []
    definitions = [{"id": "notify", "name": "Notify"}]
    monkeypatch.setattr(server, "load_actions", lambda: definitions)
    monkeypatch.setattr(tasks, "load_actions", lambda: definitions)
    monkeypatch.setattr(server, "ensure_actions_available", lambda values: None)
    task = save_task(
        {
            **recovery_task["task"],
            "sources": [
                {"sourceId": recovery_task["source"]["id"], "actionId": "notify"}
            ],
        }
    )

    async def classify(log: str, *args: object) -> Result:
        return {"category": "normal", "review": False}

    async def action(settings: Result, result: Result) -> Result:
        action_calls.append(result["eventId"])
        entered.set()
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(server, "classify_log", classify)
    monkeypatch.setattr(server, "run_action", action)
    job = JOBS[(await server.launch_task(task, "manual"))["jobId"]]
    await asyncio.wait_for(entered.wait(), 5)
    await job.suspend()
    JOBS.clear()
    await server.restore_task_runs()
    recovered = JOBS[job.id]
    await asyncio.wait_for(recovered.task, 5)
    assert len(action_calls) == 1
    assert recovered.state == "failed" and recovered.counts["actionFailed"] == 1
    row = recovered.store.page(job.id, {}, 10)["items"][0]["result"]
    assert row["review"] and row["actionExecution"]["interrupted"]
    assert row["eventId"] == action_calls[0]


async def test_hard_process_exit_recovers_committed_sqlite_queue(
    recovery_task: Result, tmp_path: Path
) -> None:
    import os
    import subprocess
    import sys

    data = get_data_directory()
    marker = tmp_path / "run-id"
    setup = f"""
import asyncio, os
from pathlib import Path
import server
from jobs import JOBS
from tasks import load_tasks
async def main():
    entered = asyncio.Event()
    async def classify(log, *args):
        if log == "two":
            entered.set()
            await asyncio.Event().wait()
        return {{"category":"normal","review":False}}
    server.classify_log = classify
    run = await server.launch_task(load_tasks()[0], "manual")
    job = JOBS[run["jobId"]]
    await entered.wait()
    while job.counts["completed"] != 1:
        await asyncio.sleep(.01)
    Path({str(marker)!r}).write_text(job.id)
    os._exit(0)
asyncio.run(main())
"""
    environment = {**os.environ, "DECIFLOW_DATA_DIR": str(data)}
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", setup],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr
    recovered = f"""
import asyncio
from pathlib import Path
import server
from jobs import JOBS
async def main():
    calls = []
    async def classify(log, *args):
        calls.append(log)
        return {{"category":"normal","review":False}}
    server.classify_log = classify
    await server.restore_task_runs()
    job = JOBS[Path({str(marker)!r}).read_text()]
    await asyncio.wait_for(job.task, 5)
    assert calls == ["two", "three"], calls
    assert job.counts["completed"] == 3 and job.state == "completed"
asyncio.run(main())
"""
    process = await asyncio.to_thread(
        subprocess.run,
        [sys.executable, "-c", recovered],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0, process.stderr


async def test_jsonl_utf8_recovery_preserves_record_boundaries(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    path = recovery_task["path"]
    path.write_text(
        "\n".join(
            json.dumps({"content": text}, ensure_ascii=False)
            for text in ("첫째 상담", "둘째 상담", "셋째 상담")
        )
        + "\n"
    )
    save_sources(
        [{**recovery_task["source"], "format": "jsonl", "contentField": "content"}]
    )
    entered = asyncio.Event()
    gate = asyncio.Event()
    calls: list[str] = []

    async def classify(log: str, *args: object) -> Result:
        calls.append(log)
        if log == "둘째 상담":
            entered.set()
            await gate.wait()
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", classify)
    job = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
    await asyncio.wait_for(entered.wait(), 5)
    await wait_completed(job, 1)
    await job.suspend()
    JOBS.clear()
    gate.set()
    await server.restore_task_runs()
    recovered = JOBS[job.id]
    await asyncio.wait_for(recovered.task, 5)
    assert calls == ["첫째 상담", "둘째 상담", "둘째 상담", "셋째 상담"]
    rows = recovered.store.page(job.id, {}, 10)["items"]
    assert [item["result"]["recordNumber"] for item in rows] == [3, 2, 1]


async def test_sftp_cursor_resumes_utf8_without_repeating_first_line(
    tmp_path: Path,
) -> None:
    import asyncssh

    from classifier import EXECUTION_CONTROL, ExecutionControl
    from remote_sources import _lines

    path = tmp_path / "remote.log"
    path.write_text("첫째\n둘째\n마지막", encoding="utf-8")

    class TestServer(asyncssh.SSHServer):
        def begin_auth(self, username: str) -> bool:
            return False

    key = asyncssh.generate_private_key("ssh-ed25519")
    # Ephemeral local test server only; production host verification is unchanged.
    async with (
        await asyncssh.listen(
            "127.0.0.1",
            0,
            server_factory=TestServer,
            server_host_keys=[key],
            sftp_factory=asyncssh.SFTPServer,
        ) as listener,
        asyncssh.connect(
            "127.0.0.1", listener.get_port(), username="test", known_hosts=None
        ) as connection,
        connection.start_sftp_client() as sftp,
    ):
        control = ExecutionControl()

        async def checkpoint(source: str, cursor: Result) -> None:
            pass

        control.checkpoint = checkpoint
        token = EXECUTION_CONTROL.set(control)
        spec = {
            "type": "ssh",
            "host": "127.0.0.1",
            "port": listener.get_port(),
            "username": "test",
        }
        try:
            lines = _lines(sftp, str(path), spec, live=False, from_start=True)
            first = await anext(lines)
            await lines.aclose()
            control.cursors[first["source"]] = first["_checkpoint"]
            control.recovering = True
            rows = [
                row
                async for row in _lines(
                    sftp, str(path), spec, live=False, from_start=True
                )
            ]
            assert [row["log"] for row in rows] == ["둘째", "마지막"]
            assert [row["line"] for row in rows] == [2, 3]
        finally:
            EXECUTION_CONTROL.reset(token)


async def test_explicit_stop_is_not_recovered_and_engine_change_is_reported(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def classify(log: str, *args: object) -> Result:
        await asyncio.Event().wait()
        return {}

    monkeypatch.setattr(server, "classify_log", classify)
    first = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
    await first.stop()
    JOBS.clear()
    assert await server.restore_task_runs() == set()
    assert not JOBS
    second = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
    second.settings.pop("runtimeSnapshot", None)  # Legacy runs lack frozen options.
    await second.pause()
    await second.suspend()
    JOBS.clear()
    monkeypatch.setenv("DECISION_ENGINE", "jev")
    await server.restore_task_runs()
    assert not JOBS
    saved = task_runs(recovery_task["task"]["id"])[0]
    assert saved["state"] == "failed" and "engine or model changed" in saved["error"]


async def test_server_lifespan_recovers_before_accepting_new_starts(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()
    gate = asyncio.Event()

    async def initialize() -> None:
        pass

    async def classify(log: str, *args: object) -> Result:
        if log == "two":
            entered.set()
            await gate.wait()
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "initialize_default_action", initialize)
    monkeypatch.setattr(server, "classify_log", classify)
    async with server.lifespan(server.app):
        job = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
        await asyncio.wait_for(entered.wait(), 5)
        await wait_completed(job, 1)
    assert not JOBS and job.state == "running"
    async with server.lifespan(server.app):
        # Recovery is installed before the server exposes its routes.
        recovered = JOBS[job.id]
        assert server.active_task_job(recovery_task["task"]["id"]) is recovered
        with pytest.raises(ValueError, match="already running"):
            await server.launch_task(recovery_task["task"], "manual")
        gate.set()
        await asyncio.wait_for(recovered.task, 5)
        assert recovered.counts["completed"] == 3


async def test_recovery_preserves_runtime_snapshot_after_settings_change(
    recovery_task: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app_settings import save_settings
    from config import Engine

    observed = []

    async def classify(log: str, engine: Engine, *args: object) -> Result:
        observed.append((engine.name, engine.model, engine.head_tokens))
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", classify)
    first = JOBS[(await server.launch_task(recovery_task["task"], "manual"))["jobId"]]
    await first.pause()
    await first.suspend()
    JOBS.clear()
    save_settings(
        {
            "resultsPerPage": 30,
            "runtimeOverrides": {"DECISION_ENGINE": "jev", "LAYA_HEAD_TOKENS": "400"},
        }
    )
    await server.restore_task_runs()
    restored = JOBS[first.id]
    assert restored.settings["engine"] == "laya"
    assert "JEV_API_KEY" not in restored.settings["runtimeSnapshot"]
    await restored.resume()
    await asyncio.wait_for(restored.task, 5)
    assert restored.state == "completed"
    assert all(item == ("laya", "multilingual", 256) for item in observed)
