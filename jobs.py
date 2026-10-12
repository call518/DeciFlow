"""Keep analysis jobs alive independently of browser connections."""

import asyncio
import json
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from uuid import uuid4

from classifier import Result


class Job:
    """Own one analysis stream and replay its events without rerunning analysis."""

    def __init__(self, settings: Result, events: AsyncIterator[str]) -> None:
        self.id = uuid4().hex
        self.settings = settings
        self.state = "running"
        self.events: list[str] = []
        self.timing: str | None = None
        self.progress: Result = {"elapsedMs": 0, "activeProcessingMs": 0}
        self.changed = asyncio.Event()
        self.task = asyncio.create_task(self.handle_run(events))

    def append(self, event: Result) -> None:
        """Retain results and terminal events; keep only the latest timing tick."""
        encoded = json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n"
        for key in self.progress:
            if key in event:
                self.progress[key] = event[key]
        if event["type"] == "timing":
            self.timing = encoded
        else:
            self.events.append(encoded)
        self.changed.set()

    async def handle_run(self, events: AsyncIterator[str]) -> None:
        """Drain the producer even when no browser is connected."""
        try:
            async with aclosing(events):
                async for encoded in events:
                    event = json.loads(encoded)
                    if event["type"] == "done":
                        self.state = (
                            "completed" if self.state == "running" else self.state
                        )
                        event["state"] = self.state
                    elif event["type"] == "error":
                        self.state = "failed"
                    self.append(event)
        except asyncio.CancelledError:
            self.state = "stopped"
        except Exception as error:  # noqa: BLE001 - preserve a terminal job result
            self.state = "failed"
            self.append({"type": "error", "error": str(error)})
        finally:
            if self.state == "running":
                self.state = "completed"
            if not self.events or json.loads(self.events[-1])["type"] != "done":
                self.append(
                    {
                        "type": "done",
                        "state": self.state,
                        **self.progress,
                    }
                )
            self.changed.set()

    async def stream(self) -> AsyncGenerator[str, None]:
        """Replay retained events, then follow live events until the job ends."""
        cursor = 0
        timing = None
        while True:
            self.changed.clear()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                yield event
            if self.state != "running" and self.task.done():
                return
            if self.timing and self.timing != timing:
                timing = self.timing
                yield timing
            await self.changed.wait()

    async def stop(self) -> None:
        """Cancel analysis and its subprocesses, retaining completed results."""
        if self.task.done():
            return
        self.state = "stopped"
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        if not self.events or json.loads(self.events[-1])["type"] != "done":
            self.append({"type": "done", "state": "stopped", **self.progress})


JOBS: dict[str, Job] = {}
