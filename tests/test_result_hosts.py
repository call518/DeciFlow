"""Keep collection and processing identities on success, failure, and replay."""

from collections.abc import AsyncGenerator

import pytest

from deciflow import classifier


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize(
    "record,expected",
    [
        ({"source": "/logs/app.log", "sourceType": "local"}, ["analysis-01"]),
        ({"source": "/logs/app.log"}, ["analysis-01"]),
        ({"sourceType": "ssh", "hostAddress": "web-01"}, ["web-01"]),
        (
            {"sourceType": "hdfs", "hostId": "hdfs://cluster:8020"},
            ["hdfs://cluster:8020"],
        ),
        (
            {"sourceType": "webhdfs", "hostId": "swebhdfs://cluster:9871"},
            ["swebhdfs://cluster:9871"],
        ),
        ({}, []),
    ],
)
@pytest.mark.anyio
async def test_stream_hosts(monkeypatch, engine, record, expected):
    monkeypatch.setenv("DECIFLOW_HOST", "analysis-01")

    async def records() -> AsyncGenerator[dict, None]:
        yield {**record, "log": "event"}

    async def classify(log):
        return {"engine": engine}

    results = [
        item async for _, item in classifier.classify_stream(records(), classify)
    ]
    assert len(results) == 1
    result = results[0]
    assert result["sourceHosts"] == expected
    assert result["deciflowHost"] == "analysis-01"


@pytest.mark.anyio
async def test_failure_and_replay_hosts(monkeypatch):
    monkeypatch.setenv("DECIFLOW_HOST", "new-processor")
    recovered = {
        "_recoveredResult": True,
        "log": "old",
        "sourceHosts": ["old-source"],
        "deciflowHost": "old-processor",
    }

    async def records():
        yield {
            "log": "",
            "sourceType": "ssh",
            "hostAddress": "offline",
            "error": "failed",
        }
        yield recovered

    async def classify(log):
        raise AssertionError("Neither record needs inference")

    results = {i: r async for i, r in classifier.classify_stream(records(), classify)}
    assert results[0]["sourceHosts"] == ["offline"]
    assert results[0]["deciflowHost"] == "new-processor"
    assert results[1] == recovered


def test_system_hostname(monkeypatch):
    monkeypatch.setenv("DECIFLOW_HOST", "  ")
    monkeypatch.setattr(classifier.socket, "gethostname", lambda: "system-host")
    assert classifier.result_hosts({"source": "/log"}) == {
        "sourceHosts": ["system-host"],
        "deciflowHost": "system-host",
    }
