"""Exercise source persistence and real key-authenticated SFTP without external hosts."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import aclosing
from pathlib import Path
from typing import Any

import anyio
import anyio.lowlevel
import asyncssh
import httpx
import pytest

import remote_sources
import server
from classifier import Result
from source_registry import load_sources, save_sources, source_pattern
from source_settings import parse_source_settings, resolve_configured_sources
from ssh_hosts import get_hosts_path, save_host


@pytest.fixture
async def ssh_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Result]:
    """Serve an isolated directory with generated client and host keys."""
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    client_key = asyncssh.generate_private_key("ssh-ed25519")
    host_key = asyncssh.generate_private_key("ssh-ed25519")
    key_path = tmp_path / "client_key"
    client_key.write_private_key(key_path)
    root = tmp_path / "remote"
    root.mkdir()
    connections: set[asyncssh.SSHServerConnection] = set()

    class KeyServer(asyncssh.SSHServer):
        def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
            """Track live connections so stop/close behavior can be verified."""
            connections.add(conn)

        def connection_lost(self, exc: Exception | None) -> None:
            """Forget connections closed by the client."""
            connections.difference_update(
                conn for conn in list(connections) if conn.is_closed()
            )

        def begin_auth(self, username: str) -> bool:
            """Require authentication for every connection."""
            return True

        def public_key_auth_supported(self) -> bool:
            """Allow public-key authentication only."""
            return True

        def validate_public_key(self, username: str, key: asyncssh.SSHKey) -> bool:
            """Accept only the fixture's generated client key and username."""
            return username == "logs" and key == client_key.convert_to_public()

    listener = await asyncssh.create_server(
        KeyServer,
        "127.0.0.1",
        0,
        server_host_keys=[host_key],
        sftp_factory=lambda channel: asyncssh.SFTPServer(
            channel, chroot=os.fsencode(root)
        ),
    )
    port = listener.get_port()
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    known_hosts = get_hosts_path().parent / "known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.write_text(
        f"[127.0.0.1]:{port} {host_key.export_public_key().decode()}"
    )
    source = {
        "name": "Remote test",
        "type": "ssh",
        "host": "127.0.0.1",
        "port": port,
        "username": "logs",
        "keyPath": str(key_path),
        "path": "/logs/*.log",
    }
    connection = save_host(source)
    saved = save_sources([{**source, "hostId": connection["id"]}])[0]
    try:
        yield {
            **parse_source_settings(
                [{"sourceId": saved["id"], "hostIds": [connection["id"]]}]
            )[0],
            "sourceId": saved["id"],
            "profile": "general",
            "chunkEvents": 1,
            "root": root,
            "connections": connections,
        }
    finally:
        for conn in list(connections):
            conn.close()
            await conn.wait_closed()
        listener.close()
        await listener.wait_closed()


def test_registry_roundtrip_and_no_secret_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep definitions persistent and independent from per-run settings."""
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path))
    saved = save_sources(
        [
            {
                "name": "App logs",
                "type": "local",
                "path": "/var/log/*.log",
                "action": "ignored",
            }
        ]
    )
    assert load_sources() == saved
    spec = parse_source_settings(
        [
            {
                "sourceId": saved[0]["id"],
                "path": "/tampered",
                "host": "attacker",
                "profile": "application",
                "chunkEvents": 3,
            }
        ]
    )[0]
    assert spec["path"] == "/var/log/*.log"
    assert "host" not in spec and "action" not in spec
    assert spec["profile"] == "application"
    save_sources([])
    assert load_sources() == []
    with pytest.raises(ValueError, match="registered source"):
        parse_source_settings([{"sourceId": saved[0]["id"]}])


@pytest.mark.parametrize(
    "changes",
    [
        {"name": ""},
        {"path": None},
        {"path": "relative.log"},
        {"name": None},
        {"path": ""},
        {"type": "http"},
        {"id": "../../outside"},
    ],
)
@pytest.mark.anyio
async def test_invalid_source_does_not_replace_registry(
    ssh_source: Result, changes: Result
) -> None:
    before = load_sources()
    with pytest.raises((ValueError, TypeError)):
        save_sources([{**before[0], **changes}])
    assert load_sources() == before


@pytest.mark.anyio
async def test_sftp_batch_streams_utf8_and_metadata(ssh_source: Result) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    (directory / "app.log").write_text("hello\n\n한글 로그\nlast", encoding="utf-8")
    spec = {**ssh_source, "chunkEvents": 2, "action": "notify"}
    rows = [row async for row in remote_sources.read_remote(spec)]
    assert [row["log"] for row in rows] == ["hello\n한글 로그", "last"]
    assert rows[0]["line"] == 1 and rows[0]["lineEnd"] == 3
    assert rows[0]["source"] == source_pattern({**spec, "path": "/logs/app.log"})
    assert rows[0]["sourceId"] == spec["id"]
    assert rows[0]["action"] == "notify"
    assert rows[0]["sourcePatterns"] == [source_pattern(spec)]


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["host", "key", "missing"])
async def test_sftp_rejects_unknown_hosts_wrong_keys_and_missing_files(
    ssh_source: Result, tmp_path: Path, failure: str
) -> None:
    spec = {**ssh_source}
    if failure == "host":
        (get_hosts_path().parent / "known_hosts").write_text("")
    elif failure == "key":
        wrong = tmp_path / "wrong_key"
        asyncssh.generate_private_key("ssh-ed25519").write_private_key(wrong)
        spec["keyPath"] = str(wrong)
    with pytest.raises(ValueError):
        _ = [row async for row in remote_sources.read_remote(spec)]


@pytest.mark.anyio
async def test_sftp_realtime_discovery_append_rotation_and_stop(
    ssh_source: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    scanned = anyio.Event()
    original = remote_sources._scan

    async def handle_paths(
        sftp: asyncssh.SFTPClient, pattern: str
    ) -> dict[str, asyncssh.SFTPAttrs]:
        paths = await original(sftp, pattern)
        scanned.set()
        return paths

    monkeypatch.setattr(remote_sources, "_scan", handle_paths)
    async with aclosing(remote_sources.read_remote(ssh_source, live=True)) as stream:
        pending = asyncio.create_task(anext(stream))
        with anyio.fail_after(5):
            await scanned.wait()
            directory = ssh_source["root"] / "logs"
            directory.mkdir()
            path = directory / "new.log"
            path.write_text("new file\n")
            assert (await pending)["log"] == "new file"
            with path.open("a") as file:
                file.write("appended\n")
            assert (await anext(stream))["log"] == "appended"
            path.rename(directory / "old.txt")
            path.write_text("rotated\n")
            row = await anext(stream)
            assert row["log"] == "rotated" and row["line"] == 1
    with anyio.fail_after(5):
        while any(not conn.is_closed() for conn in ssh_source["connections"]):
            await anyio.sleep(0.01)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_mixed_registered_sources_share_provider_and_run_settings(
    ssh_source: Result, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    (directory / "app.log").write_text("remote event\n")
    local = tmp_path / "local.log"
    local.write_text("local event\n")
    remote, local_def = save_sources(
        [load_sources()[0], {"name": "Local test", "type": "local", "path": str(local)}]
    )
    calls = []

    async def handle_classify(
        log: str, selected: Any, client: httpx.AsyncClient, profile: str = "general"
    ) -> Result:
        calls.append((log, selected.name, profile))
        return {"category": "normal", "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.post("/api/sources")).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.post(
            "/api/file-source",
            headers=headers,
            json={
                "mode": "batch",
                "sources": [
                    {
                        "sourceId": source["id"],
                        "profile": "application",
                        **(
                            {"hostIds": [ssh_source["hostId"]]}
                            if source["type"] == "ssh"
                            else {}
                        ),
                    }
                    for source in (remote, local_def)
                ],
            },
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
    rows = [event["result"] for event in events if event["type"] == "result"]
    assert {row["sourceName"] for row in rows} == {"Local test", "Remote test"}
    assert sorted(calls) == [
        ("local event", engine, "application"),
        ("remote event", engine, "application"),
    ]


@pytest.mark.anyio
async def test_source_api_persists_edits_and_freezes_run_definition(
    ssh_source: Result,
) -> None:
    original = load_sources()[0]
    snapshot = parse_source_settings(
        [{"sourceId": original["id"], "hostIds": [ssh_source["hostId"]]}]
    )[0]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        assert (await client.put("/api/sources", json=[])).status_code == 403
        headers = {"Origin": "http://localhost"}
        response = await client.put(
            "/api/sources",
            headers=headers,
            json=[{**original, "name": "Renamed remote", "path": "/different/*.log"}],
        )
        assert response.status_code == 200
        current = (await client.post("/api/sources", headers=headers)).json()[
            "sources"
        ][0]
        assert current["id"] == original["id"]
        assert current["name"] == "Renamed remote"
        assert snapshot["path"] == original["path"]
        assert snapshot["name"] == original["name"]
        response = await client.put(
            "/api/sources", headers=headers, json=[current, {**current, "id": "f" * 32}]
        )
        assert response.status_code == 400
        assert load_sources() == [current]
        response = await client.put("/api/sources", headers=headers, json=[])
        assert response.status_code == 200
        assert load_sources() == []


@pytest.mark.anyio
async def test_remote_recursive_patterns_and_non_regular_files(
    ssh_source: Result,
) -> None:
    directory = ssh_source["root"] / "logs"
    (directory / "nested").mkdir(parents=True)
    (directory / "root.log").write_text("root\n")
    (directory / "nested" / "child.log").write_text("child\n")
    (directory / "directory.log").mkdir()
    spec = {**ssh_source, "path": "/logs/**/*.log"}
    rows = [row async for row in remote_sources.read_remote(spec)]
    assert {row["log"] for row in rows} == {"root", "child"}


@pytest.mark.anyio
async def test_remote_realtime_skips_existing_content_and_cancels_pending_read(
    ssh_source: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    path = directory / "app.log"
    path.write_text("existing\n")
    idle = anyio.Event()
    original = asyncssh.SFTPClientFile.read

    async def handle_read(file: Any, size: int = -1, offset: int | None = None) -> Any:
        data = await original(file, size, offset)
        if offset and size == 65536 and not data:
            idle.set()
        return data

    monkeypatch.setattr(asyncssh.SFTPClientFile, "read", handle_read)
    stream = remote_sources.read_remote(ssh_source, live=True)
    pending = asyncio.create_task(anext(stream))
    with anyio.fail_after(5):
        await idle.wait()
        with path.open("a") as file:
            file.write("new event\n")
        row = await pending
        assert row["log"] == "new event" and row["line"] == 1
    pending = asyncio.create_task(anext(stream))
    await anyio.lowlevel.checkpoint()
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    await stream.aclose()
    with anyio.fail_after(5):
        while any(not conn.is_closed() for conn in ssh_source["connections"]):
            await anyio.sleep(0.01)


@pytest.mark.anyio
async def test_known_hosts_setting_is_ignored_and_not_saved(
    ssh_source: Result,
) -> None:
    logs = ssh_source["root"] / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("event\n")
    saved = save_sources([{**ssh_source, "knownHostsPath": None}])[0]
    assert "knownHostsPath" not in saved
    assert "knownHostsPath" not in load_sources()[0]
    spec = {**ssh_source, **saved, "knownHostsPath": None}
    async with aclosing(remote_sources.read_remote(spec)) as stream:
        assert [record async for record in stream]


@pytest.mark.anyio
async def test_realtime_idle_files_do_not_reopen_for_every_discovery_scan(
    ssh_source: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    file_count = 20
    for number in range(file_count):
        (directory / f"{number}.log").write_text("existing\n")
    scans = 0
    opens = 0
    canonicalizations = 0
    scanned = anyio.Event()
    original_glob = asyncssh.SFTPClient.glob_sftpname
    original_open = asyncssh.SFTPClient.open
    original_realpath = asyncssh.SFTPClient.realpath

    async def handle_glob(client: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal scans
        matches = await original_glob(client, *args, **kwargs)
        scans += 1
        if scans >= 4:
            scanned.set()
        return matches

    def handle_open(client: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal opens
        opens += 1
        return original_open(client, *args, **kwargs)

    async def handle_realpath(client: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal canonicalizations
        canonicalizations += 1
        return await original_realpath(client, *args, **kwargs)

    monkeypatch.setattr(asyncssh.SFTPClient, "realpath", handle_realpath)
    monkeypatch.setattr(asyncssh.SFTPClient, "glob_sftpname", handle_glob)
    monkeypatch.setattr(asyncssh.SFTPClient, "open", handle_open)
    monkeypatch.setattr(remote_sources, "monotonic", lambda: 0, raising=False)
    async with aclosing(remote_sources.read_remote(ssh_source, live=True)) as stream:
        pending = asyncio.create_task(anext(stream))
        try:
            with anyio.fail_after(5):
                await scanned.wait()
            assert not pending.done()
            assert opens == file_count
            assert canonicalizations <= scans
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.anyio
async def test_remote_scan_deduplicates_links_and_ignores_broken_links(
    ssh_source: Result,
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    (directory / "file.log").write_text("one event\n")
    (directory / "alias.log").symlink_to("file.log")
    (directory / "broken.log").symlink_to("missing")
    rows = [row async for row in remote_sources.read_remote(ssh_source)]
    assert len(rows) == 1
    assert rows[0]["log"] == "one event"
    assert rows[0]["source"].endswith("/logs/file.log")


@pytest.mark.anyio
async def test_remote_replacement_probe_handles_unchanged_metadata(
    ssh_source: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    path = directory / "app.log"
    path.write_text("existing\n")
    idle = anyio.Event()
    clock = [0]
    original_read = asyncssh.SFTPClientFile.read

    async def handle_read(file: Any, size: int = -1, offset: int | None = None) -> Any:
        data = await original_read(file, size, offset)
        if offset and size == 65536 and not data:
            idle.set()
        return data

    monkeypatch.setattr(asyncssh.SFTPClientFile, "read", handle_read)
    monkeypatch.setattr(remote_sources, "monotonic", lambda: clock[0])
    monkeypatch.setattr(remote_sources, "_signature", lambda attrs: ())
    async with aclosing(remote_sources.read_remote(ssh_source, live=True)) as stream:
        pending = asyncio.create_task(anext(stream))
        with anyio.fail_after(5):
            await idle.wait()
            path.unlink()
            path.write_text("changed!\n")
            clock[0] = 1
            row = await pending
        assert row["log"] == "changed!" and row["line"] == 1


@pytest.mark.anyio
async def test_remote_deleted_glob_watchers_close_without_losing_partial_events(
    ssh_source: Result, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    paths = [directory / f"{number}.log" for number in range(20)]
    for path in paths:
        path.write_text("existing\n")
    opened: set[str] = set()
    closed: set[str] = set()
    ready = anyio.Event()
    retired = anyio.Event()
    original = remote_sources._chunks

    async def handle_chunks(
        sftp: asyncssh.SFTPClient, path: str, spec: Result, **kwargs: Any
    ) -> AsyncIterator[Result]:
        opened.add(path)
        if len(opened) == 20:
            ready.set()
        try:
            async with aclosing(original(sftp, path, spec, **kwargs)) as stream:
                async for record in stream:
                    yield record
        finally:
            closed.add(path)
            if len(closed) >= 19:
                retired.set()

    monkeypatch.setattr(remote_sources, "_chunks", handle_chunks)
    async with aclosing(remote_sources.read_remote(ssh_source, live=True)) as stream:
        pending = asyncio.create_task(anext(stream))
        try:
            with anyio.fail_after(5):
                await ready.wait()
                for path in paths[:-1]:
                    path.unlink()
                await retired.wait()
                assert len(opened - closed) == 1
                with paths[-1].open("a") as file:
                    file.write("new event\n")
                assert (await pending)["log"] == "new event"
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


def test_multiline_source_paths_validate_and_deduplicate_local_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "data"))
    first = tmp_path / "first.log"
    second = tmp_path / "second.txt"
    first.write_text("first\n")
    second.write_text("second\n")
    patterns = [str(tmp_path / "*.log"), str(first), str(second)]
    source = save_sources(
        [
            {
                "name": "Multiple files",
                "type": "local",
                "path": "\n".join([*patterns, "", str(first)]),
            }
        ]
    )[0]
    assert source["path"] == "\n".join(patterns)
    specs = parse_source_settings([{"sourceId": source["id"]}])
    files = resolve_configured_sources(specs)
    assert set(files) == {first, second}
    assert files[first]["sourcePatterns"] == patterns[:2]
    assert files[second]["sourcePatterns"] == [str(second)]


@pytest.mark.anyio
async def test_remote_multiline_paths_share_connection_and_deduplicate(
    ssh_source: Result,
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    (directory / "first.log").write_text("first\n")
    (directory / "second.txt").write_text("second\n")
    spec = {**ssh_source, "path": "/logs/*.log\n/logs/first.log\n/logs/second.txt"}
    rows = [row async for row in remote_sources.read_remote(spec)]
    assert sorted(row["log"] for row in rows) == ["first", "second"]
    assert all(len(row["sourcePatterns"]) == 3 for row in rows)
    with pytest.raises(ValueError, match="absolute POSIX"):
        save_sources([{**load_sources()[0], "path": "/logs/*.log\nrelative.log"}])


@pytest.mark.anyio
async def test_remote_multiline_realtime_discovers_each_pattern(
    ssh_source: Result,
) -> None:
    directory = ssh_source["root"] / "logs"
    directory.mkdir()
    spec = {**ssh_source, "path": "/logs/*.log\n/logs/*.txt"}
    async with aclosing(remote_sources.read_remote(spec, live=True)) as stream:
        pending = asyncio.create_task(anext(stream))
        try:
            await asyncio.sleep(0.4)
            (directory / "new.txt").write_text("new text\n")
            assert (await asyncio.wait_for(pending, 5))["log"] == "new text"
            (directory / "new.log").write_text("new log\n")
            assert (await asyncio.wait_for(anext(stream), 5))["log"] == "new log"
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
