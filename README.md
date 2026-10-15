<p align="center">
  <img src="images/DeciFlow-Logo.png" alt="DeciFlow" width="480">
</p>

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

Each chunk receives three decisions in one Laya or Jev request: **`choice` for category**,
**`score` for urgency** (0–3: Low, Medium, High, Critical), and **`noul` for the
probability that a work ticket is needed**. Urgency is a probability-weighted score,
not a rounded grade. Results show both values and retain all answers in JSON.
DeciFlow does not create tickets automatically.

**DeciFlow** runs on the node containing your logs, reads events, and displays
results in a browser. The **Laya server** runs the decision model on the same or a separate
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

## Architecture

[![Ask DeepWiki](https://img.shields.io/badge/Ask-DeepWiki-blue)](https://deepwiki.com/call518/DeciFlow)

![DeciFlow architecture](images/DeciFlow-Architecture.png)

## Quick start — Docker + Laya CPU

**Requires:** Git and Docker with the Compose plugin on one Linux host.
A compatible NVIDIA GPU can improve Laya's inference performance; see
[Run with GPU (CUDA)](#laya-gpu). This quick start
uses CPU so you can try DeciFlow across a wider range of environments.
Laya runs the decision engine; DeciFlow runs log analysis and the web UI in a second container.

### 1. Prepare the repository

```bash
git clone https://github.com/call518/DeciFlow.git
cd DeciFlow
# Only if .env does not exist / 기존 .env가 없다면
test -f .env || cp .env.example .env
```

### 2. Configure CPU execution

Set these values in `.env`. The `laya` hostname resolves inside the Compose network
for both CPU and CUDA. Keep your existing API key; Compose passes it to both containers.

```dotenv
COMPOSE_PROFILES=cpu
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya:8000/v1/systemone
PORT=4000
```

### 3. Start the containers

```bash
docker compose up -d
docker compose logs --follow laya-cpu
```

Wait for the initial model download/loading, then press `Ctrl+C` to leave the log viewer.
[Check readiness](#laya-health) before continuing.

### 4. Analyze sample logs

Open **http://127.0.0.1:4000** on the same host and select **Batch**.
Keep only `/host-logs/sample-logs/access-100.log`, select **HTTP access** criteria,
**Events/chunk: 1**, and **Action: None**, then start analysis.

For optional GPU acceleration, see [Docker deployment details](#laya-docker);
for a paid API, see [Jev](#jev).
The default key `changeme` is for trials. Change it in `.env` before deployment.

## Usage and configuration

| Guide | Contents |
| --- | --- |
| [Usage](docs/usage.md) | Input modes, criteria, filters, human review, reconnecting, timing |
| [Configuration](docs/configuration.md) | Environment variables, models, input budgets |
| [Criteria](docs/criteria.md) | Manage fixed-category profiles; Default Criteria is view-only |
| [Python Actions](docs/actions.md) | Configuration viewing, environment Status, pip-enabled environments, Reset venv, revision history, deletion, source assignment |
| [Result JSON](docs/results.md) | Real response example and field reference |

Sidebar views have URLs: Main `/`, Criteria `/#criteria`, Actions `/#actions`.
Reloading, browser history, and direct links retain the selected view.

- **Paste:** Analyze pasted text.
- **Batch:** Analyze existing files. Docker maps host `/var/log` to `/host-logs/var/log`.
- **Realtime:** Follow new logs; choose criteria and chunk size per source.
- **Processing status:** Success / Failed / Total shows classified, failed, and total completed chunks. Action Success / Failed / Total counts follow-up executions separately. Needs review
  counts successful classifications only. Engine connection shows the last actual request; initially Not checked.
- **Review:** Filter Needs review, record corrections, and export JSON. Certain does not
  guarantee accuracy. Export results you need to keep: restarting the server loses jobs/results.

## Docker deployment details

<a id="laya-docker"></a>

### Use the Laya decision engine

Connect to an existing shared Laya server, or set up one on a remote host below.
If a server is already available, skip setup and configure DeciFlow.

Use [docker-compose.yml](docker-compose.yml) from the cloned repository on the Laya
host. CPU is the default in `.env.example`; a compatible NVIDIA GPU can improve
inference performance. Actual performance varies with hardware and workload.

#### CPU execution

Set `COMPOSE_PROFILES=cpu` in `.env`, then run:

```bash
docker compose up -d laya-cpu
```

For Laya and DeciFlow together, use `docker compose up -d` instead.
Both Laya variants publish host port **8000**, share the `deciflow-laya-model-cache`
volume, and preload `english`, `multilingual`, and `typed-decisions`.
Choose exactly one profile; CPU and CUDA cannot run together with this configuration.
`LAYA_API_KEY` in `.env` configures both Laya and DeciFlow; an empty key disables authentication.

<a id="laya-gpu"></a>

#### Optional: GPU acceleration (CUDA)

CUDA additionally requires a compatible NVIDIA GPU, a driver, and
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Check the GPU and driver with `nvidia-smi`: its `CUDA Version` describes driver
support, not the installed Toolkit. These containers need no local CUDA Toolkit.
The CUDA 13.0 image requires [driver 580 or newer](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html).
The CUDA service reserves all GPUs; the CPU service requests none.

To switch an existing deployment, export any results you need, then stop the current
stack **before editing the profile**:

```bash
docker compose down
```

Set `COMPOSE_PROFILES=cuda` in `.env`, then run:

```bash
docker compose up -d
docker compose logs --follow laya-cuda
```

To return to CPU, follow the same steps with `COMPOSE_PROFILES=cpu`.
The internal URL `http://laya:8000/v1/systemone` stays the same.

<a id="laya-health"></a>

#### Check and manage

Use the server's key for the health request. This command reads it inside the
selected container without printing it; replace `laya-cpu` with `laya-cuda` for CUDA:

```bash
docker compose exec laya-cpu python -c 'import os, urllib.request; r = urllib.request.Request("http://127.0.0.1:8000/health", headers={"Authorization": "Bearer " + os.environ["LAYA_API_KEY"]}); print(urllib.request.urlopen(r).read().decode())'
```

For CUDA, inspect `checkpoint_devices`/`device` and `cpu_fallbacks` to verify GPU use.
Restrict Laya access to trusted DeciFlow nodes and use TLS over external networks.
Keep `LAYA_JEV_STRICT=0` for required truncation metadata. Initial model loading can
take several minutes; inspect container logs for startup errors.

| Action | Command |
| --- | --- |
| Status | `docker compose ps` |
| Logs | `docker compose logs --tail=100` |
| Stop | `docker compose stop` |
| Resume | `docker compose start` |
| Remove containers | `docker compose down` |

`down` preserves named volumes. Do not add `--volumes` if you need to keep data.
Choose either native execution or Docker.

#### DeciFlow connection

For the same Compose stack, set `LAYA_API_URL=http://laya:8000/v1/systemone`.
For an external Laya server, set its reachable URL and matching API key in `.env`:

```dotenv
DECISION_ENGINE=laya
LAYA_MODEL=multilingual
LAYA_API_URL=http://laya-server.example:8000/v1/systemone
LAYA_API_KEY=changeme
PORT=4000
```

Run only the UI with `docker compose up -d ui`; no local Laya is started.
For native DeciFlow on the Laya host, use `http://127.0.0.1:8000/v1/systemone` instead.

<a id="jev"></a>

### Use the Jev decision engine

Obtain a TypeSafe API key from the [Jev setup guide](https://docs.typesafe.ai/introduction/quickstart)
and set it in `.env`. Jev is paid; no Laya server is needed.

```dotenv
DECISION_ENGINE=jev
JEV_MODEL=jev-1.13.0
JEV_API_KEY=your-typesafe-api-key
PORT=4000
```

### DeciFlow Docker

Choose this **instead of the Python startup in the appendix**. The DeciFlow host needs
Docker with Compose, not local Python/uv/CUDA. Configure `.env` for Laya or Jev first.
For external Laya or Jev, set `COMPOSE_PROFILES=` and start only the UI:

```bash
docker compose up -d ui
```

Compose uses the published `call518/deciflow-ui:0.0.1` image from Docker Hub.
The image provides Python, uv, and operational utilities. The repository is mounted
read-only at `/app`; `uv sync --frozen` installs dependencies into `deciflow-venv`
on startup. Initial startup needs network access. Compose passes `.env` to the UI;
`PORT` controls both host and container ports (default: 4000).

The UI is published on all host interfaces. For local-only access, change its
Compose port mapping to `127.0.0.1:${PORT:-4000}:${PORT:-4000}`.
Open **http://127.0.0.1:4000** with the default port; use the DeciFlow host IP for remote access.
The `deciflow-data` volume stores Actions and Criteria at `DECIFLOW_DATA_DIR`
(default: `/var/lib/deciflow-data`); `deciflow-logs` stores server logs.
Use absolute container paths for custom data/log directories.

#### Mount host log directories

Host `/var/log` and repository `sample-logs` are mounted read-only at
`/host-logs/var/log` and `/host-logs/sample-logs`. For other logs, add a mount under
`services.ui.volumes` in `docker-compose.yml`:

```yaml
      - /your/logs:/host-logs/custom:ro
```

Apply mount changes with `docker compose up -d ui`. Export needed results first;
recreating the UI loses server-memory jobs/results. In the UI, use the container
path `/host-logs/custom/app.log`. The process needs permission to read host files.

#### Connection settings and restart

The Compose Laya address is `http://laya:8000/v1/systemone`; for an external server,
use an address reachable from the container. `127.0.0.1` refers to the UI container.
Sidebar host/OS/IP information describes the container.
After changing `.env`, run `docker compose up -d` to recreate affected containers;
`restart` alone does not refresh the environment supplied by Compose.
For source changes, run `docker compose restart ui` and refresh the browser after UI
changes. If you modify the Dockerfile, build the UI image explicitly with
`docker build --tag call518/deciflow-ui:0.0.1 .`, then run
`docker compose up -d --force-recreate ui`.
Stop DeciFlow before switching source versions.

#### Migrate from the launch scripts

Export results you need, then stop and remove the old containers once before
starting Compose (these commands preserve named volumes):

```bash
docker stop DeciFlow-UI DeciFlow-Laya-CPU DeciFlow-Laya-CUDA
docker rm DeciFlow-UI DeciFlow-Laya-CPU DeciFlow-Laya-CUDA
```

Include only container names that exist. Compose reuses the existing data, logs,
venv, and model-cache volumes. Set `COMPOSE_PROFILES=cpu` or `cuda` and, for the local
stack, `LAYA_API_URL=http://laya:8000/v1/systemone` in `.env` before starting it.
CPU's published port changes from 8001 to 8000; update external DeciFlow connections.

For ngrok/reverse-proxy file access, set `DECIFLOW_CSRF_TRUSTED_ORIGINS` to the
UI origin, e.g. `https://your-domain.ngrok-free.app`, or
`https://*.ngrok-free.app` for changing ngrok domains (no trailing slash),
and run `docker compose up -d ui`. Empty allows file access only through localhost.
This setting controls the CSRF Origin check, not CORS, login authentication, or
CSRF token validation. Wildcards also trust other users’ subdomains; protect public
access with proxy authentication.

## Limits

- No application file-size or line-count cap; RAM and browser capacity still matter.
  File reads are incremental. Chunks use an event count; each nonempty line currently forms one event.
  Automatic multiline event-boundary detection is not implemented.
- **Laya:** selected checkpoint; request windows and question budgets are in the [configuration reference](docs/configuration.md).
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
requests and background jobs. Server-memory jobs and results are lost on shutdown.

## Appendix — Potential applications

Logs are the starting point. Extending input handling and decision criteria could
bring the same workflow to real-time `tcpdump` traffic monitoring or manufacturing
quality decisions based on sensor and inspection data. These applications require
additional integration and domain validation; image inspection also requires a
vision model.

## Appendix — Run directly on the host

Choose this instead of DeciFlow Docker startup. The DeciFlow host needs Python 3.11+
and uv. Use the same Laya Docker server or Jev connection settings; DeciFlow needs no GPU
when connecting to a separate Laya server. Prepare `.env` in the repository and configure
one engine, then run:

```bash
uv sync
uv run python server.py
```

For native DeciFlow, set `LAYA_API_URL` in `.env` to the reachable Laya server URL
(for Laya on the same host: `http://127.0.0.1:8000/v1/systemone`). The Compose-only
hostname `laya` does not resolve outside its Docker network.

Open **http://127.0.0.1:4000**. Startup creates the default Criteria file, so shared storage must be writable. If the default
`/var/lib/deciflow-data` is not writable, set `DECIFLOW_DATA_DIR=./data`
in `.env`. Restart DeciFlow after configuration changes.

## Appendix — Custom Docker images (optional)

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

Replace the selected Laya service image in `docker-compose.yml` with your custom tag.
`cpu` installs CPU-only PyTorch; `cu130` means CUDA **13.0**. Select a CUDA build
supported by your GPU/driver and the Dockerfile's `TORCH_VERSION` using the
[PyTorch installation list](https://pytorch.org/get-started/previous-versions/).
Validate API compatibility when upgrading Laya.

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

### DeciFlow HTTP logs

Set `DECIFLOW_LOG_DIR=/var/log/deciflow` in `.env` and restart DeciFlow to write timestamped
`server.log` (startup and server errors) and `access.log` (client, request, HTTP status),
while retaining console logs. The default is `/var/log/deciflow`; missing directories
are created automatically with parent directories, requiring write permission. Relative paths start at the project directory. Each
file rotates at 10 MiB with 5 backups. Empty disables file logging. This does not
record browser interactions or classification results. For Docker, use a writable
container path and bind-mount it to retain logs on the host.
