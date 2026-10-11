# DeciFlow

[English](README.md) | [한국어](README.ko.md)

**Classify logs in real time with AI and spot error and security events at a glance.**

[Demo Video](https://www.youtube.com/watch?v=wGMtxpeHHBs)

[![Watch the DeciFlow demo on YouTube](images/DeciFlow-Demo-Screenshot-2026-10-11-034530.png)](https://www.youtube.com/watch?v=wGMtxpeHHBs)

DeciFlow groups log events into chunks and classifies each chunk as **Normal, Warning, Error, Security, or Other**
with Laya or Jev. Scan a batch, follow new events, and focus your review with
category probabilities and confidence instead of reading every line unaided.
Choose a domain profile and chunk size per source; compare category counts in a
live chart and pause list updates to inspect individual results.

Logs are the starting point. Extending input handling and decision criteria could
bring the same workflow to real-time `tcpdump` traffic monitoring or manufacturing
quality decisions based on sensor and inspection data. These applications require
additional integration and domain validation; image inspection also requires a
vision model.

**DeciFlow** runs on the node containing your logs, reads events, and displays
results in a browser. The **Laya server** runs the decision model on a separate
host; **Jev** is an alternative hosted decision API. DeciFlow sends events to the
selected engine and receives predictions.

- **Use logs where they live.** Paste text or select multiple files across
  directories with wildcard patterns; no manual file merging.
- **Switch from investigation to monitoring.** Read existing files in batches or
  monitor new lines and file rotation. Newest completed predictions appear first.
- **Keep people in control.** Filter uncertain predictions, record reviewer
  corrections, and export results as JSON. Rejected events retain their original
  text for review.
- **Share inference across nodes.** Run DeciFlow on each log node and connect
  to a shared Laya server; DeciFlow nodes need no local GPU or PyTorch.
- **Choose your engine.** Use self-hosted Laya by default without Jev API charges,
  or select Jev in `.env`. Both use the same workflow; no automatic paid fallback.

For access logs, application errors, and operational events—start with an existing
log file and review the predictions in your browser.

## Architecture & Internal (DeepWiki)

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![Flow Diagram of Quickstart/Tutorial](images/DeciFlow-Architecture.png)

## Quick start

Choose **Laya or Jev** below; configure only one engine.
For container startup, see [Run DeciFlow with Docker](#run-deciflow-with-docker).

Requires **Python 3.11+** and **uv** on the DeciFlow node. A separate Laya server
or the Jev API handles inference, so this node needs no Docker or CUDA.
Create and activate the virtual environment, then install dependencies from the
DeciFlow directory (Linux/macOS/WSL, Bash):

```bash
uv venv
source .venv/bin/activate
uv sync
```

If `.env` does not exist, copy [.env.example](.env.example) to `.env`.
Apply the settings for your chosen engine:

### Use the Laya decision engine

Connect to an existing shared Laya server, or set up one on a remote host below.
If a server is already available, skip setup and configure DeciFlow.

The instructions below use Docker run on the Laya host. Docker Compose is an
alternative; see the official guide linked below and choose only one method.

This guide uses Docker to simplify Laya server setup for both CPU and CUDA.
CUDA additionally requires an NVIDIA driver and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Check the GPU and driver with `nvidia-smi`: its `CUDA Version` describes driver
support, not the installed Toolkit. `nvcc --version` checks a local Toolkit,
which these containers do not require. A CUDA 13.0 image requires a compatible GPU
and [driver 580 or newer](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).

#### Docker run

Use **`call518/deciflow-laya:cpu`** or **`call518/deciflow-laya:cuda`**.
No clone or build is needed. Copy the required script to the Laya host and run
**only one** of the CPU/CUDA commands below.

CPU: [run-deciflow-laya-cpu.sh](scripts/run-deciflow-laya-cpu.sh)

```bash
bash scripts/run-deciflow-laya-cpu.sh
```

CUDA: [run-deciflow-laya-cuda.sh](scripts/run-deciflow-laya-cuda.sh)

```bash
bash scripts/run-deciflow-laya-cuda.sh
```

The scripts explicitly set `--env LAYA_API_KEY=changeme`; exporting a different
key does not override this argument. For deployment, change this argument and set
the same key in DeciFlow's `.env`.

The scripts use port **8000**, preload `multilingual`, and share the
`deciflow-laya-model-cache` volume. CUDA exposes all GPUs to the container.
To change the host interface/port, edit `--publish HOST_IP:HOST_PORT:8000` and
update `LAYA_API_URL`. Both scripts use `DeciFlow-Laya`; stop/remove the existing
container before switching CPU/CUDA or changing settings.

> **NOTE:** For Docker Compose deployment, see the official
> [Laya Docker guide — HTTP serving](https://nandhakishorm.github.io/laya/docker/#http-serving).

#### Check and manage

Use the server's key in `LAYA_API_KEY` for the health request (default: `changeme`).

```bash
curl --fail --silent --show-error \
  --header "Authorization: Bearer ${LAYA_API_KEY:-changeme}" \
  http://127.0.0.1:8000/health
```

On the DeciFlow node, replace `127.0.0.1` with the server address. Inspect
`checkpoint_devices`/`device` and `cpu_fallbacks` to verify actual GPU use.
Restrict Laya access to trusted DeciFlow nodes and use TLS over external networks.
Keep `LAYA_JEV_STRICT=0` for required truncation metadata. Initial model loading
can take several minutes; inspect container logs for startup errors.

| Action | Docker run |
| --- | --- |
| Status | `docker ps --filter name=DeciFlow-Laya` |
| Logs | `docker logs --tail=100 DeciFlow-Laya` |
| Stop | `docker stop DeciFlow-Laya` |
| Resume | `docker start DeciFlow-Laya` |
| Remove | `docker rm DeciFlow-Laya` after stopping |

Removal preserves the model cache. Use only one deployment method at a time.

#### Custom Docker run images (optional)

Build from Laya **v0.4.1** only when you need your own image. Run the CPU **or** CUDA
build command for your target:

```bash
git clone --branch v0.4.1 --depth 1 https://github.com/NandhaKishorM/laya.git
cd laya

docker build \
  --build-arg TORCH_INDEX=cpu \
  --tag my-laya:cpu .

docker build \
  --build-arg TORCH_INDEX=cu130 \
  --tag my-laya:cuda .
```

Replace the image in the chosen Docker run script with your custom tag.
`cpu` installs CPU-only PyTorch; `cu130` means CUDA **13.0**. Select a CUDA build
supported by your GPU/driver and the Dockerfile's `TORCH_VERSION` using the
[PyTorch installation list](https://pytorch.org/get-started/previous-versions/).
Validate API compatibility when upgrading Laya.

#### DeciFlow connection

On the DeciFlow node, set the shared Laya server URL and matching API key in `.env`:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

### Use the Jev decision engine

Obtain a TypeSafe API key from the [Jev setup guide](https://docs.typesafe.ai/introduction/quickstart)
and set it in `.env`. Jev is paid; no Laya server is needed.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### Run DeciFlow

```bash
uv run python server.py
```

Open **http://127.0.0.1:4000**. Restart DeciFlow after configuration changes.

## Run DeciFlow with Docker

Choose this **instead of the Python startup above**. The DeciFlow host needs
Docker, not local Python/uv/CUDA. Configure `.env` for either Laya or Jev first;
Laya inference still runs on the separate Laya server.

Run these commands from your cloned DeciFlow directory. The image contains only
Python and uv; your repository is mounted read-only at `/app`. On startup,
`uv sync --frozen` installs the checked-out version’s dependencies into a separate
Docker volume. The first startup requires network access for package downloads.

```bash
docker build --tag deciflow:local .

docker run --detach \
  --name deciflow \
  --init \
  --restart unless-stopped \
  --mount "type=bind,src=$(pwd),dst=/app,readonly" \
  --mount type=volume,src=deciflow-venv,dst=/opt/deciflow-venv \
  --publish 127.0.0.1:4000:4000 \
  --mount type=bind,src=/var/log,dst=/host-logs,readonly \
  deciflow:local
```

Open **http://127.0.0.1:4000**. Host `/var/log` is available as `/host-logs` in
Batch/Realtime (e.g. `/host-logs/messages`); mount other directories read-only as needed. If `.env` uses
another `PORT`, adjust both port numbers above. For remote browser access, change
the publish address to the DeciFlow host's IP.

Use a Laya URL reachable from the container; `127.0.0.1` names the container,
not the host or remote Laya server. Sidebar host/OS/IP information describes the
container. DeciFlow reads the mounted `/app/.env` on each startup; settings supplied
with Docker `--env` take precedence. Restart after changing `.env`:

```bash
docker restart deciflow
```

Existing containers created with `--env-file .env` must be recreated once using
the command above and the rebuilt image. Port mappings and mounts still require
container recreation when changed.
For source changes or a different Git version, restart with `docker restart deciflow`;
no image rebuild is needed. Refresh the browser after UI changes. Rebuild the image
only when changing the Dockerfile’s runtime. Stop DeciFlow before switching versions.

For ngrok/reverse-proxy file access, set `DECIFLOW_CSRF_TRUSTED_ORIGINS` to the
UI origin, e.g. `https://your-domain.ngrok-free.app`, or
`https://*.ngrok-free.app` for changing ngrok domains (no trailing slash),
and restart the container. Empty allows file access only through localhost.
This setting controls the CSRF Origin check, not CORS, login authentication, or
CSRF token validation. Wildcards also trust other users’ subdomains; protect public
access with proxy authentication.

## Configuration

DeciFlow settings live in `.env`; process environment variables take precedence.
Laya server settings are managed separately on the Laya host.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DECISION_ENGINE` | `laya` | `laya` or `jev` |
| `PORT` | `4000` | DeciFlow web port |
| `LAYA_API_URL` | `http://127.0.0.1:8000/v1/systemone` | Full Laya URL, including any proxy prefix |
| `LAYA_API_KEY` | `changeme` | Key matching the Laya server |
| `LAYA_MODEL` | `multilingual` | Built-in or registered custom checkpoint name; server must provide it |
| `LAYA_MAX_TOKENS` | Blank | Sent as `max_len`; blank keeps built-in defaults; required for custom models |
| `LAYA_HEAD_TOKENS` | `256` | Sent as `head_max_len`; question/option budget, below the total window |
| `LAYA_CONCURRENCY` | `4` | Maximum simultaneous Laya requests per run; positive integer |
| `JEV_API_KEY` | Unset | Jev API key |
| `JEV_MODEL` | `jev-1.13.0` | TypeSafe-supported version ID or alias, e.g. `jev-latest` |
| `JEV_MAX_INPUT_BYTES` | `30000` | Jev request JSON budget in UTF-8 bytes; range 1–30000 |
| `JEV_CONCURRENCY` | `4` | Maximum simultaneous Jev requests per run; positive integer |

`LAYA_HEAD_TOKENS=384` sends `"head_max_len": 384` in each Laya request.
`LAYA_MAX_TOKENS=1024` similarly sends `"max_len": 1024`. Both override the
checkpoint defaults for that call. Restart DeciFlow after editing `.env`.
These are DeciFlow settings; no remote Docker change is needed to send them.

Blank `LAYA_MAX_TOKENS` keeps DeciFlow's built-in windows: English 512,
Multilingual/Typed-decisions 8192. English accepts up to 512; other models up to
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

See the [integration review](docs/laya-integration-review.md) for parameter
behavior and implemented versus deferred improvements. Evaluate all five profiles
with 36 labeled synthetic cases (including header variants):

```bash
uv run python -m scripts.evaluate_laya --output /tmp/laya-validation.json
```

The report includes a confusion matrix, failures, uncertain counts, and correct
predictions within the Certain group. These samples are regression probes, not a
production accuracy estimate. Use `--cases PATH` for your own labeled JSON cases
(`log`, `expected`, optional `profile`), or `--model NAME` to compare checkpoints.
Evaluation uses only Laya, never paid Jev.

## Usage

On wide screens, the left **40%** shows **Classification overview → Log input**;
the right **60%** shows **Classification results**. Narrow screens stack the panels.
The sidebar identifies the DeciFlow log source host by hostname, detected IPs, and
OS/version. In WSL or containers, these identify that environment, not its host OS;
IPs are not a full interface inventory. **Ready to connect** reports configuration,
not a successful connection to the decision engine.

### Input and criteria

**Realtime** is selected by default. Each mode starts with editable examples.

| Mode | What DeciFlow reads |
| --- | --- |
| Realtime | New lines after existing files' end; new/replacement files from the beginning |
| Batch | Matching files from the beginning to EOF |
| Paste | Pasted text grouped into chunks |

Mode identifiers in the UI and exported JSON are `realtime`, `batch`, and `paste`.
The file API also accepts legacy `follow` and returns `realtime`.

File sources are on the **DeciFlow node**, not the Laya host. They require local
browser access (`localhost`/`127.0.0.1`) and readable UTF-8 regular files. Enter one
path or pattern per line; absolute paths, multiple directories, `*`, `?`, `[abc]`,
and recursive `**` are supported. Relative paths start at DeciFlow's working
directory. Batch needs matching files; Realtime can wait for new matches.
Batch reads selected files concurrently and interleaves ready chunks, preserving
each file’s line order, profile, and chunk size. Engine concurrency limits apply
to the entire run, not separately to each file; a limit of 1 serializes requests.

Choose **Criteria** and **Events/chunk** for each path/pattern or for Paste.
Defaults: **General system**, **1 event per chunk**. Currently, each nonempty line
is one event; multiline boundaries are not yet detected. Every profile uses `choice` with
**Normal, Warning, Error, Security, Other**; only the descriptions and instructions
differ. Laya and Jev use the same selected profile. Type detection is manual;
`score` and `noul` are not used.

| Criteria profile | Focus |
| --- | --- |
| General system | System/service operation and failures |
| Authentication | Authentication/session outcomes, service failures, and abuse |
| HTTP access | Responses, request failures, and suspicious access |
| Application | Application operations, exceptions, and dependencies |
| Network / tcpdump text | Connection/packet evidence in text; binary PCAP is unsupported |

Edit/add a JSON file in [`profiles/`](profiles/) and restart DeciFlow to update the
selector. Keep `label`, `instructions`, `criteria`, and the existing five category
keys. Describe event outcomes and evidence; keep specific log strings in evaluation
samples rather than adding message-by-message exceptions to production criteria.

Chunks never mix files. Batch flushes remaining events at EOF; Realtime flushes at
the configured size or after one second without a new event, and separates
file rotations. Blank lines are skipped; event boundaries are not automatically
detected. Overlapping matches with identical settings are deduplicated by resolved
path; conflicting settings are rejected. Chunking does not bypass model budgets.

General system separates routine operation (Normal), recoverable problems
(Warning), explicit failures (Error), and evidenced abuse or policy violations
(Security). A service name, IP address, or security-related topic is not evidence
of an incident. These criteria guide predictions; validate your deployed model
against representative logs before relying on the categories.

Authentication distinguishes unsuccessful individual attempts (Warning), service
or supporting-mechanism failures (Error), and evidence of abuse (Security).
Other means an unrelated or unidentifiable outcome, not merely unknown root cause.
For recognized **single-line classic syslog**, Authentication removes timestamp,
hostname, and PID from model input while preserving service and message contents
(users, IPs, ports). Original logs remain intact; changed `decisionInput` appears
in JSON. Multiline chunks and unrecognized formats are unchanged. Normalization
reduces input variation; it does not guarantee identical predictions or accuracy.

### Results and controls

Newest **completed** chunks appear first, with 100 results per page; this is
completion order, not log timestamp order. File locations show **File line(s)**
for Batch and **Observed line(s)** for Realtime—the sequence read since monitoring
started or the file rotated. `1 event (max 5)` means one event was submitted
with a configured maximum of five. JSON uses `chunkEvents` for the configured
limit and `eventCount` for actual events. `line`, `lineEnd`, and `lineCount`
retain line locations/counts. Legacy API input `chunkLines` remains accepted;
new requests and results use `chunkEvents`.

**Uncertain** marks selected category probability (`answerProbability`) below 70% or a top-two category probability
gap below 10 percentage points. The model's choice and probabilities are preserved;
the UI shows provisional candidates, and JSON records candidates, the gap, and
review reasons. Other and failed requests also require review. These thresholds
are review heuristics, not accuracy guarantees; provider `confidence` scales differ
between engines and are preserved separately; they do not determine Uncertain. Filter **All results / Needs review / No review needed**. Category filtering
and case-insensitive literal search of original log text combine with the review
filter. **Source**, after Search logs, filters by an entered path/pattern and shows
completed counts, including failures. Overlapping patterns retain all matches in
`sourcePatterns`; files are still processed once. Filters affect the list only,
not metrics, chart, or JSON export.

| Control | Behavior |
| --- | --- |
| Pause updates / Resume updates | Freeze/unfreeze the list, including before the first result; analysis, metrics, and chart continue. Filters/pages use the frozen list; the button counts pending results. |
| Stop processing | Cancel file readers and pending engine requests; retain completed results, discard unsubmitted chunks. Remote inference already running may finish. |
| View JSON | Expand one result, including failures, profile/chunk metadata, and reviewer edits. Expanded state survives list refreshes. Copy inside the JSON panel copies the current result, including reviewer edits. |
| Reviewer category | Record `reviewerCategory`; does not change AI category, review status, chart, or train the model. |
| Export JSON | After processing finishes or stops, export all received results—including those not displayed while paused. |

**Classification overview** combines AI category counts across all sources,
including uncertain choices. Counts are **chunks**, not raw lines; percentages use
successfully classified chunks. Failed requests are shown separately. Filters and
reviewer edits do not change the chart. Choose **All / Uncertain / Certain** to chart all
classified chunks or just one certainty group; percentages use the selected group.
Certain means no Uncertain flag, not verified accuracy. The failure count always
shows all failed requests, which belong to neither certainty group.
**Truncated** counts responses reporting `usage.truncated=true` across all groups;
these rejected predictions are included in failures, not category bars. Missing
truncation metadata and local byte-budget rejections are not counted as truncated.
This is log/state truncation, not a count of shortened question instructions.

Result JSON keeps `requestedModel`, UTC `requestedAt`, request size, input budget,
and the question/criteria snapshot. `providerResponse` preserves the returned
model, `routing` (actual checkpoint), `usage` (tokens/truncation), and full answer
metadata, including provider confidence fields and action/abstention when present.
Top-level `answerProbability` is the probability of the selected category;
`confidence` remains the original provider value. `uncertaintyBasis` identifies
the selected-category scale used by the fixed 70% threshold.
HTTP status and available request-ID/inference-time headers are retained;
credentials and authorization headers are excluded. API failures and rejected
predictions retain available diagnostics too. `model` alone may be a generic
Laya name: inspect `providerResponse.routing` for the actual checkpoint.

Results and reviewer edits live **only in browser memory**. Refreshing/closing the
page loses them; a newly started run replaces them. Export before leaving or
starting another run. No saved history or JSON import is provided.

### Timing metrics

| Metric | Meaning |
| --- | --- |
| Processed chunks | Completed results, including failed requests |
| Needs review | Selected category probability below 70%, close probabilities, Other, or request failure; not an error count |
| Throughput | Successfully classified chunks/s over the last 5 seconds, including idle time; uses elapsed time during the first 5 seconds; freezes when stopped/completed |
| Total elapsed time | Time since the run started, including idle periods |
| Active processing time | Time with at least one request in flight, counting overlap once; percentage of total elapsed time |
| Average processing time | Mean completed request duration, including failures; per chunk |

Active and average times include network/server wait. Active time excludes idle
periods and stays within 0–100% of elapsed time; it is not CPU/GPU utilization or
pure inference time. Timing refreshes once per second while waiting; stopping or
disconnecting retains the last snapshot, which may lag by about one second.

## Limits

- No application file-size or line-count cap; RAM and browser capacity still matter.
  File reads are incremental. Chunks use an event count; each nonempty line currently forms one event.
  Automatic multiline event-boundary detection is not implemented.
- **Laya:** selected checkpoint; request windows and question budgets are listed above.
  The [official HTTP server](https://nandhakishorm.github.io/laya/http-api/#limits)
  also limits state to 50,000 characters and requests to 2 MiB; verify the deployed version.
  Truncated responses or missing truncation metadata are rejected.
- **Jev:** `jev-1.13.0`, [32k state + longest question, 64k full request](https://docs.typesafe.ai/models).
  The byte budget is a conservative guard, not a token count or acceptance guarantee.
- Rejected events retain their original text for review; other events continue.
  Source read/UTF-8 errors stop processing and preserve completed results.
- Each chunk makes one request. Engine concurrency settings default to 4 per run;
  timeouts are Laya 120s and Jev 30s. Higher client concurrency does not guarantee
  parallel inference or higher throughput; server capacity and admission limits apply.
- Realtime polls every 250ms and waits for complete lines. Rotation leftovers are
  marked `incomplete`; line numbers reset on rotation. Rapid rotation or
  copy-truncate/regrowth can lose events. File deduplication does not remove duplicate
  contents; avoid matching both active logs and their rotated copies.
- Laya sends logs to your server; Jev sends them to TypeSafe and incurs API charges.
  DeciFlow does not save logs/results to server disk. Remove sensitive data before
  submission and never commit `.env`. Public deployment needs authentication and
  usage limits.

`Ctrl+C` stops DeciFlow, waiting up to two seconds before cancelling remaining
requests. Browser-memory results are not saved by server shutdown.

## Development

For real-model results and remaining limitations, see [Laya log validation](docs/laya-validation.md).
Re-run the selected Laya model on the 13 labeled examples:

```bash
uv run python -m scripts.evaluate_laya \
  --cases tests/fixtures/general_evaluation.json \
  --output /tmp/laya-validation.json
```

This calls your Laya server only; it refuses paid Jev. The small sample is not an
accuracy guarantee.

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pyright
uv run pytest
```

UI regression test (requires Node.js only for testing):

```bash
node --test tests/test_ui.mjs
```

Tests cover both providers without paid calls, input budgets, streaming,
cancellation, and file discovery/rotation. Keep both READMEs and actual/example
`.env` files synchronized; environment comments use English and Korean.

For optional local Laya development (0.3.20):

```bash
uv sync --extra laya
uv run --extra laya python laya_server.py
```

Set DeciFlow's `LAYA_API_URL` to loopback and start DeciFlow in another terminal. Use this
adapter for 0.3.20; it adds token-budget checks and truncation metadata missing from
that version's HTTP server. Set local server options through process environment
variables. DeciFlow nodes using a separate Laya server do not need the `laya` extra.

[Laya](https://github.com/NandhaKishorM/laya) · [Jev](https://docs.typesafe.ai/introduction/quickstart)

## Implementation status and roadmap

`[x]` Implemented · `[ ]` Planned (listed in priority order).

| Status | Item | Features / target |
| --- | --- | --- |
| [x] | Log sources | Realtime, Batch, Paste; multiple paths, wildcards, concurrent file reads, discovery and rotation tracking |
| [x] | Criteria and chunks | Five profiles; per-source Events/chunk; original logs and source metadata retained |
| [x] | Decision engines | Laya/Jev; model, input budget and concurrency settings in `.env`; shared validation |
| [x] | Analysis UI | Category chart; review, category and source filters; text search and source counts |
| [x] | Monitoring and controls | Throughput and timing metrics; stop processing; pause/resume list updates |
| [x] | Results | Individual JSON view/copy, full export and reviewer annotations |
| [x] | Diagnostics | Uncertainty reasons, truncation counts, provider responses and request metadata |
| [x] | Deployment | Docker with mounted source; `.env` reload on restart; trusted-origin checks |
| [x] | Verification | Python/UI regression tests and labeled-case Laya evaluation tool |
| [ ] | Classification quality | Expand labeled logs; compare profiles/models and category errors; evaluate log-specific checkpoints |
| [ ] | Question preservation | Verify instructions and choices with the deployed tokenizer, separately from log truncation |
| [ ] | Persistent results | Restore runs, results and reviews after refresh/restart; reuse reviewed labels for evaluation |
| [ ] | **Multiline events** | Recognize variable-length Python/Java stack traces and other event boundaries; group complete events using Events/chunk |
| [ ] | Profile suggestions | Validate automatic type/profile suggestions while retaining manual selection |
| [ ] | Inference throughput | Benchmark Laya inference batch API and GPU capacity; retain cancellation and Realtime responsiveness |
| [ ] | Realtime recovery | Save read positions; recover reconnects; verify loss/duplication during rapid rotation and copy-truncate |
| [ ] | Long-running sessions | Limit browser memory and aggregation costs; incrementally load retained results; benchmark large runs |
| [ ] | Shared access | Add authentication, per-user file permissions and request limits |

Currently, **one nonempty line is one event**. Events/chunk groups events but does
not detect multiline boundaries. Inference batching is separate from multi-file
Batch mode. Certain is a model-based flag, not verified accuracy.
