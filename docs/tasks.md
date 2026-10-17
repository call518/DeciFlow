# Tasks

[English](tasks.md) | [한국어](tasks.ko.md) | [Documentation](README.md)

A **Task** saves an execution configuration; each start creates a separate **run**.
Register Sources first, then add a Task with a name, mode, and Source assignments
(Criteria, Events/Chunk, optional Action, and source Hosts for Remote File). Save does not start a run.

A Source assignment can be set to **None** to temporarily release its dependency. Tasks with no Sources can be saved but cannot run. Stop a Starting, Running, Pausing, or Paused Task before editing it.

Main lists enabled Tasks with running/starting Tasks first, then name order within each group. Click a Task to display its current or latest run; a fresh page has no selection. Disabled Tasks remain available in the Tasks management list. The Tasks list
provides an Enabled switch and Run, Stop, Pause / Resume, View, Edit, History, and Delete.
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
| Realtime | Follow new lines continuously until Stop. Existing content is skipped; new/replacement files start at the beginning. Active executions recover after restart; an optional startup setting starts a new run when none can be recovered. |

Every new Batch Run rereads files and can repeat Actions for the same events.
An interrupted active run instead recovers its saved position under the same ID. Stop cancels the current run. Disabling a Task also stops its current run and
blocks manual Run, cron, and automatic restart. Enabling does not immediately
start a run; use Run or wait for the next cron occurrence.
Missed schedules during server downtime are not replayed. Recoverable Realtime
executions continue from saved positions, including downtime lines still present
in the original files. The optional startup setting starts a new run only when
there is no recoverable execution; that new run skips existing file content.

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

View and History expand directly below the selected Task. Opening either for another
Task closes the previous detail; clicking the same button again collapses it.
List refreshes preserve the expanded detail in place.

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
and Action outcomes across server restarts. Checkpoint-enabled Running executions
resume automatically; Paused/Pausing executions recover as Paused under the same
run ID. Older executions without checkpoints become Stopped.
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

At startup, **VOC Asia Culture Center Consulting QnA** is provided as a disabled manual
Batch Task using the VOC Asia Culture Center Consulting QnA Source, Korean Criteria, one event per chunk,
and Action None. Enable it, then Run to analyze the file. Existing Task settings are preserved.

**System Messages** is also provided at startup as a disabled Realtime Task with
General system, one event per chunk, and Action None. It reuses **System messages**,
whose initial local path is `/host-logs/var/log/messages`. Saved Source edits,
including Remote File type, are preserved. For SSH, use the path on the remote
host (usually `/var/log/messages`) and select Source Hosts in the Task.
The untouched erroneous System Message Source is removed and its Task references
are reassigned to System messages; customized duplicate Sources are preserved.

Clicking Run in Tasks automatically opens Main to show the selected Task results.

## Task History Versus Current Run

A Task is a saved definition; each Run creates an independent execution ID and
starts its counters at zero. Main displays one selected run, not a lifetime Task
total. Stop ends that run; Run creates a new one rather than resuming a checkpoint.
Previous results and reviews remain under Tasks → History → View Results. Batch
rereads from the beginning, while a new Realtime run watches new input. For example,
stopping a run at 100 results and starting another leaves the old 100 in History
and shows zero for the new run until it completes records. This does not delete
the old results. There is no cumulative cross-run dashboard. Pause/Resume and
server restart recovery continue the existing run; Stop followed by Run does not. History lists the latest 50 runs; this display
limit is not a retention limit.


## Pause And Resume

One button in Tasks switches between **Pause / Resume** with the execution state. Click **Pause** to stop starting new records. **Pausing** means previously
admitted decisions and Actions are still finishing; **Paused** means they have been
stored. **Resume** continues the same run, preserving results, reviews, counters,
and the open source position. Stop also works while paused; a later Run starts a
new execution. Paused runs still prevent overlapping manual or cron executions.
Other Tasks continue normally.

Both Batch and Realtime support Pause. Source readers can retain a bounded number
of prefetched records; no growing full-file queue is created. Realtime data written
while paused is read after Resume if the original file is still available. Rotation,
truncation, removal, or SSH interruption can cause gaps under existing source rules.
Pause survives a DeciFlow server restart for checkpoint-enabled executions:
they recover as Paused and wait for Resume.

Total elapsed time and whole-run Throughput include paused intervals and server downtime. Processing
Time excludes waiting at the pause gate. **Pause Display Updates** only freezes the
result list; it does not pause execution.


## Recovery After A Server Restart

New file-based Task executions durably queue each input together with its source
cursor before inference. Saving a result also removes its queued input in the same
SQLite transaction. Unfinished inputs are replayed before reading beyond the saved
cursor; completed results, reviews, metrics, frozen Criteria/Actions, and run IDs
remain intact. An unfinished inference may be requested again, including a paid Jev
request; a stored result is not classified again. The configured engine and model
must match the original run; recovery never switches to a different provider.

This applies to manual/cron Batch and local/SSH Realtime. Realtime readers save their
initial positions even before a first event arrives. Local files are checked using
file identity, size, and a prefix fingerprint; SSH files use size and a prefix
fingerprint because SFTP does not expose a portable inode. These are change checks,
not a guarantee of detecting every in-place rewrite. Missing, replaced, or truncated
inputs can prevent recovery and are reported rather than silently restarted from
the beginning. Removed downtime files cannot be reconstructed.

Before an external Action starts, its intent and event ID are committed. Its outcome
is committed after it returns. If restart leaves an uncertain Action outcome, it is
not automatically repeated: the decision is retained for review with a failed Action
and an explanation. Verify the external destination using its event ID. This prevents
automatic duplicate side effects but is not an exactly-once delivery guarantee.
An Action whose successful outcome was recorded is replayed without executing again.

User Stop, Task disabling, and Reset remain explicit termination operations. One
DeciFlow process per data directory is required. Recovery adds tables to the existing
SQLite DB without deleting history. Runs created before this feature have no durable
input cursors and cannot be upgraded safely: the first deployment restart ends those
runs; subsequent new Runs support recovery. Keep the data volume and original files.

Set Criteria to **None** to release its dependency temporarily. Assign Criteria to every Source before running the Task.

The government sample also provides a Source, Korean Criteria, and a disabled
Batch Task at startup. See [VOC Central Gov Consulting QnA](voc.md#government-qna-sample).
