"""Keep analysis jobs alive independently of browser connections."""

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from classifier import Result


class Job:
    """Own one analysis stream and replay its events without rerunning analysis."""

    def __init__(
        self,
        settings: Result,
        events: AsyncGenerator[str, None],
        directory: Path | None = None,
    ) -> None:
        self.id = uuid4().hex
        self.directory = directory / self.id if directory else None
        self.storage_failed = False
        self.started_at = datetime.now(UTC).isoformat()
        self.finished_at: str | None = None
        self.error: str | None = None
        self.counts = {"completed": 0, "failed": 0, "actionFailed": 0}
        self.hosts: dict[str, Result] = {
            source["hostId"]: {
                "hostId": source["hostId"],
                "hostName": source["hostName"],
                "hostAddress": source["host"],
                "hostPort": source["port"],
                "collectionState": "pending",
                "completed": 0,
                "failed": 0,
            }
            for source in settings.get("sources", [])
            if source.get("hostId")
        }
        self.settings = settings
        self.state = "running"
        self.events: list[str] = []
        self.timing: str | None = None
        self.progress: Result = {"elapsedMs": 0, "activeProcessingMs": 0}
        self.changed = asyncio.Event()
        if self.directory:
            self.directory.mkdir(parents=True, mode=0o700)
            self._persist()
        self.task = asyncio.create_task(self.handle_run(events))

    def snapshot(self) -> Result:
        """Return status and the frozen settings for this execution."""
        return {
            "jobId": self.id,
            "state": self.state,
            "settings": self.settings,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "counts": self.counts,
            "hosts": list(self.hosts.values()),
            **self.progress,
            **({"error": self.error} if self.error else {}),
        }

    def _persist(self) -> None:
        if self.directory is None or self.storage_failed:
            return
        path = self.directory / "run.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.snapshot()) + "\n", encoding="utf-8")
        temporary.replace(path)

    def append(self, event: Result) -> None:
        """Retain results and terminal events; keep only the latest timing tick."""
        if event["type"] in {"start", "host-status"}:
            for host in event.get("hosts", []):
                identity = host["hostId"]
                self.hosts.setdefault(identity, {"completed": 0, "failed": 0}).update(
                    host
                )
        if event["type"] == "result" and event["result"].get("hostId") in self.hosts:
            result = event["result"]
            host = self.hosts[result["hostId"]]
            host["completed"] += 1
            if result.get("error"):
                host["failed"] += 1
        if event["type"] == "error":
            self.error = event["error"]
        if event["type"] == "result":
            self.counts["completed"] += 1
            if event["result"].get("error"):
                self.counts["failed"] += 1
            if event["result"].get("actionExecution", {}).get("status") == "failed":
                self.counts["actionFailed"] += 1
        if event["type"] == "done" and self.state != "running":
            self.finished_at = datetime.now(UTC).isoformat()
        encoded = json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n"
        for key in self.progress:
            if key in event:
                self.progress[key] = event[key]
        if event["type"] == "timing":
            self.timing = encoded
        else:
            self.events.append(encoded)
            if self.directory and not self.storage_failed:
                try:
                    with (self.directory / "events.ndjson").open(
                        "a", encoding="utf-8"
                    ) as output:
                        output.write(encoded)
                    self._persist()
                except OSError:
                    self.storage_failed = True
                    raise
        self.changed.set()

    async def handle_run(self, events: AsyncGenerator[str, None]) -> None:
        """Drain the producer even when no browser is connected."""
        try:
            async with aclosing(events):
                async for encoded in events:
                    event = json.loads(encoded)
                    if event["type"] == "done":
                        self.state = (
                            "completed" if self.state == "running" else self.state
                        )
                        if self.directory and (
                            self.counts["failed"] or self.counts["actionFailed"]
                        ):
                            self.state = "failed"
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
            self.finished_at = datetime.now(UTC).isoformat()
            self._persist()
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


def read_archived_run(root: Path, identity: str) -> tuple[Result, Path] | None:
    """Find a persisted execution by its generated ID without accepting paths."""
    if not re.fullmatch(r"[0-9a-f]{32}", identity):
        return None
    for path in root.glob(f"*/runs/{identity}/run.json"):
        return json.loads(path.read_text(encoding="utf-8")), path.parent
    return None


async def replay_archived_run(directory: Path) -> AsyncGenerator[str, None]:
    """Replay saved events without executing analysis or Actions again."""
    path = directory / "events.ndjson"
    if path.exists():
        with path.open(encoding="utf-8") as events:
            for event in events:
                yield event
