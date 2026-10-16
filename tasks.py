"""Persist reusable Tasks and schedule executions independently of browsers."""

import asyncio
import json
import os
import re
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from actions import load_actions
from classifier import Result
from result_store import open_result_store
from source_registry import get_sources_path, load_sources, save_sources
from source_settings import parse_source_settings

DEFAULT_TASK_NAME = "DeciFlow Server Log"
DEFAULT_TASK_ID = uuid5(NAMESPACE_URL, "deciflow:task:server-log").hex
DEFAULT_SOURCE_ID = uuid5(NAMESPACE_URL, "deciflow:source:server-log").hex


def get_tasks_directory() -> Path:
    """Return Task definitions and run history storage under the shared volume."""
    return get_sources_path().parent.parent / "tasks"


def load_tasks() -> list[Result]:
    """Read definitions, including Tasks whose dependencies need repair."""
    load_sources()  # Move legacy Source host bindings into Task selections first.
    path = get_tasks_directory() / "tasks.json"
    tasks = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(tasks, list):
        raise TypeError("Invalid Task registry.")
    return tasks


def _write_tasks(tasks: list[Result]) -> None:
    path = get_tasks_directory() / "tasks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def ensure_default_task() -> None:
    """Restore the disabled server-log Task without overwriting saved settings."""
    tasks = load_tasks()
    if any(
        task["id"] == DEFAULT_TASK_ID or task["name"] == DEFAULT_TASK_NAME
        for task in tasks
    ):
        return
    sources = load_sources()
    directory = Path(
        os.getenv("DECIFLOW_LOG_DIR", "/var/log/deciflow").strip()
        or "/var/log/deciflow"
    )
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parent / directory
    pattern = "\n".join(str(directory / name) for name in ("server.log", "access.log"))
    source = next(
        (
            source
            for source in sources
            if source["id"] == DEFAULT_SOURCE_ID
            or (source["type"] == "local" and source["path"] == pattern)
        ),
        None,
    )
    if source is None:
        name = DEFAULT_TASK_NAME
        if any(source["name"].casefold() == name.casefold() for source in sources):
            name += " (Default)"
        source = {
            "id": DEFAULT_SOURCE_ID,
            "name": name,
            "type": "local",
            "path": pattern,
        }
        save_sources([*sources, source])
    _write_tasks(
        [
            *tasks,
            {
                "id": DEFAULT_TASK_ID,
                "name": DEFAULT_TASK_NAME,
                "mode": "realtime",
                "cron": "",
                "timezone": "UTC",
                "enabled": False,
                "resumeOnRestart": False,
                "sources": [
                    {
                        "sourceId": source["id"],
                        "profile": "general",
                        "chunkEvents": 1,
                        "action": "",
                    }
                ],
            },
        ]
    )


def next_run(task: Result, now: datetime) -> datetime:
    """Calculate the next five-field cron occurrence in the explicit timezone."""
    local = now.astimezone(ZoneInfo(task["timezone"]))
    return croniter(task["cron"], local).get_next(datetime).astimezone(UTC)


def save_task(value: object) -> Result:
    """Validate references and save a reusable execution configuration."""
    if not isinstance(value, dict):
        raise TypeError("Enter Task details.")
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Enter a Task name.")
    mode = value.get("mode")
    if mode not in {"batch", "realtime"}:
        raise ValueError("Select Batch or Realtime.")
    identities = value.get("sources")
    if (
        not isinstance(identities, list)
        or not identities
        or any(
            not isinstance(item, dict) or not item.get("sourceId")
            for item in identities
        )
    ):
        raise ValueError("Select at least one registered Source.")
    specs = parse_source_settings(identities)
    if len({item["sourceId"] for item in identities}) != len(identities):
        raise ValueError("Select each Source only once per Task.")
    selections: dict[str, Result] = {}
    for spec in specs:
        identity = spec["sourceId"]
        if identity not in selections:
            selections[identity] = {
                key: spec[key]
                for key in ("sourceId", "profile", "chunkEvents", "action")
                if key in spec
            }
        if spec.get("hostId"):
            selections[identity].setdefault("hostIds", []).append(spec["hostId"])
    action_names = {action["name"] for action in load_actions()}
    if any(spec.get("action") and spec["action"] not in action_names for spec in specs):
        raise ValueError("Select registered Actions or leave them empty.")
    cron = value.get("cron", "")
    timezone = value.get("timezone", "UTC")
    if not isinstance(cron, str) or not isinstance(timezone, str):
        raise TypeError("Enter a cron expression and IANA timezone.")
    cron = cron.strip()
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("Enter a valid IANA timezone, such as Asia/Seoul.") from error
    if mode == "realtime" and cron:
        raise ValueError("Realtime Tasks cannot have a cron schedule.")
    if cron and (len(cron.split()) != 5 or not croniter.is_valid(cron)):
        raise ValueError(
            "Enter a five-field cron expression: minute hour day month weekday."
        )
    enabled = value.get("enabled", True)
    resume = value.get("resumeOnRestart", False)
    if type(enabled) is not bool or type(resume) is not bool:
        raise TypeError("Automatic execution settings must be booleans.")
    identity = value.get("id") or uuid4().hex
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Invalid Task ID.")
    tasks = load_tasks()
    if value.get("id") and not any(task["id"] == identity for task in tasks):
        raise ValueError("Task not found.")
    if any(
        task["id"] != identity and task["name"].casefold() == name.strip().casefold()
        for task in tasks
    ):
        raise ValueError("Task names must be unique.")
    task = {
        "id": identity,
        "name": name.strip(),
        "mode": mode,
        "cron": cron,
        "timezone": timezone,
        "enabled": enabled,
        "resumeOnRestart": resume if mode == "realtime" else False,
        "sources": list(selections.values()),
    }
    if cron:
        next_run(task, datetime.now(UTC))
    _write_tasks([item for item in tasks if item["id"] != identity] + [task])
    return task


def set_task_enabled(identity: str, enabled: object) -> Result:
    """Persist Task availability independently of dependency validation."""
    if type(enabled) is not bool:
        raise TypeError("Task enabled state must be a boolean.")
    tasks = load_tasks()
    task = next((item for item in tasks if item["id"] == identity), None)
    if task is None:
        raise ValueError("Task not found.")
    task = {**task, "enabled": enabled}
    _write_tasks([task if item["id"] == identity else item for item in tasks])
    return task


def delete_task(identity: str) -> None:
    """Remove Task files, all stored results, and its registration."""
    tasks = load_tasks()
    if not any(task["id"] == identity for task in tasks):
        raise ValueError("Task not found.")
    directory = get_tasks_directory() / identity
    store = open_result_store(directory.parent.parent)
    if directory.exists():
        shutil.rmtree(directory)
    store.delete_task(identity)
    _write_tasks([task for task in tasks if task["id"] != identity])


def task_runs(identity: str, limit: int = 50) -> list[Result]:
    """Return the latest persisted executions, including skipped cron occurrences."""
    if not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Invalid Task ID.")
    directory = get_tasks_directory() / identity / "runs"
    _index_history(directory)
    return open_result_store(get_tasks_directory().parent).history(identity, limit)


@lru_cache(maxsize=128)
def _index_history(directory: Path) -> None:
    store = open_result_store(directory.parents[2])
    for path in directory.glob("*/run.json"):
        store.register_legacy(json.loads(path.read_text(encoding="utf-8")))


def record_unstarted_run(task: Result, state: str, trigger: str, error: str) -> Result:
    """Retain skipped/failed starts so schedules never fail silently."""
    identity = uuid4().hex
    directory = get_tasks_directory() / task["id"] / "runs" / identity
    directory.mkdir(parents=True, mode=0o700)
    now = datetime.now(UTC).isoformat()
    settings = {
        "taskId": task["id"],
        "taskName": task["name"],
        "mode": task["mode"],
        "sources": [],
        "trigger": trigger,
    }
    run = {
        "jobId": identity,
        "state": state,
        "settings": settings,
        "startedAt": now,
        "finishedAt": now,
        "error": error,
        "counts": {"completed": 0, "failed": 0, "actionFailed": 0},
    }
    (directory / "run.json").write_text(json.dumps(run) + "\n", encoding="utf-8")
    events = [
        {
            "type": "start",
            "engine": os.getenv("DECISION_ENGINE", "laya"),
            "mode": task["mode"],
            "total": 0,
        },
        {"type": "error", "error": error},
        {"type": "done", "state": state, "elapsedMs": 0, "activeProcessingMs": 0},
    ]
    store = open_result_store(get_tasks_directory().parent)
    store.create(identity, run)
    for event in events:
        store.append(identity, event, run)
    return run


def recover_interrupted_runs() -> None:
    """Mark interrupted executions stopped; never automatically retry a Batch."""
    for path in get_tasks_directory().glob("*/runs/*/run.json"):
        run = json.loads(path.read_text(encoding="utf-8"))
        if run["state"] != "running":
            continue
        run.update(
            state="stopped",
            finishedAt=datetime.now(UTC).isoformat(),
            error="Server restarted; execution was interrupted.",
        )
        path.write_text(json.dumps(run) + "\n", encoding="utf-8")
        event = {
            "type": "done",
            "state": "stopped",
            "elapsedMs": run.get("elapsedMs", 0),
            "activeProcessingMs": run.get("activeProcessingMs", 0),
        }
        store = open_result_store(get_tasks_directory().parent)
        if store.contains(run["jobId"]):
            store.append(run["jobId"], event, run)
        else:
            with (path.parent / "events.ndjson").open("a", encoding="utf-8") as events:
                events.write(json.dumps(event) + "\n")
            store.register_legacy(run)


class TaskScheduler:
    """Run cron occurrences once, skipping downtime and overlapping executions."""

    def __init__(self, launch: Callable[[Result, str], Awaitable[Result]]) -> None:
        self.launch = launch
        self.due: dict[str, tuple[tuple, datetime]] = {}

    async def tick(self, now: datetime) -> None:
        """Start due schedules and calculate the next future occurrence."""
        if not (get_tasks_directory() / "tasks.json").exists():
            ensure_default_task()
        tasks = load_tasks()
        identities = {task["id"] for task in tasks}
        self.due = {key: value for key, value in self.due.items() if key in identities}
        for task in tasks:
            identity = task["id"]
            if task["mode"] != "batch" or not task["cron"] or not task["enabled"]:
                self.due.pop(identity, None)
                continue
            signature = (task["cron"], task["timezone"])
            if identity not in self.due or self.due[identity][0] != signature:
                self.due[identity] = signature, next_run(task, now)
            if self.due[identity][1] <= now:
                self.due[identity] = signature, next_run(task, now)
                await self.launch(task, "cron")

    async def run(self) -> None:
        """Rebuild schedules at startup and resume only opted-in Realtime Tasks."""
        self.due.clear()
        ensure_default_task()
        recover_interrupted_runs()
        for task in load_tasks():
            if (
                task["enabled"]
                and task["mode"] == "realtime"
                and task["resumeOnRestart"]
            ):
                await self.launch(task, "restart")
        while True:
            await self.tick(datetime.now(UTC))
            await asyncio.sleep(1)
