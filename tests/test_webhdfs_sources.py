"""Test WebHDFS HTTP operations through the shared Batch and sampling pipeline."""

import io
import json
from contextlib import aclosing
from pathlib import Path

import httpx
import pytest

import server
import webhdfs_sources
from classifier import EXECUTION_CONTROL, ExecutionControl
from criteria_generation import preview_samples
from hdfs_sources import prepare_hdfs_sources, read_hdfs_sources
from profiles import GENERAL_PROFILE_ID
from source_registry import save_sources, source_pattern, validate_sources
from source_settings import parse_source_settings, resolve_configured_sources
from tasks import save_task


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def cluster(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("DECIFLOW_DATA_DIR", str(tmp_path / "state"))
    files = {
        "/data/상담.jsonl": '{"text":"first"}\n{"text":"상담"}\n'.encode(),
        "/data/part.jsonl": b'{"text":"second"}\n',
    }
    state = {
        "files": files,
        "requests": [],
        "clients": [],
        "mtime": 1000,
        "redirect": "http://data.test:9864/webhdfs/v1",
        "status": 200,
    }

    def handle(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        path = request.url.path.removeprefix("/webhdfs/v1")
        op = request.url.params.get("op")
        if state["status"] != 200:
            return httpx.Response(state["status"])

        def status(name: str) -> dict:
            return {
                "pathSuffix": name.rsplit("/", 1)[-1],
                "type": "FILE",
                "length": len(files[name]),
                "modificationTime": state["mtime"],
            }

        if op == "GETFILESTATUS":
            value = (
                status(path)
                if path in files
                else {
                    "type": "DIRECTORY",
                    "pathSuffix": "",
                    "length": 0,
                    "modificationTime": 1000,
                }
            )
            value["pathSuffix"] = ""
            return httpx.Response(200, json={"FileStatus": value})
        if op == "LISTSTATUS":
            return httpx.Response(
                200,
                json={"FileStatuses": {"FileStatus": [status(name) for name in files]}},
            )
        if request.url.host == "nn.test":
            target = httpx.URL(state["redirect"] + path).copy_merge_params(
                request.url.params
            )
            return httpx.Response(307, headers={"location": str(target)})
        return httpx.Response(
            200, content=files[path][int(request.url.params.get("offset", 0)) :]
        )

    original = httpx.Client

    def client(**kwargs):
        result = original(**kwargs, transport=httpx.MockTransport(handle))
        state["clients"].append(result)
        return result

    monkeypatch.setattr(webhdfs_sources.httpx, "Client", client)
    return state


def definition(**changes) -> dict:
    return {
        "name": "Web Data",
        "type": "webhdfs",
        "endpoint": "http://nn.test:9870",
        "path": "/data\n/data/*.jsonl",
        "format": "jsonl",
        "contentField": "text",
        **changes,
    }


def register(**changes) -> tuple[dict, dict]:
    source = save_sources([definition(**changes)])[0]
    return source, parse_source_settings(
        [{"sourceId": source["id"], "profile": GENERAL_PROFILE_ID}]
    )[0]


@pytest.mark.parametrize(
    "changes",
    [
        {"endpoint": "ftp://nn.test"},
        {"endpoint": "http://user:secret@nn.test"},
        {"endpoint": "http://nn.test?delegation=secret"},
        {"endpoint": "http://nn.test/#fragment"},
        {"endpoint": "http://nn.test:bad"},
        {"endpoint": "http://nn.test/unknown"},
        {"path": "relative"},
        {"tokenFile": "relative"},
        {"caFile": "relative"},
        {"username": "bad\nuser"},
    ],
)
def test_validation(changes: dict) -> None:
    with pytest.raises(ValueError):
        validate_sources([definition(**changes)])


@pytest.mark.anyio
async def test_web_batch_preview_and_api(cluster: dict) -> None:
    source, spec = register(username="reader")
    assert not resolve_configured_sources([spec])
    assert source_pattern(spec).startswith("webhdfs://nn.test:9870/")
    await prepare_hdfs_sources([spec], "batch")
    assert len(spec["hdfsFiles"]) == 2
    rows = [row async for row in read_hdfs_sources([spec])]
    assert {row["log"] for row in rows} == {"first", "second", "상담"}
    assert all(row["sourceType"] == "webhdfs" and not row.get("error") for row in rows)
    assert (
        len(await preview_samples({"sourceId": source["id"], "sampleCount": 10})) == 3
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        response = await client.post(
            "/api/sources/hdfs-test",
            json=source,
            headers={"origin": "http://localhost"},
        )
    assert response.status_code == 200, response.text
    assert response.json()["fileCount"] == 2
    assert all(
        request.url.params.get("user.name") == "reader"
        for request in cluster["requests"]
    )
    assert all(client.is_closed for client in cluster["clients"])
    with pytest.raises(ValueError, match="Batch"):
        await prepare_hdfs_sources([spec], "realtime")
    with pytest.raises(ValueError, match="Batch"):
        save_task(
            {
                "name": "Invalid",
                "mode": "realtime",
                "sources": [{"sourceId": source["id"], "profile": GENERAL_PROFILE_ID}],
            }
        )


@pytest.mark.anyio
async def test_changed_files_and_http_failure(cluster: dict) -> None:
    _, spec = register()
    await prepare_hdfs_sources([spec], "batch")
    cluster["mtime"] += 1
    rows = [row async for row in read_hdfs_sources([spec])]
    assert all(row["sourceFailure"] and "changed" in row["error"] for row in rows)
    cluster["status"] = 403
    with pytest.raises(ValueError, match="HTTP 403"):
        await prepare_hdfs_sources([spec], "batch")
    assert all(client.is_closed for client in cluster["clients"])


def test_stream_seek_and_token_redaction(cluster: dict, tmp_path: Path) -> None:
    token = tmp_path / "token"
    token.write_text("private-token-value")
    source = validate_sources([definition(tokenFile=str(token), username="ignored")])[0]
    fs = webhdfs_sources.WebHDFSFileSystem(source)
    try:
        with io.BufferedReader(fs.open_input_file("/data/part.jsonl")) as reader:
            assert reader.read(5) == b'{"tex'
            assert reader.seek(0) == 0
            assert reader.read() == cluster["files"]["/data/part.jsonl"]
        assert all(
            request.url.params.get("delegation") == "private-token-value"
            for request in cluster["requests"]
        )
        assert all(
            "user.name" not in request.url.params for request in cluster["requests"]
        )
        cluster["status"] = 401
        with pytest.raises(ValueError) as caught:
            fs.get_file_info("/data")
        assert "private-token-value" not in str(caught.value)
    finally:
        fs.close()


@pytest.mark.parametrize(
    "redirect",
    [
        "file:///etc/passwd",
        "http://user:secret@data.test/file",
        "http://data.test/file",
    ],
)
def test_reject_unsafe_redirect(cluster: dict, redirect: str) -> None:
    source = validate_sources([definition(endpoint="https://nn.test:9870")])[0]
    cluster["redirect"] = redirect
    fs = webhdfs_sources.WebHDFSFileSystem(source)
    try:
        with pytest.raises(ValueError, match="Unsafe"):
            fs._request("/data/part.jsonl", "OPEN")
    finally:
        fs.close()


def test_invalid_json_and_network_errors_are_safe(
    cluster: dict, tmp_path: Path
) -> None:
    token = tmp_path / "token"
    token.write_text("private-token-value")
    fs = webhdfs_sources.WebHDFSFileSystem(
        validate_sources([definition(tokenFile=str(token))])[0]
    )
    fs.client.close()
    # The fixture factory already supplies its own transport; use its concrete class.
    client_type = type(cluster["clients"][0])

    def invalid(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not a WebHDFS response</html>")

    fs.client = client_type(transport=httpx.MockTransport(invalid))
    try:
        with pytest.raises(ValueError, match="Invalid WebHDFS"):
            fs.get_file_info("/data")
    finally:
        fs.client.close()

    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(str(request.url), request=request)

    fs.client = client_type(transport=httpx.MockTransport(fail))
    try:
        with pytest.raises(ValueError) as caught:
            fs.get_file_info("/data")
        assert "ConnectError" in str(caught.value)
        assert "private-token-value" not in str(caught.value)
    finally:
        fs.close()


def test_premature_eof_is_a_failure(cluster: dict) -> None:
    fs = webhdfs_sources.WebHDFSFileSystem(validate_sources([definition()])[0])
    try:
        raw = fs.open_input_file("/data/part.jsonl")
        raw.size += 1
        with (
            io.BufferedReader(raw) as reader,
            pytest.raises(ValueError, match="before its recorded size"),
        ):
            reader.read()
    finally:
        fs.close()


@pytest.mark.anyio
async def test_checkpoint_resume_and_early_close(cluster: dict) -> None:
    cluster["files"].clear()
    first = "가" * 30000
    cluster["files"]["/data/large.txt"] = f"{first}\nsecond\nthird\n".encode()
    _, spec = register(format="text", path="/data", chunkEvents=1)
    await prepare_hdfs_sources([spec], "batch")
    control = ExecutionControl()

    async def checkpoint(uri: str, cursor: dict) -> None:
        control.cursors[uri] = cursor

    control.checkpoint = checkpoint
    token = EXECUTION_CONTROL.set(control)
    try:
        async with aclosing(read_hdfs_sources([spec])) as records:
            row = await anext(records)
            assert row["log"] == first
        control.cursors[row["source"]] = row["_checkpoint"]
        remaining = [item async for item in read_hdfs_sources([spec])]
        assert [item["log"] for item in remaining] == ["second", "third"]
        assert any(
            int(request.url.params.get("offset", 0)) > 65536
            for request in cluster["requests"]
        )
        assert all(client.is_closed for client in cluster["clients"])
    finally:
        EXECUTION_CONTROL.reset(token)


@pytest.mark.anyio
@pytest.mark.parametrize("engine", ["laya", "jev"])
async def test_shared_engine_pipeline(
    cluster: dict, monkeypatch: pytest.MonkeyPatch, engine: str
) -> None:
    source, _ = register()
    monkeypatch.setenv("DECISION_ENGINE", engine)
    calls = []

    async def classify(log, selected, client, profile=GENERAL_PROFILE_ID):
        calls.append((log, selected.name))
        return {"decisions": {}, "review": False}

    monkeypatch.setattr(server, "classify_log", classify)
    settings, events = await server.prepare_file_execution(
        "batch", [{"sourceId": source["id"], "profile": GENERAL_PROFILE_ID}]
    )
    output = [json.loads(event) async for event in events]
    results = [event["result"] for event in output if event["type"] == "result"]
    assert len(results) == 3
    assert set(calls) == {("first", engine), ("second", engine), ("상담", engine)}
    assert all(item["sourceType"] == "webhdfs" for item in results)
    assert settings["sources"][0]["hdfsFiles"]
    assert not any(event["type"] == "error" for event in output)
