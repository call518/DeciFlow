"""Persist reusable local and SSH file sources independently of run settings."""

import re
from pathlib import PurePosixPath
from uuid import uuid4

from classifier import Result
from config_store import load_records, save_record, save_records

VOC_SOURCE = {
    "id": f"{5:032x}",
    "name": "VOC Consultations",
    "type": "local",
    "path": "/host-logs/sample-logs/voc-consulting_content.jsonl",
    "format": "jsonl",
    "contentField": "consulting_content",
}

DEFAULT_SOURCES = [
    {"id": f"{index:032x}", "name": name, "type": "local", "path": path}
    for index, name, path in (
        (1, "System messages", "/host-logs/var/log/messages"),
        (2, "Sample HTTP access", "/host-logs/sample-logs/access-1k.log"),
        (3, "Sample SSH authentication", "/host-logs/sample-logs/SSH_2k.log"),
    )
] + [VOC_SOURCE]


def ensure_voc_source() -> None:
    """Add the consultation sample at startup without replacing saved Sources."""
    sources = load_sources()
    if any(
        source["id"] == VOC_SOURCE["id"]
        or source["name"].casefold() == VOC_SOURCE["name"].casefold()
        or (source["type"] == "local" and source["path"] == VOC_SOURCE["path"])
        for source in sources
    ):
        return
    save_record("sources", VOC_SOURCE["id"], VOC_SOURCE)


def load_sources() -> list[Result]:
    """Read saved Sources, persisting sample defaults on the first access."""
    return list(
        load_records("sources", {item["id"]: item for item in DEFAULT_SOURCES}).values()
    )


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
        if source["type"] not in {"local", "ssh"}:
            raise ValueError("Select Local File or Remote File (SSH).")
        identity = value.get("id") or uuid4().hex
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
            raise ValueError("Invalid source ID.")
        if identity in identities or source["name"].casefold() in names:
            raise ValueError("Source names and IDs must be unique.")
        identities.add(identity)
        names.add(source["name"].casefold())
        source["id"] = identity
        paths = source_paths(source["path"])
        if source["type"] == "ssh" and any(
            not PurePosixPath(path).is_absolute() for path in paths
        ):
            raise ValueError("Remote file paths must be absolute POSIX paths.")
        source.update(input_settings(value))
        source["path"] = "\n".join(paths)
        result.append(source)
    return result


def save_sources(values: object) -> list[Result]:
    """Atomically save Source records in SQLite; active runs retain their own snapshots."""
    sources = validate_sources(values)
    previous = {source["id"]: source for source in load_sources()}
    tasks = load_records("tasks")
    for source in sources:
        old = previous.get(source["id"])
        if old is None or old["type"] == source["type"]:
            continue
        references = [
            task["name"]
            for task in tasks.values()
            if any(item["sourceId"] == source["id"] for item in task["sources"])
        ]
        if references:
            raise ValueError(
                f"Source Type cannot be changed while used by Tasks: "
                f"{', '.join(references)}. Create another Source or remove "
                "these Task assignments first."
            )
    _write_sources(sources)
    return load_sources()


def _write_sources(sources: list[Result]) -> None:
    save_records("sources", {item["id"]: item for item in sources})


def source_pattern(source: Result) -> str:
    """Disambiguate identical remote paths on different SSH hosts in results."""
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
