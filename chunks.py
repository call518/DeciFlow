"""Group lines from one file, preserving boundaries and bounded idle latency."""

import asyncio
from collections.abc import AsyncGenerator

from classifier import Result


def _combine(rows: list[Result], profile: str, size: int) -> Result:
    return {
        **rows[0],
        "log": "\n".join(row["log"] for row in rows),
        "lineEnd": rows[-1]["line"],
        "lineCount": len(rows),
        "profile": profile,
        "chunkLines": size,
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
            if rows and row["line"] <= rows[-1]["line"]:
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
