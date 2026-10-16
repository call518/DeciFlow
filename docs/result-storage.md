# Result Storage

[한국어](result-storage.ko.md) | [Documentation](README.md)

Task results, original inputs, Action outcomes, reviewer corrections, and run
aggregates are stored in `DECIFLOW_DATA_DIR/results.sqlite3`. Definitions remain
JSON files; `settings.json` stores application display settings. No separate DB
server or new environment setting is required.

## Bounded Result Loading

- Settings → Results sets Results per Page: **50** by default, with 10/30/50/100 options.
- The server applies filters and cursor pagination before returning results. The
  browser retains only the current page; previous pages are fetched when needed.
- Latest-page polling requests results after the last received cursor. Polling is
  suspended outside Main and in hidden tabs. Tasks continue independently.
- Older pages and paused lists remain stable while new results arrive. Latest
  Results returns to the newest page. Metrics and charts cover the entire run,
  regardless of the page or filters.
- Writes update aggregates incrementally. Each live job retains at most 128 recent
  events, and completed job objects are evicted beyond 32 cached jobs. Durable Task
  history remains available. Throughput uses bounded 100 ms buckets over 5 seconds.
- **Export All JSON** streams the entire run up to the starting cursor, including
  reviewer corrections, without loading all results into browser/server memory.
- **Export Reviewed JSON** queries only nonempty reviewer categories that differ
  from the original AI category in the selected run. It uses a partial index and
  bounded batches, retains complete original results plus `reviewerCategory`,
  and does not duplicate data in a separate review store. Display filters do not
  affect either export. Cleared and unchanged reviews are excluded.

Memory no longer grows with accumulated result count. Active hosts/files, individual
record size, configured parallelism, and SQLite/OS caches still consume memory.
Indexed page retrieval avoids scanning all earlier results; arbitrary substring
search may scan many rows. Search input is debounced. Disk use continues to grow:
there is no automatic retention policy. This is not a guarantee of constant CPU
under every query or input workload.

## Existing History and Backups

Existing `tasks/<task-id>/runs/<run-id>/events.ndjson` files are imported once when
the run is opened. Import streams records in one transaction and preserves the
original file. A failed import rolls back and can be retried. Large first imports
can take time and temporarily delay other writes. New runs use SQLite directly.

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
interface and extending the factory, with migration and concurrency tests.
Only SQLite is implemented today; no PostgreSQL/MySQL connection setting is exposed.

A local synthetic check compared 5,000 and 50,000 records: median 30-row retrieval
was about 0.37 ms in both cases. This measures indexed retrieval on that machine,
not end-to-end inference, text searches, or a production performance guarantee.

Confirming Task deletion permanently removes its definition, all run history, results, reviewer corrections, and Task directory. Original Source files are kept. Existing orphan Task directories are not automatically removed. SQLite reuses freed space; the DB file may not shrink immediately.
