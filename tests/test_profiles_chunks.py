import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest

import server
from chunks import chunk_records
from classifier import Result, classify_log
from config import get_engine
from configured_sources import read_configured
from profiles import PROFILES, validate_settings
from source_settings import parse_source_settings, resolve_configured_sources


@pytest.mark.parametrize("engine", ["laya", "jev"])
@pytest.mark.parametrize("profile", list(PROFILES))
@pytest.mark.anyio
async def test_profiles_reach_both_engines(
    monkeypatch: pytest.MonkeyPatch, engine: str, profile: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)

    def handle_request(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["state"] == "line one\nline two"
        question = payload["questions"]["category"]
        assert question["criteria"] == PROFILES[profile]["criteria"]
        assert PROFILES[profile]["instructions"] in question["instructions"]
        assert "Prefer security" not in question["instructions"]
        assert "Use other when context is insufficient" not in question["instructions"]
        return httpx.Response(
            200,
            json={
                "usage": {"truncated": False},
                "answers": {
                    "category": {
                        "choice": "normal",
                        "confidence": 1,
                        "probabilities": {
                            key: int(key == "normal") for key in question["criteria"]
                        },
                    }
                },
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handle_request)
    ) as client:
        result = await classify_log("line one\nline two", get_engine(), client, profile)
    assert result["category"] == "normal"


@pytest.mark.parametrize("size", [0, -1, True, "2", 1.5])
def test_invalid_chunk_size(size: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        validate_settings("general", size)


def test_unknown_profile() -> None:
    with pytest.raises(ValueError, match="profile"):
        validate_settings("unknown", 1)


def test_legacy_chunk_setting_is_normalized_to_events() -> None:
    specs = parse_source_settings([{"path": "example.log", "chunkLines": 2}])
    assert specs[0]["chunkEvents"] == 2
    assert "chunkLines" not in specs[0]


@pytest.mark.anyio
async def test_chunks_count_multiline_events_separately_from_lines() -> None:
    async def records() -> AsyncGenerator[Result, None]:
        yield {
            "log": "Traceback\n  frame\nValueError",
            "source": "application.log",
            "line": 1,
            "lineEnd": 3,
            "lineCount": 3,
        }
        yield {
            "log": "Exception\n  frame",
            "source": "application.log",
            "line": 4,
            "lineEnd": 5,
            "lineCount": 2,
        }

    rows = [row async for row in chunk_records(records(), "application", 2)]
    assert len(rows) == 1
    assert rows[0]["eventCount"] == 2
    assert rows[0]["chunkEvents"] == 2
    assert rows[0]["lineCount"] == 5
    assert rows[0]["line"] == 1
    assert rows[0]["lineEnd"] == 5


def test_overlap_settings(tmp_path: Path) -> None:
    path = tmp_path / "access.log"
    path.write_text("log\n")
    specs = parse_source_settings(
        [
            {"path": str(path), "profile": "http_access", "chunkEvents": 2},
            {
                "path": str(tmp_path / "*.log"),
                "profile": "http_access",
                "chunkEvents": 2,
            },
        ]
    )
    assert len(resolve_configured_sources(specs)) == 1
    specs[1]["chunkEvents"] = 1
    with pytest.raises(ValueError, match="Conflicting"):
        resolve_configured_sources(specs)


@pytest.mark.anyio
async def test_batch_chunks_do_not_mix_files_and_flush_eof(tmp_path: Path) -> None:
    for name in ("a.log", "b.log"):
        (tmp_path / name).write_text("one\n\ntwo\nthree\n")
    specs = parse_source_settings(
        [{"path": str(tmp_path / "*.log"), "profile": "application", "chunkEvents": 2}]
    )
    rows = [row async for row in read_configured(resolve_configured_sources(specs))]
    for name in ("a.log", "b.log"):
        source_rows = [row for row in rows if row["source"].endswith(name)]
        assert [row["log"] for row in source_rows] == ["one\ntwo", "three"]
        assert [row["lineCount"] for row in source_rows] == [2, 1]
        assert source_rows[0]["line"] == 1 and source_rows[0]["lineEnd"] == 3
    assert all(row["profile"] == "application" for row in rows)


@pytest.mark.anyio
async def test_realtime_idle_flush_and_cancel() -> None:
    closed = asyncio.Event()

    async def records() -> AsyncGenerator[Result, None]:
        try:
            yield {"log": "one", "line": 1, "source": "live.log"}
            await asyncio.Event().wait()
        finally:
            closed.set()

    async with aclosing(chunk_records(records(), "general", 3, live=True)) as chunks:
        async with asyncio.timeout(2):
            row = await anext(chunks)
        assert row["log"] == "one" and row["lineCount"] == 1
    assert closed.is_set()


@pytest.mark.anyio
async def test_rotation_boundary_flushes_separate_chunks() -> None:
    async def records() -> AsyncGenerator[Result, None]:
        for line, text in [(1, "old"), (1, "new"), (2, "next")]:
            yield {"line": line, "log": text, "source": "rotating.log"}

    rows = [row async for row in chunk_records(records(), "general", 3)]
    assert [row["log"] for row in rows] == ["old", "new\nnext"]


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_paste_chunk_metadata_including_failures(
    monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    seen = []

    async def handle_classify(
        log: str, selected: object, client: object, profile: str = "general"
    ) -> Result:
        seen.append((log, profile))
        raise ValueError("test failure")

    monkeypatch.setattr(server, "classify_log", handle_classify)
    events = [
        json.loads(row)
        async for row in server.handle_events(
            ["one", "two", "three"], get_engine(), "authentication", 2
        )
    ]
    assert events[0]["total"] == 2
    results = [event["result"] for event in events if event["type"] == "result"]
    assert sorted(seen) == [("one\ntwo", "authentication"), ("three", "authentication")]
    assert all(row["profile"] == "authentication" and row["review"] for row in results)
    assert sorted(row["lineCount"] for row in results) == [1, 2]
    assert sorted(row["eventCount"] for row in results) == [1, 2]
    assert all(row["chunkEvents"] == 2 for row in results)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_file_api_applies_each_source_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    monkeypatch.setenv("DECISION_ENGINE", engine)
    first, second = tmp_path / "auth.log", tmp_path / "http.log"
    first.write_text("first\nsecond\nthird\n")
    second.write_text("GET / 200\n")

    async def handle_classify(
        log: str, selected: object, client: object, profile: str = "general"
    ) -> Result:
        return {"category": "normal", "usedProfile": profile}

    monkeypatch.setattr(server, "classify_log", handle_classify)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/file-source",
            headers={"Origin": "http://localhost"},
            json={
                "mode": "batch",
                "sources": [
                    {"path": str(first), "profile": "authentication", "chunkEvents": 2},
                    {"path": str(second), "profile": "http_access", "chunkEvents": 1},
                ],
            },
        )
    assert response.status_code == 200
    results = [
        json.loads(line)["result"]
        for line in response.text.splitlines()
        if json.loads(line)["type"] == "result"
    ]
    assert len(results) == 3
    assert all(row["profile"] == row["usedProfile"] for row in results)
    assert sorted(row["lineCount"] for row in results) == [1, 1, 2]


@pytest.mark.anyio
async def test_realtime_discovers_globs_with_per_file_chunks(tmp_path: Path) -> None:
    from configured_sources import follow_configured

    specs = parse_source_settings(
        [{"path": str(tmp_path / "*.log"), "profile": "network", "chunkEvents": 2}]
    )
    async with aclosing(follow_configured(specs)) as records:
        pending = asyncio.create_task(anext(records))
        try:
            await asyncio.sleep(0.3)
            (tmp_path / "one.log").write_text("one-a\none-b\n")
            (tmp_path / "two.log").write_text("two-a\ntwo-b\n")
            async with asyncio.timeout(4):
                first = await pending
                second = await anext(records)
            assert {first["log"], second["log"]} == {"one-a\none-b", "two-a\ntwo-b"}
            assert first["source"] != second["source"]
            assert first["profile"] == second["profile"] == "network"
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.anyio
async def test_live_rotation_does_not_mix_generations(tmp_path: Path) -> None:
    from sources import follow_file

    path = tmp_path / "rotate.log"
    path.write_text("")
    async with aclosing(
        chunk_records(follow_file(path), "general", 4, live=True)
    ) as records:
        pending = asyncio.create_task(anext(records))
        try:
            await asyncio.sleep(0.3)
            path.write_text("old line\n")
            await asyncio.sleep(0.3)
            path.rename(tmp_path / "rotate.log.1")
            path.write_text("new line\nsecond new line\n")
            async with asyncio.timeout(4):
                first = await pending
                second = await anext(records)
            assert first["log"] == "old line"
            assert second["log"] == "new line\nsecond new line"
            assert first["line"] == second["line"] == 1
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


@pytest.mark.anyio
async def test_batch_files_keep_independent_profiles_and_chunk_sizes(
    tmp_path: Path,
) -> None:
    first = tmp_path / "a.log"
    second = tmp_path / "b.log"
    first.write_text("a\n" * 30)
    second.write_text("b\n" * 7)
    paths = {
        first: {"profile": "general", "chunkEvents": 2},
        second: {"profile": "authentication", "chunkEvents": 3},
    }
    rows = [row async for row in read_configured(paths)]
    assert next(i for i, row in enumerate(rows) if row["source"] == str(second)) < 15
    for path, spec in paths.items():
        selected = [row for row in rows if row["source"] == str(path)]
        assert all(row["profile"] == spec["profile"] for row in selected)
        assert all(row["chunkEvents"] == spec["chunkEvents"] for row in selected)
        assert [row["line"] for row in selected] == (
            list(range(1, 31, 2)) if path == first else [1, 4, 7]
        )
        assert selected[-1]["lineCount"] == (2 if path == first else 1)


@pytest.mark.anyio
async def test_overlapping_source_patterns_are_retained_without_duplicate_chunks(
    tmp_path: Path,
) -> None:
    path = tmp_path / "events.log"
    path.write_text("first\nsecond\n")
    pattern = str(tmp_path / "*.log")
    specs = parse_source_settings([str(path), pattern])
    paths = resolve_configured_sources(specs)
    rows = [row async for row in read_configured(paths)]
    assert len(rows) == 2
    assert all(row["sourcePatterns"] == [str(path), pattern] for row in rows)
