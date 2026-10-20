"""Exercise HDFS orchestration with local native file handles, without a cluster."""

import json
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest
from pyarrow.fs import LocalFileSystem

import hdfs_sources
import server
from classifier import EXECUTION_CONTROL, ExecutionControl
from criteria_generation import preview_samples
from profiles import GENERAL_PROFILE_ID
from source_registry import save_sources, source_pattern, validate_sources
from source_settings import parse_source_settings, resolve_configured_sources
from tasks import save_task


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(hdfs_sources, "connect_hdfs", lambda spec: LocalFileSystem())
    root = tmp_path / "files"
    root.mkdir()
    return {
        "name": "HDFS Test",
        "type": "hdfs",
        "endpoint": "hdfs://namenode.example.test:8020",
        "path": str(root),
    }


def register(source: dict) -> dict:
    saved = save_sources([source])[0]
    return parse_source_settings(
        [{"sourceId": saved["id"], "profile": GENERAL_PROFILE_ID, "chunkEvents": 1}]
    )[0]


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "http://invalid"},
        {"endpoint": "hdfs://host/path"},
        {"endpoint": "hdfs://host:-1"},
        {"endpoint": "hdfs://user:password@host:8020"},
        {"endpoint": "hdfs://host:65536"},
        {"ticketCache": "relative"},
        {"path": "relative/path"},
        {"username": "bad\nuser"},
    ],
)
def test_hdfs_validation(source: dict, changes: dict) -> None:
    with pytest.raises(ValueError):
        validate_sources([{**source, **changes}])


@pytest.mark.anyio
async def test_frozen_manifest_dedup_and_jsonl(source: dict) -> None:
    root = Path(source["path"])
    (root / "part-1.jsonl").write_text('{"text":"첫번째"}\nnot json\n')
    (root / "part-2.jsonl").write_text('{"text":"second"}\n')
    spec = register(
        {
            **source,
            "path": f"{root}\n{root}/*.jsonl",
            "format": "jsonl",
            "contentField": "text",
        }
    )
    assert not resolve_configured_sources([spec])
    await hdfs_sources.prepare_hdfs_sources([spec], "batch")
    assert len(spec["hdfsFiles"]) == 2
    (root / "part-new.jsonl").write_text('{"text":"not in this run"}\n')
    rows = [row async for row in hdfs_sources.read_hdfs_sources([spec])]
    assert len(rows) == 3
    assert sum(bool(row.get("error")) for row in rows) == 1
    assert {row["log"] for row in rows if not row.get("error")} == {"첫번째", "second"}
    assert all(row["sourceType"] == "hdfs" for row in rows)
    assert all(
        row["source"].startswith("hdfs://namenode.example.test:8020/") for row in rows
    )
    assert all("ticketCache" not in row for row in rows)


@pytest.mark.anyio
async def test_resume_uses_cursor_and_rejects_changed_files(source: dict) -> None:
    path = Path(source["path"]) / "input.txt"
    path.write_text("one\ntwo\nthree\nfour\n")
    spec = register(source)
    spec["chunkEvents"] = 2
    await hdfs_sources.prepare_hdfs_sources([spec], "batch")
    control = ExecutionControl()

    async def checkpoint(uri: str, cursor: dict) -> None:
        control.cursors[uri] = cursor

    control.checkpoint = checkpoint
    token = EXECUTION_CONTROL.set(control)
    try:
        async with aclosing(hdfs_sources.read_hdfs_sources([spec])) as records:
            first = await anext(records)
            assert first["log"] == "one\ntwo"
        control.cursors[first["source"]] = first["_checkpoint"]
        rows = [row async for row in hdfs_sources.read_hdfs_sources([spec])]
        assert [row["log"] for row in rows] == ["three\nfour"]
        path.write_text("replaced\n")
        rows = [row async for row in hdfs_sources.read_hdfs_sources([spec])]
        assert len(rows) == 1 and rows[0]["sourceFailure"]
        assert "changed" in rows[0]["error"]
    finally:
        EXECUTION_CONTROL.reset(token)


@pytest.mark.anyio
async def test_overlap_conflicts_and_batch_only(source: dict) -> None:
    (Path(source["path"]) / "input.txt").write_text("data\n")
    spec = register(source)
    second = {**spec, "sourceId": "a" * 32}
    await hdfs_sources.prepare_hdfs_sources([spec, second], "batch")
    assert len(spec["hdfsFiles"]) == 1 and second["hdfsFiles"] == []
    with pytest.raises(ValueError, match="Conflicting"):
        await hdfs_sources.prepare_hdfs_sources(
            [spec, {**second, "chunkEvents": 2}], "batch"
        )
    with pytest.raises(ValueError, match="Batch"):
        await hdfs_sources.prepare_hdfs_sources([spec], "realtime")
    with pytest.raises(ValueError, match="Batch"):
        save_task(
            {
                "name": "Invalid live task",
                "mode": "realtime",
                "sources": [
                    {"sourceId": spec["sourceId"], "profile": GENERAL_PROFILE_ID}
                ],
            }
        )


@pytest.mark.anyio
async def test_missing_file_and_line_limit(
    source: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = register(source)
    with pytest.raises(ValueError, match="No HDFS"):
        await hdfs_sources.prepare_hdfs_sources([spec], "batch")
    (Path(source["path"]) / "input.txt").write_text("too long\n")
    await hdfs_sources.prepare_hdfs_sources([spec], "batch")
    monkeypatch.setattr(hdfs_sources, "MAX_LINE_BYTES", 4)
    rows = [row async for row in hdfs_sources.read_hdfs_sources([spec])]
    assert len(rows) == 1 and rows[0]["sourceFailure"]
    assert "limit" in rows[0]["error"]


@pytest.mark.anyio
async def test_hdfs_preview_and_explicit_connection_test(source: dict) -> None:
    path = Path(source["path"]) / "input.jsonl"
    path.write_text("\n".join(json.dumps({"text": str(index)}) for index in range(25)))
    spec = register({**source, "format": "jsonl", "contentField": "text"})
    samples = await preview_samples({"sourceId": spec["sourceId"], "sampleCount": 10})
    assert len(samples) == 10 and len(set(samples)) == 10
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/sources/hdfs-test",
            json=source,
            headers={"origin": "http://localhost"},
        )
        assert response.status_code == 200
        assert response.json() == {"connected": True, "fileCount": 1}
        response = await client.post(
            "/api/sources/hdfs-test",
            json=source,
            headers={"origin": "https://untrusted.example.test"},
        )
        assert response.status_code == 403
    assert "hdfsFiles" not in validate_sources([source])[0]
    assert (
        source_pattern({**spec, "host": "default", "port": 0, "path": "/logs"})
        == "hdfs://default/logs"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_mixed_hdfs_and_local_share_engine_pipeline(
    source: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    (Path(source["path"]) / "input.txt").write_text("hdfs event\n")
    local = tmp_path / "local.txt"
    local.write_text("local event\n")
    sources = save_sources(
        [source, {"name": "Local", "type": "local", "path": str(local)}]
    )
    monkeypatch.setenv("DECISION_ENGINE", engine)
    calls = []

    async def classify(log, selected, client, profile=GENERAL_PROFILE_ID):
        calls.append((log, selected.name))
        return {"decisions": {}, "review": False}

    monkeypatch.setattr(server, "classify_log", classify)
    settings, events = await server.prepare_file_execution(
        "batch",
        [{"sourceId": item["id"], "profile": GENERAL_PROFILE_ID} for item in sources],
    )
    output = [json.loads(event) async for event in events]
    results = [event["result"] for event in output if event["type"] == "result"]
    assert len(results) == 2
    assert set(calls) == {("hdfs event", engine), ("local event", engine)}
    assert {item["sourceType"] for item in results} == {"local", "hdfs"}
    assert settings["sources"][0]["hdfsFiles"]
    assert not any(event["type"] == "error" for event in output)


@pytest.mark.anyio
async def test_reader_parallelism_and_early_close(
    source: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    import anyio

    for index in range(12):
        (Path(source["path"]) / f"part-{index}.txt").write_text("one\ntwo\n")
    spec = register(source)
    await hdfs_sources.prepare_hdfs_sources([spec], "batch")
    original = hdfs_sources._lines
    active = peak = 0

    async def tracked(*args):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await anyio.sleep(0.005)
            async with aclosing(original(*args)) as records:
                async for record in records:
                    yield record
        finally:
            active -= 1

    monkeypatch.setattr(hdfs_sources, "_lines", tracked)
    rows = [row async for row in hdfs_sources.read_hdfs_sources([spec])]
    assert len(rows) == 24 and peak == 4 and active == 0
    async with aclosing(hdfs_sources.read_hdfs_sources([spec])) as records:
        await anext(records)
    assert active == 0


def test_default_hdfs_requires_cluster_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import pyarrow.fs

    monkeypatch.setenv("HADOOP_CONF_DIR", str(tmp_path))
    calls = []
    monkeypatch.setattr(
        pyarrow.fs,
        "HadoopFileSystem",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "native-client",
    )
    source = {"host": "default", "port": 0}
    with pytest.raises(ValueError, match="fs.defaultFS"):
        hdfs_sources.connect_hdfs(source)
    config = tmp_path / "core-site.xml"
    config.write_text(
        "<configuration><property><name>fs.defaultFS</name><value>file:///</value></property></configuration>"
    )
    with pytest.raises(ValueError, match="Local filesystem fallback"):
        hdfs_sources.connect_hdfs(source)
    assert not calls
    config.write_text(
        "<configuration><property><name>fs.defaultFS</name><value>hdfs://cluster.example.test:8020</value></property></configuration>"
    )
    assert hdfs_sources.connect_hdfs(source) == "native-client"
    assert len(calls) == 1
    assert (
        calls[0][1]["extra_conf"]["fs.defaultFS"] == "hdfs://cluster.example.test:8020"
    )


@pytest.mark.parametrize(
    ("endpoint", "host", "port"),
    [
        ("hdfs://namenode.example.test:8020", "namenode.example.test", 8020),
        ("hdfs://nameservice1", "nameservice1", 0),
        ("default", "default", 0),
        ("hdfs://[::1]:8020/", "::1", 8020),
    ],
)
def test_native_endpoint_parsing(endpoint: str, host: str, port: int) -> None:
    source = validate_sources(
        [{"name": "Native", "type": "hdfs", "endpoint": endpoint, "path": "/logs"}]
    )[0]
    assert source["host"] == host
    assert source["port"] == port
    assert source["endpoint"] == endpoint.rstrip("/")


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "namenode:8020",
        "hdfs://host:",
        "hdfs://host?user=a",
        "hdfs://host#path",
        "hdfs://host/dir",
        "hdfs://",
        "hdfs://host:wrong",
    ],
)
def test_reject_invalid_native_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError):
        validate_sources(
            [{"name": "Native", "type": "hdfs", "endpoint": endpoint, "path": "/logs"}]
        )
