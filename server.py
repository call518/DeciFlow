"""Serve the DeciFlow UI and its existing JSON/NDJSON API."""

import asyncio
import json
import os
import platform
import socket
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from functools import partial
from ipaddress import ip_address
from pathlib import Path
from time import perf_counter

import anyio
import httpx
import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from classifier import Result, classify_batch, classify_log, classify_stream, parse_logs
from config import (
    JEV_CONTEXT_TOKENS,
    JEV_REQUEST_TOKENS,
    LAYA_CONTEXT_TOKENS,
    Engine,
    get_engine,
    get_jev_input_bytes,
)
from sources import follow_sources, read_sources, resolve_sources

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
            "host": await anyio.to_thread.run_sync(_host_info),
            "limits": {
                "max_jev_input_bytes": get_jev_input_bytes(),
                "context_tokens": JEV_CONTEXT_TOKENS,
                "request_tokens": JEV_REQUEST_TOKENS,
            }
            if engine.name == "jev"
            else {"context_tokens": LAYA_CONTEXT_TOKENS},
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


async def handle_events(logs: list[str], engine: Engine) -> AsyncIterator[str]:
    """Stream progress and cancel in-flight engine calls on client disconnect."""
    clock = _ProcessingClock()
    yield _encode({"type": "start", "total": len(logs), "engine": engine.name})
    async with httpx.AsyncClient(timeout=engine.timeout) as client:

        async def handle_classify(log: str) -> Result:
            clock.begin()
            try:
                return await classify_log(log, engine, client)
            finally:
                clock.end()

        async with (
            aclosing(
                classify_batch(logs, handle_classify, engine.concurrency)
            ) as results,
            aclosing(_timed_results(results, clock)) as events,
        ):
            async for event in events:
                yield event
    yield _encode({"type": "done", **clock.snapshot()})


async def handle_classify(request: Request) -> Response:
    """Validate a same-origin upload before opening the decision stream."""
    if request.headers.get("origin") != f"http://{request.headers.get('host')}":
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
    except (ValueError, TypeError) as error:
        return _json(400, {"error": str(error)})
    try:
        engine = get_engine()
    except ValueError as error:
        return _json(503, {"error": str(error)})
    if engine.name == "jev" and not engine.api_key:
        return _json(
            503,
            {"error": "Set the TYPESAFE_API_KEY environment variable on the server."},
        )
    return StreamingResponse(
        handle_events(logs, engine), media_type="application/x-ndjson", headers=HEADERS
    )


async def handle_file_events(
    values: object, paths: list[Path], mode: str, engine: Engine
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
        }
    )
    records = follow_sources(values) if mode == "follow" else read_sources(paths)
    try:
        async with httpx.AsyncClient(timeout=engine.timeout) as client:

            async def handle_classify(log: str) -> Result:
                clock.begin()
                try:
                    return await classify_log(log, engine, client)
                finally:
                    clock.end()

            async with (
                aclosing(
                    classify_stream(records, handle_classify, engine.concurrency)
                ) as results,
                aclosing(_timed_results(results, clock)) as events,
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
    if request.headers.get(
        "origin"
    ) != f"http://{request.headers.get('host')}" or request.url.hostname not in {
        "127.0.0.1",
        "localhost",
    }:
        return _json(
            403, {"error": "File sources require a same-origin localhost request."}
        )
    try:
        body = await request.json()
        if not isinstance(body, dict) or body.get("mode") not in {"batch", "follow"}:
            raise ValueError("Select Batch or Realtime mode.")
        mode = body["mode"]
        values = body.get("paths", body.get("path"))
        paths = await anyio.to_thread.run_sync(
            partial(resolve_sources, values, follow=mode == "follow"),
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
            {"error": "Set the TYPESAFE_API_KEY environment variable on the server."},
        )
    return StreamingResponse(
        handle_file_events(values, paths, mode, engine),
        media_type="application/x-ndjson",
        headers=HEADERS,
    )


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
    routes=[
        Route("/api/status", handle_status, methods=["GET"]),
        Route("/api/classify", handle_classify, methods=["POST"]),
        Route("/api/file-source", handle_file_source, methods=["POST"]),
        Route("/{path:path}", handle_asset),
    ]
)


def main() -> None:
    """Load local settings and start DeciFlow on loopback, port 4000 by default."""
    load_dotenv(ROOT / ".env")
    get_engine()
    port = int(os.getenv("PORT") or "4000")
    print(f"DeciFlow: http://127.0.0.1:{port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, timeout_graceful_shutdown=2)


if __name__ == "__main__":
    main()
