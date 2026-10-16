"""Serve the DeciFlow UI and its existing JSON/NDJSON API."""

import asyncio
import json
import os
import platform
import socket
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime
from functools import partial
from ipaddress import ip_address
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit
from uuid import uuid4

import anyio
import httpx
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route
from uvicorn.config import LOGGING_CONFIG

from actions import (
    ensure_actions_available,
    get_action_status,
    load_actions,
    reset_action,
    run_action,
    save_actions,
    use_actions,
)
from app_settings import load_settings, save_settings
from classifier import Result, classify_log, classify_stream, parse_logs
from config import (
    JEV_CONTEXT_TOKENS,
    JEV_REQUEST_TOKENS,
    Engine,
    get_engine,
    get_jev_input_bytes,
)
from configured_sources import follow_configured, read_configured
from host_sources import host_metadata, read_host_sources
from jobs import JOBS, Job, archived_store, read_archived_run, replay_archived_run
from profiles import (
    PROFILES,
    load_profiles,
    save_profiles,
    use_profile_snapshot,
    validate_settings,
)
from source_registry import load_sources, save_sources, source_patterns
from source_settings import parse_source_settings, resolve_configured_sources
from sources import follow_sources, read_sources
from ssh_hosts import delete_host, load_hosts, save_host, test_host_connection
from ssh_keys import (
    add_key,
    add_key_from_path,
    delete_key,
    get_keys_directory,
    list_keys,
)
from tasks import (
    TaskScheduler,
    delete_task,
    get_tasks_directory,
    load_tasks,
    next_run,
    record_unstarted_run,
    save_task,
    set_task_enabled,
    task_runs,
)

ROOT = Path(__file__).resolve().parent
DEFAULT_LOG_DIR = "/var/log/deciflow"
HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/stream.js": ("stream.js", "text/javascript"),
    "/vendor/prism/prism-python-1.30.0.min.js": (
        "vendor/prism/prism-python-1.30.0.min.js",
        "text/javascript",
    ),
    "/style.css": ("style.css", "text/css"),
    "/favicon.ico": ("../images/icons/favicon.ico", "image/vnd.microsoft.icon"),
    "/icons/deciflow-icon-16.png": (
        "../images/icons/deciflow-icon-16.png",
        "image/png",
    ),
    "/icons/deciflow-icon-32.png": (
        "../images/icons/deciflow-icon-32.png",
        "image/png",
    ),
    "/logo.png": ("../images/DeciFlow-Logo.png", "image/png"),
}


def _json(status: int, data: Result) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers=HEADERS)


def _host_info() -> Result:
    hostname = socket.gethostname()
    addresses: set[str] = set()
    try:
        addresses.update(
            str(address[4][0]) for address in socket.getaddrinfo(hostname, None)
        )
    except OSError:
        pass
    # UDP connect selects the default-route address without sending any packets.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            addresses.add(connection.getsockname()[0])
    except OSError:
        pass
    addresses = {
        address
        for address in addresses
        if not ip_address(address).is_loopback
        and not ip_address(address).is_unspecified
    }
    os_name = f"{platform.system()} {platform.release()}"
    if platform.system() == "Linux":
        try:
            os_name = platform.freedesktop_os_release().get("PRETTY_NAME", os_name)
        except OSError:
            pass
    return {"hostname": hostname, "addresses": sorted(addresses), "os": os_name}


async def handle_status(request: Request) -> Response:
    """Report the active engine and its budget without exposing credentials."""
    try:
        engine = get_engine()
    except ValueError as error:
        return _json(503, {"error": str(error)})
    return _json(
        200,
        {
            "configured": engine.name == "laya" or bool(engine.api_key),
            "engine": engine.name,
            "model": engine.model,
            "workingDirectory": str(Path.cwd()),
            "profiles": {key: value["label"] for key, value in PROFILES.items()},
            "host": await anyio.to_thread.run_sync(_host_info),
            "limits": {
                "max_jev_input_bytes": get_jev_input_bytes(),
                "context_tokens": JEV_CONTEXT_TOKENS,
                "request_tokens": JEV_REQUEST_TOKENS,
            }
            if engine.name == "jev"
            else {"context_tokens": engine.context_tokens},
        },
    )


def _encode(event: Result) -> str:
    return json.dumps(event, ensure_ascii=True, allow_nan=False) + "\n"


class _ProcessingClock:
    def __init__(self) -> None:
        self.started = perf_counter()
        self.pending = 0
        self.active_since = self.started
        self.active_seconds = 0.0

    def begin(self) -> None:
        if self.pending == 0:
            self.active_since = perf_counter()
        self.pending += 1

    def end(self) -> None:
        self.pending -= 1
        if self.pending == 0:
            self.active_seconds += perf_counter() - self.active_since

    def snapshot(self) -> Result:
        now = perf_counter()
        active = self.active_seconds
        if self.pending:
            active += now - self.active_since
        return {
            "elapsedMs": round((now - self.started) * 1000),
            "activeProcessingMs": round(active * 1000),
        }


async def _timed_results(
    results: AsyncGenerator[tuple[int, Result], None], clock: _ProcessingClock
) -> AsyncGenerator[str, None]:
    pending: asyncio.Task[tuple[int, Result]] | None = None
    completed = 0
    try:
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(results))
            done, _ = await asyncio.wait({pending}, timeout=1)
            if not done:
                yield _encode({"type": "timing", **clock.snapshot()})
                continue
            try:
                index, result = pending.result()
            except StopAsyncIteration:
                break
            pending = None
            completed += 1
            yield _encode(
                {
                    "type": "result",
                    "index": index,
                    "result": result,
                    "completed": completed,
                    **clock.snapshot(),
                }
            )
    finally:
        if pending is not None:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def handle_events(
    logs: list[str],
    engine: Engine,
    profile: str = "general",
    chunk_events: int = 1,
    profile_snapshot: dict[str, Result] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream progress and cancel in-flight engine calls on client disconnect."""

    snapshot = profile_snapshot if profile_snapshot is not None else deepcopy(PROFILES)

    async def handle_records() -> AsyncGenerator[Result, None]:
        for index in range(0, len(logs), chunk_events):
            events = logs[index : index + chunk_events]
            yield {
                "log": "\n".join(events),
                "profile": profile,
                "chunkEvents": chunk_events,
                "eventCount": len(events),
                "lineCount": sum(len(event.splitlines()) for event in events),
            }

    total = (len(logs) + chunk_events - 1) // chunk_events
    clock = _ProcessingClock()
    yield _encode({"type": "start", "total": total, "engine": engine.name})
    async with httpx.AsyncClient(timeout=engine.timeout) as client:

        async def handle_classify(log: str) -> Result:
            clock.begin()
            try:
                with use_profile_snapshot(snapshot):
                    decision = (
                        await classify_log(log, engine, client)
                        if profile == "general"
                        else await classify_log(log, engine, client, profile)
                    )
                    return decision
            finally:
                clock.end()

        async with (
            aclosing(
                classify_stream(
                    handle_records(),
                    handle_classify,
                    engine.concurrency,
                )
            ) as results,
            aclosing(_timed_results(results, clock)) as events,
        ):
            async for event in events:
                yield event
    yield _encode({"type": "done", **clock.snapshot()})


def _matches_origin(origin: str, pattern: str) -> bool:
    if "*" not in pattern:
        return origin == pattern
    try:
        actual = urlsplit(origin)
        expected = urlsplit(pattern)
        hostname = expected.hostname or ""
        if not hostname.startswith("*.") or hostname.count("*") != 1:
            return False
        return (
            actual.scheme == expected.scheme
            and actual.scheme in {"http", "https"}
            and actual.port == expected.port
            and bool(actual.hostname)
            and actual.hostname.endswith(hostname[1:])
            and actual.username is None
            and expected.username is None
            and not (actual.path or actual.query or actual.fragment)
            and not (expected.path or expected.query or expected.fragment)
        )
    except ValueError:
        return False


def _allowed_origin(request: Request, *, files: bool = False) -> bool:
    origin = request.headers.get("origin", "")
    allowed = {
        entry.strip()
        for entry in os.getenv("DECIFLOW_CSRF_TRUSTED_ORIGINS", "").split(",")
        if entry.strip()
    }
    if origin and any(_matches_origin(origin, pattern) for pattern in allowed):
        return True
    if origin != f"http://{request.headers.get('host')}":
        return False
    return not files or urlsplit(origin).hostname in {"127.0.0.1", "localhost"}


async def handle_classify(request: Request) -> Response:
    """Validate a same-origin upload before opening the decision stream."""
    if not _allowed_origin(request):
        return _json(403, {"error": "Only same-origin requests are allowed."})
    chunks = bytearray()
    async for chunk in request.stream():
        chunks.extend(chunk)
    try:
        body = json.loads(chunks)
    except (ValueError, UnicodeDecodeError):
        return _json(400, {"error": "Invalid JSON request body."})
    try:
        logs = parse_logs(body.get("text") if isinstance(body, dict) else None)
        profile, chunk_events = validate_settings(
            body.get("profile", "general"),
            body.get("chunkEvents", body.get("chunkLines", 1)),
        )
    except (ValueError, TypeError) as error:
        return _json(400, {"error": str(error)})
    try:
        engine = get_engine()
    except ValueError as error:
        return _json(503, {"error": str(error)})
    if engine.name == "jev" and not engine.api_key:
        return _json(
            503,
            {"error": "Set the JEV_API_KEY environment variable on the server."},
        )
    events = handle_events(logs, engine, profile, chunk_events, deepcopy(PROFILES))
    if body.get("persist") is True:
        return _start_job(
            {
                "mode": "paste",
                "text": body["text"],
                "profile": profile,
                "chunkEvents": chunk_events,
            },
            events,
        )
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers=HEADERS,
    )


async def handle_file_events(
    values: object,
    paths: list[Path] | dict[Path, Result],
    mode: str,
    engine: Engine,
    specs: list[Result] | None = None,
    actions: list[Result] | None = None,
    profile_snapshot: dict[str, Result] | None = None,
) -> AsyncGenerator[str, None]:
    """Stream classifications from a file without buffering its full contents."""
    with use_actions(actions or []):
        snapshot = (
            profile_snapshot if profile_snapshot is not None else deepcopy(PROFILES)
        )
        clock = _ProcessingClock()
        host_states = {
            spec["hostId"]: {**host_metadata(spec), "collectionState": "pending"}
            for spec in specs or []
            if spec.get("type") == "ssh"
        }
        last_host_states = ""
        yield _encode(
            {
                "type": "start",
                "total": None,
                "mode": mode,
                "hosts": list(host_states.values()),
                "engine": engine.name,
                "sources": [str(path) for path in paths],
                "sourcePatterns": [
                    pattern for spec in specs for pattern in source_patterns(spec)
                ]
                if specs
                else values,
            }
        )
        if specs is not None and mode == "realtime":
            records = follow_configured(
                [spec for spec in specs if spec.get("type") != "ssh"]
            )
        elif isinstance(paths, dict):
            records = read_configured(paths)
        else:
            records = (
                follow_sources(values) if mode == "realtime" else read_sources(paths)
            )
        if specs and any(spec.get("type") == "ssh" for spec in specs):
            records = read_host_sources(
                records, specs, live=mode == "realtime", statuses=host_states
            )
        try:
            async with httpx.AsyncClient(timeout=engine.timeout) as client:

                async def handle_classify(log: str) -> Result:
                    clock.begin()
                    try:
                        with use_profile_snapshot(snapshot):
                            return await classify_log(log, engine, client)
                    finally:
                        clock.end()

                async def handle_record(record: Result) -> Result:
                    clock.begin()
                    try:
                        with use_profile_snapshot(snapshot):
                            profile = record.get("profile", "general")
                            if profile == "general":
                                return await classify_log(record["log"], engine, client)
                            return await classify_log(
                                record["log"], engine, client, profile
                            )
                    finally:
                        clock.end()

                async with (
                    aclosing(
                        classify_stream(
                            records,
                            handle_classify,
                            engine.concurrency,
                            classify_record=handle_record,
                        )
                    ) as results,
                    aclosing(
                        _action_results(results, actions or [], engine.name)
                    ) as acted,
                    aclosing(_timed_results(acted, clock)) as events,
                ):
                    async for event in events:
                        serialized = json.dumps(host_states)
                        if host_states and serialized != last_host_states:
                            last_host_states = serialized
                            yield _encode(
                                {
                                    "type": "host-status",
                                    "hosts": list(host_states.values()),
                                }
                            )
                        yield event
        except (OSError, UnicodeError, ValueError) as error:
            yield _encode({"type": "error", "error": f"File source stopped: {error}"})
        finally:
            await records.aclose()
        if host_states:
            yield _encode({"type": "host-status", "hosts": list(host_states.values())})
        yield _encode({"type": "done", **clock.snapshot()})


class EngineUnavailableError(ValueError):
    """Indicate a provider configuration problem before a run can start."""


async def prepare_file_execution(
    mode: str, values: object
) -> tuple[Result, AsyncGenerator[str, None]]:
    """Resolve settings once for both direct file requests and saved Tasks."""
    specs = parse_source_settings(values)
    profile_snapshot = deepcopy(PROFILES)
    actions = load_actions() if any(spec.get("action") for spec in specs) else []
    names = {action["name"] for action in actions}
    if any(spec.get("action") and spec["action"] not in names for spec in specs):
        raise ValueError("Select a registered action or None.")
    selected = {spec.get("action") for spec in specs}
    actions = [action for action in actions if action["name"] in selected]
    ensure_actions_available(actions)
    paths = await anyio.to_thread.run_sync(
        partial(resolve_configured_sources, specs, follow=mode == "realtime"),
        abandon_on_cancel=True,
    )
    ensure_actions_available(actions)

    try:
        engine = get_engine()
    except ValueError as error:
        raise EngineUnavailableError(str(error)) from error
    if engine.name == "jev" and not engine.api_key:
        raise EngineUnavailableError(
            "Set the JEV_API_KEY environment variable on the server."
        )
    settings = {"mode": mode, "sources": specs}
    return settings, handle_file_events(
        values, paths, mode, engine, specs, actions, profile_snapshot
    )


async def handle_file_source(request: Request) -> Response:
    """Start selected files, sharing the same preparation as Task executions."""
    if not _allowed_origin(request, files=True):
        return _json(
            403,
            {
                "error": "File access denied. Add this UI origin to DECIFLOW_CSRF_TRUSTED_ORIGINS."
            },
        )
    try:
        body = await request.json()
        if not isinstance(body, dict) or body.get("mode") not in {
            "batch",
            "realtime",
            "follow",
        }:
            raise ValueError("Select Batch or Realtime mode.")
        mode = "realtime" if body["mode"] == "follow" else body["mode"]
        values = body.get("sources", body.get("paths", body.get("path")))
        settings, events = await prepare_file_execution(mode, values)
    except EngineUnavailableError as error:
        return _json(503, {"error": str(error)})
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    if body.get("persist") is True:
        return _start_job(settings, events)
    return StreamingResponse(events, media_type="application/x-ndjson", headers=HEADERS)


TASK_STARTING: set[str] = set()


def active_task_job(identity: str) -> Job | None:
    """Find a Task execution which has not finished cleanup."""
    return next(
        (
            job
            for job in JOBS.values()
            if job.settings.get("taskId") == identity and not job.task.done()
        ),
        None,
    )


async def launch_task(task: Result, trigger: str) -> Result:
    """Start a nonoverlapping Task with frozen settings and persistent events."""
    identity = task["id"]
    current = next((item for item in load_tasks() if item["id"] == identity), None)
    if current is None or not current["enabled"]:
        raise ValueError("Enable the Task before running it.")
    if identity in TASK_STARTING or active_task_job(identity):
        if trigger != "manual":
            return record_unstarted_run(
                task, "skipped", trigger, "Previous execution is still running."
            )
        raise ValueError("This Task is already running.")
    TASK_STARTING.add(identity)
    try:
        try:
            settings, events = await prepare_file_execution(
                task["mode"], task["sources"]
            )
            current = next(
                (item for item in load_tasks() if item["id"] == identity), None
            )
            if current is None or not current["enabled"]:
                return record_unstarted_run(
                    task, "stopped", trigger, "Task was disabled during startup."
                )
            settings.update(taskId=identity, taskName=task["name"], trigger=trigger)
            job = Job(settings, events, get_tasks_directory() / identity / "runs")
            JOBS[job.id] = job
            return job.snapshot()
        except (ValueError, TypeError, OSError) as error:
            return record_unstarted_run(task, "failed", trigger, str(error))
    finally:
        TASK_STARTING.discard(identity)


SCHEDULER = TaskScheduler(launch_task)


def deletion_dependencies(kind: str, identity: str) -> list[str]:
    """Describe saved and live references that prevent deleting an item."""
    if kind not in {"Task", "Source", "Criteria", "Action", "SSH Key", "SSH Host"}:
        raise ValueError("Invalid item type.")
    references: set[str] = set()
    key_path = (get_keys_directory() / identity / "private_key").resolve()

    def matches(source: Result) -> bool:
        if kind == "Source":
            return source.get("sourceId", source.get("id")) == identity
        if kind == "Criteria":
            return source.get("profile") == identity
        if kind == "Action":
            return source.get("action") == identity
        if kind == "SSH Host":
            return source.get("hostId") == identity or identity in source.get(
                "hostIds", []
            )
        return (
            kind == "SSH Key"
            and bool(source.get("keyPath"))
            and (Path(source["keyPath"]).resolve() == key_path)
        )

    if kind != "Task":
        for task in load_tasks():
            if any(matches(source) for source in task["sources"]):
                references.add(f"Task: {task['name']}")
    if kind in {"SSH Key", "SSH Host"}:
        for source in load_sources():
            if matches(source):
                references.add(f"Source: {source['name']}")
    if kind == "SSH Key":
        for host in load_hosts():
            if matches(host):
                references.add(f"SSH Host: {host['name']}")
    for job_id, job in list(JOBS.items()):
        if job.state != "running":
            continue
        if (kind == "Task" and job.settings.get("taskId") == identity) or any(
            matches(source) for source in job.settings.get("sources", [])
        ):
            references.add(f"Running task: {job.settings.get('taskName', job_id)}")
    if kind == "Task" and identity in TASK_STARTING:
        references.add("Task execution is starting")
    return sorted(references, key=str.casefold)


def require_unused(kind: str, identity: object) -> None:
    """Recheck dependencies when a destructive request is submitted."""
    if not isinstance(identity, str):
        raise TypeError("Select an item to delete.")
    references = deletion_dependencies(kind, identity)
    if references:
        raise ValueError("Cannot delete while in use. " + "; ".join(references))


async def handle_delete_check(request: Request) -> Response:
    """Read current deletion blockers without changing registrations or files."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Dependency checks require a trusted UI origin."})
    try:
        body = await request.json()
        if (
            not isinstance(body, dict)
            or not isinstance(body.get("id"), str)
            or not isinstance(body.get("kind"), str)
        ):
            raise TypeError("Select an item to check.")
        references = await anyio.to_thread.run_sync(
            deletion_dependencies, body["kind"], body["id"]
        )
        return _json(200, {"references": references})
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})


async def handle_tasks(request: Request) -> Response:
    """Manage Tasks and execute them only from trusted file-access origins."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Task management requires a trusted UI origin."})
    try:
        if request.method == "PUT":
            saved = save_task(await request.json())
            if not saved["enabled"]:
                SCHEDULER.due.pop(saved["id"], None)
                job = active_task_job(saved["id"])
                if job:
                    await job.stop()
        elif request.method == "DELETE":
            body = await request.json()
            if not isinstance(body, dict) or not isinstance(body.get("id"), str):
                raise ValueError("Select a Task.")
            identity = body["id"]
            if identity in TASK_STARTING or active_task_job(identity):
                return _json(409, {"error": "Stop the Task before deleting it."})
            await anyio.to_thread.run_sync(delete_task, identity)
            for job_id, job in list(JOBS.items()):
                if job.settings.get("taskId") == identity:
                    JOBS.pop(job_id)
            SCHEDULER.due.pop(identity, None)
        tasks = []
        for task in load_tasks():
            active = active_task_job(task["id"])
            runs = await anyio.to_thread.run_sync(
                partial(task_runs, task["id"], limit=1)
            )
            pending = SCHEDULER.due.get(task["id"])
            upcoming = (
                (
                    pending[1]
                    if pending and pending[0] == (task["cron"], task["timezone"])
                    else next_run(task, datetime.now(UTC))
                )
                if task["mode"] == "batch" and task["cron"] and task["enabled"]
                else None
            )
            tasks.append(
                {
                    **task,
                    "latestRun": runs[0] if runs else None,
                    "activeRun": active.snapshot() if active else None,
                    "starting": task["id"] in TASK_STARTING,
                    "nextRunAt": upcoming.isoformat() if upcoming else None,
                }
            )
        return _json(200, {"tasks": tasks})
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})


async def handle_task_operation(request: Request) -> Response:
    """Start, stop, or list executions of a registered Task."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Task access requires a trusted UI origin."})
    identity = request.path_params["task_id"]
    task = next((item for item in load_tasks() if item["id"] == identity), None)
    if task is None:
        return _json(404, {"error": "Task not found."})
    operation = request.url.path.rsplit("/", 1)[-1]
    try:
        if operation == "enabled":
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Enter Task enabled state.")
            updated = set_task_enabled(identity, body.get("enabled"))
            if not updated["enabled"]:
                SCHEDULER.due.pop(identity, None)
                job = active_task_job(identity)
                if job:
                    await job.stop()
            return _json(200, {"enabled": updated["enabled"]})
        if operation == "runs":
            return _json(
                200, {"runs": await anyio.to_thread.run_sync(task_runs, identity)}
            )
        if operation == "stop":
            job = active_task_job(identity)
            if job:
                await job.stop()
            return _json(200, job.snapshot() if job else {"state": "idle"})
        return _json(202, await launch_task(task, "manual"))
    except (ValueError, TypeError, OSError) as error:
        return _json(409, {"error": str(error)})


async def _action_results(
    results: AsyncGenerator[tuple[int, Result], None],
    actions: list[Result],
    engine: str,
) -> AsyncGenerator[tuple[int, Result], None]:
    registered = {action["name"]: action for action in actions}
    async for index, result in results:
        name = result.get("action")
        if name and not result.get("error"):
            result.update(
                {
                    "schemaVersion": 1,
                    "eventId": str(uuid4()),
                    "decidedAt": datetime.now(UTC).isoformat(),
                    "engine": engine,
                }
            )
            result["actionExecution"] = await run_action(registered[name], result)
        yield index, result


async def handle_test_ssh_host(request: Request) -> Response:
    """Test saved or draft SSH settings only from trusted file-access origins."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "SSH host testing requires a trusted UI origin."})
    try:
        value = await request.json()
        trusted_key = value.get("trustedHostKey") if isinstance(value, dict) else None
        if (
            isinstance(value, dict)
            and set(value) <= {"id", "trustedHostKey"}
            and "id" in value
        ):
            value = next(
                (host for host in load_hosts() if host["id"] == value["id"]), None
            )
            if value is None:
                return _json(404, {"error": "SSH host not found."})
        return _json(200, await test_host_connection(value, trusted_key))
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})


async def handle_ssh_hosts(request: Request) -> Response:
    """Manage shared SSH connections from trusted file-access origins."""
    if not _allowed_origin(request, files=True):
        return _json(
            403, {"error": "SSH host management requires a trusted UI origin."}
        )
    try:
        load_sources()  # Migrate existing Source connections before listing hosts.
        if request.method == "PUT":
            save_host(await request.json())
        elif request.method == "DELETE":
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Select an SSH host.")
            active = [
                source
                for job in JOBS.values()
                if job.state == "running"
                for source in job.settings.get("sources", [])
            ]
            saved = [
                {"hostId": identity}
                for task in load_tasks()
                for source in task["sources"]
                for identity in source.get("hostIds", [])
            ]
            require_unused("SSH Host", body.get("id"))
            delete_host(body.get("id"), [*saved, *active])
        return _json(200, {"hosts": load_hosts()})
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})


async def handle_ssh_keys(request: Request) -> Response:
    """Manage key pairs only from trusted file-access UI origins."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "SSH key management requires a trusted UI origin."})
    try:
        if request.method != "POST":
            chunks = bytearray()
            async for chunk in request.stream():
                chunks.extend(chunk)
                if len(chunks) > 131072:
                    return _json(413, {"error": "SSH key request is too large."})
            body = json.loads(chunks)
            if not isinstance(body, dict):
                raise ValueError("Enter SSH key details.")
            if request.method == "PUT":
                method = body.get("inputMethod", "upload")
                if method == "path":
                    add_key_from_path(body.get("name"), body.get("privateKeyPath"))
                elif method in {"paste", "upload"}:
                    add_key(body.get("name"), body.get("privateKey"))
                else:
                    raise ValueError("Select a private key input method.")
            else:
                active = [
                    source
                    for job in JOBS.values()
                    if job.state == "running"
                    for source in job.settings.get("sources", [])
                ]
                require_unused("SSH Key", body.get("name"))
                delete_key(body.get("name"), active)
        return _json(200, {"keys": list_keys()})
    except (ValueError, TypeError, OSError):
        return _json(
            400,
            {
                "error": "Could not manage SSH keys. Check the key name, "
                "unencrypted key file, storage permissions, and Host/Source/job references."
            },
        )


async def handle_sources(request: Request) -> Response:
    """Read or replace source definitions using trusted file-access origins."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Source management requires a trusted UI origin."})
    try:
        if request.method == "PUT":
            values = await request.json()
            if isinstance(values, list):
                identities = {
                    source.get("id") for source in values if isinstance(source, dict)
                }
                for task in load_tasks():
                    if any(
                        source["sourceId"] not in identities
                        for source in task["sources"]
                    ):
                        raise ValueError(
                            f"A Source is used by Task '{task['name']}'. Update the Task before deleting it."
                        )
                for source in load_sources():
                    if source["id"] not in identities:
                        require_unused("Source", source["id"])
            sources = save_sources(values)
        else:
            sources = load_sources()
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    return _json(200, {"sources": sources})


async def handle_criteria(request: Request) -> Response:
    """Manage fixed-category profiles with the same trusted-origin rules as Actions."""
    if not _allowed_origin(request, files=True):
        return _json(
            403, {"error": "Criteria management requires a trusted UI origin."}
        )
    try:
        if request.method == "PUT":
            values = await request.json()
            if isinstance(values, dict):
                for task in load_tasks():
                    if any(
                        source["profile"] not in values for source in task["sources"]
                    ):
                        raise ValueError(
                            f"Criteria is used by Task '{task['name']}'. Update the Task before deleting it."
                        )
            if isinstance(values, dict):
                for identity in PROFILES.keys() - values.keys():
                    require_unused("Criteria", identity)
            profiles = save_profiles(values)
        else:
            profiles = deepcopy(PROFILES)
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    return _json(200, {"profiles": profiles})


async def handle_reset_action(request: Request) -> Response:
    """Reset a saved environment using the same trusted-origin checks as Actions."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Action reset requires a trusted UI origin."})
    try:
        action = await reset_action(request.path_params["action_id"])
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    return _json(
        200, {"action": {**action, "environmentStatus": get_action_status(action)}}
    )


async def handle_actions(request: Request) -> Response:
    """List or replace local action registrations using file-access origin checks."""
    if request.method != "GET" and not _allowed_origin(request, files=True):
        return _json(
            403, {"error": "Action registration requires a trusted UI origin."}
        )
    try:
        if request.method in {"GET", "POST"}:
            actions = load_actions()
            for action in actions:
                action["environmentStatus"] = get_action_status(action)
            if request.method == "GET":
                return _json(
                    200,
                    {
                        "actions": [
                            {
                                key: value
                                for key, value in action.items()
                                if key != "code"
                            }
                            for action in actions
                        ]
                    },
                )
            for action in actions:
                if "code" not in action:
                    script = Path(action["script"])
                    action["code"] = (
                        script.read_text(encoding="utf-8") if script.is_file() else ""
                    )
        else:
            values = await request.json()
            if isinstance(values, list):
                names = {
                    action.get("name") for action in values if isinstance(action, dict)
                }
                for task in load_tasks():
                    if any(
                        source.get("action") and source["action"] not in names
                        for source in task["sources"]
                    ):
                        raise ValueError(
                            f"An Action is used by Task '{task['name']}'. Update the Task before deleting or renaming it."
                        )
                for action in load_actions():
                    if action["name"] not in names:
                        require_unused("Action", action["name"])
            actions = await save_actions(values)
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    return _json(
        200,
        {
            "actions": [
                {**action, "environmentStatus": get_action_status(action)}
                for action in actions
            ]
        },
    )


def _start_job(settings: Result, events: AsyncGenerator[str, None]) -> Response:
    job = Job(settings, events)
    JOBS[job.id] = job
    return _json(202, {"jobId": job.id, "state": job.state, "settings": settings})


async def handle_job(request: Request) -> Response:
    """Inspect, replay, or stop an existing job using trusted-origin checks."""
    if not _allowed_origin(request):
        return _json(403, {"error": "Job access requires a trusted UI origin."})
    job = JOBS.get(request.path_params["job_id"])
    if job is None:
        archived = read_archived_run(
            get_tasks_directory(), request.path_params["job_id"]
        )
        if archived:
            if not _allowed_origin(request, files=True):
                return _json(403, {"error": "Job access requires a trusted UI origin."})
            snapshot, directory = archived
            if request.url.path.endswith("/events"):
                return StreamingResponse(
                    replay_archived_run(directory),
                    media_type="application/x-ndjson",
                    headers=HEADERS,
                )
            return _json(200, snapshot)
        return _json(
            404, {"error": "Job no longer exists. The server may have restarted."}
        )
    if job.settings["mode"] != "paste" and not _allowed_origin(request, files=True):
        return _json(403, {"error": "Job access requires a trusted UI origin."})
    operation = request.url.path.rsplit("/", 1)[-1]
    if operation == "stop":
        await job.stop()
    elif operation == "events":
        return StreamingResponse(
            job.stream(), media_type="application/x-ndjson", headers=HEADERS
        )
    return _json(200, job.snapshot())


async def handle_settings(request: Request) -> Response:
    """Read or save application preferences using trusted-origin checks."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Settings access requires a trusted UI origin."})
    try:
        values = await request.json() if request.method == "PUT" else None
        settings = await anyio.to_thread.run_sync(
            partial(save_settings, values) if request.method == "PUT" else load_settings
        )
        return _json(200, settings)
    except (ValueError, OSError) as error:
        return _json(400, {"error": str(error)})


async def handle_result_page(request: Request) -> Response:
    """Query bounded result pages, save corrections, or stream a complete export."""
    if not _allowed_origin(request, files=True):
        return _json(403, {"error": "Result access requires a trusted UI origin."})
    identity = request.path_params["job_id"]
    job = JOBS.get(identity)
    try:
        if job is not None:
            store = job.store
        else:
            archived = await anyio.to_thread.run_sync(
                read_archived_run, get_tasks_directory(), identity
            )
            if archived is None:
                return _json(404, {"error": "Run not found."})
            store = await anyio.to_thread.run_sync(archived_store, archived[1])
        operation = request.url.path.rsplit("/", 1)[-1]
        if operation in {"export", "export-reviewed"}:
            reviewed_only = operation == "export-reviewed"
            state = await anyio.to_thread.run_sync(store.state, identity)
            snapshot = state["snapshot"]
            metadata = {
                "mode": state["summary"].get("engine"),
                "sourceMode": snapshot["settings"]["mode"],
                "total": snapshot.get("total"),
                "completed": state["summary"]["total"],
                "elapsedMs": snapshot.get("elapsedMs", 0),
                "activeProcessingMs": snapshot.get("activeProcessingMs", 0),
            }

            if reviewed_only:
                metadata["exportScope"] = "reviewed-changes"

            async def export() -> AsyncGenerator[str, None]:
                yield json.dumps(metadata)[:-1] + ',"results":['
                cursor = 0
                separator = ""
                exported = 0
                while batch := await anyio.to_thread.run_sync(
                    partial(store.events, identity, cursor, reviewed_only=reviewed_only)
                ):
                    for cursor, encoded in batch:
                        if cursor > state["sequence"]:
                            break
                        event = json.loads(encoded)
                        if event["type"] == "result":
                            yield separator + json.dumps(event["result"])
                            separator = ","
                            exported += 1
                    if cursor >= state["sequence"]:
                        break
                yield f'],"exported":{exported}}}' if reviewed_only else "]}"

            return StreamingResponse(
                export(),
                media_type="application/json",
                headers={
                    **HEADERS,
                    "Content-Disposition": (
                        'attachment; filename="deciflow-reviewed-results.json"'
                        if reviewed_only
                        else 'attachment; filename="deciflow-results.json"'
                    ),
                },
            )
        body = await request.json()
        if not isinstance(body, dict):
            raise TypeError("Invalid result request.")
        if operation == "review":
            sequence, category = body.get("sequence"), body.get("category")
            if type(sequence) is not int or not isinstance(category, str):
                raise TypeError("Invalid reviewer category or result cursor.")
            await anyio.to_thread.run_sync(store.review, identity, sequence, category)
            return _json(200, {"saved": True})
        state = await anyio.to_thread.run_sync(store.state, identity)
        if job is not None:
            state["snapshot"] = job.snapshot()
        page = (
            {}
            if body.get("onlySummary")
            else await anyio.to_thread.run_sync(
                store.page, identity, body, load_settings()["resultsPerPage"]
            )
        )
        return _json(200, {**state, **page})
    except (ValueError, TypeError) as error:
        return _json(400, {"error": str(error)})
    except (OSError, sqlite3.Error):
        return _json(503, {"error": "Result storage is unavailable."})


@asynccontextmanager
async def lifespan(application: Starlette) -> AsyncIterator[None]:
    """Stop background analysis jobs when the server shuts down."""
    load_profiles()
    get_keys_directory()
    scheduler = asyncio.create_task(SCHEDULER.run())
    try:
        yield
    finally:
        scheduler.cancel()
        await asyncio.gather(scheduler, return_exceptions=True)
        await asyncio.gather(*(job.stop() for job in JOBS.values()))
        JOBS.clear()


async def handle_asset(request: Request) -> Response:
    """Serve only the UI assets exposed by the original server."""
    asset = ASSETS.get(request.url.path)
    if request.method != "GET" or asset is None:
        return _json(404, {"error": "Not found."})
    name, media_type = asset
    path = ROOT / "public" / name
    if not path.is_file():
        return Response("Could not load the file.", status_code=500, headers=HEADERS)
    headers = HEADERS
    if request.url.path == "/vendor/prism/prism-python-1.30.0.min.js":
        headers = {**HEADERS, "Cache-Control": "public, max-age=31536000, immutable"}
    return FileResponse(path, media_type=media_type, headers=headers)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/api/settings", handle_settings, methods=["POST", "PUT"]),
        Route("/api/jobs/{job_id}/results", handle_result_page, methods=["POST"]),
        Route("/api/jobs/{job_id}/review", handle_result_page, methods=["POST"]),
        Route(
            "/api/jobs/{job_id}/export-reviewed", handle_result_page, methods=["POST"]
        ),
        Route("/api/jobs/{job_id}/export", handle_result_page, methods=["POST"]),
        Route("/api/delete-check", handle_delete_check, methods=["POST"]),
        Route("/api/tasks", handle_tasks, methods=["POST", "PUT", "DELETE"]),
        Route("/api/tasks/{task_id}/enabled", handle_task_operation, methods=["POST"]),
        Route("/api/tasks/{task_id}/run", handle_task_operation, methods=["POST"]),
        Route("/api/tasks/{task_id}/stop", handle_task_operation, methods=["POST"]),
        Route("/api/tasks/{task_id}/runs", handle_task_operation, methods=["POST"]),
        Route("/api/jobs/{job_id}", handle_job, methods=["POST"]),
        Route("/api/jobs/{job_id}/events", handle_job, methods=["POST"]),
        Route("/api/jobs/{job_id}/stop", handle_job, methods=["POST"]),
        Route("/api/ssh-keys", handle_ssh_keys, methods=["POST", "PUT", "DELETE"]),
        Route("/api/ssh-hosts/test", handle_test_ssh_host, methods=["POST"]),
        Route("/api/ssh-hosts", handle_ssh_hosts, methods=["POST", "PUT", "DELETE"]),
        Route("/api/sources", handle_sources, methods=["POST", "PUT"]),
        Route("/api/criteria", handle_criteria, methods=["POST", "PUT"]),
        Route("/api/actions/{action_id}/reset", handle_reset_action, methods=["POST"]),
        Route("/api/actions", handle_actions, methods=["GET", "POST", "PUT"]),
        Route("/api/status", handle_status, methods=["GET"]),
        Route("/api/classify", handle_classify, methods=["POST"]),
        Route("/api/file-source", handle_file_source, methods=["POST"]),
        Route("/{path:path}", handle_asset),
    ],
)


def get_log_config() -> Result:
    """Keep console logs and optionally rotate server/access files separately."""
    config = deepcopy(LOGGING_CONFIG)
    directory = os.getenv("DECIFLOW_LOG_DIR", DEFAULT_LOG_DIR).strip()
    if not directory:
        return config
    path = Path(directory)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    config["formatters"]["server_file"] = {
        "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",
    }
    config["formatters"]["access_file"] = {
        "()": "uvicorn.logging.AccessFormatter",
        "fmt": '%(asctime)s %(client_addr)s - "%(request_line)s" %(status_code)s',
        "use_colors": False,
    }
    for name, filename, logger in (
        ("server_file", "server.log", "uvicorn"),
        ("access_file", "access.log", "uvicorn.access"),
    ):
        config["handlers"][name] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": name,
            "filename": str(path / filename),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
            "encoding": "utf-8",
        }
        config["loggers"][logger]["handlers"].append(name)
    return config


def main(*, host: str = "127.0.0.1") -> None:
    """Read local settings at startup; bind to loopback unless specified."""
    load_dotenv(ROOT / ".env")
    get_engine()
    port = int(os.getenv("PORT") or "4000")
    print(f"DeciFlow: http://{host}:{port}", flush=True)
    uvicorn.run(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=2,
        log_config=get_log_config(),
    )


if __name__ == "__main__":
    main()
