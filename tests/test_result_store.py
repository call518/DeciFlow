"""Verify bounded persistence, keyset pagination and full-run aggregates."""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

import server
from classifier import Result
from jobs import JOBS, Job
from result_store import SQLiteResultStore


def snapshot() -> Result:
    return {
        "jobId": "a" * 32,
        "state": "completed",
        "settings": {"mode": "batch", "taskId": "b" * 32},
        "startedAt": "2026-10-16T00:00:00Z",
    }


def event(number: int) -> Result:
    return {
        "type": "result",
        "index": number,
        "elapsedMs": number * 10,
        "result": {
            "log": f"record {number} % literal",
            "category": "normal",
            "review": number % 2 == 0,
            "elapsedMs": 2,
            "hostId": f"host-{number % 3}",
            "source": "/input.txt",
            "sourcePatterns": ["/input*.txt"],
        },
    }


def test_keyset_pages_filters_and_aggregates_stay_independent(tmp_path: Path) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    run = snapshot()
    store.create(run["jobId"], run)
    for number in range(1000):
        store.append(run["jobId"], event(number), run)
    first = store.page(run["jobId"], {}, 30)
    assert len(first["items"]) == 30 and first["hasNext"]
    assert first["items"][0]["result"]["log"].startswith("record 999 ")
    second = store.page(run["jobId"], {"before": first["items"][-1]["sequence"]}, 30)
    assert not {item["sequence"] for item in first["items"]}.intersection(
        item["sequence"] for item in second["items"]
    )
    filtered = store.page(
        run["jobId"],
        {
            "host": "host-1",
            "review": "needs-review",
            "source": "/input*.txt",
            "search": "% LITERAL",
        },
        30,
    )
    assert len(filtered["items"]) == 30
    assert all(
        item["result"]["hostId"] == "host-1" and item["result"]["review"]
        for item in filtered["items"]
    )
    stats = store.state(run["jobId"])["summary"]
    assert stats["total"] == 1000 and stats["review"] == 500
    assert stats["categories"]["all"]["normal"] == 1000
    assert stats["processingPercentiles"] == {
        "minMs": 2,
        "maxMs": 2,
        "medianMs": 2,
        "p95Ms": 2,
        "p99Ms": 2,
    }
    assert "throughputBuckets" not in stats
    with store.reader() as connection:
        plan = connection.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM events "
            "WHERE run_id=? AND kind='result' AND sequence<? "
            "ORDER BY sequence DESC LIMIT 30",
            (run["jobId"], 900),
        )
        assert any("SEARCH" in row["detail"] for row in plan)
    with pytest.raises(ValueError):
        store.page(run["jobId"], {"before": "bad"}, 30)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_paged_api_settings_reviews_export_and_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))

    async def produce() -> AsyncGenerator[str, None]:
        yield json.dumps({"type": "start", "engine": engine, "total": 300})
        for number in range(300):
            yield json.dumps(event(number))
        yield json.dumps({"type": "done", "elapsedMs": 3000})

    job = Job(
        {"mode": "batch", "taskId": "b" * 32, "sources": []},
        produce(),
        tmp_path,
    )
    JOBS[job.id] = job
    try:
        await asyncio.wait_for(job.task, 10)
        assert len(job.events) == 128
        assert job.persistent
        assert not list(tmp_path.rglob("*.json"))
        assert not list(tmp_path.rglob("*.ndjson"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
        ) as client:
            url = f"/api/jobs/{job.id}"
            assert (await client.post(url + "/results", json={})).status_code == 403
            client.headers["Origin"] = "http://localhost"
            initial = (await client.post(url + "/results", json={})).json()
            assert len(initial["items"]) == 10
            assert initial["summary"]["total"] == 300
            for invalid in (0, 31, True, "30"):
                assert (
                    await client.put("/api/settings", json={"resultsPerPage": invalid})
                ).status_code == 400
            assert (
                await client.put("/api/settings", json={"resultsPerPage": 10})
            ).status_code == 200
            smaller = (await client.post(url + "/results", json={})).json()
            assert len(smaller["items"]) == 10
            sequence = smaller["items"][0]["sequence"]
            assert (
                await client.post(
                    url + "/review", json={"sequence": sequence, "category": "security"}
                )
            ).status_code == 200
            data = (await client.post(url + "/results", json={})).json()
            assert data["items"][0]["result"]["category"] == "normal"
            assert data["items"][0]["result"]["reviewerCategory"] == "security"
            assert data["summary"]["categories"]["all"]["security"] == 0
            exported = (await client.post(url + "/export")).json()
            assert len(exported["results"]) == 300
            assert exported["results"][-1]["reviewerCategory"] == "security"
            reviewed_response = await client.post(url + "/export-reviewed")
            reviewed = reviewed_response.json()
            assert reviewed["exportScope"] == "reviewed-changes"
            assert reviewed["exported"] == 1
            assert reviewed["results"] == [exported["results"][-1]]
            assert (
                "deciflow-reviewed-results.json"
                in reviewed_response.headers["content-disposition"]
            )
            for category in ("normal", ""):
                await client.post(
                    url + "/review", json={"sequence": sequence, "category": category}
                )
                empty = (await client.post(url + "/export-reviewed")).json()
                assert empty["results"] == [] and empty["exported"] == 0
            await client.post(
                url + "/review", json={"sequence": sequence, "category": "security"}
            )
            JOBS.pop(job.id)
            archived = (await client.post(url + "/results", json={})).json()
            assert archived["summary"]["total"] == 300
            assert (await client.post(url + "/export-reviewed")).json()["exported"] == 1
            replay = await client.post(url + "/events")
            assert (
                len(
                    [
                        json.loads(line)
                        for line in replay.text.splitlines()
                        if json.loads(line)["type"] == "result"
                    ]
                )
                == 300
            )
    finally:
        await job.stop()
        JOBS.pop(job.id, None)


@pytest.mark.anyio
async def test_stop_waits_for_an_in_progress_transaction_before_terminal_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from threading import Event

    entered, release = Event(), Event()

    async def produce() -> AsyncGenerator[str, None]:
        yield json.dumps(event(0))
        await asyncio.Event().wait()

    job = Job(
        {"mode": "batch", "taskId": "b" * 32},
        produce(),
        tmp_path,
    )
    original = job.store.append

    def handle_write(run_id: str, value: Result, state: Result) -> None:
        if value["type"] == "result":
            entered.set()
            assert release.wait(5)
        original(run_id, value, state)

    monkeypatch.setattr(job.store, "append", handle_write)
    stop = None
    try:
        async with asyncio.timeout(5):
            while not entered.is_set():
                await asyncio.sleep(0.01)
            stop = asyncio.create_task(job.stop())
            await asyncio.sleep(0)
            release.set()
            await stop
        events = [json.loads(encoded) async for encoded in job.stream()]
        assert [value["type"] for value in events] == ["result", "done"]
        assert events[-1]["state"] == "stopped"
        assert job.store.state(job.id)["summary"]["total"] == 1
    finally:
        release.set()
        await job.stop()
        if stop:
            await stop


def test_task_deletion_removes_all_related_rows_only(tmp_path: Path) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    first = snapshot()
    second = {**first, "jobId": "c" * 32, "settings": {"taskId": "d" * 32}}
    for run in (first, second):
        store.create(run["jobId"], run)
        store.append(run["jobId"], event(0), run)
    store.delete_task(first["settings"]["taskId"])
    assert not store.contains(first["jobId"])
    assert store.contains(second["jobId"])
    with store.reader() as connection:
        for table in ("runs", "events", "sources"):
            assert (
                connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1
            )


def test_reviewed_export_queries_only_changes_in_bounded_batches(
    tmp_path: Path,
) -> None:
    store = SQLiteResultStore(tmp_path / "reviewed.sqlite3")
    run = snapshot()
    identity = run["jobId"]
    store.create(identity, run)
    for number in range(300):
        store.append(identity, event(number), run)
        if number % 2 == 0:
            store.review(identity, number + 1, "security")
    store.review(identity, 1, "normal")
    store.review(identity, 3, "")
    first = store.events(identity, reviewed_only=True)
    assert len(first) == 128
    second = store.events(identity, first[-1][0], reviewed_only=True)
    assert len(second) == 20
    assert store.events(identity, second[-1][0], reviewed_only=True) == []
    for _, encoded in first + second:
        result = json.loads(encoded)["result"]
        assert result["reviewerCategory"] == "security"
        assert result["category"] == "normal"
    assert store.state(identity)["summary"]["total"] == 300


@pytest.mark.parametrize(
    "durations", [[], [7], [1, 1, 1, 100], [183, 214, 270, 299], list(range(1, 101))]
)
def test_whole_run_percentiles_and_histogram_counts(
    tmp_path: Path, durations: list[int]
) -> None:
    """Check exact median/nearest-rank tails including failed records."""
    import statistics
    from math import ceil

    store = SQLiteResultStore(tmp_path / "percentiles.db")
    run = snapshot()
    store.create(run["jobId"], run)
    for number, duration in enumerate(reversed(durations)):
        item = event(number)
        item["result"]["elapsedMs"] = duration
        item["result"]["actionExecution"] = {"status": "success", "elapsedMs": 5000}
        if number == 0:
            item["result"]["error"] = "Request failed"
        store.append(run["jobId"], item, run)
    stats = store.state(run["jobId"])["summary"]
    ordered = sorted(durations)
    expected = {
        "minMs": min(ordered) if ordered else None,
        "maxMs": max(ordered) if ordered else None,
        "medianMs": statistics.median(ordered) if ordered else None,
        "p95Ms": ordered[ceil(len(ordered) * 0.95) - 1] if ordered else None,
        "p99Ms": ordered[ceil(len(ordered) * 0.99) - 1] if ordered else None,
    }
    assert stats["processingPercentiles"] == expected
    assert stats["processingMs"] == sum(durations)
    assert stats["total"] == len(durations)
    with store.reader() as connection:
        assert connection.execute(
            "SELECT COALESCE(SUM(samples),0) FROM processing_times"
        ).fetchone()[0] == len(durations)
    store.close()


@pytest.mark.parametrize("backfill_on_read", [True, False])
def test_old_runs_backfill_once_then_use_histograms(
    tmp_path: Path, backfill_on_read: bool
) -> None:
    """An existing run is migrated once and retains exact subsequent appends."""
    store = SQLiteResultStore(tmp_path / "old-times.db")
    run = snapshot()
    store.create(run["jobId"], run)
    for number, duration in enumerate([100, 200, 300, 400]):
        item = event(number)
        item["result"]["elapsedMs"] = duration
        store.append(run["jobId"], item, run)
    with store.transaction() as connection:
        connection.execute("DELETE FROM processing_times")
    store.append(run["jobId"], {"type": "done"}, run)
    assert (
        store.connection.execute("SELECT COUNT(*) FROM processing_times").fetchone()[0]
        == 0
    )
    if backfill_on_read:
        first = store.state(run["jobId"])["summary"]
        assert first["processingPercentiles"] == {
            "minMs": 100,
            "maxMs": 400,
            "medianMs": 250,
            "p95Ms": 400,
            "p99Ms": 400,
        }
    item = event(4)
    item["result"]["elapsedMs"] = 500
    store.append(run["jobId"], item, run)
    assert (
        store.state(run["jobId"])["summary"]["processingPercentiles"]["medianMs"] == 300
    )
    statements: list[str] = []
    store.connection.set_trace_callback(statements.append)
    store.state(run["jobId"])
    assert not any("FROM events" in statement for statement in statements)
    store.delete_task(run["settings"]["taskId"])
    assert (
        store.connection.execute("SELECT COUNT(*) FROM processing_times").fetchone()[0]
        == 0
    )
    store.close()
