"""Keep analysis jobs alive independently of browser connections."""

import asyncio
import json
import re
import sqlite3
from collections import deque
from collections.abc import AsyncGenerator, Callable
from contextlib import aclosing
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from uuid import uuid4

import anyio

from classifier import EXECUTION_CONTROL, ExecutionControl, Result
from result_store import open_result_store


class Job:
    """Own one analysis stream and replay its events without rerunning analysis."""

    def __init__(
        self,
        settings: Result,
        events: AsyncGenerator[str, None],
        storage_root: Path | None = None,
        *,
        restored: Result | None = None,
    ) -> None:
        self.id = restored["jobId"] if restored else uuid4().hex
        self.persistent = storage_root is not None
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
        if restored:
            self.started_at = restored["startedAt"]
            self.counts = dict(restored["counts"])
            self.hosts = {
                host["hostId"]: dict(host) for host in restored.get("hosts", [])
            }
        self.settings = settings
        self.suspending = False
        self.state = "running"
        self.control = ExecutionControl()
        self.events: deque[str] = deque(maxlen=128)
        self.failure_events: list[str] = []
        self.timing: str | None = None
        self.progress: Result = {
            "elapsedMs": restored.get("elapsedMs", 0) if restored else 0,
            "activeProcessingMs": restored.get("activeProcessingMs", 0)
            if restored
            else 0,
        }
        if restored:
            self.control.recovering = True
            if restored["state"] in {"paused", "pausing"}:
                self.state = "paused"
                self.control.ready.clear()
        self.temporary = (
            TemporaryDirectory(prefix="deciflow-job-") if storage_root is None else None
        )
        if storage_root is not None:
            root = storage_root
        else:
            assert self.temporary is not None
            root = Path(self.temporary.name)
        self.store = open_result_store(root)
        self.store.create(self.id, self.snapshot())
        if self.persistent and settings.get("recoveryVersion") == 1:
            self.control.cursors = self.store.checkpoints(self.id)
            self.control.enqueue = self.handle_enqueue
            self.control.checkpoint = self.handle_checkpoint
            self.control.action_checkpoint = self.handle_action_checkpoint
            self.control.replay = self.handle_replay_work
        if restored:
            self._persist()
        self.changed = asyncio.Event()
        self.task = asyncio.create_task(self.handle_run(events))
        completed = [identity for identity, job in JOBS.items() if job.task.done()]
        for identity in completed[:-32]:
            JOBS.pop(identity, None)

    async def _durable(self, function: Callable[..., Any], *args: Any) -> Any:
        pending = asyncio.create_task(anyio.to_thread.run_sync(function, *args))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            raise

    async def handle_enqueue(self, record: Result) -> Result:
        """Retain the input and cursor before allowing a provider request."""
        return await self._durable(self.store.enqueue, self.id, record)

    async def handle_checkpoint(self, source: str, cursor: Result) -> None:
        """Retain the starting position of an idle Realtime reader."""
        await self._durable(self.store.checkpoint, self.id, source, cursor)

    async def handle_action_checkpoint(self, result: Result, phase: str) -> None:
        """Retain Action intent and outcome across cancellation or process loss."""
        await self._durable(self.store.action_checkpoint, self.id, result, phase)

    async def handle_replay_work(self) -> AsyncGenerator[Result, None]:
        """Replay unfinished inputs in bounded pages before reopening readers."""
        cursor = 0
        while items := await anyio.to_thread.run_sync(
            self.store.pending, self.id, cursor
        ):
            for item in items:
                cursor = item["_workId"]
                yield item

    def snapshot(self) -> Result:
        """Return status and the frozen settings for this execution."""
        return {
            "jobId": self.id,
            "pagedResults": self.persistent,
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
        if not self.persistent or self.storage_failed:
            return
        self.store.save_snapshot(self.id, self.snapshot())

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
            if not self.storage_failed:
                try:
                    self.store.append(self.id, event, self.snapshot())
                except (OSError, sqlite3.Error) as error:
                    self.storage_failed = True
                    raise OSError(f"Result storage failed: {error}") from error
            else:
                self.failure_events.append(encoded)
            self.events.append(encoded)

    async def _append_event(self, event: Result) -> None:
        pending = asyncio.create_task(anyio.to_thread.run_sync(self.append, event))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            raise
        self.changed.set()

    async def handle_run(self, events: AsyncGenerator[str, None]) -> None:
        """Drain the producer even when no browser is connected."""
        token = EXECUTION_CONTROL.set(self.control)
        try:
            async with aclosing(events):
                async for encoded in events:
                    event = json.loads(encoded)
                    if self.control.recovering and event["type"] == "start":
                        continue
                    if event["type"] == "done":
                        self.state = (
                            "completed"
                            if self.state in {"running", "pausing", "paused"}
                            else self.state
                        )
                        if self.persistent and (
                            self.counts["failed"] or self.counts["actionFailed"]
                        ):
                            self.state = "failed"
                        event["state"] = self.state
                    elif event["type"] == "error":
                        self.state = "failed"
                    await self._append_event(event)
                    if event["type"] == "result":
                        self.control.active = max(0, self.control.active - 1)
                    if self.state == "pausing" and not self.control.active:
                        self.state = "paused"
                        await anyio.to_thread.run_sync(self._persist)
                        self.changed.set()
        except asyncio.CancelledError:
            if not self.suspending:
                self.state = "stopped"
        except Exception as error:  # noqa: BLE001 - preserve a terminal job result
            self.state = "failed"
            self.append({"type": "error", "error": str(error)})
        finally:
            EXECUTION_CONTROL.reset(token)
            if not self.suspending:
                if self.state in {"running", "pausing", "paused"}:
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
            else:
                self._persist()
                self.changed.set()

    async def stream(self) -> AsyncGenerator[str, None]:
        """Replay retained events, then follow live events until the job ends."""
        cursor = 0
        timing = None
        while True:
            self.changed.clear()
            batch = await anyio.to_thread.run_sync(self.store.events, self.id, cursor)
            if batch:
                for cursor, event in batch:
                    yield event
                continue
            if self.state != "running" and self.task.done():
                for event in self.failure_events:
                    yield event
                return
            if self.timing and self.timing != timing:
                timing = self.timing
                yield timing
            await self.changed.wait()

    async def pause(self) -> None:
        """Pause admission; finish and store already admitted records first."""
        if self.task.done() or self.state not in {"running", "pausing", "paused"}:
            raise ValueError("This execution has already finished.")
        self.control.ready.clear()
        self.state = "pausing" if self.control.active else "paused"
        await anyio.to_thread.run_sync(self._persist)
        self.changed.set()

    async def resume(self) -> None:
        """Continue the same execution with its retained source position."""
        if self.task.done() or self.state not in {"running", "pausing", "paused"}:
            raise ValueError("This execution has already finished.")
        self.state = "running"
        self.control.ready.set()
        await anyio.to_thread.run_sync(self._persist)
        self.changed.set()

    async def suspend(self) -> None:
        """Release process resources while preserving a recoverable active run."""
        if self.task.done():
            return
        if self.settings.get("recoveryVersion") != 1:
            await self.stop()
            return
        self.suspending = True
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        self._persist()

    async def stop(self) -> None:
        """Cancel analysis and its subprocesses, retaining completed results."""
        if self.task.done():
            return
        self.state = "stopped"
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)
        if not self.events or json.loads(self.events[-1])["type"] != "done":
            self.append({"type": "done", "state": "stopped", **self.progress})
        self.changed.set()


JOBS: dict[str, Job] = {}


def read_archived_run(root: Path, identity: str) -> Result | None:
    """Read a persisted execution by ID directly from the database."""
    if not re.fullmatch(r"[0-9a-f]{32}", identity):
        return None
    store = open_result_store(root)
    if store.contains(identity):
        return {**store.state(identity)["snapshot"], "pagedResults": True}
    return None


async def replay_archived_run(root: Path, identity: str) -> AsyncGenerator[str, None]:
    """Replay archived events in bounded batches without rerunning decisions."""
    store = await anyio.to_thread.run_sync(open_result_store, root)
    cursor = 0
    while batch := await anyio.to_thread.run_sync(store.events, identity, cursor):
        for cursor, event in batch:
            yield event
