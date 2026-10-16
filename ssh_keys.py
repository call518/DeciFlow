"""Store SSH key pairs without returning private key contents."""

import os
import re
import shutil
from pathlib import Path

import asyncssh

from classifier import Result
from source_registry import get_sources_path, load_sources
from ssh_hosts import load_hosts


def get_keys_directory() -> Path:
    """Return the private SSH key directory in persistent application storage."""
    directory = get_sources_path().parent.parent / "ssh-keys"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    return directory


def _key_directory(name: object) -> Path:
    if (
        not isinstance(name, str)
        or not name.strip()
        or not re.fullmatch(r"[A-Za-z0-9_ -]{1,64}", name)
    ):
        raise ValueError(
            "Use 1–64 letters, digits, spaces, underscores, or hyphens for the key name."
        )
    return get_keys_directory() / name


def list_keys() -> list[Result]:
    """List managed paths and public keys; never read private keys for display."""
    keys = []
    for directory in sorted(get_keys_directory().iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            continue
        private = directory / "private_key"
        public = directory / "public_key.pub"
        if private.is_file() and public.is_file():
            keys.append(
                {
                    "name": directory.name,
                    "privatePath": str(private),
                    "publicPath": str(public),
                    "publicKey": public.read_text(encoding="utf-8"),
                }
            )
    return keys


def add_key(name: object, private_key: object) -> None:
    """Import an unencrypted private key and derive its matching public key."""
    directory = _key_directory(name)
    if not isinstance(private_key, str) or len(private_key) > 65536:
        raise ValueError("Select a private key file of at most 64 KiB.")
    try:
        key = asyncssh.import_private_key(private_key)
    except (ValueError, asyncssh.KeyImportError) as error:
        raise ValueError("Provide a valid private key without a passphrase.") from error
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("An SSH key with this name already exists.") from error
    try:
        private = directory / "private_key"
        with private.open("xb") as output:
            os.chmod(private, 0o600)
            output.write(key.export_private_key("openssh"))
        public = directory / "public_key.pub"
        public.write_bytes(key.export_public_key("openssh"))
        public.chmod(0o644)
    except Exception:
        shutil.rmtree(directory)
        raise


def add_key_from_path(name: object, path: object) -> None:
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
    add_key(name, text)


def delete_key(name: object, active_sources: list[Result]) -> None:
    """Delete an unused managed pair without following directory symlinks."""
    directory = _key_directory(name)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("SSH key not found.")
    path = (directory / "private_key").resolve()
    for source in [*load_sources(), *load_hosts(), *active_sources]:
        if source.get("keyPath") and Path(source["keyPath"]).resolve() == path:
            raise ValueError(
                "This SSH key is used by an SSH Host, saved Source, or running job."
            )
    shutil.rmtree(directory)
