"""Persist reusable local, SSH, and HDFS Sources independently of run settings."""

import re
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid4, uuid5

from deciflow.classifier import Result
from deciflow.config_store import load_records, save_record, save_records

VOC_SOURCE = {
    "id": uuid5(NAMESPACE_URL, "deciflow:source:voc-consultations").hex,
    "name": "Sample VOC Asia Culture Center Consulting QnA",
    "type": "local",
    "path": "/host-logs/sample-logs/voc-asia-culture-center-consulting-qna.jsonl",
    "format": "jsonl",
    "contentField": "consulting_content",
}

CENTRAL_GOV_SOURCE = {
    "id": uuid5(NAMESPACE_URL, "deciflow:source:central-gov-qna").hex,
    "name": "Sample VOC Central Gov Consulting QnA",
    "type": "local",
    "path": "/host-logs/sample-logs/voc-central-gov-consulting-qna.jsonl",
    "format": "jsonl",
    "contentField": "consulting_content",
}

LOCAL_GOV_SOURCE = {
    "id": uuid5(NAMESPACE_URL, "deciflow:source:local-gov-qna").hex,
    "name": "Sample VOC Local Gov Consulting QnA",
    "type": "local",
    "path": "/host-logs/sample-logs/voc-local-gov-consulting-qna.jsonl",
    "format": "jsonl",
    "contentField": "상담내용",
}

DEFAULT_SOURCES = [
    {
        "id": uuid5(NAMESPACE_URL, f"deciflow:source:{slug}").hex,
        "name": name,
        "type": "local",
        "path": path,
    }
    for slug, name, path in (
        ("system-message", "Sample System Messages", "/host-logs/var/log/messages"),
        ("http-access", "Sample HTTP access", "/host-logs/sample-logs/access-1k.log"),
        (
            "ssh-authentication",
            "Sample SSH authentication",
            "/host-logs/sample-logs/SSH_2k.log",
        ),
    )
] + [VOC_SOURCE, CENTRAL_GOV_SOURCE, LOCAL_GOV_SOURCE]


def ensure_voc_source() -> None:
    """Add the consultation sample at startup without replacing saved Sources."""
    _ensure_sample_source(VOC_SOURCE)


def ensure_central_gov_source() -> None:
    """Add the government QnA sample without replacing saved Sources."""
    _ensure_sample_source(CENTRAL_GOV_SOURCE)


def ensure_local_gov_source() -> None:
    """Add the local government QnA sample without replacing saved Sources."""
    _ensure_sample_source(LOCAL_GOV_SOURCE)


def _ensure_sample_source(sample: Result) -> None:
    sources = load_sources()
    if any(
        source["id"] == sample["id"]
        or source["name"].casefold() == sample["name"].casefold()
        or (source["type"] == "local" and source["path"] == sample["path"])
        for source in sources
    ):
        return
    save_record("sources", sample["id"], sample)


def load_sources() -> list[Result]:
    """Read saved Sources, persisting sample defaults on the first access."""
    records = load_records("sources", {item["id"]: item for item in DEFAULT_SOURCES})

    return list(records.values())


def input_settings(value: Result) -> Result:
    """Validate independent file format and a literal top-level JSONL text field."""
    kind = value.get("format", "text")
    if kind not in {"text", "jsonl"}:
        raise ValueError("Select TEXT (Chunk) or JSONL (Line).")
    if kind == "text":
        return {"format": "text"} if "format" in value else {}
    field = value.get("contentField")
    if not isinstance(field, str) or not field.strip() or "\x00" in field:
        raise ValueError("Enter the JSONL content field name.")
    return {"format": "jsonl", "contentField": field.strip()}


def validate_sources(values: object) -> list[Result]:
    """Validate definitions without connecting to hosts or reading log/key contents."""
    if not isinstance(values, list):
        raise TypeError("Sources must be a list.")
    result = []
    names: set[str] = set()
    identities: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise TypeError("Each source must contain a name, type, and path.")
        source: Result = {}
        for key in ("name", "type", "path"):
            text = value.get(key)
            if not isinstance(text, str) or not text.strip() or "\x00" in text:
                raise ValueError(f"Enter a source {key}.")
            source[key] = text.strip()
        if source["type"] not in {"local", "ssh", "hdfs", "webhdfs"}:
            raise ValueError(
                "Select Local File, Remote File (SSH), HDFS (Native), or HDFS (WebHDFS)."
            )
        identity = value.get("id") or uuid4().hex
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
            raise ValueError("Invalid source ID.")
        if identity in identities or source["name"].casefold() in names:
            raise ValueError("Source names and IDs must be unique.")
        identities.add(identity)
        names.add(source["name"].casefold())
        source["id"] = identity
        paths = source_paths(source["path"])
        if source["type"] in {"ssh", "hdfs", "webhdfs"} and any(
            not PurePosixPath(path).is_absolute() for path in paths
        ):
            raise ValueError("Remote file paths must be absolute POSIX paths.")
        if source["type"] == "hdfs":
            endpoint = value.get("endpoint", "default")
            if not isinstance(endpoint, str):
                raise ValueError("Enter an HDFS URI or default.")
            endpoint = endpoint.strip()
            host, port = "default", 0
            if endpoint != "default":
                try:
                    uri = urlsplit(endpoint)
                    host, port = uri.hostname, uri.port or 0
                except ValueError as error:
                    raise ValueError("Invalid HDFS URI.") from error
                if (
                    uri.scheme != "hdfs"
                    or not host
                    or not re.fullmatch(r"[A-Za-z0-9_.:-]+", host)
                    or uri.username is not None
                    or uri.password is not None
                    or uri.netloc.endswith(":")
                    or uri.path not in {"", "/"}
                    or uri.query
                    or uri.fragment
                    or any(char.isspace() for char in endpoint)
                ):
                    raise ValueError(
                        "Use hdfs://hostname:port, hdfs://nameservice, or default. "
                        "Enter file paths separately."
                    )
                endpoint = f"hdfs://{uri.netloc}"
            source.update(endpoint=endpoint, host=host, port=port)
            for key in ("username", "ticketCache"):
                text = value.get(key, "")
                if not isinstance(text, str) or "\x00" in text or "\n" in text:
                    raise ValueError(f"Invalid HDFS {key}.")
                source[key] = text.strip()
            if (
                source["ticketCache"]
                and not PurePosixPath(source["ticketCache"]).is_absolute()
            ):
                raise ValueError("Kerberos ticket cache must be an absolute file path.")
        if source["type"] == "webhdfs":
            endpoint = value.get("endpoint", "")
            if not isinstance(endpoint, str):
                raise ValueError("Enter a WebHDFS HTTP(S) endpoint.")
            endpoint = endpoint.strip().rstrip("/")
            try:
                url = urlsplit(endpoint)
                port = url.port
            except ValueError as error:
                raise ValueError("Invalid WebHDFS endpoint.") from error
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or port == 0
                or url.username is not None
                or url.password is not None
                or url.query
                or url.fragment
                or url.path not in {"", "/webhdfs/v1"}
                or any(char.isspace() for char in endpoint)
                or "\\" in endpoint
            ):
                raise ValueError(
                    "Use http(s)://host:port or http(s)://host:port/webhdfs/v1 "
                    "without credentials, query parameters, or fragments."
                )
            source.update(
                endpoint=endpoint.removesuffix("/webhdfs/v1"),
                host=url.hostname,
                port=port or (443 if url.scheme == "https" else 80),
            )
            for key in ("username", "tokenFile", "caFile"):
                text = value.get(key, "")
                if not isinstance(text, str) or any(c in text for c in "\x00\r\n"):
                    raise ValueError(f"Invalid WebHDFS {key}.")
                source[key] = text.strip()
                if (
                    key != "username"
                    and text.strip()
                    and not PurePosixPath(text.strip()).is_absolute()
                ):
                    raise ValueError(
                        "WebHDFS token and CA files must be absolute file paths."
                    )
        source.update(input_settings(value))
        source["path"] = "\n".join(paths)
        result.append(source)
    return result


def save_sources(values: object) -> list[Result]:
    """Atomically save Source records in SQLite; active runs retain their own snapshots."""
    sources = validate_sources(values)
    _write_sources(sources)
    return load_sources()


def _write_sources(sources: list[Result]) -> None:
    save_records("sources", {item["id"]: item for item in sources})


def source_pattern(source: Result) -> str:
    """Qualify remote paths by their SSH host or HDFS endpoint in results."""
    if source.get("type") == "webhdfs":
        endpoint = urlsplit(source["endpoint"])
        scheme = "swebhdfs" if endpoint.scheme == "https" else "webhdfs"
        return f"{scheme}://{endpoint.netloc}{source['path']}"
    if source.get("type") == "hdfs":
        host = source["host"]
        if ":" in host:
            host = f"[{host}]"
        port = f":{source['port']}" if source.get("port") else ""
        return f"hdfs://{host}{port}{source['path']}"
    if source.get("type") != "ssh":
        return source["path"]
    host = source["host"]
    if ":" in host:
        host = f"[{host}]"
    return f"ssh://{source['username']}@{host}:{source['port']}{source['path']}"


def source_paths(value: str) -> list[str]:
    """Return distinct nonempty paths from a newline-separated Source field."""
    return list(
        dict.fromkeys(line.strip() for line in value.splitlines() if line.strip())
    )


def source_patterns(source: Result) -> list[str]:
    """Return an individual result-filter pattern for every configured path."""
    return [
        source_pattern({**source, "path": path})
        for path in source_paths(source["path"])
    ]
