"""Manage UUID-based SSH key metadata without exposing private key contents."""

import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

import asyncssh

from deciflow.classifier import Result
from deciflow.config_store import (
    delete_record,
    get_data_directory,
    load_records,
    save_record,
)


def get_keys_directory() -> Path:
    """Return the private SSH key directory in persistent application storage."""
    directory = get_data_directory() / "ssh-keys"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def _key_directory(identity: object) -> Path:
    if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{32}", identity):
        raise ValueError("Select a valid SSH Key.")
    directory = get_keys_directory() / identity
    if directory.is_symlink():
        raise ValueError("SSH key directory must not be a symlink.")
    return directory


def _validate_name(name: object, identity: str = "") -> str:
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9_ -]{1,64}", name)
        or not name.strip()
    ):
        raise ValueError(
            "Use 1–64 letters, digits, spaces, underscores, or hyphens for the key name."
        )
    name = name.strip()
    if any(
        key != identity and item["name"].casefold() == name.casefold()
        for key, item in load_records("ssh_keys").items()
    ):
        raise ValueError("An SSH key with this name already exists.")
    return name


def get_key(identity: object) -> Result:
    """Resolve a managed SSH Key UUID into metadata and fixed file locations."""
    directory = _key_directory(identity)
    record = load_records("ssh_keys").get(str(identity))
    if record is None:
        raise ValueError("SSH key not found.")
    return {
        **record,
        "privatePath": str(directory / "private_key"),
        "publicPath": str(directory / "public_key.pub"),
    }


def list_keys() -> list[Result]:
    """List registered keys and public material, never private key contents."""
    keys = []
    for identity in load_records("ssh_keys"):
        key = get_key(identity)
        public = Path(key["publicPath"])
        key["publicKey"] = (
            public.read_text(encoding="utf-8") if public.is_file() else ""
        )
        keys.append(key)
    return sorted(keys, key=lambda key: key["name"].casefold())


def add_key(name: object, private_key: object) -> Result:
    """Import an unencrypted key under a UUID and register its display name."""
    name = _validate_name(name)
    if not isinstance(private_key, str) or len(private_key) > 65536:
        raise ValueError("Select a private key file of at most 64 KiB.")
    try:
        key = asyncssh.import_private_key(private_key)
    except (ValueError, asyncssh.KeyImportError) as error:
        raise ValueError("Provide a valid private key without a passphrase.") from error
    identity = uuid4().hex
    directory = _key_directory(identity)
    directory.mkdir(mode=0o700)
    try:
        private = directory / "private_key"
        with private.open("xb") as output:
            os.chmod(private, 0o600)
            output.write(key.export_private_key("openssh"))
        public = directory / "public_key.pub"
        public.write_bytes(key.export_public_key("openssh"))
        public.chmod(0o644)
        record = {"id": identity, "name": name}
        save_record("ssh_keys", identity, record)
    except Exception:
        shutil.rmtree(directory)
        raise
    return get_key(identity)


def rename_key(identity: object, name: object) -> None:
    """Rename metadata while keeping UUID references and physical paths stable."""
    key = get_key(identity)
    name = _validate_name(name, key["id"])
    save_record("ssh_keys", key["id"], {"id": key["id"], "name": name})


def add_key_from_path(name: object, path: object) -> Result:
    """Copy a private key from a server-side file into managed storage."""
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("Enter a private key file path.")
    source = Path(path.strip()).expanduser()
    if not source.is_file():
        raise ValueError("The private key path must identify a readable file.")
    with source.open("rb") as stream:
        contents = stream.read(65537)
    if len(contents) > 65536:
        raise ValueError("The private key file must be at most 64 KiB.")
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Provide a UTF-8 private key file.") from error
    return add_key(name, text)


def delete_key(identity: object, active_sources: list[Result]) -> None:
    """Delete unused UUID key metadata and files without following symlinks."""
    from deciflow.ssh_hosts import load_hosts

    key = get_key(identity)
    if any(
        source.get("keyId") == identity for source in [*load_hosts(), *active_sources]
    ):
        raise ValueError("This SSH key is used by an SSH Host or running job.")
    directory = _key_directory(identity)
    if directory.exists():
        shutil.rmtree(directory)
    delete_record("ssh_keys", key["id"])
