"""Verify multi-host Task configuration, fairness, isolation and durable identity."""

import asyncio
import json
from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest

import host_sources
import server
import tasks
from classifier import Result
from jobs import JOBS
from source_registry import get_sources_path, load_sources, save_sources
from source_settings import parse_source_settings
from ssh_hosts import save_host
from tasks import get_tasks_directory, load_tasks, save_task, task_runs

pytestmark = pytest.mark.anyio


@pytest.fixture
async def multi(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Result]:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    key = tmp_path / "key"
    key.write_text("fixture file; SSH is mocked")
    hosts = [
        save_host(
            {
                "name": name,
                "host": name.lower(),
                "port": 22,
                "username": "reader",
                "keyPath": str(key),
            }
        )
        for name in ("Alpha", "Beta", "Gamma")
    ]
    source = save_sources(
        [{"name": "Common logs", "type": "ssh", "path": "/logs/*.log"}]
    )[0]
    selection = {
        "sourceId": source["id"],
        "profile": "general",
        "chunkEvents": 1,
        "hostIds": [host["id"] for host in hosts],
    }
    task = save_task({"name": "Fleet", "mode": "batch", "sources": [selection]})
    yield {"hosts": hosts, "source": source, "selection": selection, "task": task}
    await asyncio.gather(*(job.stop() for job in JOBS.values()))
    JOBS.clear()
    server.TASK_STARTING.clear()


async def empty() -> AsyncGenerator[Result, None]:
    if False:
        yield {}


async def test_target_validation_and_resolved_settings_are_authoritative(
    multi: Result,
) -> None:
    selection = multi["selection"]
    specs = parse_source_settings(
        [{**selection, "host": "attacker", "keyPath": "tampered"}]
    )
    assert len(specs) == 3
    assert {spec["host"] for spec in specs} == {"alpha", "beta", "gamma"}
    assert "hostId" not in load_sources()[0]
    assert load_tasks()[0]["sources"][0]["hostIds"] == selection["hostIds"]
    for ids in [None, [], "alpha", ["missing"], [selection["hostIds"][0]] * 2, [None]]:
        with pytest.raises((ValueError, TypeError)):
            save_task({**multi["task"], "sources": [{**selection, "hostIds": ids}]})
    with pytest.raises(ValueError, match="only once"):
        save_task({**multi["task"], "sources": [selection, selection]})
    local = save_sources([{"name": "Local", "type": "local", "path": "/local"}])[0]
    with pytest.raises(ValueError, match="Local File"):
        parse_source_settings(
            [{"sourceId": local["id"], "hostIds": selection["hostIds"]}]
        )


async def test_legacy_source_targets_move_to_all_tasks_once(multi: Result) -> None:
    source = multi["source"]
    host = multi["hosts"][0]
    source_path = get_sources_path()
    source_path.write_text(json.dumps([{**source, "hostId": host["id"]}]))
    tasks = [
        {
            **multi["task"],
            "id": str(index) * 32,
            "sources": [{"sourceId": source["id"], "chunkEvents": 2}],
        }
        for index in (1, 2)
    ]
    task_path = get_tasks_directory() / "tasks.json"
    task_path.write_text(json.dumps(tasks))
    history = get_tasks_directory() / tasks[0]["id"] / "runs" / ("f" * 32) / "run.json"
    history.parent.mkdir(parents=True)
    history.write_text('{"state":"completed","settings":{"host":"original"}}')
    snapshot = history.read_bytes()
    migrated = load_tasks()
    assert all(task["sources"][0]["hostIds"] == [host["id"]] for task in migrated)
    assert load_sources() == [source]
    stored = task_path.read_bytes()
    assert load_tasks() == migrated and task_path.read_bytes() == stored
    assert history.read_bytes() == snapshot


async def test_slow_host_gets_the_next_round_and_backpressure_is_bounded(
    multi: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    gate = asyncio.Event()
    idle = asyncio.Event()
    read = Counter()
    closed: set[str] = set()

    async def remote(spec: Result, **kwargs: object) -> AsyncGenerator[Result, None]:
        name = spec["host"]
        try:
            if name == "beta":
                await gate.wait()
            if name == "gamma":
                await idle.wait()
            for number in range(1000):
                read[name] += 1
                yield {"log": f"{name}-{number}"}
        finally:
            closed.add(name)

    monkeypatch.setattr(host_sources, "read_remote", remote)
    specs = parse_source_settings([multi["selection"]])
    states = {spec["hostId"]: {} for spec in specs}
    consumed = Counter()
    async with aclosing(
        host_sources.read_host_sources(empty(), specs, live=True, statuses=states)
    ) as records:
        for _ in range(8):
            record = await asyncio.wait_for(anext(records), 2)
            consumed[record["hostAddress"]] += 1
        assert consumed == {"alpha": 8}
        assert read["alpha"] <= consumed["alpha"] + 2
        gate.set()
        for _ in range(20):
            await asyncio.sleep(0)  # Let Beta's already-issued independent read finish.
        following = [await asyncio.wait_for(anext(records), 2) for _ in range(2)]
        assert "beta" in {record["hostAddress"] for record in following}
    assert closed == {"alpha", "beta", "gamma"}


async def test_host_fairness_is_independent_of_number_of_sources(
    multi: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def remote(spec: Result, **kwargs: object) -> AsyncGenerator[Result, None]:
        for number in range(1000):
            yield {"log": str(number)}

    monkeypatch.setattr(host_sources, "read_remote", remote)
    specs = parse_source_settings([multi["selection"]])
    specs.extend({**specs[0], "sourceId": f"extra-{index}"} for index in range(10))
    states = {spec["hostId"]: {} for spec in specs}
    async with aclosing(
        host_sources.read_host_sources(empty(), specs, live=False, statuses=states)
    ) as records:
        # Every host's one pending result becomes ready between submissions.
        counts = Counter()
        for index in range(36):
            record = await anext(records)
            if index >= 6:
                counts[record["hostAddress"]] += 1
            for _ in range(12):
                await asyncio.sleep(0)
        assert set(counts) == {"alpha", "beta", "gamma"}
        assert max(counts.values()) - min(counts.values()) <= 1


@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_partial_host_failure_and_frozen_run_replay(
    multi: Result, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    calls: list[str] = []

    async def remote(spec: Result, **kwargs: object) -> AsyncGenerator[Result, None]:
        if spec["host"] == "beta":
            raise ValueError("Host key is not approved")
        for number in range(2):
            yield {
                "action": spec.get("action"),
                "log": f"{spec['host']}-{number}",
                "sourceId": spec["sourceId"],
                "source": f"ssh://{spec['host']}/logs/app.log",
            }

    async def classify(log: str, *args: object) -> Result:
        calls.append(log)
        await asyncio.sleep(0)
        return {"category": "normal", "review": False}

    action_inputs: list[Result] = []

    async def action(settings: Result, result: Result) -> Result:
        action_inputs.append(dict(result))
        return {"name": "Notify", "status": "success"}

    actions = lambda: [{"name": "Notify"}]
    monkeypatch.setattr(server, "load_actions", actions)
    monkeypatch.setattr(tasks, "load_actions", actions)
    monkeypatch.setattr(server, "ensure_actions_available", lambda values: None)
    monkeypatch.setattr(server, "run_action", action)
    multi["task"]["sources"][0]["action"] = "Notify"
    monkeypatch.setattr(host_sources, "read_remote", remote)
    monkeypatch.setattr(server, "classify_log", classify)
    run = await server.launch_task(multi["task"], "manual")
    job = JOBS[run["jobId"]]
    save_task(
        {
            **multi["task"],
            "sources": [{**multi["selection"], "hostIds": [multi["hosts"][2]["id"]]}],
        }
    )
    await asyncio.wait_for(job.task, 3)
    assert job.state == "failed"
    assert len(calls) == 4 and all(not log.startswith("beta") for log in calls)
    events = [json.loads(line) async for line in job.stream()]
    rows = [event["result"] for event in events if event["type"] == "result"]
    assert len(rows) == 5 and all(row["hostId"] and row["hostName"] for row in rows)
    assert sum(bool(row.get("sourceFailure")) for row in rows) == 1
    assert len(action_inputs) == 4
    assert {row["hostAddress"] for row in action_inputs} == {"alpha", "gamma"}
    assert all(row["chunkSequence"] in {1, 2} for row in action_inputs)
    assert len(job.settings["sources"]) == 3
    states = {
        host["hostAddress"]: host["collectionState"] for host in job.snapshot()["hosts"]
    }
    assert states == {"alpha": "completed", "beta": "failed", "gamma": "completed"}
    assert task_runs(multi["task"]["id"])[0]["hosts"] == job.snapshot()["hosts"]
    JOBS.clear()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as client:
        replay = await client.post(f"/api/jobs/{job.id}/events")
        assert len(replay.text.splitlines()) == len(events)
        assert len(calls) == 4
        denied = await client.request(
            "DELETE", "/api/ssh-hosts", json={"id": multi["hosts"][2]["id"]}
        )
        assert denied.status_code == 400 and "Task" in denied.json()["error"]
