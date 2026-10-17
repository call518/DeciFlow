# Configuration

[English](configuration.md) | [한국어](configuration.ko.md) | [Documentation](README.md) | [README](../README.md)

DeciFlow settings live in `.env`; process environment variables take precedence.
Laya server settings are managed on the Laya host; Compose shares `LAYA_API_KEY`
with DeciFlow. `COMPOSE_PROFILES` selects `cpu` or `cuda`; empty starts only the UI.

| Variable | Code default (when unset) | Purpose |
| --- | --- | --- |
| `COMPOSE_PROFILES` | Unset (UI only) | Compose only: set cpu or cuda, exactly one; .env.example selects cpu |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Shared Sources/Tasks/history/Actions/Criteria/SSH Key/host storage root; must be writable |
| `DECIFLOW_CSRF_TRUSTED_ORIGINS` | Empty | Comma-separated trusted UI origins, including optional https://*.ngrok-free.app; origin check only, not authentication |
| `DECIFLOW_LOG_DIR` | `/var/log/deciflow` | Server/access logs; empty disables file logging. Compose persists logs in deciflow-logs |
| `PORT` | `4000` | DeciFlow web port |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | Full Laya URL, including any proxy prefix. Compose CPU/CUDA both use `http://laya:8000/v1/systemone`; native execution uses loopback |
| `LAYA_API_KEY` | `changeme` | Key matching the Laya server |
| `LAYA_MODEL` | `multilingual` | Built-in or registered custom checkpoint name; server must provide it |
| `LAYA_MAX_TOKENS` | Blank | Sent as `max_len`; blank keeps built-in defaults; required for custom models |
| `LAYA_HEAD_TOKENS` | `256` | Sent as `head_max_len`; question/option budget, below the total window |
| `LAYA_CONCURRENCY` | `4` | Maximum simultaneous Laya requests per run; positive integer |
| `JEV_API_KEY` | Unset | Jev API key |
| `JEV_MODEL` | `jev-1.13.0` | TypeSafe-supported version ID or alias, e.g. `jev-latest` |
| `JEV_MAX_INPUT_BYTES` | `30000` | Jev request JSON budget in UTF-8 bytes; range 1–30000 |
| `JEV_CONCURRENCY` | `4` | Maximum simultaneous Jev requests per run; positive integer |

`.env.example` overrides some code defaults: LAYA_API_URL uses the Compose hostname
`laya`, LAYA_MODEL is `english`, JEV_MODEL is `jev-latest`, and trusted UI origins
include `https://*.ngrok-free.app`. Existing `.env` values
are not overwritten. For native DeciFlow or an external Laya host, set the reachable
URL explicitly. Both CPU and CUDA publish port 8000.
At UI startup, explicit `DECISION_ENGINE`, `LAYA_*`, and `JEV_*` entries in the
mounted `.env` override the inherited engine environment. After changing them,
use Docker Desktop Restart on DeciFlow-UI (or `docker compose restart ui`), then
refresh the browser. Missing entries retain inherited values. Other settings retain
environment precedence. Changes to ports, mounts, Compose profiles, or the Laya
service require `docker compose up -d` to recreate affected containers. For native
execution, restart the Python process.
See [request/result JSON](results.md) for state, the three questions, and outputs.

`LAYA_HEAD_TOKENS=384` sends `"head_max_len": 384` in each Laya request.
`LAYA_MAX_TOKENS=1024` similarly sends `"max_len": 1024`. Both override the
checkpoint defaults for that call. Apply `.env` changes as described above.
These are DeciFlow settings; no remote Docker change is needed to send them.

**Leave `LAYA_MAX_TOKENS=` blank for built-in models.** DeciFlow automatically
selects the window from `LAYA_MODEL`: English 512, Multilingual/Typed-decisions
8192. When switching built-in models, change only `LAYA_MODEL`; no token-budget
edit is needed while this value is blank. Custom models require an explicit budget.
An explicit value overrides automatic selection. English accepts up to 512; other models up to
8192. The question budget must be positive and below the selected window.
256 is a default, not a Laya API maximum. These are **DeciFlow validation limits**.
The official checkpoint defaults are English 512/192 and the others 1024/256.
The server separately caps both overrides with `LAYA_MAX_TOKEN_BUDGET` (default
8192); exceeding its cap returns 422. Budgets appear in result JSON `inputBudget`.

Budgets are not fixed reservations: actual log space depends on the rendered
question, not simply `max_len - head_max_len`. `usage.truncated` describes log
truncation, not complete instruction preservation. When Laya reports collapsed
category options, DeciFlow marks the prediction Uncertain/Needs Review and shows
why, while preserving the original category, probabilities, and provider response.

For a custom checkpoint, register its name with remote server `LAYA_EXTRA_MODELS`,
then set `LAYA_MODEL` to that name and explicitly set `LAYA_MAX_TOKENS` within
its verified capacity. Names use letters, digits, `_` or `-`, starting with a
letter; URLs/paths are not accepted. The response must confirm the requested
custom name in `routing.model`; silent routing to another model is rejected.
DeciFlow does not install or train models.

Concurrency applies to Batch and Realtime Tasks and direct API requests. Laya v0.4.1 uses one inference
worker: `LAYA_CONCURRENCY` controls client requests, while server
`LAYA_MAX_CONCURRENT` controls admission (default 16; excess returns 503).
Neither is GPU inference parallelism. Keep server `LAYA_JEV_STRICT=0` for
truncation/routing metadata; CPU `LAYA_THREADS` should not exceed physical cores.
File Batch still sends individual requests, not a native inference batch.

Jev ignores Laya budgets. Its API has no equivalent `head_max_len` control;
Jev 1.13 limits state + longest question to 32k tokens and the full request to
64k. `JEV_MAX_INPUT_BYTES` is a conservative byte guard, not a token allocation.
Jev model availability depends on the account/API; aliases may change limits.

See [Laya integration](laya-integration.md) for request validation and
server settings. Evaluate all five profiles
with 36 labeled synthetic cases (including header variants):

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

The report includes a confusion matrix, failures, uncertain counts, and correct
predictions within the Certain group. These samples are regression probes, not a
production accuracy estimate. Use `--cases PATH` for your own labeled JSON cases
(`log`, `expected`, optional `profile`), or `--model NAME` to compare checkpoints.
Evaluation uses only Laya, never paid Jev.


## Persistent application data

`DECIFLOW_DATA_DIR` contains the following application-managed files:

| Path | Contents |
| --- | --- |
| `deciflow.sqlite3` | Sources, Criteria, Tasks, Actions, SSH Hosts, SSH Key metadata, application preferences, execution snapshots, results, reviews, and aggregates (SQLite WAL) |
| `actions/<name>-<id>/` | Action code, venv, project, and lockfile |
| `ssh-keys/<key-id>/` | Managed private key and derived public key |
| `ssh-hosts/known_hosts` | Host keys explicitly approved in DeciFlow |

Back up and protect the whole directory; it contains raw logs and private keys.
No automatic run-history cleanup is applied. Use one DeciFlow process per data
directory. Per-run engine concurrency is shared by all source Hosts; different
Tasks have separate limits. See [Tasks](tasks.md) for scheduling and storage limits.

Copying only the live database can omit data in its WAL. Stop the server before backing up the whole data directory, or use the SQLite backup API. See [Result storage](result-storage.md).

## Reset DeciFlow

Open **Settings → Configurations → Reset DeciFlow**. The in-app warning lists
what will be lost and the exact `DECIFLOW_DATA_DIR` path. Cancel, Escape, or the
close button makes no change. **Yes, Reset DeciFlow** permanently deletes entries
in that directory, including hidden files, except `ssh-keys` and its registration, after stopping the scheduler,
Tasks, and Action subprocesses and closing SQLite. The directory itself remains;
child symlinks are removed without deleting their external targets.

This removes Sources, Tasks, Actions and their environments, custom Criteria,
results/history/reviews, managed SSH Hosts, approved known_hosts, and saved
settings. SSH key files and their IDs/names are preserved and remain usable.
Back up the data directory and export any results/reviews first.
Application files, `.env`, Laya/model caches, and inputs/logs outside the data
directory remain unchanged. Put only DeciFlow-managed data in the configured root.

The server replaces its process with the original Python command; no Docker socket
or Docker control permission is required. Use one server process per data directory.
Default Criteria, sample Sources, the disabled default Task, and default settings
return. The browser waits for a new server instance and reloads; it does not retry
the destructive request. An incomplete cleanup is reported in red after restart;
check server logs before retrying. Existing Task runs do not resume because their
definitions have been deleted.

Trusted UI origins only: `POST /api/reset/status` describes the directory and
server instance; `POST /api/reset` requires
`{ "confirmation": "RESET DECIFLOW" }` and returns HTTP 202 before graceful
shutdown. Repeated requests during a reset are rejected. Protected system/project
roots and a symlink used as the data root are rejected. This maintenance API has
the same trusted-origin boundary as file and Action management; do not expose it
to untrusted users.

In **Settings → Configurations**, edit settings and select **Save Changes** at the bottom to apply them together. **Reset DeciFlow** is a separate immediate action with its own confirmation.
