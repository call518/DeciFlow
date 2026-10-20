"""Deletion stays blocked when mutable registrations release live dependencies."""

from pathlib import Path

import pytest

import server
from classifier import Result
from config_store import save_records
from result_store import open_result_store


@pytest.fixture
def usage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[Result]:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    save_records("tasks", {})
    save_records("sources", {})
    save_records("ssh_hosts", {})
    return [
        {
            "sourceId": "source",
            "profile": "criteria",
            "actionId": "action",
            "hostId": "host",
            "keyId": "key",
        }
    ]


@pytest.mark.parametrize(
    ("kind", "identity"),
    [
        ("Source", "source"),
        ("Criteria", "criteria"),
        ("Action", "action"),
        ("SSH Host", "host"),
        ("SSH Key", "key"),
    ],
)
def test_starting_and_streaming_dependencies_block_delete(
    usage: list[Result], kind: str, identity: str
) -> None:
    with (
        server.use_source_snapshot(usage),
        pytest.raises(ValueError, match="Cannot delete"),
    ):
        server.require_unused(kind, identity)
    server.TASK_STARTING_SOURCES["task"] = usage
    try:
        with pytest.raises(ValueError, match="Cannot delete"):
            server.require_unused(kind, identity)
    finally:
        server.TASK_STARTING_SOURCES.pop("task", None)
    server.require_unused(kind, identity)


@pytest.mark.parametrize(
    ("kind", "identity"),
    [
        ("Task", "task"),
        ("Source", "source"),
        ("Criteria", "criteria"),
        ("Action", "action"),
        ("SSH Host", "host"),
        ("SSH Key", "key"),
    ],
)
def test_persisted_recovery_dependencies_block_delete(
    usage: list[Result], kind: str, identity: str
) -> None:
    store = open_result_store(server.get_data_directory())
    snapshot = {
        "jobId": "run",
        "state": "paused",
        "settings": {
            "taskId": "task",
            "taskName": "Worker",
            "sources": usage,
            "recoveryVersion": 1,
        },
    }
    store.create("run", snapshot)
    with pytest.raises(ValueError, match="Cannot delete"):
        server.require_unused(kind, identity)
    store.save_snapshot("run", {**snapshot, "state": "stopped"})
    server.require_unused(kind, identity)


@pytest.mark.anyio
async def test_direct_classification_protects_criteria(usage: list[Result]) -> None:
    from contextlib import aclosing

    from config import get_engine
    from profiles import GENERAL_PROFILE_ID

    async with aclosing(server.handle_events(["event"], get_engine())) as events:
        await anext(events)
        with pytest.raises(ValueError, match="Cannot delete"):
            server.require_unused("Criteria", GENERAL_PROFILE_ID)
    server.require_unused("Criteria", GENERAL_PROFILE_ID)


@pytest.mark.anyio
async def test_reference_details_share_delete_protection_and_are_read_only(
    usage: list[Result],
) -> None:
    import httpx

    save_records(
        "tasks",
        {
            "task": {
                "id": "task",
                "name": "Worker",
                "mode": "batch",
                "enabled": False,
                "sources": usage,
            }
        },
    )
    store = open_result_store(server.get_data_directory())
    snapshot = {
        "jobId": "run",
        "state": "paused",
        "settings": {
            "taskId": "task",
            "taskName": "Worker",
            "sources": usage,
            "recoveryVersion": 1,
            "mode": "batch",
        },
    }
    store.create("run", snapshot)
    before = server.load_tasks()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (
            await client.post(
                "/api/delete-check", json={"kind": "Source", "id": "source"}
            )
        ).status_code == 403
        for kind, identity in [
            ("Source", "source"),
            ("Criteria", "criteria"),
            ("Action", "action"),
        ]:
            response = await client.post(
                "/api/delete-check",
                json={"kind": kind, "id": identity},
                headers={"origin": "http://localhost"},
            )
            assert response.status_code == 200
            value = response.json()
            assert set(value["references"]) == {
                row["description"] for row in value["details"]
            }
            assert {row["relation"] for row in value["details"]} == {
                "Task Assignment",
                "Recoverable Run",
            }
            task = next(
                row for row in value["details"] if row["relation"] == "Task Assignment"
            )
            assert task["id"] == "task" and task["status"] == "Disabled"
            run = next(
                row for row in value["details"] if row["relation"] == "Recoverable Run"
            )
            assert run["id"] == "run" and run["status"] == "Paused"
            assert run["sourceIds"] == ["source"]
            assert not any(
                key in json_text
                for json_text in [str(value)]
                for key in ["privatePath", "ticketCache"]
            )
            with pytest.raises(ValueError, match="Cannot delete"):
                server.require_unused(kind, identity)
    assert server.load_tasks() == before
