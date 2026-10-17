"""Group events from one file, preserving boundaries and bounded idle latency."""

import asyncio
import json
from collections.abc import AsyncGenerator

from classifier import Result
from result_payload import compact_result


def _combine(rows: list[Result], profile: str, size: int) -> Result:
    return {
        **rows[0],
        "log": "\n".join(row["log"] for row in rows),
        **(
            {"_checkpoint": rows[-1]["_checkpoint"]}
            if "_checkpoint" in rows[-1]
            else {}
        ),
        "lineEnd": rows[-1].get("lineEnd", rows[-1]["line"]),
        "lineCount": sum(
            row.get("lineCount", len(row["log"].splitlines())) for row in rows
        ),
        "eventCount": len(rows),
        "profile": profile,
        "chunkEvents": size,
        "incomplete": any(row.get("incomplete", False) for row in rows),
    }


async def chunk_records(
    records: AsyncGenerator[Result, None],
    profile: str,
    size: int,
    *,
    live: bool = False,
) -> AsyncGenerator[Result, None]:
    """Flush at size, EOF, rotation boundary, or one second of live inactivity."""
    rows: list[Result] = []
    pending: asyncio.Task[Result] | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(records))
            done, _ = await asyncio.wait(
                {pending}, timeout=1 if live and rows else None
            )
            if not done:
                yield _combine(rows, profile, size)
                rows = []
                continue
            try:
                row = pending.result()
            except StopAsyncIteration:
                if rows:
                    yield _combine(rows, profile, size)
                return
            pending = None
            if rows and row["line"] <= rows[-1].get("lineEnd", rows[-1]["line"]):
                yield _combine(rows, profile, size)
                rows = []
            rows.append(row)
            if len(rows) >= size or row.get("incomplete"):
                yield _combine(rows, profile, size)
                rows = []
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await records.aclose()
        await records.aclose()


def source_records(
    records: AsyncGenerator[Result, None], spec: Result, *, live: bool = False
) -> AsyncGenerator[Result, None]:
    """Select shared TEXT chunking or isolated JSONL parsing for local and SSH input."""
    if spec.get("format", "text") == "text":
        return chunk_records(records, spec["profile"], spec["chunkEvents"], live=live)
    return _jsonl_records(records, spec)


async def _jsonl_records(
    records: AsyncGenerator[Result, None], spec: Result
) -> AsyncGenerator[Result, None]:
    try:
        async for row in records:
            item = {
                **row,
                "rawInput": row["log"],
                "inputFormat": "jsonl",
                "contentField": spec["contentField"],
                "profile": spec["profile"],
                "chunkEvents": 1,
                "eventCount": 1,
                "lineCount": 1,
                "recordNumber": row["line"],
            }
            try:
                if row.get("incomplete"):
                    raise ValueError("Incomplete JSONL record at file rotation.")
                data = json.loads(row["log"])
                if not isinstance(data, dict):
                    raise TypeError("JSONL records must be objects.")
                content = data.get(spec["contentField"])
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("JSONL content field must contain nonempty text.")
                item.update(log=content, inputRecord=data)
            except (ValueError, TypeError) as error:
                item.update(error=str(error), review=False)
            yield compact_result(item)
    finally:
        await records.aclose()
