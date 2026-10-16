"""Persist reusable local and SSH file sources independently of run settings."""

import json
import os
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath
from uuid import uuid4

from classifier import Result
from ssh_hosts import import_legacy_host

DEFAULT_SOURCES = [
    {"id": f"{index:032x}", "name": name, "type": "local", "path": path}
    for index, name, path in (
        (1, "System messages", "/host-logs/var/log/messages"),
        (2, "Sample HTTP access", "/host-logs/sample-logs/access-1k.log"),
        (3, "Sample SSH authentication", "/host-logs/sample-logs/SSH_2k.log"),
    )
]


def get_sources_path() -> Path:
    """Return the source registry under the shared persistent data directory."""
    directory = os.getenv("DECIFLOW_DATA_DIR", "").strip() or "/var/lib/deciflow-data"
    return Path(directory).expanduser().absolute() / "sources" / "sources.json"


def load_sources() -> list[Result]:
    """Read saved sources, or provide editable sample sources before the first save."""
    path = get_sources_path()
    values = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else deepcopy(DEFAULT_SOURCES)
    )
    if not isinstance(values, list):
        raise TypeError("Invalid source registry.")
    legacy_hosts: dict[str, str] = {}
    for source in values:
        if not isinstance(source, dict) or source.get("type") not in {"local", "ssh"}:
            raise ValueError("Invalid source registry.")
        if any(
            not isinstance(source.get(key), str) or not source[key].strip()
            for key in ("id", "name", "type", "path")
        ):
            raise ValueError("Invalid source registry fields.")
        if source["type"] == "ssh":
            if source.get("hostId"):
                legacy_hosts[source["id"]] = source["hostId"]
            elif source.get("host"):
                legacy_hosts[source["id"]] = import_legacy_host(source)
    if legacy_hosts:
        # Write Tasks first so an interrupted migration can be repeated safely.
        task_path = path.parent.parent / "tasks" / "tasks.json"
        if task_path.exists():
            tasks = json.loads(task_path.read_text(encoding="utf-8"))
            for task in tasks:
                for selection in task["sources"]:
                    identity = selection.get("sourceId")
                    if identity in legacy_hosts and "hostIds" not in selection:
                        selection["hostIds"] = [legacy_hosts[identity]]
            temporary = task_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(tasks, indent=2) + "\n", encoding="utf-8")
            temporary.replace(task_path)
        values = [
            {key: source[key] for key in ("id", "name", "type", "path")}
            for source in values
        ]
        _write_sources(values)

    return values


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
        if source["type"] == "ssh" and not PurePosixPath(source["path"]).is_absolute():
            raise ValueError("Remote file paths must be absolute POSIX paths.")
        result.append(source)
    return result


def save_sources(values: object) -> list[Result]:
    """Atomically save source definitions; active runs retain their own snapshots."""
    sources = validate_sources(values)
    _write_sources(sources)
    return load_sources()


def _write_sources(sources: list[Result]) -> None:
    path = get_sources_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def source_pattern(source: Result) -> str:
    """Disambiguate identical remote paths on different SSH hosts in results."""
    if source.get("type") != "ssh":
        return source["path"]
    host = source["host"]
    if ":" in host:
        host = f"[{host}]"
    return f"ssh://{source['username']}@{host}:{source['port']}{source['path']}"
