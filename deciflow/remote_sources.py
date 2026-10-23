"""Stream remote UTF-8 logs over key-authenticated, host-verified SFTP."""

import asyncio
import posixpath
from collections.abc import AsyncGenerator
from contextlib import aclosing
from hashlib import sha256
from time import monotonic

import asyncssh
from asyncssh.constants import (
    FILEXFER_TYPE_REGULAR,
    FILEXFER_TYPE_SYMLINK,
    FILEXFER_TYPE_UNKNOWN,
)

from deciflow.chunks import source_records
from deciflow.classifier import EXECUTION_CONTROL, Result
from deciflow.source_registry import source_paths, source_pattern, source_patterns
from deciflow.sources import merge_batch
from deciflow.ssh_hosts import ssh_connection_options


async def _scan_pattern(
    sftp: asyncssh.SFTPClient, pattern: str
) -> dict[str, asyncssh.SFTPAttrs]:
    try:
        matches = await sftp.glob_sftpname(pattern)
    except asyncssh.SFTPNoSuchFile:
        return {}
    parents: dict[str, str] = {}
    paths: dict[str, asyncssh.SFTPAttrs] = {}
    for match in matches:
        path, attrs = str(match.filename), match.attrs
        regular = attrs.type == FILEXFER_TYPE_REGULAR
        if not regular:
            if attrs.type not in {
                FILEXFER_TYPE_SYMLINK,
                FILEXFER_TYPE_UNKNOWN,
            }:
                continue
            try:
                attrs = await sftp.stat(path)
            except (
                asyncssh.SFTPNoSuchFile,
                asyncssh.SFTPNoSuchPath,
                asyncssh.SFTPPermissionDenied,
            ):
                continue
            if attrs.type != FILEXFER_TYPE_REGULAR:
                continue
            path = str(await sftp.realpath(path))
        else:
            parent = posixpath.dirname(path) or "."
            if parent not in parents:
                parents[parent] = str(await sftp.realpath(parent))
            path = posixpath.join(parents[parent], posixpath.basename(path))
        paths[path] = attrs
    return dict(sorted(paths.items()))


async def _scan(
    sftp: asyncssh.SFTPClient, pattern: str
) -> dict[str, asyncssh.SFTPAttrs]:
    paths: dict[str, asyncssh.SFTPAttrs] = {}
    for entry in source_paths(pattern):
        paths.update(await _scan_pattern(sftp, entry))
    return dict(sorted(paths.items()))


async def _paths(sftp: asyncssh.SFTPClient, pattern: str) -> list[str]:
    paths: dict[str, asyncssh.SFTPAttrs] = {}
    for entry in source_paths(pattern):
        matches = await _scan_pattern(sftp, entry)
        if not matches:
            raise ValueError(f"No remote regular files match: {entry}")
        paths.update(matches)
    return sorted(paths)


def _signature(attrs: asyncssh.SFTPAttrs) -> tuple[int | None, ...]:
    return attrs.size, attrs.mtime, attrs.mtime_ns, attrs.ctime, attrs.ctime_ns


async def _lines(
    sftp: asyncssh.SFTPClient,
    path: str,
    spec: Result,
    *,
    live: bool,
    from_start: bool,
    changed: asyncio.Event | None = None,
    removed: asyncio.Event | None = None,
) -> AsyncGenerator[Result, None]:
    position: int | None = None
    prefix = b""
    pending = b""
    line_number = 0
    uri = source_pattern({**spec, "path": path})
    control = EXECUTION_CONTROL.get()
    saved = control.cursors.get(uri) if control else None
    line_position = 0

    def cursor() -> Result:
        return {
            "offset": line_position,
            "line": line_number,
            "prefix": sha256(prefix).hexdigest(),
            "prefixBytes": len(prefix),
        }

    def metadata() -> Result:
        return {"_checkpoint": cursor()} if control and control.checkpoint else {}

    while True:
        if removed is not None and removed.is_set():
            if pending and (log := pending.decode("utf-8").strip()):
                yield {
                    "log": log,
                    "source": uri,
                    "line": line_number + 1,
                    "incomplete": True,
                    **(
                        {
                            "_checkpoint": {
                                **cursor(),
                                "offset": line_position + len(pending),
                                "line": line_number + 1,
                            }
                        }
                        if control and control.checkpoint
                        else {}
                    ),
                }
            return
        try:
            async with sftp.open(path, "rb", encoding=None) as file:
                attrs = await file.stat()
                size = attrs.size or 0
                if position is None:
                    position = (
                        size
                        if live
                        and not from_start
                        and not (control and control.recovering)
                        else 0
                    )
                    if saved:
                        position, line_number = int(saved["offset"]), int(saved["line"])
                        prefix = await file.read(saved["prefixBytes"], offset=0)
                        if (
                            size < position
                            or sha256(prefix).hexdigest() != saved["prefix"]
                        ):
                            raise ValueError(
                                "Remote source changed since checkpoint; automatic recovery was stopped."
                            )
                        saved = None
                    else:
                        prefix = await file.read(min(position, 256), offset=0)
                    assert position is not None
                    line_position = position
                    if control and control.checkpoint:
                        await control.checkpoint(uri, cursor())
                elif size < position or (
                    prefix and await file.read(len(prefix), offset=0) != prefix
                ):
                    if pending and (log := pending.decode("utf-8").strip()):
                        yield {
                            "log": log,
                            "source": uri,
                            "line": line_number + 1,
                            "incomplete": True,
                            **(
                                {
                                    "_checkpoint": {
                                        **cursor(),
                                        "offset": line_position + len(pending),
                                        "line": line_number + 1,
                                    }
                                }
                                if control and control.checkpoint
                                else {}
                            ),
                        }
                    position, line_number, pending, prefix = 0, 0, b"", b""
                    line_position = 0
                assert position is not None
                while chunk := await file.read(65536, offset=position):
                    position += len(chunk)
                    if not prefix:
                        prefix = await file.read(min(position, 256), offset=0)
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        line_number += 1
                        line_position += len(line) + 1
                        if log := line.decode("utf-8").strip():
                            yield {
                                "log": log,
                                "source": uri,
                                "line": line_number,
                                **metadata(),
                            }
        except asyncssh.SFTPNoSuchFile:
            if not live:
                raise
        if not live:
            if pending and (log := pending.decode("utf-8").strip()):
                line_position += len(pending)
                line_number += 1
                yield {"log": log, "source": uri, "line": line_number, **metadata()}
            return
        if changed is None:
            await asyncio.sleep(0.25)
        else:
            await changed.wait()
            changed.clear()


async def _chunks(
    sftp: asyncssh.SFTPClient,
    path: str,
    spec: Result,
    *,
    live: bool,
    from_start: bool,
    changed: asyncio.Event | None = None,
    removed: asyncio.Event | None = None,
) -> AsyncGenerator[Result, None]:
    async with aclosing(
        source_records(
            _lines(
                sftp,
                path,
                spec,
                live=live,
                from_start=from_start,
                changed=changed,
                removed=removed,
            ),
            spec,
            live=live,
        )
    ) as records:
        async for record in records:
            yield {
                **record,
                "sourceId": spec["sourceId"],
                "sourceName": spec["name"],
                "sourceType": "ssh",
                "sourcePatterns": source_patterns(spec),
                **({"actionId": spec["actionId"]} if spec.get("actionId") else {}),
            }


async def _follow(
    sftp: asyncssh.SFTPClient, spec: Result
) -> AsyncGenerator[Result, None]:
    watchers: dict[str, AsyncGenerator[Result, None]] = {}
    reads: dict[asyncio.Task[Result], str] = {}
    tick: asyncio.Task[None] | None = None
    initial = True
    changes: dict[str, asyncio.Event] = {}
    removed: dict[str, asyncio.Event] = {}
    signatures: dict[str, tuple[int | None, ...]] = {}
    last_probe = monotonic()
    try:
        while True:
            if tick is None:
                paths = await _scan(sftp, spec["path"])
                for path in watchers.keys() - paths.keys():
                    removed[path].set()
                    changes[path].set()
                now = monotonic()
                # SFTP v3 timestamps can miss same-size replacements within a second.
                probe = now - last_probe >= 1
                for path, attrs in paths.items():
                    signature = _signature(attrs)
                    if path not in watchers:
                        changes[path] = asyncio.Event()
                        removed[path] = asyncio.Event()
                        records = _chunks(
                            sftp,
                            path,
                            spec,
                            live=True,
                            from_start=not initial,
                            changed=changes[path],
                            removed=removed[path],
                        )
                        watchers[path] = records
                        reads[asyncio.create_task(anext(records))] = path
                    elif signatures.get(path) != signature:
                        changes[path].set()
                    signatures[path] = signature
                if probe:
                    for changed in changes.values():
                        changed.set()
                    last_probe = now
                initial = False
                tick = asyncio.create_task(asyncio.sleep(0.25))
            waiting: set[asyncio.Task] = {*reads, tick}
            done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is tick:
                    tick = None
                else:
                    path = reads.pop(task)
                    try:
                        record = task.result()
                    except StopAsyncIteration:
                        await watchers.pop(path).aclose()
                        changes.pop(path)
                        removed.pop(path)
                        signatures.pop(path, None)
                        continue
                    yield record
                    reads[asyncio.create_task(anext(watchers[path]))] = path
    finally:
        tasks: set[asyncio.Task] = set(reads)
        if tick is not None:
            tasks.add(tick)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for records in watchers.values():
            await records.aclose()


async def read_remote(
    spec: Result, *, live: bool = False
) -> AsyncGenerator[Result, None]:
    """Open one verified SSH connection per source; close it on completion or stop."""
    try:
        async with (
            asyncssh.connect(
                spec["host"],
                **ssh_connection_options(spec),
            ) as connection,
            connection.start_sftp_client() as sftp,
        ):
            if live:
                stream = _follow(sftp, spec)
            else:
                paths = await _paths(sftp, spec["path"])
                if not paths:
                    raise ValueError(f"No remote regular files match: {spec['path']}")
                stream = merge_batch(
                    [
                        _chunks(sftp, path, spec, live=False, from_start=True)
                        for path in paths
                    ]
                )
            async with aclosing(stream) as records:
                async for record in records:
                    yield record
    except (asyncssh.Error, OSError, TimeoutError) as error:
        raise ValueError(f"Remote source {spec['name']}: {error}") from error
