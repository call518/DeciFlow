"""Persist reusable SSH connections independently of log file paths."""

import json
import os
import re
from pathlib import Path
from uuid import uuid4

from classifier import Result


def get_hosts_path() -> Path:
    """Return the SSH host registry in the shared data volume."""
    root = os.getenv("DECIFLOW_DATA_DIR", "").strip() or "/var/lib/deciflow-data"
    return Path(root).expanduser().absolute() / "ssh-hosts" / "hosts.json"


def load_hosts() -> list[Result]:
    """Read saved SSH connections without opening network connections."""
    path = get_hosts_path()
    hosts = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    if not isinstance(hosts, list):
        raise TypeError("Invalid SSH host registry.")
    for host in hosts:
        if not isinstance(host, dict) or not host.get("id"):
            raise ValueError("Invalid SSH host registry fields.")
        _validate_host(host, check_file=False)
    return hosts


def _validate_host(value: object, *, check_file: bool = True) -> Result:
    if not isinstance(value, dict):
        raise TypeError("Enter SSH host details.")
    host: Result = {}
    for field in ("name", "host", "username", "keyPath"):
        text = value.get(field)
        if (
            not isinstance(text, str)
            or not text.strip()
            or any(char in text for char in "\x00\n\r")
        ):
            raise ValueError(f"Enter a single-line SSH {field}.")
        host[field] = text.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", host["host"]):
        raise ValueError("Enter an SSH hostname or IP address, not a URL.")
    if not re.fullmatch(r"[^/@:\s]+", host["username"]):
        raise ValueError("Enter an SSH username, not a connection URL.")
    port = value.get("port", 22)
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("SSH port must be between 1 and 65535.")
    identity = value.get("id") or uuid4().hex
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Invalid SSH host ID.")
    path = Path(host["keyPath"]).expanduser().absolute()
    if check_file and not path.is_file():
        raise ValueError("Select an SSH key readable by DeciFlow.")
    return {**host, "id": identity, "port": port, "keyPath": str(path)}


def _write_hosts(hosts: list[Result]) -> None:
    path = get_hosts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(hosts, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def save_host(value: object) -> Result:
    """Add or edit a connection; active runs retain their resolved settings."""
    host = _validate_host(value)
    hosts = load_hosts()
    existing = next((item for item in hosts if item["id"] == host["id"]), None)
    if isinstance(value, dict) and value.get("id") and existing is None:
        raise ValueError("SSH host not found.")
    if any(
        item["id"] != host["id"] and item["name"].casefold() == host["name"].casefold()
        for item in hosts
    ):
        raise ValueError("SSH host names must be unique.")
    _write_hosts([item for item in hosts if item["id"] != host["id"]] + [host])
    return host


def import_legacy_host(source: Result) -> str:
    """Reuse or preserve an existing Source connection during schema migration."""
    hosts = load_hosts()
    fields = ("host", "port", "username", "keyPath")
    for host in hosts:
        if all(host[field] == source.get(field) for field in fields):
            return host["id"]
    name = source["name"]
    suffix = 2
    while any(host["name"].casefold() == name.casefold() for host in hosts):
        name = f"{source['name']} ({suffix})"
        suffix += 1
    host = _validate_host({**source, "id": uuid4().hex, "name": name}, check_file=False)
    _write_hosts([*hosts, host])
    return host["id"]


def delete_host(identity: object, references: list[Result]) -> None:
    """Delete a connection only when no saved Source or running job uses it."""
    hosts = load_hosts()
    if not any(host["id"] == identity for host in hosts):
        raise ValueError("SSH host not found.")
    if any(source.get("hostId") == identity for source in references):
        raise ValueError("This SSH host is used by a saved Source or running job.")
    _write_hosts([host for host in hosts if host["id"] != identity])
