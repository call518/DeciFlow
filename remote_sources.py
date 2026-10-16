"""Stream remote UTF-8 logs over key-authenticated, host-verified SFTP."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing

import asyncssh

from chunks import chunk_records
from classifier import Result
from source_registry import source_pattern
from sources import merge_batch
from ssh_hosts import ssh_connection_options


async def _paths(sftp: asyncssh.SFTPClient, pattern: str) -> list[str]:
    try:
        matches = await sftp.glob(pattern)
    except asyncssh.SFTPNoSuchFile:
        return []
    return sorted(
        {str(await sftp.realpath(path)) for path in matches if await sftp.isfile(path)}
    )


async def _lines(
    sftp: asyncssh.SFTPClient, path: str, spec: Result, *, live: bool, from_start: bool
) -> AsyncGenerator[Result, None]:
    position: int | None = None
    prefix = b""
    pending = b""
    line_number = 0
    uri = source_pattern({**spec, "path": path})
    while True:
        try:
            async with sftp.open(path, "rb", encoding=None) as file:
                attrs = await file.stat()
                size = attrs.size or 0
                if position is None:
                    position = size if live and not from_start else 0
                    prefix = await file.read(min(position, 256), offset=0)
                elif size < position or (
                    prefix and await file.read(len(prefix), offset=0) != prefix
                ):
                    if pending and (log := pending.decode("utf-8").strip()):
                        yield {
                            "log": log,
                            "source": uri,
                            "line": line_number + 1,
                            "incomplete": True,
                        }
                    position, line_number, pending, prefix = 0, 0, b"", b""
                while chunk := await file.read(65536, offset=position):
                    position += len(chunk)
                    if not prefix:
                        prefix = await file.read(min(position, 256), offset=0)
                    pending += chunk
                    while b"\n" in pending:
                        line, pending = pending.split(b"\n", 1)
                        line_number += 1
                        if log := line.decode("utf-8").strip():
                            yield {"log": log, "source": uri, "line": line_number}
        except asyncssh.SFTPNoSuchFile:
            if not live:
                raise
        if not live:
            if pending and (log := pending.decode("utf-8").strip()):
                yield {"log": log, "source": uri, "line": line_number + 1}
            return
        await asyncio.sleep(0.25)


async def _chunks(
    sftp: asyncssh.SFTPClient, path: str, spec: Result, *, live: bool, from_start: bool
) -> AsyncGenerator[Result, None]:
    async with aclosing(
        chunk_records(
            _lines(sftp, path, spec, live=live, from_start=from_start),
            spec["profile"],
            spec["chunkEvents"],
            live=live,
        )
    ) as records:
        async for record in records:
            yield {
                **record,
                "sourceId": spec["sourceId"],
                "sourceName": spec["name"],
                "sourceType": "ssh",
                "sourcePatterns": [source_pattern(spec)],
                **({"action": spec["action"]} if spec.get("action") else {}),
            }


async def _follow(
    sftp: asyncssh.SFTPClient, spec: Result
) -> AsyncGenerator[Result, None]:
    watchers: dict[str, AsyncGenerator[Result, None]] = {}
    reads: dict[asyncio.Task[Result], str] = {}
    tick: asyncio.Task[None] | None = None
    initial = True
    try:
        while True:
            if tick is None:
                for path in await _paths(sftp, spec["path"]):
                    if path not in watchers:
                        records = _chunks(
                            sftp, path, spec, live=True, from_start=not initial
                        )
                        watchers[path] = records
                        reads[asyncio.create_task(anext(records))] = path
                initial = False
                tick = asyncio.create_task(asyncio.sleep(0.25))
            waiting: set[asyncio.Task] = {*reads, tick}
            done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is tick:
                    tick = None
                else:
                    path = reads.pop(task)
                    yield task.result()
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
