# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [Documentation](README.md)

A **Task** saves an execution configuration; each start creates a separate **run**.
Register Sources first, then add a Task with a name, mode, and Source assignments
(Criteria, Events/chunk, optional Action, and target Hosts for Remote File). Save does not start a run.
Main lists currently running Tasks in name order. Click a Task to display its run; a fresh page has no selection. The Tasks list
provides Run, Stop, View, Edit, History, and Delete.

| Mode | Execution |
| --- | --- |
| Batch / Manual | Read matching files from the beginning once, then finish. Run again explicitly. |
| Batch / Cron | Repeat using a five-field expression and explicit IANA timezone, e.g. `0 9 * * *`, `Asia/Seoul`. Enable schedule controls future automatic runs; manual Run remains available. |
| Realtime | Follow new lines continuously until Stop. Existing content is skipped; new/replacement files start at the beginning. Resume on restart is optional and off by default. |

Every Batch rereads files and can repeat Actions for the same events. There is no
incremental checkpoint or automatic retry. Stop cancels the current run; disabling
a cron schedule prevents future starts and does not stop its current run.
Missed schedules during server downtime are not replayed. Realtime restart starts
a new run and does not recover lines written during downtime.

Only one run of a Task can execute at a time. Overlapping manual starts are
rejected; cron occurrences are recorded as Skipped. Different Tasks can run
concurrently, each using the selected engine's per-run concurrency limit.
The engine is selected from server configuration at run start; Laya never falls
back automatically to paid Jev.

Run states are Running, Completed, Failed, Stopped, and Skipped; an unexecuted Task
is Idle. Any failed decision request or Action makes the run Failed. History lists
the latest 50 records with start/finish times, trigger, counts, and View results.
Replaying results never reruns decisions or Actions. Main follows new runs of the
selected Task unless a historical run was explicitly opened.

Edits apply to new runs; running jobs keep their settings snapshot. Source,
Criteria, and Action references cannot be removed while saved Tasks use them.
Stop a Task before deleting it. Deletion retains its run directories on disk.

## Multiple target Hosts

Each Remote File Source row selects one or more SSH Hosts. Local File has no SSH
Host selector. At run start, Source × Host expands into frozen connection snapshots.
Existing Source host bindings are migrated to Task rows automatically.

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
tasks/
  tasks.json
  <task-id>/runs/<run-id>/
    run.json
    events.ndjson
```

The data volume preserves definitions, status, settings, original logs, decisions,
and Action outcomes across server restarts. Interrupted runs become Stopped;
Batch is not resumed automatically. Opted-in Realtime Tasks start new runs at startup.
Reviewer edits remain browser-only; export JSON to retain them.

Use **one server process/instance per data directory**. This is an in-process
scheduler, without distributed workers or DAG dependencies. All run results also
remain in RAM until shutdown. No automatic disk retention/cleanup is applied;
large batches and long-running Realtime Tasks require appropriate memory and disk.

## API

All endpoints require a trusted file-access UI Origin:

| Request | Purpose |
| --- | --- |
| `POST /api/tasks` | List definitions, active/latest runs, next scheduled time |
| `PUT /api/tasks` | Save one Task (`id` for update) |
| `DELETE /api/tasks` | Delete a Task definition with `{ "id": "..." }` |
| `POST /api/tasks/<id>/run` | Start manually; HTTP 202 returns run status and jobId |
| `POST /api/tasks/<id>/stop` | Stop the active run |
| `POST /api/tasks/<id>/runs` | Latest 50 run records |
| `POST /api/jobs/<jobId>` | Inspect live or archived run |
| `POST /api/jobs/<jobId>/events` | Replay/follow NDJSON results |

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
  "enabled": false,
  "resumeOnRestart": false,
  "sources": [
    {
      "sourceId": "<remote-source-id>",
      "profile": "general",
      "chunkEvents": 1,
      "action": "",
      "hostIds": ["<first-host-id>", "<second-host-id>"]
    }
  ]
}
```
