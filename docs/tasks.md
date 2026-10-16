# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [Documentation](README.md)

A **Task** saves an execution configuration; each start creates a separate **run**.
Register Sources first, then add a Task with a name, mode, and Source assignments
(Criteria, Events/Chunk, optional Action, and source Hosts for Remote File). Save does not start a run.
Main lists all saved Tasks with running/starting Tasks first, then name order within each group. Click a Task to display its current or latest run; a fresh page has no selection. The Tasks list
provides an Enabled switch and Run, Stop, View, Edit, History, and Delete.
Task Monitor shows the Task name and availability/state on the first row, Source and distinct Source Host count
on the second, then Type / Mode / Action on the third (Action: None if unset). Long assignments
are truncated. Keep the pointer still over a card for one second, or focus it with the keyboard, to open a styled tooltip with all Source
paths, settings, and the complete Source Host list (names and SSH addresses).
Local File counts DeciFlow as one Source Host. Press Escape to dismiss the tooltip. Click to view results. Running Tasks
remain first. Execution counts, times, and schedules stay in results and Tasks.

| Mode | Execution |
| --- | --- |
| Batch / Manual | Read matching files from the beginning once, then finish. Run again explicitly. |
| Batch / Cron | Repeat using a five-field expression and explicit IANA timezone, e.g. `0 9 * * *`, `Asia/Seoul`. The Enabled switch controls whether the Task can run. |
| Realtime | Follow new lines continuously until Stop. Existing content is skipped; new/replacement files start at the beginning. Resume on restart is optional and off by default. |

Every Batch rereads files and can repeat Actions for the same events. There is no
incremental checkpoint or automatic retry. Stop cancels the current run. Disabling a Task also stops its current run and
blocks manual Run, cron, and automatic restart. Enabling does not immediately
start a run; use Run or wait for the next cron occurrence.
Missed schedules during server downtime are not replayed. Realtime restart starts
a new run and does not recover lines written during downtime.

Only one run of a Task can execute at a time. Overlapping manual starts are
rejected; cron occurrences are recorded as Skipped. Different Tasks can run
concurrently, each using the selected engine's per-run concurrency limit.
The engine is selected from server configuration at run start; Laya never falls
back automatically to paid Jev.

Run states are Running, Completed, Failed, Stopped, and Skipped; an unexecuted Task
is Idle. Any failed decision request or Action makes the run Failed. History lists
the latest 50 records with start/finish times, trigger, counts, and View Results.
Replaying results never reruns decisions or Actions. Main follows new runs of the
selected Task unless a historical run was explicitly opened.

Edits apply to new runs; running jobs keep their settings snapshot. Source,
Criteria, and Action references cannot be removed while saved Tasks use them.
Stop a Task before deleting it. Deletion permanently removes its history, results, and reviews.

## Default Task

DeciFlow creates **DeciFlow Server Log** with its **Sample DeciFlow Server Log** Local File Source first in the
Sources registry. It monitors
`DECIFLOW_LOG_DIR/server.log` / `DECIFLOW_LOG_DIR/access.log`, General system criteria, one event per chunk, and
no Action. It uses Realtime mode with the Task disabled; enable it, then use Run to start
it manually. Automatic restart is off. File logging must be enabled.

The server identifies the default Task by UUID and restores it at startup, including after a reset. If its name conflicts with another Task, a numeric suffix is added.
Existing Task settings are preserved; deleted nondefault Tasks and history are not
restored. Deleting only the default Task through the UI keeps it removed until
next startup. Deleting application files while the server runs is unsupported;
use Reset DeciFlow to stop execution and close the database first.


Action selections store `actionId`; SSH Hosts store `keyId`. Names are display metadata, so renaming does not change saved assignments.

## Multiple Source Hosts

Each Remote File Source row selects one or more SSH Hosts. Local File has no SSH
Host selector. At run start, Source × Host expands into frozen connection snapshots.

Collection runs independently per host. Prepared records are submitted in rotating
host order, skipping empty slots without additional remote availability probes.
Each host has one pending merged chunk; its Sources have bounded pending reads.
A host with many Sources gets the same turns as a host with one Source. Empty or
slow hosts stay eligible without blocking others; new ready chunks get their turn.
The engine concurrency limit is shared across the whole run, not multiplied per host.

Chunks never mix hosts/files. Results appear in completion order, including
host identity and per-Source/Host chunkSequence. Source and Host filters combine
without changing aggregate metrics or repeating Actions. Collection status is
reported per host separately from classification counts.

An SSH Source read failure becomes a `sourceFailure` result with host identity; no engine
or Action is called for it. Other hosts/Sources continue. Failed collection records
are included in failure counts. Local file read/UTF-8 errors stop the run. Batch ends Failed if any read,
decision, or Action failed. Realtime continues on healthy hosts until stopped; failed readers are not
automatically retried. A host with no readable Batch matches is recorded as failed;
a Realtime pattern with no current files keeps watching for new files.

## Storage and operation

Under `DECIFLOW_DATA_DIR` (default `/var/lib/deciflow-data`):

```text
deciflow.sqlite3
```

The data volume preserves definitions, status, settings, original logs, decisions,
and Action outcomes across server restarts. Interrupted runs become Stopped;
Batch is not resumed automatically. Enabled, opted-in Realtime Tasks start new runs at startup.
Reviewer corrections are stored with the run in SQLite and included in JSON export.

Use **one server process/instance per data directory**. This is an in-process
scheduler, without distributed workers or DAG dependencies. SQLite stores results;
the server retains bounded event caches and aggregates, and the browser loads only
the current page. No automatic disk retention/cleanup is applied. See
[Result storage](result-storage.md) for configuration storage, pagination, backups, and limits.

## API

All endpoints require a trusted file-access UI Origin:

| Request | Purpose |
| --- | --- |
| `POST /api/tasks` | List definitions, active/latest runs, next scheduled time |
| `PUT /api/tasks` | Save one Task (`id` for update) |
| `DELETE /api/tasks` | Permanently delete the Task and its history/results/reviews with `{ "id": "..." }` |
| `POST /api/tasks/<id>/run` | Start manually; HTTP 202 returns run status and jobId |
| `POST /api/tasks/<id>/stop` | Stop the active run |
| `POST /api/tasks/<id>/enabled` | Set `{ "enabled": true/false }`; false also stops the active run |
| `POST /api/tasks/<id>/runs` | Latest 50 run records |
| `POST /api/jobs/<jobId>` | Inspect live or archived run |
| `POST /api/jobs/<jobId>/events` | Replay/follow NDJSON results |
| `POST /api/jobs/<jobId>/results` | Query a filtered result page and run aggregates |
| `POST /api/jobs/<jobId>/review` | Save `{ "sequence": ..., "category": "..." }` for a result |
| `POST /api/jobs/<jobId>/export` | Export All JSON for the selected run |
| `POST /api/jobs/<jobId>/export-reviewed` | Export Reviewed JSON, only changed reviewer categories |

Save fields: `name`, `mode` (`batch`/`realtime`), `sources` (each has `sourceId`,
`profile`, `chunkEvents`, optional `action`, and `hostIds` for Remote File), `cron` (empty for manual), `timezone`,
`enabled`, `resumeOnRestart`. IDs are server-generated. A failed preparation is
also recorded as a Failed run, including its error.

### Remote File Task example

Send this body to `PUT /api/tasks`, replacing the IDs with registered Source and
SSH Host IDs. Both hosts use the Source's common path; Action is optional. Start
with `POST /api/tasks/<id>/run` using the returned Task ID.

```json
{
  "name": "System logs across hosts",
  "mode": "batch",
  "cron": "",
  "timezone": "Asia/Seoul",
  "enabled": true,
  "resumeOnRestart": false,
  "sources": [
    {
      "sourceId": "<remote-source-id>",
      "profile": "general",
      "chunkEvents": 1,
      "actionId": "",
      "hostIds": ["<first-host-id>", "<second-host-id>"]
    }
  ]
}
```

Confirming Task deletion permanently removes its definition, all run history, results, and reviewer corrections. Original Source files are kept. SQLite reuses freed space; the DB file may not shrink immediately.

Once visible, the tooltip stays open while the pointer is over the Task card or
tooltip. Move into the tooltip to select/copy text; leaving both closes it.
