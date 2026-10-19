# Python Actions

[English](actions.md) | [한국어](actions.ko.md) | [Documentation](README.md) | [README](../README.md)

## Default Sample Action

On first initialization or after Reset DeciFlow, **Sample Elasticsearch** is registered
with Python **3.12**, module **elasticsearch**, and code that writes each result to
`http://host.docker.internal:9200`, index `deciflow`, adding a UTC `@timestamp`.
Startup automatically creates its script and venv and installs Python and its module
before Tasks start. Initial setup requires package download access and can delay startup.
If preparation fails, Actions shows **Not ready** with the error; use
**Save & Prepare Environments** to retry, or restart DeciFlow. The sample code is not
executed during setup. Saved edits and deletions are preserved on later starts.
In Compose, `host.docker.internal` resolves to the Docker host gateway.
For direct Python execution, use a hostname reachable from the DeciFlow host.

## Managing Actions

Add/Edit hides the list and shows only the form. Saving or Cancel Edit returns to the list.

**View** shows names, Python Version, modules, code, and paths in compact label/value fields directly below the selected row. Click View again to collapse it without changing drafts or environments. Python Code uses syntax colors for keywords, strings, comments, and other tokens in both View and Add/Edit. Coloring preserves source text and save/execution behavior, uses no external CDN, and does not provide syntax validation or autocomplete. Edit/Add closes View.

Open **Actions** in the left sidebar to create, edit, or remove handlers. Click
**Add Action**, enter a name, Python Version (e.g. `3.12`), modules, and Python
code directly in the editor, then **Save & Prepare Environments**. No script path
or separate file upload is needed. The list shows one row per Action with its
name, Python Version, modules, environment Status, and **View**/**Edit**/**Reset venv**/**Delete** buttons.
**Search by Name** filters names by a case-insensitive partial match.
**Edit** opens one handler;
**Cancel Edit** discards its draft. Removal takes effect when you save. Return to
**Tasks** to assign an Action or **None** to each log file or pattern and start
Batch/Realtime. Analysis continues when changing pages. Re-entering Actions from
the sidebar returns to the list and discards unsaved drafts. Assignments are saved per Task.

Modules accept one package per line, with optional extras or version constraints
(e.g. `httpx==0.28.1`, `requests>=2.32,<3`). URLs, local paths, index options,
and environment markers are not supported. Leave modules empty for code using
only the standard library. Each handler reads the decision with
`result = json.load(sys.stdin)`; the initial editor includes a runnable template.

**Status** shows environment readiness: Ready when the script, Python interpreter, dependency lock and installation marker exist,
Preparing... during preparation, or Not ready for missing/incomplete environments.
Actions using external Python show External. Saving/resetting displays
Preparing...; pending statuses refresh automatically until preparation ends.
The editor also displays preparation status.

DeciFlow needs `uv` on its PATH and writable persistent storage. It uses `uv venv --seed`,
`uv add`, and `uv sync` to prepare an independent environment. Python/package
installation may require network access. Preparation allows five minutes per uv
command; failure preserves the previous registrations. Existing file-based
registrations remain executable; Actions imports their code into the editor,
and saving converts them to UI-managed code and environments.

Actions use `actions/` under the shared `DECIFLOW_DATA_DIR` root. The default is
`/var/lib/deciflow-data/actions` for both Python and Docker. Direct host startup needs write
permission; set the shared root to `./data` if needed. For Docker, keep the shared data
root and volume destination identical. Registrations are stored in
`DECIFLOW_DATA_DIR/deciflow.sqlite3`; code, projects, lockfiles and venvs remain in `actions/`. New Task Source rows default to
**None**. Action assignments, Criteria, and chunk sizes are saved in the Task on
the server and survive page reloads. Each run keeps its original settings snapshot;
edits affect new runs. Changing the data directory does not migrate existing data
automatically.

The shared SQLite database stores current Action configurations.
Each UI-managed Action uses `<Action UUID>/`. Older versioned or name-prefixed
layouts are not migrated. Edit can change Name when it remains unique
(case-insensitive). Task assignments, execution selection and deletion checks use
`actionId`, never the display name. Renaming keeps the UUID, original directory,
script and environment unchanged; running jobs retain their original snapshots. Code and the environment live directly in that directory:

```text
<Action UUID>/
├── action.py
├── .venv/
├── pyproject.toml
├── uv.lock
└── .ready
```

`action.py` is the current script; `.venv` is its Python environment.
`pyproject.toml` and `uv.lock` keep the environment settings and resolved packages.
`.ready` marks completed preparation. Code-only edits reuse the environment;
Python/module changes rebuild `.venv` at the same path. Unchanged ready settings
are reused.

Saving temporarily backs up files it will change and removes the backup after
success. Preparation or saving failure restores those files and keeps the saved
configuration. Backups are temporary working files, not stored versions.

An Action cannot be changed, reset, or deleted while analysis uses it. Stop that
analysis first. Saving unchanged Actions and editing other Actions remain allowed.
New runs cannot use an Action while its configuration is being changed.
Saving is serialized within one DeciFlow process; multiple writers sharing a
volume are not supported. Deletion is also blocked by saved Task references;
change those Tasks to another Action or None before deleting the Action.

**Reset venv** deletes the saved Action's current `.venv` and rebuilds it from its
Python/module settings and `uv.lock`, including pip. Code, registrations, and lockfiles
stay intact. It uses saved settings, not editor drafts. A failed reset leaves the
environment unready; retry with Reset venv. Actions using external Python
cannot be reset.

**Delete → Save & Prepare Environments** removes the Action's data folder, including
code, the environment, lockfiles, and data. External scripts/Python
outside DeciFlow-managed storage are not deleted. Changes/reset/deletion are rejected while
analysis uses the Action; click **Stop** first. New runs using it cannot start during
maintenance.

To restore a deleted venv, save Actions again. Keep the project and `uv.lock` to
restore resolved package versions; deleting them requires resolving again. Log
processing never installs packages. Missing or incomplete environments are shown
as Action failures. Overlapping patterns must agree on profile, chunk size, and
Action.

Each successful decision (including uncertain decisions) is passed as one JSON
object on stdin to a new Python process. The payload is the existing result,
including log text, source, line range, profile, probabilities, and review flags,
plus `schemaVersion: 2`, `eventId`, UTC `decidedAt`, and `engine`. The event ID
identifies this execution; rerunning a batch creates new IDs. Filter categories
or review flags in your code. Both Laya and Jev use the same contract. Provider
failures, Source read failures, and unassigned sources do not trigger Actions.
Remote input also includes `hostId`, `hostName`, `hostAddress`, `hostPort`, and
`chunkSequence`; these identify the source host without changing the log text.

All profiles expose validated answers under `decisions[decision_id]` and frozen
configuration under `decisionDefinitions`. JSONL adds canonical `log`, remaining `inputRecord` metadata,
`inputContentInLog: true`, and `recordNumber`; redundant valid `rawInput` is omitted. Use the source location/record number for business deduplication
when appropriate; eventId changes on reruns. Actions run before later human
corrections and do not automatically rerun when a reviewer edits a result.

You can copy the [Python handler example](../examples/action_print.py) into the editor.

Exit code 0 means success. DeciFlow displays `actionExecution` with the name,
status, exit code, and duration; failed stderr is retained up to 4 KiB. Stdout is
discarded, so scripts must write their own files or call their integrations.
Actions execute sequentially per run, with a 30-second timeout and no automatic
retry. A slow Action delays result delivery and reduces throughput; failure is
recorded without stopping subsequent decisions. **Stop** cancels the current
Action process; browser disconnects leave UI jobs running. Cancellation cannot
undo external effects. Scripts must manage
any subprocesses they spawn. Task run history stores Action outcomes on disk and
exposes them in the UI and JSON export. This is execution history, without a
durable Action queue or automatic retries.

Only register trusted scripts: Actions run with DeciFlow's OS permissions,
environment, and working directory, without a sandbox. Registration uses the same
local/trusted-origin restrictions as file access; trusted origins therefore grant
code-execution capability. Keep credentials in environment variables or a secret
store, and avoid printing them to stderr.

Docker Compose already mounts the `deciflow-data` volume at `DECIFLOW_DATA_DIR`
(default `/var/lib/deciflow-data`), shared with Criteria and outside read-only `/app`.
No separate host data directory is needed. If changing the data path, migrate
existing Actions and prepare their environments at the new path, then apply the
Compose configuration with `docker compose up -d ui`. Rebuilding the UI image is
unnecessary for data-path changes. See [Docker deployment](../README.md#deciflow-docker).

Syntax colors use vendored PrismJS 1.30.0 Core + Python (about 9.4 KiB, MIT). No external CDN is contacted at runtime; the versioned asset is browser-cacheable. Sources, license, and SHA-256 checksums are recorded in `public/vendor/prism/`; update these records and rerun UI checks when upgrading. Existing editor input and scrolling are preserved.


Use `decisions` and `decisionAssessments` for per-decision processing and
`anyUncertain` for record-level Choice uncertainty. Changing `defaultDecision`
only changes display and never reruns Actions.

## Compact Result JSON Contract (Version 2)

Input text lives once in `log`; other JSONL fields remain in `inputRecord`.
With `inputContentInLog: true`, the field named by `contentField` lives in `log`.
Custom Actions reading `inputRecord[contentField]` must read `log` instead.
Reconstruct the parsed input object as follows; original whitespace and escape
formatting are not reproduced:

```python
record = dict(result.get("inputRecord", {}))
if result.get("inputContentInLog"):
    record[result["contentField"]] = result["log"]
```

Malformed or differing original `rawInput` and failure diagnostics are retained.
Successful results omit repeated `questions`; definitions remain in
`decisionDefinitions`. With `providerResponse.answersInDecisions: true`, identical
answers live once in `decisions`. Usage, model, routing, and other provider fields
remain. Internal work IDs and checkpoints are excluded from Action stdin.
User scripts and existing ES documents are not automatically rewritten. Actions
that forward the whole result, including the Elasticsearch sample, forward this
new contract. It applies to Laya/Jev and TEXT/JSONL alike.
