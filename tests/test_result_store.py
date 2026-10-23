"""Verify bounded persistence, keyset pagination and full-run aggregates."""

import asyncio
import json
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest

from deciflow import server
from deciflow.classifier import Result
from deciflow.jobs import JOBS, Job
from deciflow.profiles import DEFAULT_PROFILES
from deciflow.result_store import SQLiteResultStore


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
            "criteriaGroup": "system",
            "defaultDecision": "category",
            "decisionDefinitions": DEFAULT_PROFILES[
                "4e6d5417-611e-49e0-8e23-2444a0f49ee4"
            ]["questions"],
            "decisions": {
                "category": {
                    "type": "choice",
                    "choice": "normal",
                    "probabilities": {
                        "normal": 1,
                        "warning": 0,
                        "error": 0,
                        "security": 0,
                        "other": 0,
                    },
                }
            },
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
    reopened = SQLiteResultStore(tmp_path / "results.db")
    for item in filtered["items"]:
        number = item["result"]["resultNumber"]
        assert number == int(item["result"]["log"].split()[1]) + 1
        restored = reopened.page(run["jobId"], {"before": item["sequence"] + 1}, 10)
        assert restored["items"][0]["result"]["resultNumber"] == number
    assert all(
        item["result"]["hostId"] == "host-1" and item["result"]["review"]
        for item in filtered["items"]
    )
    stats = store.state(run["jobId"])["summary"]
    assert stats["total"] == 1000 and stats["review"] == 500
    assert stats["decisionGroups"]["system:category"]["counts"]["all"]["normal"] == 1000
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
            assert len(initial["items"]) == 30
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
                    url + "/review",
                    json={
                        "sequence": sequence,
                        "question": "category",
                        "value": "security",
                    },
                )
            ).status_code == 200
            data = (await client.post(url + "/results", json={})).json()
            assert (
                data["items"][0]["result"]["decisions"]["category"]["choice"]
                == "normal"
            )
            assert (
                data["items"][0]["result"]["reviewerDecisions"]["category"]
                == "security"
            )
            assert (
                data["summary"]["decisionGroups"]["system:category"]["counts"]["all"][
                    "security"
                ]
                == 0
            )
            exported = (await client.post(url + "/export")).json()
            assert len(exported["results"]) == 300
            assert (
                exported["results"][-1]["reviewerDecisions"]["category"] == "security"
            )
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
                    url + "/review",
                    json={
                        "sequence": sequence,
                        "question": "category",
                        "value": category or None,
                    },
                )
                empty = (await client.post(url + "/export-reviewed")).json()
                assert empty["results"] == [] and empty["exported"] == 0
            await client.post(
                url + "/review",
                json={
                    "sequence": sequence,
                    "question": "category",
                    "value": "security",
                },
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
            store.review(identity, number + 1, "category", "security")
    store.review(identity, 1, "category", "normal")
    store.review(identity, 3, "category", None)
    first = store.events(identity, reviewed_only=True)
    assert len(first) == 128
    second = store.events(identity, first[-1][0], reviewed_only=True)
    assert len(second) == 20
    assert store.events(identity, second[-1][0], reviewed_only=True) == []
    for _, encoded in first + second:
        result = json.loads(encoded)["result"]
        assert result["reviewerDecisions"]["category"] == "security"
        assert result["decisions"]["category"]["choice"] == "normal"
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


def test_result_numbers_follow_completion_order_excluding_status_events(
    tmp_path: Path,
) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    run = snapshot()
    store.create(run["jobId"], run)
    store.append(run["jobId"], {"type": "start", "engine": "laya"}, run)
    store.append(run["jobId"], event(7), run)
    store.append(run["jobId"], {"type": "host-status", "hosts": []}, run)
    store.append(run["jobId"], event(0), run)
    legacy = event(2)
    del legacy["index"]
    store.append(run["jobId"], legacy, run)
    page = store.page(run["jobId"], {}, 10)
    assert [item["result"]["resultNumber"] for item in page["items"]] == [3, 2, 1]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "filters", [{}, {"after": 100}, {"through": 10000}, {"search": "record"}]
)
async def test_result_page_excludes_completions_after_its_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, filters: Result
) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    run = snapshot()
    store.create(run["jobId"], run)
    store.append(run["jobId"], {"type": "start", "engine": "laya"}, run)
    for number in range(244):
        store.append(run["jobId"], event(number), run)
    monkeypatch.setattr(server, "read_archived_run", lambda *_: run)
    monkeypatch.setattr(server, "open_result_store", lambda *_: store)
    read_page = store.page
    appended = False

    def append_then_read(run_id: str, query: Result, limit: int) -> Result:
        nonlocal appended
        if not appended:
            store.append(run_id, event(244), run)
            appended = True
        return read_page(run_id, query, limit)

    monkeypatch.setattr(store, "page", append_then_read)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app),
            base_url="http://localhost",
            headers={"Origin": "http://localhost"},
        ) as client:
            response = await client.post(
                f"/api/jobs/{run['jobId']}/results", json=filters
            )
            assert response.status_code == 200
            page = response.json()
            assert page["summary"]["total"] == 244
            if filters.get("search"):
                assert page["chartSummary"]["total"] == 244
            assert page["items"][0]["result"]["resultNumber"] == 244
            assert all(item["sequence"] <= page["sequence"] for item in page["items"])
            next_page = (
                await client.post(f"/api/jobs/{run['jobId']}/results", json={})
            ).json()
            assert next_page["summary"]["total"] == 245
            assert next_page["items"][0]["result"]["resultNumber"] == 245
    finally:
        store.close()


def test_all_decisions_remain_counted_after_reopen(tmp_path: Path) -> None:
    """Keep all decision counts across persisted pages and reopening."""
    store = SQLiteResultStore(tmp_path / "results.db")
    run = snapshot()
    store.create(run["jobId"], run)
    definitions = {
        "area": {"label": "Area", "type": "choice", "criteria": {"a": "A", "b": "B"}},
        "response": {
            "label": "Response",
            "type": "choice",
            "criteria": {"done": "Done", "pending": "Pending"},
        },
        "urgency": {"label": "Urgency", "type": "score", "criteria": ["Low", "High"]},
        "followup": {"label": "Follow-up", "type": "noul"},
    }
    for index, probability in enumerate([0, 0.25, 0.5, 0.75, 1]):
        item = event(index)
        item["result"].update(
            criteriaGroup="voc",
            profileLabel="VOC",
            defaultDecision="area",
            decisionDefinitions=definitions,
            category="a",
            uncertain=index == 2,
            decisions={
                "area": {"choice": "a"},
                "response": {"choice": "pending"},
                "urgency": {"score": 0.5},
                "followup": {"noul": probability},
            },
        )
        store.append(run["jobId"], item, run)
    failure = event(6)
    failure["result"]["error"] = "failed"
    store.append(run["jobId"], failure, run)
    expected = store.state(run["jobId"])["summary"]["decisionGroups"]
    assert expected["voc:area"]["default"]
    assert expected["voc:response"]["counts"]["all"] == {"done": 0, "pending": 5}
    assert expected["voc:urgency"]["counts"]["all"] == {"0 · Low": 0, "1 · High": 5}
    assert list(expected["voc:followup"]["counts"]["all"].values()) == [1, 1, 1, 2]
    assert sum(expected["voc:followup"]["counts"]["uncertain"].values()) == 0
    assert sum(expected["voc:response"]["counts"]["unassessed"].values()) == 5
    reopened = SQLiteResultStore(tmp_path / "results.db")
    assert reopened.state(run["jobId"])["summary"]["decisionGroups"] == expected
    reopened.close()
    store.close()


def test_processing_status_filters_combine_with_source_host_and_paging(
    tmp_path: Path,
) -> None:
    store = SQLiteResultStore(tmp_path / "results.db")
    run = snapshot()
    store.create(run["jobId"], run)
    for number in range(8):
        item = event(number)
        if number % 2:
            item["result"]["error"] = "Invalid response"
        else:
            item["result"]["actionExecution"] = {"status": "failed"}
        store.append(run["jobId"], item, run)
    for status, parity in [("successful", 0), ("failed", 1)]:
        page = store.page(run["jobId"], {"processing": status}, 10)
        assert len(page["items"]) == 4
        assert all(item["result"]["review"] == (parity == 0) for item in page["items"])
        assert store.state(run["jobId"])["summary"]["total"] == 8
    filtered = store.page(
        run["jobId"],
        {
            "processing": "failed",
            "host": "host-1",
            "source": "/input*.txt",
            "search": "record",
            "before": 8,
        },
        10,
    )
    assert [item["result"]["log"] for item in filtered["items"]] == [
        "record 1 % literal"
    ]
    assert not store.page(
        run["jobId"], {"processing": "failed", "review": "needs-review"}, 10
    )["items"]
    for invalid in ["unknown", 1, {}, None]:
        with pytest.raises(ValueError, match="processing status"):
            store.page(run["jobId"], {"processing": invalid}, 10)


@pytest.mark.parametrize(
    "filters",
    [
        {"host": "node-a"},
        {"source": "/source-a"},
        {"search": "TARGET"},
        {"review": "needs-review"},
        {"review": "no-review"},
        {"processing": "failed"},
        {
            "host": "node-a",
            "source": "/source-a",
            "search": "target",
            "processing": "successful",
        },
        {"host": "missing"},
    ],
)
def test_filtered_chart_aggregates_all_matches_independently_of_pages(
    tmp_path, filters
):
    from deciflow.decisions import needs_review

    store = SQLiteResultStore(tmp_path / "filtered.db")
    run = snapshot()
    identity = run["jobId"]
    store.create(identity, run)
    records = []
    for index in range(120):
        item = event(index)
        value = item["result"]
        value.update(
            providerResponse={"usage": {"truncated": index % 17 == 0}},
            hostId="node-a" if index % 2 else "node-b",
            sourcePatterns=["/source-a" if index % 3 else "/source-b"],
            log="target event" if index % 4 else "other event",
            review=index % 5 == 0,
        )
        choice = "normal" if index % 2 else "warning"
        value["decisions"]["category"].update(
            choice=choice,
            probabilities={
                key: int(key == choice)
                for key in value["decisions"]["category"]["probabilities"]
            },
        )
        if index % 11 == 0:
            value["error"] = "failed"
        records.append(value)
        store.append(identity, item, run)
    expected = [
        value
        for value in records
        if (filters.get("host", value["hostId"]) == value["hostId"])
        and ("source" not in filters or filters["source"] in value["sourcePatterns"])
        and filters.get("search", "").lower() in value["log"].lower()
        and (filters.get("processing") != "successful" or not value.get("error"))
        and (filters.get("processing") != "failed" or value.get("error"))
        and (
            "review" not in filters
            or (
                not value.get("error")
                and needs_review(value) == (filters["review"] == "needs-review")
            )
        )
    ]
    page = store.page(identity, filters, 10)
    chart = page["chartSummary"]
    assert chart["total"] == len(expected)
    assert chart["failed"] == sum(bool(value.get("error")) for value in expected)
    assert chart["truncated"] == sum(
        value.get("providerResponse", {}).get("usage", {}).get("truncated") is True
        for value in expected
    )
    counts = chart["decisionGroups"]["system:category"]["counts"]["all"]
    for choice in ["normal", "warning"]:
        assert counts[choice] == sum(
            not value.get("error")
            and value["decisions"]["category"]["choice"] == choice
            for value in expected
        )
    assert len(page["items"]) <= 10
    held = store.page(
        identity, {**filters, "onlySummary": True, "before": 3, "after": 0}, 10
    )
    assert held["chartSummary"] == chart
    assert "items" not in held
    assert (
        store.page(identity, {**filters, "after": 10000}, 10)["chartSummary"] == chart
    )
    assert store.state(identity)["summary"]["total"] == 120
    assert store.page(identity, {}, 10)["chartSummary"] is None
    store.close()


@pytest.mark.parametrize(
    "question,bucket,expected",
    [
        ("area", "a", [0, 2, 4, 6]),
        ("urgency", "1 · Medium", [1, 4, 7]),
        ("followup", "25–<50%", [3, 4, 5]),
    ],
)
def test_decision_value_filter_leaves_chart_counts_unchanged_across_pages(
    tmp_path: Path, question: str, bucket: str, expected: list[int]
) -> None:
    store = SQLiteResultStore(tmp_path / "decisions.db")
    run = snapshot()
    identity = run["jobId"]
    store.create(identity, run)
    definitions = {
        "area": {"type": "choice", "criteria": {"a": "A", "b": "B"}},
        "urgency": {"type": "score", "criteria": ["Low", "Medium", "High"]},
        "followup": {"type": "noul"},
    }
    for index in range(60):
        number = index // 5
        item = event(number)
        item["result"].update(
            criteriaGroup="voc" if number < 8 else "other",
            decisionDefinitions=definitions,
            decisions={
                "area": {"choice": "a" if number % 2 == 0 else "b"},
                "urgency": {"score": number % 3 + 0.2},
                "followup": {"noul": number / 11},
            },
        )
        store.append(identity, item, run)
    filters = {"decision": f"voc:{question}", "category": bucket, "search": "RECORD"}
    first = store.page(identity, filters, 10)
    second = store.page(
        identity, {**filters, "before": first["items"][-1]["sequence"]}, 10
    )
    rows = first["items"] + second["items"]
    assert [row["result"]["log"] for row in rows] == [
        f"record {number} % literal" for number in reversed(expected) for _ in range(5)
    ]
    chart = first["chartSummary"]
    assert chart["total"] == 60
    for key in ["voc:area", "voc:urgency", "voc:followup"]:
        assert sum(chart["decisionGroups"][key]["counts"]["all"].values()) == 40
    assert sum(chart["decisionGroups"]["other:area"]["counts"]["all"].values()) == 20
    assert store.page(identity, {"search": "RECORD"}, 10)["chartSummary"] == chart
    assert (
        store.page(identity, {"decision": f"voc:{question}", "category": bucket}, 10)[
            "chartSummary"
        ]
        is None
    )
    common = {"host": "host-0", "source": "/input*.txt", "search": "record"}
    assert (
        store.page(identity, {**filters, **common}, 10)["chartSummary"]
        == store.page(identity, common, 10)["chartSummary"]
    )
    assert second["chartSummary"] == chart
    assert (
        store.page(identity, {**filters, "onlySummary": True}, 10)["chartSummary"]
        == chart
    )
    assert store.state(identity)["summary"]["total"] == 60
    store.close()


def test_choice_named_all_is_a_literal_filter_value(tmp_path: Path) -> None:
    store = SQLiteResultStore(tmp_path / "literal-all.db")
    run = snapshot()
    store.create(run["jobId"], run)
    for index, choice in enumerate(["all", "other"]):
        item = event(index)
        item["result"]["decisionDefinitions"] = {
            "category": {"type": "choice", "criteria": {"all": "All", "other": "Other"}}
        }
        item["result"]["decisions"] = {"category": {"choice": choice}}
        store.append(run["jobId"], item, run)
    filters = {"decision": "system:category", "category": "all"}
    page = store.page(run["jobId"], filters, 10)
    assert len(page["items"]) == 1
    assert page["chartSummary"] is None
    assert page["items"][0]["result"]["decisions"]["category"]["choice"] == "all"
    assert (
        len(store.page(run["jobId"], {"decision": "system:category"}, 10)["items"]) == 2
    )
    store.close()
