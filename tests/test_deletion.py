"""Verify deletion blockers use saved and active references without side effects."""

from types import SimpleNamespace

import httpx
import pytest

import server


@pytest.mark.anyio
async def test_dependency_check_lists_saved_and_running_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = {
        "id": "source-1",
        "sourceId": "source-1",
        "name": "Input",
        "profile": "profile-1",
        "actionId": "notify-id",
        "hostId": "host-1",
        "keyId": "key-id",
    }
    task = {"id": "task-1", "name": "Analysis", "sources": [source]}
    host = {"id": "host-1", "name": "Remote", "keyId": "key-id"}
    monkeypatch.setattr(server, "load_tasks", lambda: [task])
    monkeypatch.setattr(server, "load_sources", lambda: [source])
    monkeypatch.setattr(server, "load_hosts", lambda: [host])
    monkeypatch.setattr(
        server,
        "JOBS",
        {
            "run-1": SimpleNamespace(
                id="run-1",
                state="running",
                settings={
                    "taskId": "task-1",
                    "taskName": "Analysis",
                    "sources": [source],
                },
            )
        },
    )
    cases = {
        "Source": "source-1",
        "Criteria": "profile-1",
        "Action": "notify-id",
        "SSH Key": "key-id",
        "SSH Host": "host-1",
        "Task": "task-1",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/delete-check", json={})).status_code == 403
        client.headers["Origin"] = "http://localhost"
        for kind, identity in cases.items():
            response = await client.post(
                "/api/delete-check", json={"kind": kind, "id": identity}
            )
            assert response.status_code == 200
            references = response.json()["references"]
            assert references == sorted(
                {item["description"] for item in response.json()["details"]},
                key=str.casefold,
            )
            assert "Running task: Analysis" in references
            if kind != "Task":
                assert "Task: Analysis" in references
            if kind == "SSH Key":
                assert "SSH Host: Remote" in references
            with pytest.raises(ValueError, match="Cannot delete while in use"):
                server.require_unused(kind, identity)
        allowed = await client.post(
            "/api/delete-check", json={"kind": "Source", "id": "unused"}
        )
        assert allowed.json() == {"references": [], "details": []}
        invalid = await client.post(
            "/api/delete-check", json={"kind": "unknown", "id": "unused"}
        )
        assert invalid.status_code == 400
