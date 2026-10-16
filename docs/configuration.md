# Configuration

[English](configuration.md) | [한국어](configuration.ko.md) | [Documentation](README.md) | [README](../README.md)

DeciFlow settings live in `.env`; process environment variables take precedence.
Laya server settings are managed on the Laya host; Compose shares `LAYA_API_KEY`
with DeciFlow. `COMPOSE_PROFILES` selects `cpu` or `cuda`; empty starts only the UI.

| Variable | Code default (when unset) | Purpose |
| --- | --- | --- |
| `COMPOSE_PROFILES` | Unset (UI only) | Compose only: set cpu or cuda, exactly one; .env.example selects cpu |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `DECIFLOW_DATA_DIR` | `/var/lib/deciflow-data` | Shared Sources/Actions/Criteria/SSH key/host storage root; must be writable |
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
Apply Compose environment changes with `docker compose up -d`; `restart` does not
reload `env_file` values. For native execution, restart the Python process.
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
category options, DeciFlow marks the prediction Uncertain/Needs review and shows
why, while preserving the original category, probabilities, and provider response.

For a custom checkpoint, register its name with remote server `LAYA_EXTRA_MODELS`,
then set `LAYA_MODEL` to that name and explicitly set `LAYA_MAX_TOKENS` within
its verified capacity. Names use letters, digits, `_` or `-`, starting with a
letter; URLs/paths are not accepted. The response must confirm the requested
custom name in `routing.model`; silent routing to another model is rejected.
DeciFlow does not install or train models.

Concurrency applies to Paste, Batch, and Realtime. Laya v0.4.1 uses one inference
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

