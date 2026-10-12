"""Serve the DeciFlow UI and its existing JSON/NDJSON API."""

import asyncio
import json
import os
import platform
import socket
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
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

from actions import load_actions, run_action, save_actions
from classifier import Result, classify_log, classify_stream, parse_logs
from config import (
    JEV_CONTEXT_TOKENS,
    JEV_REQUEST_TOKENS,
    Engine,
    get_engine,
    get_jev_input_bytes,
)
from configured_sources import follow_configured, read_configured
from jobs import JOBS, Job
from profiles import PROFILES, validate_settings
from source_settings import parse_source_settings, resolve_configured_sources
from sources import follow_sources, read_sources

ROOT = Path(__file__).resolve().parent
HEADERS = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
ASSETS = {
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/stream.js": ("stream.js", "text/javascript"),
    "/style.css": ("style.css", "text/css"),
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
    logs: list[str], engine: Engine, profile: str = "general", chunk_events: int = 1
) -> AsyncIterator[str]:
    """Stream progress and cancel in-flight engine calls on client disconnect."""

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
    events = handle_events(logs, engine, profile, chunk_events)
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
) -> AsyncIterator[str]:
    """Stream classifications from a file without buffering its full contents."""
    clock = _ProcessingClock()
    yield _encode(
        {
            "type": "start",
            "total": None,
            "mode": mode,
            "engine": engine.name,
            "sources": [str(path) for path in paths],
            "sourcePatterns": [spec["path"] for spec in specs] if specs else values,
        }
    )
    if specs is not None and mode == "realtime":
        records = follow_configured(specs)
    elif isinstance(paths, dict):
        records = read_configured(paths)
    else:
        records = follow_sources(values) if mode == "realtime" else read_sources(paths)
    try:
        async with httpx.AsyncClient(timeout=engine.timeout) as client:

            async def handle_classify(log: str) -> Result:
                clock.begin()
                try:
                    return await classify_log(log, engine, client)
                finally:
                    clock.end()

            async def handle_record(record: Result) -> Result:
                clock.begin()
                try:
                    profile = record.get("profile", "general")
                    if profile == "general":
                        return await classify_log(record["log"], engine, client)
                    return await classify_log(record["log"], engine, client, profile)
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
                aclosing(_action_results(results, actions or [], engine.name)) as acted,
                aclosing(_timed_results(acted, clock)) as events,
            ):
                async for event in events:
                    yield event
    except (OSError, UnicodeError, ValueError) as error:
        yield _encode({"type": "error", "error": f"File source stopped: {error}"})
    finally:
        await records.aclose()
    yield _encode({"type": "done", **clock.snapshot()})


async def handle_file_source(request: Request) -> Response:
    """Start explicitly selected server files through a local same-origin request."""
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
        specs = parse_source_settings(values)
        actions = load_actions() if any(spec.get("action") for spec in specs) else []
        names = {action["name"] for action in actions}
        if any(spec.get("action") and spec["action"] not in names for spec in specs):
            raise ValueError("Select a registered action or None.")
        paths = await anyio.to_thread.run_sync(
            partial(resolve_configured_sources, specs, follow=mode == "realtime"),
            abandon_on_cancel=True,
        )
    except (ValueError, TypeError, OSError) as error:
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
    events = handle_file_events(values, paths, mode, engine, specs, actions)
    if body.get("persist") is True:
        return _start_job({"mode": mode, "sources": specs}, events)
    return StreamingResponse(
        events,
        media_type="application/x-ndjson",
        headers=HEADERS,
    )


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


async def handle_actions(request: Request) -> Response:
    """List or replace local action registrations using file-access origin checks."""
    if request.method != "GET" and not _allowed_origin(request, files=True):
        return _json(
            403, {"error": "Action registration requires a trusted UI origin."}
        )
    try:
        if request.method in {"GET", "POST"}:
            actions = load_actions()
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
            actions = await save_actions(await request.json())
    except (ValueError, TypeError, OSError) as error:
        return _json(400, {"error": str(error)})
    return _json(200, {"actions": actions})


def _start_job(settings: Result, events: AsyncIterator[str]) -> Response:
    job = Job(settings, events)
    JOBS[job.id] = job
    return _json(202, {"jobId": job.id, "state": job.state, "settings": settings})


async def handle_job(request: Request) -> Response:
    """Inspect, replay, or stop an existing job using trusted-origin checks."""
    if not _allowed_origin(request):
        return _json(403, {"error": "Job access requires a trusted UI origin."})
    job = JOBS.get(request.path_params["job_id"])
    if job is None:
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
    return _json(200, {"jobId": job.id, "state": job.state, "settings": job.settings})


@asynccontextmanager
async def lifespan(application: Starlette) -> AsyncIterator[None]:
    """Stop background analysis jobs when the server shuts down."""
    try:
        yield
    finally:
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
    return FileResponse(path, media_type=media_type, headers=HEADERS)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/api/jobs/{job_id}", handle_job, methods=["POST"]),
        Route("/api/jobs/{job_id}/events", handle_job, methods=["POST"]),
        Route("/api/jobs/{job_id}/stop", handle_job, methods=["POST"]),
        Route("/api/actions", handle_actions, methods=["GET", "POST", "PUT"]),
        Route("/api/status", handle_status, methods=["GET"]),
        Route("/api/classify", handle_classify, methods=["POST"]),
        Route("/api/file-source", handle_file_source, methods=["POST"]),
        Route("/{path:path}", handle_asset),
    ],
)


def main(*, host: str = "127.0.0.1") -> None:
    """Read local settings at startup; bind to loopback unless specified."""
    load_dotenv(ROOT / ".env")
    get_engine()
    port = int(os.getenv("PORT") or "4000")
    print(f"DeciFlow: http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()
