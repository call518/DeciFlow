"""Read and follow explicitly configured sources with per-file chunking."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial
from pathlib import Path

import anyio

from deciflow.chunks import source_records
from deciflow.classifier import Result
from deciflow.source_settings import resolve_configured_sources
from deciflow.sources import follow_file, merge_batch, read_file


async def _source_chunks(
    path: Path,
    spec: Result,
    *,
    live: bool = False,
    from_start: bool = False,
    removed: asyncio.Event | None = None,
) -> AsyncGenerator[Result, None]:
    source = (
        follow_file(path, from_start=from_start, removed=removed)
        if live
        else read_file(path)
    )
    async with aclosing(source_records(source, spec, live=live)) as records:
        async for record in records:
            yield {
                **record,
                **({"actionId": spec["actionId"]} if spec.get("actionId") else {}),
                **(
                    {
                        "sourceId": spec["sourceId"],
                        "sourceName": spec["name"],
                        "sourceType": "local",
                    }
                    if spec.get("sourceId")
                    else {}
                ),
                "sourcePatterns": spec.get("sourcePatterns", [str(path)]),
            }


async def read_configured(paths: dict[Path, Result]) -> AsyncGenerator[Result, None]:
    """Merge batch files concurrently with independent profiles and chunk sizes."""
    streams = [_source_chunks(path, spec) for path, spec in paths.items()]
    async with aclosing(merge_batch(streams)) as records:
        async for record in records:
            yield record


async def follow_configured(specs: list[Result]) -> AsyncGenerator[Result, None]:
    """Merge live files and discover new glob matches with bounded per-file reads."""
    watchers: dict[Path, AsyncGenerator[Result, None]] = {}
    removed: dict[Path, asyncio.Event] = {}
    reads: dict[asyncio.Task[Result], Path] = {}
    tick: asyncio.Task[None] | None = None
    initial = True
    try:
        while True:
            if tick is None:
                paths = await anyio.to_thread.run_sync(
                    partial(resolve_configured_sources, specs, follow=True),
                    abandon_on_cancel=True,
                )
                for path in watchers.keys() - paths.keys():
                    removed[path].set()
                for path, spec in paths.items():
                    if path in watchers:
                        continue
                    removed[path] = asyncio.Event()
                    records = _source_chunks(
                        path,
                        spec,
                        live=True,
                        from_start=not initial,
                        removed=removed[path],
                    )
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
                try:
                    record = task.result()
                except StopAsyncIteration:
                    await watchers.pop(path).aclose()
                    removed.pop(path)
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
