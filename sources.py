"""Read a server-side log file once or follow its name across rotation."""

import asyncio
import glob
import os
from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial
from pathlib import Path
from typing import BinaryIO

import anyio

from classifier import Result


def resolve_source(value: object, *, follow: bool = False) -> Path:
    """Accept absolute paths or resolve relative paths from the server directory."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Enter a server-side log file path.")
    supplied = Path(value).expanduser()
    path = supplied if supplied.is_absolute() else Path.cwd() / supplied
    if path.exists() and not path.is_file():
        raise ValueError("Select a regular file, not a directory or device.")
    if not follow and not path.is_file():
        raise ValueError("Log file does not exist.")
    return path


async def read_file(path: Path) -> AsyncGenerator[Result, None]:
    """Yield UTF-8 lines without reading the entire batch file into memory."""
    resolve_source(str(path))
    async with await anyio.open_file(path, encoding="utf-8") as file:
        line_number = 0
        async for line in file:
            line_number += 1
            if log := line.strip():
                yield {"log": log, "source": str(path), "line": line_number}


async def follow_file(
    path: Path, *, from_start: bool = False
) -> AsyncGenerator[Result, None]:
    """Follow appended UTF-8 lines; reopen replacements and wait for recreation."""
    file: BinaryIO | None = None
    identity: tuple[int, int] | None = None
    pending = b""
    initialized = from_start or not path.exists()
    line_number = 0
    try:
        while True:
            resolve_source(str(path), follow=True)
            if file is None:
                try:
                    file = await anyio.to_thread.run_sync(lambda: path.open("rb"))
                except FileNotFoundError:
                    await anyio.sleep(0.25)
                    continue
                stat = os.fstat(file.fileno())
                identity = (stat.st_dev, stat.st_ino)
                if not initialized:
                    file.seek(0, os.SEEK_END)
                    initialized = True
                line_number = 0
            chunk = await anyio.to_thread.run_sync(file.read, 65536)
            if chunk:
                pending += chunk
                while b"\n" in pending:
                    line, pending = pending.split(b"\n", 1)
                    line_number += 1
                    if log := line.decode("utf-8").strip():
                        yield {"log": log, "source": str(path), "line": line_number}
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                # Keep draining the old descriptor until the path reappears.
                await anyio.sleep(0.25)
                continue
            rotated = (stat.st_dev, stat.st_ino) != identity
            truncated = stat.st_size < file.tell()
            if rotated or truncated:
                if pending and (log := pending.decode("utf-8").strip()):
                    yield {
                        "log": log,
                        "source": str(path),
                        "line": line_number + 1,
                        "incomplete": True,
                    }
                pending = b""
                file.close()
                file = None
                continue
            await anyio.sleep(0.25)
    finally:
        if file is not None:
            file.close()


def resolve_sources(values: object, *, follow: bool = False) -> list[Path]:
    """Expand paths/globs and deduplicate matches across directories."""
    if isinstance(values, str):
        entries = [line.strip() for line in values.splitlines() if line.strip()]
    elif isinstance(values, list) and all(isinstance(value, str) for value in values):
        entries = [value.strip() for value in values if value.strip()]
    else:
        raise ValueError("Enter file paths or wildcard patterns, one per line.")
    if not entries:
        raise ValueError("Enter at least one file path or wildcard pattern.")
    paths: list[Path] = []
    seen: set[Path] = set()
    for entry in entries:
        pattern = resolve_source(entry, follow=True)
        if glob.has_magic(str(pattern)):
            matches = [
                Path(match)
                for match in sorted(glob.glob(str(pattern), recursive=True))
                if Path(match).is_file()
            ]
            if not matches and not follow:
                raise ValueError(f"No regular files match: {entry}")
        else:
            matches = [resolve_source(entry, follow=follow)]
        for match in matches:
            path = resolve_source(str(match), follow=follow)
            target = path.resolve()
            if target not in seen:
                seen.add(target)
                paths.append(path)
    return paths


async def merge_batch(
    streams: list[AsyncGenerator[Result, None]],
) -> AsyncGenerator[Result, None]:
    """Read files concurrently, yielding ready records fairly with bounded buffers."""
    reads = {asyncio.create_task(anext(stream)): stream for stream in streams}
    try:
        while reads:
            done, _ = await asyncio.wait(reads, return_when=asyncio.FIRST_COMPLETED)
            task = next(task for task in reads if task in done)
            stream = reads.pop(task)
            try:
                record = task.result()
            except StopAsyncIteration:
                continue
            yield record
            reads[asyncio.create_task(anext(stream))] = stream
    finally:
        for task in reads:
            task.cancel()
        await asyncio.gather(*reads, return_exceptions=True)
        for stream in streams:
            await stream.aclose()


async def read_sources(paths: list[Path]) -> AsyncGenerator[Result, None]:
    """Merge batch files concurrently, preserving each file's line order."""
    async with aclosing(merge_batch([read_file(path) for path in paths])) as records:
        async for record in records:
            yield record


async def follow_sources(values: object) -> AsyncGenerator[Result, None]:
    """Merge live files and discover new glob matches with bounded per-file reads."""
    watchers: dict[Path, AsyncGenerator[Result, None]] = {}
    reads: dict[asyncio.Task[Result], Path] = {}
    tick: asyncio.Task[None] | None = None
    initial = True
    try:
        while True:
            if tick is None:
                paths = await anyio.to_thread.run_sync(
                    partial(resolve_sources, values, follow=True),
                    abandon_on_cancel=True,
                )
                for path in paths:
                    if path in watchers:
                        continue
                    records = follow_file(path, from_start=not initial)
                    watchers[path] = records
                    reads[asyncio.create_task(anext(records))] = path
                initial = False
                tick = asyncio.create_task(asyncio.sleep(0.25))
            waiting: set[asyncio.Task] = set(reads)
            waiting.add(tick)
            done, _ = await asyncio.wait(waiting, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task is tick:
                    tick = None
                    continue
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
