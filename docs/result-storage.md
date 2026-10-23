# Result Storage

[한국어](result-storage.ko.md) | [Documentation](README.md)

Task results, original inputs, Action outcomes, reviewer corrections, and run
aggregates share `DECIFLOW_DATA_DIR/deciflow.sqlite3` with Source, Criteria, Task,
Action, SSH Host, SSH Key metadata, and application settings. Configuration collections store one
record per item, keyed by its internal identifier; nested fields remain JSON payloads
inside the DB. No separate DB server or new environment setting is required.

Decision values/buckets and Choice certainty are indexed in `result_decisions`
when results are stored. Filters cover the whole run
without re-evaluating all results on every query.

## Bounded Result Loading

- Settings → Configurations sets Results per Page: **30** by default, with 10/30/50/100 options.
- The server applies filters and cursor pagination before returning results. The
  browser retains only the current page; previous pages are fetched when needed.
- Latest-page polling requests results after the last received cursor. Polling is
  suspended outside Main and in hidden tabs. Tasks continue independently.
- Older pages and paused lists remain stable while new results arrive. Latest
  Results returns to the newest page. Metrics and charts cover the entire run,
  regardless of the page or filters.
- Writes update aggregates incrementally. Each live job retains at most 128 recent
  events, and completed job objects are evicted beyond 32 cached jobs. Durable Task
  history remains available. Throughput uses whole-run success counts and elapsed
  time. Exact Median/P95/P99 use incrementally maintained duration counts in
  `processing_times`, not full result scans on every poll. Each distinct duration
  occupies one row per run. Task
  deletion removes the corresponding histogram rows.
- **Export All JSON** streams the entire run up to the starting cursor, including
  reviewer corrections, without loading all results into browser/server memory.
- **Export Reviewed JSON** queries successful results with any human correction
  different from its AI value. It uses a partial index and bounded batches, keeps
  complete original results with `reviewerDecisions`, and does not duplicate results in a separate store.
  Display filters do not affect exports; cleared and unchanged reviews are excluded.


Memory no longer grows with accumulated result count. Active hosts/files, individual
record size, configured parallelism, and SQLite/OS caches still consume memory.
Indexed page retrieval avoids scanning all earlier results; arbitrary substring
search may scan many rows. Search input is debounced. Disk use continues to grow:
there is no automatic retention policy. This is not a guarantee of constant CPU
under every query or input workload.

## Execution Recovery

`pending_work` retains bounded unfinished inputs; `source_checkpoints` stores one
read cursor per physical source. Queue insertion and cursor advancement share a
transaction, as do result insertion and queue removal. Action intent/outcome are
journaled separately to avoid automatically repeating uncertain external effects.
Frozen Criteria/Action definitions are part of the run snapshot.
See [Tasks](tasks.md#recovery-after-a-server-restart) for restart states and file validation.

## Initialization and Backups

On a fresh data directory, bundled Sources, Criteria, the Elasticsearch sample Action and disabled default
Task are created in SQLite. Empty saved lists remain empty. No configuration JSON,
run.json, or events.ndjson is generated.
Bundled Criteria JSON files under `deciflow/profiles/` remain read-only seed definitions.

Use one DeciFlow process per data directory on a local filesystem. SQLite uses WAL,
FULL synchronous commits, and a 2 MiB connection cache. Do not place the active DB
on a shared network filesystem. For a consistent backup, stop DeciFlow and back up
the whole data directory, or use SQLite's backup API. Copying just the live DB file
can omit records still in its WAL. Protect backups: inputs and SSH private keys
are sensitive.

## Future Database Adapters

Application code calls the `ResultRepository` interface. `open_result_store()`
selects the implementation; SQL and transactions are isolated in
`SQLiteResultStore`. PostgreSQL or MySQL can be introduced by implementing this
interface and extending the factory, with migration and concurrency tests. Configuration SQL is isolated in `config_store.py` and must also receive a matching adapter.
Only SQLite is implemented today; no PostgreSQL/MySQL connection setting is exposed.

A local synthetic check compared 5,000 and 50,000 records: median 30-row retrieval
was about 0.37 ms in both cases. This measures indexed retrieval on that machine,
not end-to-end inference, text searches, or a production performance guarantee.

Confirming Task deletion permanently removes its definition, all run history, results, and reviewer corrections. Original Source files are kept. SQLite reuses freed space; the DB file may not shrink immediately.

For a complete reset, use **Settings → Configurations → Reset DeciFlow**.
It stops execution, closes SQLite, removes all application data, and restarts the
server only after confirmation. See [reset details](configuration.md#reset-deciflow).


## Compact Payload Storage

New results and recovery queue items store input text once. SQLite shares repeated
Criteria and diagnostic question definitions in `result_contexts` per run, keyed
by content hash. Indexed pages, review validation, replay, and exports restore
those definitions transparently; the cache is bounded. Standalone Action/export
results retain their definitions so they do not depend on a private SQLite DB.
`log_folded` remains a deliberate case-insensitive search copy. Task deletion also
removes its shared contexts. Reads do not rewrite stored payloads or ES documents.
