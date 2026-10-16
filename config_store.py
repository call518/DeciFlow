"""Persist configuration records alongside execution data in SQLite."""

import json
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

Records = dict[str, dict[str, Any]]


def get_data_directory() -> Path:
    """Return the shared application data root."""
    root = os.getenv("DECIFLOW_DATA_DIR", "").strip() or "/var/lib/deciflow-data"
    return Path(root).expanduser().absolute()


def get_database_path() -> Path:
    """Return the database containing configurations and execution results."""
    return get_data_directory() / "deciflow.sqlite3"


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    path = get_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(path, timeout=30)) as connection:
            path.chmod(0o600)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS configuration_collections (
                    kind TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS configuration_records (
                    kind TEXT NOT NULL REFERENCES configuration_collections(kind),
                    id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (kind, id)
                );
            """)
            with connection:
                yield connection
    except sqlite3.Error as error:
        raise OSError(f"Configuration storage failed: {error}") from error


def load_records(kind: str, defaults: Records | None = None) -> Records:
    """Initialize a collection once and read its individual ordered records."""
    with _connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM configuration_collections WHERE kind=?", (kind,)
        ).fetchone()
        if not exists:
            connection.execute("BEGIN IMMEDIATE")
            # Recheck after locking: another first reader may have seeded it.
            if not connection.execute(
                "SELECT 1 FROM configuration_collections WHERE kind=?", (kind,)
            ).fetchone():
                _replace(connection, kind, defaults or {})
        rows = connection.execute(
            "SELECT id,payload FROM configuration_records WHERE kind=? "
            "ORDER BY position,id",
            (kind,),
        ).fetchall()
        return {identity: json.loads(payload) for identity, payload in rows}


def _replace(connection: sqlite3.Connection, kind: str, records: Records) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO configuration_collections VALUES(?)", (kind,)
    )
    connection.execute("DELETE FROM configuration_records WHERE kind=?", (kind,))
    connection.executemany(
        "INSERT INTO configuration_records VALUES(?,?,?,?)",
        [
            (kind, identity, index, json.dumps(record, ensure_ascii=False))
            for index, (identity, record) in enumerate(records.items())
        ],
    )


def save_records(kind: str, records: Records) -> None:
    """Replace a submitted collection atomically, retaining explicit empty lists."""
    with _connection() as connection:
        _replace(connection, kind, records)


def save_record(kind: str, identity: str, record: dict[str, Any]) -> None:
    """Insert or update one item without overwriting concurrent unrelated edits."""
    with _connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO configuration_collections VALUES(?)", (kind,)
        )
        connection.execute(
            "INSERT INTO configuration_records(kind,id,position,payload) "
            "VALUES(?,?,(SELECT COALESCE(MAX(position),-1)+1 FROM "
            "configuration_records WHERE kind=?),?) "
            "ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload",
            (kind, identity, kind, json.dumps(record, ensure_ascii=False)),
        )


def delete_record(kind: str, identity: str) -> None:
    """Delete one configuration record without changing the collection marker."""
    with _connection() as connection:
        connection.execute(
            "DELETE FROM configuration_records WHERE kind=? AND id=?", (kind, identity)
        )
