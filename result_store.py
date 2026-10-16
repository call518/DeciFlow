"""Keep result persistence behind one repository, independent of HTTP and providers.

SQLite is the first adapter. Future PostgreSQL/MySQL adapters must preserve the
append/page/events/review/summary contract; callers never issue SQL themselves.
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import RLock
from typing import Protocol

from classifier import Result

CATEGORIES = ("normal", "warning", "error", "security", "other")


def empty_summary() -> Result:
    """Return aggregates whose size depends on hosts/sources, not result count."""
    return {
        "total": 0,
        "failed": 0,
        "review": 0,
        "truncated": 0,
        "processingMs": 0,
        "actionSuccess": 0,
        "actionFailed": 0,
        "groups": {"all": 0, "certain": 0, "uncertain": 0},
        "categories": {
            group: dict.fromkeys(CATEGORIES, 0)
            for group in ("all", "certain", "uncertain")
        },
        "hosts": {},
        "sources": {},
    }


def _host_id(result: Result) -> str:
    if result.get("hostId"):
        return result["hostId"]
    source = result.get("source", "")
    if source.startswith("ssh://"):
        return "legacy:" + source[6:].split("/", 1)[0].split("@")[-1]
    return "local"


def _aggregate(stats: Result, result: Result) -> None:
    stats["total"] += 1
    failed = bool(result.get("error"))
    stats["failed"] += failed
    stats["review"] += not failed and bool(result.get("review"))
    stats["truncated"] += (
        result.get("providerResponse", {}).get("usage", {}).get("truncated") is True
    )
    stats["processingMs"] += result.get("elapsedMs", 0)
    action = result.get("actionExecution", {}).get("status")
    stats["actionSuccess"] += action == "success"
    stats["actionFailed"] += action == "failed"
    category = result.get("category")
    if not failed and category in CATEGORIES:
        group = "uncertain" if result.get("uncertain") else "certain"
        for name in ("all", group):
            stats["groups"][name] += 1
            stats["categories"][name][category] += 1
    host = _host_id(result)
    entry = stats["hosts"].setdefault(
        host,
        {
            "name": result.get(
                "hostName",
                host.removeprefix("legacy:") if host != "local" else "DeciFlow (Local)",
            ),
            "count": 0,
            "failed": 0,
        },
    )
    entry["count"] += 1
    entry["failed"] += failed
    for source in set(result.get("sourcePatterns", [result.get("source", "")])):
        if source:
            stats["sources"][source] = stats["sources"].get(source, 0) + 1


class ResultRepository(Protocol):
    """Backend contract shared by execution, HTTP, and export callers."""

    def close(self) -> None: ...
    def contains(self, run_id: str) -> bool: ...
    def create(self, run_id: str, snapshot: Result) -> None: ...
    def save_snapshot(self, run_id: str, snapshot: Result) -> None: ...
    def append(self, run_id: str, event: Result, snapshot: Result) -> None: ...
    def recover_interrupted(self) -> None: ...
    def delete_task(self, task_id: str) -> None: ...
    def history(self, task_id: str, limit: int) -> list[Result]: ...
    def state(self, run_id: str) -> Result: ...
    def page(self, run_id: str, filters: Result, limit: int) -> Result: ...
    def review(self, run_id: str, sequence: int, category: str) -> None: ...
    def events(
        self, run_id: str, after: int = 0, *, reviewed_only: bool = False
    ) -> list[tuple[int, str]]: ...


class SQLiteResultStore:
    """Store append-only events, indexed result pages, and incremental aggregates."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = RLock()
        self.connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        path.chmod(0o600)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            PRAGMA cache_size=-2048;
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, snapshot TEXT NOT NULL,
                summary TEXT NOT NULL, sequence INTEGER NOT NULL DEFAULT 0,
                task_id TEXT, started_at TEXT, state TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS run_history ON runs(task_id,started_at DESC);
            CREATE INDEX IF NOT EXISTS run_state ON runs(state);
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                kind TEXT NOT NULL, payload TEXT NOT NULL,
                category TEXT, host TEXT, review INTEGER, failed INTEGER,
                log_folded TEXT, reviewer TEXT,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS result_page
                ON events(run_id, kind, sequence);
            CREATE INDEX IF NOT EXISTS result_category
                ON events(run_id, category, sequence);
            CREATE INDEX IF NOT EXISTS result_host
                ON events(run_id, host, sequence);
            CREATE INDEX IF NOT EXISTS reviewed_changes
                ON events(run_id, sequence)
                WHERE kind='result' AND failed=0
                    AND reviewer<>'' AND reviewer<>category;
            CREATE TABLE IF NOT EXISTS sources (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence, source)
            );
            CREATE INDEX IF NOT EXISTS result_source
                ON sources(run_id, source, sequence);
        """)

    def close(self) -> None:
        """Release the database connection after all application jobs stop."""
        with self.lock:
            self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize short transactions; never retain a reader across a download."""
        with self.lock, self.connection:
            yield self.connection

    @contextmanager
    def reader(self) -> Iterator[sqlite3.Connection]:
        """Read without blocking the single WAL writer or retaining snapshots."""
        with closing(
            sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=30)
        ) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA cache_size=-2048")
            yield connection

    def contains(self, run_id: str) -> bool:
        """Return whether an execution exists in the database."""
        with self.lock:
            return (
                self.connection.execute(
                    "SELECT 1 FROM runs WHERE id=?", (run_id,)
                ).fetchone()
                is not None
            )

    def create(self, run_id: str, snapshot: Result) -> None:
        """Create an empty run without overwriting an existing execution."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO runs(id,snapshot,summary,task_id,started_at,state) VALUES(?,?,?,?,?,?)",
                (
                    run_id,
                    json.dumps(snapshot),
                    json.dumps(empty_summary()),
                    snapshot.get("settings", {}).get("taskId"),
                    snapshot.get("startedAt"),
                    snapshot.get("state", "running"),
                ),
            )

    def history(self, task_id: str, limit: int) -> list[Result]:
        """Fetch recent run metadata using an index instead of directory sorting."""
        with self.lock:
            rows = self.connection.execute(
                "SELECT snapshot FROM runs WHERE task_id=? ORDER BY started_at DESC,id DESC LIMIT ?",
                (task_id, limit),
            ).fetchall()
            return [
                {**json.loads(row["snapshot"]), "pagedResults": True} for row in rows
            ]

    def save_snapshot(self, run_id: str, snapshot: Result) -> None:
        """Persist the execution state separately from result payloads."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE runs SET snapshot=?,state=? WHERE id=?",
                (json.dumps(snapshot), snapshot["state"], run_id),
            )

    def _append(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        event: Result,
        sequence: int,
        stats: Result,
    ) -> None:
        if event["type"] == "start":
            stats["engine"] = event.get("engine")
        result = event.get("result", {})
        failed = bool(result.get("error"))
        connection.execute(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                sequence,
                event["type"],
                json.dumps(event, ensure_ascii=False),
                result.get("category"),
                _host_id(result),
                int(not failed and bool(result.get("review"))),
                int(failed),
                result.get("log", "").lower(),
                None,
            ),
        )
        if event["type"] != "result":
            return
        _aggregate(stats, result)
        elapsed = event.get("elapsedMs", 0)
        buckets = stats.setdefault("throughputBuckets", {})
        for bucket in list(buckets):
            if int(bucket) * 100 <= elapsed - 5000:
                del buckets[bucket]
        if not failed:
            bucket = str(int(elapsed / 100))
            buckets[bucket] = buckets.get(bucket, 0) + 1
        connection.executemany(
            "INSERT INTO sources VALUES(?,?,?)",
            [
                (run_id, sequence, source)
                for source in set(
                    result.get("sourcePatterns", [result.get("source", "")])
                )
                if source
            ],
        )

    def append(self, run_id: str, event: Result, snapshot: Result) -> None:
        """Commit an event and its aggregates atomically, without retaining history."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT summary,sequence FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            stats = json.loads(row["summary"])
            sequence = row["sequence"] + 1
            self._append(connection, run_id, event, sequence, stats)
            connection.execute(
                "UPDATE runs SET summary=?,sequence=?,snapshot=?,state=? WHERE id=?",
                (
                    json.dumps(stats),
                    sequence,
                    json.dumps(snapshot),
                    snapshot["state"],
                    run_id,
                ),
            )

    def recover_interrupted(self) -> None:
        """Stop interrupted DB runs in bounded batches without replaying inputs."""
        while True:
            with self.reader() as connection:
                rows = connection.execute(
                    "SELECT id,snapshot FROM runs WHERE state='running' LIMIT 128"
                ).fetchall()
            if not rows:
                return
            for row in rows:
                snapshot = json.loads(row["snapshot"])
                snapshot.update(
                    state="stopped",
                    finishedAt=datetime.now(UTC).isoformat(),
                    error="Server restarted; execution was interrupted.",
                )
                self.append(
                    row["id"],
                    {
                        "type": "done",
                        "state": "stopped",
                        "elapsedMs": snapshot.get("elapsedMs", 0),
                        "activeProcessingMs": snapshot.get("activeProcessingMs", 0),
                    },
                    snapshot,
                )

    def delete_task(self, task_id: str) -> None:
        """Delete all run records and related rows for exactly one Task."""
        with self.transaction() as connection:
            for table in ("sources", "events"):
                connection.execute(
                    f"DELETE FROM {table} WHERE run_id IN "
                    "(SELECT id FROM runs WHERE task_id=?)",
                    (task_id,),
                )
            connection.execute("DELETE FROM runs WHERE task_id=?", (task_id,))

    def state(self, run_id: str) -> Result:
        """Read a bounded run snapshot and aggregate record."""
        with self.lock:
            row = self.connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            return {
                "snapshot": json.loads(row["snapshot"]),
                "summary": json.loads(row["summary"]),
                "sequence": row["sequence"],
            }

    def page(self, run_id: str, filters: Result, limit: int) -> Result:
        """Read a keyset page; never use an OFFSET proportional to history length."""
        if type(limit) is not int or limit not in {10, 30, 50, 100}:
            raise ValueError("Invalid page size.")
        where = ["e.run_id=?", "e.kind='result'"]
        params: list[object] = [run_id]
        for key, operator in (("before", "<"), ("after", ">"), ("through", "<=")):
            value = filters.get(key)
            if value is not None:
                if type(value) is not int or not 0 <= value < 2**63:
                    raise ValueError("Invalid result cursor.")
                where.append(f"e.sequence {operator} ?")
                params.append(value)
        category = filters.get("category", "all")
        if category == "failed":
            where.append("e.failed=1")
        elif category != "all":
            if category not in CATEGORIES:
                raise ValueError("Invalid category filter.")
            where.extend(["e.category=?", "e.failed=0"])
            params.append(category)
        review = filters.get("review", "all")
        if review != "all":
            if review not in {"needs-review", "no-review"}:
                raise ValueError("Invalid review filter.")
            where.extend(["e.review=?", "e.failed=0"])
            params.append(int(review == "needs-review"))
        host = filters.get("host", "all")
        if host != "all":
            where.append("e.host=?")
            params.append(host)
        source = filters.get("source", "all")
        if source != "all":
            where.append(
                "EXISTS (SELECT 1 FROM sources s WHERE s.run_id=e.run_id "
                "AND s.sequence=e.sequence AND s.source=?)"
            )
            params.append(source)
        search = filters.get("search", "")
        if not isinstance(search, str):
            raise TypeError("Invalid search text.")
        if search:
            where.append("instr(e.log_folded,?)>0")
            params.append(search.lower())
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT e.sequence,e.payload,e.reviewer FROM events e WHERE "
                + " AND ".join(where)
                + " ORDER BY e.sequence DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        return {
            "items": [
                {"sequence": row["sequence"], "result": self._result(row)}
                for row in rows[:limit]
            ],
            "hasNext": len(rows) > limit,
            "limit": limit,
        }

    @staticmethod
    def _result(row: sqlite3.Row) -> Result:
        result = json.loads(row["payload"])["result"]
        if row["reviewer"] is not None:
            result["reviewerCategory"] = row["reviewer"]
        return result

    def review(self, run_id: str, sequence: int, category: str) -> None:
        """Save a human correction without altering AI categories or aggregates."""
        if type(sequence) is not int or category not in (*CATEGORIES, ""):
            raise ValueError("Invalid reviewer category or result cursor.")
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE events SET reviewer=? WHERE run_id=? AND sequence=? "
                "AND kind='result' AND failed=0",
                (category, run_id, sequence),
            )
            if not cursor.rowcount:
                raise ValueError("Result not found or classification failed.")

    def events(
        self, run_id: str, after: int = 0, *, reviewed_only: bool = False
    ) -> list[tuple[int, str]]:
        """Read bounded events, optionally only human changes to AI categories."""
        selection = (
            " AND kind='result' AND failed=0 AND reviewer<>'' AND reviewer<>category"
            if reviewed_only
            else ""
        )
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT sequence,payload,reviewer,kind FROM events "
                f"WHERE run_id=? AND sequence>?{selection} ORDER BY sequence LIMIT 128",
                (run_id, after),
            ).fetchall()
        output = []
        for row in rows:
            event = json.loads(row["payload"])
            if row["kind"] == "result" and row["reviewer"] is not None:
                event["result"]["reviewerCategory"] = row["reviewer"]
            output.append((row["sequence"], json.dumps(event) + "\n"))
        return output


@lru_cache(maxsize=8)
def _cached_store(root: Path) -> ResultRepository:
    """Select the result repository adapter; SQL stays inside its implementation."""
    return SQLiteResultStore(root / "deciflow.sqlite3")


_STORE_LOCK = RLock()


def open_result_store(root: Path) -> ResultRepository:
    """Select the backend once per root; future adapters implement ResultRepository."""
    with _STORE_LOCK:
        return _cached_store(root.absolute())


def close_result_store(root: Path) -> None:
    """Close the active data repository before deleting its files."""
    with _STORE_LOCK:
        _cached_store(root.absolute()).close()
        _cached_store.cache_clear()
