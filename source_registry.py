"""Persist reusable local and SSH file sources independently of run settings."""

import json
import os
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath
from uuid import uuid4

from classifier import Result
from ssh_hosts import import_legacy_host, load_hosts

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
    migrated = False
    for source in values:
        if not isinstance(source, dict) or source.get("type") not in {"local", "ssh"}:
            raise ValueError("Invalid source registry.")
        fields = ("id", "name", "type", "path")
        if any(
            not isinstance(source.get(key), str) or not source[key].strip()
            for key in fields
        ):
            raise ValueError("Invalid source registry fields.")
        if source["type"] == "ssh":
            if "hostId" not in source:
                source["hostId"] = import_legacy_host(source)
                migrated = True
            if not isinstance(source["hostId"], str) or not source["hostId"]:
                raise ValueError("Invalid SSH host reference in source registry.")
    hosts = {host["id"]: host for host in load_hosts()}
    if migrated:
        _write_sources(
            [
                {
                    key: source[key]
                    for key in ("id", "name", "type", "path", "hostId")
                    if key in source
                }
                for source in values
            ]
        )
    for source in values:
        if source["type"] == "ssh":
            host = hosts.get(source["hostId"])
            if host is None:
                raise ValueError("The Source references a missing SSH host.")
            source.update(
                {key: host[key] for key in ("host", "port", "username", "keyPath")}
            )
            source["hostName"] = host["name"]
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
        if source["type"] == "ssh":
            identity = value.get("hostId")
            if not isinstance(identity, str) or not any(
                host["id"] == identity for host in load_hosts()
            ):
                raise ValueError("Select an SSH host registered in Settings.")
            source["hostId"] = identity
            if not PurePosixPath(source["path"]).is_absolute():
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
