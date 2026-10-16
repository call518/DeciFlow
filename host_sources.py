"""Merge independently collected host streams with one pending chunk per host."""

from collections.abc import AsyncGenerator
from contextlib import aclosing

from classifier import Result
from remote_sources import read_remote
from source_registry import source_pattern
from sources import merge_batch


def host_metadata(spec: Result) -> Result:
    """Keep stable host identity on results, Actions, snapshots and replay."""
    return {
        "hostId": spec["hostId"],
        "hostName": spec["hostName"],
        "hostAddress": spec["host"],
        "hostPort": spec["port"],
    }


async def _read_source(
    spec: Result, live: bool, status: Result
) -> AsyncGenerator[Result, None]:
    sequence = 0
    try:
        async with aclosing(read_remote(spec, live=live)) as records:
            async for record in records:
                sequence += 1
                yield {**record, **host_metadata(spec), "chunkSequence": sequence}
    except (OSError, ValueError, UnicodeError) as error:
        status.update(collectionState="failed", error=str(error))
        yield {
            **host_metadata(spec),
            "sourceId": spec["sourceId"],
            "sourceName": spec["name"],
            "sourceType": "ssh",
            "source": source_pattern(spec),
            "sourcePatterns": [source_pattern(spec)],
            "profile": spec["profile"],
            "chunkEvents": spec["chunkEvents"],
            "log": "",
            "error": str(error),
            "sourceFailure": True,
        }


async def _read_host(
    specs: list[Result], live: bool, status: Result
) -> AsyncGenerator[Result, None]:
    status["collectionState"] = "reading"
    try:
        async with aclosing(
            merge_batch([_read_source(spec, live, status) for spec in specs])
        ) as records:
            async for record in records:
                yield record
        if status["collectionState"] != "failed":
            status["collectionState"] = "completed"
    finally:
        if status["collectionState"] == "reading":
            status["collectionState"] = "stopped"


async def read_host_sources(
    local: AsyncGenerator[Result, None],
    specs: list[Result],
    *,
    live: bool,
    statuses: dict[str, Result],
) -> AsyncGenerator[Result, None]:
    """Give each host one rotating ready slot, independently of its Source count."""
    grouped: dict[str, list[Result]] = {}
    for spec in specs:
        if spec.get("type") == "ssh":
            grouped.setdefault(spec["hostId"], []).append(spec)
    streams = [
        local,
        *(
            _read_host(items, live, statuses[identity])
            for identity, items in grouped.items()
        ),
    ]
    # merge_batch rotates ready readers to the back; slow readers stay eligible.
    # One outstanding anext per host bounds buffering and propagates backpressure.
    async with aclosing(merge_batch(streams)) as records:
        async for record in records:
            yield record
