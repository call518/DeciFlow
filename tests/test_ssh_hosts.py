"""Validate reusable SSH connections, migration, and reference boundaries."""

import json
from pathlib import Path
from types import SimpleNamespace

import asyncssh
import httpx
import pytest

import server
from classifier import Result
from source_registry import get_sources_path, load_sources, save_sources
from source_settings import parse_source_settings
from ssh_hosts import delete_host, load_hosts, save_host
from ssh_keys import add_key, delete_key, list_keys


@pytest.fixture
def connection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Result:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    add_key(
        "logs",
        asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode(),
    )
    return {
        "name": "Production",
        "host": "logs.example.com",
        "port": 22,
        "username": "reader",
        "keyPath": list_keys()[0]["privatePath"],
    }


def test_host_edit_resolves_new_runs_and_preserves_snapshots(
    connection: Result,
) -> None:
    host = save_host(connection)
    source = save_sources(
        [
            {
                "name": "Access",
                "type": "ssh",
                "path": "/logs/access.log",
                "hostId": host["id"],
            }
        ]
    )[0]
    before = parse_source_settings([{"sourceId": source["id"]}])[0]
    save_host({**host, "username": "newreader", "port": 2222})
    after = parse_source_settings(
        [{"sourceId": source["id"], "hostId": "tampered", "host": "attacker"}]
    )[0]
    assert before["username"] == "reader" and before["port"] == 22
    assert after["username"] == "newreader" and after["port"] == 2222
    assert after["host"] == connection["host"]
    persisted = json.loads(get_sources_path().read_text())[0]
    assert persisted["hostId"] == host["id"] and "keyPath" not in persisted
    with pytest.raises(ValueError, match="used"):
        delete_host(host["id"], load_sources())
    save_sources([])
    with pytest.raises(ValueError, match="used"):
        delete_host(host["id"], [before])
    with pytest.raises(ValueError, match="SSH Host"):
        delete_key("logs", [])
    delete_host(host["id"], [])
    delete_key("logs", [])


def test_legacy_sources_migrate_once_and_share_host(connection: Result) -> None:
    path = get_sources_path()
    path.parent.mkdir(parents=True)
    legacy = [
        {
            **connection,
            "id": f"{index:032x}",
            "name": f"File {index}",
            "type": "ssh",
            "path": f"/logs/{index}.log",
        }
        for index in (1, 2)
    ]
    path.write_text(json.dumps(legacy))
    migrated = load_sources()
    assert len(load_hosts()) == 1
    assert migrated[0]["hostId"] == migrated[1]["hostId"]
    assert migrated[0]["keyPath"] == connection["keyPath"]
    assert load_sources() == migrated
    assert all(
        "host" not in source and "username" not in source
        for source in json.loads(path.read_text())
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"port": True},
        {"port": 65536},
        {"host": "ssh://example.com"},
        {"username": "user@host"},
        {"keyPath": "/does/not/exist"},
        {"keyPath": "-----BEGIN PRIVATE KEY-----\nsecret"},
        {"name": ""},
        {"id": "../outside"},
    ],
)
def test_invalid_host_keeps_registry(connection: Result, changes: Result) -> None:
    host = save_host(connection)
    with pytest.raises((ValueError, TypeError)):
        save_host({**host, **changes})
    assert load_hosts() == [host]


@pytest.mark.anyio
async def test_host_api_crud_origin_and_running_references(
    connection: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        for method in ["POST", "PUT", "DELETE"]:
            assert (
                await client.request(method, "/api/ssh-hosts", json=connection)
            ).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.put("/api/ssh-hosts", json=connection, headers=headers)
        assert response.status_code == 200
        host = response.json()["hosts"][0]
        assert (await client.post("/api/ssh-hosts", headers=headers)).json()[
            "hosts"
        ] == [host]
        duplicate = await client.put(
            "/api/ssh-hosts", json={**connection, "name": "PRODUCTION"}, headers=headers
        )
        assert duplicate.status_code == 400
        changed = await client.put(
            "/api/ssh-hosts", json={**host, "port": 2222}, headers=headers
        )
        assert changed.json()["hosts"][0]["port"] == 2222
        monkeypatch.setattr(
            server,
            "JOBS",
            {
                "job": SimpleNamespace(
                    state="running", settings={"sources": [{"hostId": host["id"]}]}
                )
            },
        )
        blocked = await client.request(
            "DELETE", "/api/ssh-hosts", json={"id": host["id"]}, headers=headers
        )
        assert blocked.status_code == 400
        monkeypatch.setattr(server, "JOBS", {})
        deleted = await client.request(
            "DELETE", "/api/ssh-hosts", json={"id": host["id"]}, headers=headers
        )
        assert deleted.status_code == 200 and deleted.json()["hosts"] == []
