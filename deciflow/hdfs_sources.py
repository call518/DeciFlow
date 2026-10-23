"""Read immutable HDFS Batch inputs over native Hadoop or WebHDFS."""

import fnmatch
import io
import os
import posixpath
from collections.abc import AsyncGenerator, Iterator
from contextlib import aclosing
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

import anyio

from deciflow.chunks import source_records
from deciflow.classifier import EXECUTION_CONTROL, Result
from deciflow.source_registry import source_paths, source_pattern
from deciflow.sources import merge_batch

READERS = 4
MAX_LINE_BYTES = 16 * 1024 * 1024


def connect_hdfs(spec: Result) -> Any:
    """Load JNI only when HDFS is used; keep network waits bounded."""
    if spec.get("type") == "webhdfs":
        from deciflow.webhdfs_sources import WebHDFSFileSystem

        return WebHDFSFileSystem(spec)
    try:
        default_conf: dict[str, str] = {}
        if spec["host"] == "default":
            directory = Path(os.environ.get("HADOOP_CONF_DIR", "/etc/hadoop/conf"))
            default_uri = ""
            for name in ("core-site.xml", "hdfs-site.xml"):
                path = directory / name
                if path.is_file():
                    for prop in ElementTree.parse(path).getroot().findall("property"):
                        if prop.findtext("name", "").strip() == "fs.defaultFS":
                            default_uri = prop.findtext("value", "").strip()
            uri = urlsplit(default_uri)
            if uri.scheme != "hdfs" or not uri.netloc:
                raise ValueError(
                    "Configure an hdfs:// fs.defaultFS in HADOOP_CONF_DIR, "
                    "or enter an hdfs:// endpoint instead of default. "
                    "Local filesystem fallback is not allowed for HDFS Sources."
                )
            default_conf["fs.defaultFS"] = default_uri
        from pyarrow.fs import HadoopFileSystem

        return HadoopFileSystem(
            spec["host"],
            port=spec["port"],
            user=spec.get("username") or None,
            kerb_ticket=spec.get("ticketCache") or None,
            extra_conf={
                **default_conf,
                "ipc.client.connect.timeout": "10000",
                "ipc.client.connect.max.retries": "0",
                "ipc.client.connect.max.retries.on.timeouts": "0",
                "ipc.client.rpc-timeout.ms": "15000",
                "dfs.client.socket-timeout": "15000",
                "dfs.client.retry.policy.enabled": "false",
                "dfs.client.failover.max.attempts": "2",
                "dfs.client.failover.sleep.max.millis": "1000",
            },
        )
    except (ImportError, OSError, ValueError, ElementTree.ParseError) as error:
        raise ValueError(
            "HDFS connection failed. Check the native Hadoop runtime, NameNode, "
            "cluster XML configuration, network access, and authentication. "
            f"{error}"
        ) from error


def _files(filesystem: Any, pattern: str) -> list[Any]:
    from pyarrow.fs import FileSelector, FileType

    paths = ["/"]
    for part in posixpath.normpath(pattern).strip("/").split("/"):
        anyio.from_thread.check_cancelled()
        if not part:
            continue
        if part == "**":
            raise ValueError(
                "Use a directory for recursive HDFS reads; ** is unsupported."
            )
        if any(char in part for char in "*?["):
            paths = [
                item.path
                for path in paths
                for item in filesystem.get_file_info(FileSelector(path))
                if fnmatch.fnmatchcase(posixpath.basename(item.path), part)
            ]
        else:
            paths = [posixpath.join(path, part) for path in paths]
    files: dict[str, Any] = {}
    for path in paths:
        info = filesystem.get_file_info(path)
        pending = [info]
        while pending:
            anyio.from_thread.check_cancelled()
            item = pending.pop()
            if item.type == FileType.Directory:
                pending.extend(filesystem.get_file_info(FileSelector(item.path)))
            elif item.type == FileType.File:
                files[item.path] = item
    if not files:
        raise ValueError(f"No HDFS regular files match: {pattern}")
    return sorted(files.values(), key=lambda item: item.path)


def _manifest(spec: Result) -> list[Result]:
    filesystem = connect_hdfs(spec)
    files: dict[str, Result] = {}
    try:
        for pattern in source_paths(spec["path"]):
            for info in _files(filesystem, pattern):
                files[info.path] = {
                    "path": info.path,
                    "size": info.size,
                    "mtimeNs": info.mtime_ns,
                }
    finally:
        if spec.get("type") == "webhdfs":
            filesystem.close()
    return list(files.values())


async def prepare_hdfs_sources(specs: list[Result], mode: str) -> None:
    """Freeze the file list once and reject conflicting overlapping assignments."""
    seen: dict[str, Result] = {}
    for spec in specs:
        if spec.get("type") not in {"hdfs", "webhdfs"}:
            continue
        if mode != "batch":
            raise ValueError("HDFS Sources support Batch mode only.")
        files = await anyio.to_thread.run_sync(_manifest, spec)
        spec["hdfsFiles"] = []
        for item in files:
            uri = source_pattern({**spec, "path": item["path"]})
            previous = seen.get(uri)
            if previous is not None:
                fields = (
                    "profile",
                    "chunkEvents",
                    "actionId",
                    "format",
                    "contentField",
                    "username",
                    "ticketCache",
                    "tokenFile",
                    "caFile",
                )
                if any(previous.get(key) != spec.get(key) for key in fields):
                    raise ValueError(f"Conflicting HDFS Source settings for: {uri}")
                continue
            seen[uri] = spec
            spec["hdfsFiles"].append(item)


def _validate_file(filesystem: Any, item: Result) -> None:
    info = filesystem.get_file_info(item["path"])
    if info.size != item["size"] or info.mtime_ns != item["mtimeNs"]:
        raise ValueError(
            "HDFS file changed or disappeared since Batch startup; "
            "start a new run after the input files are complete."
        )


async def _lines(
    filesystem: Any, spec: Result, item: Result
) -> AsyncGenerator[Result, None]:
    uri = source_pattern({**spec, "path": item["path"]})
    control = EXECUTION_CONTROL.get()
    saved = control.cursors.get(uri) if control else None
    reader = None
    try:
        await anyio.to_thread.run_sync(_validate_file, filesystem, item)
        native = await anyio.to_thread.run_sync(
            filesystem.open_input_file, item["path"]
        )
        reader = io.BufferedReader(native, buffer_size=65536)
        prefix = await anyio.to_thread.run_sync(reader.read, 256)
        fingerprint = {
            "size": item["size"],
            "mtimeNs": item["mtimeNs"],
            "prefix": sha256(prefix).hexdigest(),
        }
        if saved and any(saved.get(key) != value for key, value in fingerprint.items()):
            raise ValueError("HDFS source changed since checkpoint; recovery stopped.")
        offset, line = (saved["offset"], saved["line"]) if saved else (0, 0)
        await anyio.to_thread.run_sync(reader.seek, offset)
        if control and control.checkpoint:
            await control.checkpoint(
                uri, {**fingerprint, "offset": offset, "line": line}
            )
        while raw := await anyio.to_thread.run_sync(
            reader.readline, MAX_LINE_BYTES + 1
        ):
            if len(raw) > MAX_LINE_BYTES:
                raise ValueError("HDFS input line exceeds the 16 MiB limit.")
            offset += len(raw)
            line += 1
            if text := raw.decode("utf-8").strip():
                yield {
                    "log": text,
                    "source": uri,
                    "line": line,
                    **(
                        {"_checkpoint": {**fingerprint, "offset": offset, "line": line}}
                        if control and control.checkpoint
                        else {}
                    ),
                }
        await anyio.to_thread.run_sync(_validate_file, filesystem, item)
    finally:
        if reader is not None:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(reader.close)


def _metadata(spec: Result) -> Result:
    cluster = source_pattern({**spec, "path": "/"}).rstrip("/")
    return {
        "hostId": cluster,
        "hostName": cluster,
        "hostAddress": spec["host"],
        "hostPort": spec["port"],
        "sourceId": spec["sourceId"],
        "sourceName": spec["name"],
        "sourceType": spec["type"],
        "sourcePatterns": [
            source_pattern({**spec, "path": path})
            for path in source_paths(spec["path"])
        ],
        **({"actionId": spec["actionId"]} if spec.get("actionId") else {}),
    }


async def _worker(
    jobs: Iterator[tuple[Result, Result]], filesystems: dict[str, Any]
) -> AsyncGenerator[Result, None]:
    for spec, item in jobs:
        try:
            key = spec["sourceId"]
            if isinstance(filesystems[key], Exception):
                raise filesystems[key]
            async with aclosing(
                source_records(_lines(filesystems[key], spec, item), spec)
            ) as records:
                async for record in records:
                    yield {**record, **_metadata(spec)}
        except (OSError, ValueError, UnicodeError) as error:
            yield {
                **_metadata(spec),
                "log": "",
                "profile": spec["profile"],
                "chunkEvents": spec["chunkEvents"],
                "sourceFailure": True,
                "source": source_pattern({**spec, "path": item["path"]}),
                "error": str(error),
            }


async def read_hdfs_sources(specs: list[Result]) -> AsyncGenerator[Result, None]:
    """Use four rotating file readers with bounded buffers and shared inference limits."""
    jobs = iter(
        (spec, item)
        for spec in specs
        if spec.get("type") in {"hdfs", "webhdfs"}
        for item in spec["hdfsFiles"]
    )
    filesystems: dict[str, Any] = {}
    try:
        for spec in specs:
            if spec.get("type") in {"hdfs", "webhdfs"} and spec["hdfsFiles"]:
                try:
                    filesystems[spec["sourceId"]] = await anyio.to_thread.run_sync(
                        connect_hdfs, spec
                    )
                except (OSError, ValueError) as error:
                    filesystems[spec["sourceId"]] = error
        async with aclosing(
            merge_batch([_worker(jobs, filesystems) for _ in range(READERS)])
        ) as records:
            async for record in records:
                yield record
    finally:
        with anyio.CancelScope(shield=True):
            for spec in specs:
                filesystem = filesystems.get(spec["sourceId"])
                if (
                    spec.get("type") == "webhdfs"
                    and filesystem is not None
                    and not isinstance(filesystem, Exception)
                ):
                    await anyio.to_thread.run_sync(filesystem.close)


async def test_hdfs_source(spec: Result) -> Result:
    """Check listing and actual file-read permission without classifying data."""
    files = await anyio.to_thread.run_sync(_manifest, spec)
    filesystem = await anyio.to_thread.run_sync(connect_hdfs, spec)

    def read() -> None:
        try:
            with filesystem.open_input_stream(files[0]["path"]) as stream:
                stream.read(1)
        finally:
            if spec.get("type") == "webhdfs":
                filesystem.close()

    await anyio.to_thread.run_sync(read)
    return {"connected": True, "fileCount": len(files)}
