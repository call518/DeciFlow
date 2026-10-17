"""Persist reusable Tasks and schedule executions independently of browsers."""

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from actions import load_actions
from classifier import Result
from config_store import (
    delete_record,
    get_data_directory,
    load_records,
    save_record,
    save_records,
)
from profiles import DEFAULT_PROFILES, PROFILES
from result_store import open_result_store
from source_registry import DEFAULT_SOURCES, VOC_SOURCE, load_sources, save_sources
from source_settings import parse_source_settings

DEFAULT_TASK_NAME = "DeciFlow Server Log"
DEFAULT_SOURCE_NAME = "Sample DeciFlow Server Log"
DEFAULT_TASK_ID = uuid5(NAMESPACE_URL, "deciflow:task:server-log").hex
DEFAULT_SOURCE_ID = uuid5(NAMESPACE_URL, "deciflow:source:server-log").hex
VOC_TASK_ID = uuid5(NAMESPACE_URL, "deciflow:task:voc-consultations").hex
VOC_TASK_NAME = "VOC Consultation Review (KOR)"
SYSTEM_MESSAGE_TASK_ID = uuid5(NAMESPACE_URL, "deciflow:task:system-message").hex
SYSTEM_MESSAGE_SOURCE_ID = uuid5(NAMESPACE_URL, "deciflow:source:system-message").hex


def load_tasks() -> list[Result]:
    """Read definitions, including Tasks whose dependencies need repair."""
    return list(load_records("tasks").values())


def _write_tasks(tasks: list[Result]) -> None:
    save_records("tasks", {task["id"]: task for task in tasks})


def ensure_default_task() -> None:
    """Restore the disabled server-log Task without overwriting saved settings."""
    tasks = load_tasks()
    if any(task["id"] == DEFAULT_TASK_ID for task in tasks):
        return
    task_name = DEFAULT_TASK_NAME
    suffix = 1
    task_names = {task["name"].casefold() for task in tasks}
    while task_name.casefold() in task_names:
        suffix += 1
        task_name = f"{DEFAULT_TASK_NAME} ({suffix})"
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
        name = DEFAULT_SOURCE_NAME
        suffix = 1
        source_names = {source["name"].casefold() for source in sources}
        while name.casefold() in source_names:
            suffix += 1
            name = f"{DEFAULT_SOURCE_NAME} ({suffix})"
        source = {
            "id": DEFAULT_SOURCE_ID,
            "name": name,
            "type": "local",
            "path": pattern,
        }
        save_sources([source, *sources])
    _write_tasks(
        [
            *tasks,
            {
                "id": DEFAULT_TASK_ID,
                "name": task_name,
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
                        "actionId": "",
                    }
                ],
            },
        ]
    )


def ensure_voc_task() -> None:
    """Provide a disabled manual VOC Batch without changing existing Tasks."""
    if any(
        task["id"] == VOC_TASK_ID or task["name"].casefold() == VOC_TASK_NAME.casefold()
        for task in load_tasks()
    ):
        return
    source = next(
        source
        for source in load_sources()
        if source["id"] == VOC_SOURCE["id"]
        or source["name"].casefold() == VOC_SOURCE["name"].casefold()
        or (source["type"] == "local" and source["path"] == VOC_SOURCE["path"])
    )
    profile = (
        "consultation"
        if "consultation" in PROFILES
        else next(
            identity
            for identity, definition in PROFILES.items()
            if definition["label"].casefold()
            == DEFAULT_PROFILES["consultation"]["label"].casefold()
        )
    )
    save_record(
        "tasks",
        VOC_TASK_ID,
        {
            "id": VOC_TASK_ID,
            "name": VOC_TASK_NAME,
            "mode": "batch",
            "cron": "",
            "timezone": "UTC",
            "enabled": False,
            "resumeOnRestart": False,
            "sources": [
                {
                    "sourceId": source["id"],
                    "profile": profile,
                    "chunkEvents": 1,
                    "actionId": "",
                }
            ],
        },
    )


def ensure_system_message_task() -> None:
    """Reuse System messages and repair the untouched duplicate sample."""
    name = "System Messages"
    sources = load_sources()
    default = DEFAULT_SOURCES[0]
    source = next(
        (item for item in sources if item["id"] == default["id"]),
        None,
    )
    if source is None:
        source = next(
            (
                item
                for item in sources
                if item["name"].casefold() == default["name"].casefold()
                or (item["type"] == "local" and item["path"] == default["path"])
            ),
            None,
        )
    if source is None:
        source = dict(default)
        save_record("sources", source["id"], source)
    legacy = {
        "id": SYSTEM_MESSAGE_SOURCE_ID,
        "name": "System Message",
        "type": "local",
        "path": "/host-logs/var/log/message",
        "format": "text",
    }
    tasks = load_tasks()
    if legacy in sources:
        for task in tasks:
            changed = False
            for assignment in task["sources"]:
                if assignment["sourceId"] == SYSTEM_MESSAGE_SOURCE_ID:
                    assignment["sourceId"] = source["id"]
                    changed = True
            if changed:
                save_record("tasks", task["id"], task)
        delete_record("sources", SYSTEM_MESSAGE_SOURCE_ID)
    existing = next(
        (task for task in tasks if task["id"] == SYSTEM_MESSAGE_TASK_ID), None
    )
    if existing is not None:
        if existing["name"] == "System Message" and not any(
            task["name"].casefold() == name.casefold() for task in tasks
        ):
            existing["name"] = name
            save_record("tasks", existing["id"], existing)
        return
    if any(task["name"].casefold() == name.casefold() for task in tasks):
        return
    save_record(
        "tasks",
        SYSTEM_MESSAGE_TASK_ID,
        {
            "id": SYSTEM_MESSAGE_TASK_ID,
            "name": name,
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
                    "actionId": "",
                }
            ],
        },
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
    if not isinstance(identities, list) or any(
        not isinstance(item, dict) or not item.get("sourceId") for item in identities
    ):
        raise ValueError("Select at least one registered Source.")
    specs = (
        parse_source_settings(identities, allow_unassigned_profile=True)
        if identities
        else []
    )
    if len({item["sourceId"] for item in identities}) != len(identities):
        raise ValueError("Select each Source only once per Task.")
    selections: dict[str, Result] = {}
    for spec in specs:
        identity = spec["sourceId"]
        if identity not in selections:
            selections[identity] = {
                key: spec[key]
                for key in ("sourceId", "profile", "chunkEvents", "actionId")
                if key in spec
            }
        if spec.get("hostId"):
            selections[identity].setdefault("hostIds", []).append(spec["hostId"])
    action_ids = {action["id"] for action in load_actions()}
    if any(
        spec.get("actionId") and spec["actionId"] not in action_ids for spec in specs
    ):
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
    save_record("tasks", identity, task)
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
    save_record("tasks", identity, task)
    return task


def delete_task(identity: str) -> None:
    """Remove the Task registration and all stored execution results."""
    tasks = load_tasks()
    if not any(task["id"] == identity for task in tasks):
        raise ValueError("Task not found.")
    store = open_result_store(get_data_directory())
    store.delete_task(identity)
    delete_record("tasks", identity)


def task_runs(identity: str, limit: int = 50) -> list[Result]:
    """Return the latest persisted executions, including skipped cron occurrences."""
    if not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Invalid Task ID.")
    return open_result_store(get_data_directory()).history(identity, limit)


def record_unstarted_run(task: Result, state: str, trigger: str, error: str) -> Result:
    """Retain skipped/failed starts so schedules never fail silently."""
    identity = uuid4().hex
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
    store = open_result_store(get_data_directory())
    store.create(identity, run)
    for event in events:
        store.append(identity, event, run)
    return run


def recover_interrupted_runs() -> None:
    """Stop legacy interrupted executions while preserving checkpoint-enabled runs."""
    open_result_store(get_data_directory()).recover_interrupted()


class TaskScheduler:
    """Run cron occurrences once, skipping downtime and overlapping executions."""

    def __init__(
        self,
        launch: Callable[[Result, str], Awaitable[Result]],
        restore: Callable[[], Awaitable[set[str]]] | None = None,
    ) -> None:
        self.launch = launch
        self.restore = restore
        self.ready = asyncio.Event()
        self.due: dict[str, tuple[tuple, datetime]] = {}

    async def tick(self, now: datetime) -> None:
        """Start due schedules and calculate the next future occurrence."""
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
        """Recover interrupted runs before accepting schedules or new UI starts."""
        self.ready.clear()
        self.due.clear()
        ensure_default_task()
        recovered = await self.restore() if self.restore else set()
        recover_interrupted_runs()
        for task in load_tasks():
            if (
                task["enabled"]
                and task["mode"] == "realtime"
                and task["resumeOnRestart"]
                and task["id"] not in recovered
            ):
                await self.launch(task, "restart")
        self.ready.set()
        while True:
            await self.tick(datetime.now(UTC))
            await asyncio.sleep(1)
