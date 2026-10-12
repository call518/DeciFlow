# Python Actions

[English](actions.md) | [한국어](actions.ko.md) | [README](../README.md)

Add/Edit hides the list and shows only the form. Saving or Cancel edit returns to the list.

**View** shows the current name, Python version, modules, code, and stored paths
read-only. **Cancel** dismisses it without changing editor drafts or preparing
environments. List controls appear as **View / Edit / Reset venv / Delete**. Edit/Add closes View. Viewing
hides the editor and disables saving; Cancel restores any existing draft.

Open **Actions** in the left sidebar to create, edit, or remove handlers. Click
**Add action**, enter a name, Python version (e.g. `3.12`), modules, and Python
code directly in the editor, then **Save & prepare environments**. No script path
or separate file upload is needed. The list shows one row per Action with its
name, Python version, modules, environment Status, and **View**/**Edit**/**Reset venv**/**Delete** buttons.
**Search by Name** filters names by a case-insensitive partial match.
**Edit** opens one handler;
**Cancel edit** discards its draft. Removal takes effect when you save. Return to
**Main** to assign an Action or **None** to each log file or pattern and start
Batch/Realtime. Switching views preserves ongoing analysis and editor drafts.
Paste mode does not run Actions.

Modules accept one package per line, with optional extras or version constraints
(e.g. `httpx==0.28.1`, `requests>=2.32,<3`). URLs, local paths, index options,
and environment markers are not supported. Leave modules empty for code using
only the standard library. Each handler reads the decision with
`result = json.load(sys.stdin)`; the initial editor includes a runnable template.

**Status** shows environment readiness: Ready after Python/dependency installation,
Preparing... during preparation, or Not ready for missing/incomplete environments.
Legacy Actions using external Python show External. Saving/resetting displays
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
root and volume destination identical. Registrations, code snapshots,
projects, lockfiles, and venvs are stored together. New analysis sources default to **None**, including sources with older stored
assignments. Reconnecting to a running job displays its original Action settings
and continues that same job. Restored completed jobs default to **None** for a new run. Action selections persist only during the
current page session; users must explicitly select them again after reload.
Criteria and chunk sizes remain in browser local storage. Changing this directory does not migrate
existing data automatically.

`actions.json` remains at the storage root. Each Action groups its code under
`<UUID>/scripts/` and environments under `<UUID>/environments/<revision>/`.
Saving older registrations prepares this layout using the existing lockfile;
old directories remain available for running processes. Venvs are rebuilt rather
than moved because installed entry points contain absolute paths.

Unchanged ready environments are reused. Python/module changes create a new
revision; code edits save a new script snapshot and reuse the environment. Existing
runs keep their original scripts and environments; saved changes apply to the next
run. Old code and environment revisions are retained: remove unused revisions
only after their runs have stopped. After renaming/removing an Action, check its
source assignments.

**Reset venv** deletes the saved Action's current `.venv` and rebuilds it from its
Python/module settings and `uv.lock`, including pip. Code, registrations, and lockfiles
stay intact. It uses saved settings, not editor drafts. A failed reset leaves the
environment unready; retry with Reset venv. Legacy Actions using external Python
cannot be reset.

**Delete → Save & prepare environments** removes the Action's UUID folder, including
code snapshots, all environment revisions, lockfiles, and data. External scripts/Python
outside DeciFlow-managed storage are not deleted. Reset/deletion is rejected while
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
plus `schemaVersion: 1`, `eventId`, UTC `decidedAt`, and `engine`. The event ID
identifies this execution; rerunning a batch creates new IDs. Filter categories
or review flags in your code. Both Laya and Jev use the same contract. Provider
failures and unassigned sources do not trigger Actions.

You can copy the [Python handler example](../examples/action_print.py) into the editor.

Exit code 0 means success. DeciFlow displays `actionExecution` with the name,
status, exit code, and duration; failed stderr is retained up to 4 KiB. Stdout is
discarded, so scripts must write their own files or call their integrations.
Actions execute sequentially per run, with a 30-second timeout and no automatic
retry. A slow Action delays result delivery and reduces throughput; failure is
recorded without stopping subsequent decisions. **Stop** cancels the current
Action process; browser disconnects leave UI jobs running. Cancellation cannot
undo external effects. Scripts must manage
any subprocesses they spawn. Execution history is retained in the UI and JSON
export, not a durable job queue.

Only register trusted scripts: Actions run with DeciFlow's OS permissions,
environment, and working directory, without a sandbox. Registration uses the same
local/trusted-origin restrictions as file access; trusted origins therefore grant
code-execution capability. Keep credentials in environment variables or a secret
store, and avoid printing them to stderr.

For Docker, use the following options together (also supported by the launch script):

```bash
--env DECIFLOW_DATA_DIR=/var/lib/deciflow-data \
--mount type=volume,src=deciflow-data,dst=/var/lib/deciflow-data
```

The volume is outside read-only `/app`; no separate host data directory is needed.
When switching from the old volume/mount, rebuild the Docker image and recreate the
container. Existing Actions require data migration and environment preparation at
the new path.
