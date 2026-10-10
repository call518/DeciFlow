import asyncio
from contextlib import aclosing
from pathlib import Path

import anyio
import httpx
import pytest

import server
from classifier import Result, classify_stream
from config import Engine
from sources import (
    follow_file,
    follow_sources,
    read_file,
    read_sources,
    resolve_source,
    resolve_sources,
)


@pytest.fixture(autouse=True)
def working_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate relative paths to each test's temporary directory."""
    monkeypatch.chdir(tmp_path)


def test_source_path_validation(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("event\n")
    assert resolve_source("access.log") == path
    for value in [None, "", "../outside.log", str(tmp_path), "missing.log"]:
        with pytest.raises(ValueError):
            resolve_source(value)
    assert resolve_source("missing.log", follow=True) == tmp_path / "missing.log"
    link = tmp_path / "escape.log"
    outside = tmp_path.parent / f"{tmp_path.name}-outside.log"
    outside.write_text("outside event\n")
    link.symlink_to(outside)
    assert resolve_source(str(link)) == link
    assert resolve_source(str(outside)) == outside


@pytest.mark.anyio
async def test_batch_lines_and_final_partial_line(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_bytes("first\r\n\nsecond ☃\nlast".encode())
    records = [record async for record in read_file(path)]
    assert [record["log"] for record in records] == ["first", "second ☃", "last"]
    assert [record["line"] for record in records] == [1, 3, 4]
    assert all(record["source"] == str(path) for record in records)


@pytest.mark.anyio
async def test_follow_appends_utf8_rotation_and_truncation(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("old event\n")
    async with aclosing(follow_file(path)) as records:
        task = asyncio.create_task(anext(records))
        await anyio.sleep(0.05)
        encoded = "new ☃\n".encode()
        with path.open("ab") as file:
            file.write(encoded[:-2])
        await anyio.sleep(0.3)
        assert not task.done()
        with path.open("ab") as file:
            file.write(encoded[-2:])
        with anyio.fail_after(3):
            assert (await task)["log"] == "new ☃"

        task = asyncio.create_task(anext(records))
        path.rename(tmp_path / "access.log.1")
        path.write_text("replacement\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "replacement"

        task = asyncio.create_task(anext(records))
        path.write_text("")
        await anyio.sleep(0.3)
        path.write_text("after truncate\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "after truncate"


@pytest.mark.anyio
async def test_follow_missing_file_and_recreation(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    async with aclosing(follow_file(path)) as records:
        task = asyncio.create_task(anext(records))
        await anyio.sleep(0.05)
        path.write_text("created\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "created"
        task = asyncio.create_task(anext(records))
        path.unlink()
        await anyio.sleep(0.3)
        path.write_text("recreated\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "recreated"


@pytest.mark.anyio
async def test_rotation_retains_partial_line(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("")
    async with aclosing(follow_file(path)) as records:
        task = asyncio.create_task(anext(records))
        await anyio.sleep(0.05)
        path.write_text("partial")
        await anyio.sleep(0.3)
        path.rename(tmp_path / "access.log.1")
        path.write_text("next\n")
        with anyio.fail_after(3):
            result = await task
            assert result["log"] == "partial"
            assert result["incomplete"] is True
            assert (await anext(records))["log"] == "next"


@pytest.mark.anyio
async def test_stream_results_without_waiting_for_next_log(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("before\n")
    calls = 0

    async def handle_classify(log: str) -> Result:
        nonlocal calls
        calls += 1
        return {"category": "normal"}

    async with aclosing(classify_stream(follow_file(path), handle_classify)) as results:
        task = asyncio.create_task(anext(results))
        await anyio.sleep(0.05)
        with path.open("a") as file:
            file.write("after\n")
        with anyio.fail_after(3):
            index, result = await task
        assert index == 0
        assert result["log"] == "after"
    assert calls == 1


@pytest.mark.anyio
async def test_stream_backpressure_and_cancellation(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("\n".join(str(index) for index in range(20)))
    calls = active = peak = cancelled = 0
    started = anyio.Event()

    async def handle_classify(log: str) -> Result:
        nonlocal calls, active, peak, cancelled
        calls += 1
        active += 1
        peak = max(peak, active)
        if calls == 4:
            started.set()
        try:
            if log == "0":
                await started.wait()
                return {"category": "normal"}
            await anyio.sleep_forever()
            raise AssertionError("sleep_forever returned")
        except asyncio.CancelledError:
            cancelled += 1
            raise
        finally:
            active -= 1

    async with aclosing(classify_stream(read_file(path), handle_classify)) as results:
        with anyio.fail_after(3):
            assert (await anext(results))[0] == 0
    assert calls == peak == 4
    assert cancelled == 3


@pytest.mark.anyio
@pytest.mark.parametrize("engine_name", ["laya", "jev"])
async def test_file_api_and_localhost_access(
    engine_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine_name)
    path = tmp_path / "access.log"
    path.write_text("first\nsecond\n")

    async def handle_classify(
        log: str, engine: Engine, client: httpx.AsyncClient
    ) -> Result:
        return {"category": "normal", "confidence": 1, "review": False}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://127.0.0.1"
    ) as client:
        response = await client.post(
            "/api/file-source",
            headers={"Origin": "http://127.0.0.1"},
            json={"mode": "batch", "path": "access.log"},
        )
        assert response.status_code == 200
        import json

        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[0]["total"] is None
        assert events[-1]["type"] == "done"
        assert {event["result"]["log"] for event in events[1:-1]} == {"first", "second"}
        (tmp_path / "second.log").write_text("third\n")
        response = await client.post(
            "/api/file-source",
            headers={"Origin": "http://127.0.0.1"},
            json={"mode": "batch", "paths": ["access.log", "*.log"]},
        )
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert len(events[0]["sources"]) == 2
        assert {event["result"]["log"] for event in events[1:-1]} == {
            "first",
            "second",
            "third",
        }
        assert (await client.post("/api/file-source", json={})).status_code == 403
        for body in [
            {},
            {"mode": "batch", "path": "../outside"},
            {"mode": "batch", "path": str(tmp_path)},
        ]:
            response = await client.post(
                "/api/file-source",
                headers={"Origin": "http://127.0.0.1"},
                json=body,
            )
            assert response.status_code == 400


def test_globs_duplicates_and_invalid_inputs(tmp_path: Path) -> None:
    (tmp_path / "a.log").write_text("a\n")
    (tmp_path / "b.log").write_text("b\n")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.log").write_text("c\n")
    paths = resolve_sources("a.log\n*.log\nnested/**/?.log")
    assert paths == [tmp_path / "a.log", tmp_path / "b.log", nested / "c.log"]
    assert resolve_sources(["[ab].log", "a.log"]) == paths[:2]
    with pytest.raises(ValueError, match="No regular files"):
        resolve_sources("missing-*.log")
    assert resolve_sources("missing-*.log", follow=True) == []
    for value in [[], [123]]:
        with pytest.raises(ValueError):
            resolve_sources(value, follow=True)


@pytest.mark.anyio
async def test_files_across_directories(tmp_path: Path) -> None:
    local = tmp_path / "local.log"
    local.write_text("local\n")
    external = tmp_path.parent / f"{tmp_path.name}-logs"
    external.mkdir()
    remote = external / "remote.log"
    remote.write_text("remote\n")
    paths = resolve_sources(f"local.log\n{external}/*.log\n{remote}")
    assert paths == [local, remote]
    records = [record async for record in read_sources(paths)]
    assert [record["log"] for record in records] == ["local", "remote"]


@pytest.mark.anyio
async def test_multiple_batch_files_once(tmp_path: Path) -> None:
    (tmp_path / "a.log").write_text("a1\na2\n")
    (tmp_path / "b.log").write_text("b1\n")
    paths = resolve_sources("a.log\n*.log")
    records = [record async for record in read_sources(paths)]
    assert [record["log"] for record in records] == ["a1", "a2", "b1"]
    assert [record["line"] for record in records] == [1, 2, 1]


@pytest.mark.anyio
async def test_follow_many_and_discover_new_matches(tmp_path: Path) -> None:
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    a.write_text("old a\n")
    b.write_text("old b\n")
    async with aclosing(follow_sources("a.log\n*.log")) as records:
        task = asyncio.create_task(anext(records))
        await anyio.sleep(0.1)
        with b.open("a") as file:
            file.write("new b\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "new b"
        task = asyncio.create_task(anext(records))
        with a.open("a") as file:
            file.write("new a\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "new a"
        task = asyncio.create_task(anext(records))
        (tmp_path / "c.log").write_text("new file first line\n")
        with anyio.fail_after(3):
            record = await task
            assert record["log"] == "new file first line"
            assert record["source"].endswith("c.log")


@pytest.mark.anyio
async def test_follow_pattern_initially_empty(tmp_path: Path) -> None:
    async with aclosing(follow_sources("new-*.log")) as records:
        task = asyncio.create_task(anext(records))
        await anyio.sleep(0.1)
        (tmp_path / "new-one.log").write_text("first\n")
        with anyio.fail_after(3):
            assert (await task)["log"] == "first"


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["batch", "realtime"])
async def test_stop_all_sources_and_workers(mode: str, tmp_path: Path) -> None:
    for name in ["a.log", "b.log"]:
        (tmp_path / name).write_text("" if mode == "realtime" else "event\n")
    cancelled = 0
    started = anyio.Event()

    async def handle_classify(log: str) -> Result:
        started.set()
        nonlocal cancelled
        try:
            await anyio.sleep_forever()
            raise AssertionError("sleep_forever returned")
        except asyncio.CancelledError:
            cancelled += 1
            raise

    source = (
        follow_sources("*.log")
        if mode == "realtime"
        else read_sources(resolve_sources("*.log"))
    )
    stream = classify_stream(source, handle_classify)
    task = asyncio.create_task(anext(stream))
    if mode == "realtime":
        await anyio.sleep(0.1)
        for name in ["a.log", "b.log"]:
            with (tmp_path / name).open("a") as file:
                file.write("event\n")
    with anyio.fail_after(3):
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await stream.aclose()
    assert cancelled >= 1
