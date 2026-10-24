# Configuration

[English](configuration.md) | [한국어](configuration.ko.md) | [Documentation](README.md) | [README](../README.md)

DeciFlow operational settings can be edited in **Settings → Configurations**.
Saved UI overrides take precedence over `.env`/process environment values, then
code defaults. Clearing **Use UI Override** restores the environment/default value.
The initial environment setup remains in `.env`.
Laya server settings are managed on the Laya host; Compose shares `LAYA_API_KEY`
with DeciFlow. `COMPOSE_PROFILES` selects `cpu` or `cuda`; empty starts no local Laya container.

## Environment File Locations

Choose one execution method in this recommended order: **PyPI / uv tool → Docker
Compose → Git checkout native Python**. Follow the
[uv tool guide](tool-install.md) for installation from PyPI.
`<checkout>` below means the cloned DeciFlow repository root on the host.

| Method | File Read by DeciFlow | How to Prepare or Select It |
| --- | --- | --- |
| PyPI / uv tool | `~/.config/deciflow/.env` | `deciflow init` creates templates; edit before startup |
| Git clone + Docker Compose | `<checkout>/.env` on the host, mounted at `/app/.env` in the UI container | Copy `<checkout>/.env.example` to `<checkout>/.env`; run Compose from the checkout |
| Git clone + native Python | `<checkout>/.env` | Copy the template; `uv run deciflow start --config-dir "$PWD"` and `uv run --extra laya python laya_server.py` read this file |

For uv tool, `~` is the home of the user running the command; root therefore uses
`/root/.config/deciflow/.env`. `--config-dir /path/to/deciflow-config` selects
`/path/to/deciflow-config/.env` for `init`, `config list`, `config test`, `run`, `status`, and `stop`.
Pass the same option every time. A `.env` in the shell's current directory is not
automatically selected. Initialization preserves existing files.

For Git native CLI execution, run from the checkout and select it explicitly with
`--config-dir "$PWD"`; otherwise the CLI uses `~/.config/deciflow`. The direct
`server.py` script reads the checkout file regardless of the shell directory.
Run documented commands from the checkout so relative Source paths are predictable.
The local Laya adapter reads that same checkout file. A separately deployed Laya
server has its own configuration on its own host.

Compose uses the checkout file for interpolation and the UI's `env_file`; DeciFlow
also reads the mounted `/app/.env` at startup. `docker compose --env-file ...`
alone does not change the UI's `env_file` or replace the mounted `/app/.env`.
It is not a way to switch the whole Docker deployment to the uv tool file.
`--config-dir` is a DeciFlow CLI option, not a Compose or `server.py` option.

The files are independent, with no automatic search, synchronization, or fallback
between them. To deliberately reuse a native checkout file with the installed
command, pass `--config-dir /path/to/DeciFlow`. Docker's `http://laya:8000` address
only works inside its network; host-based execution needs a reachable Laya URL.

These configuration paths are separate from `DECIFLOW_DATA_DIR` and
`DECIFLOW_LOG_DIR`. Defaults remain `/var/lib/deciflow-data` (including a blank data
setting) and `/var/log/deciflow`. Docker uses these paths inside the container and
backs them with named volumes; uv tool/native execution uses host directories.
The native quick start explicitly overrides them with `./data` and `./logs`.

## Environment Settings

| Variable | Code default (when unset) | Purpose |
| --- | --- | --- |
| `COMPOSE_PROFILES` | Unset (no local Laya) | Compose only: set cpu or cuda, exactly one; .env.example selects cpu |
| `OAUTH2_PROXY_ENABLED` | `false` | true: Google sign-in and HTTPS; false: unauthenticated HTTP demo. Docker and native |
| `DECIFLOW_BIND_HOST` | `127.0.0.1` | HTTP address when OAuth2-Proxy disabled; 0.0.0.0 allows external access. With OAuth2-Proxy enabled no UI port is published |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Shared Sources/Tasks/history/Actions/Criteria/SSH Key/host storage root; must be writable |
| `DECIFLOW_CSRF_TRUSTED_ORIGINS` | Empty | Comma-separated trusted UI origins, including optional https://*.ngrok-free.app; origin check only, not authentication. With OAuth2-Proxy enabled, uses OAUTH2_PROXY_PUBLIC_URL |
| `DECIFLOW_LOG_DIR` | `/var/log/deciflow` | Server/access logs; empty disables file logging. Compose persists logs in deciflow-logs |
| `PORT` | `4000` | UI listening port; also published by Docker when OAuth2-Proxy is disabled |
| `OAUTH2_PROXY_PUBLIC_URL` | Required when OAuth2-Proxy enabled | Public HTTPS origin including :4443; sets callback and trusted UI origin |
| `OAUTH2_PROXY_CLIENT_ID` | Required when OAuth2-Proxy enabled | Google Web application client ID |
| `OAUTH2_PROXY_CLIENT_SECRET` | Required when OAuth2-Proxy enabled | Google client secret; keep in ignored .env |
| `OAUTH2_PROXY_COOKIE_SECRET` | Required when OAuth2-Proxy enabled | Random Base64-encoded 32-byte cookie key |
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
`laya`, LAYA_MODEL is `multilingual`, and JEV_MODEL is `jev-latest`. Trusted UI origins
are empty by default; `https://*.ngrok-free.app` is an optional example. Existing `.env` values
are not overwritten. For native DeciFlow or an external Laya host, set the reachable
URL explicitly. Both CPU and CUDA publish port 8000.
UI overrides remain authoritative after restart. At UI startup, explicit `DECISION_ENGINE`, `LAYA_*`, and `JEV_*` entries in the
mounted `.env` override the inherited engine environment. After changing environment engine settings or credentials,
use **Restart DeciFlow**, Docker Desktop Restart on DeciFlow-UI, or `docker compose restart ui`, then
refresh the browser. Missing entries retain inherited values. Other settings retain
environment precedence. Changes to ports, mounts, Compose profiles, or the Laya
service require `docker compose up -d` to recreate affected containers. For native
execution, restart the Python process.
See [request/result JSON](results.md) for state, the three questions, and outputs.

After changing OAuth2-Proxy mode or the bind address, run `docker compose up -d --remove-orphans`
for Docker, or stop and start native DeciFlow again. External HTTP without OAuth2-Proxy gives
anyone who can connect access to management features.

OAuth settings are deployment settings, not UI overrides. Changing a Google client
ID/secret or cookie key requires `docker compose up -d --force-recreate oauth2-proxy`;
**Restart DeciFlow** alone does not reload the proxy. After changing
`OAUTH2_PROXY_PUBLIC_URL`, update Google's registered origin/redirect URI and run
`docker compose up -d ui oauth2-proxy`. For files and certificate renewal, see
[authentication operations](authentication.md#operations).

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
Sample Criteria, sample Sources, the disabled default Task, and default settings
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

## Runtime configurations

**Configurations → Save Changes** saves results per page and enabled runtime overrides
atomically in SQLite. Runtime fields cover Decision Engine, Laya URL/model/total and
question token budgets/concurrency, Jev model/request byte budget/concurrency, and
OpenAI Criteria authoring model. Each field shows its environment identifier, source,
application timing, concise help, and the English reference comments from `.env.example`.
Both engines' effective configuration is validated before saving. Switching to Jev
requires a configured `JEV_API_KEY` and an explicit cost confirmation; there is no fallback.
The browser reloads to reflect saved runtime settings; the server need not restart.

New runs use the saved configuration. Active runs retain their engine, model, URL,
budgets and concurrency. Recoverable new runs persist these non-secret settings and
restore them even if Configurations changed. Existing legacy runs without such a
snapshot still stop recovery if the engine/model changed. Credentials are read from
the environment and never saved in run snapshots. AI Criteria generation uses the
settings captured when that request starts.

API keys (`LAYA_API_KEY`, `JEV_API_KEY`, `OPENAI_API_KEY`) remain in `.env`; the UI
shows only whether they are set. Server port, data/log directories, trusted origins,
and Compose profiles stay under deployment control. The Environment and Deployment
section describes them without offering edits. Remote Laya model loading, GPU, workers,
ports and mounts remain settings of that host/container. A UI override never edits `.env`.

## Restart DeciFlow

**Restart DeciFlow**, below **Reset DeciFlow**, restarts only the DeciFlow Python
process without deleting application data. Its confirmation reports active runs and
unsaved configuration changes. Cancel/Escape does nothing. Active jobs are suspended
with checkpoints; eligible enabled Tasks recover under their original IDs/settings,
paused jobs stay paused, and ordinary Task recovery rules still apply. In-flight
external inference may already have reached the provider; Actions retain the existing
conservative recovery behavior. This is not a guarantee of uninterrupted or exactly-once execution.

The UI sends one confirmed restart request, waits up to 60 seconds for a new server
instance, then reloads. If the server has not returned, it displays an error; check
server logs and refresh manually. Concurrent Reset/Restart requests are rejected.
Restart reloads engine/credential entries from the mounted `.env`; it does not restart
Laya, reload its models, or apply Docker port/mount/profile/GPU changes. Recreate the
affected containers for those changes. External process invocation must support
DeciFlow's original-command process replacement; use one process per data directory.

`POST /api/configuration` reads safe metadata. `PUT /api/configuration` accepts
`resultsPerPage` and `runtimeOverrides` (only supported non-secret environment identifiers).
`POST /api/restart` requires `{ "confirmation": "RESTART DECIFLOW" }` and returns 202.
The application checks trusted origins. With `OAUTH2_PROXY_ENABLED=true`, both Docker
and native deployments require Google sign-in through OAuth2-Proxy for UI/API requests.
With false, access requires no sign-in. See [authentication](authentication.md).


## Logging

`DECIFLOW_LOG_DIR` selects DeciFlow's log directory (default `/var/log/deciflow`).
These are operational logs; the original input logs, decisions, and Action results
belong to Task History and result storage.

| File | Contents and Use | Retention |
| --- | --- | --- |
| `access.log` | HTTP client address, method, request path, and response status. Start here to find failed requests; a 200 response can still carry a failed analysis result or stream event. | Rotates at 10 MiB, keeping 5 backups |
| `server.log` | Uvicorn startup/shutdown, warnings, unhandled request exceptions, and application diagnostics for handled engine configuration, storage/I/O, Criteria generation, file-stream, background job, and reset failures. Serves the role of an error log, but includes informational messages. | Rotates at 10 MiB, keeping 5 backups |
| `daemon.log` | Created by `deciflow start --daemon`; captures startup checks, general stdout/stderr, and the managed OAuth2-Proxy output. Check it when startup or Google sign-in fails. Uvicorn server/access records use their dedicated files without duplication here. | Appends across launches; no automatic rotation |

Foreground and Docker execution retain Uvicorn console output as well as the
server/access files. Docker does not create `daemon.log`; use
`docker compose logs ui oauth2-proxy` for container console/proxy output when
OAuth2-Proxy is enabled. Laya has its own service logs.

For troubleshooting, find the request and timestamp in `access.log`, then inspect
`server.log` at the same time. Application failure diagnostics identify the operation,
exception type, code locations, and available OS/SQLite error codes. They omit
exception values, source lines, local variables, request bodies, and provider bodies
to avoid copying credentials or input data into these diagnostics. A wrapper's direct
cause is used when present. They do not provide full exception text.

Expected validation errors, access denials, and missing items are normally recorded
only by their HTTP status and response; per-event classification/Action failures and
SSH Host collection details remain in results and Task History. Engine health probes
return connection status to the UI. Not every 4xx/5xx produces a separate diagnostic,
and streaming failures can occur after HTTP 200. Uvicorn's unhandled-exception traces,
access URLs, and third-party proxy output are not automatically redacted; protect
log files and review them before sharing.

An empty `DECIFLOW_LOG_DIR` disables server/access file logging and keeps console
output; daemon mode requires a nonempty, existing, writable directory. Relative paths
are resolved from DeciFlow's working/configuration directory. Configure host log
rotation for `daemon.log`. Compose persists server/access logs in `deciflow-logs`;
use a writable bind mount if host-directory access is needed. Restart DeciFlow after
changing log settings.
