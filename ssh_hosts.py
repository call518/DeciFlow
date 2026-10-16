"""Persist reusable SSH connections independently of log file paths."""

import asyncio
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import asyncssh

from classifier import Result
from config_store import delete_record, get_data_directory, load_records, save_record
from ssh_keys import get_key


def get_hosts_directory() -> Path:
    """Return the directory for approved SSH known_hosts keys."""
    return get_data_directory() / "ssh-hosts"


def load_hosts() -> list[Result]:
    """Read saved SSH connections without opening network connections."""
    return [
        {**host, "keyPath": get_key(host["keyId"])["privatePath"]}
        for host in load_records("ssh_hosts").values()
    ]


def _validate_host(value: object, *, check_file: bool = True) -> Result:
    if not isinstance(value, dict):
        raise TypeError("Enter SSH host details.")
    host: Result = {}
    for field in ("name", "host", "username"):
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
    key = get_key(value.get("keyId"))
    host["keyId"] = key["id"]
    path = Path(key["privatePath"])
    if check_file and not path.is_file():
        raise ValueError("Select an SSH key readable by DeciFlow.")
    return {**host, "id": identity, "port": port, "keyPath": str(path)}


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
    save_record(
        "ssh_hosts",
        host["id"],
        {key: value for key, value in host.items() if key != "keyPath"},
    )
    return host


def delete_host(identity: object, references: list[Result]) -> None:
    """Delete a connection only when no saved Task or running job uses it."""
    hosts = load_hosts()
    if not any(host["id"] == identity for host in hosts):
        raise ValueError("SSH host not found.")
    if any(source.get("hostId") == identity for source in references):
        raise ValueError("This SSH host is used by a saved Task or running job.")
    delete_record("ssh_hosts", str(identity))


def known_host_data() -> bytes:
    """Read only DeciFlow's persistent host approvals, separate from user SSH."""
    path = get_hosts_directory() / "known_hosts"
    return path.read_bytes() if path.is_file() else b""


class HostKeyCheck(asyncssh.SSHClient):
    """Require explicit approval for a new host key; reject changed keys."""

    def __init__(
        self, known: asyncssh.SSHKnownHosts, approved: asyncssh.SSHKey | None
    ) -> None:
        self.known = known
        self.approved = approved
        self.key: asyncssh.SSHKey | None = None
        self.changed = False
        self.revoked = False

    def validate_host_public_key(
        self, host: str, addr: str, port: int, key: asyncssh.SSHKey
    ) -> bool:
        """Capture the presented key without trusting unknown or changed keys."""
        self.key = key
        matched = asyncssh.match_known_hosts(self.known, host, addr, port)
        exact = asyncssh.match_known_hosts(self.known, f"[{host}]:{port}", "", None)
        address_match = asyncssh.match_known_hosts(
            self.known, f"[{addr}]:{port}", "", None
        )
        self.changed = bool(matched[0] or exact[0] or address_match[0])
        self.revoked = key in matched[2] or key in exact[2] or key in address_match[2]
        return (
            not self.changed
            and not self.revoked
            and self.approved is not None
            and key == self.approved
        )


def _remember_host_key(host: Result, key: asyncssh.SSHKey) -> None:
    path = get_hosts_directory() / "known_hosts"
    path.parent.mkdir(parents=True, exist_ok=True)
    address = host["host"] if host["port"] == 22 else f"[{host['host']}]:{host['port']}"
    line = f"{address} {key.export_public_key().decode().strip()}\n"
    if path.exists() and line in path.read_text(encoding="utf-8").splitlines(True):
        return
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as output:
        output.write(line)


def ssh_connection_options(host: Result) -> Result:
    """Use the same verified, key-only SSH connection for reading and testing."""
    return {
        "port": host["port"],
        "known_hosts": asyncssh.import_known_hosts(known_host_data().decode()),
        "username": host["username"],
        "client_keys": [host["keyPath"]],
        "agent_path": None,
        "config": None,
        "preferred_auth": "publickey",
        "connect_timeout": 15,
        "login_timeout": 15,
        "keepalive_interval": 15,
        "keepalive_count_max": 2,
    }


async def test_host_connection(
    value: object, trusted_host_key: object = None
) -> Result:
    """Check SSH authentication and SFTP without saving or reading remote logs."""
    host = _validate_host(value)
    approved = None
    if trusted_host_key is not None:
        if not isinstance(trusted_host_key, str):
            raise ValueError("Invalid host key approval.")
        approved = asyncssh.import_public_key(trusted_host_key)
    options = ssh_connection_options(host)
    check = HostKeyCheck(options["known_hosts"], approved)
    started = perf_counter()
    result: Result = {"connected": False}
    try:
        async with asyncio.timeout(15):
            async with asyncssh.connect(
                host["host"], client_factory=lambda: check, **options
            ) as connection:
                if approved is not None and check.key == approved:
                    _remember_host_key(host, approved)
                async with connection.start_sftp_client():
                    result["connected"] = True
    except (asyncssh.Error, OSError, TimeoutError) as error:
        result["error"] = (
            "Connection test timed out after 15 seconds."
            if isinstance(error, TimeoutError)
            else str(error) or type(error).__name__
        )
    if isinstance(result.get("error"), str) and check.key is not None:
        if check.revoked:
            result["error"] = (
                "Host key is revoked. Verify the host before updating known_hosts."
            )
        elif check.changed:
            result["error"] = (
                "Host key changed. Verify the host and update its known_hosts entry."
            )
        elif not result["connected"] and approved is None:
            result["hostKey"] = {
                "fingerprint": check.key.get_fingerprint(),
                "publicKey": check.key.export_public_key().decode().strip(),
                "host": host["host"],
                "port": host["port"],
            }
    return {
        **result,
        "checkedAt": datetime.now(UTC).isoformat(),
        "elapsedMs": round((perf_counter() - started) * 1000),
    }
