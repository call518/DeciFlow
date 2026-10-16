"""Validate reusable SSH connections, migration, and reference boundaries."""

from pathlib import Path
from types import SimpleNamespace

import asyncssh
import httpx
import pytest

import server
from classifier import Result
from source_registry import load_sources, save_sources
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
        "keyId": list_keys()[0]["id"],
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
    before = parse_source_settings(
        [{"sourceId": source["id"], "hostIds": [host["id"]]}]
    )[0]
    save_host({**host, "username": "newreader", "port": 2222})
    after = parse_source_settings(
        [
            {
                "sourceId": source["id"],
                "hostIds": [host["id"]],
                "hostId": "tampered",
                "host": "attacker",
            }
        ]
    )[0]
    assert before["username"] == "reader" and before["port"] == 22
    assert after["username"] == "newreader" and after["port"] == 2222
    assert after["host"] == connection["host"]
    persisted = load_sources()[0]
    assert "hostId" not in persisted and "keyPath" not in persisted
    save_sources([])
    with pytest.raises(ValueError, match="used"):
        delete_host(host["id"], [before])
    with pytest.raises(ValueError, match="SSH Host"):
        delete_key(connection["keyId"], [])
    delete_host(host["id"], [])
    delete_key(connection["keyId"], [])


@pytest.mark.parametrize(
    "changes",
    [
        {"port": 0},
        {"port": True},
        {"port": 65536},
        {"host": "ssh://example.com"},
        {"username": "user@host"},
        {"keyId": "missing"},
        {"keyId": "invalid\nkey"},
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


@pytest.mark.anyio
async def test_connection_api_saved_and_draft_without_saving(
    connection: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import asynccontextmanager

    calls: list[tuple[str, Result]] = []
    sftp_checks: list[bool] = []

    @asynccontextmanager
    async def sftp():
        sftp_checks.append(True)
        yield object()

    @asynccontextmanager
    async def connect(address: str, **options: object):
        calls.append((address, options))
        yield SimpleNamespace(start_sftp_client=sftp)

    monkeypatch.setattr(asyncssh, "connect", connect)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        endpoint = "/api/ssh-hosts/test"
        assert (await client.post(endpoint, json=connection)).status_code == 403
        assert calls == []
        headers = {"Origin": "http://localhost"}
        draft = await client.post(endpoint, json=connection, headers=headers)
        assert draft.status_code == 200 and draft.json()["connected"] is True
        assert draft.json()["checkedAt"] and draft.json()["elapsedMs"] >= 0
        assert load_hosts() == []
        host = save_host(connection)
        saved = await client.post(endpoint, json={"id": host["id"]}, headers=headers)
        assert saved.json()["connected"] is True
        assert len(calls) == len(sftp_checks) == 2
        assert calls[0][1]["agent_path"] is None
        assert calls[0][1]["preferred_auth"] == "publickey"
        assert calls[0][1]["client_keys"] == [connection["keyPath"]]
        assert calls[0][1]["known_hosts"] is not None
        assert load_hosts() == [host]
        invalid = await client.post(
            endpoint, json={**connection, "port": 0}, headers=headers
        )
        assert invalid.status_code == 400 and len(calls) == 2
        assert (
            await client.post(endpoint, json={"id": "missing"}, headers=headers)
        ).status_code == 404


@pytest.mark.anyio
@pytest.mark.parametrize(
    "error",
    [
        asyncssh.PermissionDenied("Authentication failed"),
        asyncssh.HostKeyNotVerifiable("Host key not trusted"),
        asyncssh.SFTPFailure("SFTP unavailable"),
        OSError("Connection refused"),
        TimeoutError(),
    ],
)
async def test_connection_failures_report_reason_and_close_connection(
    connection: Result, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    from contextlib import asynccontextmanager

    from ssh_hosts import test_host_connection as check_connection

    closed: list[bool] = []

    @asynccontextmanager
    async def sftp():
        raise error
        yield  # pragma: no cover - async contextmanager requires a generator

    @asynccontextmanager
    async def connect(*args: object, **kwargs: object):
        try:
            yield SimpleNamespace(start_sftp_client=sftp)
        finally:
            closed.append(True)

    monkeypatch.setattr(asyncssh, "connect", connect)
    result = await check_connection(connection)
    assert result["connected"] is False and result["error"]
    assert closed == [True]
    assert load_hosts() == []


@pytest.mark.anyio
async def test_real_ssh_approvals_persist_and_ignore_cli_known_hosts(
    connection: Result, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ssh_hosts import get_hosts_directory
    from ssh_hosts import test_host_connection as check_connection

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    client_key = asyncssh.read_private_key(connection["keyPath"])
    authenticated: list[bool] = []

    class Server(asyncssh.SSHServer):
        def begin_auth(self, username: str) -> bool:
            return True

        def public_key_auth_supported(self) -> bool:
            return True

        def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:
            authenticated.append(True)
            return key.export_public_key() == client_key.export_public_key()

    async with await asyncssh.listen(
        "127.0.0.1",
        0,
        server_factory=Server,
        server_host_keys=[host_key],
        sftp_factory=asyncssh.SFTPServer,
    ) as listener:
        host = {**connection, "host": "127.0.0.1", "port": listener.get_port()}
        known = get_hosts_directory() / "known_hosts"
        unknown = await check_connection(host)
        assert unknown["connected"] is False
        assert unknown["hostKey"]["fingerprint"] == host_key.get_fingerprint()
        assert not authenticated and not known.exists()
        other_key = asyncssh.generate_private_key("ssh-ed25519")
        wrong = await check_connection(host, other_key.export_public_key().decode())
        assert wrong["connected"] is False and not known.exists()
        public = host_key.export_public_key().decode()
        approved = await check_connection(host, public)
        assert approved["connected"] is True and authenticated, approved
        assert known.stat().st_mode & 0o777 == 0o600
        assert (await check_connection(host))["connected"] is True
        line = known.read_text()
        known.write_text(
            line.replace(public.strip(), other_key.export_public_key().decode().strip())
        )
        changed = await check_connection(host, public)
        assert not changed["connected"] and "changed" in changed["error"]
        assert "hostKey" not in changed
        known.write_text("@revoked " + line)
        revoked = await check_connection(host)
        assert not revoked["connected"] and "hostKey" not in revoked
        known.unlink()
        cli_known = Path.home() / ".ssh" / "known_hosts"
        cli_known.parent.mkdir(parents=True)
        cli_known.write_text(line)
        isolated = await check_connection(host)
        assert not isolated["connected"] and isolated["hostKey"]
        assert not known.exists()
        assert (await check_connection(host, public))["connected"] is True
        assert (await check_connection(host))["connected"] is True
        assert cli_known.read_text() == line
