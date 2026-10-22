"""Keep result persistence behind one repository, independent of HTTP and providers.

SQLite is the first adapter. Future PostgreSQL/MySQL adapters must preserve the
append/page/events/review/summary contract; callers never issue SQL themselves.
"""

import json
import sqlite3
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import closing, contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Protocol

from classifier import Result
from decisions import (
    answer_value,
    decision_assessments,
    decision_bucket,
    is_probability,
    needs_review,
    result_answers,
    result_definitions,
)
from result_payload import compact_result


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
        "decisionGroups": {},
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


def _decision_entries(result: Result) -> Iterator[tuple[str, Result, str | None, str]]:
    if result.get("error"):
        return
    identity = result.get("criteriaGroup", "system")
    answers = result_answers(result)
    assessments = decision_assessments(result)
    for question, definition in result_definitions(result).items():
        kind = definition["type"]
        options = (
            list(definition["criteria"])
            if kind == "choice"
            else [
                f"{i} · {text.split(':')[0]}"
                for i, text in enumerate(definition["criteria"])
            ]
            if kind == "score"
            else ["0–<25%", "25–<50%", "50–<75%", "75–100%"]
        )
        entry = {
            "criteria": result.get("profileLabel", "System"),
            "identity": identity,
            "profileId": result.get("profileId", result.get("profile")),
            "question": question,
            "label": definition.get("label", question),
            "default": question == result.get("defaultDecision"),
            "type": kind,
            "options": options,
            "counts": {
                name: dict.fromkeys(options, 0)
                for name in ("all", "certain", "uncertain", "unassessed")
            },
        }
        uncertain = assessments.get(question, {}).get("uncertain")
        status = (
            (
                "uncertain"
                if uncertain is True
                else "certain"
                if uncertain is False
                else "unassessed"
            )
            if kind == "choice"
            else "not_applicable"
        )
        yield (
            f"{identity}:{question}",
            entry,
            decision_bucket(definition, answers.get(question, {})),
            status,
        )


def _aggregate_decisions(stats: Result, result: Result) -> None:
    for key, definition, bucket, status in _decision_entries(result):
        entry = stats.setdefault("decisionGroups", {}).setdefault(key, definition)
        if bucket is None:
            continue
        entry["counts"]["all"][bucket] += 1
        if status != "not_applicable":
            entry["counts"][status][bucket] += 1


def _assessed_result(result: Result) -> Result:
    if result.get("error"):
        return result
    assessments = decision_assessments(result)
    return {
        **result,
        "decisionAssessments": assessments,
        "anyUncertain": any(item["uncertain"] is True for item in assessments.values()),
        "needsReview": needs_review(result),
    }


def _aggregate(stats: Result, result: Result) -> None:
    _aggregate_decisions(stats, result)
    stats["total"] += 1
    failed = bool(result.get("error"))
    stats["failed"] += failed
    stats["review"] += needs_review(result)
    provider = result.get("providerResponse")
    usage = provider.get("usage") if isinstance(provider, dict) else None
    stats["truncated"] += isinstance(usage, dict) and usage.get("truncated") is True
    stats["processingMs"] += result.get("elapsedMs", 0)
    action = result.get("actionExecution", {}).get("status")
    stats["actionSuccess"] += action == "success"
    stats["actionFailed"] += action == "failed"
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
    def recoverable_runs(self) -> list[Result]: ...
    def checkpoint(self, run_id: str, source: str, cursor: Result) -> None: ...
    def checkpoints(self, run_id: str) -> dict[str, Result]: ...
    def enqueue(self, run_id: str, record: Result) -> Result: ...
    def pending(self, run_id: str, after: int) -> list[Result]: ...
    def action_checkpoint(self, run_id: str, result: Result, phase: str) -> None: ...
    def delete_task(self, task_id: str) -> None: ...
    def history(self, task_id: str, limit: int) -> list[Result]: ...
    def state(self, run_id: str) -> Result: ...
    def page(self, run_id: str, filters: Result, limit: int) -> Result: ...
    def review(
        self,
        run_id: str,
        sequence: int,
        question: str,
        value: object,
    ) -> None: ...
    def events(
        self, run_id: str, after: int = 0, *, reviewed_only: bool = False
    ) -> list[tuple[int, str]]: ...


class SQLiteResultStore:
    """Store append-only events, indexed result pages, and incremental aggregates."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = RLock()
        self.context_cache: OrderedDict[tuple[str, str], str] = OrderedDict()
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
                host TEXT, review INTEGER, failed INTEGER,
                log_folded TEXT, reviews TEXT, changed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (run_id, sequence)
            );
            CREATE INDEX IF NOT EXISTS result_page
                ON events(run_id, kind, sequence);
            CREATE INDEX IF NOT EXISTS non_result_sequence
                ON events(run_id, sequence) WHERE kind<>'result';
            CREATE INDEX IF NOT EXISTS result_host ON events(run_id,host,sequence);
            CREATE INDEX IF NOT EXISTS reviewed_changes ON events(run_id,sequence)
                WHERE kind='result' AND failed=0 AND changed=1;
            CREATE TABLE IF NOT EXISTS sources (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL, source TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence, source)
            );
            CREATE INDEX IF NOT EXISTS result_source
                ON sources(run_id, source, sequence);
            CREATE TABLE IF NOT EXISTS result_decisions (
                run_id TEXT NOT NULL, sequence INTEGER NOT NULL,
                decision TEXT NOT NULL, bucket TEXT NOT NULL, certainty TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence, decision)
            );
            CREATE INDEX IF NOT EXISTS decision_value_page
                ON result_decisions(run_id, decision, bucket, sequence);
            CREATE INDEX IF NOT EXISTS decision_certainty_page
                ON result_decisions(run_id, decision, certainty, sequence);
            CREATE TABLE IF NOT EXISTS result_contexts (
                run_id TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (run_id, key)
            );
            CREATE TABLE IF NOT EXISTS source_checkpoints (
                run_id TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (run_id, source)
            );
            CREATE TABLE IF NOT EXISTS pending_work (
                id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                payload TEXT NOT NULL, phase TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE INDEX IF NOT EXISTS pending_run ON pending_work(run_id,id);
            CREATE TABLE IF NOT EXISTS processing_times (
                run_id TEXT NOT NULL, elapsed_ms REAL NOT NULL,
                samples INTEGER NOT NULL,
                PRIMARY KEY (run_id, elapsed_ms)
            );
        """)

        self.connection.commit()

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

    def _pack(
        self, connection: sqlite3.Connection, run_id: str, result: Result
    ) -> Result:
        item = compact_result(result)
        refs = {}
        for field in ("decisionDefinitions", "questions"):
            if field not in item:
                continue
            payload = json.dumps(item.pop(field), ensure_ascii=False)
            key = sha256(payload.encode()).hexdigest()
            connection.execute(
                "INSERT OR IGNORE INTO result_contexts VALUES(?,?,?)",
                (run_id, key, payload),
            )
            refs[field] = key
        if refs:
            item["_contextRefs"] = refs
        return item

    def _expand(self, run_id: str, result: Result) -> Result:
        item = dict(result)
        for field, key in item.pop("_contextRefs", {}).items():
            cache_key = (run_id, key)
            with self.lock:
                payload = self.context_cache.get(cache_key)
                if payload is None:
                    row = self.connection.execute(
                        "SELECT payload FROM result_contexts WHERE run_id=? AND key=?",
                        (run_id, key),
                    ).fetchone()
                    if row is None:
                        raise ValueError("Stored result context is missing.")
                    payload = row[0]
                    self.context_cache[cache_key] = payload
                    if len(self.context_cache) > 128:
                        self.context_cache.popitem(last=False)
                self.context_cache.move_to_end(cache_key)
            item[field] = json.loads(payload)
        return compact_result(item)

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
            "INSERT INTO events(run_id,sequence,kind,payload,host,review,failed,log_folded) VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id,
                sequence,
                event["type"],
                json.dumps(
                    {**event, "result": self._pack(connection, run_id, result)}
                    if event["type"] == "result"
                    else event,
                    ensure_ascii=False,
                ),
                _host_id(result),
                int(needs_review(result)),
                int(failed),
                result.get("log", "").lower(),
            ),
        )
        if event["type"] != "result":
            return
        _aggregate(stats, result)
        self._index_decisions(connection, run_id, sequence, result)
        connection.execute(
            "INSERT INTO processing_times VALUES(?,?,1) "
            "ON CONFLICT(run_id,elapsed_ms) DO UPDATE SET samples=samples+1",
            (run_id, result.get("elapsedMs", 0)),
        )
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
            result = event.get("result", {})
            work_id = result.get("_workId")
            if work_id is not None:
                event = {
                    **event,
                    "result": {
                        key: value
                        for key, value in result.items()
                        if key
                        not in {
                            "_workId",
                            "_checkpoint",
                            "_recoveredResult",
                            "_actionPhase",
                        }
                    },
                }
                connection.execute(
                    "DELETE FROM pending_work WHERE run_id=? AND id=?",
                    (run_id, work_id),
                )
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

    def recoverable_runs(self) -> list[Result]:
        """Find checkpoint-enabled executions interrupted by a process restart."""
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT snapshot FROM runs WHERE state IN ('running','pausing','paused') "
                "AND json_extract(snapshot,'$.settings.recoveryVersion')=1"
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def checkpoint(self, run_id: str, source: str, cursor: Result) -> None:
        """Save an initial reader position without overtaking queued work."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO source_checkpoints VALUES(?,?,?)",
                (run_id, source, json.dumps(cursor)),
            )

    def checkpoints(self, run_id: str) -> dict[str, Result]:
        """Load one durable position per physical source."""
        with self.reader() as connection:
            return {
                row[0]: json.loads(row[1])
                for row in connection.execute(
                    "SELECT source,payload FROM source_checkpoints WHERE run_id=?",
                    (run_id,),
                )
            }

    def enqueue(self, run_id: str, record: Result) -> Result:
        """Atomically retain an input and advance its source cursor before inference."""
        item = {key: value for key, value in record.items() if key != "_checkpoint"}
        with self.transaction() as connection:
            row = connection.execute(
                "INSERT INTO pending_work(run_id,payload) VALUES(?,?)",
                (run_id, json.dumps(self._pack(connection, run_id, item))),
            )
            if cursor := record.get("_checkpoint"):
                connection.execute(
                    "INSERT OR REPLACE INTO source_checkpoints VALUES(?,?,?)",
                    (run_id, record["source"], json.dumps(cursor)),
                )
            return {**item, "_workId": row.lastrowid}

    def pending(self, run_id: str, after: int) -> list[Result]:
        """Read a bounded page of unfinished records, including uncertain Actions."""
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT id,payload,phase FROM pending_work WHERE run_id=? AND id>? ORDER BY id LIMIT 128",
                (run_id, after),
            ).fetchall()
        items = []
        for row in rows:
            item = {**self._expand(run_id, json.loads(row[1])), "_workId": row[0]}
            if row[2] != "pending":
                item.update(_recoveredResult=True, _actionPhase=row[2])
            if row[2] == "action":
                item.update(
                    review=True,
                    actionExecution={
                        "status": "failed",
                        "name": item.get("action", "Action"),
                        "elapsedMs": 0,
                        "interrupted": True,
                        "error": "Action outcome is unknown after restart; verify externally before retrying.",
                    },
                )
            items.append(item)
        return items

    def action_checkpoint(self, run_id: str, result: Result, phase: str) -> None:
        """Record Action intent before side effects, and outcome before publication."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE pending_work SET payload=?,phase=? WHERE run_id=? AND id=?",
                (
                    json.dumps(self._pack(connection, run_id, result)),
                    phase,
                    run_id,
                    result["_workId"],
                ),
            )

    def recover_interrupted(self) -> None:
        """Stop legacy interrupted runs; checkpoint-enabled runs are recovered separately."""
        while True:
            with self.reader() as connection:
                rows = connection.execute(
                    "SELECT id,snapshot FROM runs "
                    "WHERE state IN ('running','pausing','paused') "
                    "AND COALESCE(json_extract(snapshot,'$.settings.recoveryVersion'),0)<>1 LIMIT 128"
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
            for table in (
                "sources",
                "events",
                "processing_times",
                "source_checkpoints",
                "pending_work",
                "result_contexts",
                "result_decisions",
            ):
                connection.execute(
                    f"DELETE FROM {table} WHERE run_id IN "
                    "(SELECT id FROM runs WHERE task_id=?)",
                    (task_id,),
                )
            connection.execute("DELETE FROM runs WHERE task_id=?", (task_id,))
            self.context_cache.clear()

    @staticmethod
    def _index_decisions(
        connection: sqlite3.Connection, run_id: str, sequence: int, result: Result
    ) -> None:
        connection.executemany(
            "INSERT OR REPLACE INTO result_decisions VALUES(?,?,?,?,?)",
            [
                (run_id, sequence, key, bucket, status)
                for key, _, bucket, status in _decision_entries(result)
                if bucket is not None
            ],
        )

    def state(self, run_id: str) -> Result:
        """Read whole-run aggregates and exact percentiles from duration counts."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            stats = json.loads(row["summary"])
            total = stats["total"]
            values = connection.execute(
                "SELECT MIN(elapsed_ms) AS minMs,MAX(elapsed_ms) AS maxMs,"
                "(MIN(CASE WHEN n>=? THEN elapsed_ms END)+"
                " MIN(CASE WHEN n>=? THEN elapsed_ms END))/2.0 AS medianMs,"
                "MIN(CASE WHEN n>=? THEN elapsed_ms END) AS p95Ms,"
                "MIN(CASE WHEN n>=? THEN elapsed_ms END) AS p99Ms "
                "FROM (SELECT elapsed_ms,SUM(samples) OVER (ORDER BY elapsed_ms) AS n "
                "FROM processing_times WHERE run_id=?)",
                (
                    (total + 1) // 2,
                    total // 2 + 1,
                    (95 * total + 99) // 100,
                    (99 * total + 99) // 100,
                    run_id,
                ),
            ).fetchone()
            stats["processingPercentiles"] = dict(values)
            return {
                "snapshot": json.loads(row["snapshot"]),
                "summary": stats,
                "sequence": row["sequence"],
            }

    def page(self, run_id: str, filters: Result, limit: int) -> Result:
        """Read a keyset page; never use an OFFSET proportional to history length."""
        if type(limit) is not int or limit not in {10, 30, 50, 100}:
            raise ValueError("Invalid page size.")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT summary,sequence FROM runs WHERE id=?", (run_id,)
            ).fetchone()
            stats = json.loads(row["summary"]) if row is not None else empty_summary()
        table = "events e"
        where = ["e.run_id=?", "e.kind='result'"]
        params: list[object] = [run_id]
        cursor_where: list[str] = []
        cursor_params: list[object] = []
        for key, operator in (("before", "<"), ("after", ">"), ("through", "<=")):
            value = filters.get(key)
            if value is not None:
                if type(value) is not int or not 0 <= value < 2**63:
                    raise ValueError("Invalid result cursor.")
                cursor_where.append(f"e.sequence {operator} ?")
                cursor_params.append(value)
        decision = filters.get("decision", "all")
        decision_where = None
        decision_params: list[object] = []
        certainty = filters.get("certainty", "all")
        if certainty not in {"all", "certain", "uncertain", "unassessed"}:
            raise ValueError("Invalid decision certainty filter.")
        if decision != "all":
            definition = (
                stats["decisionGroups"].get(decision)
                if isinstance(decision, str)
                else None
            )
            if definition is None:
                raise ValueError("Invalid decision filter.")
            if certainty != "all" and definition["type"] != "choice":
                raise ValueError("Certainty filters require a Choice decision.")
            conditions = [
                "selected_decision.run_id=e.run_id",
                "selected_decision.sequence=e.sequence",
                "selected_decision.decision=?",
            ]
            decision_params = [decision]
            value = filters.get("category")
            if value is not None:
                if value not in definition["options"]:
                    raise ValueError("Invalid decision value filter.")
                conditions.append("selected_decision.bucket=?")
                decision_params.append(value)
            if certainty != "all":
                conditions.append("selected_decision.certainty=?")
                decision_params.append(certainty)
            decision_where = (
                "EXISTS (SELECT 1 FROM result_decisions selected_decision WHERE "
                + " AND ".join(conditions)
                + ")"
            )
        elif certainty != "all":
            raise ValueError("Select a Choice decision before filtering certainty.")
        if decision == "all" and filters.get("category") is not None:
            raise ValueError("Select a decision before filtering its value.")
        processing = filters.get("processing", "all")
        if not isinstance(processing, str) or processing not in {
            "all",
            "successful",
            "failed",
        }:
            raise ValueError("Invalid processing status filter.")
        if processing != "all":
            where.append("e.failed=?")
            params.append(int(processing == "failed"))
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
        chart = None
        if len(where) > 2:
            boundary = filters.get("chartThrough", row["sequence"] if row else 0)
            if type(boundary) is not int or not 0 <= boundary < 2**63:
                raise ValueError("Invalid chart boundary.")
            chart = self._filtered_chart(stats, where, params, boundary)
        if filters.get("onlySummary"):
            return {"chartSummary": chart}
        # Decision selection narrows result cards, not Overview aggregates.
        if decision_where is not None:
            where.append(decision_where)
            params.extend(decision_params)
        where.extend(cursor_where)
        params.extend(cursor_params)
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT e.run_id,e.sequence,e.payload,e.reviews, "
                "e.sequence-(SELECT COUNT(*) FROM events n "
                "WHERE n.run_id=e.run_id AND n.kind<>'result' "
                f"AND n.sequence<=e.sequence) AS result_number FROM {table} WHERE "
                + " AND ".join(where)
                + " ORDER BY e.sequence DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        return {
            "chartSummary": chart,
            "items": [
                {"sequence": row["sequence"], "result": self._result(row)}
                for row in rows[:limit]
            ],
            "hasNext": len(rows) > limit,
            "limit": limit,
        }

    def _filtered_chart(
        self, stats: Result, where: list[str], params: list[object], boundary: int
    ) -> Result:
        """Aggregate matching results using decision indexes, independent of paging."""
        chart = empty_summary()
        chart["decisionGroups"] = deepcopy(stats["decisionGroups"])
        for entry in chart["decisionGroups"].values():
            for counts in entry["counts"].values():
                for bucket in counts:
                    counts[bucket] = 0
        predicate = " AND ".join([*where, "e.sequence<=?"])
        with self.reader() as connection:
            connection.execute("BEGIN")
            counts = connection.execute(
                "SELECT COUNT(*) AS total,COALESCE(SUM(e.failed),0) AS failed,"
                "COALESCE(SUM(json_extract(e.payload,"
                "'$.result.providerResponse.usage.truncated')=1),0) AS truncated "
                f"FROM events e WHERE {predicate}",
                (*params, boundary),
            ).fetchone()
            chart.update(dict(counts))
            groups = connection.execute(
                "SELECT d.decision,d.bucket,d.certainty,COUNT(*) AS n "
                "FROM result_decisions d JOIN events e "
                "ON e.run_id=d.run_id AND e.sequence=d.sequence "
                f"WHERE {predicate} GROUP BY d.decision,d.bucket,d.certainty",
                (*params, boundary),
            )
            for group in groups:
                entry = chart["decisionGroups"].get(group["decision"])
                if not entry or group["bucket"] not in entry["counts"]["all"]:
                    continue
                entry["counts"]["all"][group["bucket"]] += group["n"]
                if group["certainty"] in entry["counts"]:
                    entry["counts"][group["certainty"]][group["bucket"]] += group["n"]
        return chart

    def _result(self, row: sqlite3.Row) -> Result:
        result = _assessed_result(
            self._expand(row["run_id"], json.loads(row["payload"])["result"])
        )
        result["resultNumber"] = row["result_number"]
        if row["reviews"]:
            result["reviewerDecisions"] = json.loads(row["reviews"])
        return result

    def review(
        self,
        run_id: str,
        sequence: int,
        question: str,
        value: object,
    ) -> None:
        """Save typed human corrections without changing original model answers."""
        if type(sequence) is not int:
            raise ValueError("Invalid result cursor.")
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT payload,reviews FROM events WHERE run_id=? AND sequence=? "
                "AND kind='result' AND failed=0",
                (run_id, sequence),
            ).fetchone()
            if row is None:
                raise ValueError("Result not found or classification failed.")
            result = self._expand(run_id, json.loads(row["payload"])["result"])
            definition = result.get("decisionDefinitions", {}).get(question)
            if definition is None:
                raise ValueError("Unknown decision.")
            kind = definition["type"]
            if value is not None:
                valid = (
                    isinstance(value, str) and value in definition["criteria"]
                    if kind == "choice"
                    else is_probability(value)
                    if kind == "noul"
                    else isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and 0 <= value <= len(definition["criteria"]) - 1
                )
                if not valid:
                    raise ValueError("Invalid reviewer decision value.")
            reviews = json.loads(row["reviews"] or "{}")
            if value is None:
                reviews.pop(question, None)
            else:
                reviews[question] = value
            changed = any(
                v != answer_value(result["decisions"][k]) for k, v in reviews.items()
            )
            connection.execute(
                "UPDATE events SET reviews=?,changed=? WHERE run_id=? AND sequence=?",
                (json.dumps(reviews), int(changed), run_id, sequence),
            )

    def events(
        self, run_id: str, after: int = 0, *, reviewed_only: bool = False
    ) -> list[tuple[int, str]]:
        """Read bounded events, optionally only human changes to AI categories."""
        selection = (
            " AND kind='result' AND failed=0 AND changed=1" if reviewed_only else ""
        )
        with self.reader() as connection:
            rows = connection.execute(
                "SELECT sequence,payload,reviews,kind FROM events "
                f"WHERE run_id=? AND sequence>?{selection} ORDER BY sequence LIMIT 128",
                (run_id, after),
            ).fetchall()
        output = []
        for row in rows:
            event = json.loads(row["payload"])
            if event.get("type") == "result":
                event["result"] = _assessed_result(
                    self._expand(run_id, event["result"])
                )
            if row["kind"] == "result" and row["reviews"]:
                event["result"]["reviewerDecisions"] = json.loads(row["reviews"])
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
